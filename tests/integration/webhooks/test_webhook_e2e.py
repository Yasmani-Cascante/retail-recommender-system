"""
Tests de Integración E2E — Webhooks M4 (POST /api/webhooks/shopify/pages)
=========================================================================

Estos tests ejercen el endpoint real usando TestClient de FastAPI.
Verifican la integración completa de la cadena:

    Request HTTP → webhooks_router → HMAC validation → BackgroundTask
                                                            ↓
                                               ShopifyWebhookHandler
                                                   ↓           ↓
                                           Redis idempotency  ShopifyKBSyncService
                                                                   ↓
                                                            DB upsert / delete

Diferencia con los tests unitarios:
    - unit/test_webhook_security.py  → prueba validate_shopify_webhook() aislada
    - unit/test_webhook_handler.py   → prueba ShopifyWebhookHandler() aislado
    - ESTE archivo                   → prueba el endpoint HTTP completo con
                                       TestClient, incluyendo routing, headers,
                                       respuestas HTTP y ejecución de background tasks

Estrategia de mocks:
    Los tests de integración parchean solo las dependencias externas
    (Redis, ShopifyKBSyncService). El router y el handler se usan reales
    para detectar problemas de integración genuinos.

    Los fixtures están definidos en conftest.py del mismo directorio:
        webhook_app        → Mini-app FastAPI, solo webhooks_router (sin lifespan)
        mock_sync_service  → AsyncMock de ShopifyKBSyncService (scope=function)
        mock_redis         → AsyncMock de RedisService, store en memoria (scope=function)
        webhook_client     → TestClient con los 3 patches activos (scope=function)

    Por qué conftest.py local y NO el conftest.py raíz:
        El conftest raíz monta la app completa con lifespan() que conecta
        Redis real, PostgreSQL y entrena el modelo TF-IDF (~5-20 s).
        Para webhooks solo necesitamos el router + mocks → mini-app.

APRENDIZAJE: BackgroundTasks en TestClient
    FastAPI ejecuta BackgroundTasks de forma SÍNCRONA dentro de TestClient
    antes de retornar la response. Cuando .post() retorna, el background
    task ya se ejecutó completamente. No se necesita sleep() ni polling.

Author: Retail Recommender — QA Team
Date:   2026-02-26
Phase:  M4 — Incremental Sync (Webhooks)
"""

# ── Imports ───────────────────────────────────────────────────────────────
# Solo los necesarios para los helpers HMAC y las aserciones de los tests.
# Los fixtures (webhook_client, mock_sync_service, mock_redis) vienen de
# conftest.py automáticamente — no se importan ni se redefinen aquí.
import hmac
import hashlib
import base64
import json
import pytest
from typing import Dict, Any


# ══════════════════════════════════════════════════════════════════════════
# CONSTANTES DE TEST
# ══════════════════════════════════════════════════════════════════════════
# Deben coincidir exactamente con los valores en conftest.py del mismo
# directorio, donde se usan para configurar el mock de settings.

WEBHOOK_SECRET = "test_webhook_secret_e2e_2026"   # == conftest.WEBHOOK_SECRET
SHOP_DOMAIN = "test-store.myshopify.com"


# ══════════════════════════════════════════════════════════════════════════
# HELPERS DE FIRMA HMAC
# ══════════════════════════════════════════════════════════════════════════

def _sign_payload(payload: Dict[str, Any], secret: str = WEBHOOK_SECRET) -> str:
    """
    Firma un payload JSON exactamente como lo haría Shopify.

    Proceso:
        1. Serializa el dict a JSON bytes compactos (sin espacios en separadores)
        2. Calcula HMAC-SHA256 con el secreto del webhook
        3. Codifica el digest en base64

    CRÍTICO: separators=(",", ":") es obligatorio. Un espacio de diferencia
    en la serialización cambia completamente el HMAC resultante.

    Args:
        payload: Diccionario Python con los datos del webhook
        secret:  Secreto HMAC (usa WEBHOOK_SECRET del test por defecto)

    Returns:
        String base64 listo para el header X-Shopify-Hmac-Sha256
    """
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")


def _signed_headers(
    payload: Dict[str, Any],
    topic: str,
    secret: str = WEBHOOK_SECRET,
    shop: str = SHOP_DOMAIN,
) -> Dict[str, str]:
    """
    Construye el set completo de headers que Shopify envía con cada webhook.

    Headers incluidos:
        X-Shopify-Hmac-Sha256   → firma HMAC del body raw
        X-Shopify-Topic         → tipo de evento (ej. "pages/update")
        X-Shopify-Shop-Domain   → dominio de la tienda
        Content-Type            → siempre "application/json"

    Args:
        payload: Payload del webhook (necesario para calcular la firma)
        topic:   Topic del webhook
        secret:  Secreto HMAC para firmar
        shop:    Dominio de la tienda

    Returns:
        Dict de headers listos para TestClient.post(headers=...)
    """
    return {
        "X-Shopify-Hmac-Sha256": _sign_payload(payload, secret),
        "X-Shopify-Topic": topic,
        "X-Shopify-Shop-Domain": shop,
        "Content-Type": "application/json",
    }


# ══════════════════════════════════════════════════════════════════════════
# CLASE 1: Autenticación HMAC
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestWebhookAuthentication:
    """
    Tests para la capa de autenticación HMAC del endpoint.

    Verifican que el endpoint rechaza requests sin firma o con firma
    inválida, y acepta solo los correctamente firmados con el secreto.
    """

    def test_valid_hmac_returns_200(self, webhook_client):
        """
        Webhook con HMAC correcto → 200 OK.

        Happy-path fundamental: Shopify envía el webhook firmado con el
        secreto compartido → el endpoint acepta, encola en background y
        responde 200 inmediatamente.
        """
        payload = {"id": 12345, "handle": "politica-devoluciones"}
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="pages/update"),
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {response.text}"
        )
        assert response.json()["status"] == "accepted"

    def test_missing_hmac_header_returns_401(self, webhook_client):
        """
        Request sin header X-Shopify-Hmac-Sha256 → 401 Unauthorized.

        Shopify siempre incluye este header. Su ausencia indica un actor
        externo intentando acceder directamente al endpoint interno.
        """
        payload = {"id": 12345, "handle": "test-page"}
        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            json=payload,
            headers={
                "X-Shopify-Topic": "pages/update",
                "X-Shopify-Shop-Domain": SHOP_DOMAIN,
                # Deliberadamente sin X-Shopify-Hmac-Sha256
            },
        )
        assert response.status_code == 401
        assert "HMAC" in response.json()["detail"]

    def test_wrong_hmac_signature_returns_401(self, webhook_client):
        """
        HMAC calculado con secreto incorrecto → 401 Unauthorized.

        Simula un atacante que conoce el formato del header pero no el
        secreto compartido. La firma es válida base64, pero no coincide
        con el payload firmado con el secreto correcto.
        """
        payload = {"id": 12345, "handle": "test-page"}
        body = json.dumps(payload, separators=(",", ":")).encode()

        # Firmar con un secreto DIFERENTE al configurado en conftest.py
        attacker_secret = "wrong_secret_attacker_does_not_know_real_one"
        tampered_signature = _sign_payload(payload, secret=attacker_secret)

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": tampered_signature,
                "X-Shopify-Topic": "pages/update",
                "X-Shopify-Shop-Domain": SHOP_DOMAIN,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401
        assert "HMAC" in response.json()["detail"]

    def test_missing_topic_header_returns_400(self, webhook_client):
        """
        HMAC válido pero sin X-Shopify-Topic → 400 Bad Request.

        El topic es obligatorio para el routing. Sin él no se puede
        determinar qué operación ejecutar en el background task.
        """
        payload = {"id": 12345, "handle": "test-page"}
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": _sign_payload(payload),
                # Deliberadamente sin X-Shopify-Topic
                "X-Shopify-Shop-Domain": SHOP_DOMAIN,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 400

    def test_hmac_failure_does_not_trigger_background_task(
        self, webhook_client, mock_sync_service
    ):
        """
        Request con HMAC inválido NO dispara el background task.

        Verificación de seguridad crítica: el 401 debe cortocircuitar el
        request antes de llegar al handler. El contenido potencialmente
        malicioso nunca se sincroniza con la base de datos.
        """
        payload = {"id": 99999, "handle": "malicious-page"}
        body = json.dumps(payload, separators=(",", ":")).encode()

        webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": "aW52YWxpZHNpZ25hdHVyZQ==",  # base64 random
                "X-Shopify-Topic": "pages/update",
                "X-Shopify-Shop-Domain": SHOP_DOMAIN,
                "Content-Type": "application/json",
            },
        )

        # Ningún método del servicio de sync debe haber sido llamado
        mock_sync_service.sync_single_page.assert_not_called()
        mock_sync_service.delete_kb_for_page.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# CLASE 2: Routing por topic
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestWebhookTopicRouting:
    """
    Tests para el routing correcto según X-Shopify-Topic.

    Cada topic debe disparar exactamente la operación correcta en el
    ShopifyWebhookHandler. El handler usa mock_sync_service del conftest.
    """

    def _post_valid_webhook(self, client, payload: Dict, topic: str):
        """Helper: construye un webhook válido y lo envía."""
        body = json.dumps(payload, separators=(",", ":")).encode()
        return client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic=topic),
        )

    def test_pages_create_triggers_sync(self, webhook_client, mock_sync_service):
        """
        pages/create → sync_single_page(page_id) en background.

        Un editor publica una página nueva en Shopify. El webhook debe
        disparar el sync de esa página a la Knowledge Base.
        """
        payload = {"id": 11111, "handle": "nueva-pagina"}
        response = self._post_valid_webhook(webhook_client, payload, "pages/create")

        assert response.status_code == 200
        # El background task se ejecuta sincrónicamente en TestClient
        mock_sync_service.sync_single_page.assert_called_once_with(11111)

    def test_pages_update_triggers_sync(self, webhook_client, mock_sync_service):
        """
        pages/update → sync_single_page(page_id) en background.

        Un editor modifica el contenido de una página KB existente.
        El re-sync actualiza el contenido en la base de conocimiento.
        """
        payload = {"id": 22222, "handle": "pagina-actualizada"}
        response = self._post_valid_webhook(webhook_client, payload, "pages/update")

        assert response.status_code == 200
        mock_sync_service.sync_single_page.assert_called_once_with(22222)

    def test_pages_delete_triggers_delete_kb(self, webhook_client, mock_sync_service):
        """
        pages/delete → delete_kb_for_page(page_id) en background.

        Un editor elimina una página KB en Shopify. El chatbot debe dejar
        de usar ese contenido → se borra de la Knowledge Base.

        Verificación doble:
        - delete_kb_for_page fue llamado → borrado ocurrió
        - sync_single_page NO fue llamado → no hay sync inadvertido
        """
        payload = {"id": 33333, "handle": "pagina-eliminada"}
        response = self._post_valid_webhook(webhook_client, payload, "pages/delete")

        assert response.status_code == 200
        mock_sync_service.delete_kb_for_page.assert_called_once_with(33333)
        mock_sync_service.sync_single_page.assert_not_called()

    def test_translations_update_triggers_sync(
        self, webhook_client, mock_sync_service
    ):
        """
        translations/update → sync_single_page(resource_id) en background.

        Un traductor actualiza la versión en inglés de una página KB.
        El handler re-sincroniza todos los idiomas de esa página.

        Nota: El payload de translations/update difiere del de pages/*:
            - "resource_id" en lugar de "id"
            - "resource_type" = "Page"
            - "locale" = código de idioma actualizado
        """
        payload = {
            "locale": "en",
            "resource_id": 44444,
            "resource_type": "Page",
            "key": "body_html",
            "value": "<p>Updated English content</p>",
        }
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="translations/update"),
        )

        assert response.status_code == 200
        mock_sync_service.sync_single_page.assert_called_once_with(44444)

    def test_translations_non_page_resource_ignored(
        self, webhook_client, mock_sync_service
    ):
        """
        translations/update con resource_type != "Page" → 200 status=ignored.

        Shopify puede enviar traducciones de Products, Blogs, etc.
        Solo procesamos traducciones de Pages; el resto se ignora
        silenciosamente para que Shopify no reintente por un 4xx.
        """
        payload = {
            "locale": "en",
            "resource_id": 55555,
            "resource_type": "Product",   # ← No es "Page"
            "key": "body_html",
            "value": "<p>Product description in English</p>",
        }
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="translations/update"),
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        mock_sync_service.sync_single_page.assert_not_called()

    def test_unknown_topic_returns_200_ignored(self, webhook_client):
        """
        Topic no registrado → 200 con status=ignored.

        Shopify puede agregar nuevos topics en el futuro. El endpoint los
        acepta con 200 para no generar retries innecesarios, pero los ignora
        silenciosamente sin ejecutar ningún background task.
        """
        payload = {"id": 66666, "handle": "alguna-pagina"}
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": _sign_payload(payload),
                "X-Shopify-Topic": "pages/unpublish",   # Topic hipotético futuro
                "X-Shopify-Shop-Domain": SHOP_DOMAIN,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


# ══════════════════════════════════════════════════════════════════════════
# CLASE 3: Estructura de Response
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestWebhookResponseStructure:
    """
    Tests para verificar la estructura JSON de las respuestas.

    Shopify solo mira el status code (2xx = éxito). Sin embargo, la
    estructura de la respuesta es importante para monitoring y logging.
    """

    def test_accepted_response_contains_required_fields(self, webhook_client):
        """
        Respuesta 200 accepted contiene: status, page_id, topic, message.

        Estos campos son consumidos por:
        - Logs de webhook delivery en Shopify Partners Dashboard
        - Dashboards internos de monitoreo
        - Scripts de debugging cuando hay delays en el sync
        """
        payload = {"id": 77777, "handle": "test-response-structure"}
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="pages/update"),
        )

        assert response.status_code == 200
        data = response.json()

        assert data.get("status") == "accepted"
        assert data.get("page_id") == 77777
        assert data.get("topic") == "pages/update"
        assert "message" in data, "La respuesta debe incluir un campo 'message'"

    def test_verify_endpoint_lists_supported_topics(self, webhook_client):
        """
        GET /api/webhooks/shopify/verify → 200 con lista de topics soportados.

        Este endpoint se usa durante el setup de webhooks en Shopify para:
        - Verificar que la URL está activa
        - Conocer qué topics registrar en el Partners Dashboard
        """
        response = webhook_client.get("/api/webhooks/shopify/verify")

        assert response.status_code == 200
        data = response.json()

        assert data.get("status") == "ok"
        assert "supported_topics" in data

        expected_topics = {"pages/create", "pages/update", "pages/delete", "translations/update"}
        actual_topics = set(data["supported_topics"])
        assert expected_topics.issubset(actual_topics), (
            f"Topics faltantes: {expected_topics - actual_topics}"
        )

    def test_ignored_response_contains_topic(self, webhook_client):
        """
        Respuesta "ignored" contiene el topic ignorado para debugging.

        Útil en los logs para saber qué topics llegan pero no se procesan
        (indica que hay webhooks extras registrados en Shopify).
        """
        payload = {"id": 12345}
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": _sign_payload(payload),
                "X-Shopify-Topic": "orders/create",   # Topic válido de Shopify, ignorado aquí
                "X-Shopify-Shop-Domain": SHOP_DOMAIN,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert "topic" in data


# ══════════════════════════════════════════════════════════════════════════
# CLASE 4: Idempotency E2E
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestWebhookIdempotencyE2E:
    """
    Tests de idempotency a nivel de endpoint HTTP completo.

    Shopify garantiza at-least-once delivery, no exactly-once.
    El mismo webhook puede llegar 2-19 veces (Shopify reintenta hasta 19x).

    El fixture mock_redis (scope="function" en conftest.py) se recrea
    con store vacío para cada test, garantizando aislamiento total.
    """

    def _post_page_update(self, client, page_id: int):
        """Helper: envía un pages/update webhook para la página dada."""
        payload = {"id": page_id, "handle": f"page-{page_id}"}
        body = json.dumps(payload, separators=(",", ":")).encode()
        return client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="pages/update"),
        )

    def test_duplicate_webhook_both_return_200(self, webhook_client):
        """
        Dos copias del mismo webhook retornan 200 ambas.

        Si el duplicado retornara 4xx, Shopify lo marcaría como fallido
        y continuaría reintentando → bucle infinito de retries.
        El 200 en el duplicado es intencional y correcto.
        """
        r1 = self._post_page_update(webhook_client, page_id=88888)
        r2 = self._post_page_update(webhook_client, page_id=88888)

        assert r1.status_code == 200, f"Primera entrega falló: {r1.text}"
        assert r2.status_code == 200, f"Segunda entrega (duplicado) falló: {r2.text}"

    def test_duplicate_webhook_sync_called_only_once(
        self, webhook_client, mock_sync_service
    ):
        """
        El sync se ejecuta solo para el PRIMER webhook; el duplicado es ignorado.

        Mecanismo de idempotency:
        1. Primera entrega → handler genera clave "webhook:idempotency:pages/update:99001"
           → Redis GET retorna None → procesamos → Redis SET la clave con TTL
        2. Segunda entrega → misma clave → Redis GET retorna el valor → SKIP

        El mock_redis del conftest usa un dict en memoria que persiste
        dentro del mismo test (scope=function), simulando Redis correctamente.
        """
        page_id = 99001
        self._post_page_update(webhook_client, page_id=page_id)   # Primera entrega
        self._post_page_update(webhook_client, page_id=page_id)   # Duplicado

        call_count = mock_sync_service.sync_single_page.call_count
        assert call_count == 1, (
            f"sync_single_page llamado {call_count} veces, esperado 1. "
            "Los duplicados deben omitirse via idempotency Redis."
        )

    def test_different_pages_each_synced_once(
        self, webhook_client, mock_sync_service
    ):
        """
        Webhooks de páginas DIFERENTES se procesan cada uno exactamente una vez.

        Las claves de idempotency incluyen el page_id, por lo que páginas
        diferentes no se bloquean entre sí.
        """
        page_ids = [99101, 99102, 99103]
        for page_id in page_ids:
            self._post_page_update(webhook_client, page_id=page_id)

        assert mock_sync_service.sync_single_page.call_count == 3
        synced_ids = sorted(
            call.args[0]
            for call in mock_sync_service.sync_single_page.call_args_list
        )
        assert synced_ids == page_ids


# ══════════════════════════════════════════════════════════════════════════
# CLASE 5: Validación de payload
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestWebhookPayloadValidation:
    """
    Tests para la validación de los campos requeridos en el payload.

    El endpoint rechaza payloads malformados con 400 Bad Request.
    Esto es correcto: 400 indica a Shopify "request mal formado" →
    Shopify NO reintentará (a diferencia de un 500, que sí genera retries).
    """

    def test_pages_payload_without_id_returns_400(self, webhook_client):
        """
        Payload de pages/* sin campo 'id' → 400 Bad Request.

        'id' es el identificador único de la página en Shopify.
        Sin él es imposible saber qué página sincronizar o eliminar.
        """
        payload = {"handle": "alguna-pagina"}   # Sin 'id'
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="pages/update"),
        )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "id" in detail or "page" in detail

    def test_translations_payload_without_resource_id_returns_400(
        self, webhook_client
    ):
        """
        Payload de translations/update sin 'resource_id' → 400 Bad Request.

        resource_id es el equivalente a 'id' para eventos de traducción.
        """
        payload = {
            "locale": "en",
            "resource_type": "Page",
            "key": "body_html",
            "value": "<p>Content</p>",
            # Deliberadamente sin 'resource_id'
        }
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="translations/update"),
        )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "resource_id" in detail or "id" in detail

    def test_invalid_json_body_returns_400(self, webhook_client):
        """
        Body que no es JSON válido → 400 Bad Request.

        NOTA sobre HMAC: El HMAC se calcula sobre bytes raw, no sobre JSON
        parseado. El HMAC de un body inválido es técnicamente correcto.
        El 400 ocurre después en el json.loads() posterior a la validación HMAC.

        Secuencia: HMAC ✓ → json.loads() ✗ → 400.
        """
        invalid_body = b"this is definitely not valid json {"
        # El HMAC de este body es válido (firma sobre bytes raw)
        valid_hmac_of_invalid_body = base64.b64encode(
            hmac.new(
                WEBHOOK_SECRET.encode("utf-8"),
                invalid_body,
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=invalid_body,
            headers={
                "X-Shopify-Hmac-Sha256": valid_hmac_of_invalid_body,
                "X-Shopify-Topic": "pages/update",
                "X-Shopify-Shop-Domain": SHOP_DOMAIN,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 400

    def test_extra_fields_in_payload_accepted(self, webhook_client):
        """
        Payload con campos extra (título, fechas, metadatos) → 200 accepted.

        Shopify envía el objeto completo de la página (decenas de campos).
        El endpoint solo usa 'id' y 'handle'; los demás se ignoran sin error.
        """
        payload = {
            "id": 111222,
            "handle": "pagina-con-extras",
            "title": "Página con Extras",
            "body_html": "<p>Contenido largo aquí...</p>",
            "created_at": "2025-01-10T10:00:00-05:00",
            "updated_at": "2026-01-15T08:30:00-05:00",
            "published_at": "2025-01-15T08:30:00-05:00",
            "shop_id": 987654321,
            "template_suffix": None,
            "admin_graphql_api_id": "gid://shopify/Page/111222",
        }
        body = json.dumps(payload, separators=(",", ":")).encode()

        response = webhook_client.post(
            "/api/webhooks/shopify/pages",
            content=body,
            headers=_signed_headers(payload, topic="pages/update"),
        )

        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


# ══════════════════════════════════════════════════════════════════════════
# CLASE 6: Flujos completos de producción
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestWebhookProductionFlow:
    """
    Tests que simulan flujos reales de producción multi-step.

    Más complejos que los unitarios: combinan múltiples requests y
    verifican el estado acumulado de los mocks después de cada secuencia.
    """

    def test_page_lifecycle_create_update_delete(
        self, webhook_client, mock_sync_service
    ):
        """
        Ciclo de vida completo de una página: create → update → delete.

        Simula lo que ocurre cuando un editor del equipo de marketing:
        1. Publica una nueva página de política (pages/create)
        2. La corrige al día siguiente (pages/update)
        3. La elimina cuando la política cambia (pages/delete)

        Verificaciones:
        - create y update → 2 llamadas a sync_single_page
        - delete → 1 llamada a delete_kb_for_page, nunca a sync
        """
        page_id = 200001

        def send(topic: str):
            """Helper interno: envía un webhook del topic indicado."""
            # pages/delete no incluye handle en el payload real de Shopify
            payload = (
                {"id": page_id}
                if topic == "pages/delete"
                else {"id": page_id, "handle": "politica-ciclo-vida"}
            )
            body = json.dumps(payload, separators=(",", ":")).encode()
            return webhook_client.post(
                "/api/webhooks/shopify/pages",
                content=body,
                headers=_signed_headers(payload, topic=topic),
            )

        # Ciclo completo — cada topic tiene clave de idempotency diferente
        assert send("pages/create").status_code == 200
        assert send("pages/update").status_code == 200
        assert send("pages/delete").status_code == 200

        # create + update → 2 syncs; delete → 0 syncs adicionales
        assert mock_sync_service.sync_single_page.call_count == 2
        mock_sync_service.delete_kb_for_page.assert_called_once_with(page_id)

    def test_multilingual_translation_updates_both_processed(
        self, webhook_client, mock_sync_service
    ):
        """
        Actualizaciones de ES y EN de la misma página en el mismo día.

        Un traductor actualiza dos idiomas. Cada uno dispara su propio
        webhook translations/update con distinto locale.

        Ambas deben sincronizarse: las claves de idempotency incluyen el
        locale, por lo que ES y EN no se bloquean entre sí.
        """
        page_id = 200002

        def send_translation(locale: str):
            payload = {
                "locale": locale,
                "resource_id": page_id,
                "resource_type": "Page",
                "key": "body_html",
                "value": f"<p>Contenido en {locale}</p>",
            }
            body = json.dumps(payload, separators=(",", ":")).encode()
            return webhook_client.post(
                "/api/webhooks/shopify/pages",
                content=body,
                headers=_signed_headers(payload, topic="translations/update"),
            )

        assert send_translation("es").status_code == 200
        assert send_translation("en").status_code == 200

        # Ambas traducciones deben disparar sync
        assert mock_sync_service.sync_single_page.call_count == 2
        synced_ids = [
            call.args[0]
            for call in mock_sync_service.sync_single_page.call_args_list
        ]
        assert all(pid == page_id for pid in synced_ids)

    def test_bulk_page_import_all_pages_synced(
        self, webhook_client, mock_sync_service
    ):
        """
        Bulk import de 10 páginas: todas se sincronizan individualmente.

        Un bulk import en Shopify puede desencadenar decenas de webhooks
        en segundos. El endpoint debe procesar cada uno exactamente una vez.

        Verificaciones:
        - 10 requests → 10 syncs (sin pérdidas, sin duplicaciones)
        - Los IDs sincronizados coinciden exactamente con los enviados
        """
        page_ids = list(range(300001, 300011))   # 10 páginas: 300001..300010

        for page_id in page_ids:
            payload = {"id": page_id, "handle": f"bulk-page-{page_id}"}
            body = json.dumps(payload, separators=(",", ":")).encode()
            response = webhook_client.post(
                "/api/webhooks/shopify/pages",
                content=body,
                headers=_signed_headers(payload, topic="pages/create"),
            )
            assert response.status_code == 200, (
                f"Webhook para page_id={page_id} falló: {response.text}"
            )

        assert mock_sync_service.sync_single_page.call_count == 10
        synced_ids = sorted(
            call.args[0]
            for call in mock_sync_service.sync_single_page.call_args_list
        )
        assert synced_ids == page_ids, (
            f"IDs sincronizados: {synced_ids}\nEsperados: {page_ids}"
        )
