# src/api/mcp/adapters/market_manager.py
"""
Market Context Manager - Enterprise Integration
===============================================

Gestiona contexto específico por mercado con soporte para:
- RedisService (enterprise, recomendado)
- AsyncRedisWrapper (legacy fallback)
- Graceful degradation sin Redis

Author: Senior Architecture Team
Date: 2025-11-28
Version: 2.0.0 - Enterprise Migration

FIX APLICADO:
- ✅ TYPE_CHECKING pattern para evitar "RedisService is not defined"
- ✅ Soporte para RedisService (enterprise) como prioridad
- ✅ Fallback a AsyncRedisWrapper (legacy)
- ✅ Graceful degradation sin Redis
"""

from typing import Dict, Optional, List, Any, TYPE_CHECKING
import asyncio
import json
import logging
import random
from datetime import datetime

# ✅ TYPE_CHECKING: Evita circular imports y define tipo para type hints
if TYPE_CHECKING:
    from src.api.core.redis_service import RedisService

# ✅ LEGACY SUPPORT: Mantener compatibilidad con AsyncRedisWrapper
# try:
#     from src.api.core.cache import (
#         get_redis_client, 
#         AsyncRedisWrapper, 
#         get_async_redis_wrapper
#     )
# except ImportError as e:
#     logging.error(f"Error importando cache: {e}")
#     get_redis_client = None
#     AsyncRedisWrapper = None
#     get_async_redis_wrapper = None

# ✅ NOTA: Ya no necesitamos importar AsyncRedisWrapper
#    ServiceFactory siempre proporciona RedisService

logger = logging.getLogger(__name__)

class MarketContextManager:
    """
    🌍 ENTERPRISE MARKET CONTEXT MANAGER
    
    Gestiona contexto específico por mercado con:
    - Detección automática de mercado
    - Configuración específica por región  
    - Adaptación de recomendaciones
    - Cálculo de precios localizados
    
    Versión: 2.0.0 - Enterprise Migration
    """
    
    def __init__(
        self,
        redis_service: 'RedisService',  # ← REQUIRED (no Optional)
        default_market: str = "US"
        # redis_service= None,  # type: ignore  
        # default_market: str = "US" 
    ):
        """
        Initialize Market Context Manager with Redis enterprise service.
        
        Args:
            redis_service: RedisService instance (from ServiceFactory).
                        Handles graceful degradation internally - returns None/False on errors.
            default_market: Default market to use (default: "US")
        
        Architecture:
            - ALWAYS use ServiceFactory.get_market_context_manager() to obtain instances
            - RedisService manages connection, pooling, and graceful degradation internally
            - No fallback needed - service layer handles all error cases
            
        Usage:
            # ✅ CORRECT (via ServiceFactory):
            manager = await ServiceFactory.get_market_context_manager()
            
            # ❌ INCORRECT (direct instantiation):
            # manager = MarketContextManager(...)  # Don't do this
        
        Author: Senior Architecture Team
        Version: 3.0.0 - Simplified Architecture (Dead Code Removed)
        Date: 2025-11-29
        """
        self.default_market = default_market
        self.redis = redis_service
        self.market_configs = {}
        self._initialized = False
        
        logger.info(
            f"✅ MarketContextManager initialized with RedisService (enterprise) | "
            f"Default market: {default_market}"
        )
        
    async def ensure_initialized(self):
        """Asegura que el manager esté inicializado (lazy initialization)"""
        if not self._initialized:
            await self.initialize()
        
    async def initialize(self):
        """Inicializar gestor de mercados"""
        if self._initialized:
            return True
            
        logger.info("🔄 Initializing Market Manager...")
        
        # Cargar configuraciones de mercados soportados
        self.market_configs = await self.get_supported_markets()
        self._initialized = True
        
        logger.info(
            f"✅ Market Manager initialized with {len(self.market_configs)} markets"
        )
        return True
        
    async def detect_market(self, request_context: Dict) -> str:
        """
        Detectar mercado basado en contexto de request.
        
        Args:
            request_context: Diccionario con contexto del request:
                - market_id: ID explícito del mercado
                - country_code: Código de país (para geolocation)
                - user_id: ID de usuario (para preferencias cacheadas)
        
        Returns:
            str: Market ID detectado (o "default")
        
        Priority Order:
            1. Explicit market_id en request
            2. Geolocation basado en country_code
            3. User preference cacheada en Redis
            4. Default market
        """
        await self.ensure_initialized()
        
        # Priority order: explicit > geolocation > user preference > default
        
        if request_context.get('market_id'):
            return request_context['market_id']
            
        if geo_country := request_context.get('country_code'):
            return self._country_to_market(geo_country)
            
        if user_id := request_context.get('user_id'):
            if self.redis:
                cached_preference = await self.redis.get(f"user_market:{user_id}")
                if cached_preference:
                    return cached_preference
                
        return self.default_market
    
    async def get_market_config(self, market_id: str) -> Dict:
        """
        Obtener configuración específica del mercado.
        
        Args:
            market_id: ID del mercado (US, ES, MX, CL, etc.)
        
        Returns:
            Dict con configuración del mercado incluyendo:
                - name: Nombre del mercado
                - currency: Moneda local
                - language: Idioma principal
                - timezone: Zona horaria
                - scoring_weights: Pesos para scoring
                - localization: Configuración de localización
        
        Cache Strategy:
            1. Check Redis cache (1 hour TTL)
            2. Load from config file
            3. Fallback to supported_markets
            4. Ultimate fallback to "default" market
        """
        await self.ensure_initialized()
        
        cache_key = f"market_config:{market_id}"
        
        # Check cache first
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                return cached  # RedisCache ya deserializa automáticamente
            
        # Load from configuration files or fall back to supported markets
        try:
            config_path = f"config/markets/{market_id}/config.json"
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Cache for 1 hour
            if self.redis:
                await self.redis.set(cache_key, config, ttl=3600)
            return config
            
        except FileNotFoundError:
            # Fallback to supported markets
            supported_markets = await self.get_supported_markets()
            if market_id in supported_markets:
                return supported_markets[market_id]
            
            # Ultimate fallback to default
            return supported_markets.get("default", {})
    
    async def get_supported_markets(self) -> Dict[str, Dict]:
        """
        Obtener lista de mercados soportados.
        
        Returns:
            Dict[str, Dict]: Mapa de market_id -> configuración
        
        Markets Soportados:
            - US: United States (USD)
            - ES: Spain (EUR)
            - MX: Mexico (MXN)
            - CL: Chile (CLP)
            - default: Global fallback (USD)
        
        Cache Strategy:
            - Redis cache: 24 hours TTL
            - Recarga automática en cada deploy
        """
        cache_key = "supported_markets"
        
        # Check cache first
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                return cached  # RedisCache ya deserializa automáticamente
        
        # Definición de mercados soportados
        markets = {
            "US": {
                "name": "United States",
                "currency": "USD",
                "language": "en",
                "timezone": "America/New_York",
                "enabled": True,
                "scoring_weights": {
                    "relevance": 0.5,
                    "popularity": 0.3,
                    "profit_margin": 0.2
                },
                "localization": {
                    "date_format": "MM/DD/YYYY",
                    "cultural_preferences": {
                        "size_system": "US",
                        "preferred_categories": ["electronics", "clothing"]
                    }
                }
            },
            "ES": {
                "name": "Spain",
                "currency": "EUR",
                "language": "es",
                "timezone": "Europe/Madrid",
                "enabled": True,
                "scoring_weights": {
                    "relevance": 0.4,
                    "popularity": 0.4,
                    "profit_margin": 0.2
                },
                "localization": {
                    "date_format": "DD/MM/YYYY",
                    "cultural_preferences": {
                        "size_system": "EU",
                        "preferred_categories": ["fashion", "home"]
                    }
                }
            },
            "MX": {
                "name": "Mexico",
                "currency": "MXN",
                "language": "es",
                "timezone": "America/Mexico_City",
                "enabled": True,
                "scoring_weights": {
                    "relevance": 0.4,
                    "popularity": 0.3,
                    "profit_margin": 0.3
                },
                "localization": {
                    "date_format": "DD/MM/YYYY",
                    "cultural_preferences": {
                        "size_system": "MX",
                        "preferred_categories": ["electronics", "home"]
                    }
                }
            },
            "CL": {
                "name": "Chile",
                "currency": "CLP",
                "language": "es",
                "timezone": "America/Santiago",
                "enabled": True,
                "scoring_weights": {
                    "relevance": 0.45,
                    "popularity": 0.35,
                    "profit_margin": 0.2
                },
                "localization": {
                    "date_format": "DD/MM/YYYY",
                    "cultural_preferences": {
                        "size_system": "EU",
                        "preferred_categories": ["fashion", "electronics", "home"],
                        "seasonal_adjustments": {
                            "summer": [12, 1, 2],
                            "winter": [6, 7, 8]
                        }
                    }
                }
            },
            "default": {
                "name": "Global",
                "currency": "USD",
                "language": "en",
                "timezone": "UTC",
                "enabled": True,
                "scoring_weights": {
                    "relevance": 0.5,
                    "popularity": 0.3,
                    "profit_margin": 0.2
                },
                "localization": {
                    "date_format": "YYYY-MM-DD",
                    "cultural_preferences": {
                        "size_system": "US",
                        "preferred_categories": ["electronics", "clothing"]
                    }
                }
            }
        }
        
        # Cache for 24 hours
        if self.redis:
            await self.redis.set(cache_key, markets, ttl=86400)
        
        return markets
    
    async def adapt_recommendations_for_market(
        self, 
        recommendations: List[Dict], 
        market_id: str
    ) -> List[Dict]:
        """
        Adaptar recomendaciones para mercado específico.
        
        Args:
            recommendations: Lista de recomendaciones base
            market_id: ID del mercado target
        
        Returns:
            List[Dict]: Recomendaciones adaptadas con:
                - market_price: Precio localizado
                - market_score: Score ajustado por mercado
                - localized_title: Título localizado
                - market_factors: Metadata de mercado
                - viability_score: Score de viabilidad
        
        Adaptations Applied:
            1. Validación de disponibilidad en mercado
            2. Cálculo de precios localizados (con impuestos)
            3. Ajuste de scoring con pesos de mercado
            4. Localización de contenido
            5. Metadata de mercado
        """
        await self.ensure_initialized()
        
        market_config = await self.get_market_config(market_id)
        
        adapted = []
        for rec in recommendations:
            # Validate availability in market
            if not await self._is_available_in_market(rec.get('id'), market_id):
                continue
                
            # Calculate landed costs
            rec['market_price'] = await self._calculate_landed_cost(
                rec.get('price', 0), market_id
            )
            
            # Apply market-specific scoring weights
            rec['market_score'] = self._apply_market_weights(
                rec.get('score', 0.5), market_config.get('scoring_weights', {})
            )
            
            # Localize content
            rec['localized_title'] = await self._localize_content(
                rec.get('title', ''), market_config.get('language', 'en')
            )
            
            # Add market factors
            rec['market_factors'] = {
                "market_id": market_id,
                "currency": market_config.get("currency", "USD"),
                "adaptation_timestamp": datetime.utcnow().isoformat()
            }
            
            # Calculate viability score (combination of factors)
            rec['viability_score'] = 0.8  # Default high score
            
            adapted.append(rec)
            
        # Sort by market-adjusted score
        adapted.sort(key=lambda x: x['market_score'], reverse=True)
        return adapted
        
    def _country_to_market(self, country_code: str) -> str:
        """
        Convertir código de país a mercado.
        
        Args:
            country_code: Código ISO de país (ej: "US", "ES")
        
        Returns:
            str: Market ID correspondiente
        
        Mappings:
            - US, CA -> US
            - ES -> ES
            - MX -> MX
            - CL -> CL
            - Others -> default
        """
        country_market_map = {
            "US": "US",
            "CA": "US",  # Canadá usa mercado US
            "ES": "ES",
            "MX": "MX",
            "CL": "CL",
        }
        
        return country_market_map.get(country_code.upper(), self.default_market)
    
    async def _is_available_in_market(self, product_id: str, market_id: str) -> bool:
        """
        Verificar si un producto está disponible en el mercado.
        
        Args:
            product_id: ID del producto
            market_id: ID del mercado
        
        Returns:
            bool: True si disponible
        
        TODO:
            - Implementar consulta real a inventario
            - Agregar caché por producto-mercado
            - Integrar con Shopify Markets API
        """
        # En producción, esto consultaría inventario real
        return True
    
    async def _calculate_landed_cost(self, base_price: float, market_id: str) -> float:
        """
        Calcular precio final con impuestos/aranceles del mercado.
        
        Args:
            base_price: Precio base en USD
            market_id: ID del mercado
        
        Returns:
            float: Precio final localizado
        
        Process:
            1. Convertir moneda (USD -> local)
            2. Aplicar impuestos locales
            3. Redondear según convenciones locales
        
        TODO:
            - Integrar API real de conversión de moneda
            - Agregar aranceles de importación
            - Considerar costos de envío
        """
        market_config = await self.get_market_config(market_id)
        target_currency = market_config.get("currency", "USD")
        
        # Conversión de moneda (simulada)
        conversion_rates = {
            "USD_EUR": 0.85,
            "USD_MXN": 17.50,
            "USD_CLP": 930.0,
        }
        
        if target_currency == "USD":
            converted_price = base_price
        elif target_currency == "EUR":
            converted_price = base_price * conversion_rates.get("USD_EUR", 1.0)
        elif target_currency == "MXN":
            converted_price = base_price * conversion_rates.get("USD_MXN", 1.0)
        elif target_currency == "CLP":
            converted_price = base_price * conversion_rates.get("USD_CLP", 1.0)
        else:
            converted_price = base_price
        
        # Aplicar impuestos locales
        tax_rates = {
            "US": 0.0825,  # 8.25% promedio
            "ES": 0.21,    # IVA 21%
            "MX": 0.16,    # IVA 16%
            "CL": 0.19,    # IVA 19%
            "default": 0.05
        }
        
        tax_rate = tax_rates.get(market_id, tax_rates["default"])
        price_with_tax = converted_price * (1 + tax_rate)
        
        # Redondear según convenciones del mercado
        if target_currency == "EUR":
            # .95 o .99
            base = int(price_with_tax)
            decimal = price_with_tax - base
            price_with_tax = base + (0.95 if decimal >= 0.5 else -0.01)
        elif target_currency == "MXN":
            # .90 o .99
            base = int(price_with_tax)
            decimal = price_with_tax - base
            price_with_tax = base + (0.90 if decimal >= 0.5 else -0.01)
        elif target_currency == "CLP":
            # Redondear a 990
            base = int(price_with_tax / 1000) * 1000
            remainder = price_with_tax - base
            price_with_tax = base + (990 if remainder >= 500 else -10)
        
        return round(price_with_tax, 2)
    
    def _apply_market_weights(self, base_score: float, weight_config: Dict) -> float:
        """
        Aplicar pesos específicos del mercado a la puntuación.
        
        Args:
            base_score: Score base (0.0 - 1.0)
            weight_config: Configuración de pesos del mercado
        
        Returns:
            float: Score ajustado (0.0 - 1.0)
        
        Formula:
            adjusted_score = (base_score * relevance_weight) + 
                           (popularity_score * popularity_weight)
        """
        relevance_weight = weight_config.get("relevance", 0.5)
        popularity_weight = weight_config.get("popularity", 0.3)
        
        # Simular popularity score
        popularity_score = random.uniform(0.6, 0.95)
        
        adjusted_score = (base_score * relevance_weight) + \
                        (popularity_score * popularity_weight)
        
        # Normalizar entre 0 y 1
        return min(max(adjusted_score, 0.0), 1.0)
    
    async def _localize_content(self, content: str, target_language: str) -> Optional[str]:
        """
        Localizar contenido al idioma del mercado.
        
        Args:
            content: Contenido original (inglés)
            target_language: Idioma target (es, fr, de, etc.)
        
        Returns:
            Optional[str]: Contenido localizado o None si no requiere
        
        TODO:
            - Integrar servicio de traducción real (Google Translate, DeepL)
            - Agregar caché de traducciones
            - Considerar variaciones regionales (es-MX vs es-ES)
        """
        if target_language == "en":
            return None  # Sin localización necesaria
        
        # Simulación simple
        language_names = {
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch"
        }
        language_name = language_names.get(target_language, target_language.upper())
        return f"[{language_name}] {content}"