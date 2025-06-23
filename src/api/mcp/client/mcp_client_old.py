# src/api/mcp/client/mcp_client.py
import asyncio
import httpx
from typing import Dict, List, Optional
from anthropic import Anthropic

class ShopifyMCPClient:
    """Cliente MCP para integración con Shopify Markets Pro"""
    
    def __init__(self, store_domain: str, api_version: str = "2025-04"):
        self.store_domain = store_domain
        self.api_version = api_version
        self.anthropic = Anthropic()  # Para conversation processing
        self.session = httpx.AsyncClient()
        
    async def initialize(self):
        """Inicializar conexión y validar capabilities"""
        try:
            # Verificar conectividad MCP
            response = await self.session.get(
                f"https://{self.store_domain}/admin/api/{self.api_version}/markets.json",
                headers=self._get_headers()
            )
            response.raise_for_status()
            
            # Cargar configuraciones de mercado
            self.markets = await self._load_market_configurations()
            
            return True
        except Exception as e:
            logger.error(f"MCP initialization failed: {e}")
            return False
    
    async def get_market_products(self, market_id: str, 
                                  include_availability: bool = True,
                                  include_landed_costs: bool = True) -> List[Dict]:
        """Obtener productos específicos para un mercado"""
        endpoint = f"/admin/api/{self.api_version}/markets/{market_id}/products.json"
        
        params = {
            'include_availability': include_availability,
            'include_landed_costs': include_landed_costs,
            'limit': 250
        }
        
        products = []
        url = f"https://{self.store_domain}{endpoint}"
        
        while url:
            response = await self.session.get(url, params=params, headers=self._get_headers())
            data = response.json()
            
            products.extend(data.get('products', []))
            url = self._extract_next_page_url(response)
            
        return products
    
    async def process_conversation_intent(self, conversation: str, 
                                          market_context: Dict) -> Dict:
        """Procesar intención conversacional usando Anthropic"""
        prompt = f"""
        Analiza esta conversación de e-commerce y extrae la intención:
        
        Conversación: "{conversation}"
        Mercado: {market_context.get('market_id')}
        Moneda: {market_context.get('currency')}
        
        Extrae:
        1. Intención principal (search, recommend, compare, etc.)
        2. Categoría de producto si se menciona
        3. Presupuesto si se indica
        4. Preferencias específicas
        5. Urgencia temporal
        
        Responde en JSON formato:
        """
        
        response = await self.anthropic.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response y structure intent
        return self._parse_intent_response(response.content[0].text)