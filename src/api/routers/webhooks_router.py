"""
Webhooks Router — M4 Incremental Sync
======================================

╔══════════════════════════════════════════════════════════════════════════╗
║  NOTA PARA DESARROLLADORES — ESTADO ACTUAL (Feb 2026)                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Este router está IMPLEMENTADO Y FUNCIONAL, pero los webhooks de         ║
║  Shopify para el recurso Pages (pages/create, pages/update,              ║
║  pages/delete) NO EXISTEN en la plataforma Shopify.                      ║
║                                                                          ║
║  Shopify no ha implementado estos topics en ninguna versión de su        ║
║  REST Admin API ni en GraphQL (investigado y confirmado Feb 2026).       ║
║  Ref: https://community.shopify.com/t/285494 (sin resolución oficial)   ║
║                                                                          ║
║  ESTRATEGIA ACTUAL:                                                      ║
║    La sincronización de cambios en páginas KB se realiza mediante        ║
║    polling incremental por updated_at (ver KBBackgroundSyncJob en        ║
║    shopify_kb_sync.py). Latencia: 0 a KB_SYNC_INTERVAL_MINUTES (5 min). ║
║                                                                          ║
║  POR QUÉ CONSERVAMOS ESTE ARCHIVO:                                       ║
║    1. translations/update SÍ existe y funciona → sync multilingüe       ║
║       en tiempo real cuando marketing actualiza traducciones.            ║
║    2. Si Shopify agrega pages/* en el futuro, solo hay que:              ║
║       a) Registrar los topics en shopify_webhook_registry.py             ║
║       b) Activar KB_WEBHOOKS_ENABLED=true en .env                        ║
║       c) El router, handler, HMAC y idempotency ya están listos.         ║
║    3. La infraestructura (HMAC, idempotency Redis, métricas) es          ║
║       reutilizable para cualquier webhook futuro de Shopify.             ║
║                                                                          ║
║  PARA ACTIVAR WEBHOOKS CUANDO SHOPIFY LOS SOPORTE:                       ║
║    1. Editar shopify_webhook_registry.py → descomentar REQUIRED_WEBHOOKS ║
║    2. Setear KB_WEBHOOKS_ENABLED=true en .env                            ║
║    3. Reiniciar el servicio → el startup registra los webhooks           ║
║       automáticamente via ensure_webhooks_registered()                   ║
╚══════════════════════════════════════════════════════════════════════════╝

Router canónico para todos los webhooks de Shopify.
Consolida y reemplaza src/api/webhooks/shopify_webhooks.py (deprecado).

Topics soportados (vía header X-Shopify-Topic):
    pages/create        → upsert KB content para la página nueva
    pages/update        → upsert KB content para la página modificada
    pages/delete        → eliminar KB content + invalidar cache
    translations/update → re-sync todos los idiomas de la página afectada

NOTA: pages/* no generan webhooks reales desde Shopify (ver nota arriba).
El endpoint existe y funciona; solo translations/update llega activamente.

Flujo de cada webhook:
    1. Leer body raw  (ANTES de JSON parsing — requerido por HMAC)
    2. Validar HMAC   (webhook_security.validate_shopify_webhook)
    3. Incrementar métrica de recepción
    4. ACK inmediato  (return 200 — Shopify exige respuesta < 5 s)
    5. Procesar en BackgroundTask (sync + cache invalidation + métricas)

Seguridad:
    - HMAC validado con hmac.compare_digest (resistente a timing attacks)
    - Idempotency via Redis (ShopifyWebhookHandler.is_duplicate_event)
    - Sin dependencias externas en el path crítico de validación

Diferencias respecto al router legacy (shopify_webhooks.py):
    LEGACY                              M4
    ──────────────────────────────────────────────────────────────
    4 endpoints separados por topic     1 endpoint, routing por header
    HMAC via shopify_client (frágil)    HMAC via webhook_security (puro)
    Sin idempotency                     Idempotency Redis
    Sin métricas en router              Métricas en todos los pasos
    Logging estándar                    structlog
    Depende de SHOPIFY_KB_AVAILABLE     Independiente de KB modules

Author: Retail Recommender System Team
Version: M4 — Incremental Sync
"""

import json
import structlog
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Header
from typing import Optional

from src.api.core.webhook_security import validate_shopify_webhook
from src.api.services.shopify_webhook_handler import ShopifyWebhookHandler
from src.api.core.config import get_settings

settings = get_settings()

logger = structlog.get_logger(__name__)

# Prefijo propio: /api/webhooks
# Endpoint principal: POST /api/webhooks/shopify/pages
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks M4"])


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL — recibe todos los topics de páginas y traducciones
# ══════════════════════════════════════════════════════════════════════════

@router.post(
    "/shopify/pages",
    status_code=200,
    summary="Shopify Pages & Translations Webhook",
    description=(
        "Endpoint unificado para webhooks de Shopify. "
        "Enruta por el header X-Shopify-Topic:\n"
        "- `pages/create` → sincroniza página nueva\n"
        "- `pages/update` → re-sincroniza página modificada\n"
        "- `pages/delete` → elimina KB content\n"
        "- `translations/update` → re-sync multilingüe"
    ),
)
async def handle_shopify_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_shopify_hmac_sha256: Optional[str] = Header(default=None),
    x_shopify_shop_domain: Optional[str] = Header(default=None),
    x_shopify_topic: Optional[str] = Header(default=None),
):
    """
    Receptor unificado para webhooks de Shopify (páginas y traducciones).

    Shopify envía todos los webhooks registrados a esta URL con el topic
    indicado en X-Shopify-Topic. El enrutamiento a la lógica correcta se
    hace en _dispatch_background(), después del ACK.

    Args:
        request:               FastAPI Request (para leer body raw)
        background_tasks:      FastAPI BackgroundTasks (procesamiento asíncrono)
        x_shopify_hmac_sha256: Firma HMAC del payload (header de seguridad)
        x_shopify_shop_domain: Dominio de la tienda (logging/auditoría)
        x_shopify_topic:       Topic del evento (pages/create, pages/update…)
    """

    # ── 1. Leer body RAW ──────────────────────────────────────────────────
    # CRÍTICO: request.body() se lee ANTES del JSON parsing.
    # validate_shopify_webhook necesita los bytes exactos que Shopify firmó.
    # Si se hace json.loads() primero, el re-serializado puede diferir (espacios,
    # orden de claves) y la validación HMAC fallará con payloads válidos.
    body_bytes = await request.body()

    # ── 2. Validar HMAC ───────────────────────────────────────────────────
    # Bug 5 FIX: incrementar kb_webhook_hmac_failures_total ANTES de lanzar
    # la excepción para que la métrica capture intentos sin header.
    if not x_shopify_hmac_sha256:
        _inc_hmac_failure()
        logger.warning(
            "webhook_missing_hmac",
            shop=x_shopify_shop_domain,
            topic=x_shopify_topic,
        )
        raise HTTPException(status_code=401, detail="Missing HMAC header")

    if not validate_shopify_webhook(
        payload_bytes=body_bytes,
        shopify_hmac_header=x_shopify_hmac_sha256,
        webhook_secret=settings.SHOPIFY_WEBHOOK_SECRET,
    ):
        _inc_hmac_failure()
        logger.warning(
            "webhook_invalid_hmac",
            shop=x_shopify_shop_domain,
            topic=x_shopify_topic,
        )
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    # ── 3. Validar topic ──────────────────────────────────────────────────
    # Topics soportados. Cualquier otro se acepta con 200 pero no se procesa
    # (evita que Shopify marque el endpoint como fallido por topics futuros).
    SUPPORTED_TOPICS = {
        "pages/create",
        "pages/update",
        "pages/delete",
        "translations/update",
        # F-04: invalidacion de cache de perfil de cliente
        "customers/create",
        "customers/update",
    }

    topic = x_shopify_topic or ""

    if not topic:
        logger.warning("webhook_missing_topic", shop=x_shopify_shop_domain)
        raise HTTPException(status_code=400, detail="Missing X-Shopify-Topic header")

    if topic not in SUPPORTED_TOPICS:
        # ACK sin procesar — no queremos que Shopify reintente por topics
        # que intencionalmente ignoramos (app/uninstalled, orders/*, etc.)
        logger.info("webhook_topic_ignored", topic=topic, shop=x_shopify_shop_domain)
        return {"status": "ignored", "topic": topic}

    # ── 4. Parse payload ──────────────────────────────────────────────────
    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError as e:
        logger.error("webhook_invalid_json", error=str(e), topic=topic)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # ── 5. Extraer campos según topic ─────────────────────────────────────
    # pages/* envían { "id": <int>, "handle": "<str>", ... }
    # translations/update envía { "locale": "<str>", "resource_id": <int>,
    #                              "resource_type": "Page", ... }
    # customers/* envían { "id": <int>, "email": "<str>", ... }
    if topic in ("customers/create", "customers/update"):
        customer_id = payload.get("id")
        if not customer_id:
            logger.warning("webhook_missing_customer_id", topic=topic, payload_keys=list(payload.keys()))
            raise HTTPException(status_code=400, detail="Missing customer ID in payload")
        # Valores dummy para los parametros de pages que no aplican aqui
        page_id = customer_id
        page_handle = ""

    elif topic in ("pages/create", "pages/update", "pages/delete"):
        page_id = payload.get("id")
        page_handle = payload.get("handle", "")

        if not page_id:
            logger.warning("webhook_missing_page_id", topic=topic, payload_keys=list(payload.keys()))
            raise HTTPException(status_code=400, detail="Missing page ID in payload")

    else:  # translations/update
        page_id = payload.get("resource_id")
        locale = payload.get("locale", "")
        resource_type = payload.get("resource_type", "")
        page_handle = ""  # No disponible en payload de translation

        if not page_id:
            logger.warning("webhook_missing_resource_id", topic=topic, payload_keys=list(payload.keys()))
            raise HTTPException(status_code=400, detail="Missing resource_id in payload")

        # Solo procesamos traducciones de Pages; ignorar otros resource_types
        if resource_type != "Page":
            logger.info(
                "webhook_translation_non_page_ignored",
                resource_type=resource_type,
                resource_id=page_id,
            )
            return {"status": "ignored", "reason": f"resource_type={resource_type} is not Page"}

    # ── 6. Bug 5 FIX: métrica de recepción ────────────────────────────────
    # Se incrementa DESPUÉS de validación HMAC y ANTES del ACK.
    # Esto garantiza que solo contamos webhooks legítimos, no intentos de ataque.
    _inc_received(topic)

    logger.info(
        "webhook_accepted",
        page_id=page_id,
        topic=topic,
        shop=x_shopify_shop_domain,
    )

    # ── 7. ACK + dispatch a BackgroundTask ────────────────────────────────
    # Shopify requiere respuesta en < 5 s o marca el webhook como fallido
    # y agenda reintentos (hasta 19 en 48 h). El procesamiento real
    # (sync + DB + cache) puede tardar varios segundos → va en background.
    background_tasks.add_task(
        _dispatch_background,
        page_id=int(page_id),
        page_handle=page_handle if topic != "translations/update" else "",
        topic=topic,
        locale=payload.get("locale", "") if topic == "translations/update" else "",
    )

    return {
        "status": "accepted",
        "page_id": page_id,
        "topic": topic,
        "message": "Webhook received, processing in background",
    }


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINT DE VERIFICACIÓN — para setup en Shopify Partners Dashboard
# ══════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════
# F-04 (03/04/2026) — ENDPOINT PARA WEBHOOKS DE CLIENTES
# ══════════════════════════════════════════════════════════════════════════
#
# Recibe dos topics de Shopify (via header X-Shopify-Topic):
#
#   customers/update
#     → Cambios en datos del perfil: email, nombre, dirección, tags.
#     → Desde Shopify 2025-01 ya NO incluye total_spent ni orders_count.
#
#   customers/purchasing_summary
#     → Nuevo topic (Shopify 2025-01) que dispara cuando el cliente
#       compra o cancela, actualizando su LTV.
#     → Contiene total_spent y orders_count (movidos desde customers/update).
#
# En ambos casos la acción es la misma: INVALIDAR el cache Redis del perfil
# bajo la clave 'mcp:customer:profile:{customer_id}' (TTL 24h).
# El siguiente request del chat hará un fetch fresco desde la API REST
# de Shopify, que sigue devolviendo todos los campos sin cambios.
#
# Seguridad: misma validación HMAC que el endpoint de páginas.
# Idempotencia: misma lógica SET NX de ShopifyWebhookHandler.
# ══════════════════════════════════════════════════════════════════════════

@router.post(
    "/shopify/customers",
    status_code=200,
    summary="Shopify Customers Webhook (F-04)",
    description=(
        "Recibe eventos de clientes de Shopify.\n"
        "Topics soportados (via X-Shopify-Topic):\n"
        "- `customers/update` → invalidar cache de perfil\n"
        "- `customers/purchasing_summary` → invalidar cache de LTV"
    ),
)
async def handle_customers_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_shopify_hmac_sha256: Optional[str] = Header(default=None),
    x_shopify_shop_domain: Optional[str] = Header(default=None),
    x_shopify_topic: Optional[str] = Header(default=None),
):
    """
    Receptor de webhooks de clientes Shopify — F-04 Personalización por historial.

    Flujo (mismo patrón M4 que el endpoint de páginas):
        1. Leer body raw   (antes del JSON parsing — requerido por HMAC)
        2. Validar HMAC    (hmac.compare_digest, resistente a timing attacks)
        3. Validar topic   (customers/update o customers/purchasing_summary)
        4. Extraer customer_id del payload
        5. ACK inmediato   (Shopify exige respuesta < 5 s)
        6. Invalidar cache en background (ShopifyWebhookHandler.handle_customer_event)
    """
    # ── 1. Leer body raw ────────────────────────────────────────────────────────
    raw_body = await request.body()

    # ── 2. Validar HMAC ────────────────────────────────────────────────────────
    webhook_secret = settings.SHOPIFY_WEBHOOK_SECRET
    if not webhook_secret:
        logger.error("customers_webhook_no_secret_configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not x_shopify_hmac_sha256:
        _inc_hmac_failure()
        logger.warning("customers_webhook_missing_hmac_header",
                        shop=x_shopify_shop_domain)
        raise HTTPException(status_code=401, detail="Missing HMAC header")

    if not validate_shopify_webhook(raw_body, x_shopify_hmac_sha256, webhook_secret):
        _inc_hmac_failure()
        logger.warning("customers_webhook_invalid_hmac",
                        shop=x_shopify_shop_domain, topic=x_shopify_topic)
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    # ── 3. Validar topic ───────────────────────────────────────────────────────
    topic = x_shopify_topic or ""
    SUPPORTED_TOPICS = {"customers/update", "customers/purchasing_summary"}

    if topic not in SUPPORTED_TOPICS:
        # Topic no soportado — responder 200 para evitar reintentos de Shopify
        logger.info("customers_webhook_unsupported_topic", topic=topic)
        return {"status": "ignored", "reason": f"topic={topic} not handled here"}

    # ── 4. Parsear payload y extraer customer_id ───────────────────────────
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("customers_webhook_invalid_json", topic=topic)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # customers/update:            payload["id"]          (ID del cliente)
    # customers/purchasing_summary: payload["customer_id"] (Shopify 2025-01)
    if topic == "customers/purchasing_summary":
        customer_id_raw = payload.get("customer_id")
    else:
        customer_id_raw = payload.get("id")

    if not customer_id_raw:
        logger.warning("customers_webhook_missing_customer_id",
                        topic=topic, keys=list(payload.keys()))
        return {"status": "ignored", "reason": "customer_id not found in payload"}

    customer_id = str(customer_id_raw)

    # ── 5. Métrica de recepción ────────────────────────────────────────────────────
    _inc_received(topic)

    logger.info(
        "customers_webhook_accepted",
        customer_id=customer_id,
        topic=topic,
        shop=x_shopify_shop_domain,
    )

    # ── 6. ACK inmediato + dispatch a BackgroundTask ───────────────────────────
    # La invalidación de cache es rápida (~1-2 ms en Redis) pero va en
    # background para no comprometer el ACK < 5s exigido por Shopify.
    background_tasks.add_task(
        _dispatch_customer_event,
        customer_id=customer_id,
        topic=topic,
    )

    return {
        "status": "accepted",
        "customer_id": customer_id,
        "topic": topic,
        "message": "Customer webhook received, cache invalidation queued",
    }


async def _dispatch_customer_event(customer_id: str, topic: str) -> None:
    """
    Procesa el webhook de cliente en background tras el ACK.

    Delega a ShopifyWebhookHandler.handle_customer_event() que implementa:
      - Idempotencia via Redis SET NX (evita procesar el mismo evento dos veces)
      - Invalidación del cache 'mcp:customer:profile:{id}'
      - Logging estructurado con duración

    Args:
        customer_id: ID numérico del cliente como string.
        topic: 'customers/update' o 'customers/purchasing_summary'.
    """
    handler = ShopifyWebhookHandler()
    await handler.handle_customer_event(
        customer_id=customer_id,
        topic=topic,
    )


# ══════════════════════════════════════════════════════════════════════
# F-01 (07/04/2026) — ENDPOINT PARA WEBHOOKS DE PRODUCTOS
# ══════════════════════════════════════════════════════════════════════
#
# Cuando un producto se actualiza en Shopify Admin (título, descripción,
# colecciones, tags, precio, estado), el contexto cacheado en Redis bajo
# 'mcp:product:context:{handle}:{market_id}' queda desactualizado.
# Sin este webhook, Claude puede sugerir el upsell con información
# antigua hasta que el TTL de 5 minutos expire naturalmente.
#
# Con este endpoint:
#   Shopify Admin edita producto → products/update → cache invalidado
#   → el siguiente request del chat hace un fetch fresco (~600ms)
#
# Payload de Shopify products/update:
#   { "id": 9978786152757, "handle": "vestido-corto-emma-champagne",
#     "title": "...", "product_type": "...", "tags": "...", ... }
#
# Seguridad: misma validación HMAC que customers y pages.
# Idempotencia: misma lógica SET NX de ShopifyWebhookHandler.
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/shopify/products",
    status_code=200,
    summary="Shopify Products Webhook (F-01)",
    description=(
        "Recibe eventos de productos de Shopify.\n"
        "Topics soportados (via X-Shopify-Topic):\n"
        "- `products/update` → invalidar cache de contexto de producto\n"
        "- `products/delete` → invalidar cache de contexto de producto"
    ),
)
async def handle_products_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_shopify_hmac_sha256: Optional[str] = Header(default=None),
    x_shopify_shop_domain: Optional[str] = Header(default=None),
    x_shopify_topic: Optional[str] = Header(default=None),
):
    """
    Receptor de webhooks de productos Shopify — F-01 Upsell Contextual.

    Invalida el cache 'mcp:product:context:{handle}:{market_id}' cuando
    un producto se actualiza en Shopify Admin, garantizando que Claude
    siempre tiene información fresca al construir el prompt de upsell.
    """
    # ── 1. Leer body raw (HMAC requiere los bytes exactos) ─────────────
    raw_body = await request.body()

    # ── 2. Validar HMAC ─────────────────────────────────────────────
    webhook_secret = settings.SHOPIFY_WEBHOOK_SECRET
    if not webhook_secret:
        logger.error("products_webhook_no_secret_configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not x_shopify_hmac_sha256:
        _inc_hmac_failure()
        logger.warning("products_webhook_missing_hmac", shop=x_shopify_shop_domain)
        raise HTTPException(status_code=401, detail="Missing HMAC header")

    if not validate_shopify_webhook(raw_body, x_shopify_hmac_sha256, webhook_secret):
        _inc_hmac_failure()
        logger.warning(
            "products_webhook_invalid_hmac",
            shop=x_shopify_shop_domain,
            topic=x_shopify_topic,
        )
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    # ── 3. Validar topic ─────────────────────────────────────────────
    topic = x_shopify_topic or ""
    SUPPORTED_TOPICS = {"products/update", "products/delete"}

    if topic not in SUPPORTED_TOPICS:
        # ACK sin procesar — evita reintentos de Shopify por topics no gestionados
        logger.info("products_webhook_topic_ignored", topic=topic)
        return {"status": "ignored", "reason": f"topic={topic} not handled here"}

    # ── 4. Parsear payload y extraer campos ─────────────────────────
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("products_webhook_invalid_json", topic=topic)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # products/update payload: { "id": 12345, "handle": "vestido-...", ... }
    product_id_raw = payload.get("id")
    product_handle = payload.get("handle", "").strip()

    if not product_id_raw:
        logger.warning(
            "products_webhook_missing_id",
            topic=topic,
            keys=list(payload.keys()),
        )
        # 200 para evitar reintentos — sin ID no podemos procesar
        return {"status": "ignored", "reason": "product_id not found in payload"}

    product_id = str(product_id_raw)

    # ── 5. Métrica de recepción ─────────────────────────────────────────
    _inc_received(topic)
    logger.info(
        "products_webhook_accepted",
        product_id=product_id,
        product_handle=product_handle,
        topic=topic,
        shop=x_shopify_shop_domain,
    )

    # ── 6. ACK inmediato + dispatch a BackgroundTask ────────────────
    background_tasks.add_task(
        _dispatch_product_event,
        product_id=product_id,
        product_handle=product_handle,
        topic=topic,
    )

    return {
        "status": "accepted",
        "product_id": product_id,
        "product_handle": product_handle,
        "topic": topic,
        "message": "Product webhook received, cache invalidation queued",
    }


async def _dispatch_product_event(
    product_id: str,
    product_handle: str,
    topic: str,
) -> None:
    """
    Procesa el webhook de producto en background tras el ACK.

    Delega a ShopifyWebhookHandler.handle_product_event() que implementa:
      - Idempotencia via Redis SET NX
      - Invalidación de cache 'mcp:product:context:{handle}:{market_id}'
        para todos los mercados activos (CL, CH, MX, ES)
      - Logging estructurado con duración

    Args:
        product_id:     ID numérico del producto como string.
        product_handle: Handle/slug del producto.
        topic:          'products/update' o 'products/delete'.
    """
    handler = ShopifyWebhookHandler()
    await handler.handle_product_event(
        product_id=product_id,
        product_handle=product_handle,
        topic=topic,
    )


@router.get(
    "/shopify/verify",
    summary="Webhook endpoint verification",
    description="Verifica que el endpoint está activo. Shopify lo usa durante el registro.",
)
async def verify_webhook_endpoint():
    """
    Endpoint de verificación usado durante el setup de webhooks en Shopify.

    Shopify realiza un GET a este endpoint antes de registrar la URL
    para confirmar que está accesible. Retorna 200 con la lista de
    topics aceptados.
    """
    return {
        "status": "ok",
        "message": "Shopify webhook endpoint is active (M4)",
        "supported_topics": [
            "pages/create",
            "pages/update",
            "pages/delete",
            "translations/update",
            "customers/update",
            "customers/purchasing_summary",
            "products/update",
            "products/delete",
        ],
        "endpoints": {
            "pages": "/api/webhooks/shopify/pages",
            "customers": "/api/webhooks/shopify/customers",
            "products": "/api/webhooks/shopify/products",
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# BACKGROUND DISPATCH — enruta al handler correcto según topic
# ══════════════════════════════════════════════════════════════════════════

async def _dispatch_background(
    page_id: int,
    page_handle: str,
    topic: str,
    locale: str,
) -> None:
    """
    Procesamiento real del webhook, ejecutado en background tras el ACK.

    Crea una instancia de ShopifyWebhookHandler (stateless) y delega
    a handle_page_event() o handle_translation_event() según el topic.

    Bug 6 FIX: ShopifyWebhookHandler resuelve sus dependencias (Redis,
    ShopifyKBSyncService) de forma lazy mediante el patrón ServiceFactory,
    sin necesitar que el router le inyecte nada. Esto es correcto porque
    las dependencias están disponibles a nivel de proceso cuando esta
    función se ejecuta en background.

    Args:
        page_id:      ID de la página Shopify afectada
        page_handle:  Handle/slug (solo para topics pages/*)
        topic:        Topic del webhook (pages/create, pages/update, etc.)
        locale:       Código de idioma (solo para translations/update)
    """
    # Bug 6 FIX: Handler creado sin argumentos — usa lazy init interno.
    # No se pasan redis_service ni sync_service porque el handler los
    # obtiene a través de get_redis_service() / ShopifyKBSyncService()
    # que siguen el patrón singleton del ServiceFactory.
    handler = ShopifyWebhookHandler()

    if topic == "translations/update":
        await handler.handle_translation_event(
            page_id=page_id,
            locale=locale,
        )
    else:
        # pages/create, pages/update, pages/delete
        await handler.handle_page_event(
            page_id=page_id,
            page_handle=page_handle,
            topic=topic,
        )


# ══════════════════════════════════════════════════════════════════════════
# HELPERS DE MÉTRICAS — Bug 5 FIX
# ══════════════════════════════════════════════════════════════════════════
# Encapsulados en funciones para aislar el ImportError si prometheus_metrics
# no está disponible en el entorno (ej. tests unitarios sin Prometheus).

def _inc_received(topic: str) -> None:
    """
    Incrementa kb_webhook_received_total para el topic dado.

    Se llama DESPUÉS de validar HMAC (solo webhooks legítimos).
    Permite detectar en Prometheus qué topics llegan con más frecuencia.
    """
    try:
        from src.api.core.prometheus_metrics import kb_webhook_received_total
        kb_webhook_received_total.labels(topic=topic).inc()
    except ImportError:
        pass


def _inc_hmac_failure() -> None:
    """
    Incrementa kb_webhook_hmac_failures_total.

    Se llama en AMBAS rutas de fallo HMAC:
    1. Header ausente    → posible error de configuración
    2. Firma inválida    → posible ataque / replay

    Una tasa alta en esta métrica en Prometheus debe disparar una alerta.
    """
    try:
        from src.api.core.prometheus_metrics import kb_webhook_hmac_failures_total
        kb_webhook_hmac_failures_total.inc()
    except ImportError:
        pass
