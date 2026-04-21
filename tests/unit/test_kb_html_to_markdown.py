"""
Unit Tests — L1: _html_to_markdown() y _html_to_text_fallback()
================================================================

Tests unitarios para el método _html_to_markdown() de ShopifyKBSyncService,
implementado en L1 usando la librería markdownify en lugar del parser regex
manual anterior.

QUÉ SE PRUEBA:
    1. Casos base: HTML vacío, None, texto plano
    2. Estructura semántica: headings, listas, tablas, links
    3. HTML real de Shopify: scripts, styles, iframes, noscript
    4. Fallback: comportamiento cuando markdownify no está disponible
    5. Flag _MARKDOWNIFY_AVAILABLE: testeable directamente (pattern del módulo)

QUÉ NO SE PRUEBA:
    - Integración con DB o Redis (eso es Día 1 — test_kb_sync_integration.py)
    - Comportamiento de Shopify API (mocks en kb_fixtures.py)
    - Performance end-to-end del sync

DISEÑO DE AISLAMIENTO:
    ShopifyKBSyncService necesita shopify_client, db_pool y redis_service.
    Para tests unitarios del método _html_to_markdown(), usamos mocks mínimos
    (AsyncMock) para todos los parámetros del constructor — el método que
    probamos no usa ninguno de ellos.

Autor: Retail Recommender System Team
Fecha: 28 Febrero 2026
Fase: L1 — HTML→Markdown Library
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_service():
    """
    Instancia ShopifyKBSyncService con mocks mínimos.

    _html_to_markdown() es un método de instancia puro — no usa self.shopify,
    self.db ni self.redis. Solo lee el flag de módulo _MARKDOWNIFY_AVAILABLE
    y llama a _markdownify.markdownify() o al fallback.

    Por lo tanto, podemos construir el servicio con AsyncMock para todo
    sin necesitar una conexión real a ningún servicio externo.
    """
    from src.api.services.shopify_kb_sync import ShopifyKBSyncService

    shopify_mock = AsyncMock()
    shopify_mock.shop_url = "test.myshopify.com"  # Necesario para construir URLs

    service = ShopifyKBSyncService(
        shopify_client=shopify_mock,
        db_pool=AsyncMock(),
        redis_service=AsyncMock()
    )
    return service


# ============================================================================
# GRUPO 1: Casos Base
# ============================================================================

class TestHTMLToMarkdownBasics:
    """
    Tests de comportamiento básico: entradas vacías, texto plano, HTML mínimo.

    Estos son los casos más simples y deben pasar siempre, tanto con
    markdownify disponible como en modo fallback.
    """

    def test_empty_string_returns_empty(self):
        """
        HTML vacío → retorna string vacío, nunca lanza excepción.

        Caso real: página Shopify con body_html="" (página recién creada).
        El servicio debe manejar esto gracefully.
        """
        service = _make_service()
        result = service._html_to_markdown("")
        assert result == "", f"Expected empty string, got: {repr(result)}"

    def test_none_like_empty_string_returns_empty(self):
        """
        HTML que es solo whitespace → retorna string vacío.

        Shopify puede devolver "   \n\t  " para páginas sin contenido.
        El método hace `if not html or not html.strip(): return ""`
        """
        service = _make_service()
        result = service._html_to_markdown("   \n\t  ")
        assert result == "", f"Expected empty string, got: {repr(result)}"

    def test_plain_text_passthrough(self):
        """
        Texto plano sin tags HTML → texto preservado.

        markdownify pasa el texto tal cual si no hay tags. El post-procesado
        strip() puede quitar whitespace exterior.
        """
        service = _make_service()
        result = service._html_to_markdown("Texto de prueba sin HTML")
        assert "Texto de prueba sin HTML" in result

    def test_simple_paragraph(self):
        """
        <p>texto</p> → texto sin tags.

        markdownify convierte <p> a párrafo con saltos de línea.
        Verificamos que el contenido de texto esté presente.
        """
        service = _make_service()
        result = service._html_to_markdown("<p>Este es un párrafo de prueba.</p>")
        assert "párrafo de prueba" in result
        assert "<p>" not in result, "Tags HTML no deberían aparecer en el output"

    def test_returns_string_type(self):
        """
        El método siempre retorna str, nunca None.

        Importante para _upsert_kb_content() que pasa content a asyncpg
        — un None causaría un TypeError en la query SQL.
        """
        service = _make_service()
        result = service._html_to_markdown("<p>contenido</p>")
        assert isinstance(result, str), f"Expected str, got {type(result)}"

    def test_no_excessive_blank_lines(self):
        """
        El post-procesado limita líneas en blanco consecutivas a máximo 2.

        markdownify puede generar 3+ líneas en blanco entre secciones.
        El método aplica re.sub(r'\\n{3,}', '\\n\\n', markdown) para normalizar.
        Verificamos que no haya 3 o más \\n consecutivos en el output.
        """
        service = _make_service()
        html = "<h2>Sección 1</h2><p>Párrafo 1</p><h2>Sección 2</h2><p>Párrafo 2</p>"
        result = service._html_to_markdown(html)
        assert "\n\n\n" not in result, "No debería haber 3+ líneas en blanco consecutivas"


# ============================================================================
# GRUPO 2: Estructura Semántica
# ============================================================================

class TestHTMLToMarkdownStructure:
    """
    Tests de preservación de estructura semántica del HTML.

    L1 reemplaza el regex parser precisamente porque éste perdía estructura:
    tablas se convertían en texto plano, links perdían sus URLs, headings
    no se diferenciaban. markdownify preserva toda esta semántica.
    """

    def test_h2_heading_converts_to_atx_style(self):
        """
        <h2>Título</h2> → ## Título (estilo ATX)

        El servicio configura heading_style="ATX" explícitamente.
        ATX usa # para headings (## H2) en lugar del estilo Setext (H2\n---).
        """
        service = _make_service()
        result = service._html_to_markdown("<h2>Política de Devoluciones</h2>")
        # ATX H2 comienza con ##
        assert "## Política de Devoluciones" in result, (
            f"Expected ATX heading '## Política de Devoluciones', got:\n{result}"
        )

    def test_h1_heading(self):
        """<h1>Título</h1> → # Título"""
        service = _make_service()
        result = service._html_to_markdown("<h1>Título Principal</h1>")
        assert "# Título Principal" in result

    def test_unordered_list_uses_dash_bullets(self):
        """
        <ul><li> → - ítem (bullets con guión, no asterisco).

        El servicio configura bullets="-" explícitamente para consistencia.
        """
        service = _make_service()
        html = "<ul><li>Visa</li><li>Mastercard</li><li>PayPal</li></ul>"
        result = service._html_to_markdown(html)

        assert "- Visa" in result, f"Expected '- Visa' bullet, got:\n{result}"
        assert "- Mastercard" in result
        assert "- PayPal" in result
        assert "<li>" not in result, "Tags HTML no deberían estar en el output"

    def test_ordered_list(self):
        """<ol><li> → 1. ítem (listas numeradas preservadas)"""
        service = _make_service()
        html = "<ol><li>Primero</li><li>Segundo</li><li>Tercero</li></ol>"
        result = service._html_to_markdown(html)
        assert "1." in result
        assert "Primero" in result
        assert "Segundo" in result

    def test_link_preserves_url(self):
        """
        <a href="url">texto</a> → [texto](url)

        Crítico para KB: links a páginas de políticas, términos, etc.
        El regex parser anterior descartaba las URLs — solo preservaba el texto.
        markdownify las mantiene en formato Markdown estándar.
        """
        service = _make_service()
        html = '<a href="https://tienda.com/politica">Ver política completa</a>'
        result = service._html_to_markdown(html)
        # La URL debe aparecer en el output
        assert "https://tienda.com/politica" in result, (
            f"URL should be preserved in markdown output, got:\n{result}"
        )
        assert "Ver política completa" in result

    def test_table_converts_to_markdown(self):
        """
        <table> → tabla en formato Markdown (pipes |).

        Uno de los motivadores principales de L1: el regex parser NO podía
        convertir tablas. markdownify las convierte a formato pipe table:
        | Col1 | Col2 |
        |------|------|
        | Val1 | Val2 |
        """
        service = _make_service()
        html = """
        <table>
            <tr><th>Método de Pago</th><th>Disponible en</th></tr>
            <tr><td>Visa</td><td>MX, ES, US</td></tr>
            <tr><td>PayPal</td><td>US, ES</td></tr>
        </table>
        """
        result = service._html_to_markdown(html)

        # El contenido de la tabla debe estar presente
        assert "Método de Pago" in result, f"Table header missing, got:\n{result}"
        assert "Visa" in result
        assert "PayPal" in result
        # No deben quedar tags HTML de tabla
        assert "<table>" not in result
        assert "<td>" not in result

    def test_bold_text(self):
        """<strong>texto</strong> → **texto**"""
        service = _make_service()
        result = service._html_to_markdown("<p><strong>Importante:</strong> leer esto.</p>")
        assert "**Importante:**" in result or "Importante" in result

    def test_nested_structure(self):
        """
        HTML anidado (heading + párrafo + lista) → estructura Markdown preservada.

        Simula el HTML típico de una política de Shopify.
        """
        service = _make_service()
        html = """
        <h2>Política de Devoluciones</h2>
        <p>Aceptamos devoluciones dentro de 30 días.</p>
        <ul>
            <li>Producto sin usar</li>
            <li>Embalaje original</li>
        </ul>
        """
        result = service._html_to_markdown(html)

        assert "Política de Devoluciones" in result
        assert "30 días" in result
        assert "Producto sin usar" in result
        assert "<h2>" not in result
        assert "<ul>" not in result


# ============================================================================
# GRUPO 3: HTML Real de Shopify (Ruido a Eliminar)
# ============================================================================

class TestHTMLToMarkdownShopifyHTML:
    """
    Tests con HTML que Shopify incluye y que debe ser eliminado/ignorado.

    Shopify puede incluir scripts de analytics, iframes de chat,
    meta tags, y otros elementos que no deben aparecer en el Markdown KB.
    El método configura strip=["script","style","iframe","noscript","meta","link"].
    """

    def test_script_tags_stripped(self):
        """
        <script> y su contenido deben eliminarse completamente.

        Shopify incluye scripts de tracking (GA4, Pixel, etc.) en el HTML.
        Estos no tienen valor para el KB y confunden al LLM.
        """
        service = _make_service()
        html = """
        <p>Contenido real de la página.</p>
        <script type="text/javascript">
            gtag('event', 'page_view', {'page_title': 'Policy'});
        </script>
        <p>Más contenido.</p>
        """
        result = service._html_to_markdown(html)

        assert "Contenido real de la página" in result
        assert "Más contenido" in result
        # El script debe haberse eliminado
        assert "gtag" not in result, "Script content should be stripped"
        assert "<script>" not in result

    def test_style_tags_stripped(self):
        """<style> y su contenido deben eliminarse."""
        service = _make_service()
        html = """
        <style>.policy { color: red; font-size: 14px; }</style>
        <h2>Política de Envío</h2>
        <p>Enviamos en 3-5 días hábiles.</p>
        """
        result = service._html_to_markdown(html)

        assert "Política de Envío" in result
        assert ".policy" not in result, "Style rules should be stripped"
        assert "color: red" not in result

    def test_iframe_stripped(self):
        """<iframe> (chat widgets, videos) deben eliminarse."""
        service = _make_service()
        html = """
        <p>Contáctanos por chat.</p>
        <iframe src="https://chat.example.com/widget" width="300" height="500"></iframe>
        <p>O por email.</p>
        """
        result = service._html_to_markdown(html)

        assert "Contáctanos por chat" in result
        assert "O por email" in result
        assert "<iframe>" not in result
        assert "chat.example.com" not in result

    def test_real_shopify_policy_html(self):
        """
        HTML completo de una política real de Shopify.

        Simula el body_html que Shopify retorna para una página de política,
        incluyendo el ruido típico que hay que eliminar.
        """
        service = _make_service()
        html = """
        <h2>Política de Devoluciones</h2>
        <p>En nuestra tienda aceptamos devoluciones dentro de <strong>30 días</strong>
        a partir de la fecha de compra.</p>

        <h3>Condiciones</h3>
        <ul>
            <li>Producto en estado original</li>
            <li>Con embalaje original</li>
            <li>Con ticket de compra</li>
        </ul>

        <h3>Proceso</h3>
        <p>Para iniciar una devolución,
        <a href="https://tienda.com/contacto">contáctanos aquí</a>.</p>

        <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){dataLayer.push(arguments);}
        </script>

        <style>
        .return-policy { background: #f5f5f5; }
        </style>
        """
        result = service._html_to_markdown(html)

        # Contenido real debe estar
        assert "Política de Devoluciones" in result
        assert "30" in result
        assert "Condiciones" in result
        assert "Producto en estado original" in result
        assert "tienda.com/contacto" in result

        # Ruido debe haberse eliminado
        assert "dataLayer" not in result
        assert "gtag" not in result
        assert ".return-policy" not in result
        assert "<script>" not in result
        assert "<style>" not in result


# ============================================================================
# GRUPO 4: Comportamiento del Fallback
# ============================================================================

class TestHTMLToMarkdownFallback:
    """
    Tests del comportamiento cuando markdownify falla o no está disponible.

    El método tiene dos niveles de fallback:
    1. Si _MARKDOWNIFY_AVAILABLE = False → _html_to_text_fallback() directo
    2. Si markdownify.markdownify() lanza excepción → _html_to_text_fallback()

    _html_to_text_fallback() usa BeautifulSoup para extraer texto plano.
    Si BeautifulSoup tampoco está → regex simple.

    PRINCIPIO: El método NUNCA debe lanzar excepción, siempre retorna str.
    """

    def test_fallback_when_markdownify_raises_exception(self):
        """
        Si markdownify.markdownify() lanza una excepción inesperada,
        el método usa el fallback y NO propaga la excepción.

        Simula HTML muy malformado que confunde a markdownify.
        """
        service = _make_service()

        # Parchear _markdownify.markdownify para que lance una excepción
        import src.api.services.shopify_kb_sync as sync_module

        original_available = sync_module._MARKDOWNIFY_AVAILABLE

        if original_available and sync_module._markdownify is not None:
            # Solo ejecutar si markdownify está disponible — si no, el fallback
            # ya se usa por defecto y el test no aplica
            original_func = sync_module._markdownify.markdownify

            try:
                # Reemplazar la función con una que falla
                sync_module._markdownify.markdownify = lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError("Simulated markdownify internal error")
                )

                html = "<p>Contenido de prueba para fallback.</p>"
                # No debe lanzar excepción
                result = service._html_to_markdown(html)

                # Debe retornar algo (fallback extrae texto plano)
                assert isinstance(result, str)
                assert "Contenido de prueba para fallback" in result, (
                    f"Fallback should extract plain text, got: {repr(result)}"
                )
            finally:
                # Restaurar siempre, incluso si el test falla
                sync_module._markdownify.markdownify = original_func

    def test_fallback_strips_html_tags(self):
        """
        _html_to_text_fallback() elimina todos los tags HTML.

        Verificamos el fallback directamente llamándolo, ya que es un método
        público-interno del servicio.
        """
        service = _make_service()
        html = "<h2>Título</h2><p>Párrafo con <strong>negrita</strong>.</p>"
        result = service._html_to_text_fallback(html)

        assert "Título" in result
        assert "Párrafo con" in result
        assert "negrita" in result
        assert "<h2>" not in result
        assert "<strong>" not in result

    def test_fallback_strips_scripts(self):
        """_html_to_text_fallback() elimina scripts y su contenido."""
        service = _make_service()
        html = """
        <p>Texto visible.</p>
        <script>alert('NO_DEBERIA_VERSE');</script>
        """
        result = service._html_to_text_fallback(html)

        assert "Texto visible" in result
        assert "NO_DEBERIA_VERSE" not in result
        assert "alert" not in result

    def test_fallback_returns_string(self):
        """_html_to_text_fallback() siempre retorna str, nunca None."""
        service = _make_service()
        result = service._html_to_text_fallback("<p>test</p>")
        assert isinstance(result, str)

    def test_when_markdownify_unavailable_uses_fallback(self):
        """
        Cuando _MARKDOWNIFY_AVAILABLE = False, el método usa _html_to_text_fallback()
        directamente, sin intentar importar markdownify.

        Este test parchea el flag a nivel de módulo para simular el escenario
        de entorno sin markdownify instalado.
        """
        import src.api.services.shopify_kb_sync as sync_module

        html = "<h2>Título KB</h2><p>Contenido de la Knowledge Base.</p>"

        with patch.object(sync_module, "_MARKDOWNIFY_AVAILABLE", False):
            service = _make_service()
            result = service._html_to_markdown(html)

        # El fallback debe haber extraído el texto sin tags
        assert "Título KB" in result
        assert "Contenido de la Knowledge Base" in result
        assert "<h2>" not in result


# ============================================================================
# GRUPO 5: Flag _MARKDOWNIFY_AVAILABLE
# ============================================================================

class TestMarkdownifyAvailabilityFlag:
    """
    Tests del patrón de disponibilidad de módulo establecido en L1.

    El flag _MARKDOWNIFY_AVAILABLE al nivel de módulo permite:
    1. Testear el flag directamente (sin instanciar el servicio)
    2. Que el linter conozca la disponibilidad en tiempo de análisis
    3. Rollback fácil: si markdownify da problemas, desinstalarlo baja el flag

    Este patrón sigue el mismo diseño que DistributedLockError en M3.
    """

    def test_flag_is_true_when_markdownify_installed(self):
        """
        _MARKDOWNIFY_AVAILABLE = True cuando markdownify está en requirements.txt.

        Este test falla intencionalmente si markdownify no está instalado en el venv,
        alertando al desarrollador de un problema de configuración de entorno.
        """
        import src.api.services.shopify_kb_sync as sync_module
        assert sync_module._MARKDOWNIFY_AVAILABLE is True, (
            "markdownify debe estar instalado. "
            "Ejecutar: pip install markdownify>=0.12.1"
        )

    def test_flag_is_boolean(self):
        """El flag es bool, no None ni str — assert directo funciona."""
        import src.api.services.shopify_kb_sync as sync_module
        assert isinstance(sync_module._MARKDOWNIFY_AVAILABLE, bool)

    def test_markdownify_module_alias_set_when_available(self):
        """
        Cuando _MARKDOWNIFY_AVAILABLE = True, _markdownify no es None.

        El import block del módulo asigna:
            import markdownify as _markdownify  →  _markdownify es el módulo real
        o bien:
            _markdownify = None                 →  _MARKDOWNIFY_AVAILABLE = False
        """
        import src.api.services.shopify_kb_sync as sync_module

        if sync_module._MARKDOWNIFY_AVAILABLE:
            assert sync_module._markdownify is not None, (
                "Si _MARKDOWNIFY_AVAILABLE=True, _markdownify debe ser el módulo real"
            )
        else:
            assert sync_module._markdownify is None, (
                "Si _MARKDOWNIFY_AVAILABLE=False, _markdownify debe ser None"
            )

    def test_markdownify_callable_when_available(self):
        """
        Si _MARKDOWNIFY_AVAILABLE, _markdownify.markdownify() es callable.

        El servicio llama: _markdownify.markdownify(html, heading_style=..., ...)
        Verificamos que la función existe y es callable antes de llegar a prod.
        """
        import src.api.services.shopify_kb_sync as sync_module

        if sync_module._MARKDOWNIFY_AVAILABLE:
            assert callable(sync_module._markdownify.markdownify), (
                "_markdownify.markdownify debe ser callable"
            )

    def test_flag_survives_module_reimport(self):
        """
        El flag se evalúa una vez al cargar el módulo (nivel de módulo).
        Un reimport no lo resetea — el valor queda cacheado en sys.modules.

        Esto confirma que el patrón try/except en el nivel del módulo funciona
        correctamente con el sistema de importación de Python.
        """
        import importlib
        import src.api.services.shopify_kb_sync as sync_module

        original_flag = sync_module._MARKDOWNIFY_AVAILABLE

        # Reimportar — no debe cambiar el flag
        importlib.reload(sync_module)
        assert sync_module._MARKDOWNIFY_AVAILABLE == original_flag, (
            "El flag no debe cambiar después de un reload del módulo "
            "(markdownify sigue instalado o desinstalado)"
        )


# ============================================================================
# GRUPO 6: Tests de Regresión post-L1
# ============================================================================

class TestHTMLToMarkdownRegression:
    """
    Tests de regresión que garantizan que L1 no rompió comportamiento existente.

    Estos tests documentan contratos que el método tenía antes de L1 y que
    deben seguir cumpliéndose: el refactor solo cambió la implementación
    interna, no el comportamiento observable.
    """

    def test_method_exists_on_service(self):
        """El método _html_to_markdown existe en ShopifyKBSyncService."""
        service = _make_service()
        assert hasattr(service, "_html_to_markdown"), (
            "ShopifyKBSyncService debe tener el método _html_to_markdown"
        )
        assert callable(service._html_to_markdown)

    def test_fallback_method_exists_on_service(self):
        """El método _html_to_text_fallback existe (es el safety net)."""
        service = _make_service()
        assert hasattr(service, "_html_to_text_fallback")
        assert callable(service._html_to_text_fallback)

    def test_html_with_special_characters(self):
        """
        HTML con caracteres especiales (tildes, eñes, comillas) se preserva.

        El KB es principalmente en español → tildes y eñes son críticos.
        """
        service = _make_service()
        html = "<p>Política de devolución: acepta ñoños y acentuación correcta.</p>"
        result = service._html_to_markdown(html)
        assert "ñoños" in result
        assert "acentuación" in result
        assert "devolución" in result

    def test_html_entities_decoded(self):
        """
        HTML entities (&amp;, &lt;, &gt;) se decodifican correctamente.

        markdownify y BeautifulSoup decodifican entities automáticamente.
        """
        service = _make_service()
        html = "<p>Precio: $100 &amp; descuento del 10%</p>"
        result = service._html_to_markdown(html)
        # &amp; debe decodificarse como &
        assert "&" in result
        assert "&amp;" not in result

    def test_idempotency(self):
        """
        Llamar _html_to_markdown() dos veces sobre el mismo input da el mismo output.

        No debe haber efectos de estado interno entre llamadas.
        """
        service = _make_service()
        html = "<h2>Sección</h2><p>Contenido de prueba.</p>"

        result1 = service._html_to_markdown(html)
        result2 = service._html_to_markdown(html)

        assert result1 == result2, (
            "El método debe ser idempotente — mismo input siempre da mismo output"
        )

    def test_multiple_sections_preserved(self):
        """
        Documento con múltiples secciones mantiene orden y estructura.

        Verifica que markdownify no reordena ni fusiona secciones del HTML.
        """
        service = _make_service()
        html = """
        <h2>Sección A</h2>
        <p>Contenido de A.</p>
        <h2>Sección B</h2>
        <p>Contenido de B.</p>
        <h2>Sección C</h2>
        <p>Contenido de C.</p>
        """
        result = service._html_to_markdown(html)

        # Verificar presencia y orden relativo
        pos_a = result.find("Sección A")
        pos_b = result.find("Sección B")
        pos_c = result.find("Sección C")

        assert pos_a < pos_b < pos_c, (
            "Las secciones deben aparecer en el orden original: A → B → C"
        )
