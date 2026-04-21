"""
Test Simplificado: Intent Detection Logic Only
===============================================

Este test verifica SOLO la lógica de Intent Detection
sin inicializar el sistema completo (Redis, HybridRecommender, etc.)
"""

import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.core.intent_detection import detect_intent
from src.api.core.intent_types import IntentType, InformationalSubIntent
from src.api.core.knowledge_base import get_answer
from src.api.core.config import get_settings


async def test_intent_detection_logic():
    """Test Intent Detection logic in isolation"""
    
    print("="*80)
    print("INTENT DETECTION LOGIC TEST - ISOLATED")
    print("="*80)
    print()
    
    # Check configuration
    settings = get_settings()
    print(f"🔧 Configuration:")
    print(f"   Intent Detection Enabled: {settings.enable_intent_detection}")
    print(f"   Confidence Threshold: {settings.intent_confidence_threshold}")
    print()
    print("="*80)
    print()
    
    test_cases = [
        {
            "name": "Test 1: Policy Return Query",
            "query": "¿cuál es la política de devolución?",
            "expected_intent": IntentType.INFORMATIONAL,
            "expected_action": "RETURN_KB_ANSWER"
        },
        {
            "name": "Test 2: Shipping Query",
            "query": "cómo funciona el envío",
            "expected_intent": IntentType.INFORMATIONAL,
            "expected_action": "RETURN_KB_ANSWER"
        },
        {
            "name": "Test 3: Payment Query",
            "query": "qué métodos de pago aceptan",
            "expected_intent": IntentType.INFORMATIONAL,
            "expected_action": "RETURN_KB_ANSWER"
        },
        {
            "name": "Test 4: Product Search Query",
            "query": "busco vestidos elegantes",
            "expected_intent": IntentType.TRANSACTIONAL,
            "expected_action": "CONTINUE_TO_PRODUCTS"
        },
        {
            "name": "Test 5: Product Search Query 2",
            "query": "necesito zapatos formales",
            "expected_intent": IntentType.TRANSACTIONAL,
            "expected_action": "CONTINUE_TO_PRODUCTS"
        },
        {
            "name": "Test 6: Purchase Intent Query",
            "query": "quiero comprar este vestido",
            "expected_intent": IntentType.TRANSACTIONAL,
            "expected_action": "CONTINUE_TO_PRODUCTS"
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        print(f"{test_case['name']}")
        print("-" * 60)
        print(f"Query: '{test_case['query']}'")
        
        try:
            # Step 1: Detect Intent
            intent_result = detect_intent(test_case['query'])
            
            print(f"\n✓ Detected Intent: {intent_result.primary_intent}")
            print(f"✓ Sub-Intent: {intent_result.sub_intent}")
            print(f"✓ Confidence: {intent_result.confidence:.2f}")
            print(f"✓ Reasoning: {intent_result.reasoning}")
            
            # Step 2: Check threshold
            meets_threshold = intent_result.confidence >= settings.intent_confidence_threshold
            print(f"\n✓ Meets Threshold ({settings.intent_confidence_threshold}): {meets_threshold}")
            
            # Step 3: Determine action
            if meets_threshold and intent_result.primary_intent == IntentType.INFORMATIONAL:
                action = "RETURN_KB_ANSWER"
                
                # Step 4: Get KB Answer (if informational)
                kb_answer = get_answer(
                    sub_intent=InformationalSubIntent(intent_result.sub_intent),
                    product_context=intent_result.product_context,
                    query=test_case['query']
                )
                
                if kb_answer:
                    print(f"✓ Action: {action}")
                    print(f"\n📚 KB Answer Preview:")
                    print(f"   {kb_answer.answer[:100]}...")
                    print(f"   Sources: {kb_answer.sources}")
                else:
                    action = "CONTINUE_TO_PRODUCTS (KB answer not found)"
                    print(f"⚠️  Action: {action}")
            
            elif meets_threshold and intent_result.primary_intent == IntentType.TRANSACTIONAL:
                action = "CONTINUE_TO_PRODUCTS"
                print(f"✓ Action: {action}")
            
            else:
                action = "CONTINUE_TO_PRODUCTS (below threshold)"
                print(f"✓ Action: {action}")
            
            # Validation
            intent_match = intent_result.primary_intent == test_case['expected_intent']
            action_match = action.startswith(test_case['expected_action'])
            
            if intent_match and action_match:
                print(f"\n✅ PASS")
                results.append({'test': test_case['name'], 'status': 'PASS'})
            else:
                print(f"\n❌ FAIL")
                if not intent_match:
                    print(f"   Expected Intent: {test_case['expected_intent']}, Got: {intent_result.primary_intent}")
                if not action_match:
                    print(f"   Expected Action: {test_case['expected_action']}, Got: {action}")
                results.append({'test': test_case['name'], 'status': 'FAIL'})
        
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append({'test': test_case['name'], 'status': 'ERROR'})
        
        print()
        print("="*80)
        print()
    
    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print()
    
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    
    print(f"Total: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Errors: {errors}")
    print()
    
    if passed == len(results):
        print("🎉 ALL TESTS PASSED!")
        print()
        print("✅ Intent Detection is working correctly!")
        print("✅ Knowledge Base integration is working!")
        print("✅ Logic flow is correct!")
        print()
        print("📝 Next Steps:")
        print("   1. Test with full system running (server + Redis)")
        print("   2. Create E2E tests with real API calls")
        print("   3. Monitor metrics in production")
    else:
        print("⚠️  Some tests failed.")
    
    print()
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_intent_detection_logic())