# src/api/mcp/adapters/market_manager.py
from typing import Dict, Optional
import asyncio
from src.api.core.cache import get_redis_client
import json
import logging
from typing import Dict, Optional, List, Any

class MarketContextManager:
    """Gestiona contexto específico por mercado"""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.market_configs = {}
        
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
            return json.loads(cached)
            
        # Load from configuration files
        config_path = f"config/markets/{market_id}/config.json"
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Cache for 1 hour
            await self.redis.setex(cache_key, 3600, json.dumps(config))
            return config
            
        except FileNotFoundError:
            # Fallback to default
            return await self.get_market_config("default")
    
    async def adapt_recommendations_for_market(self, recommendations: List[Dict], 
                                               market_id: str) -> List[Dict]:
        """Adaptar recomendaciones para mercado específico"""
        market_config = await self.get_market_config(market_id)
        
        adapted = []
        for rec in recommendations:
            # Validate availability in market
            if not await self._is_available_in_market(rec['id'], market_id):
                continue
                
            # Calculate landed costs
            rec['market_price'] = await self._calculate_landed_cost(
                rec['base_price'], market_id
            )
            
            # Apply market-specific scoring weights
            rec['market_score'] = self._apply_market_weights(
                rec['score'], market_config.get('scoring_weights', {})
            )
            
            # Localize content
            rec['localized_title'] = await self._localize_content(
                rec['title'], market_config.get('language', 'en')
            )
            
            adapted.append(rec)
            
        # Sort by market-adjusted score
        adapted.sort(key=lambda x: x['market_score'], reverse=True)
        return adapted