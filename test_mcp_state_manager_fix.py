#!/usr/bin/env python3
"""
VALIDATION SCRIPT: mcp_state_manager fix verification
"""

import sys
sys.path.append('src')

def test_mcp_state_manager_availability():
    """Test que mcp_state_manager está disponible en main_unified_redis"""
    
    print("🔍 TESTING MCP_STATE_MANAGER AVAILABILITY IN MAIN_UNIFIED_REDIS")
    print("=" * 70)
    
    try:
        # Importar main_unified_redis
        from src.api import main_unified_redis
        
        # Verificar si mcp_state_manager existe
        has_mcp_state_manager = hasattr(main_unified_redis, 'mcp_state_manager')
        
        print(f"📋 mcp_state_manager attribute exists: {has_mcp_state_manager}")
        
        if has_mcp_state_manager:
            mcp_state_manager = getattr(main_unified_redis, 'mcp_state_manager')
            print(f"📋 mcp_state_manager type: {type(mcp_state_manager) if mcp_state_manager else 'None'}")
            
            if mcp_state_manager:
                print("✅ SUCCESS: mcp_state_manager is available and initialized")
                return True
            else:
                print("⚠️ PARTIAL: mcp_state_manager exists but is None")
                return False
        else:
            print("❌ FAILED: mcp_state_manager attribute does not exist")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_mcp_state_manager_availability()
    
    if success:
        print("\n🎉 FIX VERIFICATION SUCCESSFUL")
        print("mcp_state_manager is now available in main_unified_redis")
        print("\n🎯 Next steps:")
        print("   1. Restart the server: python src/api/main_unified_redis.py")
        print("   2. Test conversation state persistence")
        print("   3. Re-run Phase 2 validation")
    else:
        print("\n❌ FIX VERIFICATION FAILED")
        print("mcp_state_manager is still not properly available")
    
    sys.exit(0 if success else 1)
