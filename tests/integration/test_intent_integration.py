"""
Test de Integración: Intent Detection + MCP Handler
====================================================

Este test verifica que Intent Detection funciona correctamente
integrado con el MCP Conversation Handler.
"""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.core.mcp_conversation_handler import get_mcp_conversation_recommendations


async def test_integration():
    """Test complete integration of Intent Detection with MCP Handler"""
    
    test_cases = [
        {
            "name": "Test 1: Informational - Return Policy",
            "query": "¿cuál es la política de devolución?",
            "expected_type": "informational",
            "expected_has_products": False
        },
        {
            "name": "Test 2: Informational - Shipping Policy",
            "query": "cómo funciona el envío",
            "expected_type": "informational",
            "expected_has_products": False
        },
        {
            "name": "Test 3: Transactional - Product Search",
            "query": "busco vestidos elegantes",
            "expected_type": None,  # Normal response (not "informational")
            "expected_has_products": True
        },
        {
            "name": "Test 4: Transactional - Product Search",
            "query": "necesito zapatos formales",
            "expected_type": None,  # Normal response
            "expected_has_products": True
        }
    ]
    
    print("="*80)
    print("INTEGRATION TEST: Intent Detection + MCP Handler")
    print("="*80)
    print()
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"{test_case['name']}")
        print("-" * 60)
        print(f"Query: '{test_case['query']}'")
        
        try:
            # Call MCP Handler
            result = await get_mcp_conversation_recommendations(
                validated_user_id=f"test_user_{i}",
                validated_product_id=None,
                conversation_query=test_case['query'],
                market_id='US',
                n_recommendations=5,
                session_id=f"test_session_{i}"
            )
            
            # Extract key information
            response_type = result.get('type', 'normal')
            has_products = len(result.get('recommendations', [])) > 0
            answer = result.get('answer', '')
            ai_response = result.get('ai_response', '')
            metadata = result.get('metadata', {})
            
            # Check intent detection metadata
            intent_info = metadata.get('intent_detection', {})
            kb_used = metadata.get('knowledge_base_used', False)
            
            print(f"\n✓ Response Type: {response_type}")
            print(f"✓ Has Products: {has_products} ({len(result.get('recommendations', []))} items)")
            print(f"✓ KB Used: {kb_used}")
            
            if intent_info:
                print(f"✓ Intent Detected: {intent_info.get('primary_intent', 'N/A')}")
                print(f"✓ Sub-Intent: {intent_info.get('sub_intent', 'N/A')}")
                print(f"✓ Confidence: {intent_info.get('confidence', 0):.2f}")
            
            # Show response preview
            if response_type == "informational":
                print(f"\n📚 Answer Preview:")
                print(f"   {(answer or ai_response)[:150]}...")
            else:
                print(f"\n🛍️ AI Response Preview:")
                print(f"   {ai_response[:150]}...")
            
            # Validation
            type_match = (
                (test_case['expected_type'] is None and response_type != "informational") or
                (test_case['expected_type'] == response_type)
            )
            products_match = has_products == test_case['expected_has_products']
            
            if type_match and products_match:
                print(f"\n✅ PASS - Test successful")
                results.append({
                    'test': test_case['name'],
                    'status': 'PASS',
                    'response_type': response_type,
                    'has_products': has_products
                })
            else:
                print(f"\n❌ FAIL - Mismatch detected")
                print(f"   Expected type: {test_case['expected_type']}, Got: {response_type}")
                print(f"   Expected products: {test_case['expected_has_products']}, Got: {has_products}")
                results.append({
                    'test': test_case['name'],
                    'status': 'FAIL',
                    'response_type': response_type,
                    'has_products': has_products
                })
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            print(f"   Exception type: {type(e).__name__}")
            import traceback
            print(f"   Traceback:")
            traceback.print_exc()
            results.append({
                'test': test_case['name'],
                'status': 'ERROR',
                'error': str(e)
            })
        
        print()
        print("="*80)
        print()
    
    # Summary
    print("="*80)
    print("TEST SUMMARY")
    print("="*80)
    print()
    
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    
    print(f"Total Tests: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Errors: {errors}")
    print()
    
    if passed == len(results):
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  Some tests failed. Review the output above for details.")
    
    print()
    print("="*80)
    
    return results


if __name__ == "__main__":
    print("\n")
    print("🚀 Starting Integration Tests...")
    print("\n")
    
    # Run async test
    asyncio.run(test_integration())