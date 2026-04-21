# tests/e2e/test_user_journey_conversational_with_intent.py

"""
E2E Test: Conversational Flow con Intent Detection
Valida que sistema responde correctamente a queries informacionales.
"""

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_mixed_intent_conversation(
    test_client_with_warmup: AsyncClient,
    mock_auth
):
    """
    Escenario: Usuario alterna entre queries transaccionales e informacionales.
    
    CRÍTICO: Sistema debe responder apropiadamente a cada tipo.
    """
    
    # ═══════════════════════════════════════════════════════════
    # TURN 1: TRANSACTIONAL - Buscar vestidos
    # ═══════════════════════════════════════════════════════════
    
    response = await test_client_with_warmup.post(
        "/v1/mcp/conversation",
        json={
            "query": "busco vestidos elegantes para boda",
            "user_id": "test_user_123",
            "market_id": "US"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Debe retornar PRODUCTOS
    assert data['type'] == 'transactional'
    assert len(data['recommendations']) > 0
    assert 'vestido' in data['recommendations'][0]['title'].lower()
    
    session_id = data['session_id']
    
    # ═══════════════════════════════════════════════════════════
    # TURN 2: INFORMATIONAL - Política de devolución
    # ═══════════════════════════════════════════════════════════
    
    response = await test_client_with_warmup.post(
        "/v1/mcp/conversation",
        json={
            "query": "¿cuál es la política de devolución?",
            "user_id": "test_user_123",
            "session_id": session_id,
            "market_id": "US"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # ✅ Debe retornar INFO, NO productos
    assert data['type'] == 'informational'
    assert len(data['recommendations']) == 0  # Sin productos
    assert 'devolución' in data['answer'].lower() or '30 días' in data['answer']
    
    # ═══════════════════════════════════════════════════════════
    # TURN 3: TRANSACTIONAL - Mostrar vestido específico
    # ═══════════════════════════════════════════════════════════
    
    response = await test_client_with_warmup.post(
        "/v1/mcp/conversation",
        json={
            "query": "muéstrame el vestido más caro",
            "user_id": "test_user_123",
            "session_id": session_id,
            "market_id": "US"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Debe retornar PRODUCTOS otra vez
    assert data['type'] == 'transactional'
    assert len(data['recommendations']) > 0
    
    # ═══════════════════════════════════════════════════════════
    # TURN 4: INFORMATIONAL - Info de envío
    # ═══════════════════════════════════════════════════════════
    
    response = await test_client_with_warmup.post(
        "/v1/mcp/conversation",
        json={
            "query": "¿cuánto cuesta el envío?",
            "user_id": "test_user_123",
            "session_id": session_id,
            "market_id": "US"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # ✅ Debe retornar INFO, NO productos
    assert data['type'] == 'informational'
    assert len(data['recommendations']) == 0
    assert 'envío' in data['answer'].lower() or 'gratis' in data['answer'].lower()
    
    print(f"""
    ✅ TEST PASSED: Mixed Intent Conversation
    
    Turn 1 (TRANS): Productos ✅
    Turn 2 (INFO):  Sin productos, solo respuesta ✅
    Turn 3 (TRANS): Productos ✅
    Turn 4 (INFO):  Sin productos, solo respuesta ✅
    
    Conversación fluida lograda! 🎉
    """)