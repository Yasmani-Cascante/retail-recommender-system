# ==============================================================================
# USER JOURNEY 2: PRODUCT DISCOVERY & RECOMMENDATIONS
# ==============================================================================
"""
Persona: Carlos, 35, ES, casual shopper
Goal: Browse and discover lingerie products
Market: ES
Expected Duration: ~2s (was ~15-20s)

✅ FIXED:
- Uses real category from catalog (LENCERIA)
- Injects mock_auth fixture properly
- Uses existing endpoints
- ~10x faster
"""

import pytest


@pytest.mark.asyncio
async def test_user_journey_discovery(
    test_client_with_warmup,
    mock_auth  # ✅ ADDED: Inject auth fixture
):
    """
    User Journey: Product Discovery Flow
    
    Tests the complete flow of browsing, viewing details,
    getting recommendations, and recording user events.
    """
    
    # STEP 1: Browse Category
    print("\n📂 STEP 1: Browse products by category...")
    response = await test_client_with_warmup.get(
        "/v1/products/category/LENCERIA",  # ✅ FIXED: Real category from catalog
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    # products = response.json()
    # assert isinstance(products, list), "Response should be a list of products"
    # assert len(products) > 0, "Should return at least one product"

    # ✅ FIX: El endpoint retorna {"products": [...], "pagination": {...}}
    # no una lista directa
    response_data = response.json()
    assert "products" in response_data, "Response should have 'products' key"
    products = response_data["products"]

    assert isinstance(products, list), "Products should be a list"
    assert len(products) > 0, "Should return at least one product"

    # Verify product structure
    first_product = products[0]
    assert "id" in first_product, "Product should have 'id'"
    assert "title" in first_product, "Product should have 'title'"
    print(f"✅ Found {len(products)} products in LENCERIA category")
    
    # STEP 2: View Product Details
    print("\n🔍 STEP 2: View product details and get recommendations...")
    product_id = first_product["id"]
    response = await test_client_with_warmup.get(
        f"/v1/recommendations/{product_id}",
        params={"n": 5}
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    recommendations_data = response.json()
    assert "product" in recommendations_data, "Should include product info"
    assert "recommendations" in recommendations_data, "Should include recommendations"
    print(f"✅ Got product details and recommendations")
    
    # STEP 3: Explore Similar Products
    print("\n🎯 STEP 3: Explore similar products...")
    similar_products = recommendations_data["recommendations"]
    assert len(similar_products) > 0, "Should return at least one recommendation"
    print(f"✅ Got {len(similar_products)} similar products")
    
    # STEP 4: Record User Events
    print("\n📝 STEP 4: Record user interactions...")
    events_recorded = 0
    for product in similar_products[:2]:  # Record views for first 2 products
        response = await test_client_with_warmup.post(
            f"/v1/events/user/user_carlos_456",
            params={
                "event_type": "detail-page-view",
                "product_id": product["id"]
            }
        )
        assert response.status_code == 200, f"Event recording failed: {response.text}"
        assert response.json()["status"] == "success", "Event should be recorded successfully"
        events_recorded += 1
    
    print(f"✅ Recorded {events_recorded} user events")
    
    # FINAL VALIDATION
    print("\n✅ USER JOURNEY DISCOVERY COMPLETED SUCCESSFULLY")
    print(f"   - Browsed category: LENCERIA")
    print(f"   - Viewed product: {product_id}")
    print(f"   - Got {len(similar_products)} recommendations")
    print(f"   - Recorded {events_recorded} events")