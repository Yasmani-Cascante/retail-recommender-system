#!/usr/bin/env python3
"""
Test Import After Redis Fixes
=============================

Verifica que los imports funcionan después de corregir referencias a RedisClient.
"""

import sys
sys.path.append('src')

def test_imports():
    """Test que los imports funcionan sin errores"""
    
    print("🧪 TESTING IMPORTS POST-FIX")
    print("=" * 40)
    
    try:
        print("1. Testing optimized_conversation_manager...")
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        print("   ✅ Import successful")
        
        # Test constructor
        try:
            manager = OptimizedConversationAIManager('test_key')
            print("   ✅ Constructor successful")
        except Exception as e:
            print(f"   ⚠️ Constructor issue: {e}")
        
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
    
    try:
        print("\n2. Testing mcp_personalization_engine...")
        from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine
        print("   ✅ Import successful")
        
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
    
    print("\n✅ IMPORT TEST COMPLETED")

if __name__ == "__main__":
    test_imports()
