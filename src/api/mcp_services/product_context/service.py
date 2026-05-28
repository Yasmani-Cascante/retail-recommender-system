# src/api/mcp_services/product_context/service.py
"""
ProductContextService — F-01: Upsell Contextual (04/04/2026)
============================================================

Responsabilidad única: dado un product handle (string de URL como
"camisa-azul"), obtener los metadatos del producto necesarios para
construir un prompt de upsell contextual en MCPPersonalizationEngine.

Ubicación: src/api/mcp_services/product_context/service.py
Sigue el mismo patrón que CustomerProfileService en:
           src/api/mcp_services/customer/service.py

  - Una carpeta por dominio de servicio
  - Un único archivo service.py como boundary claro
  - Preparado para extracción como microservicio independiente
  - Usa structlog (mismo que customer/service.py)
  - Usa redis_service.get_json / set_json (mismo contrato)

Flujo:
    1. product_handle llega desde widget_context["product_id"]
       (extraído por extractProductId() del path /products/{handle})
    2. Redis cache hit  (~1ms)   → retorna dict normalizado
    3. Redis cache miss (~400ms) → 2x fetch Shopify REST + cachea 5 min
    4. Degradación graceful      → cualquier fallo retorna None
       El chat sigue funcionando sin contexto de producto.

Por qué TTL 5 minutos:
    - Título, tipo y tags de un producto cambian raramente.
    - El precio NO se incluye — los precios por mercado los resuelve
      get_prices_for_products() en tiempo real para las recomendaciones.
    - 5 min balancea frescura y reducción de llamadas a Shopify.

Integración:
    - Instanciado como singleton via ServiceFactory.get_product_context_service()
    - Llamado desde mcp_conversation_handler.py (bloque F-01), después del
      bloque F-04 (customer profile), antes de pasar mcp_context al engine.
    - El resultado se inyecta en mcp_context.current_product_context.
    - MCPPersonalizationEngine lee ese atributo al construir el prompt.

Redis key: product_ctx:{handle}:{market_id}   TTL 300 s (5 min)

Author: Senior Architecture Team
Version: 1.0.0 — F-01 MVP
Date: 04/04/2026
"""

from typing import Optional, Dict, Any

import os
import structlog

logger = structlog.get_logger(__name__)

# Prefijo de cache Redis — mismo estilo que customer/service.py
# customer usa "mcp:customer:profile:" → nosotros usamos "mcp:product:context:"
PRODUCT_CONTEXT_KEY_PREFIX = "mcp:product:context:"

# TTL del contexto cacheado: 5 minutos
# Más corto que customer (24h) porque el contexto de producto es menos personal
# y queremos refrescar si el título o las colecciones cambian.
PRODUCT_CONTEXT_TTL = 300


class ProductContextService:
    """
    Servicio de enriquecimiento de contexto de producto para upsell (F-01).

    Instanciado como singleton via ServiceFactory.get_product_context_service().
    Acepta redis=None y shopify=None para degradación graceful.

    Ejemplo de dict retornado (product_context):
        {
            "id":             "9978700071221",
            "handle":         "camisa-azul",
            "title":          "Camisa Oxford Azul",
            "product_type":   "Camisas",
            "tags":           ["formal", "manga larga", "algodón"],
            "collections":    ["Formal Men", "Novedades"],
            "vendor":         "Marca XYZ",
            "variants_count": 4,
        }
    """

    def __init__(self, shopify_client=None, redis_service=None):
        """
        Args:
            shopify_client: Instancia de ShopifyIntegration.
                            Acepta None — degradación graceful sin Shopify.
            redis_service:  Instancia de RedisService.
                            Acepta None — funciona sin cache (fetch en cada request).
        """
        self._shopify = shopify_client
        self._redis = redis_service

    # ──────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────

    async def get_product_context(
        self,
        handle: str,
        market_id: str = "CL",
    ) -> Optional[Dict[str, Any]]:
        """Retorna el contexto enriquecido del producto o None si no disponible.

        Flujo:
          1. Normaliza el handle (lowercase, sin slashes).
          2. Consulta Redis. Si existe → retorna el dict cacheado.
          3. Si miss → fetch desde Shopify, cachea y retorna.
          4. Si Shopify falla → retorna None (degradación graceful).

        Args:
            handle:    Handle del producto extraído de la URL
                       (ej. "camisa-azul" de /products/camisa-azul).
            market_id: ID de mercado activo (CL, CH, MX, ES).
                       Incluido en la cache key para futuras variantes por mercado.

        Returns:
            Dict con metadatos del producto, o None si no se pudo obtener.
        """
        # Normalizar: quitar slashes y espacios residuales del path parsing
        clean_handle = handle.strip().strip("/").lower()
        if not clean_handle:
            logger.warning("F-01 get_product_context called with empty handle")
            return None

        # ── 1. Cache hit ──────────────────────────────────────────────────
        cached = await self._get_from_cache(clean_handle, market_id)
        if cached is not None:
            logger.debug(
                "product_context_cache_hit",
                handle=clean_handle,
                market_id=market_id,
            )
            return cached

        # ── 2. Fetch desde Shopify ────────────────────────────────────────
        logger.info(
            "product_context_cache_miss_fetching",
            handle=clean_handle,
            market_id=market_id,
        )
        context = await self._fetch_from_shopify(clean_handle)
        if context is None:
            return None

        # ── 3. Cachear resultado ──────────────────────────────────────────
        await self._set_in_cache(clean_handle, market_id, context)
        return context

    async def invalidate(self, handle: str, market_id: str = "CL") -> None:
        """Invalida el cache del contexto de un producto.

        Útil si se registra un webhook products/update en el futuro (F-05).

        Args:
            handle:    Handle del producto a invalidar.
            market_id: Mercado cuyo cache se invalida.
        """
        if not self._redis or not handle:
            return
        key = _make_key(handle.strip().strip("/").lower(), market_id)
        await self._redis.delete(key)
        logger.info(
            "product_context_cache_invalidated",
            handle=handle,
            market_id=market_id,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internos — cache
    # ──────────────────────────────────────────────────────────────────────

    async def _get_from_cache(
        self, handle: str, market_id: str
    ) -> Optional[Dict[str, Any]]:
        """Lee el contexto desde Redis. Retorna None si no existe o Redis no disponible."""
        if not self._redis:
            return None
        key = _make_key(handle, market_id)
        # Usa get_json (mismo contrato que CustomerProfileService)
        return await self._redis.get_json(key)

    async def _set_in_cache(
        self, handle: str, market_id: str, context: Dict[str, Any]
    ) -> None:
        """Persiste el contexto en Redis. Fallo silencioso — el dato ya fue obtenido."""
        if not self._redis:
            return
        key = _make_key(handle, market_id)
        # Usa set_json (mismo contrato que CustomerProfileService)
        try:
            await self._redis.set_json(key, context, ttl=PRODUCT_CONTEXT_TTL)
            logger.info(
                "product_context_cached",
                handle=handle,
                market_id=market_id,
                ttl=PRODUCT_CONTEXT_TTL,
            )
        except Exception as e:
            # No crítico — el contexto ya fue obtenido, solo el cache falla.
            logger.warning(
                "product_context_cache_write_failed",
                handle=handle,
                error=str(e),
            )

    # ──────────────────────────────────────────────────────────────────────
    # Internos — fetch Shopify
    # ──────────────────────────────────────────────────────────────────────

    async def _fetch_from_shopify(
        self, handle: str
    ) -> Optional[Dict[str, Any]]:
        """Delega el fetch al método get_product_context_by_handle de ShopifyIntegration.

        ShopifyIntegration ya encapsula:
          - GET /products.json?handle= → producto + ID numérico
          - GET /collects.json?product_id= → collection_ids
          - GET /custom_collections/{id}.json + /smart_collections/{id}.json → títulos

        Este método solo delega y maneja la degradación graceful.

        TIMEOUT (fix Mayo 2026):
          Shopify puede tardar >2 minutos en responder si hay SSL errors con retries.
          Sin timeout, el request completo queda bloqueado 132s+ (observado en prod).
          Con asyncio.wait_for(10s), si Shopify no responde en 10s → retorna None
          y el handler continua sin contexto de producto (F-01 no aplica boost
          pero la respuesta llega en tiempo normal).
        """
        import asyncio  # noqa: PLC0415 — import local por convención del módulo

        # Timeout configurable via env var para flexibilidad en distintos entornos
        # PRODUCT_CONTEXT_TIMEOUT_S: default 10s, suficiente para Shopify en condiciones normales
        timeout_s = float(os.getenv("PRODUCT_CONTEXT_TIMEOUT_S", "10"))

        if not self._shopify:
            logger.warning(
                "product_context_no_shopify_client",
                handle=handle,
            )
            return None

        try:
            return await asyncio.wait_for(
                self._shopify.get_product_context_by_handle(handle=handle),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "product_context_fetch_timeout",
                handle=handle,
                timeout_s=timeout_s,
                note="proceeding without product context — F-01 boost not applied",
            )
            return None
        except Exception as e:
            logger.error(
                "product_context_fetch_error",
                handle=handle,
                error=str(e),
            )
            return None


# ──────────────────────────────────────────────────────────────────────────
# Helpers de módulo
# ──────────────────────────────────────────────────────────────────────────

def _make_key(handle: str, market_id: str) -> str:
    """Construye la clave Redis canónica para un contexto de producto.

    Formato: mcp:product:context:{handle}:{market_id}
    Ejemplo: mcp:product:context:camisa-azul:CL

    Incluir market_id permite cachear variantes por mercado si en el futuro
    el contexto incluye precio o disponibilidad específicos del mercado.
    """
    return f"{PRODUCT_CONTEXT_KEY_PREFIX}{handle}:{market_id}"
