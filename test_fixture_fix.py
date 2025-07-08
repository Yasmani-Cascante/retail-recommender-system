#!/usr/bin/env python3
"""
Test rápido para verificar que el fixture fix funciona
"""

import sys
import os
from pathlib import Path

# Añadir root del proyecto al path
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

def test_optimized_manager_import():
    """Test básico de importación"""
    try:
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        print("✅ OptimizedConversationAIManager importado exitosamente")
        return True
    except Exception as e:
        print(f"❌ Error importando OptimizedConversationAIManager: {e}")
        return False

def test_fixture_creation():
    """Test simulación del fixture corregido"""
    try:
        from unittest.mock import Mock, AsyncMock, patch
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        
        print("🔍 Simulando fixture corregido...")
        
        with patch('src.api.integrations.ai.optimized_conversation_manager.Anthropic') as mock_anthropic:
            # Mock Claude response
            mock_message = Mock()
            mock_message.content = [Mock(text='{"message": "Test response", "intent": {"type": "test", "confidence": 0.8}}')]
            mock_message.usage.input_tokens = 100
            mock_message.usage.output_tokens = 50
            
            mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_message)
            
            # Crear manager como en el fixture
            manager = OptimizedConversationAIManager(
                anthropic_api_key="test-key",
                enable_circuit_breaker=True,
                enable_caching=True
            )
            
            # Verificar que es el objeto correcto, no un async_generator
            print(f"   Tipo de objeto: {type(manager)}")
            print(f"   Tiene enable_circuit_breaker: {hasattr(manager, 'enable_circuit_breaker')}")
            print(f"   Tiene process_conversation: {hasattr(manager, 'process_conversation')}")
            print(f"   Tiene _basic_intent_analysis: {hasattr(manager, '_basic_intent_analysis')}")
            
            # Test básico de atributos
            assert hasattr(manager, 'enable_circuit_breaker'), "Missing enable_circuit_breaker"
            assert hasattr(manager, 'process_conversation'), "Missing process_conversation"
            assert hasattr(manager, '_basic_intent_analysis'), "Missing _basic_intent_analysis"
            assert hasattr(manager, '_generate_cache_key'), "Missing _generate_cache_key"
            
            print("✅ Fixture simulation exitosa - objeto correcto creado")
            return True
            
    except Exception as e:
        print(f"❌ Error en simulación de fixture: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_context_fixture():
    """Test del fixture de contexto"""
    try:
        from src.api.integrations.ai.ai_conversation_manager import ConversationContext
        
        context = ConversationContext(
            user_id="test_user",
            session_id="test_session",
            market_id="ES",
            currency="EUR",
            conversation_history=[],
            user_profile={"preference": "electronics"},
            cart_items=[],
            browsing_history=["product1", "product2"],
            intent_signals={}
        )
        
        print(f"✅ ConversationContext creado exitosamente")
        print(f"   Tipo: {type(context)}")
        print(f"   Market ID: {context.market_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error creando ConversationContext: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 VERIFICACIÓN DE FIXTURE FIX")
    print("=" * 40)
    
    tests = [
        ("Import OptimizedConversationAIManager", test_optimized_manager_import),
        ("Fixture Simulation", test_fixture_creation),
        ("Context Fixture", test_context_fixture),
    ]
    
    all_passed = True
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}:")
        result = test_func()
        if not result:
            all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("🎉 ¡Todos los tests de verificación pasaron!")
        print("✅ Fixture fix aplicado correctamente")
        print("\n🚀 PRÓXIMO PASO:")
        print("   pytest tests/phase0_consolidation/test_optimized_conversation_manager.py -v")
    else:
        print("⚠️ Algunos tests fallaron")
        print("🔧 Revisar errores arriba")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
