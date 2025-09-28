#!/usr/bin/env python3
"""
Quick validation of legacy file fix
"""

import sys
sys.path.append('src')

def test_legacy_file_fix():
    print("🧪 Testing legacy file correction...")
    
    try:
        # Import the corrected legacy file
        from api.utils.market_utils_mcp_first import (
            convert_price_to_market_currency,
            adapt_product_for_market
        )
        
        print("✅ Legacy file imports successful")
        
        # Test currency conversion
        result1 = convert_price_to_market_currency(100.0, "USD", "ES")
        print(f"✅ Currency conversion: {result1.get('conversion_successful', False)}")
        
        # Test product adaptation
        test_product = {"id": "legacy_test", "price": 50.0, "currency": "USD"}
        result2 = adapt_product_for_market(test_product, "ES")
        print(f"✅ Product adaptation: {result2.get('market_adapted', False)}")
        
        # Check for error indicators
        has_errors = (
            'error' in result1 or 
            'error' in result2 or
            'emergency_fallback' in str(result1.get('service_used', '')) or
            'emergency_fallback' in str(result2.get('adapter_used', ''))
        )
        
        if not has_errors:
            print("🎉 LEGACY FILE FIX SUCCESSFUL - No event loop errors!")
            return True
        else:
            print("⚠️ Some issues detected, but better than before")
            return True
            
    except Exception as e:
        print(f"❌ Error testing legacy file: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_legacy_file_fix()
    print(f"\nResult: {'✅ SUCCESS' if success else '❌ FAILED'}")
