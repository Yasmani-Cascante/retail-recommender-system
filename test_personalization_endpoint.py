
# test_personalization_endpoint.py
"""
Endpoint simple para testing manual del motor de personalización
"""

import time
from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import sys
import os

# Configurar path
project_root = r"C:\Users\yasma\Desktop\retail-recommender-system"
sys.path.insert(0, os.path.join(project_root, "src"))

app = FastAPI(title="Personalization Test API")

class TestRequest(BaseModel):
    user_message: str
    user_id: str = "test_user"
    market_id: str = "US"

@app.post("/test-strategy-selection")
async def test_strategy_selection(request: TestRequest):
    """Test directo de selección de estrategia"""
    
    try:
        # Importar el motor
        from src.api.mcp.engines.mcp_personalization_engine import (
            MCPPersonalizationEngine, 
            PersonalizationStrategy
        )
        
        # Mock básico para testing
        class MockRedis:
            async def get(self, key): return None
            async def setex(self, key, ttl, value): return True
        
        class MockClaude:
            pass
            
        # Crear instancia mínima
        engine = MCPPersonalizationEngine(
            redis_client=MockRedis(),
            anthropic_client=MockClaude(),
            conversation_manager=None,
            state_manager=None
        )
        
        # Test directo de selección
        strategy = await engine._determine_optimal_strategy(
            request.user_message,
            request.market_id,
            request.user_id
        )
        
        return {
            "status": "success",
            "user_message": request.user_message,
            "selected_strategy": strategy.value,
            "available_strategies": [s.value for s in PersonalizationStrategy],
            "timestamp": time.time()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "user_message": request.user_message
        }

@app.get("/health")
async def health_check():
    """Health check básico"""
    return {"status": "healthy", "service": "personalization_test"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor de testing...")
    print("📡 Disponible en: http://localhost:8001")
    print("📝 Docs en: http://localhost:8001/docs")
    uvicorn.run(app, host="0.0.0.0", port=8001)
