#!/usr/bin/env python3
"""
DEEP DIAGNOSTIC - Response Structure Analysis
============================================

Diagnóstico profundo para identificar exactamente qué está devolviendo
el endpoint optimizado vs qué está buscando el script de validación.
"""

import requests
import json
import time
from datetime import datetime

# Configuración
BASE_URL = "http://localhost:8000"
API_KEY = "2fed9999056fab6dac5654238f0cae1c"

class ResponseStructureDiagnostic:
    """Diagnostica la estructura de respuesta del endpoint optimizado"""
    
    def __init__(self):
        self.headers = {
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def analyze_endpoint_response(self):
        """Analiza la estructura completa de respuesta del endpoint optimizado"""
        
        print("🔍 DEEP DIAGNOSTIC - ANALYZING ENDPOINT RESPONSE STRUCTURE")
        print("=" * 70)
        
        # Test payload similar al usado por validate_phase2_complete.py
        payload = {
            "query": "I need running shoes for marathon training",
            "user_id": "diagnostic_user_123",
            "session_id": "diagnostic_session_456", 
            "market_id": "US",
            "n_recommendations": 5,
            "enable_optimization": True
        }
        
        print(f"📤 REQUEST PAYLOAD:")
        print(json.dumps(payload, indent=2))
        print()
        
        try:
            # Llamada al endpoint optimizado
            print("🔄 Calling /v1/mcp/conversation/optimized...")
            start_time = time.perf_counter()
            
            response = self.session.post(
                f"{BASE_URL}/v1/mcp/conversation/optimized",
                json=payload,
                timeout=30
            )
            
            end_time = time.perf_counter()
            response_time_ms = (end_time - start_time) * 1000
            
            print(f"⏱️ Response time: {response_time_ms:.1f}ms")
            print(f"📊 Status code: {response.status_code}")
            print()
            
            if response.status_code == 200:
                response_data = response.json()
                
                print("📥 COMPLETE RESPONSE STRUCTURE:")
                print("=" * 50)
                print(json.dumps(response_data, indent=2, default=str))
                print()
                
                # Análisis específico de campos
                self.analyze_specific_fields(response_data)
                
                # Segunda llamada para verificar persistencia
                print("\n🔄 TESTING STATE PERSISTENCE...")
                self.test_state_persistence(payload)
                
            else:
                print(f"❌ Error response: {response.status_code}")
                print(f"📝 Response text: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    def analyze_specific_fields(self, response_data):
        """Analiza campos específicos que busca el script de validación"""
        
        print("🔍 FIELD-BY-FIELD ANALYSIS:")
        print("=" * 30)
        
        # Campos que busca validate_phase2_complete.py
        expected_fields = [
            'session_tracking',
            'session_id', 
            'turn_number',
            'intent_evolution',
            'intents_tracked',
            'intent_progression',
            'conversation_state',
            'state_persistence'
        ]
        
        print("📋 LOOKING FOR VALIDATION SCRIPT FIELDS:")
        for field in expected_fields:
            found_paths = self.find_field_in_response(response_data, field)
            if found_paths:
                print(f"   ✅ '{field}' found at: {found_paths}")
            else:
                print(f"   ❌ '{field}' NOT FOUND")
        
        print("\n📋 ACTUAL TOP-LEVEL FIELDS IN RESPONSE:")
        for key in response_data.keys():
            value_type = type(response_data[key]).__name__
            if isinstance(response_data[key], dict):
                sub_keys = list(response_data[key].keys())
                print(f"   📁 '{key}' ({value_type}): {sub_keys}")
            elif isinstance(response_data[key], list):
                list_length = len(response_data[key])
                print(f"   📝 '{key}' ({value_type}): {list_length} items")
            else:
                print(f"   📄 '{key}' ({value_type}): {response_data[key]}")
    
    def find_field_in_response(self, data, field_name, current_path=""):
        """Encuentra un campo específico en cualquier nivel de la respuesta"""
        found_paths = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{current_path}.{key}" if current_path else key
                
                if key == field_name:
                    found_paths.append(new_path)
                
                # Buscar recursivamente
                sub_paths = self.find_field_in_response(value, field_name, new_path)
                found_paths.extend(sub_paths)
        
        elif isinstance(data, list):
            for i, item in enumerate(data):
                new_path = f"{current_path}[{i}]"
                sub_paths = self.find_field_in_response(item, field_name, new_path)
                found_paths.extend(sub_paths)
        
        return found_paths
    
    def test_state_persistence(self, original_payload):
        """Prueba la persistencia del estado con una segunda llamada"""
        
        # Segunda llamada con el mismo session_id
        second_payload = original_payload.copy()
        second_payload["query"] = "Show me more options in a different color"
        
        print(f"📤 SECOND REQUEST (same session_id):")
        print(f"   Session ID: {second_payload['session_id']}")
        print(f"   New query: {second_payload['query']}")
        print()
        
        try:
            response = self.session.post(
                f"{BASE_URL}/v1/mcp/conversation/optimized",
                json=second_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                
                print("📥 SECOND RESPONSE - KEY FIELDS:")
                
                # Buscar evidencia de persistencia
                session_info = self.extract_session_info(response_data)
                intent_info = self.extract_intent_info(response_data)
                
                print(f"📊 Session Info: {session_info}")
                print(f"🎯 Intent Info: {intent_info}")
                
                # Verificar si turn_number incrementó
                if session_info and 'turn_number' in session_info:
                    turn_num = session_info['turn_number']
                    if turn_num > 1:
                        print(f"✅ PERSISTENCE WORKING: Turn number = {turn_num}")
                    else:
                        print(f"❌ PERSISTENCE ISSUE: Turn number = {turn_num}")
                else:
                    print("❌ NO TURN NUMBER FOUND in response")
                
            else:
                print(f"❌ Second call failed: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Exception in persistence test: {e}")
    
    def extract_session_info(self, response_data):
        """Extrae información de sesión de la respuesta"""
        possible_paths = [
            ['session_tracking'],
            ['conversation_state'],
            ['session_details'],
            ['state_persistence'],
            ['session_info']
        ]
        
        for path in possible_paths:
            current_data = response_data
            for key in path:
                if isinstance(current_data, dict) and key in current_data:
                    current_data = current_data[key]
                else:
                    current_data = None
                    break
            
            if current_data:
                return current_data
        
        return None
    
    def extract_intent_info(self, response_data):
        """Extrae información de intents de la respuesta"""
        possible_paths = [
            ['intent_evolution'],
            ['intent_tracking'],
            ['conversation_state', 'intents'],
            ['session_tracking', 'intents']
        ]
        
        for path in possible_paths:
            current_data = response_data
            for key in path:
                if isinstance(current_data, dict) and key in current_data:
                    current_data = current_data[key]
                else:
                    current_data = None
                    break
            
            if current_data:
                return current_data
        
        return None
    
    def generate_fix_recommendations(self):
        """Genera recomendaciones específicas para el fix"""
        
        print("\n" + "=" * 70)
        print("💡 FIX RECOMMENDATIONS")
        print("=" * 70)
        
        print("Basado en el análisis, el problema probablemente es:")
        print("1. 📝 Campo naming mismatch entre endpoint y validation script")
        print("2. 🔍 Validation script busca campos en paths incorrectos")
        print("3. 🔄 Estado se genera pero en formato no reconocido por validator")
        print()
        print("📋 Próximos pasos:")
        print("1. Revisar output de este diagnóstico")
        print("2. Comparar con campos que busca validate_phase2_complete.py")
        print("3. Crear mapping correcto entre response y validation expectations")

def main():
    """Función principal de diagnóstico"""
    
    print("🚀 INICIANDO DIAGNÓSTICO PROFUNDO")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("Objetivo: Identificar mismatch entre endpoint response y validation script")
    print()
    
    diagnostic = ResponseStructureDiagnostic()
    diagnostic.analyze_endpoint_response()
    diagnostic.generate_fix_recommendations()
    
    print("\n🎯 DIAGNÓSTICO COMPLETADO")
    print("Revisa el output para identificar el problema exacto.")

if __name__ == "__main__":
    main()
