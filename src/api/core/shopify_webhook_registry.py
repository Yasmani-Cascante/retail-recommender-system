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
# F-04 (03/04/2026): Añadidos webhooks de clientes para invalidar el cache
# de perfil de CustomerProfileService cuando Shopify notifica cambios.
#
# NOTA IMPORTANTE sobre Shopify 2025-01:
#   El endpoint REST GET /customers/{id}.json NO fue modificado.
#   Los campos total_spent, orders_count y tags siguen disponibles en REST.
#   El cambio afectó SOLO al payload del webhook customers/update, donde
#   esos campos fueron movidos al nuevo topic customers/purchasing_summary.
#
#   Por eso registramos AMBOS topics:
#     - customers/update            → cambios en datos del perfil (email,
#                                     dirección, tags de segmentación)
#     - customers/purchasing_summary → cambios en LTV y conteo de pedidos
#                                     (campos movidos aquí desde 2025-01)
#
#   En ambos casos la acción es la misma: invalidar el cache Redis del
#   perfil para que el siguiente request haga un fetch fresco desde la
#   API REST, que sigue devolviendo todos los campos correctamente.
# ──────────────────────────────────────────────────────────────────────────

# F-04: Webhooks de clientes para invalidación de cache de perfil.
# Endpoint destino: POST /api/webhooks/shopify/customers
# Handler: ShopifyWebhookHandler.handle_customer_event()
#
# F-01 (07/04/2026): Webhooks de productos para invalidación de cache de contexto.
# Cuando un producto se actualiza en Shopify Admin (título, descripción,
# colecciones, tags), el contexto cacheado bajo
# 'mcp:product:context:{handle}:{market_id}' queda obsoleto.
# Endpoint destino: POST /api/webhooks/shopify/products
# Handler: ShopifyWebhookHandler.handle_product_event()
REQUIRED_WEBHOOKS: List[Dict] = [
    {
        # Dispara cuando cambian datos del perfil: email, dirección, tags,
        # nombre. Permite mantener actualizada la segmentación del cliente.
        "topic": "customers/update",
        "address": "{APP_URL}/api/webhooks/shopify/customers",
        "format": "json",
    },
    {
        # Shopify 2025-01: nuevo topic que contiene total_spent y orders_count
        # (movidos desde customers/update). Dispara cuando el cliente realiza
        # o cancela una compra, afectando su LTV y tier de personalización.
        "topic": "customers/purchasing_summary",
        "address": "{APP_URL}/api/webhooks/shopify/customers",
        "format": "json",
    },
    {
        # F-01: Dispara cuando un producto se edita en Shopify Admin.
        # Invalida el cache de contexto del producto en todos los mercados
        # para que Claude use datos frescos al construir el prompt de upsell.
        # Incluye cambios en: título, descripción, colecciones, tags,
        # precio, estado (active/draft/archived), variantes, imágenes.
        "topic": "products/update",
        "address": "{APP_URL}/api/webhooks/shopify/products",
        "format": "json",
    },
    {
        # F-01: Dispara cuando un producto se elimina de Shopify Admin.
        # Invalida cualquier contexto en cache para evitar que Claude
        # sugiera un producto que ya no existe en la tienda.
        "topic": "products/delete",
        "address": "{APP_URL}/api/webhooks/shopify/products",
        "format": "json",
    },
]


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
