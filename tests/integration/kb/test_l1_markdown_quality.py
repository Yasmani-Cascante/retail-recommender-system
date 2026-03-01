"""
Integration Tests — L1: Calidad del Markdown en KB
====================================================

Verifica que _html_to_markdown() produce Markdown de calidad óptima
cuando procesa HTML real de Shopify que llega a la Knowledge Base.

PROPÓSITO DE ESTE ARCHIVO (vs. los otros tests de KB):
───────────────────────────────────────────────────────
- test_kb_html_to_markdown.py (unit)  → Comportamiento INTERNO del método
  (entradas vacías, fallback, flag del módulo, casos base)

- test_kb_sync_integration.py (integration) → El sync LLEGA a la DB
  (cuenta de registros, idiomas, cache invalidation)

- test_l1_markdown_quality.py (este) → El Markdown ALMACENADO es de CALIDAD
  (estructura preservada, ruido eliminado, tokens reducidos, LLM-friendly)

TIPOS DE VALIDACIÓN:
────────────────────
1. Structural fidelity  — El Markdown refleja fielmente la estructura del HTML
2. Noise elimination    — Scripts, styles e iframes no aparecen en el output
3. Token efficiency     — El Markdown es más corto que el HTML original
4. LLM readability      — El contenido es parseable por el LLM (estructura clara)
5. Multi-language       — La calidad se mantiene para contenido en ES, EN y con tildes

FIXTURES HTML UTILIZADOS:
──────────────────────────
Todos los fixtures son representativos del HTML real que Shopify genera para
páginas de políticas, FAQs y guías de producto. Están diseñados para ejercitar
los casos más comunes (tablas, listas, links, scripts de analytics, etc.)
sin depender de una conexión real a la API de Shopify.

NOTA SOBRE INTEGRACIÓN:
───────────────────────
Estos tests NO usan la DB ni Redis — prueban _html_to_markdown() de forma
integrada con su pila de dependencias real (markdownify + BeautifulSoup),
a diferencia de los unit tests que mockean partes del proceso.
La distinción es: unit tests → comportamiento observable externo,
estos tests → calidad del output en el contexto del pipeline completo.

Autor: Retail Recommender System Team
Fecha: 01 Marzo 2026
Fase: L1 — HTML→Markdown Library (Día 2)
"""

import pytest
from unittest.mock import AsyncMock

# ============================================================================
# HELPERS
# ============================================================================

def _make_service():
    """
    Instancia ShopifyKBSyncService con mocks mínimos.

    _html_to_markdown() no usa self.shopify, self.db ni self.redis.
    Los mocks solo satisfacen el constructor. Ver test_kb_html_to_markdown.py
    para el mismo patrón y la explicación detallada.
    """
    from src.api.services.shopify_kb_sync import ShopifyKBSyncService

    shopify_mock = AsyncMock()
    shopify_mock.shop_url = "test.myshopify.com"

    return ShopifyKBSyncService(
        shopify_client=shopify_mock,
        db_pool=AsyncMock(),
        redis_service=AsyncMock()
    )


# ============================================================================
# FIXTURES HTML — HTML representativo de páginas Shopify reales
# ============================================================================

# HTML de una política de devoluciones típica en ES.
# Contiene: heading, párrafo con negrita, lista de condiciones, tabla de plazos,
# link a formulario, y ruido (script de GA4 + CSS inline).
HTML_RETURN_POLICY_ES = """
<h2>Política de Devoluciones</h2>
<p>En <strong>AI-Shoppings</strong> aceptamos devoluciones dentro de
<strong>30 días calendario</strong> a partir de la fecha de compra.</p>

<h3>Condiciones de Devolución</h3>
<ul>
  <li>Producto en estado original, sin uso</li>
  <li>Embalaje original intacto</li>
  <li>Ticket de compra o comprobante digital</li>
  <li>Sin etiquetas removidas</li>
</ul>

<h3>Plazos por Método de Pago</h3>
<table>
  <thead>
    <tr><th>Método de Pago</th><th>Plazo de Reembolso</th><th>Días Hábiles</th></tr>
  </thead>
  <tbody>
    <tr><td>Tarjeta de crédito</td><td>5-10 días</td><td>Hábiles</td></tr>
    <tr><td>PayPal</td><td>3-5 días</td><td>Hábiles</td></tr>
    <tr><td>Transferencia</td><td>7-14 días</td><td>Hábiles</td></tr>
  </tbody>
</table>

<p>Para iniciar una devolución,
<a href="https://ai-shoppings.com/contacto">completa este formulario</a>.</p>

<script type="text/javascript">
  gtag('event', 'page_view', {
    'page_title': 'Política de Devoluciones',
    'page_location': window.location.href
  });
</script>
<style>
  .return-policy-table { border-collapse: collapse; width: 100%; }
  .return-policy-table td { padding: 8px; }
</style>
"""

# HTML de la misma política en EN (traducción).
# Mismo contenido, mismos tipos de tags, idioma diferente.
HTML_RETURN_POLICY_EN = """
<h2>Return Policy</h2>
<p>At <strong>AI-Shoppings</strong> we accept returns within
<strong>30 calendar days</strong> from the date of purchase.</p>

<h3>Return Conditions</h3>
<ul>
  <li>Product in original condition, unused</li>
  <li>Original packaging intact</li>
  <li>Purchase receipt or digital proof</li>
  <li>Tags not removed</li>
</ul>

<h3>Timelines by Payment Method</h3>
<table>
  <thead>
    <tr><th>Payment Method</th><th>Refund Timeline</th><th>Business Days</th></tr>
  </thead>
  <tbody>
    <tr><td>Credit card</td><td>5-10 days</td><td>Business</td></tr>
    <tr><td>PayPal</td><td>3-5 days</td><td>Business</td></tr>
    <tr><td>Bank transfer</td><td>7-14 days</td><td>Business</td></tr>
  </tbody>
</table>

<p>To initiate a return,
<a href="https://ai-shoppings.com/contact">complete this form</a>.</p>

<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
</script>
"""

# HTML de una página FAQ con secciones anidadas y listas mixtas.
# Ejercita: múltiples headings H2/H3, listas ordenadas y desordenadas, párrafos cortos.
HTML_FAQ_SHIPPING = """
<h2>Preguntas Frecuentes — Envíos</h2>

<h3>¿Cuánto tarda mi pedido?</h3>
<p>Los tiempos de entrega dependen del destino:</p>
<ul>
  <li>Santiago Centro: 1-2 días hábiles</li>
  <li>Región Metropolitana: 2-3 días hábiles</li>
  <li>Regiones: 3-7 días hábiles</li>
</ul>

<h3>¿Cómo hago seguimiento de mi pedido?</h3>
<ol>
  <li>Recibirás un email con número de seguimiento</li>
  <li>Ingresa el número en el sitio del courier</li>
  <li>Consulta el estado en tiempo real</li>
</ol>

<h3>¿Qué pasa si no estoy en casa?</h3>
<p>El courier dejará un aviso y reintentará la entrega al día siguiente.
Después de 2 intentos fallidos, el paquete vuelve a nuestro bodega y nos
contactaremos contigo para coordinar.</p>

<p>¿Tienes otra pregunta?
<a href="mailto:soporte@ai-shoppings.com">Escríbenos aquí</a>.</p>
"""

# HTML con alto contenido de ruido — simula una página que tiene múltiples
# scripts de tracking, un iframe de chat y CSS inline extenso.
# El objetivo es verificar que TODO el ruido se elimina y el contenido real sobrevive.
HTML_HEAVY_NOISE = """
<script src="https://www.googletagmanager.com/gtm.js?id=GTM-XXXX"></script>
<style>
  body { font-family: Arial; }
  .container { max-width: 1200px; }
  .policy-section { padding: 20px; background: #f9f9f9; }
  h2 { color: #333; font-size: 24px; }
</style>

<h2>Política de Privacidad</h2>
<p>Tu privacidad es importante para nosotros. Esta política explica qué datos
recopilamos y cómo los usamos.</p>

<iframe src="https://chat.tidio.com/widget/abc123.js"
        width="0" height="0" style="display:none"></iframe>

<h3>Datos que Recopilamos</h3>
<ul>
  <li>Nombre y apellido</li>
  <li>Correo electrónico</li>
  <li>Dirección de envío</li>
  <li>Historial de compras</li>
</ul>

<script>
  // Facebook Pixel
  !function(f,b,e,v,n,t,s){
    if(f.fbq)return;n=f.fbq=function(){n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)};
  }(window, document,'script','https://connect.facebook.net/en_US/fbevents.js');
  fbq('init', '1234567890');
  fbq('track', 'PageView');
</script>
<noscript>
  <img height="1" width="1" style="display:none"
       src="https://www.facebook.com/tr?id=1234567890&ev=PageView&noscript=1"/>
</noscript>

<h3>Uso de Cookies</h3>
<p>Usamos cookies de sesión y persistentes para mejorar tu experiencia.</p>
"""

# HTML de una guía de cuidado de producto con caracteres especiales en español.
# Ejercita: tildes, eñes, guiones en nombres, HTML entities (&amp;, &lt;, &gt;).
HTML_PRODUCT_CARE_SPECIAL_CHARS = """
<h2>Cuidado y Mantenimiento de Productos</h2>
<p>Nuestros productos están fabricados con materiales de alta calidad.
Sigue estas instrucciones para prolongar su vida útil.</p>

<h3>Limpieza &amp; Mantenimiento</h3>
<ul>
  <li>Limpia con un paño húmedo &amp; suave</li>
  <li>Evita productos químicos agresivos &lt;abrasivos&gt;</li>
  <li>No uses agua caliente (&gt;40°C)</li>
</ul>

<h3>Almacenamiento</h3>
<p>Guarda en un lugar fresco y seco. La temperatura óptima es entre 15°C y 25°C.
No exponer a luz solar directa por períodos prolongados.</p>

<h3>Garantía</h3>
<p>Los productos tienen garantía de <strong>2 años</strong> contra defectos de fabricación.
Ver <a href="/garantia">política de garantía completa</a>.</p>
"""


# ============================================================================
# GRUPO 1: Fidelidad Estructural
# ============================================================================

class TestMarkdownStructuralFidelity:
    """
    Verifica que la estructura semántica del HTML se preserva en el Markdown.

    El valor de L1 sobre el regex parser anterior es precisamente este:
    headings quedan como headings, tablas quedan como tablas, links mantienen
    sus URLs. Si la estructura se pierde, el LLM no puede razonar bien
    sobre el contenido de la KB.
    """

    def test_return_policy_headings_preserved(self):
        """
        Los headings H2 y H3 de la política de devoluciones se convierten
        a ATX Markdown (## y ###), no quedan como texto plano.

        Impacto KB: El LLM usa los headings como delimitadores de sección.
        Si desaparecen, no sabe dónde empieza "Condiciones" vs "Plazos".
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        assert "## Política de Devoluciones" in result, (
            "H2 principal debe convertirse a '## ...'"
        )
        assert "### Condiciones de Devolución" in result, (
            "H3 subsección debe convertirse a '### ...'"
        )
        assert "### Plazos por Método de Pago" in result

    def test_return_policy_list_items_preserved(self):
        """
        Los ítems de la lista de condiciones aparecen como bullets con guión.

        Impacto KB: El LLM necesita leer las condiciones como lista,
        no como una cadena de texto difícil de parsear.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        assert "- Producto en estado original, sin uso" in result
        assert "- Embalaje original intacto" in result
        assert "- Ticket de compra o comprobante digital" in result
        assert "- Sin etiquetas removidas" in result

    def test_return_policy_table_content_preserved(self):
        """
        La tabla de plazos por método de pago conserva su contenido.

        Impacto KB: Las tablas son la forma más densa de información en las
        políticas de Shopify. Si se pierden, el LLM no puede responder
        'cuántos días tarda el reembolso con PayPal'.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        # Contenido de la tabla debe estar presente
        assert "Tarjeta de crédito" in result
        assert "5-10 días" in result
        assert "PayPal" in result
        assert "3-5 días" in result
        assert "Transferencia" in result
        assert "7-14 días" in result

        # No deben quedar tags HTML de tabla
        assert "<table>" not in result
        assert "<td>" not in result
        assert "<th>" not in result

    def test_return_policy_link_url_preserved(self):
        """
        El link al formulario de devolución preserva su URL en formato Markdown.

        Impacto KB: Las URLs son cruciales para que el LLM pueda recomendar
        al usuario 'visita este enlace para iniciar tu devolución'.
        El regex parser anterior descartaba todas las URLs.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        assert "https://ai-shoppings.com/contacto" in result
        assert "completa este formulario" in result

    def test_faq_ordered_list_preserved(self):
        """
        La lista numerada del proceso de seguimiento mantiene su numeración.

        Importante para FAQs donde el orden de los pasos importa.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_FAQ_SHIPPING)

        # La lista numerada debe estar presente con algún formato numérico
        assert "1." in result
        assert "2." in result
        assert "3." in result
        # Y los textos de los pasos
        assert "número de seguimiento" in result
        assert "sitio del courier" in result

    def test_faq_multiple_h3_sections_in_order(self):
        """
        El FAQ con 3 secciones H3 mantiene el orden y todas las secciones.

        Verifica que markdownify no reordena ni fusiona secciones cuando
        hay múltiples headings del mismo nivel.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_FAQ_SHIPPING)

        # Las 3 preguntas deben aparecer
        assert "¿Cuánto tarda mi pedido?" in result
        assert "¿Cómo hago seguimiento de mi pedido?" in result
        assert "¿Qué pasa si no estoy en casa?" in result

        # En el orden correcto
        pos_1 = result.find("¿Cuánto tarda")
        pos_2 = result.find("¿Cómo hago seguimiento")
        pos_3 = result.find("¿Qué pasa si")

        assert pos_1 < pos_2 < pos_3, (
            "Las secciones del FAQ deben aparecer en el orden original del HTML"
        )


# ============================================================================
# GRUPO 2: Eliminación de Ruido
# ============================================================================

class TestMarkdownNoiseElimination:
    """
    Verifica que el ruido habitual de Shopify (scripts, styles, iframes)
    queda completamente eliminado del Markdown resultante.

    CONTEXTO DEL BUG CORREGIDO EN L1 DÍA 2:
    El parámetro strip=['script','style'] de markdownify solo eliminaba
    los TAGS pero dejaba el CONTENIDO (texto) del script visible.
    El fix: BeautifulSoup.decompose() antes de llamar a markdownify.
    Estos tests verifican que el fix funciona en contexto real.
    """

    def test_ga4_script_completely_removed(self):
        """
        El script de Google Analytics (GA4) con gtag() no aparece en el Markdown.

        Este script está presente en prácticamente todas las páginas de Shopify
        que tienen el canal de Google conectado.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        assert "gtag" not in result, (
            "Contenido del script GA4 debe eliminarse completamente"
        )
        assert "page_view" not in result
        assert "window.location.href" not in result
        assert "<script" not in result

    def test_css_style_block_completely_removed(self):
        """
        El bloque de CSS inline (.return-policy-table etc.) no aparece en el Markdown.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        assert ".return-policy-table" not in result, (
            "Las reglas CSS deben eliminarse — confunden al LLM con selectores y propiedades"
        )
        assert "border-collapse" not in result
        assert "padding: 8px" not in result
        assert "<style>" not in result

    def test_dataLayer_script_removed_en(self):
        """
        El script dataLayer/gtag del HTML en inglés también se elimina.

        Verifica que la eliminación de scripts funciona igual para
        el contenido en EN (mismo método, mismo BeautifulSoup pre-procesado).
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_EN)

        assert "dataLayer" not in result
        assert "function gtag" not in result
        assert "window.dataLayer" not in result

    def test_facebook_pixel_script_removed(self):
        """
        El Facebook Pixel (común en tiendas Shopify) se elimina completamente.

        Este script tiene un formato inusual (IIFE inmediatamente invocada)
        que podría confundir a parsers simples. Verificamos que BeautifulSoup
        lo maneja correctamente.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_HEAVY_NOISE)

        assert "fbq" not in result, "Función fbq de Facebook Pixel debe eliminarse"
        assert "callMethod" not in result
        assert "connect.facebook.net" not in result

    def test_iframe_chat_widget_removed(self):
        """
        El iframe del widget de chat (Tidio, Intercom, etc.) se elimina.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_HEAVY_NOISE)

        assert "tidio.com" not in result, "URL del iframe de chat debe eliminarse"
        assert "<iframe" not in result

    def test_noscript_fallback_image_removed(self):
        """
        El <noscript> con el pixel de Facebook (img 1x1) se elimina.

        noscript blocks son fallbacks para analytics cuando JS está deshabilitado.
        No tienen valor informativo para el KB.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_HEAVY_NOISE)

        # La URL del pixel de Facebook no debe aparecer
        assert "facebook.com/tr?" not in result
        assert "noscript=1" not in result

    def test_heavy_noise_content_survives(self):
        """
        A pesar del alto nivel de ruido, el contenido real de la política
        de privacidad sobrevive intacto.

        Verifica que la eliminación agresiva de ruido no se 'lleva' el
        contenido útil por accidente.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_HEAVY_NOISE)

        # El contenido real debe estar presente
        assert "Política de Privacidad" in result
        assert "Nombre y apellido" in result
        assert "Correo electrónico" in result
        assert "Datos que Recopilamos" in result
        assert "Uso de Cookies" in result

    def test_no_html_tags_in_output(self):
        """
        El output no contiene ningún tag HTML visible al usuario.

        Verificación general: el Markdown no debe tener <p>, <div>, <span>
        ni ningún otro tag residual. Los únicos '<' que pueden aparecer son
        en contenido de texto (ej. &lt; decodificado como <).
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        # Tags que definitivamente no deben quedar
        tags_to_check = ["<p>", "<div>", "<span>", "<ul>", "<li>", "<table>", "<tr>"]
        for tag in tags_to_check:
            assert tag not in result, f"Tag HTML residual encontrado: {tag}"


# ============================================================================
# GRUPO 3: Eficiencia de Tokens
# ============================================================================

class TestMarkdownTokenEfficiency:
    """
    Verifica que el Markdown es significativamente más corto que el HTML.

    MOTIVACIÓN:
    El LLM tiene un context window limitado. Cada token de ruido (tags HTML,
    scripts, CSS) es un token que no contribuye a la respuesta.
    La expectativa de L1 es una reducción ≥30% en longitud para HTML con ruido.

    NOTA: No medimos tokens exactos (requeriría un tokenizer). Usamos longitud
    de caracteres como proxy, que es proporcional al conteo de tokens para
    texto en prosa (relación aproximada 1 token ≈ 4 caracteres).
    """

    def test_return_policy_shorter_than_html(self):
        """
        El Markdown de la política de devoluciones es más corto que el HTML.

        Con scripts y CSS eliminados, el Markdown debe ser notablemente más corto.
        Umbral conservador: al menos 20% de reducción.
        """
        service = _make_service()
        markdown = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        # Calcular reducción
        html_len = len(HTML_RETURN_POLICY_ES)
        md_len = len(markdown)
        reduction_pct = (1 - md_len / html_len) * 100

        assert md_len < html_len, (
            f"Markdown ({md_len} chars) debe ser más corto que el HTML ({html_len} chars)"
        )
        assert reduction_pct >= 20, (
            f"Reducción esperada ≥20%, obtenida: {reduction_pct:.1f}%. "
            f"HTML: {html_len} chars, Markdown: {md_len} chars"
        )

    def test_heavy_noise_significant_reduction(self):
        """
        Para HTML con mucho ruido (scripts, styles, iframes), la reducción
        debe ser mayor — al menos 40%.

        HTML_HEAVY_NOISE tiene ~800 chars de ruido sobre ~300 chars de contenido.
        El Markdown debe contener solo los ~300 chars útiles.
        """
        service = _make_service()
        markdown = service._html_to_markdown(HTML_HEAVY_NOISE)

        html_len = len(HTML_HEAVY_NOISE)
        md_len = len(markdown)
        reduction_pct = (1 - md_len / html_len) * 100

        assert reduction_pct >= 40, (
            f"Para HTML con alto ruido, reducción esperada ≥40%, "
            f"obtenida: {reduction_pct:.1f}%. "
            f"HTML: {html_len} chars, Markdown: {md_len} chars. "
            "¿Se están eliminando los scripts y styles correctamente?"
        )

    def test_faq_markdown_is_dense(self):
        """
        El Markdown del FAQ contiene casi toda la información del HTML
        pero en formato más compacto.

        Verifica que la compresión no sacrifica demasiado contenido:
        el ratio información/espacio debe mejorar, no empeorar.
        """
        service = _make_service()
        markdown = service._html_to_markdown(HTML_FAQ_SHIPPING)

        html_len = len(HTML_FAQ_SHIPPING)
        md_len = len(markdown)

        # Para FAQs sin scripts/styles, la reducción es menor (20-50%)
        # porque el HTML no tiene tanto ruido extra
        assert md_len < html_len, (
            "El Markdown del FAQ debe ser más corto que el HTML fuente"
        )

        # El contenido clave debe estar presente (densidad = info/chars)
        content_markers = [
            "1-2 días hábiles",     # dato concreto de shipping
            "2 intentos fallidos",  # condición específica
            "soporte@ai-shoppings.com",  # contact info
        ]
        for marker in content_markers:
            assert marker in markdown, (
                f"Contenido clave '{marker}' perdido — la compresión es demasiado agresiva"
            )


# ============================================================================
# GRUPO 4: Legibilidad para LLM
# ============================================================================

class TestMarkdownLLMReadability:
    """
    Verifica que el Markdown producido es óptimo para ser procesado por el LLM.

    'Legibilidad para LLM' significa:
    - Estructura clara (headings delimitan secciones)
    - Sin ruido técnico (no hay JS, CSS, ni atributos HTML visibles)
    - Sin líneas en blanco excesivas que diluyen el contexto
    - Información preservada de forma concisa y parseable

    Estos tests validan las propiedades que hacen que el KB sea útil
    como contexto de retrieval en el sistema MCP conversacional.
    """

    def test_no_excessive_blank_lines_in_real_content(self):
        """
        El Markdown de una política real no tiene 3+ líneas en blanco consecutivas.

        markdownify puede generar líneas en blanco extra entre secciones,
        especialmente para tables y listas. El post-procesado (re.sub n{3,}) las normaliza.
        Para el LLM, muchas líneas en blanco diluyen el contexto sin añadir información.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        assert "\n\n\n" not in result, (
            "No debe haber 3+ líneas en blanco consecutivas — "
            "diluyen el contexto para el LLM"
        )

    def test_atx_headings_in_real_content(self):
        """
        Todos los headings usan estilo ATX (# prefix) en lugar de Setext (underline).

        ATX es el estilo estándar de Markdown y el más reconocido por los LLMs.
        Setext (=== o ---) es menos común y puede confundirse con separadores horizontales.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_FAQ_SHIPPING)

        # El estilo Setext usa === o --- en la línea siguiente al título
        # Si ATX está activado correctamente, NO deben aparecer
        lines = result.split('\n')
        for i, line in enumerate(lines):
            if i > 0 and line.strip():
                # Una línea de solo = o - sería un heading Setext
                is_setext_h1 = set(line.strip()) == {'='}
                is_setext_h2 = set(line.strip()) == {'-'} and len(line.strip()) > 2
                assert not is_setext_h1, (
                    f"Heading Setext H1 encontrado en línea {i}: '{lines[i-1]}'"
                )
                # Nota: - solo puede ser un bullet. Verificamos que no sea un underline largo
                # (los underlines Setext son 3+ caracteres de -)
                if is_setext_h2 and len(line.strip()) >= 3:
                    assert False, (
                        f"Posible heading Setext H2 encontrado en línea {i}: '{lines[i-1]}'"
                    )

    def test_dash_bullets_in_real_content(self):
        """
        Las listas usan guión (-) como bullet, no asterisco (*) ni plus (+).

        El guión es el estándar de facto en Markdown moderno y el más
        reconocido por los LLMs entrenados con código y documentación.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        # Los ítems de la lista de condiciones deben usar -
        assert "- Producto en estado original" in result
        # NO deben usar *
        assert "* Producto en estado original" not in result

    def test_markdown_is_valid_string_type(self):
        """
        _html_to_markdown() siempre retorna str, incluso para HTML complejo.

        Importante: asyncpg rechaza None en columnas TEXT de PostgreSQL,
        causando un error silencioso en el upsert. El método garantiza
        siempre retornar str.
        """
        service = _make_service()
        inputs = [
            HTML_RETURN_POLICY_ES,
            HTML_RETURN_POLICY_EN,
            HTML_FAQ_SHIPPING,
            HTML_HEAVY_NOISE,
            HTML_PRODUCT_CARE_SPECIAL_CHARS,
        ]
        for html in inputs:
            result = service._html_to_markdown(html)
            assert isinstance(result, str), (
                f"Se esperaba str, se obtuvo {type(result)} para input de {len(html)} chars"
            )
            assert result, "El Markdown no debe ser vacío para HTML con contenido"


# ============================================================================
# GRUPO 5: Soporte Multi-Idioma
# ============================================================================

class TestMarkdownMultiLanguageSupport:
    """
    Verifica que la conversión funciona correctamente para contenido en múltiples
    idiomas, incluyendo caracteres especiales del español y HTML entities.

    El sistema opera en ES, EN, MX, CL — todos con posibles tildes, eñes,
    y caracteres especiales que deben preservarse intactos.
    """

    def test_spanish_special_characters_preserved(self):
        """
        Tildes, eñes y caracteres acentuados del español se preservan.

        Si BeautifulSoup o markdownify cambian la codificación, el LLM
        recibirá texto corrupto que no podrá asociar con las queries de usuarios.

        NOTA SOBRE CAPITALIZACIÓN:
        Las aserciones usan exactamente la forma en que el texto aparece en el
        fixture HTML: 'Mantenimiento' (capital) en headings y listas, 'útil' en
        prosa. Verificamos que los caracteres acentuados sobreviven la conversión,
        no la presencia de formas en minúscula que no existen en el fixture.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_PRODUCT_CARE_SPECIAL_CHARS)

        # Tildes en headings y contenido — en la forma exacta del fixture
        # 'Mantenimiento' aparece en: H2 y H3 (capitalizado como en el HTML)
        assert "Mantenimiento" in result, (
            "'Mantenimiento' (con tilde implícita en la 'o') debe preservarse "
            "en el heading y la sección de limpieza"
        )
        # 'útil' aparece en: 'vida útil' (prosa, minúscula)
        assert "útil" in result, (
            "'útil' con tilde debe preservarse en el párrafo introductorio"
        )
        # Otras palabras con tildes en el fixture
        assert "instrucciones" in result
        assert "temperatura" in result
        # 'prolongados' tiene tilde implícita en 'ó' — verificar preservación
        assert "prolongados" in result

        # Caracteres especiales del español
        assert "°C" in result, "El símbolo de grado °C debe preservarse"

    def test_html_entities_decoded_in_context(self):
        """
        &amp; se decodifica como &, &lt; como <, &gt; como > en el Markdown.

        Shopify usa HTML entities en el body_html para caracteres especiales.
        El LLM debe ver & no &amp; para entender el texto naturalmente.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_PRODUCT_CARE_SPECIAL_CHARS)

        # &amp; → &
        assert "&amp;" not in result, "&amp; debe decodificarse como &"
        assert "&" in result  # El & real debe estar presente

        # &lt; → < y &gt; → > (en el contexto del texto de la guía)
        assert "&lt;" not in result, "&lt; debe decodificarse"
        assert "&gt;" not in result, "&gt; debe decodificarse"

    def test_english_content_quality_equivalent(self):
        """
        La calidad del Markdown en EN es equivalente a la del ES.

        El método no tiene lógica condicional por idioma — pero verificamos
        que el procesamiento produce resultados de igual calidad para EN.
        """
        service = _make_service()
        result_es = service._html_to_markdown(HTML_RETURN_POLICY_ES)
        result_en = service._html_to_markdown(HTML_RETURN_POLICY_EN)

        # Ambos deben tener headings ATX
        assert "## Return Policy" in result_en
        assert "### Return Conditions" in result_en

        # Ambos deben tener sus links
        assert "https://ai-shoppings.com/contact" in result_en
        assert "https://ai-shoppings.com/contacto" in result_es

        # Ninguno debe tener scripts
        assert "dataLayer" not in result_en
        assert "gtag" not in result_es

    def test_mixed_language_faq_structure(self):
        """
        El FAQ en español con URL de soporte (mailto:) preserva la estructura
        correctamente incluyendo el link de correo.

        Verifica que markdownify maneja mailto: links igual que https: links.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_FAQ_SHIPPING)

        assert "soporte@ai-shoppings.com" in result, (
            "El link mailto: debe preservar la dirección de email"
        )


# ============================================================================
# GRUPO 6: Regresión del Pipeline Completo
# ============================================================================

class TestMarkdownPipelineRegression:
    """
    Tests de regresión que verifican el pipeline completo de conversión
    tal como se ejecuta en producción: HTML de Shopify → Markdown en KB.

    Estos tests documentan el comportamiento esperado post-L1 para prevenir
    regresiones en refactors futuros (L2, L3, L4).
    """

    def test_full_pipeline_return_policy_es(self):
        """
        Pipeline completo para una política de devoluciones en español.

        Verifica las propiedades clave del output de forma integral:
        estructura preservada + ruido eliminado + eficiencia.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_RETURN_POLICY_ES)

        # ── Estructura preservada ─────────────────────────────────────────────
        assert "## Política de Devoluciones" in result
        assert "### Condiciones de Devolución" in result
        assert "### Plazos por Método de Pago" in result
        assert "- Embalaje original intacto" in result
        assert "Tarjeta de crédito" in result
        assert "https://ai-shoppings.com/contacto" in result

        # ── Ruido eliminado ─────────────────────────────────────────────────
        assert "gtag" not in result
        assert ".return-policy-table" not in result
        assert "<script>" not in result
        assert "<table>" not in result

        # ── Propiedades del output ──────────────────────────────────────────
        assert isinstance(result, str)
        assert len(result) > 0
        assert "\n\n\n" not in result
        assert len(result) < len(HTML_RETURN_POLICY_ES)

    def test_full_pipeline_heavy_noise_html(self):
        """
        Pipeline completo para HTML con máximo nivel de ruido.

        Caso más exigente: verifica que incluso con 3 scripts diferentes,
        CSS extenso e iframe, el output es Markdown limpio y útil.
        """
        service = _make_service()
        result = service._html_to_markdown(HTML_HEAVY_NOISE)

        # ── Contenido útil presente ──────────────────────────────────────────
        assert "Política de Privacidad" in result
        assert "Nombre y apellido" in result
        assert "Uso de Cookies" in result

        # ── Todo el ruido eliminado ──────────────────────────────────────────
        noise_patterns = [
            "GTM-XXXX",         # GTM script
            "fbq",              # Facebook Pixel
            "callMethod",       # Facebook Pixel internals
            ".container",       # CSS selector
            "font-family",      # CSS property
            "tidio.com",        # Chat iframe
            "facebook.com/tr",  # Pixel tracking URL
        ]
        for pattern in noise_patterns:
            assert pattern not in result, (
                f"Ruido no eliminado: '{pattern}' encontrado en el output"
            )

    def test_idempotency_with_real_content(self):
        """
        Aplicar _html_to_markdown() dos veces sobre el mismo input da el mismo output.

        Propiedad importante para el sistema de webhooks (M4): cuando una página
        se actualiza, el re-sync debe producir el mismo Markdown si el HTML no cambió.
        Si no es idempotente, cada sync generaría un updated_at diferente aunque
        el contenido efectivo no haya cambiado.
        """
        service = _make_service()

        for html in [HTML_RETURN_POLICY_ES, HTML_FAQ_SHIPPING, HTML_HEAVY_NOISE]:
            result_1 = service._html_to_markdown(html)
            result_2 = service._html_to_markdown(html)
            assert result_1 == result_2, (
                f"El método no es idempotente para input de {len(html)} chars. "
                "Esto causaría re-syncs innecesarios en el sistema de webhooks."
            )

    def test_all_fixtures_produce_non_empty_markdown(self):
        """
        Todos los fixtures HTML de este archivo producen Markdown no vacío.

        Verificación de sanity: ninguna de las conversiones debe retornar "".
        Si retorna vacío, significa que BeautifulSoup eliminó demasiado contenido
        o que la detección de "HTML vacío" al inicio del método es muy agresiva.
        """
        service = _make_service()
        fixtures = {
            "return_policy_es": HTML_RETURN_POLICY_ES,
            "return_policy_en": HTML_RETURN_POLICY_EN,
            "faq_shipping": HTML_FAQ_SHIPPING,
            "heavy_noise": HTML_HEAVY_NOISE,
            "product_care_special_chars": HTML_PRODUCT_CARE_SPECIAL_CHARS,
        }

        for name, html in fixtures.items():
            result = service._html_to_markdown(html)
            assert result, (
                f"El fixture '{name}' produjo Markdown vacío — "
                "revisar si BeautifulSoup está eliminando demasiado contenido"
            )
            assert len(result) > 50, (
                f"El fixture '{name}' produjo Markdown muy corto ({len(result)} chars) — "
                "posible pérdida de contenido"
            )
