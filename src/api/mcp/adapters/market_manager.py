# src/api/mcp/adapters/market_manager.py
from typing import Dict, Optional, List, Any
import asyncio
from src.api.core.cache import get_redis_client
import json
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)

class MarketContextManager:
    """Gestiona contexto específico por mercado"""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.market_configs = {}
        
    async def initialize(self):
        """Inicializar gestor de mercados"""
        logger.info("Inicializando gestor de mercados")
        
        # Cargar configuraciones de mercados soportados
        self.market_configs = await self.get_supported_markets()
        
        logger.info(f"Gestor de mercados inicializado con {len(self.market_configs)} mercados")
        return True
        
    async def detect_market(self, request_context: Dict) -> str:
        """Detectar mercado basado en contexto de request"""
        # Priority order: explicit > geolocation > user preference > default
        
        if request_context.get('market_id'):
            return request_context['market_id']
            
        if geo_country := request_context.get('country_code'):
            return self._country_to_market(geo_country)
            
        if user_id := request_context.get('user_id'):
            cached_preference = await self.redis.get(f"user_market:{user_id}")
            if cached_preference:
                return cached_preference
                
        return "default"
    
    async def get_market_config(self, market_id: str) -> Dict:
        """Obtener configuración específica del mercado"""
        cache_key = f"market_config:{market_id}"
        
        # Check cache first
        cached = await self.redis.get(cache_key)
        if cached:
            return cached  # RedisCache ya deserializa automáticamente
            
        # Load from configuration files or fall back to supported markets
        try:
            config_path = f"config/markets/{market_id}/config.json"
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Cache for 1 hour
            await self.redis.set(cache_key, config, expiration=3600)
            return config
            
        except FileNotFoundError:
            # Fallback to supported markets
            supported_markets = await self.get_supported_markets()
            if market_id in supported_markets:
                return supported_markets[market_id]
            
            # Fallback to default
            return supported_markets.get("default", {})
    
    async def get_supported_markets(self) -> Dict[str, Dict]:
        """Obtener lista de mercados soportados"""
        cache_key = "supported_markets"
        
        # Check cache first
        cached = await self.redis.get(cache_key)
        if cached:
            return cached  # RedisCache ya deserializa automáticamente
        
        # Definición de mercados soportados (simplificada para este ejemplo)
        # En producción, esto podría cargarse de una base de datos o archivo de configuración
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
        await self.redis.set(cache_key, markets, expiration=86400)
        return markets
    
    async def adapt_recommendations_for_market(self, recommendations: List[Dict], 
                                               market_id: str) -> List[Dict]:
        """Adaptar recomendaciones para mercado específico"""
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
        """Convertir código de país a mercado"""
        # Mapeo simplificado de país a mercado
        country_market_map = {
            "US": "US",
            "CA": "US",  # Canadá usa mercado US
            "ES": "ES",
            "MX": "MX",
            "CL": "CL",
            # Agregar más mapeos según sea necesario
        }
        
        return country_market_map.get(country_code.upper(), "default")
    
    async def _is_available_in_market(self, product_id: str, market_id: str) -> bool:
        """Verificar si un producto está disponible en el mercado"""
        # En producción, esto consultaría un servicio de inventario o base de datos
        # Para este ejemplo, asumimos disponibilidad
        return True
    
    async def _calculate_landed_cost(self, base_price: float, market_id: str) -> float:
        """Calcular precio final con impuestos/aranceles del mercado"""
        # Obtener configuración de mercado
        market_config = await self.get_market_config(market_id)
        
        # Obtener moneda del mercado
        target_currency = market_config.get("currency", "USD")
        
        # Simular conversión de moneda (en producción usaría una API real)
        conversion_rates = {
            "USD_EUR": 0.85,
            "USD_MXN": 17.50,
            "USD_CLP": 930.0,
            "EUR_USD": 1.18,
            "EUR_MXN": 20.65,
            "EUR_CLP": 1094.0,
            "MXN_USD": 0.057,
            "MXN_EUR": 0.048,
            "MXN_CLP": 53.0,
            "CLP_USD": 0.00108,
            "CLP_EUR": 0.00091,
            "CLP_MXN": 0.019
        }
        
        # Convertir precio base a la moneda del mercado
        # Asumimos que el precio base está en USD para simplificar
        if target_currency == "USD":
            converted_price = base_price
        elif target_currency == "EUR":
            converted_price = base_price * conversion_rates["USD_EUR"]
        elif target_currency == "MXN":
            converted_price = base_price * conversion_rates["USD_MXN"]
        elif target_currency == "CLP":
            converted_price = base_price * conversion_rates["USD_CLP"]
        else:
            converted_price = base_price
        
        # Aplicar impuestos locales (simplificado)
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
            # Redondear a .95 o .99
            base = int(price_with_tax)
            decimal = price_with_tax - base
            if decimal < 0.5:
                price_with_tax = base - 0.01  # .99
            else:
                price_with_tax = base + 0.95  # .95
        elif target_currency == "MXN":
            # Redondear a .90 o .99
            base = int(price_with_tax)
            decimal = price_with_tax - base
            if decimal < 0.5:
                price_with_tax = base - 0.01  # .99
            else:
                price_with_tax = base + 0.90  # .90
        elif target_currency == "CLP":
            # Redondear a 990 o 990 (precios psicológicos en Chile)
            base = int(price_with_tax / 1000) * 1000
            remainder = price_with_tax - base
            if remainder < 500:
                price_with_tax = base - 10  # 990
            else:
                price_with_tax = base + 990  # 990
        
        return round(price_with_tax, 2)
    
    def _apply_market_weights(self, base_score: float, weight_config: Dict) -> float:
        """Aplicar pesos específicos del mercado a la puntuación"""
        # Por simplicidad, ajustamos ligeramente el score base
        # En producción, esto aplicaría una fórmula más compleja
        relevance_weight = weight_config.get("relevance", 0.5)
        popularity_weight = weight_config.get("popularity", 0.3)
        
        # Asumimos que el score base está relacionado con la relevancia
        # y agregamos un componente aleatorio para simular popularidad
        popularity_score = random.uniform(0.6, 0.95)  # Valor aleatorio para ejemplo
        
        adjusted_score = (base_score * relevance_weight) + (popularity_score * popularity_weight)
        
        # Normalizar entre 0 y 1
        return min(max(adjusted_score, 0.0), 1.0)
    
    async def _localize_content(self, content: str, target_language: str) -> Optional[str]:
        """Simular localización de contenido"""
        # En producción, esto usaría un servicio de traducción o base de datos
        # Para este ejemplo, agregamos un prefijo simple
        if target_language != "en":
            language_names = {
                "es": "Español",
                "fr": "Français",
                "de": "Deutsch"
            }
            language_name = language_names.get(target_language, target_language.upper())
            return f"[{language_name}] {content}"
        return None  # Sin localización necesaria
