# src/api/core/shopify_webhook_registry.py
#
# ══════════════════════════════════════════════════════════════════════════
# NOTA IMPORTANTE — LIMITACIÓN DE SHOPIFY (investigada Feb 2026)
# ══════════════════════════════════════════════════════════════════════════
#
# Shopify NO implementa webhooks para el recurso "Pages" en ninguna versión
# de su REST Admin API ni en GraphQL. Los topics pages/create, pages/update,
# pages/delete NO EXISTEN en la plataforma, independientemente de los scopes
# configurados en la app.
#
# Referencia: https://community.shopify.com/t/webhook-topic-for-page-resource-page-create-update/285494
# Estado: Sin solución oficial desde enero 2024.
#
# ESTRATEGIA ADOPTADA (M4 — Incremental Sync):
# En lugar de webhooks en tiempo real, usamos polling incremental por
# updated_at timestamp. El scheduler de fondo corre cada KB_SYNC_INTERVAL_MINUTES
# y sincroniza solo las páginas modificadas desde el último sync.
# ══════════════════════════════════════════════════════════════════════════

import structlog
from typing import List, Dict

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# WEBHOOKS REGISTRADOS EN SHOPIFY
#
# ── Clientes (F-04) ──────────────────────────────────────────────────────
#   customers/update
#     → invalida cache de perfil de CustomerProfileService
#
#   customers/purchasing_summary: ELIMINADO (06/05/2026)
#     Este topic no existe en Shopify API 2025-01 ni en versiones anteriores.
#     Shopify devuelve 404 "Could not find the webhook topic" en cada startup.
#     Referencia: error confirmado en logs de producción el 06/05/2026.
#
# ── Productos — cache de contexto + índice visual FAISS ──────────────────
#   products/create
#     → invalida cache + indexación incremental en FAISS
#     → el nuevo producto queda disponible en búsquedas visuales en <1 min
#   products/update
#     → invalida cache + indexación incremental (embedding-service ignora
#       si el ID ya existe en el índice FAISS)
#   products/delete
#     → invalida cache. FAISS no se modifica (no hay .remove()).
#       El vector fantasma se limpia en el próximo rebuild semanal.
# ──────────────────────────────────────────────────────────────────────────

REQUIRED_WEBHOOKS: List[Dict] = [
    # ── Clientes ─────────────────────────────────────────────────────────
    {
        "topic": "customers/update",
        "address": "{APP_URL}/api/webhooks/shopify/customers",
        "format": "json",
    },
    # customers/purchasing_summary ELIMINADO — topic no existe en Shopify API
    # (devuelve 404 en todos los intentos de registro desde Feb 2026)

    # ── Productos ─────────────────────────────────────────────────────────
    {
        "topic": "products/create",
        "address": "{APP_URL}/api/webhooks/shopify/products",
        "format": "json",
    },
    {
        "topic": "products/update",
        "address": "{APP_URL}/api/webhooks/shopify/products",
        "format": "json",
    },
    {
        "topic": "products/delete",
        "address": "{APP_URL}/api/webhooks/shopify/products",
        "format": "json",
    },
]


async def ensure_webhooks_registered(shopify_client, app_url: str) -> None:
    """
    Registra webhooks requeridos en Shopify si no existen (idempotente).
    Se llama desde el startup hook en main_unified_redis.py.
    """
    app_url = app_url.rstrip("/")

    if not REQUIRED_WEBHOOKS:
        logger.info("webhook_registration_skipped", reason="required_webhooks_empty")
        return

    existing = await shopify_client.get_webhooks()
    existing_topics = {w["topic"] for w in existing}

    for webhook_config in REQUIRED_WEBHOOKS:
        topic = webhook_config["topic"]

        if topic not in existing_topics:
            resolved_address = webhook_config["address"].replace("{APP_URL}", app_url)
            result = await shopify_client.create_webhook(
                topic=topic,
                address=resolved_address,
                format=webhook_config.get("format", "json"),
            )
            if result:
                logger.info(
                    "webhook_registered",
                    topic=topic,
                    address=resolved_address,
                    webhook_id=result.get("id"),
                )
            else:
                logger.warning(
                    "webhook_registration_failed",
                    topic=topic,
                    address=resolved_address,
                )
        else:
            logger.debug("webhook_already_registered", topic=topic)
