# ==============================================================================
# USER JOURNEY 1: COMPLETE PURCHASE FLOW - FIXED VERSION
# ==============================================================================
"""
Persona: Maria, 28, US, fashion shopper
Goal: Find and purchase wedding dress
Market: US
Expected Duration: ~10-15s

✅ FIXED: Uses real products from catalog instead of hardcoded values
"""

import pytest
import time


@pytest.mark.asyncio
async def test_user_journey_purchase(
    test_client_with_warmup,
    mock_auth
):
    """
    Complete purchase flow test using REAL products from catalog.
    
    ✅ IMPROVEMENTS:
    - Uses actual search results instead of hardcoded product IDs
    - Validates against real product titles from catalog
    - More robust assertions with error messages
    - Added debug print statements for better visibility
    """
    start_time = time.time()
    
    # ===========================================================================
    # STEP 1: Initial Search
    # ===========================================================================
    """
    User Action: Search for "Vestido de Novia" (wedding dress)
    System Response:
      - Query TF-IDF engine for content similarity
      - Return matching products from real catalog
    Expected: < 2s, at least 5 products
    """
    print("\n" + "="*80)
    print("🛍️  STEP 1: Search for 'Vestido de Novia'")
    print("="*80)
    
    response = await test_client_with_warmup.get(
        "/v1/products/search/",
        params={"q": "Vestido de Novia"}
    )
    
    assert response.status_code == 200, f"❌ Search failed with status {response.status_code}"
    
    search_results = response.json()
    assert "products" in search_results, "❌ Response missing 'products' key"
    
    products = search_results["products"]
    assert len(products) >= 5, f"❌ Expected at least 5 products, got {len(products)}"
    
    print(f"✅ Found {len(products)} products matching 'Vestido de Novia'")
    print(f"   First 3 products:")
    for i, p in enumerate(products[:3], 1):
        print(f"   {i}. {p['title'][:60]}... (ID: {p['id']})")
    
    # ===========================================================================
    # STEP 2: View Product Details
    # ===========================================================================
    """
    User Action: Click on first product from search results
    System Response:
      - Fetch product details from cache
      - Return enriched product data with inventory
    Expected: < 2s
    """
    print("\n" + "="*80)
    print("🔍 STEP 2: View Product Details")
    print("="*80)
    
    # ✅ Use actual product from search results
    first_product = products[0]
    product_id = str(first_product["id"])  # ✅ Convert to string for consistency
    expected_title = first_product["title"]
    
    print(f"   Selected product: '{expected_title}' (ID: {product_id})")
    
    response = await test_client_with_warmup.get(f"/v1/products/{product_id}")
    
    assert response.status_code == 200, f"❌ Product details failed with status {response.status_code}"
    
    product_details = response.json()
    
    # Validate product details match what we expected
    # ✅ Convert both to string for comparison
    assert str(product_details["id"]) == str(product_id), \
        f"❌ Product ID mismatch: expected {product_id}, got {product_details['id']}"
    
    assert product_details["title"] == expected_title, \
        f"❌ Title mismatch: expected '{expected_title}', got '{product_details['title']}'"
    
    print(f"✅ Retrieved product details:")
    print(f"   Title: {product_details['title']}")
    print(f"   Price: ${product_details.get('price', 'N/A')} {product_details.get('currency', 'USD')}")
    print(f"   Stock: {product_details.get('stock_quantity', 'N/A')} units")
    print(f"   Category: {product_details.get('category', 'N/A')}")
    
    # ===========================================================================
    # STEP 3: Get Recommendations
    # ===========================================================================
    """
    User Action: Scroll to "You might also like" section
    System Response:
      - HybridRecommender combines:
        * Similar by TF-IDF (content)
        * Collaborative filtering (if available)
      - Return 5 personalized recommendations
    Expected: < 2s
    """
    print("\n" + "="*80)
    print("🎯 STEP 3: Get Recommendations")
    print("="*80)
    
    response = await test_client_with_warmup.get(
        f"/v1/recommendations/{product_id}",
        params={"n": 5}
    )
    
    assert response.status_code == 200, f"❌ Recommendations failed with status {response.status_code}"
    
    recommendations_data = response.json()
    
    # Validate recommendations structure
    assert "recommendations" in recommendations_data, "❌ Response missing 'recommendations' key"
    
    recommendations = recommendations_data["recommendations"]
    assert len(recommendations) > 0, "❌ No recommendations returned"
    assert len(recommendations) <= 5, f"❌ Too many recommendations: expected max 5, got {len(recommendations)}"
    
    print(f"✅ Got {len(recommendations)} recommendations:")
    for i, rec in enumerate(recommendations, 1):
        rec_title = rec.get('title', 'Unknown')[:50]
        rec_id = rec.get('id', 'Unknown')
        print(f"   {i}. {rec_title}... (ID: {rec_id})")
    
    # ===========================================================================
    # STEP 4: Add to Cart (Record Event)
    # ===========================================================================
    """
    User Action: Click "Add to Cart"
    System Response:
      - Record "add-to-cart" event
      - Update user interaction history
    Expected: < 1s
    """
    print("\n" + "="*80)
    print("🛒 STEP 4: Add to Cart")
    print("="*80)
    
    response = await test_client_with_warmup.post(
        f"/v1/events/user/user_maria_123",
        params={
            "event_type": "add-to-cart",
            "product_id": product_id
        }
    )
    
    assert response.status_code == 200, f"❌ Add to cart failed with status {response.status_code}"
    
    cart_response = response.json()
    assert cart_response.get("status") == "success", "❌ Event recording failed"
    
    print(f"✅ Added product to cart successfully")
    print(f"   Event type: add-to-cart")
    print(f"   Product ID: {product_id}")
    
    # ===========================================================================
    # STEP 5: Checkout (Purchase Complete)
    # ===========================================================================
    """
    User Action: Proceed to checkout
    System Response:
      - Record "purchase-complete" event
      - Finalize transaction
    Expected: < 1s
    """
    print("\n" + "="*80)
    print("💳 STEP 5: Complete Purchase")
    print("="*80)
    
    response = await test_client_with_warmup.post(
        f"/v1/events/user/user_maria_123",
        params={
            "event_type": "purchase-complete",
            "product_id": product_id,
            "purchase_amount": product_details.get("price", 99.99)
        }
    )
    
    assert response.status_code == 200, f"❌ Purchase failed with status {response.status_code}"
    
    purchase_response = response.json()
    assert purchase_response.get("status") == "success", "❌ Purchase event recording failed"
    
    print(f"✅ Purchase completed successfully")
    print(f"   Event type: purchase-complete")
    print(f"   Product ID: {product_id}")
    print(f"   Amount: ${product_details.get('price', 99.99)}")
    
    # ===========================================================================
    # VALIDATION: End-to-End Journey
    # ===========================================================================
    """
    Verify entire flow completed successfully:
      - All steps passed
      - All events recorded
      - Total time reasonable
    """
    total_elapsed_time = time.time() - start_time
    
    print("\n" + "="*80)
    print("📊 JOURNEY SUMMARY")
    print("="*80)
    print(f"   ✅ Step 1: Search - PASSED")
    print(f"   ✅ Step 2: Product Details - PASSED")
    print(f"   ✅ Step 3: Recommendations - PASSED")
    print(f"   ✅ Step 4: Add to Cart - PASSED")
    print(f"   ✅ Step 5: Purchase - PASSED")
    print(f"   ⏱️  Total Time: {total_elapsed_time:.2f}s")
    print("="*80)
    
    # Final assertion: reasonable completion time
    assert total_elapsed_time < 30.0, \
        f"❌ Journey took too long: {total_elapsed_time:.2f}s (expected < 30s)"
    
    print(f"\n🎉 USER JOURNEY PURCHASE COMPLETED SUCCESSFULLY!")