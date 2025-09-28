#!/usr/bin/env python3
"""
Script de Validación Completa del Sistema MCP
==============================================

Verifica que todas las correcciones estén aplicadas y funcionando.
Identifica la fuente real de los errores reportados.
"""

import os
import sys
import asyncio
import logging
import importlib
from datetime import datetime

# Configurar logging para capturar todos los mensajes
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MCPSystemValidator:
    """Validador completo del sistema MCP"""
    
    def __init__(self):
        self.results = {}
        self.errors_found = []
        
    async def validate_all(self):
        """Ejecutar todas las validaciones"""
        print("🔍 INICIANDO VALIDACIÓN COMPLETA DEL SISTEMA MCP")
        print("=" * 60)
        
        # 1. Validar imports y sintaxis
        await self.validate_imports()
        
        # 2. Validar RedisClient.setex()
        await self.validate_redis_client()
        
        # 3. Validar ConversationStateManager
        await self.validate_conversation_state_manager()
        
        # 4. Validar llamadas en mcp_router.py
        await self.validate_mcp_router_calls()
        
        # 5. Simular endpoint call
        await self.simulate_conversation_endpoint()
        
        # 6. Generar reporte
        self.generate_report()
    
    async def validate_imports(self):
        """Validar que todos los imports funcionen"""
        print("\n🔧 VALIDANDO IMPORTS Y SINTAXIS...")
        
        try:
            # Test mcp_router import
            from src.api.routers.mcp_router import router
            self.results['mcp_router_import'] = 'SUCCESS'
            print("   ✅ mcp_router.py imports correctamente")
        except Exception as e:
            self.results['mcp_router_import'] = f'FAILED: {e}'
            self.errors_found.append(f"Import mcp_router failed: {e}")
            print(f"   ❌ mcp_router.py import failed: {e}")
        
        try:
            # Test conversation state manager import
            from src.api.routers.mcp_conversation_state_fix import get_conversation_state_manager
            self.results['state_manager_import'] = 'SUCCESS'
            print("   ✅ mcp_conversation_state_fix.py imports correctamente")
        except Exception as e:
            self.results['state_manager_import'] = f'FAILED: {e}'
            self.errors_found.append(f"Import state manager failed: {e}")
            print(f"   ❌ mcp_conversation_state_fix.py import failed: {e}")
        
        try:
            # Test redis client import
            from src.api.core.redis_client import RedisClient
            self.results['redis_client_import'] = 'SUCCESS'
            print("   ✅ redis_client.py imports correctamente")
        except Exception as e:
            self.results['redis_client_import'] = f'FAILED: {e}'
            self.errors_found.append(f"Import redis client failed: {e}")
            print(f"   ❌ redis_client.py import failed: {e}")
    
    async def validate_redis_client(self):
        """Validar que RedisClient tenga el método setex"""
        print("\n🔧 VALIDANDO REDIS CLIENT...")
        
        try:
            from src.api.core.redis_client import RedisClient
            client = RedisClient()
            
            if hasattr(client, 'setex'):
                self.results['redis_setex_method'] = 'SUCCESS'
                print("   ✅ RedisClient.setex() método presente")
            else:
                self.results['redis_setex_method'] = 'MISSING'
                self.errors_found.append("RedisClient missing setex() method")
                print("   ❌ RedisClient.setex() método FALTANTE")
                
        except Exception as e:
            self.results['redis_setex_method'] = f'ERROR: {e}'
            self.errors_found.append(f"Redis client validation failed: {e}")
            print(f"   ❌ Error validating RedisClient: {e}")
    
    async def validate_conversation_state_manager(self):
        """Validar ConversationStateManager y su método add_conversation_turn"""
        print("\n🔧 VALIDANDO CONVERSATION STATE MANAGER...")
        
        try:
            from src.api.routers.mcp_conversation_state_fix import (
                get_conversation_state_manager, 
                ConversationStateManager,
                ConversationSession
            )
            
            # Verificar método add_conversation_turn
            import inspect
            sig = inspect.signature(ConversationStateManager.add_conversation_turn)
            params = list(sig.parameters.keys())
            
            expected_params = ['self', 'session', 'user_query', 'ai_response', 'metadata']
            
            if params == expected_params:
                self.results['state_manager_signature'] = 'SUCCESS'
                print(f"   ✅ add_conversation_turn signature correcta: {params}")
            else:
                self.results['state_manager_signature'] = f'MISMATCH: {params}'
                self.errors_found.append(f"Signature mismatch: expected {expected_params}, got {params}")
                print(f"   ❌ add_conversation_turn signature incorrecta: {params}")
            
            # Test crear instancia
            state_manager = get_conversation_state_manager()
            if state_manager:
                self.results['state_manager_instance'] = 'SUCCESS'
                print("   ✅ get_conversation_state_manager() funciona")
            else:
                self.results['state_manager_instance'] = 'FAILED'
                self.errors_found.append("get_conversation_state_manager returned None")
                print("   ❌ get_conversation_state_manager() retorna None")
                
        except Exception as e:
            self.results['state_manager_validation'] = f'ERROR: {e}'
            self.errors_found.append(f"State manager validation failed: {e}")
            print(f"   ❌ Error validating state manager: {e}")
    
    async def validate_mcp_router_calls(self):
        """Validar que las llamadas en mcp_router.py estén corregidas"""
        print("\n🔧 VALIDANDO MCP ROUTER CALLS...")
        
        try:
            # Leer el archivo y buscar patrones problemáticos
            file_path = "src/api/routers/mcp_router.py"
            
            if not os.path.exists(file_path):
                self.results['mcp_router_file'] = 'FILE_NOT_FOUND'
                print(f"   ❌ Archivo {file_path} no encontrado")
                return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Buscar patrones problemáticos
            problem_patterns = [
                'session=conversation_session',
                'user_query=conversation.query', 
                'ai_response=final_ai_response'
            ]
            
            problems_found = []
            for pattern in problem_patterns:
                if pattern in content:
                    problems_found.append(pattern)
            
            if problems_found:
                self.results['mcp_router_patterns'] = f'PROBLEMS_FOUND: {problems_found}'
                self.errors_found.extend([f"Found problematic pattern: {p}" for p in problems_found])
                print(f"   ❌ Patrones problemáticos encontrados: {problems_found}")
            else:
                self.results['mcp_router_patterns'] = 'SUCCESS'
                print("   ✅ No se encontraron patrones problemáticos")
            
            # Buscar la llamada corregida
            if 'updated_session = await state_manager.add_conversation_turn(' in content:
                # Extraer la llamada específica
                lines = content.split('\n')
                call_found = False
                for i, line in enumerate(lines):
                    if 'updated_session = await state_manager.add_conversation_turn(' in line:
                        # Capturar las siguientes líneas de la llamada
                        call_lines = []
                        j = i
                        paren_count = 0
                        while j < len(lines):
                            call_lines.append(lines[j].strip())
                            paren_count += lines[j].count('(') - lines[j].count(')')
                            j += 1
                            if paren_count == 0 and ')' in lines[j-1]:
                                break
                        
                        call_text = ' '.join(call_lines)
                        if 'conversation_session,' in call_text and 'conversation.query,' in call_text:
                            call_found = True
                            break
                
                if call_found:
                    self.results['mcp_router_corrected_call'] = 'SUCCESS'
                    print("   ✅ Llamada corregida encontrada")
                else:
                    self.results['mcp_router_corrected_call'] = 'NOT_FOUND'
                    self.errors_found.append("Corrected call not found")
                    print("   ❌ Llamada corregida NO encontrada")
            else:
                self.results['mcp_router_corrected_call'] = 'MISSING'
                print("   ❌ Llamada add_conversation_turn no encontrada")
                
        except Exception as e:
            self.results['mcp_router_validation'] = f'ERROR: {e}'
            self.errors_found.append(f"MCP router validation failed: {e}")
            print(f"   ❌ Error validating mcp_router: {e}")
    
    async def simulate_conversation_endpoint(self):
        """Simular una llamada al endpoint para capturar errores reales"""
        print("\n🔧 SIMULANDO ENDPOINT CALL...")
        
        try:
            # Simular request data
            class MockConversationRequest:
                def __init__(self):
                    self.query = "test query"
                    self.user_id = "test_user"
                    self.session_id = None
                    self.market_id = "US" 
                    self.language = "en"
                    self.product_id = None
                    self.n_recommendations = 5
            
            # Intentar importar y usar componentes
            from src.api.routers.mcp_conversation_state_fix import get_conversation_state_manager
            
            state_manager = get_conversation_state_manager()
            if not state_manager:
                self.results['endpoint_simulation'] = 'STATE_MANAGER_NONE'
                print("   ❌ state_manager es None")
                return
            
            # Simular get_or_create_session
            mock_request = MockConversationRequest()
            session = await state_manager.get_or_create_session(
                session_id=None,
                user_id="test_user",
                market_id="US"
            )
            
            # Verificar tipo de session
            if hasattr(session, 'session_id') and hasattr(session, 'turn_count'):
                self.results['session_object_type'] = 'SUCCESS'
                print(f"   ✅ Session object tipo correcto: {type(session)}")
                
                # Simular add_conversation_turn
                try:
                    updated_session = await state_manager.add_conversation_turn(
                        session,  # Positional arg 1
                        "test query",  # Positional arg 2
                        "test response",  # Positional arg 3
                        metadata={"test": True}  # Keyword arg
                    )
                    
                    self.results['add_conversation_turn_call'] = 'SUCCESS'
                    print(f"   ✅ add_conversation_turn call exitosa, turn: {updated_session.turn_count}")
                    
                except Exception as call_error:
                    self.results['add_conversation_turn_call'] = f'FAILED: {call_error}'
                    self.errors_found.append(f"add_conversation_turn call failed: {call_error}")
                    print(f"   ❌ add_conversation_turn call falló: {call_error}")
                    
            else:
                self.results['session_object_type'] = f'INVALID: {type(session)}'
                self.errors_found.append(f"Session object invalid type: {type(session)}")
                print(f"   ❌ Session object tipo incorrecto: {type(session)}")
                
        except Exception as e:
            self.results['endpoint_simulation'] = f'ERROR: {e}'
            self.errors_found.append(f"Endpoint simulation failed: {e}")
            print(f"   ❌ Error en simulación de endpoint: {e}")
    
    def generate_report(self):
        """Generar reporte final"""
        print("\n" + "=" * 60)
        print("📊 REPORTE FINAL DE VALIDACIÓN")
        print("=" * 60)
        
        success_count = sum(1 for result in self.results.values() if result == 'SUCCESS')
        total_count = len(self.results)
        
        print(f"\n✅ TESTS EXITOSOS: {success_count}/{total_count}")
        print(f"❌ ERRORS ENCONTRADOS: {len(self.errors_found)}")
        
        if self.errors_found:
            print("\n🚨 ERRORES DETALLADOS:")
            for i, error in enumerate(self.errors_found, 1):
                print(f"   {i}. {error}")
        
        print("\n📋 RESULTADOS DETALLADOS:")
        for test_name, result in self.results.items():
            status = "✅" if result == "SUCCESS" else "❌"
            print(f"   {status} {test_name}: {result}")
        
        # Recomendaciones
        print("\n🎯 RECOMENDACIONES:")
        if not self.errors_found:
            print("   ✅ SISTEMA VALIDADO - No se encontraron problemas")
            print("   🔍 Los errores reportados pueden ser de una sesión anterior")
            print("   📝 Ejecutar tests reales para confirmar")
        else:
            print("   🔧 Aplicar correcciones específicas identificadas")
            print("   🔄 Re-ejecutar validación después de correcciones")
        
        # Guardar reporte
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "success_count": success_count,
            "total_count": total_count,
            "results": self.results,
            "errors": self.errors_found
        }
        
        with open("mcp_validation_report.json", "w") as f:
            import json
            json.dump(report_data, f, indent=2)
        
        print(f"\n📄 Reporte guardado en: mcp_validation_report.json")

async def main():
    """Función principal"""
    validator = MCPSystemValidator()
    await validator.validate_all()

if __name__ == "__main__":
    asyncio.run(main())