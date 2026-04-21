"""
CustomerProfileService — F-04 Personalizacion por Historial de Cliente
=======================================================================

Responsabilidades:
  1. Fetch lazy del perfil de cliente desde Shopify API (customers/{id}.json
     + orders por cliente — ambos endpoints ya existentes en ShopifyClient).
  2. Cache del perfil en Redis con TTL 24 h para eliminar latencia en turnos
     sucesivos de la misma sesion.
  3. Invalidacion del cache cuando llega el webhook customers/update
     (ver ShopifyWebhookHandler.handle_customer_event).
  4. Clasificacion del cliente en LTV tier (new / returning / loyal / vip)
     que el motor de personalizacion usa para adaptar el tono de Claude.

Patron de uso (mcp_router.py):
    service = await ServiceFactory.get_customer_profile_service()
    profile  = await service.get_profile(customer_id)   # None si anonimo
    mcp_context.customer_profile = profile

Redis key:  mcp:customer:profile:{customer_id}   TTL 86400 s (24 h)
"""

import time
import logging
from typing import Optional, Dict, Any, List

import structlog

logger = structlog.get_logger(__name__)

# TTL del perfil cacheado (24 horas)
CUSTOMER_PROFILE_TTL = 86_400

# Prefijo de clave Redis
PROFILE_KEY_PREFIX = "mcp:customer:profile:"

# Umbral de LTV en USD/EUR para clasificar clientes
_LTV_THRESHOLDS = {
    "vip":       500.0,
    "loyal":     200.0,
    "returning":  50.0,
    # por debajo de 50 -> "new"
}

# Maximo de ordenes a fetchear para derivar categorias preferidas
_MAX_ORDERS = 5


class CustomerProfileService:
    """
    Servicio de perfil de cliente con lazy fetch y cache Redis.

    Instanciado como singleton via ServiceFactory.get_customer_profile_service().
    Acepta redis=None y shopify=None para degradacion graceful (usuario anonimo).
    """

    def __init__(self, redis_service=None, shopify_client=None, product_catalog=None):
        self._redis = redis_service
        self._shopify = shopify_client

        # Indice O(1): {str(product_id): product_type} construido una vez al init.
        # Permite que _derive_preferences() resuelva el product_type de cada
        # line_item de orden sin llamadas adicionales a Shopify ni a Redis.
        #
        # Por que se construye aqui y no en cada llamada:
        #   - product_catalog es el TFIDFRecommender singleton (3062 productos).
        #   - El indice se construye una sola vez cuando se crea el singleton de
        #     CustomerProfileService (primer request). Las llamadas sucesivas
        #     reusan el mismo dict en memoria — costo O(1) por lookup.
        #
        # Si product_catalog es None (ej. TF-IDF aun no cargado, o en tests),
        # el indice queda vacio y _derive_preferences() hace fallback al campo
        # product_type del line_item, que en ordenes REST de Shopify siempre
        # esta vacio — preferred_categories quedara [] como antes.
        self._product_type_index: Dict[str, str] = {}
        if product_catalog and hasattr(product_catalog, 'product_data'):
            for p in (product_catalog.product_data or []):
                pid = str(p.get('id', ''))
                ptype = (p.get('product_type') or '').strip()
                if pid and ptype:
                    self._product_type_index[pid] = ptype
            logger.info(
                'customer_profile_service_index_built',
                product_type_index_size=len(self._product_type_index),
            )

    # ──────────────────────────────────────────────────────────────────────
    # API publica
    # ──────────────────────────────────────────────────────────────────────

    async def get_profile(self, customer_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Retorna el perfil enriquecido del cliente o None si es anonimo.

        Flujo:
          1. Si customer_id es None/vacio → retorna None (usuario anonimo).
          2. Consulta Redis. Si existe → retorna el dict cacheado.
          3. Si miss → fetch desde Shopify, construye perfil, cachea y retorna.
          4. Si Shopify falla → retorna None (degradacion graceful).

        Args:
            customer_id: ID numerico de Shopify como string, o None.

        Returns:
            Dict con campos estandarizados del perfil, o None.
        """
        if not customer_id:
            return None

        # ── 1. Cache hit ──────────────────────────────────────────────────
        cached = await self._get_from_cache(customer_id)
        if cached is not None:
            logger.debug("customer_profile_cache_hit", customer_id=customer_id)
            return cached

        # ── 2. Fetch desde Shopify ────────────────────────────────────────
        logger.info("customer_profile_cache_miss_fetching", customer_id=customer_id)
        profile = await self._fetch_from_shopify(customer_id)
        if profile is None:
            return None

        # ── 3. Cachear resultado ──────────────────────────────────────────
        await self._set_in_cache(customer_id, profile)
        return profile

    async def invalidate(self, customer_id: str) -> None:
        """Invalida el cache del perfil. Llamado por el webhook customers/update.

        Args:
            customer_id: ID del cliente cuyo cache debe eliminarse.
        """
        if not self._redis or not customer_id:
            return
        key = f"{PROFILE_KEY_PREFIX}{customer_id}"
        await self._redis.delete(key)
        logger.info("customer_profile_cache_invalidated", customer_id=customer_id)

    # ──────────────────────────────────────────────────────────────────────
    # Internos
    # ──────────────────────────────────────────────────────────────────────

    async def _get_from_cache(self, customer_id: str) -> Optional[Dict[str, Any]]:
        if not self._redis:
            return None
        key = f"{PROFILE_KEY_PREFIX}{customer_id}"
        return await self._redis.get_json(key)

    async def _set_in_cache(self, customer_id: str, profile: Dict[str, Any]) -> None:
        if not self._redis:
            return
        key = f"{PROFILE_KEY_PREFIX}{customer_id}"
        await self._redis.set_json(key, profile, ttl=CUSTOMER_PROFILE_TTL)

    async def _fetch_from_shopify(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Fetch customer + orders desde Shopify y construye el perfil estandarizado."""
        if not self._shopify:
            logger.warning("customer_profile_no_shopify_client")
            return None

        try:
            # get_customer_by_id es sincrono — ejecutar en threadpool para no
            # bloquear el event loop (mismo patron que el resto de ShopifyClient)
            import asyncio
            loop = asyncio.get_event_loop()

            customer_data = await loop.run_in_executor(
                None, self._shopify.get_customer_by_id, customer_id
            )
            if not customer_data:
                return None

            orders = await loop.run_in_executor(
                None, self._shopify.get_orders_by_customer, customer_id, _MAX_ORDERS
            )

            return self._build_profile(customer_data, orders)

        except Exception as e:
            logger.error("customer_profile_fetch_error", customer_id=customer_id, error=str(e))
            return None

    # ──────────────────────────────────────────────────────────────────────
    # Construccion del perfil estandarizado
    # ──────────────────────────────────────────────────────────────────────

    def _build_profile(
        self, customer: Dict[str, Any], orders: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Transforma datos raw de Shopify en el perfil estandarizado para Claude.

        Campos del perfil:
          shopify_id         str  — ID unico de Shopify
          orders_count       int  — Pedidos totales segun Shopify
          total_spent        float — LTV en moneda de la tienda
          ltv_tier           str  — new | returning | loyal | vip
          tags               list — segmentos Shopify (ej. "wholesale", "vip")
          preferred_categories list — derivado de line_items de las ultimas ordenes
          top_brands         list — marcas mas compradas (vendor field)
          last_order_date    str  — ISO date de la ultima compra
          fetched_at         float — epoch para debugging de frescura
        """
        total_spent = float(customer.get("total_spent") or 0.0)
        orders_count = int(customer.get("orders_count") or 0)
        tags_raw = customer.get("tags") or ""
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        preferred_categories, top_brands = self._derive_preferences(
            orders, self._product_type_index
        )

        last_order_date = ""
        if orders:
            last_order_date = orders[0].get("created_at", "")[:10]  # ISO date only

        return {
            "shopify_id": str(customer.get("id", "")),
            "orders_count": orders_count,
            "total_spent": total_spent,
            "ltv_tier": self._classify_ltv(total_spent, orders_count),
            "tags": tags,
            "preferred_categories": preferred_categories,
            "top_brands": top_brands,
            "last_order_date": last_order_date,
            "fetched_at": time.time(),
        }

    @staticmethod
    def _classify_ltv(total_spent: float, orders_count: int) -> str:
        """Clasifica al cliente en un tier basado en LTV y numero de ordenes.

        Criterios:
          vip       — total_spent >= 500 EUR/USD
          loyal     — total_spent >= 200  o  orders_count >= 5
          returning — total_spent >=  50  o  orders_count >= 2
          new       — resto
        """
        if total_spent >= _LTV_THRESHOLDS["vip"]:
            return "vip"
        if total_spent >= _LTV_THRESHOLDS["loyal"] or orders_count >= 5:
            return "loyal"
        if total_spent >= _LTV_THRESHOLDS["returning"] or orders_count >= 2:
            return "returning"
        return "new"

    @staticmethod
    def _derive_preferences(
        orders: List[Dict[str, Any]],
        product_type_index: Dict[str, str] = None,
    ) -> tuple[List[str], List[str]]:
        """Extrae categorias y marcas preferidas de las ultimas N ordenes.

        La API REST de Shopify (/orders.json) NO incluye el campo product_type
        en los line_items de una orden — ese campo solo existe en el objeto
        producto del catalogo. Por eso se usa el product_type_index: un dict
        {str(product_id): product_type} construido en __init__() a partir del
        catalogo TF-IDF ya cargado en memoria.

        Flujo de resolucion de product_type para cada line_item:
          1. Lookup O(1) en product_type_index usando el product_id del item
             (fuente canonica — datos del catalogo TF-IDF, identicos a Shopify).
          2. Fallback a item.get('product_type') si el indice no esta disponible
             o el producto no se encuentra en el (poco probable pero defensivo).
          3. Si ninguna fuente tiene el valor, el item no contribuye a categorias.

        El campo vendor si viene en los line_items de ordenes REST y se usa
        directamente para top_brands sin lookup adicional.

        Retorna las 3 categorias y marcas mas frecuentes.
        """
        category_counts: Dict[str, int] = {}
        brand_counts: Dict[str, int] = {}

        for order in orders:
            for item in order.get("line_items", []):

                # -- Resolver product_type ----------------------------------
                # Intentar lookup en el indice del catalogo (fuente canonica).
                # product_id es int en el JSON de Shopify; convertir a str
                # para que coincida con las claves del indice.
                product_id = str(item.get("product_id") or "")
                if product_type_index and product_id:
                    product_type = product_type_index.get(product_id, "")
                else:
                    # Fallback: el campo directo del line_item (siempre vacio
                    # en ordenes REST, pero se mantiene por si Shopify cambia
                    # su comportamiento en el futuro).
                    product_type = (item.get("product_type") or "").strip()

                # -- Resolver vendor ----------------------------------------
                # vendor si viene en los line_items de ordenes REST de Shopify.
                vendor = (item.get("vendor") or "").strip()

                if product_type:
                    category_counts[product_type] = (
                        category_counts.get(product_type, 0) + 1
                    )
                if vendor:
                    brand_counts[vendor] = brand_counts.get(vendor, 0) + 1

        top_categories = sorted(
            category_counts, key=category_counts.get, reverse=True
        )[:3]
        top_brands = sorted(
            brand_counts, key=brand_counts.get, reverse=True
        )[:3]

        return top_categories, top_brands
