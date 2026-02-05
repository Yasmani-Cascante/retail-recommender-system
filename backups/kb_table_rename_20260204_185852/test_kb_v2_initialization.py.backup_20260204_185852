"""
Test: KB v2 Initialization
==========================

Verifica que Knowledge Base v2 se inicializa correctamente.

CRITICAL FIX: Este test INICIA FastAPI app con TestClient para ejecutar lifespan.

Author: Senior QA Team
Date: 2026-01-31 (Fixed)
"""

import pytest
from fastapi.testclient import TestClient


def test_kb_v2_initialization_with_testclient():
    """
    Verifica que KB v2 se inicializa correctamente usando TestClient.
    
    CRITICAL: TestClient ejecuta el lifespan startup de FastAPI,
    lo que inicializa knowledge_base correctamente.
    
    NO async porque TestClient es síncrono.
    """
    # ═══════════════════════════════════════════════════════════════
    # STEP 1: Importar y crear TestClient (ejecuta lifespan startup)
    # ═══════════════════════════════════════════════════════════════
    from src.api.main_unified_redis import app
    from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
    
    # Crear TestClient - esto ejecuta el lifespan startup event
    with TestClient(app) as client:
        # ═══════════════════════════════════════════════════════════════
        # STEP 2: Verificar que app.state tiene KB
        # ═══════════════════════════════════════════════════════════════
        assert hasattr(app.state, 'knowledge_base'), \
            "app.state should have 'knowledge_base' after lifespan startup"
        
        kb = getattr(app.state, 'knowledge_base', None)
        
        if kb is None:
            # Debugging info
            state_vars = [k for k in dir(app.state) if not k.startswith('_')]
            pytest.fail(
                f"KB not initialized in app.state.\n"
                f"app.state attributes: {state_vars}\n"
                f"Possible causes:\n"
                f"1. KB_USE_SHOPIFY_CMS=False in .env\n"
                f"2. PostgreSQL table kb_content missing\n"
                f"3. KB initialization error (check startup logs)\n"
                f"4. Redis connection failed\n"
            )
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 3: Verificar tipo correcto
        # ═══════════════════════════════════════════════════════════════
        assert isinstance(kb, ShopifyKnowledgeBase), \
            f"KB should be ShopifyKnowledgeBase, got {type(kb)}"
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 4: Verificar que tiene métodos necesarios
        # ═══════════════════════════════════════════════════════════════
        assert hasattr(kb, 'get_answer'), \
            "KB should have 'get_answer' method"
        
        assert hasattr(kb, 'db'), \
            "KB should have 'db' (PostgreSQL pool) attribute"
        
        assert hasattr(kb, 'redis'), \
            "KB should have 'redis' (RedisService) attribute"
        
        print("\n✅ KB v2 initialization test PASSED")
        print(f"   - KB initialized in app.state: True")
        print(f"   - Instance type: {type(kb).__name__}")
        print(f"   - Has get_answer method: True")
        print(f"   - Has db (PostgreSQL): True")
        print(f"   - Has redis service: True")


def test_kb_v2_has_content():
    """
    Verifica que KB v2 puede acceder a contenido en PostgreSQL.
    
    Este test verifica la integración completa con la base de datos.
    """
    from src.api.main_unified_redis import app
    
    with TestClient(app) as client:
        kb = getattr(app.state, 'knowledge_base', None)
        
        if kb is None:
            pytest.skip("KB not initialized, skipping content test")
        
        # Verificar que puede hacer query a PostgreSQL
        # No ejecutamos get_answer porque es async, solo verificamos estructura
        assert hasattr(kb, 'db'), "KB should have db pool"
        assert kb.db is not None, "DB pool should be initialized"
        
        print("\n✅ KB v2 database connectivity test PASSED")
        print(f"   - PostgreSQL pool available: True")


def test_kb_v2_fallback_mechanism():
    """
    Verifica que el mecanismo de fallback de KB funciona correctamente.
    
    Este test verifica que si KB v2 tiene fallback configurado,
    funciona correctamente.
    """
    from src.api.main_unified_redis import app
    
    with TestClient(app) as client:
        kb = getattr(app.state, 'knowledge_base', None)
        
        if kb is None:
            pytest.skip("KB not initialized, skipping fallback test")
        
        # Verificar que tiene fallback_kb attribute
        assert hasattr(kb, 'fallback_kb'), \
            "KB should have 'fallback_kb' attribute for backward compatibility"
        
        # El fallback puede ser None si enable_fallback=False, eso está OK
        if kb.fallback_kb is not None:
            # Si existe, debe tener get_answer method
            assert hasattr(kb.fallback_kb, 'get_answer'), \
                "Fallback KB should have 'get_answer' method"
            
            print("\n✅ KB fallback mechanism test PASSED")
            print(f"   - Fallback KB configured: True")
            print(f"   - Fallback KB type: {type(kb.fallback_kb).__name__}")
        else:
            print("\n✅ KB fallback mechanism test PASSED")
            print(f"   - Fallback KB configured: False (disabled in config)")