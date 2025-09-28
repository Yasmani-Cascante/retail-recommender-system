#!/usr/bin/env python3
"""
Adaptador para MCPPersonalizationEngine que añade un método get_recommendations()
compatible con la interfaz esperada por mcp_router.py
"""

from pathlib import Path

def create_mcp_adapter():
    """
    Crea un adaptador/wrapper para MCPPersonalizationEngine
    """
    
    project_root = Path(__file__).parent
    adapter_file = project_root / 'src' / 'api' / 'mcp' / 'engines' / 'mcp_adapter.py'
    
    # Asegurar que el directorio existe
    adapter_file.parent.mkdir(parents=True, exist_ok=True)
    
    adapter_code = '''"""
MCP Adapter - Compatibility Layer
=================================

Adaptador que proporciona una interfaz compatible para MCPPersonalizationEngine
permitiendo que el mcp_router.py funcione sin cambios mientras usamos la
arquitectura avanzada de personalización.

Author: Senior Architecture Team
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .mcp_personalization_engine import MCPPersonalizationEngine, PersonalizationStrategy
from src.api.mcp.conversation_state_manager import MCPConversationContext
from src.api.mcp.models.mcp_models import MarketConfig

logger = logging.getLogger(__name__)

class MCPRecommenderAdapter:
    """
    Adaptador que proporciona la interfaz get_recommendations() esperada
    por el código existente, mientras usa MCPPersonalizationEngine internamente.
    """
    
    def __init__(self, personalization_engine: MCPPersonalizationEngine):
        self.engine = personalization_engine
        logger.info("✅ MCPRecommenderAdapter initialized")
    
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5,
        market_id: str = "US",
        session_id: Optional[str] = None,
        conversation_context: Optional[Dict] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Interfaz compatible con el código existente que internamente usa
        generate_personalized_response() del MCPPersonalizationEngine.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: Número de recomendaciones
            market_id: ID del mercado
            session_id: ID de sesión (opcional)
            conversation_context: Contexto conversacional
            **kwargs: Parámetros adicionales
            
        Returns:
            Lista de recomendaciones en formato compatible
        """
        try:
            logger.info(f"🔄 Adapter processing recommendations for user {user_id}")
            
            # 1. Crear MCP Context desde parámetros
            mcp_context = self._build_mcp_context(
                user_id=user_id,
                product_id=product_id,
                market_id=market_id,
                session_id=session_id,
                conversation_context=conversation_context
            )
            
            # 2. Obtener recomendaciones base (esto debería venir del HybridRecommender)
            base_recommendations = await self._get_base_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
            )
            
            # 3. Usar MCPPersonalizationEngine para personalización avanzada
            personalized_result = await self.engine.generate_personalized_response(
                mcp_context=mcp_context,
                recommendations=base_recommendations,
                strategy=None  # Auto-detección de estrategia
            )
            
            # 4. Convertir resultado a formato esperado por router
            compatible_recommendations = self._convert_to_compatible_format(
                personalized_result
            )
            
            logger.info(f"✅ Adapter returned {len(compatible_recommendations)} personalized recommendations")
            return compatible_recommendations
            
        except Exception as e:
            logger.error(f"❌ Adapter error: {e}")
            # Fallback: devolver recomendaciones básicas
            return await self._get_fallback_recommendations(user_id, n_recommendations)
    
    def _build_mcp_context(
        self,
        user_id: str,
        product_id: Optional[str],
        market_id: str,
        session_id: Optional[str],
        conversation_context: Optional[Dict]
    ) -> MCPConversationContext:
        """Construye MCPConversationContext desde parámetros del router"""
        
        # Extraer mensaje del contexto conversacional
        user_message = ""
        if conversation_context:
            user_message = conversation_context.get('query', '') or conversation_context.get('message', '')
        
        # Crear contexto MCP
        context = MCPConversationContext(
            user_id=user_id,
            session_id=session_id or f"session_{user_id}_{int(time.time())}",
            market_id=market_id,
            user_message=user_message,
            product_context=product_id,
            conversation_stage="recommendation_request",
            intent_type="product_discovery",
            metadata=conversation_context or {}
        )
        
        return context
    
    async def _get_base_recommendations(
        self,
        user_id: str,
        product_id: Optional[str],
        n_recommendations: int
    ) -> List[Dict]:
        """Obtiene recomendaciones base del HybridRecommender"""
        
        try:
            # Importar HybridRecommender (lazy import para evitar circular imports)
            from src.api.main_unified_redis import hybrid_recommender
            
            if hybrid_recommender:
                if product_id:
                    # Recomendaciones basadas en producto
                    base_recs = await hybrid_recommender.get_recommendations(
                        product_id, n_recommendations
                    )
                else:
                    # Recomendaciones personalizadas por usuario
                    base_recs = await hybrid_recommender.get_user_recommendations(
                        user_id, n_recommendations
                    )
                
                return base_recs
            else:
                logger.warning("⚠️ HybridRecommender not available, using mock recommendations")
                return self._create_mock_recommendations(n_recommendations)
                
        except Exception as e:
            logger.error(f"❌ Error getting base recommendations: {e}")
            return self._create_mock_recommendations(n_recommendations)
    
    def _convert_to_compatible_format(
        self,
        personalized_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Convierte resultado de MCPPersonalizationEngine a formato esperado por router"""
        
        try:
            # Extraer recomendaciones personalizadas
            personalized_recs = personalized_result.get("personalized_recommendations", [])
            
            # Convertir cada recomendación al formato esperado
            compatible_recs = []
            for rec in personalized_recs:
                compatible_rec = {
                    "id": rec.get("id", "unknown"),
                    "title": rec.get("title", "Product"),
                    "price": rec.get("price", 0),
                    "currency": rec.get("currency", "USD"),
                    "score": rec.get("score", 0.5),
                    "reason": rec.get("reason", "Recommended for you"),
                    
                    # Metadatos adicionales de personalización
                    "personalization_score": rec.get("personalization_score", 0.0),
                    "cultural_adaptation": rec.get("cultural_adaptation", {}),
                    "market_optimization": rec.get("market_optimization", {}),
                    
                    # Mantener estructura original si existe
                    **rec
                }
                compatible_recs.append(compatible_rec)
            
            return compatible_recs
            
        except Exception as e:
            logger.error(f"❌ Error converting format: {e}")
            return []
    
    async def _get_fallback_recommendations(
        self,
        user_id: str,
        n_recommendations: int
    ) -> List[Dict[str, Any]]:
        """Recomendaciones de fallback en caso de error"""
        
        return self._create_mock_recommendations(n_recommendations)
    
    def _create_mock_recommendations(self, n_recommendations: int) -> List[Dict[str, Any]]:
        """Crea recomendaciones mock para testing/fallback"""
        
        mock_products = [
            {"id": f"mock_{i}", "title": f"Product {i}", "price": 10.0 * i, "currency": "USD", "score": 0.5}
            for i in range(1, n_recommendations + 1)
        ]
        
        return mock_products

# Función helper para crear el adapter
async def create_mcp_recommender_adapter(personalization_engine: MCPPersonalizationEngine):
    """
    Crea una instancia del adapter para usar en ServiceFactory
    """
    return MCPRecommenderAdapter(personalization_engine)
'''

    # Escribir el archivo
    with open(adapter_file, 'w', encoding='utf-8') as f:
        f.write(adapter_code)
    
    print(f"✅ Adaptador creado en: {adapter_file}")
    return adapter_file

if __name__ == "__main__":
    adapter_file = create_mcp_adapter()
    print(f"\n📋 PRÓXIMOS PASOS:")
    print("1. Modificar ServiceFactory.get_mcp_recommender() para usar el adaptador")
    print("2. Importar MCPRecommenderAdapter en lugar de MCPPersonalizationEngine directamente")
    print("3. Probar el endpoint /conversation")
