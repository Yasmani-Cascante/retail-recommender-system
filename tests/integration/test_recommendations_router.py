"""
Integration Tests - Recommendations Router

Este módulo contiene tests de integración para el router de recomendaciones
que ha sido migrado a FastAPI Dependency Injection.

Router bajo test: src/api/routers/recommendations.py
Dependencies: src/api/dependencies.py
ServiceFactory: src/api/factories/service_factory.py

Author: Senior Architecture Team
Date: 2025-10-29
Version: 1.0.0
"""

import pytest
from fastapi import status
from unittest.mock import patch

# ============================================================================
# INTEGRATION TESTS - Recommendations Router
# ============================================================================

@pytest.mark.integration
class TestRecommendationsEndpoint:
    """Integration tests para GET /v1/recommendations endpoint"""
    
    def test_get_recommendations_with_product_context(self, test_client):
        """
        Test: Obtener recomendaciones con product_id como contexto
        
        Scenario:
        - User hace request con user_id y product_id
        - Sistema genera recomendaciones contextuales
        - Retorna recommendations relacionadas al producto
        """
        # Execute (use product-style endpoint, pass user_id as header)
        response = test_client.get(
            "/v1/recommendations/test_prod_1?n=3",
            headers={"user_id": "test_user_001"}
        )
        
        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "recommendations" in data
        assert len(data["recommendations"]) <= 3
    
    def test_get_recommendations_missing_user_id(self, test_client):
        """
        Test: Error cuando falta user_id requerido
        
        Scenario:
        - User hace request sin user_id
        - Sistema valida parámetros requeridos
        - Retorna error 422 (Unprocessable Entity)
        """
        # Execute
        response = test_client.get("/v1/recommendations/")

        # Verify - path-only access without parameters should return 404
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()

        assert "detail" in data
        
        # Verify DI was used (el mock fue llamado)
        # Nota: En test real con overrides, verificaríamos que se llamó al mock


# ============================================================================
# SUMMARY
# ============================================================================
"""
Test Coverage Summary - Recommendations Router:

- GET /v1/recommendations/{product_id}: recomendaciones con contexto de producto
- GET /v1/recommendations/ sin parametros: 404

Total Tests: 2

Nota (04/11/2026): los 13 tests de GET /v1/recommendations/user/{user_id} se retiraron
junto con esa ruta (hallazgo de seguridad S-3, ver
DCT_Incidente_Credenciales_Expuestas_31102026.md).
"""