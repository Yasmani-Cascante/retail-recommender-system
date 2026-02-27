"""
conftest.py — Fixtures para tests de integración E2E de Webhooks M4
====================================================================

¿Por qué este conftest en lugar de usar el raíz (tests/conftest.py)?
─────────────────────────────────────────────────────────────────────
El conftest.py raíz proporciona test_app_with_mocks, que arranca la app
completa con toda la maquinaria de recomendaciones, Redis, PostgreSQL y
Shopify. Ese fixture es correcto para tests de productos y recomendaciones.

Sin embargo, el endpoint POST /api/webhooks/shopify/pages solo necesita:
  1. validate_shopify_webhook()  → función pura, cero dependencias externas
  2. ShopifyWebhookHandler       → necesita Redis e SyncService (mockeados)

Montar la app entera para testear webhooks tiene dos problemas:
  a) lifespan() intenta conectar Redis real y PostgreSQL → fallo en CI
  b) El entrenamiento del modelo TF-IDF añade 5-20 s innecesarios

SOLUCIÓN: "mini-app" FastAPI que incluye SOLO el webhooks_router.
Esta mini-app no tiene lifespan → no hace ninguna conexión real en startup.
Redis y SyncService se mockean via patch en ShopifyWebhookHandler.

Fixtures disponibles en este conftest (scope indicado en cada fixture):
  webhook_app        → Mini-app FastAPI, solo webhooks_router (scope=session)
  mock_sync_service  → AsyncMock de ShopifyKBSyncService (scope=function)
  mock_redis         → AsyncMock de RedisService con store en memoria (scope=function)
  webhook_client     → TestClient configurado con mocks inyectados (scope=function)

APRENDIZAJE — Cómo funciona el patch en métodos de clase:
  ShopifyWebhookHandler crea sus dependencias de forma lazy en cada request.
  Parcheamos los métodos en la CLASE (no en la instancia) para que TODAS
  las instancias creadas durante el TestClient usen el mock:

    patch("src.api.services.shopify_webhook_handler.ShopifyWebhookHandler._get_redis")

  Al salir del with-block del patch, el método original se restaura.

Author: Retail Recommender — QA Team
Date:   2026-02-26
Phase:  M4 — Incremental Sync (Webhooks)
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ══════════════════════════════════════════════════════════════════════════
# CONSTANTES COMPARTIDAS
# ══════════════════════════════════════════════════════════════════════════
# Deben coincidir exactamente con los valores en test_webhook_e2e.py.
# Se declaran aquí para que el fixture webhook_client pueda usarlos.

WEBHOOK_SECRET = "test_webhook_secret_e2e_2026"
SHOP_DOMAIN = "test-store.myshopify.com"


# ══════════════════════════════════════════════════════════════════════════
# FIXTURE: MINI-APP (scope=session)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def webhook_app():
    """
    Mini-app FastAPI con ÚNICAMENTE el webhooks_router.

    scope="session": Se crea una sola vez para toda la sesión.
    No tiene lifespan → no conecta a Redis ni PostgreSQL en startup.

    Solo incluye:
      - webhooks_router.router (el router bajo prueba)

    NO incluye:
      - products_router, mcp_router, kb_router (irrelevantes para webhooks)
      - lifespan(app) (evitamos el startup completo)

    El SHOPIFY_WEBHOOK_SECRET se parchea en webhook_client (scope=function)
    para que cada test use el secreto correcto.
    """
    from src.api.routers import webhooks_router as wh_router

    mini_app = FastAPI(title="Webhook E2E Test App")
    mini_app.include_router(wh_router.router)
    return mini_app


# ══════════════════════════════════════════════════════════════════════════
# FIXTURE: MOCK SYNC SERVICE (scope=function)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_sync_service():
    """
    Mock limpio de ShopifyKBSyncService para cada test.

    scope="function" (default): Se recrea limpio para cada test.
    Esto garantiza que call_count y call_args_list empiecen siempre en 0.

    Métodos mockeados:
      sync_single_page(page_id: int)   → usado en pages/create, pages/update, translations/update
      delete_kb_for_page(page_id: int) → usado en pages/delete
    """
    service = AsyncMock()
    service.sync_single_page = AsyncMock(return_value={
        "status": "synced",
        "page_id": 0,
        "languages_synced": ["es", "en"],
        "errors": [],
    })
    service.delete_kb_for_page = AsyncMock(return_value={
        "status": "deleted",
        "page_id": 0,
        "records_deleted": 2,
    })
    return service


# ══════════════════════════════════════════════════════════════════════════
# FIXTURE: MOCK REDIS (scope=function)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_redis():
    """
    Mock de RedisService con store en memoria para idempotency.

    scope="function": El dict _store se recrea vacío para cada test.
    Esto es crítico para los tests de idempotency: cada test empieza
    sin claves previas en Redis, siendo determinístico.

    _store simula las operaciones básicas de Redis:
      get(key)          → None si no existe, valor si existe
      set(key, value)   → guarda sin TTL real (TTL ignorado en tests)
      delete(key)       → elimina la clave

    _client.scan simula SCAN+DELETE para _invalidate_page_cache():
      scan retorna (0, []) → cursor=0 (fin), sin claves que borrar
    """
    redis = AsyncMock()
    redis._store = {}

    # _client para operaciones de bajo nivel (SCAN+DELETE en cache invalidation)
    redis._client = AsyncMock()
    redis._client.scan = AsyncMock(return_value=(0, []))   # Sin claves → sin-op
    redis._client.delete = AsyncMock(return_value=0)

    # ── Operaciones de idempotency ────────────────────────────────────────

    async def _get(key: str):
        """Retorna None si no existe (comportamiento de Redis real)."""
        return redis._store.get(key)

    async def _set(key: str, value, ttl=None):
        """Guarda la clave. TTL ignorado en tests (sin expiración)."""
        redis._store[key] = value

    async def _delete(key: str):
        """Elimina la clave. No falla si no existe."""
        redis._store.pop(key, None)

    redis.get = AsyncMock(side_effect=_get)
    redis.set = AsyncMock(side_effect=_set)
    redis.delete = AsyncMock(side_effect=_delete)

    return redis


# ══════════════════════════════════════════════════════════════════════════
# FIXTURE PRINCIPAL: WEBHOOK CLIENT (scope=function)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def webhook_client(webhook_app, mock_sync_service, mock_redis):
    """
    TestClient listo para usar, con todos los mocks inyectados.

    Parchea 3 puntos de integración:

      1. webhooks_router.settings
         → para que HMAC se valide con WEBHOOK_SECRET del test
         → sin esto el endpoint usaría el secreto de .env (podría fallar)

      2. ShopifyWebhookHandler._get_redis()
         → para que idempotency use mock_redis (sin Redis real)
         → el store en memoria simula la persistencia entre requests

      3. ShopifyWebhookHandler._get_sync_service()
         → para que el sync llame a mock_sync_service (sin DB real)
         → permite verificar qué métodos se llamaron y con qué args

    scope=function: Se recrea para cada test con mocks limpios.

    Diagrama del flujo con mocks aplicados:
        TestClient.post("/api/webhooks/shopify/pages")
            → webhooks_router (código real)
                → validate_shopify_webhook(secret=WEBHOOK_SECRET) ← PATCH 1
                    ↓ (válido)
                → BackgroundTask._dispatch_background()
                    → ShopifyWebhookHandler()
                        → _get_redis() → mock_redis          ← PATCH 2
                        → _get_sync_service() → mock_sync_service ← PATCH 3
    """
    HANDLER_CLASS = "src.api.services.shopify_webhook_handler.ShopifyWebhookHandler"

    with (
        # Patch 1: settings en el módulo del router
        patch("src.api.routers.webhooks_router.settings") as mock_settings,

        # Patch 2: método _get_redis en la clase ShopifyWebhookHandler
        patch(
            f"{HANDLER_CLASS}._get_redis",
            new=AsyncMock(return_value=mock_redis),
        ),

        # Patch 3: método _get_sync_service en la clase ShopifyWebhookHandler
        patch(
            f"{HANDLER_CLASS}._get_sync_service",
            new=AsyncMock(return_value=mock_sync_service),
        ),
    ):
        # Configurar el objeto settings mockeado
        mock_settings.SHOPIFY_WEBHOOK_SECRET = WEBHOOK_SECRET
        mock_settings.KB_WEBHOOKS_ENABLED = True

        # TestClient con raise_server_exceptions=False: los errores 5xx
        # no rompen el test; podemos verificar el status_code manualmente
        with TestClient(webhook_app, raise_server_exceptions=False) as client:
            yield client
