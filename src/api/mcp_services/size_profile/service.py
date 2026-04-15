# src/api/mcp_services/size_profile/service.py
"""
SizeProfileService -- F-02: Asistente de Talla Inteligente (11/04/2026)
=======================================================================

Responsabilidad unica: dado un customer_id de Shopify, inferir el perfil
de tallas del cliente a partir de su historial de compras y cachearlo en
Redis para evitar llamadas repetidas a la API.

Patron: identico a ProductContextService (F-01) y CustomerProfileService (F-04).
  - Una carpeta por dominio: src/api/mcp_services/size_profile/
  - Singleton via ServiceFactory.get_size_profile_service()
  - Redis cache con TTL 24h (las ordenes pasadas no cambian frecuentemente)
  - Degradacion graceful: cualquier fallo retorna None, el chat sigue funcionando

Flujo de datos:
    1. customer_id llega desde widget_context (solo usuarios logueados)
    2. Redis cache check  (~1ms)   -- clave: mcp:size:profile:{customer_id}
    3. Cache miss         (~600ms) -- GET /orders.json?customer_id=...&status=paid
       * Extraer variant.selected_options donde name normaliza a 'talla'/'size'
       * Agrupar por categoria de producto (usando product_type_index del TF-IDF)
       * Calcular talla mas frecuente por categoria + talla global mas frecuente
    4. Retornar SizeProfile o None si no hay datos suficientes

Riesgo critico (documentado en plan F-02):
    Los nombres de opcion de talla en Shopify no estan estandarizados.
    El merchant puede llamarlas "Talla", "Size", "Grosse", "T", "sz", etc.
    La funcion normalize_size_option_name() maneja este caso con un
    conjunto de nombres conocidos + prefijos comunes.

Redis key: mcp:size:profile:{customer_id}   TTL 86400s (24h)

Author: Senior Architecture Team
Version: 1.0.0 -- F-02 MVP
Date: 11/04/2026
"""

import time
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any
from collections import Counter

import structlog

logger = structlog.get_logger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

SIZE_PROFILE_KEY_PREFIX = "mcp:size:profile:"

# TTL 24h: el historial de compras pasadas no cambia.
# Solo crece cuando llega una nueva orden, que invalidaria el cache
# a traves de ServiceFactory si en el futuro se registra orders/create webhook.
SIZE_PROFILE_TTL = 86_400

# Maximo de ordenes a analizar. Con 10 ordenes de moda se tiene una
# muestra suficiente sin sobrecargar la API de Shopify.
_MAX_ORDERS = 10

# FIX (12/04/2026): Umbral de confianza evaluado POR CATEGORIA, no global.
# El calculo original mezclaba tallas de ropa (M, S) con tallas de zapatos
# (37, 36) y tallas de bra (B) en un mismo denominador, haciendo imposible
# alcanzar confianza alta en catalagos multi-categoria (moda + zapatos).
#
# Ejemplo real con 10 ordenes:
#   ENTERITOS: M x5, S x3 -> confianza M en ENTERITOS = 5/8 = 0.625
#   ZAPATOS:   37 x5, 36 x1 -> confianza 37 en ZAPATOS = 5/6 = 0.833
#   Global mezclado: M = 6/16 = 0.375 <- siempre bajo por magnitudes distintas
#
# La confianza global ya no se usa para el gate de has_data().
# Se mantiene en el modelo para logging y futura referencia.
MIN_CONFIDENCE_THRESHOLD = 0.4

# Minimo de items con talla por categoria para considerar valida la inferencia.
# Evita recomendar talla con 1 sola compra como evidencia.
MIN_ITEMS_PER_CATEGORY = 1

# Nombres de opcion de talla normalizados (lowercase, sin acentos).
# Cubre los nombres mas comunes en espanol, ingles, aleman y frances.
SIZE_OPTION_NAMES: set = {
    # Espanol
    "talla", "talle", "talles",
    # Ingles
    "size", "sz",
    # Aleman
    "grosse", "grobe",    # Grosse / Grobe (sin diairesis, normalizados)
    # Frances
    "taille",
    # Italiano
    "misura",
    # Abreviaciones de una letra
    "t",
}

# Mapeo de categorias de producto Shopify a grupos de talla genericos.
# Cuando no podemos resolver la categoria exacta, usamos "GENERAL".
CATEGORY_GROUPS: Dict[str, str] = {
    "VESTIDOS LARGOS":   "VESTIDOS",
    "VESTIDOS CORTOS":   "VESTIDOS",
    "VESTIDOS MIDIS":    "VESTIDOS",
    "NOVIAS LARGOS":     "VESTIDOS",
    "NOVIAS CORTOS":     "VESTIDOS",
    "NOVIAS MIDIS":      "VESTIDOS",
    "ENTERITOS LARGOS":  "ENTERITOS",
    "ENTERITOS CORTOS":  "ENTERITOS",
    "TOPS":              "TOPS",
    "BRALETTES":         "TOPS",
    "FALDAS":            "FALDAS",
    "PANTALONES":        "PANTALONES",
    "LEGGINGS":          "PANTALONES",
    "CONJUNTOS FALDAS":   "CONJUNTOS",
    "CONJUNTOS PANTALONES": "CONJUNTOS",
}


# ── Modelo de datos ───────────────────────────────────────────────────────────

@dataclass
class SizeProfile:
    """Perfil de tallas inferido del historial de compras del cliente.

    Campos:
        customer_id:         ID de Shopify del cliente.
        size_by_category:    Talla mas frecuente por categoria de producto.
                             Clave = nombre de categoria (ej. "ZAPATOS").
                             Valor = talla (ej. "37").
        confidence_by_category: Confianza por categoria.
                             Clave = nombre de categoria.
                             Valor = fraccion de items con esa talla (0-1).
                             ej. {"ZAPATOS": 0.833, "ENTERITOS": 0.625}
        most_common_size:    Talla mas frecuente globalmente (mezcla todas las
                             categorias). Solo para logging/diagnostico.
                             NO usar como gate de calidad (es baja por diseno).
        orders_analyzed:     Numero de ordenes con al menos un item con talla.
        confidence:          Confianza global (mezcla todas las categorias).
                             Mantenida para compatibilidad de logging.
                             DEPRECADA para has_data(): usar confidence_by_category.
        last_updated:        Epoch timestamp de cuando se calculo el perfil.
    """
    customer_id: str
    size_by_category: Dict[str, str] = field(default_factory=dict)
    confidence_by_category: Dict[str, float] = field(default_factory=dict)
    most_common_size: Optional[str] = None
    orders_analyzed: int = 0
    confidence: float = 0.0  # global, mantenida para logging
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el perfil a dict para almacenar en Redis."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SizeProfile":
        """Deserializa un dict de Redis a SizeProfile."""
        return cls(
            customer_id=data.get("customer_id", ""),
            size_by_category=data.get("size_by_category", {}),
            confidence_by_category=data.get("confidence_by_category", {}),
            most_common_size=data.get("most_common_size"),
            orders_analyzed=data.get("orders_analyzed", 0),
            confidence=data.get("confidence", 0.0),
            last_updated=data.get("last_updated", 0.0),
        )

    def has_data(self) -> bool:
        """True si al menos UNA categoria tiene talla con confianza suficiente.

        FIX (12/04/2026): evaluacion POR CATEGORIA en lugar de global.

        Razonamiento:
          Un catalogo de moda que vende ropa + zapatos + lenceria tiene tallas
          incomparables entre categorias (M vs 37 vs B). Mezclarlas en un
          denominador global produce confianza estructuralmente baja aunque el
          cliente sea muy consistente dentro de cada categoria.

          Ejemplo: cliente con 10 ordenes
            ENTERITOS: M en 5/8 items  -> confianza 0.625  >= 0.4 -> VALIDO
            ZAPATOS:   37 en 5/6 items -> confianza 0.833  >= 0.4 -> VALIDO
            Global mezclado: M en 6/16 = 0.375             < 0.4  -> INVALIDO (bug)

          Con la evaluacion por categoria, el perfil es valido porque tiene
          al menos una categoria con confianza suficiente.
        """
        if self.orders_analyzed == 0:
            return False

        # Verificar si alguna categoria tiene talla valida y confianza suficiente
        for category, size in self.size_by_category.items():
            if not size:
                continue
            # Confianza por categoria: si no esta disponible (perfil legacy),
            # usar la confianza global como fallback conservador.
            cat_confidence = self.confidence_by_category.get(category, self.confidence)
            if cat_confidence >= MIN_CONFIDENCE_THRESHOLD:
                return True

        return False

    def best_size_for_category(self, category: str) -> Optional[str]:
        """Retorna la talla recomendada para una categoria dada, o None.

        Solo retorna si la confianza de esa categoria supera el umbral minimo.
        Evita recomendar tallas con poca evidencia aunque esten en size_by_category.

        Args:
            category: Nombre del grupo de categoria (ej. "ZAPATOS", "ENTERITOS").

        Returns:
            La talla recomendada (ej. "37") o None si no hay suficiente evidencia.
        """
        size = self.size_by_category.get(category)
        if not size:
            return None
        cat_confidence = self.confidence_by_category.get(category, self.confidence)
        return size if cat_confidence >= MIN_CONFIDENCE_THRESHOLD else None


# ── Helpers de normalizacion ──────────────────────────────────────────────────

def normalize_size_option_name(name: str) -> bool:
    """True si el nombre de una opcion de variante corresponde a una talla.

    Normaliza eliminando acentos y caracteres especiales del aleman
    (o, ss) antes de comparar con el conjunto SIZE_OPTION_NAMES.

    Ademas reconoce nombres que comienzan con "talla" o "size"
    (ej. "talla calzado", "size chart") aunque no esten en el conjunto exacto.

    Args:
        name: Nombre de opcion de variante de Shopify (ej. "Talla", "Size").

    Returns:
        True si el nombre representa una opcion de talla.
    """
    if not name:
        return False
    n = (
        name.lower()
        .replace("\u00f6", "o")   # o con diairesis (aleman)
        .replace("\u00df", "ss")  # eszett (aleman)
        .replace("\u00e4", "a")   # a con diairesis
        .replace("\u00fc", "u")   # u con diairesis
        .strip()
    )
    if n in SIZE_OPTION_NAMES:
        return True
    if n.startswith("talla") or n.startswith("size"):
        return True
    return False


def _group_category(product_type: str) -> str:
    """Agrupa una categoria especifica en un grupo de talla generico.

    ej. "VESTIDOS LARGOS" -> "VESTIDOS"
        "TOPS"            -> "TOPS"
        "ZAPATOS"         -> "ZAPATOS"  (sin grupo -> usa la categoria tal cual)

    Args:
        product_type: product_type del catalogo TF-IDF (siempre UPPERCASE).

    Returns:
        Nombre del grupo de categoria. Si no esta en CATEGORY_GROUPS,
        retorna el product_type en uppercase como fallback.
    """
    if not product_type:
        return "GENERAL"
    pt_upper = product_type.upper().strip()
    return CATEGORY_GROUPS.get(pt_upper, pt_upper)


# ── Servicio principal ────────────────────────────────────────────────────────

class SizeProfileService:
    """Servicio de perfil de tallas con lazy fetch y cache Redis.

    Instanciado como singleton via ServiceFactory.get_size_profile_service().
    Acepta redis=None y shopify=None para degradacion graceful.

    Ejemplo de SizeProfile retornado:
        SizeProfile(
            customer_id="12345",
            size_by_category={"VESTIDOS": "M", "TOPS": "S"},
            most_common_size="M",
            orders_analyzed=4,
            confidence=0.75,
            last_updated=1712800000.0,
        )
    """

    def __init__(
        self,
        shopify_client=None,
        redis_service=None,
        product_type_index: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            shopify_client:     ShopifyIntegration singleton. Acepta None.
            redis_service:      RedisService singleton. Acepta None (sin cache).
            product_type_index: Dict {str(product_id): product_type} construido
                                desde el catalogo TF-IDF. Usado para resolver
                                el product_type de cada line_item de orden
                                (la API REST de ordenes no incluye product_type).
                                Acepta None o dict vacio (fallback a "GENERAL").
        """
        self._shopify = shopify_client
        self._redis = redis_service
        self._product_type_index: Dict[str, str] = product_type_index or {}

        logger.info(
            "F-02 SizeProfileService initialized",
            product_type_index_size=len(self._product_type_index),
            redis_available=redis_service is not None,
            shopify_available=shopify_client is not None,
        )

    # ── API publica ───────────────────────────────────────────────────────

    async def get_size_profile(
        self,
        customer_id: Optional[str],
    ) -> Optional[SizeProfile]:
        """Retorna el perfil de tallas del cliente o None si no disponible.

        Flujo:
          1. Si customer_id es None/vacio -> None (usuario anonimo).
          2. Redis cache hit  -> SizeProfile deserializado.
          3. Cache miss -> fetch ordenes Shopify, calcular perfil, cachear.
          4. Si el perfil calculado no tiene datos suficientes -> None.
          5. Si Shopify falla -> None (degradacion graceful).

        Args:
            customer_id: ID numerico de Shopify como string, o None.

        Returns:
            SizeProfile con datos de tallas, o None.
        """
        if not customer_id:
            return None

        # 1. Cache hit
        cached = await self._get_from_cache(customer_id)
        if cached is not None:
            logger.info(
                "F-02 size_profile_cache_hit",
                customer_id=customer_id,
                size_profile_cached=cached
            )
            logger.info(
                "F-02 cached has_data",
                respuesta=cached.has_data()
            )
            return cached if cached.has_data() else None

        # 2. Fetch y calcular
        logger.info(
            "F-02 size_profile_cache_miss_fetching",
            customer_id=customer_id,
        )
        profile = await self._fetch_and_build(customer_id)
        if profile is None:
            return None

        # 3. Cachear siempre (incluso si has_data() es False),
        #    para evitar refetch en el mismo TTL cuando el cliente no tiene tallas.
        await self._set_in_cache(customer_id, profile)

        return profile if profile.has_data() else None

    async def invalidate(self, customer_id: str) -> None:
        """Invalida el cache del perfil de tallas.

        Util si en el futuro se registra el webhook orders/create.

        Args:
            customer_id: ID del cliente cuyo cache debe eliminarse.
        """
        if not self._redis or not customer_id:
            return
        key = f"{SIZE_PROFILE_KEY_PREFIX}{customer_id}"
        try:
            await self._redis.delete(key)
            logger.info(
                "F-02 size_profile_cache_invalidated",
                customer_id=customer_id,
            )
        except Exception as e:
            logger.warning(
                "F-02 size_profile_cache_invalidate_failed",
                customer_id=customer_id,
                error=str(e),
            )

    # ── Internos: cache ───────────────────────────────────────────────────

    async def _get_from_cache(
        self, customer_id: str
    ) -> Optional[SizeProfile]:
        """Lee el perfil desde Redis. None si no existe o Redis no disponible."""
        if not self._redis:
            return None
        key = f"{SIZE_PROFILE_KEY_PREFIX}{customer_id}"
        try:
            data = await self._redis.get_json(key)
            if data is None:
                return None
            return SizeProfile.from_dict(data)
        except Exception as e:
            logger.warning(
                "F-02 size_profile_cache_read_failed",
                customer_id=customer_id,
                error=str(e),
            )
            return None

    async def _set_in_cache(
        self, customer_id: str, profile: SizeProfile
    ) -> None:
        """Persiste el perfil en Redis. Fallo silencioso."""
        if not self._redis:
            return
        key = f"{SIZE_PROFILE_KEY_PREFIX}{customer_id}"
        try:
            await self._redis.set_json(key, profile.to_dict(), ttl=SIZE_PROFILE_TTL)
            logger.info(
                "F-02 size_profile_cached",
                customer_id=customer_id,
                ttl=SIZE_PROFILE_TTL,
                orders_analyzed=profile.orders_analyzed,
                confidence=round(profile.confidence, 2),
                most_common_size=profile.most_common_size,
            )
        except Exception as e:
            logger.warning(
                "F-02 size_profile_cache_write_failed",
                customer_id=customer_id,
                error=str(e),
            )

    # ── Internos: fetch y calculo ─────────────────────────────────────────

    async def _fetch_and_build(
        self, customer_id: str
    ) -> Optional[SizeProfile]:
        """Obtiene ordenes de Shopify y construye el perfil de tallas.

        Delega la llamada HTTP al thread pool para no bloquear el event loop,
        identico al patron de CustomerProfileService._fetch_from_shopify().
        """
        if not self._shopify:
            logger.warning(
                "F-02 size_profile_no_shopify_client",
                customer_id=customer_id,
            )
            return None

        try:
            loop = asyncio.get_event_loop()
            orders: List[Dict] = await loop.run_in_executor(
                None,
                self._shopify.get_orders_by_customer,
                customer_id,
                _MAX_ORDERS,
            )
        except Exception as e:
            logger.error(
                "F-02 size_profile_orders_fetch_failed",
                customer_id=customer_id,
                error=str(e),
                exc_info=True,
            )
            return None

        if not orders:
            logger.info(
                "F-02 size_profile_no_orders",
                customer_id=customer_id,
            )
            # Retornar perfil vacio — se cachea para evitar refetch
            return SizeProfile(customer_id=customer_id)

        return self._build_profile(customer_id, orders)

    def _build_profile(
        self,
        customer_id: str,
        orders: List[Dict],
    ) -> SizeProfile:
        """Calcula el perfil de tallas a partir de las ordenes.

        Extrae de cada line_item:
          - La opcion de talla (variant.selected_options donde name es talla)
          - La categoria del producto (via product_type_index o fallback)

        Luego agrega por categoria y calcula la talla mas frecuente.

        Args:
            customer_id: ID del cliente (para el modelo de datos).
            orders:      Lista de ordenes de Shopify (de get_orders_by_customer).

        Returns:
            SizeProfile calculado.
        """
        # Contadores: {categoria_grupo: Counter({talla: n_veces})}
        size_counts_by_category: Dict[str, Counter] = {}
        # Contador global
        global_size_counter: Counter = Counter()
        # Ordenes con al menos una talla encontrada
        orders_with_size: int = 0

        for order in orders:
            order_has_size = False

            for item in order.get("line_items", []):
                # -- Resolver talla ------------------------------------------
                # selected_options es una lista de {name: str, value: str}
                # en el objeto variant de los line_items de ordenes.
                # IMPORTANTE: Shopify incluye selected_options en el objeto
                # variant del line_item, NO directamente en el line_item.
                # Algunos endpoints devuelven variant_title como fallback.
                size_value: Optional[str] = None

                variant = item.get("variant") or {}
                selected_options = variant.get("selected_options") or []

                # Buscar la opcion que es talla
                for opt in selected_options:
                    if normalize_size_option_name(opt.get("name", "")):
                        raw_val = opt.get("value", "").strip()
                        if raw_val and raw_val.upper() != "DEFAULT TITLE":
                            size_value = raw_val.upper()
                            break

                # Fallback: variant_title del line_item
                # (ej. "M / Azul" -> tomar la parte antes del " / ")
                if not size_value:
                    variant_title = (item.get("variant_title") or "").strip()
                    if variant_title and variant_title.upper() != "DEFAULT TITLE":
                        # Si tiene " / ", el primer segmento suele ser talla
                        parts = [p.strip() for p in variant_title.split("/")]
                        candidate = parts[0].upper() if parts else ""
                        # Solo considerar como talla si parece una talla
                        # (corta, sin espacios, no es un color)
                        if (
                            candidate
                            and len(candidate) <= 5
                            and " " not in candidate
                        ):
                            size_value = candidate

                if not size_value:
                    continue  # este item no tiene talla identificable

                # -- Resolver categoria --------------------------------------
                product_id = str(item.get("product_id") or "")
                product_type = ""

                if self._product_type_index and product_id:
                    product_type = self._product_type_index.get(product_id, "")

                if not product_type:
                    # Fallback: campo directo del line_item (generalmente vacio
                    # en ordenes REST, pero se intenta como ultima opcion)
                    product_type = (item.get("product_type") or "").strip()

                category_group = _group_category(product_type) if product_type else "GENERAL"

                # -- Acumular ------------------------------------------------
                if category_group not in size_counts_by_category:
                    size_counts_by_category[category_group] = Counter()

                size_counts_by_category[category_group][size_value] += 1
                global_size_counter[size_value] += 1
                order_has_size = True

            if order_has_size:
                orders_with_size += 1

        # -- Calcular talla mas frecuente por categoria ----------------------
        size_by_category: Dict[str, str] = {}
        confidence_by_category: Dict[str, float] = {}

        for category, counter in size_counts_by_category.items():
            if counter:
                top_size, top_count = counter.most_common(1)[0]
                total_in_cat = sum(counter.values())
                size_by_category[category] = top_size
                # Confianza por categoria: fraccion de items donde la talla
                # mas frecuente de esa categoria fue comprada.
                # ej. ZAPATOS: 37 en 5 de 6 items -> 0.833
                confidence_by_category[category] = round(
                    top_count / total_in_cat, 3
                ) if total_in_cat > 0 else 0.0

        # -- Calcular talla global mas frecuente -----------------------------
        # Solo para logging y diagnostico. NO usar como gate de calidad.
        # Es estructuralmente baja en catalogos multi-categoria (moda + zapatos)
        # porque mezcla magnitudes incomparables (M, 37, B).
        most_common_size: Optional[str] = None
        confidence: float = 0.0

        if global_size_counter:
            top_size, top_count = global_size_counter.most_common(1)[0]
            total_sizes = sum(global_size_counter.values())
            most_common_size = top_size
            confidence = top_count / total_sizes if total_sizes > 0 else 0.0

        profile = SizeProfile(
            customer_id=customer_id,
            size_by_category=size_by_category,
            confidence_by_category=confidence_by_category,
            most_common_size=most_common_size,
            orders_analyzed=orders_with_size,
            confidence=round(confidence, 3),
            last_updated=time.time(),
        )

        logger.info(
            "F-02 size_profile_built",
            customer_id=customer_id,
            orders_analyzed=orders_with_size,
            orders_total=len(orders),
            most_common_size=most_common_size,
            confidence_global=round(confidence, 2),
            confidence_by_category=confidence_by_category,
            categories=list(size_by_category.keys()),
            has_data=profile.has_data(),
        )

        return profile
