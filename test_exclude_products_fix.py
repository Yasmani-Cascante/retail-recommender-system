#!/usr/bin/env python3
"""
Test de Verificación - Fix exclude_products
==========================================

Test para verificar que el fix del parámetro exclude_products funciona correctamente
"""

import requests
import json
import time
import sys
import os
from dotenv import load_dotenv

load_dotenv()

def test_exclude_products_fix():
    """Test específico del parámetro exclude_products"""
    
    print("🔧 TESTING exclude_products FIX")
    print("=" * 50)
    
    api_key = os.getenv("API_KEY", "default_key")
    base_url = "http://localhost:8000"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    test_session_id = f"exclude_products_test_{int(time.time())}"
    
    try:
        # Primera llamada - establecer contexto
        print("1️⃣ Primera llamada - Estableciendo contexto...")
        
        request_1 = {
            "query": "show me recommendations",
            "user_id": "test_exclude_products",
            "session_id": test_session_id,
            "market_id": "US",
            "n_recommendations": 5
        }
        
        response_1 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=request_1,
            timeout=20
        )
        
        if response_1.status_code != 200:
            print(f"   ❌ Error primera llamada: {response_1.status_code}")
            return False
            
        data_1 = response_1.json()
        recs_1 = data_1.get("recommendations", [])
        metadata_1 = data_1.get("metadata", {})
        
        print(f"   ✅ Recommendations: {len(recs_1)}")
        print(f"   ✅ Diversification Applied: {metadata_1.get('diversification_applied', False)}")
        
        # Esperar
        time.sleep(2)
        
        # Segunda llamada - debería activar diversificación SIN error
        print("\n2️⃣ Segunda llamada - Debería activar diversificación...")
        
        request_2 = {
            "query": "show me more different products",
            "user_id": "test_exclude_products", 
            "session_id": test_session_id,
            "market_id": "US",
            "n_recommendations": 5
        }
        
        response_2 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=request_2,
            timeout=20
        )
        
        if response_2.status_code != 200:
            print(f"   ❌ Error segunda llamada: {response_2.status_code}")
            return False
            
        data_2 = response_2.json()
        recs_2 = data_2.get("recommendations", [])
        metadata_2 = data_2.get("metadata", {})
        
        print(f"   ✅ Status: {response_2.status_code}")
        print(f"   ✅ Recommendations: {len(recs_2)}")
        print(f"   ✅ Diversification Applied: {metadata_2.get('diversification_applied', False)}")
        
        # Análisis de éxito
        print(f"\n📊 RESULTADOS:")
        
        ids_1 = set(r.get('id') for r in recs_1 if r.get('id'))
        ids_2 = set(r.get('id') for r in recs_2 if r.get('id'))
        overlap = len(ids_1.intersection(ids_2))
        overlap_pct = (overlap / len(ids_1)) * 100 if len(ids_1) > 0 else 0
        
        print(f"   Primera llamada: {len(recs_1)} productos")
        print(f"   Segunda llamada: {len(recs_2)} productos")
        print(f"   Overlap: {overlap_pct:.1f}%")
        print(f"   Diversification flag: {metadata_2.get('diversification_applied', False)}")
        
        # Criterios de éxito
        success = (
            len(recs_1) > 0 and
            len(recs_2) > 0 and
            metadata_2.get('diversification_applied', False) == True and
            overlap_pct < 50  # Menos del 50% de overlap
        )
        
        print(f"\n🎯 RESULTADO:")
        if success:
            print("   ✅ FIX EXITOSO - exclude_products funciona correctamente")
            print("   - No hay errores de parámetro desconocido") 
            print("   - Diversificación se aplica correctamente")
            print("   - Productos son realmente diferentes")
        else:
            print("   ❌ FIX REQUIERE AJUSTES")
            if not metadata_2.get('diversification_applied', False):
                print("     - Diversification flag incorrecto")
            if overlap_pct >= 50:
                print(f"     - Overlap muy alto: {overlap_pct:.1f}%")
        
        return success
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

if __name__ == "__main__":
    result = test_exclude_products_fix()
    print(f"\nResultado final: {'✅ ÉXITO' if result else '❌ FALLA'}")
