"""
Tests Unitarios — webhook_security.py (M4 Incremental Sync)
============================================================

Cubre la función validate_shopify_webhook() que autentica webhooks
entrantes de Shopify mediante HMAC-SHA256.

¿Por qué importa este módulo tanto?
────────────────────────────────────
El endpoint de webhooks es público (no requiere API key propia del sistema).
Cualquier actor externo puede enviar una POST request a esa URL. La única
defensa para rechazar requests falsos/maliciosos es la validación HMAC:
  - Shopify firma cada payload con un secreto compartido.
  - Si la firma no coincide, el request no proviene de Shopify.
  - Una implementación incorrecta puede abrir la puerta a ataques de
    replay, data poisoning o consumo innecesario de recursos.

Suite de tests:
    TestValidShopifyWebhook       → casos happy-path (firmas válidas)
    TestInvalidShopifyWebhook     → casos de rechazo (firmas malas)
    TestHMACEdgeCases             → payloads vacíos, unicode, etc.
    TestTimingAttackResistance    → verificación de compare_digest

Learning para el desarrollador:
    La resistencia a timing attacks (hmac.compare_digest vs ==) es un
    patrón fundamental en cualquier validación criptográfica. Se documenta
    aquí tanto en los comentarios como en el test dedicado porque es fácil
    olvidarlo cuando se refactoriza el código.

Author: Retail Recommender — QA Team
Date:   2026-02-26
Phase:  M4 — Incremental Sync (Webhooks)
"""

import hmac
import hashlib
import base64
import time
import pytest

from src.api.core.webhook_security import validate_shopify_webhook


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# Funciones auxiliares que replican exactamente la firma que Shopify
# produce. Se usan para construir los casos de prueba de forma confiable.
# ══════════════════════════════════════════════════════════════════════════

def _compute_shopify_hmac(payload_bytes: bytes, secret: str) -> str:
    """
    Reproduce el algoritmo de firma de Shopify.

    Shopify calcula:
        HMAC = base64( SHA256( key=secret, msg=payload_bytes ) )

    y lo incluye en el header X-Shopify-Hmac-Sha256.

    Usamos esta función en los tests para generar firmas válidas
    sin hardcodear strings que podrían variar si cambia el payload.

    Args:
        payload_bytes: Body raw del request (los mismos bytes que Shopify firmó)
        secret:        Secreto webhook configurado en Shopify Partners Dashboard

    Returns:
        str: HMAC en base64, listo para comparar con el header
    """
    return base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")


# Constantes reutilizadas en múltiples tests
TEST_SECRET = "whsec_test_secret_12345"
TEST_PAYLOAD = b'{"id": 12345, "handle": "politica-devoluciones"}'


# ══════════════════════════════════════════════════════════════════════════
# CLASE 1: Firmas VÁLIDAS → debe retornar True
# ══════════════════════════════════════════════════════════════════════════

class TestValidShopifyWebhook:
    """
    Tests donde la firma HMAC es correcta.

    Todos los tests de esta clase deben retornar True.
    Si alguno falla → la función rechaza webhooks legítimos de Shopify
    (falsos negativos → el endpoint responde 401 y Shopify hace retries).
    """

    def test_valid_signature_returns_true(self):
        """
        Caso base: payload y secreto reales producen firma válida.

        Este test verifica el flujo completo:
        1. Calculamos la firma tal como lo haría Shopify.
        2. Se la pasamos a validate_shopify_webhook().
        3. Debe retornar True.
        """
        hmac_header = _compute_shopify_hmac(TEST_PAYLOAD, TEST_SECRET)
        result = validate_shopify_webhook(
            payload_bytes=TEST_PAYLOAD,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        )
        assert result is True

    def test_valid_signature_with_json_pages_update_payload(self):
        """
        Payload real de un webhook pages/update (estructura completa).

        Verifica que el módulo funciona con payloads de producción,
        no solo con datos de prueba simplificados.
        """
        payload = (
            b'{"id":12345678,"title":"Pol\\u00edtica de Devoluciones",'
            b'"handle":"politica-devoluciones","body_html":"<p>Texto</p>",'
            b'"created_at":"2025-01-10T10:00:00-05:00"}'
        )
        hmac_header = _compute_shopify_hmac(payload, TEST_SECRET)
        assert validate_shopify_webhook(
            payload_bytes=payload,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is True

    def test_valid_signature_with_translation_update_payload(self):
        """
        Payload real de un webhook translations/update.

        Estructura diferente a pages/* → aseguramos que HMAC no depende
        de la estructura del payload sino solo de los bytes raw.
        """
        payload = (
            b'{"locale":"en","resource_id":12345678,'
            b'"resource_type":"Page","key":"body_html","value":"<p>Text</p>"}'
        )
        hmac_header = _compute_shopify_hmac(payload, TEST_SECRET)
        assert validate_shopify_webhook(
            payload_bytes=payload,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is True

    def test_valid_signature_with_pages_delete_payload(self):
        """
        Payload de pages/delete: solo contiene el ID de la página eliminada.
        """
        payload = b'{"id":12345678}'
        hmac_header = _compute_shopify_hmac(payload, TEST_SECRET)
        assert validate_shopify_webhook(
            payload_bytes=payload,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is True

    def test_valid_signature_is_deterministic(self):
        """
        La misma entrada produce siempre el mismo resultado.

        HMAC es una función determinista: mismo payload + mismo secreto
        → mismo hash. Verificamos que múltiples llamadas con los mismos
        argumentos retornan siempre True (no hay aleatoriedad interna).
        """
        hmac_header = _compute_shopify_hmac(TEST_PAYLOAD, TEST_SECRET)
        for _ in range(5):
            assert validate_shopify_webhook(
                payload_bytes=TEST_PAYLOAD,
                shopify_hmac_header=hmac_header,
                webhook_secret=TEST_SECRET,
            ) is True

    def test_valid_signature_with_unicode_content(self):
        """
        Payload que contiene caracteres Unicode (tildes, ñ).

        Importante para e-commerce en español/latinoamérica donde los
        títulos de páginas pueden contener caracteres no-ASCII.
        Shopify firma los bytes del payload como los envía (UTF-8),
        por lo que debemos validar contra esos mismos bytes.
        """
        payload = "Política de devolución ñoño".encode("utf-8")
        hmac_header = _compute_shopify_hmac(payload, TEST_SECRET)
        assert validate_shopify_webhook(
            payload_bytes=payload,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is True


# ══════════════════════════════════════════════════════════════════════════
# CLASE 2: Firmas INVÁLIDAS → debe retornar False
# ══════════════════════════════════════════════════════════════════════════

class TestInvalidShopifyWebhook:
    """
    Tests donde la firma HMAC no coincide.

    Todos los tests de esta clase deben retornar False.
    Si alguno falla → la función acepta requests falsificados
    (falsos positivos → fallo de seguridad crítico).
    """

    def test_wrong_secret_returns_false(self):
        """
        HMAC calculado con secreto correcto pero validado con uno incorrecto.

        Simula el caso donde el secreto fue cambiado en Shopify pero no
        se actualizó la variable de entorno SHOPIFY_WEBHOOK_SECRET.
        """
        # Computamos la firma con el secreto correcto
        hmac_header = _compute_shopify_hmac(TEST_PAYLOAD, TEST_SECRET)
        # Validamos con un secreto diferente → debe fallar
        assert validate_shopify_webhook(
            payload_bytes=TEST_PAYLOAD,
            shopify_hmac_header=hmac_header,
            webhook_secret="wrong_secret_entirely",
        ) is False

    def test_tampered_payload_returns_false(self):
        """
        Payload modificado después de que Shopify lo firmó.

        Simula un ataque man-in-the-middle donde alguien intercepta el
        webhook y modifica el page_id para forzar el sync de otra página.
        HMAC detecta cualquier modificación, por mínima que sea.
        """
        original_payload = b'{"id": 12345, "handle": "original"}'
        hmac_header = _compute_shopify_hmac(original_payload, TEST_SECRET)

        # Atacante modifica el payload
        tampered_payload = b'{"id": 99999, "handle": "malicious"}'

        assert validate_shopify_webhook(
            payload_bytes=tampered_payload,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is False

    def test_wrong_hmac_header_returns_false(self):
        """
        HMAC header con valor completamente aleatorio.

        Simula una request directa al endpoint por alguien que no conoce
        el secreto y pone cualquier string como X-Shopify-Hmac-Sha256.
        """
        assert validate_shopify_webhook(
            payload_bytes=TEST_PAYLOAD,
            shopify_hmac_header="dGhpcyBpcyBub3QgYSB2YWxpZCBobWFj",  # base64 inválido para esta firma
            webhook_secret=TEST_SECRET,
        ) is False

    def test_empty_hmac_header_returns_false(self):
        """
        HMAC header vacío.

        Aunque el router rechaza requests sin header HMAC antes de llegar
        aquí, la función debe manejar el string vacío sin crashear.
        Retorna False (no lanza excepción).
        """
        assert validate_shopify_webhook(
            payload_bytes=TEST_PAYLOAD,
            shopify_hmac_header="",
            webhook_secret=TEST_SECRET,
        ) is False

    def test_payload_with_extra_space_returns_false(self):
        """
        Payload con un espacio extra al final.

        HMAC es extremadamente sensible: incluso un espacio extra cambia
        el hash completamente. Esto verifica que no hay normalización
        inadvertida del payload antes de calcular el HMAC.

        APRENDIZAJE: Por eso el endpoint lee el body con request.body()
        ANTES de cualquier json.loads() — el re-serializado de JSON puede
        agregar/quitar espacios y romper la validación.
        """
        original_payload = b'{"id": 12345}'
        hmac_header = _compute_shopify_hmac(original_payload, TEST_SECRET)

        # Payload con espacio extra: bytes completamente distintos
        payload_with_space = b'{"id": 12345} '

        assert validate_shopify_webhook(
            payload_bytes=payload_with_space,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is False

    def test_base64_decoded_hmac_returns_false(self):
        """
        HMAC enviado sin encodear en base64 (solo raw bytes).

        Shopify siempre envía el HMAC en base64. Si alguien envía el hash
        raw (hex string o binario), la validación debe fallar.
        """
        # Computar el HMAC en RAW (sin base64)
        raw_hmac = hmac.new(
            TEST_SECRET.encode("utf-8"),
            TEST_PAYLOAD,
            digestmod=hashlib.sha256,
        ).hexdigest()  # hexdigest, no base64

        assert validate_shopify_webhook(
            payload_bytes=TEST_PAYLOAD,
            shopify_hmac_header=raw_hmac,
            webhook_secret=TEST_SECRET,
        ) is False

    def test_correct_hmac_wrong_payload_returns_false(self):
        """
        HMAC correcto pero para un payload diferente.

        Simula un ataque de replay donde se reutiliza la firma de un
        webhook anterior con un payload diferente.
        """
        # Firma calculada para un payload A
        payload_a = b'{"id": 111, "handle": "page-a"}'
        hmac_for_a = _compute_shopify_hmac(payload_a, TEST_SECRET)

        # Intentar usar esa firma con payload B
        payload_b = b'{"id": 222, "handle": "page-b"}'

        assert validate_shopify_webhook(
            payload_bytes=payload_b,
            shopify_hmac_header=hmac_for_a,
            webhook_secret=TEST_SECRET,
        ) is False


# ══════════════════════════════════════════════════════════════════════════
# CLASE 3: Edge cases — payloads vacíos, tipos inusuales
# ══════════════════════════════════════════════════════════════════════════

class TestHMACEdgeCases:
    """
    Casos borde para garantizar robustez ante inputs inusuales.

    Aunque en producción el router ya filtra headers vacíos, la función
    debe comportarse predeciblemente ante cualquier input.
    """

    def test_empty_payload_valid_hmac(self):
        """
        Payload vacío con HMAC calculado correctamente para ese payload vacío.

        Aunque Shopify nunca envía payloads vacíos, esto verifica que el
        algoritmo HMAC funciona con bytes vacíos (caso matemáticamente válido).
        """
        empty_payload = b""
        hmac_header = _compute_shopify_hmac(empty_payload, TEST_SECRET)
        assert validate_shopify_webhook(
            payload_bytes=empty_payload,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is True

    def test_empty_payload_wrong_hmac(self):
        """
        Payload vacío con HMAC de otro payload → falla.
        """
        wrong_hmac = _compute_shopify_hmac(TEST_PAYLOAD, TEST_SECRET)
        assert validate_shopify_webhook(
            payload_bytes=b"",
            shopify_hmac_header=wrong_hmac,
            webhook_secret=TEST_SECRET,
        ) is False

    def test_large_payload(self):
        """
        Payload grande (100 KB) — simula una página con mucho contenido HTML.

        Verifica que el módulo no tiene límites de tamaño implícitos y
        que la validación funciona independientemente del tamaño del body.
        """
        large_payload = b"x" * 100_000
        hmac_header = _compute_shopify_hmac(large_payload, TEST_SECRET)
        assert validate_shopify_webhook(
            payload_bytes=large_payload,
            shopify_hmac_header=hmac_header,
            webhook_secret=TEST_SECRET,
        ) is True

    def test_different_secrets_produce_different_hmacs(self):
        """
        Secretos distintos producen HMACs distintos para el mismo payload.

        Verifica la propiedad fundamental de HMAC: el secreto es parte
        integral del cálculo. Sin esto, el HMAC no autenticaría el origen.
        """
        hmac_1 = _compute_shopify_hmac(TEST_PAYLOAD, "secret_one")
        hmac_2 = _compute_shopify_hmac(TEST_PAYLOAD, "secret_two")

        # Los HMACs deben ser diferentes
        assert hmac_1 != hmac_2

        # Y cada uno solo valida con su propio secreto
        assert validate_shopify_webhook(TEST_PAYLOAD, hmac_1, "secret_one") is True
        assert validate_shopify_webhook(TEST_PAYLOAD, hmac_2, "secret_two") is True
        assert validate_shopify_webhook(TEST_PAYLOAD, hmac_1, "secret_two") is False
        assert validate_shopify_webhook(TEST_PAYLOAD, hmac_2, "secret_one") is False

    def test_function_never_raises_exception(self):
        """
        La función debe retornar False ante cualquier input, NUNCA lanzar excepción.

        Si la función lanzara una excepción con input malformado, el router
        podría devolver un 500 en lugar de un 401, y Shopify podría interpretar
        eso como error transitorio y hacer retries (comportamiento indeseado).
        """
        edge_cases = [
            # (payload_bytes, hmac_header, secret)
            (b"", "", ""),
            (b"valid payload", "not-base64!!!", "secret"),
            (b"payload", "YQ==", ""),  # HMAC válido base64, secreto vacío
        ]

        for payload, header, secret in edge_cases:
            try:
                result = validate_shopify_webhook(payload, header, secret)
                # Si llega aquí, debe ser un booleano (True o False)
                assert isinstance(result, bool), (
                    f"Expected bool, got {type(result)} for inputs: "
                    f"payload={payload!r}, header={header!r}, secret={secret!r}"
                )
            except Exception as e:
                pytest.fail(
                    f"validate_shopify_webhook raised {type(e).__name__}: {e} "
                    f"for inputs: payload={payload!r}, header={header!r}, secret={secret!r}"
                )


# ══════════════════════════════════════════════════════════════════════════
# CLASE 4: Resistencia a timing attacks
# ══════════════════════════════════════════════════════════════════════════

class TestTimingAttackResistance:
    """
    Verifica que la comparación de HMACs usa hmac.compare_digest().

    ────────────────────────────────────────────────────────────────────
    ¿Qué es un timing attack?

    El operador == en Python retorna False en cuanto encuentra el primer
    byte diferente. Esto significa que comparar "abc" == "xyz" es más
    rápido que comparar "abc" == "abd" (fallan en el primer byte vs el
    último). Un atacante sofisticado puede medir tiempos de respuesta HTTP
    y deducir qué tan cerca está su HMAC falso del correcto.

    hmac.compare_digest() compara SIEMPRE todos los bytes, sin cortocircuito.
    El tiempo de ejecución es constante independientemente de dónde difiera.

    NOTA IMPORTANTE SOBRE ESTE TEST:
    Medir timing attacks con precisión real requiere miles de muestras y
    hardware controlado. Este test verifica la PROPIEDAD ESTRUCTURAL del
    código (que use compare_digest), no el timing real en nanosegundos.
    El test de tiempo es indicativo, no definitivo.
    ────────────────────────────────────────────────────────────────────
    """

    def test_function_uses_compare_digest_not_equality(self):
        """
        Verifica que el módulo importa y usa hmac.compare_digest.

        En lugar de medir tiempos (que son poco confiables en tests),
        inspeccionamos el código fuente del módulo para confirmar que
        se llama a compare_digest en lugar de usar el operador ==.
        """
        import inspect
        source = inspect.getsource(validate_shopify_webhook)

        # Debe usar compare_digest (resistente a timing attacks)
        assert "compare_digest" in source, (
            "validate_shopify_webhook debe usar hmac.compare_digest() "
            "para comparar el HMAC computado con el recibido. "
            "El operador == es vulnerable a timing attacks. "
            "Ver: https://docs.python.org/3/library/hmac.html#hmac.compare_digest"
        )

        # NO debe usar el operador == para comparar hashes
        # (buscamos el patrón específico "computed == " o "== shopify_hmac")
        # Nota: La búsqueda es heurística; compare_digest garantiza la seguridad.
        assert "== shopify_hmac_header" not in source, (
            "Posible uso de == para comparar HMACs. Usar hmac.compare_digest()."
        )

    def test_invalid_and_valid_hmac_both_execute_same_path(self):
        """
        Tanto firmas válidas como inválidas llegan a compare_digest.

        Este test documenta el diseño: no hay un 'short circuit' previo
        a compare_digest que pueda crear diferencias de timing.
        Ambos caminos (válido e inválido) ejecutan la misma función.
        """
        valid_hmac = _compute_shopify_hmac(TEST_PAYLOAD, TEST_SECRET)
        invalid_hmac = "completamente_invalido_aaaaaaaaaaaaaaaaaaa=="

        # Ambos deben ejecutarse sin excepción
        result_valid = validate_shopify_webhook(TEST_PAYLOAD, valid_hmac, TEST_SECRET)
        result_invalid = validate_shopify_webhook(TEST_PAYLOAD, invalid_hmac, TEST_SECRET)

        assert result_valid is True
        assert result_invalid is False

    def test_timing_similar_for_valid_and_invalid(self):
        """
        Referencia de timing: válido e inválido no difieren por factor >10x.

        IMPORTANTE: Este test es INDICATIVO. Los tiempos reales en nanosegundos
        necesitan hardware especializado para medirse con precisión.
        Un factor de 10x es un umbral conservador para detectar problemas
        obvios de short-circuit (ej. si accidentalmente se usara ==).

        En producción, el timing real de validación (~microsegundos) queda
        oculto bajo la latencia de red (milisegundos), lo que hace que
        los timing attacks sean impracticables para este endpoint.
        """
        valid_hmac = _compute_shopify_hmac(TEST_PAYLOAD, TEST_SECRET)
        # HMAC inválido que difiere desde el primer byte
        invalid_hmac_prefix_diff = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

        # Calentar la función (JIT, caches de CPU)
        for _ in range(10):
            validate_shopify_webhook(TEST_PAYLOAD, valid_hmac, TEST_SECRET)
            validate_shopify_webhook(TEST_PAYLOAD, invalid_hmac_prefix_diff, TEST_SECRET)

        # Medir tiempos
        N = 500
        start = time.perf_counter()
        for _ in range(N):
            validate_shopify_webhook(TEST_PAYLOAD, valid_hmac, TEST_SECRET)
        time_valid = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(N):
            validate_shopify_webhook(TEST_PAYLOAD, invalid_hmac_prefix_diff, TEST_SECRET)
        time_invalid = time.perf_counter() - start

        # Ratio no debe ser > 10x en ninguna dirección
        # (compare_digest garantiza tiempo constante a nivel criptográfico)
        ratio = max(time_valid, time_invalid) / (min(time_valid, time_invalid) + 1e-10)
        assert ratio < 10.0, (
            f"Diferencia de timing sospechosa (ratio={ratio:.2f}x). "
            f"Válido: {time_valid*1000:.3f}ms, Inválido: {time_invalid*1000:.3f}ms. "
            f"Verificar que se usa hmac.compare_digest() y no ==."
        )