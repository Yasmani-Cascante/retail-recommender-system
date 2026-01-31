"""
Test: KB Language Detection
============================

Verifica que el endpoint /v1/mcp/conversation respeta Accept-Language.

CRITICAL FIX: Usa TestClient (síncrono) con X-API-Key header.

Author: Senior QA Team  
Date: 2026-01-31 (Fixed)
"""

import pytest
from fastapi.testclient import TestClient


def test_conversation_respects_language_header():
    """
    Verifica que el endpoint respeta Accept-Language header.
    
    CRITICAL: Este test usa TestClient (síncrono), NO async_client.
    TestClient ejecuta el lifespan startup automáticamente.
    
    Verifica:
    1. Request con Accept-Language: en → Respuesta en inglés
    2. Request con Accept-Language: es → Respuesta en español
    """
    from src.api.main_unified_redis import app
    
    with TestClient(app) as client:
        # ═══════════════════════════════════════════════════════════════
        # TEST 1: English Language Request
        # ═══════════════════════════════════════════════════════════════
        
        response_en = client.post(
            "/v1/mcp/conversation",
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "X-API-Key": "2fed9999056fab6dac5654238f0cae1c"
            },
            json={
                "query": "What is your return policy?",
                "market_id": "US"
            }
        )
        
        # Verificar status code
        assert response_en.status_code == 200, \
            f"Expected 200, got {response_en.status_code}: {response_en.text}"
        
        data_en = response_en.json()
        
        # Verificar estructura básica del response
        assert "type" in data_en or "answer" in data_en or "ai_response" in data_en, \
            f"Response should have 'type', 'answer' or 'ai_response'. Got: {list(data_en.keys())}"
        
        # Obtener el texto de respuesta
        response_text = (
            data_en.get("answer", "") or 
            data_en.get("ai_response", "") or 
            str(data_en)
        ).lower()
        
        # Verificación flexible - buscar keywords en inglés
        english_keywords = ["return", "policy", "day", "days", "item", "refund"]
        spanish_keywords = ["devolución", "política", "día", "días", "artículo"]
        
        # Contar matches
        en_matches = sum(1 for word in english_keywords if word in response_text)
        es_matches = sum(1 for word in spanish_keywords if word in response_text)
        
        # Verificar que hay contenido en inglés
        assert en_matches > 0, \
            f"Response should contain English keywords. Got: {response_text[:200]}..."
        
        print(f"\n✅ English request test PASSED")
        print(f"   - Status: {response_en.status_code}")
        print(f"   - English keywords found: {en_matches}")
        print(f"   - Spanish keywords found: {es_matches}")
        
        # ═══════════════════════════════════════════════════════════════
        # TEST 2: Spanish Language Request
        # ═══════════════════════════════════════════════════════════════
        
        response_es = client.post(
            "/v1/mcp/conversation",
            headers={
                "Accept-Language": "es-ES,es;q=0.9",
                "Content-Type": "application/json",
                "X-API-Key": "2fed9999056fab6dac5654238f0cae1c"
            },
            json={
                "query": "¿Cuál es tu política de devoluciones?",
                "market_id": "ES"
            }
        )
        
        # Verificar status code
        assert response_es.status_code == 200, \
            f"Expected 200, got {response_es.status_code}: {response_es.text}"
        
        data_es = response_es.json()
        
        # Obtener el texto de respuesta
        response_text_es = (
            data_es.get("answer", "") or 
            data_es.get("ai_response", "") or 
            str(data_es)
        ).lower()
        
        # Contar matches
        en_matches_es = sum(1 for word in english_keywords if word in response_text_es)
        es_matches_es = sum(1 for word in spanish_keywords if word in response_text_es)
        
        # Verificar que hay contenido en español
        assert es_matches_es > 0, \
            f"Response should contain Spanish keywords. Got: {response_text_es[:200]}..."
        
        print(f"\n✅ Spanish request test PASSED")
        print(f"   - Status: {response_es.status_code}")
        print(f"   - Spanish keywords found: {es_matches_es}")
        print(f"   - English keywords found: {en_matches_es}")


def test_conversation_default_language():
    """
    Verifica comportamiento sin Accept-Language header.
    """
    from src.api.main_unified_redis import app
    
    with TestClient(app) as client:
        response = client.post(
            "/v1/mcp/conversation",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "2fed9999056fab6dac5654238f0cae1c"
            },
            json={
                "query": "What is your return policy?",
                "market_id": "US"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Simplemente verificar que hay respuesta válida
        assert "answer" in data or "ai_response" in data or "type" in data
        
        response_text = (
            data.get("answer", "") or 
            data.get("ai_response", "") or 
            str(data)
        )
        
        assert len(response_text) > 10, "Response should have content"
        
        print("\n✅ Default language test PASSED")
        print(f"   - Has response: True")
        print(f"   - Response length: {len(response_text)} chars")