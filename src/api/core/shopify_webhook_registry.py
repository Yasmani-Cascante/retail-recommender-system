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
#
# Latencia resultante: 0 a KB_SYNC_INTERVAL_MINUTES (default: 5 min).
# Para contenido KB (política de devoluciones, preguntas frecuentes, etc.)
# esta latencia es completamente aceptable.
#
# WEBHOOKS DISPONIBLES (para futura referencia):
# Si Shopify en el futuro agrega pages/* topics, este módulo puede reactivarse
# descomentando REQUIRED_WEBHOOKS y llamando a ensure_webhooks_registered()
# desde el startup hook en main_unified_redis.py PASO 7.
# ══════════════════════════════════════════════════════════════════════════

import structlog
from typing import List, Dict

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# WEBHOOKS DISPONIBLES EN SHOPIFY
#
# Solo registramos webhooks que Shopify realmente soporta.
# pages/* NO existe — ver nota al inicio del archivo.
#
# Lista de topics que SÍ funcionan y que podrían ser útiles en el futuro:
#   - locales/create, locales/update  → detectar nuevos idiomas en la tienda
#   - collections/update              → cambios en colecciones
# ──────────────────────────────────────────────────────────────────────────

# Vacío intencionalmente: pages/create, pages/update, pages/delete
# no existen en Shopify. El sistema usa polling incremental en su lugar.
REQUIRED_WEBHOOKS: List[Dict] = []


async def ensure_webhooks_registered(shopify_client, app_url: str) -> None:
    """
    Registra webhooks requeridos en Shopify si no existen (idempotente).

    ESTADO ACTUAL: REQUIRED_WEBHOOKS está vacío porque Shopify no soporta
    webhooks para el recurso Pages. El sistema usa polling incremental como
    alternativa (ver ShopifyKBSync y KB_SYNC_INTERVAL_MINUTES en config).

    Esta función se mantiene en la arquitectura para cuando Shopify
    eventualmente agregue soporte para pages/* topics, o para registrar
    otros webhooks útiles en el futuro (locales/create, etc.).

    Args:
        shopify_client: Instancia de ShopifyKBClient.
        app_url: URL pública de la aplicación (sin barra final).
    """
    # Normalizar URL defensivamente: eliminar barra final si existe.
    # Evita URLs con doble slash (https://app.run.app//api/...) que Shopify
    # rechaza con 422 incluso para topics válidos.
    app_url = app_url.rstrip("/")

    if not REQUIRED_WEBHOOKS:
        # Informar claramente en logs por qué no se registra nada.
        logger.info(
            "webhook_registration_skipped",
            reason="shopify_pages_webhooks_not_supported",
            note=(
                "Shopify does not support pages/create, pages/update, pages/delete webhook topics. "
                "Using incremental polling sync instead (see KB_SYNC_INTERVAL_MINUTES)."
            ),
            sync_strategy="incremental_polling",
        )
        return

    # ── Registro de webhooks (activar cuando REQUIRED_WEBHOOKS tenga entradas) ──

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
                    note="system_will_continue_without_this_webhook",
                )
        else:
            logger.debug(
                "webhook_already_registered",
                topic=topic,
                note="skipping",
            )
