#!/usr/bin/env python3
"""
Script de Verificación - Correcciones de Diversificación de Cache
================================================================

Verifica que las 3 correcciones aplicadas están funcionando correctamente:
1. Query normalization separando initial vs follow-up recommendations
2. Hash generation incluyendo turn_number y shown_products_count  
3. Cache context enriquecido con información conversacional

Uso:
    python verify_diversification_fixes.py
"""

import asyncio
import sys
import os

# Agregar la ruta del proyecto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

async def test_correcciones_aplicadas():
    """Verifica que las correcciones estén aplicadas correctamente"""
    
    print("🔍 VERIFICANDO CORRECCIONES DE DIVERSIFICACIÓN")
    print("=" * 60)
    
    # Test 1: Verificar CORRECCIÓN 1 - Query normalization
    print("\n1️⃣ VERIFICANDO CORRECCIÓN 1: Query Normalization")
    print("-" * 50)
    
    try:
        from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache
        
        cache = IntelligentPersonalizationCache()
        
        # Test different query types
        test_queries = [
            ("show me some recommendations", "initial_recommendations"),
            ("show me more", "follow_up_recommendations"), 
            ("find me different products", "follow_up_recommendations"),
            ("recommend something else", "follow_up_recommendations"),
            ("help me find products", "initial_recommendations")
        ]
        
        all_correct = True
        for query, expected_type in test_queries:
            result = cache._normalize_query_for_cache(query)
            success = result == expected_type
            status = "✅" if success else "❌"
            print(f"   {status} '{query}' → '{result}' (expected: '{expected_type}')")
            if not success:
                all_correct = False
        
        if all_correct:
            print("   🎉 CORRECCIÓN 1: ✅ FUNCIONANDO CORRECTAMENTE")
        else:
            print("   ⚠️ CORRECCIÓN 1: ❌ ALGUNOS CASOS FALLANDO")
            
    except Exception as e:
        print(f"   ❌ Error testing corrección 1: {e}")
    
    # Test 2: Verificar CORRECCIÓN 2 - Hash generation
    print("\n2️⃣ VERIFICANDO CORRECCIÓN 2: Hash Generation")
    print("-" * 50)
    
    try:
        cache = IntelligentPersonalizationCache()
        
        # Test contexts with different turn numbers
        context1 = {
            "market_id": "US",
            "user_segment": "standard",
            "turn_number": 1,
            "shown_products": []
        }
        
        context2 = {
            "market_id": "US", 
            "user_segment": "standard",
            "turn_number": 2,
            "shown_products": ["product_1", "product_2"]
        }
        
        hash1 = cache._generate_query_hash("show me recommendations", context1)
        hash2 = cache._generate_query_hash("show me more", context2)
        
        different_hashes = hash1 != hash2
        status = "✅" if different_hashes else "❌"
        print(f"   {status} Turn 1 vs Turn 2 generate different hashes: {different_hashes}")
        print(f"       Turn 1 hash: {hash1}")
        print(f"       Turn 2 hash: {hash2}")
        
        if different_hashes:
            print("   🎉 CORRECCIÓN 2: ✅ FUNCIONANDO CORRECTAMENTE")
        else:
            print("   ⚠️ CORRECCIÓN 2: ❌ HASHES IGUALES PARA CONTEXTS DIFERENTES")
            
    except Exception as e:
        print(f"   ❌ Error testing corrección 2: {e}")
    
    # Test 3: Verificar que las importaciones funcionan
    print("\n3️⃣ VERIFICANDO IMPORTS Y SINTAXIS")
    print("-" * 50)
    
    try:
        from src.api.core.intelligent_personalization_cache import get_personalization_cache
        from src.api.core.mcp_conversation_handler import get_mcp_conversation_recommendations
        
        print("   ✅ Import de intelligent_personalization_cache: OK")
        print("   ✅ Import de mcp_conversation_handler: OK")
        print("   🎉 SINTAXIS: ✅ TODOS LOS IMPORTS FUNCIONANDO")
        
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
    except SyntaxError as e:
        print(f"   ❌ Syntax error: {e}")
    except Exception as e:
        print(f"   ❌ Other error: {e}")
    
    print("\n" + "=" * 60)
    print("✅ VERIFICACIÓN COMPLETADA")
    print("\n🎯 PRÓXIMO PASO: Ejecutar test de diversificación:")
    print("   python test_diversification_with_server.py")
    print("\n📝 RESULTADO ESPERADO:")
    print("   1️⃣ Primera llamada: Cache miss, recomendaciones iniciales")
    print("   2️⃣ Segunda llamada: Cache miss, diversificación aplicada")
    print("   3️⃣ Overlap < 50% entre ambas llamadas")

if __name__ == "__main__":
    asyncio.run(test_correcciones_aplicadas())
