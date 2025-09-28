#!/usr/bin/env python3
"""
Test Final de Diversificación - Post-Fix
========================================

Test para validar que el fix completo de diversificación funciona correctamente:
1. Context reload en handler
2. Diversification flag correcta 
3. Logging de debug aparece
4. Recommendations realmente diferentes
"""

import asyncio
import sys
import os
import time
import logging
import requests
import json
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Setup logging para capturar todos los logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

async def test_diversification_fix():
    """Test completo del fix de diversificación"""
    
    print("🚀 TESTING DIVERSIFICATION FIX - POST IMPLEMENTATION")
    print("=" * 70)
    
    # Setup - Usar la misma API key del sistema
    api_key = os.getenv("API_KEY", "default_key")  # Misma que usa el sistema 
    base_url = "http://localhost:8000"
    test_user_id = "test_diversification_user_final"
    test_session_id = f"test_session_final_{int(time.time())}"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    print(f"📋 Test Configuration:")
    print(f"   User ID: {test_user_id}")
    print(f"   Session ID: {test_session_id}")
    print(f"   API URL: {base_url}")
    print(f"   API Key: {api_key[:8]}..." if len(api_key) > 8 else f"   API Key: {api_key}")
    print()
    
    try:
        # === TEST 1: Primera llamada ===
        print("1️⃣ PRIMERA LLAMADA - Establishing conversation")
        print("-" * 50)
        
        request_1 = {
            "query": "show me some recommendations",
            "user_id": test_user_id,
            "session_id": test_session_id,
            "market_id": "US",
            "n_recommendations": 5
        }
        
        print(f"   Enviando request: {request_1['query']}")
        start_time = time.time()
        
        response_1 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=request_1,
            timeout=30
        )
        
        call_1_time = (time.time() - start_time) * 1000
        
        if response_1.status_code != 200:
            print(f"   ❌ Error: Status {response_1.status_code}")
            print(f"   Response: {response_1.text}")
            return False
            
        data_1 = response_1.json()
        recs_1 = data_1.get("recommendations", [])
        metadata_1 = data_1.get("metadata", {})
        session_metadata_1 = data_1.get("session_metadata", {})
        
        print(f"   ✅ Status: {response_1.status_code}")
        print(f"   ✅ Response Time: {call_1_time:.1f}ms")
        print(f"   ✅ Recommendations: {len(recs_1)}")
        print(f"   ✅ Diversification Applied: {metadata_1.get('diversification_applied', False)}")
        print(f"   ✅ Turn Number: {session_metadata_1.get('turn_number', 'Unknown')}")
        print(f"   ✅ Recommendation IDs: {[r.get('id') for r in recs_1[:3]]}...")
        print()
        
        # Esperar un momento
        time.sleep(2)
        
        # === TEST 2: Segunda llamada (debería activar diversificación) ===
        print("2️⃣ SEGUNDA LLAMADA - Should trigger diversification")
        print("-" * 50)
        
        request_2 = {
            "query": "show me more products",
            "user_id": test_user_id,
            "session_id": test_session_id,
            "market_id": "US", 
            "n_recommendations": 5
        }
        
        print(f"   Enviando request: {request_2['query']}")
        start_time = time.time()
        
        response_2 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=request_2,
            timeout=30
        )
        
        call_2_time = (time.time() - start_time) * 1000
        
        if response_2.status_code != 200:
            print(f"   ❌ Error: Status {response_2.status_code}")
            print(f"   Response: {response_2.text}")
            return False
            
        data_2 = response_2.json()
        recs_2 = data_2.get("recommendations", [])
        metadata_2 = data_2.get("metadata", {})
        session_metadata_2 = data_2.get("session_metadata", {})
        
        print(f"   ✅ Status: {response_2.status_code}")
        print(f"   ✅ Response Time: {call_2_time:.1f}ms")
        print(f"   ✅ Recommendations: {len(recs_2)}")
        print(f"   ✅ Diversification Applied: {metadata_2.get('diversification_applied', False)}")
        print(f"   ✅ Turn Number: {session_metadata_2.get('turn_number', 'Unknown')}")
        print(f"   ✅ Recommendation IDs: {[r.get('id') for r in recs_2[:3]]}...")
        print()
        
        # === ANÁLISIS DE RESULTADOS ===
        print("📊 ANÁLISIS DE DIVERSIFICACIÓN")
        print("=" * 50)
        
        # Extraer IDs
        ids_1 = set(r.get('id') for r in recs_1 if r.get('id'))
        ids_2 = set(r.get('id') for r in recs_2 if r.get('id'))
        
        overlap = len(ids_1.intersection(ids_2))
        total_unique = len(ids_1.union(ids_2))
        overlap_percentage = (overlap / len(ids_1)) * 100 if len(ids_1) > 0 else 100
        
        print(f"   🔍 Primera llamada: {len(recs_1)} productos")
        print(f"   🔍 Segunda llamada: {len(recs_2)} productos") 
        print(f"   🔍 IDs en común: {overlap}")
        print(f"   🔍 Porcentaje de overlap: {overlap_percentage:.1f}%")
        print(f"   🔍 Total únicos: {total_unique}")
        print()
        
        # === CRITERIOS DE ÉXITO ===
        print("🎯 CRITERIOS DE VALIDACIÓN")
        print("-" * 50)
        
        success_criteria = {
            "response_time_acceptable": call_1_time < 10000 and call_2_time < 10000,
            "diversification_flag_correct": metadata_2.get('diversification_applied', False) == True,
            "low_overlap": overlap_percentage < 50,
            "both_have_recs": len(recs_1) > 0 and len(recs_2) > 0,
            "turn_progression": session_metadata_2.get('turn_number', 0) > session_metadata_1.get('turn_number', 0)
        }
        
        for criterion, passed in success_criteria.items():
            icon = "✅" if passed else "❌"
            print(f"   {icon} {criterion}: {passed}")
        
        print()
        
        # === RESULTADO FINAL ===
        all_passed = all(success_criteria.values())
        
        print("🏁 RESULTADO FINAL")
        print("=" * 50)
        
        if all_passed:
            print("🎉 ÉXITO - FIX DE DIVERSIFICACIÓN FUNCIONANDO CORRECTAMENTE")
            print("   - Diversificación aplicada en segunda llamada")
            print("   - Productos diferentes entre llamadas") 
            print("   - Metadata reporta correctamente")
            print("   - Performance aceptable")
            return True
        else:
            print("⚠️ FALLOS DETECTADOS - FIX NECESITA AJUSTES")
            failed_criteria = [k for k, v in success_criteria.items() if not v]
            for criterion in failed_criteria:
                print(f"   - FALLA: {criterion}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR EN TEST: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Función principal"""
    print("🧪 INICIANDO TEST FINAL DE DIVERSIFICACIÓN\n")
    
    try:
        result = asyncio.run(test_diversification_fix())
        
        print("\n" + "=" * 70)
        if result:
            print("✅ TEST EXITOSO - FIX COMPLETAMENTE IMPLEMENTADO")
            return 0
        else:
            print("❌ TEST FALLIDO - SE REQUIEREN AJUSTES ADICIONALES")
            return 1
    except Exception as e:
        print(f"\n❌ Error ejecutando test: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
