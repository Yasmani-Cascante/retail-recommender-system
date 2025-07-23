# test_market_validation.py
"""
Validation test to ensure market adaptation is actually happening
"""

import asyncio
import aiohttp
import json
from datetime import datetime


async def validate_market_adaptation():
    """Validate that market adaptation is working correctly"""
    
    API_URL = "http://localhost:8000/v1/mcp/conversation"
    API_KEY = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    # Test for US market
    data = {
        "query": "busco aros de oro",
        "market_id": "US",
        "session_id": f"validation_{int(datetime.now().timestamp())}"
    }
    
    print("🧪 MARKET ADAPTATION VALIDATION TEST")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, headers=headers, json=data) as response:
            if response.status != 200:
                print(f"❌ API Error: {response.status}")
                return False
            
            result = await response.json()
            recommendations = result.get("recommendations", [])
            
            if not recommendations:
                print("❌ No recommendations received")
                return False
            
            print(f"✅ Received {len(recommendations)} recommendations")
            
            # Validate first recommendation
            first_rec = recommendations[0]
            
            print("\nValidating first recommendation:")
            print(f"Title: {first_rec.get('title')}")
            print(f"Price: {first_rec.get('price')} {first_rec.get('currency')}")
            
            # Validation checks
            checks = {
                "Has adaptation metadata": "_market_adaptation" in first_rec,
                "Has original price": "original_price" in first_rec,
                "Price is converted": first_rec.get("price", 0) < 100,  # Should be ~$3-20, not thousands
                "Currency is USD": first_rec.get("currency") == "USD",
                "Title contains English": any(word in first_rec.get("title", "").lower() for word in ["earrings", "gold", "ring", "bracelet"])
            }
            
            print("\nValidation Results:")
            all_passed = True
            for check, passed in checks.items():
                status = "✅" if passed else "❌"
                print(f"{status} {check}")
                if not passed:
                    all_passed = False
            
            if all_passed:
                print("\n✅ ALL VALIDATIONS PASSED - Market adaptation is working!")
            else:
                print("\n❌ VALIDATION FAILED - Market adaptation is not working properly")
                
                # Debug info
                print("\nDebug info:")
                print(f"Full recommendation: {json.dumps(first_rec, indent=2)}")
            
            return all_passed


if __name__ == "__main__":
    result = asyncio.run(validate_market_adaptation())
    exit(0 if result else 1)
