#!/usr/bin/env python3
"""
Test rápido para verificar que el intent analysis fix funciona
"""

import sys
from pathlib import Path

# Añadir root del proyecto al path
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

def test_intent_analysis_fix():
    """Test específico del análisis de intención corregido"""
    try:
        from unittest.mock import Mock, AsyncMock, patch
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        
        print("🔍 Testing intent analysis fix...")
        
        with patch('src.api.integrations.ai.optimized_conversation_manager.Anthropic') as mock_anthropic:
            # Mock Claude response
            mock_message = Mock()
            mock_message.content = [Mock(text='{"message": "Test response", "intent": {"type": "test", "confidence": 0.8}}')]
            mock_message.usage.input_tokens = 100
            mock_message.usage.output_tokens = 50
            
            mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_message)
            
            # Crear manager
            manager = OptimizedConversationAIManager(
                anthropic_api_key="test-key",
                enable_circuit_breaker=True,
                enable_caching=True
            )
            
            # Test cases del test que estaba fallando
            test_cases = [
                ("Busco un teléfono", "search"),
                ("Recomiéndame algo bueno", "recommendation"),  # Este era el que fallaba
                ("Quiero comparar estos productos", "comparison"),
                ("¿Cuánto cuesta esto?", "purchase"),
                ("Hola", "general")
            ]
            
            print("   Ejecutando test cases:")
            all_passed = True
            
            for query, expected_intent in test_cases:
                intent = manager._basic_intent_analysis(query)
                result = intent["type"] == expected_intent
                
                status = "✅" if result else "❌"
                print(f"     {status} '{query}' → Expected: {expected_intent}, Got: {intent['type']}")
                
                if not result:
                    all_passed = False
                    print(f"        Confidence: {intent['confidence']}")
                    print(f"        Attributes: {intent['attributes']}")
            
            return all_passed
            
    except Exception as e:
        print(f"❌ Error en test de intent analysis: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_keywords_improvement():
    """Test de las mejoras en keywords"""
    try:
        from unittest.mock import Mock, AsyncMock, patch
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        
        print("\n🔍 Testing keywords improvement...")
        
        with patch('src.api.integrations.ai.optimized_conversation_manager.Anthropic') as mock_anthropic:
            mock_message = Mock()
            mock_message.content = [Mock(text='{"message": "Test response"}')]
            mock_message.usage.input_tokens = 50
            mock_message.usage.output_tokens = 25
            mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_message)
            
            manager = OptimizedConversationAIManager(
                anthropic_api_key="test-key",
                enable_circuit_breaker=True,
                enable_caching=True
            )
            
            # Test casos específicos que deberían funcionar con las nuevas keywords
            advanced_test_cases = [
                ("Recomiéndame", "recommendation"),  # Debería hacer match con "recomend"
                ("Sugiéreme", "recommendation"),    # Debería hacer match con "sugier"
                ("Comparalo", "comparison"),         # Debería hacer match con "compar"
                ("Quiero comprarlo", "purchase"),   # Debería hacer match con "compra"
                ("Estoy buscando", "search"),       # Debería hacer match con "buscar"
            ]
            
            print("   Ejecutando test cases avanzados:")
            all_passed = True
            
            for query, expected_intent in advanced_test_cases:
                intent = manager._basic_intent_analysis(query)
                result = intent["type"] == expected_intent
                
                status = "✅" if result else "❌"
                print(f"     {status} '{query}' → Expected: {expected_intent}, Got: {intent['type']}")
                
                if not result:
                    all_passed = False
            
            return all_passed
            
    except Exception as e:
        print(f"❌ Error en test de keywords: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 VERIFICACIÓN DE INTENT ANALYSIS FIX")
    print("=" * 45)
    
    # Test 1: Test cases originales que estaban fallando
    test1_passed = test_intent_analysis_fix()
    
    # Test 2: Test de mejoras en keywords
    test2_passed = test_keywords_improvement()
    
    print("\n" + "=" * 45)
    print("📊 RESUMEN:")
    
    if test1_passed:
        print("✅ Test cases originales: PASS")
    else:
        print("❌ Test cases originales: FAIL")
    
    if test2_passed:
        print("✅ Keywords mejoradas: PASS")
    else:
        print("❌ Keywords mejoradas: FAIL")
    
    if test1_passed and test2_passed:
        print("\n🎉 ¡Intent analysis fix verificado!")
        print("✅ El test 'test_intent_analysis_fallback' debería pasar ahora")
        print("\n🚀 EJECUTAR:")
        print("   pytest tests/phase0_consolidation/test_optimized_conversation_manager.py::TestOptimizedConversationAIManager::test_intent_analysis_fallback -v")
    else:
        print("\n⚠️ Algunos tests fallaron")
        print("🔧 Revisar la implementación del _basic_intent_analysis")
    
    return test1_passed and test2_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
