#!/usr/bin/env python3
"""
Test de Verificación - Implementación de Diversificación
=======================================================

Test para verificar que la implementación de diversificación funciona correctamente
y resuelve el problema de UX donde "show me more" devuelve recomendaciones diferentes.
"""

import asyncio
import sys
import time
import json
sys.path.append('src')

# Cargar variables de entorno
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

async def test_diversification_implementation():
    print("🧪 TESTING DIVERSIFICATION IMPLEMENTATION...")
    print("=" * 60)
    
    try:
        # Importar componentes
        from src.api.core.mcp_conversation_handler import get_mcp_conversation_recommendations
        
        # Datos de prueba
        test_user_id = "test_user_diversification"
        test_market_id = "US"
        test_session_id = f"test_session_{int(time.time())}"
        
        print(f"📋 Test User: {test_user_id}")
        print(f"📋 Test Session: {test_session_id}")
        print(f"📋 Market: {test_market_id}")
        print()
        
        # === TEST 1: Primera llamada ===
        print("1️⃣ PRIMERA LLAMADA - 'show me some recommendations'")
        print("-" * 50)
        
        start_time = time.time()
        result1 = await get_mcp_conversation_recommendations(
            validated_user_id=test_user_id,
            validated_product_id=None,
            conversation_query="show me some recommendations",
            market_id=test_market_id,
            n_recommendations=5,
            session_id=test_session_id
        )
        call1_time = (time.time() - start_time) * 1000
        
        # Extraer información de la primera llamada
        recs1 = result1.get("recommendations", [])
        recs1_ids = [rec.get('id') for rec in recs1 if rec.get('id')]
        metadata1 = result1.get("metadata", {})
        
        print(f"   ✅ Response Time: {call1_time:.1f}ms")
        print(f"   ✅ Recommendations Count: {len(recs1)}")
        print(f"   ✅ Cache Hit: {metadata1.get('cache_hit', False)}")
        print(f"   ✅ Diversification Applied: {metadata1.get('diversification_applied', False)}")
        print(f"   ✅ Recommendation IDs: {recs1_ids[:3]}...")
        print()
        
        # Esperar un momento para simular tiempo real
        await asyncio.sleep(2)
        
        # === TEST 2: Segunda llamada ===
        print("2️⃣ SEGUNDA LLAMADA - 'show me more'")
        print("-" * 50)
        
        start_time = time.time()
        result2 = await get_mcp_conversation_recommendations(
            validated_user_id=test_user_id,
            validated_product_id=None,
            conversation_query="show me more",
            market_id=test_market_id,
            n_recommendations=5,
            session_id=test_session_id
        )
        call2_time = (time.time() - start_time) * 1000
        
        # Extraer información de la segunda llamada
        recs2 = result2.get("recommendations", [])
        recs2_ids = [rec.get('id') for rec in recs2 if rec.get('id')]
        metadata2 = result2.get("metadata", {})
        
        print(f"   ✅ Response Time: {call2_time:.1f}ms")
        print(f"   ✅ Recommendations Count: {len(recs2)}")
        print(f"   ✅ Cache Hit: {metadata2.get('cache_hit', False)}")
        print(f"   ✅ Diversification Applied: {metadata2.get('diversification_applied', False)}")
        print(f"   ✅ Recommendation IDs: {recs2_ids[:3]}...")
        print()
        
        # === ANÁLISIS DE RESULTADOS ===
        print("📊 ANÁLISIS DE DIVERSIFICACIÓN")
        print("-" * 50)
        
        # Calcular overlap entre recomendaciones
        set1 = set(recs1_ids)
        set2 = set(recs2_ids)
        intersection = set1.intersection(set2)
        overlap_count = len(intersection)
        overlap_percentage = (overlap_count / max(len(set1), len(set2))) * 100 if max(len(set1), len(set2)) > 0 else 0
        
        print(f"   🔍 Recomendaciones 1: {len(set1)} productos")
        print(f"   🔍 Recomendaciones 2: {len(set2)} productos")
        print(f"   🔍 Productos en común: {overlap_count}")
        print(f"   🔍 Porcentaje de overlap: {overlap_percentage:.1f}%")
        print()
        
        # === VERIFICACIÓN DE ÉXITO ===
        print("🎯 VERIFICACIÓN DE ÉXITO")
        print("-" * 50)
        
        success_criteria = []
        
        # Criterio 1: Performance
        perf_ok = call1_time < 3000 and call2_time < 2000
        success_criteria.append(("Performance aceptable", perf_ok, f"Call1: {call1_time:.0f}ms, Call2: {call2_time:.0f}ms"))
        
        # Criterio 2: Diversificación aplicada en segunda llamada
        div_applied = metadata2.get('diversification_applied', False)
        success_criteria.append(("Diversificación aplicada en call 2", div_applied, f"Applied: {div_applied}"))
        
        # Criterio 3: Overlap menor al 50%
        low_overlap = overlap_percentage < 50
        success_criteria.append(("Bajo overlap entre recomendaciones", low_overlap, f"Overlap: {overlap_percentage:.1f}%"))
        
        # Criterio 4: Ambas llamadas devolvieron recomendaciones
        both_have_recs = len(recs1) > 0 and len(recs2) > 0
        success_criteria.append(("Ambas llamadas con recomendaciones", both_have_recs, f"Recs1: {len(recs1)}, Recs2: {len(recs2)}"))
        
        # Mostrar resultados
        all_success = True
        for criterion, passed, details in success_criteria:
            status = "✅" if passed else "❌"
            print(f"   {status} {criterion}: {details}")
            if not passed:
                all_success = False
        
        print()
        
        # === CONCLUSIÓN ===
        if all_success:
            print("🎉 IMPLEMENTACIÓN EXITOSA")
            print("   La diversificación está funcionando correctamente.")
            print("   Las queries 'show me more' ahora devuelven productos diferentes.")
        else:
            print("⚠️ IMPLEMENTACIÓN NECESITA AJUSTES")
            print("   Algunos criterios no se cumplieron.")
            print("   Revisar logs para diagnosticar problemas.")
        
        return all_success
        
    except Exception as e:
        print(f"💥 Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(test_diversification_implementation())
        print(f"\n" + "="*60)
        if result:
            print("✅ DIVERSIFICATION IMPLEMENTATION WORKING CORRECTLY")
            print("Ready for production testing!")
        else:
            print("❌ Diversification implementation has issues")
    except Exception as e:
        print(f"💥 Test script failed: {e}")
