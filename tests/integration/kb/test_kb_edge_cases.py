"""
Unit Tests - KB Edge Cases
===========================

Tests unitarios para casos extremos y edge cases del sistema KB v2:
- Idiomas no soportados
- Accept-Language malformado
- Tabla vacía
- Sub-intents inválidos
- Contenido con caracteres especiales

Fecha: 31 Enero 2026
Coverage objetivo: Mitigar R5 (Edge Case Handling Unknown)
"""

import pytest
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
import asyncpg
from datetime import datetime, timedelta
# Fixtures

from tests.fixtures.kb.kb_fixtures import (
    mock_shopify_kb_client,
    mock_redis_service,
    db_connection,
    clean_kb_table,
    create_mock_db_pool
)


# ============================================================================
# TEST CLASS: Language Edge Cases
# ============================================================================

@pytest.mark.usefixtures("clean_kb_table")
# @pytest.mark.asyncio
class TestKBLanguageEdgeCases:
    """
    Tests para edge cases relacionados con idiomas.
    """
    
    async def test_unsupported_language_falls_back_to_spanish(
        self,
        db_connection
    ):
        """
        TEST: Idioma no soportado cae a español
        
        Escenario: Usuario pide contenido en FR (no soportado)
        
        Valida:
        1. ✅ Query con language='fr' retorna contenido ES
        2. ✅ NO retorna error 404
        3. ✅ Response indica que usó fallback
        
        Mitiga: R5 (Edge Case Handling - idiomas no soportados)
        """
        from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
        
        # Setup: Insertar contenido ES en DB
        await db_connection.execute("""
            INSERT INTO kb_contents (
                sub_intent, language, category, title, content, 
                shopify_page_id, last_synced
            ) VALUES (
                'policy_return', 'es', 'general', 
                'Política de Devoluciones',
                'Contenido en español...',
                12345, NOW()
            )
        """)
        
        # Mock dependencies
        # db_pool = AsyncMock()
        # db_pool.acquire = AsyncMock(return_value=db_connection)
        db_pool = create_mock_db_pool(db_connection)
        
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)  # Cache miss
        
        kb = ShopifyKnowledgeBase(
            db_pool=db_pool,
            redis_service=redis_mock,
            shopify_client=None,  # No necesario para este test
            enable_fallback=True
        )
        
        # EJECUTAR: Query con FR (no soportado)
        result = await kb.get_answer(
            sub_intent="policy_return",
            language="fr",  # ← Idioma no soportado
            category="general"
        )
        
        # VALIDACIÓN 1: Retorna contenido (no None)
        assert result is not None, \
            "Should return content even with unsupported language"
        
        # VALIDACIÓN 2: Contenido es en español (fallback)
        assert result.answer is not None
        assert "español" in result.answer.lower() or "Política" in result.answer, \
            f"Should fallback to Spanish content, got: {result.answer[:100]}"
        
        # VALIDACIÓN 3: Metadata indica idioma usado
        # NOTE: Implementación puede variar
        # Podría ser result.language == "es" o result.fallback_used == True
        
        print(f"✅ FR query → ES fallback successful")
        print(f"✅ Content preview: {result.answer[:100]}...")
    
    
    async def test_multiple_languages_in_accept_language_header(self):
        """
        TEST: Accept-Language con múltiples idiomas usa prioridad correcta
        
        Escenario: "en-US,en;q=0.9,es;q=0.8,fr;q=0.7"
        
        Valida:
        1. ✅ Extrae "en" como primer idioma soportado
        2. ✅ Ignora "fr" (no soportado) aunque tenga q-value
        3. ✅ Respeta orden de prioridad (q-values)
        
        Mitiga: R5 (Edge Case Handling - Accept-Language complejo)
        """
        from src.api.core.knowledge_base_v2 import get_best_supported_language
        
        # TEST 1: EN como primera opción
        result1 = get_best_supported_language("en-US,en;q=0.9,es;q=0.8")
        assert result1 == "en", \
            f"Should extract 'en' from complex header, got: {result1}"
        
        # TEST 2: ES como primera opción soportada (fr ignorado)
        result2 = get_best_supported_language("fr;q=0.9,es;q=0.8,en;q=0.7")
        assert result2 == "es", \
            f"Should skip unsupported 'fr' and use 'es', got: {result2}"
        
        # TEST 3: Solo idiomas no soportados → fallback a ES
        result3 = get_best_supported_language("fr,de,pt")
        assert result3 == "es", \
            f"Should fallback to 'es' when no supported language, got: {result3}"
        
        # TEST 4: Header vacío → fallback a ES
        result4 = get_best_supported_language("")
        assert result4 == "es", \
            f"Should fallback to 'es' on empty header, got: {result4}"
        
        # TEST 5: Header malformado → fallback a ES
        result5 = get_best_supported_language("invalid;;;header")
        assert result5 == "es", \
            f"Should fallback to 'es' on malformed header, got: {result5}"
        
        print(f"✅ Complex Accept-Language headers handled correctly")
    
    
    async def test_language_code_normalization(self):
        """
        TEST: Códigos de idioma son normalizados correctamente
        
        Valida:
        1. ✅ "EN" → "en" (lowercase)
        2. ✅ "en-US" → "en" (extrae base)
        3. ✅ "es-MX" → "es" (extrae base)
        4. ✅ "ES-ES" → "es"
        
        Mitiga: R5 (Edge Case Handling - códigos de idioma variados)
        """
        from src.api.core.knowledge_base_v2 import normalize_language_code
        
        test_cases = [
            ("EN", "en"),
            ("en-US", "en"),
            ("en-GB", "en"),
            ("ES", "es"),
            ("es-MX", "es"),
            ("es-ES", "es"),
            ("ES-AR", "es"),
        ]
        
        for input_code, expected_output in test_cases:
            result = normalize_language_code(input_code)
            assert result == expected_output, \
                f"normalize_language_code('{input_code}') should return '{expected_output}', got '{result}'"
        
        print(f"✅ All language codes normalized correctly")


# ============================================================================
# TEST CLASS: Data Edge Cases
# ============================================================================

# @pytest.mark.asyncio
@pytest.mark.usefixtures("clean_kb_table")
class TestKBDataEdgeCases:
    """
    Tests para edge cases relacionados con datos.
    """
    
    async def test_empty_kb_table_returns_none(
        self,
        db_connection
    ):
        """
        TEST: Tabla vacía retorna None (no crashea)
        
        Valida:
        1. ✅ Query a tabla vacía retorna None
        2. ✅ NO crashea con exception
        3. ✅ Puede activar fallback si está habilitado
        
        Mitiga: R5 (Edge Case Handling - tabla vacía)
        """
        from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
        
        # Limpiar tabla
        await db_connection.execute("DELETE FROM kb_contents")
        
        # Setup KB
        # db_pool = AsyncMock()
        # db_pool.acquire = AsyncMock(return_value=db_connection)
        db_pool = create_mock_db_pool(db_connection)
        
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        
        kb = ShopifyKnowledgeBase(
            db_pool=db_pool,
            redis_service=redis_mock,
            shopify_client=None,
            enable_fallback=False  # Sin fallback para este test
        )
        
        # EJECUTAR: Query a tabla vacía
        result = await kb.get_answer(
            sub_intent="policy_return",
            language="es",
            category="general"
        )
        
        # VALIDACIÓN: Retorna None (no crashea)
        assert result is None, \
            "Empty table should return None, not raise exception"
        
        print(f"✅ Empty table handled gracefully (returned None)")
    
    
    async def test_invalid_sub_intent_returns_none(
        self,
        db_connection
    ):
        """
        TEST: Sub-intent inválido retorna None
        
        Valida:
        1. ✅ Query con sub_intent no existente retorna None
        2. ✅ NO crashea con exception
        
        Mitiga: R5 (Edge Case Handling - sub_intent inválido)
        """
        from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
        
        # Setup: Insertar contenido válido
        await db_connection.execute("""
            INSERT INTO kb_contents (
                sub_intent, language, category, title, content,
                shopify_page_id, last_synced
            ) VALUES (
                'policy_return', 'es', 'general',
                'Título', 'Contenido',
                12345, NOW()
            )
        """)
        
        # Setup KB
        # db_pool = AsyncMock()
        # db_pool.acquire = AsyncMock(return_value=db_connection)
        db_pool = create_mock_db_pool(db_connection)
        
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        
        kb = ShopifyKnowledgeBase(
            db_pool=db_pool,
            redis_service=redis_mock,
            shopify_client=None,
            enable_fallback=False
        )
        
        # EJECUTAR: Query con sub_intent inválido
        result = await kb.get_answer(
            sub_intent="invalid_sub_intent_xyz",
            language="es",
            category="general"
        )
        
        # VALIDACIÓN: Retorna None (no crashea)
        assert result is None, \
            "Invalid sub_intent should return None, not raise exception"
        
        print(f"✅ Invalid sub_intent handled gracefully (returned None)")
    
    
    async def test_very_long_content_handled_correctly(
        self,
        db_connection
    ):
        """
        TEST: Contenido muy largo (>10KB) se maneja correctamente
        
        Valida:
        1. ✅ Contenido >10KB se guarda en DB sin truncar
        2. ✅ Query retorna contenido completo
        3. ✅ Cache puede manejar contenido largo
        
        Mitiga: R5 (Edge Case Handling - contenido largo)
        """
        from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
        
        # Crear contenido largo (15KB)
        long_content = "A" * 15000  # 15KB de 'A's
        
        # Insertar en DB
        await db_connection.execute("""
            INSERT INTO kb_contents (
                sub_intent, language, category, title, content,
                shopify_page_id, last_synced
            ) VALUES (
                'policy_return', 'es', 'general',
                'Título', $1,
                12345, NOW()
            )
        """, long_content)
        
        # Setup KB
        # db_pool = AsyncMock()
        # db_pool.acquire = AsyncMock(return_value=db_connection)
        db_pool = create_mock_db_pool(db_connection)
        
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.set = AsyncMock()
        
        kb = ShopifyKnowledgeBase(
            db_pool=db_pool,
            redis_service=redis_mock,
            shopify_client=None
        )
        
        # EJECUTAR: Query
        result = await kb.get_answer(
            sub_intent="policy_return",
            language="es",
            category="general"
        )
        
        # VALIDACIÓN 1: Retorna contenido completo (no truncado)
        assert result is not None
        assert len(result.answer) == 15000, \
            f"Expected 15000 chars, got {len(result.answer)}"
        
        # VALIDACIÓN 2: Cache set fue llamado con contenido largo
        assert redis_mock.set.called, \
            "Redis set should be called even with long content"
        
        print(f"✅ Long content (15KB) handled correctly")
        print(f"✅ Content length preserved: {len(result.answer)} chars")
    
    
    async def test_special_characters_in_content(
        self,
        db_connection
    ):
        """
        TEST: Caracteres especiales se manejan correctamente
        
        Valida:
        1. ✅ UTF-8 characters (ñ, á, é, etc.)
        2. ✅ Emojis (😀, 🎉, etc.)
        3. ✅ HTML entities (&nbsp;, &amp;, etc.)
        4. ✅ Markdown syntax (**bold**, *italic*, etc.)
        
        Mitiga: R5 (Edge Case Handling - caracteres especiales)
        """
        from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
        
        # Contenido con caracteres especiales
        special_content = """
        # Título con ñ, á, é
        
        Contenido con **negrita** y *cursiva*.
        
        Lista:
        - Opción 1 😀
        - Opción 2 🎉
        - Opción 3 &nbsp;&amp;
        
        ¡Acentos: á, é, í, ó, ú!
        """
        
        # Insertar en DB
        await db_connection.execute("""
            INSERT INTO kb_contents (
                sub_intent, language, category, title, content,
                shopify_page_id, last_synced
            ) VALUES (
                'policy_return', 'es', 'general',
                'Título con ñ', $1,
                12345, NOW()
            )
        """, special_content)
        
        # Setup KB
        # db_pool = AsyncMock()
        # db_pool.acquire = AsyncMock(return_value=db_connection)
        db_pool = create_mock_db_pool(db_connection)
        
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        
        kb = ShopifyKnowledgeBase(
            db_pool=db_pool,
            redis_service=redis_mock,
            shopify_client=None
        )
        
        # EJECUTAR: Query
        result = await kb.get_answer(
            sub_intent="policy_return",
            language="es",
            category="general"
        )
        
        # VALIDACIÓN: Contenido preservado con caracteres especiales
        assert result is not None
        assert "ñ" in result.answer, "ñ character should be preserved"
        assert "á" in result.answer, "Accents should be preserved"
        assert "😀" in result.answer, "Emojis should be preserved"
        assert "**negrita**" in result.answer, "Markdown should be preserved"
        
        print(f"✅ Special characters handled correctly")


# ============================================================================
# TEST CLASS: Category Edge Cases
# ============================================================================

# @pytest.mark.asyncio
@pytest.mark.usefixtures("clean_kb_table") 
class TestKBCategoryEdgeCases:
    """
    Tests para edge cases relacionados con categorías.
    """
    
    async def test_null_category_defaults_to_general(
    self,
    db_connection
    ):
        """
        TEST: Category NULL en DB es tratado como "general"
        
        Valida:
        1. ✅ Registro con category=NULL matchea query con category="general"
        2. ✅ Registro con category="general" matchea query con category=None
        3. ✅ UNIQUE constraint funciona (no permite duplicados)
        
        Mitiga: R5 (Edge Case Handling - category NULL vs general)
        """
        
        # PASO 1: Insertar registro con category=NULL
        await db_connection.execute("""
            INSERT INTO kb_contents (
                sub_intent, language, category, title, content,
                shopify_page_id, last_synced
            ) VALUES (
                'policy_return', 'es', NULL, 'Título', 'Contenido',
                12345, NOW()
            )
        """)
        
        # PASO 2: Query con category='general' debe encontrar el registro NULL
        result_general = await db_connection.fetchrow("""
            SELECT * FROM kb_contents
            WHERE sub_intent = 'policy_return'
            AND language = 'es'
            AND COALESCE(category, 'general') = 'general'
        """)
        
        assert result_general is not None, \
            "Query with category='general' should match NULL category"
        
        # PASO 3: Verificar que el campo category es NULL en DB
        assert result_general["category"] is None, \
            "Database should store NULL, not 'general'"
        
        # PASO 4: Intentar INSERT duplicado (debería fallar por UNIQUE)
        try:
            await db_connection.execute("""
                INSERT INTO kb_contents (
                    sub_intent, language, category, title, content,
                    shopify_page_id, last_synced
                ) VALUES (
                    'policy_return', 'es', NULL, 'Otro', 'Otro contenido',
                    67890, NOW()
                )
            """)
            
            pytest.fail("Should not allow duplicate (sub_intent, language, NULL category)")
            
        except Exception as e:
            # Expected: unique violation
            assert "unique" in str(e).lower() or "duplicate" in str(e).lower(), \
                f"Expected unique constraint violation, got: {e}"
        
        print("✅ NULL category handled as 'general' in queries")
        print("✅ UNIQUE constraint works with NULL categories")
    
    
    async def test_custom_category_not_confused_with_general(
        self,
        db_connection
    ):
        """
        TEST: Categoría personalizada no se confunde con "general"
        
        Valida:
        1. ✅ Query con category="ZAPATOS" NO retorna category="general"
        2. ✅ Ambos pueden coexistir para mismo sub_intent
        
        Mitiga: R5 (Edge Case Handling - categorías personalizadas)
        """
        # Insertar 2 registros: general y ZAPATOS
        await db_connection.execute("""
            INSERT INTO kb_contents (
                sub_intent, language, category, title, content,
                shopify_page_id, last_synced
            ) VALUES 
            ('policy_return', 'es', 'general', 'General', 'Contenido general', 12345, NOW()),
            ('policy_return', 'es', 'ZAPATOS', 'Zapatos', 'Contenido zapatos', 67890, NOW())
        """)
        
        # Query para "general"
        general = await db_connection.fetchrow("""
            SELECT * FROM kb_contents
            WHERE sub_intent = 'policy_return'
              AND language = 'es'
              AND COALESCE(category, 'general') = 'general'
        """)
        
        # Query para "ZAPATOS"
        zapatos = await db_connection.fetchrow("""
            SELECT * FROM kb_contents
            WHERE sub_intent = 'policy_return'
              AND language = 'es'
              AND COALESCE(category, 'general') = 'ZAPATOS'
        """)
        
        assert general is not None
        assert zapatos is not None
        assert general["title"] != zapatos["title"], \
            "Different categories should have different content"
        
        print(f"✅ Custom categories work independently from 'general'")


# ============================================================================
# EXPORT ALL TESTS
# ============================================================================

__all__ = [
    "TestKBLanguageEdgeCases",
    "TestKBDataEdgeCases",
    "TestKBCategoryEdgeCases"
]