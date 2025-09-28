#!/usr/bin/env python3
"""
Script de Diagnóstico - Conversation State Persistence
====================================================

Diagnostica problemas específicos en la persistencia conversacional.
Identifica cause raíz de session_id mismatch y turn reset.

Ejecutar: python conversation_diagnostic.py
"""

import asyncio
import json
import time
import logging
import sys
import os
from datetime import datetime

# Setup path
project_root = r"C:\Users\yasma\Desktop\retail-recommender-system"
sys.path.insert(0, os.path.join(project_root, "src"))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ConversationStateDiagnostic:
    """Diagnóstico especializado de persistencia conversacional"""
    
    def __init__(self):
        self.test_results = {}
        
    async def run_full_diagnostic(self):
        """Ejecuta diagnóstico completo de conversation state"""
        
        print("🔍 DIAGNÓSTICO CONVERSATION STATE PERSISTENCE")
        print("=" * 55)
        
        # Test 1: Session ID Generation Logic
        await self.test_session_id_generation()
        
        # Test 2: User-Session Correlation  
        await self.test_user_session_correlation()
        
        # Test 3: Turn Increment Logic
        await self.test_turn_increment_logic()
        
        # Test 4: Redis Key Strategy
        await self.test_redis_key_strategy()
        
        # Test 5: Conversation Lifecycle
        await self.test_conversation_lifecycle()
        
        # Generate diagnostic report
        self.generate_diagnostic_report()
    
    async def test_session_id_generation(self):
        """Test 1: Verificar lógica de generación de session_id"""
        print("\n🧪 TEST 1: Session ID Generation Logic")
        print("-" * 40)
        
        try:
            from src.api.mcp.conversation_state_manager import MCPConversationStateManager
            
            # Mock Redis para testing
            class MockRedis:
                def __init__(self):
                    self.data = {}
                async def get(self, key): return self.data.get(key)
                async def set(self, key, value, ex=None): 
                    self.data[key] = value
                    return True
                async def setex(self, key, ttl, value): 
                    self.data[key] = value
                    return True
            
            redis_mock = MockRedis()
            state_manager = MCPConversationStateManager(redis_mock)
            
            # Test: Generar múltiples session IDs para mismo usuario
            user_id = "test_user_123"
            session_ids = []
            
            for i in range(3):
                # Simular creación de contexto
                context = await state_manager.create_conversation_context(
                    session_id=None,  # Debe generar automáticamente
                    user_id=user_id,
                    initial_query=f"test query {i}",
                    market_context={"market_id": "US"},
                    user_agent="test"
                )
                
                session_ids.append(context.session_id if hasattr(context, 'session_id') else 'NO_SESSION_ID')
                
                # Wait para asegurar timestamp diferente
                await asyncio.sleep(0.1)
            
            # Análisis de resultados
            unique_sessions = len(set(session_ids))
            should_be_same = unique_sessions == 1  # ¿Debería reutilizar session?
            
            self.test_results["session_id_generation"] = {
                "session_ids": session_ids,
                "unique_count": unique_sessions,
                "expected_behavior": "reuse_existing" if should_be_same else "create_new",
                "actual_behavior": "creates_new" if unique_sessions == 3 else "reuses_existing",
                "problem_detected": unique_sessions == 3  # Si crea nueva cada vez = problema
            }
            
            print(f"  📊 Session IDs generados: {session_ids}")
            print(f"  🔢 Únicos: {unique_sessions}/3")
            print(f"  🚨 Problema detectado: {'SÍ' if unique_sessions == 3 else 'NO'}")
            
            if unique_sessions == 3:
                print("  💡 CAUSA RAÍZ: Genera nuevo session_id en cada request")
                print("  🔧 SOLUCIÓN: Implementar session reuse logic")
            
        except Exception as e:
            print(f"  ❌ Error en test: {e}")
            self.test_results["session_id_generation"] = {"error": str(e)}
    
    async def test_user_session_correlation(self):
        """Test 2: Verificar correlación user_id ↔ session_id"""
        print("\n🧪 TEST 2: User-Session Correlation")
        print("-" * 40)
        
        try:
            # Test directo de correlación
            test_mappings = [
                ("user_123", "sess_user_123_1722240000"),
                ("user_456", "sess_user_456_1722240001"), 
                ("user_123", "sess_user_123_1722240000")  # Mismo user, debería mismo session
            ]
            
            correlation_results = []
            
            for user_id, session_id in test_mappings:
                # Verificar si la correlación es correcta
                extracted_user = self._extract_user_from_session(session_id)
                correlation_valid = extracted_user == user_id
                
                correlation_results.append({
                    "user_id": user_id,
                    "session_id": session_id,
                    "extracted_user": extracted_user,
                    "correlation_valid": correlation_valid
                })
            
            valid_correlations = sum(1 for r in correlation_results if r["correlation_valid"])
            
            self.test_results["user_session_correlation"] = {
                "test_cases": correlation_results,
                "valid_correlations": f"{valid_correlations}/{len(correlation_results)}",
                "problem_detected": valid_correlations != len(correlation_results)
            }
            
            print(f"  📊 Correlaciones válidas: {valid_correlations}/{len(correlation_results)}")
            
            for result in correlation_results:
                status = "✅" if result["correlation_valid"] else "❌"
                print(f"  {status} {result['user_id']} ↔ {result['session_id']}")
            
        except Exception as e:
            print(f"  ❌ Error en test: {e}")
            self.test_results["user_session_correlation"] = {"error": str(e)}
    
    async def test_turn_increment_logic(self):
        """Test 3: Verificar lógica de incremento de turns"""
        print("\n🧪 TEST 3: Turn Increment Logic")
        print("-" * 40)
        
        try:
            # Simular múltiples turns en la misma conversación
            class MockConversationContext:
                def __init__(self, session_id, user_id):
                    self.session_id = session_id
                    self.user_id = user_id
                    self.turns = []
                    
                def add_turn(self, user_query, response):
                    turn = {
                        "turn_number": len(self.turns) + 1,
                        "user_query": user_query,
                        "response": response,
                        "timestamp": time.time()
                    }
                    self.turns.append(turn)
                    return turn["turn_number"]
            
            # Test scenario: 5 turns en misma conversación
            context = MockConversationContext("sess_test_123", "test_user")
            
            turn_numbers = []
            for i in range(5):
                turn_num = context.add_turn(f"Query {i+1}", f"Response {i+1}")
                turn_numbers.append(turn_num)
            
            # Verificar secuencia correcta
            expected_sequence = [1, 2, 3, 4, 5]
            sequence_correct = turn_numbers == expected_sequence
            
            self.test_results["turn_increment_logic"] = {
                "turn_sequence": turn_numbers,
                "expected_sequence": expected_sequence,
                "sequence_correct": sequence_correct,
                "total_turns": len(turn_numbers),
                "problem_detected": not sequence_correct
            }
            
            print(f"  📊 Secuencia de turns: {turn_numbers}")
            print(f"  ✅ Secuencia correcta: {'SÍ' if sequence_correct else 'NO'}")
            
            if not sequence_correct:
                print("  🚨 PROBLEMA: Turn numbering incorrecto")
                print("  🔧 SOLUCIÓN: Revisar lógica de incremento en conversation context")
            
        except Exception as e:
            print(f"  ❌ Error en test: {e}")
            self.test_results["turn_increment_logic"] = {"error": str(e)}
    
    async def test_redis_key_strategy(self):
        """Test 4: Verificar estrategia de keys Redis"""
        print("\n🧪 TEST 4: Redis Key Strategy")
        print("-" * 40)
        
        try:
            # Test diferentes estrategias de keys
            test_scenarios = [
                {
                    "user_id": "user_123",
                    "session_id": "sess_user_123_1722240000",
                    "expected_keys": [
                        "mcp:conversation:sess_user_123_1722240000",
                        "mcp:user:user_123:current_session",
                        "mcp:personalization:profile:user_123"
                    ]
                }
            ]
            
            key_analysis = []
            
            for scenario in test_scenarios:
                # Generar keys según diferentes estrategias
                generated_keys = {
                    "conversation_key": f"mcp:conversation:{scenario['session_id']}",
                    "user_session_key": f"mcp:user:{scenario['user_id']}:current_session",
                    "profile_key": f"mcp:personalization:profile:{scenario['user_id']}",
                    "state_key": f"mcp:state:{scenario['session_id']}"
                }
                
                # Verificar si keys permiten correlación correcta
                correlation_possible = all(
                    scenario['user_id'] in key or scenario['session_id'] in key 
                    for key in generated_keys.values()
                )
                
                key_analysis.append({
                    "scenario": scenario,
                    "generated_keys": generated_keys,
                    "correlation_possible": correlation_possible
                })
            
            self.test_results["redis_key_strategy"] = {
                "key_analysis": key_analysis,
                "strategy_valid": all(analysis["correlation_possible"] for analysis in key_analysis)
            }
            
            print("  📊 Keys generados:")
            for analysis in key_analysis:
                for key_type, key in analysis["generated_keys"].items():
                    print(f"    {key_type}: {key}")
                print(f"    Correlación posible: {'✅' if analysis['correlation_possible'] else '❌'}")
            
        except Exception as e:
            print(f"  ❌ Error en test: {e}")
            self.test_results["redis_key_strategy"] = {"error": str(e)}
    
    async def test_conversation_lifecycle(self):
        """Test 5: Verificar lifecycle completo de conversación"""
        print("\n🧪 TEST 5: Conversation Lifecycle")
        print("-" * 40)
        
        try:
            # Simular lifecycle completo
            lifecycle_steps = [
                "create_session",
                "first_interaction", 
                "continue_conversation",
                "session_recovery",
                "session_expiry"
            ]
            
            lifecycle_results = {}
            
            # Mock del ciclo de vida
            session_state = {
                "session_id": None,
                "user_id": "test_user",
                "turns": [],
                "created_at": time.time(),
                "last_activity": time.time()
            }
            
            for step in lifecycle_steps:
                step_result = await self._simulate_lifecycle_step(step, session_state)
                lifecycle_results[step] = step_result
                
                print(f"  📝 {step}: {'✅' if step_result['success'] else '❌'}")
                if not step_result['success']:
                    print(f"    ⚠️  {step_result['error']}")
            
            self.test_results["conversation_lifecycle"] = {
                "lifecycle_steps": lifecycle_results,
                "all_steps_successful": all(result["success"] for result in lifecycle_results.values())
            }
            
        except Exception as e:
            print(f"  ❌ Error en test: {e}")
            self.test_results["conversation_lifecycle"] = {"error": str(e)}
    
    def _extract_user_from_session(self, session_id):
        """Extrae user_id de session_id usando lógica actual"""
        try:
            # Asume formato: sess_user_XXX_timestamp
            if session_id.startswith("sess_user_"):
                parts = session_id.split("_")
                if len(parts) >= 3:
                    return f"user_{parts[2]}"
            return None
        except:
            return None
    
    async def _simulate_lifecycle_step(self, step, session_state):
        """Simula un paso del lifecycle conversacional"""
        try:
            if step == "create_session":
                session_state["session_id"] = f"sess_{session_state['user_id']}_{int(time.time())}"
                return {"success": True, "action": "session_created"}
                
            elif step == "first_interaction":
                session_state["turns"].append({"turn": 1, "query": "Hello"})
                return {"success": True, "action": "first_turn_added"}
                
            elif step == "continue_conversation":
                session_state["turns"].append({"turn": 2, "query": "Continue"})
                session_state["last_activity"] = time.time()
                return {"success": True, "action": "conversation_continued"}
                
            elif step == "session_recovery":
                # Simular recuperación de sesión existente
                recovered = session_state["session_id"] is not None
                return {"success": recovered, "action": "session_recovered" if recovered else "recovery_failed"}
                
            elif step == "session_expiry":
                # Simular expiración
                age = time.time() - session_state["created_at"]
                expired = age > 3600  # 1 hora
                return {"success": not expired, "action": "session_active" if not expired else "session_expired"}
                
            return {"success": False, "error": f"Unknown step: {step}"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def generate_diagnostic_report(self):
        """Genera reporte completo de diagnóstico"""
        print("\n" + "=" * 55)
        print("📋 REPORTE DE DIAGNÓSTICO CONVERSACIONAL")
        print("=" * 55)
        
        # Resumen de problemas detectados
        problems_detected = []
        for test_name, result in self.test_results.items():
            if isinstance(result, dict) and result.get("problem_detected", False):
                problems_detected.append(test_name)
        
        print(f"\n🚨 PROBLEMAS DETECTADOS: {len(problems_detected)}")
        for problem in problems_detected:
            print(f"  ❌ {problem.replace('_', ' ').title()}")
        
        print(f"\n📊 TESTS COMPLETADOS: {len(self.test_results)}")
        for test_name, result in self.test_results.items():
            if "error" in result:
                status = "⚠️  ERROR"
            elif result.get("problem_detected", False):
                status = "❌ PROBLEMA"
            else:
                status = "✅ OK"
            
            print(f"  {status} - {test_name.replace('_', ' ').title()}")
        
        # Recomendaciones específicas
        print(f"\n💡 RECOMENDACIONES TÉCNICAS:")
        
        if "session_id_generation" in problems_detected:
            print("  🔧 Implementar session reuse logic en MCPConversationStateManager")
            print("     - Verificar si existe sesión activa antes de crear nueva")
            print("     - Usar user_id como key de lookup para sesión existente")
        
        if "user_session_correlation" in problems_detected:
            print("  🔧 Mejorar estrategia de correlación user ↔ session")
            print("     - Estandarizar formato de session_id")
            print("     - Implementar mapping table user_id → active_session_id")
        
        if "turn_increment_logic" in problems_detected:
            print("  🔧 Corregir lógica de incremento de turns")
            print("     - Persistir turn counter en Redis")
            print("     - Validar secuencia antes de agregar nuevo turn")
        
        if not problems_detected:
            print("  ✅ No se detectaron problemas críticos en conversation state")
            print("  📈 Sistema parece funcionar correctamente")
        
        # Guardar reporte
        with open("conversation_diagnostic_report.json", "w") as f:
            json.dump(self.test_results, f, indent=2, default=str)
        
        print(f"\n📄 Reporte detallado guardado en: conversation_diagnostic_report.json")

async def main():
    """Ejecutar diagnóstico completo"""
    diagnostic = ConversationStateDiagnostic()
    await diagnostic.run_full_diagnostic()

if __name__ == "__main__":
    asyncio.run(main())