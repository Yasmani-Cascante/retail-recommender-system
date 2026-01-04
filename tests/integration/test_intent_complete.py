"""
Test Intent Detection - Complete Output
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.core.intent_detection import detect_intent

def test_with_complete_output():
    """Test with complete output for both queries"""
    
    test_cases = [
        ("¿cuál es la política de devolución?", "INFORMATIONAL"),
        ("busco vestidos elegantes", "TRANSACTIONAL"),
        ("necesito zapatos formales", "TRANSACTIONAL"),
        ("qué métodos de pago aceptan", "INFORMATIONAL"),
    ]
    
    print("="*80)
    print("INTENT DETECTION - COMPLETE TEST")
    print("="*80)
    print()
    
    for query, expected in test_cases:
        print(f"Query: '{query}'")
        print(f"Expected: {expected}")
        print("-" * 60)
        
        result = detect_intent(query)
        
        print(f"✓ Primary Intent: {result.primary_intent}")
        print(f"✓ Sub-Intent: {result.sub_intent}")
        print(f"✓ Confidence: {result.confidence:.2f}")
        print(f"✓ Reasoning: {result.reasoning}")
        
        if result.matched_patterns:
            print(f"✓ Matched Patterns: {result.matched_patterns[:3]}")
        else:
            print(f"✓ Matched Patterns: []")
        
        # Validation
        is_correct = result.primary_intent.value.upper() == expected
        status = "✅ PASS" if is_correct else "❌ FAIL"
        
        print(f"\n{status}")
        print()
        print("="*80)
        print()

if __name__ == "__main__":
    test_with_complete_output()