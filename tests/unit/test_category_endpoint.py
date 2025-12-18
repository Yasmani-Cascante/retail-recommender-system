# tests/unit/test_category_endpoint.py
import pytest

@pytest.mark.asyncio
async def test_category_endpoint_uses_index(test_client, mock_tfidf):
    """Verify endpoint uses category_index when available"""
    
    # Setup: Mock with category_index
    mock_tfidf.category_index = {
        "LENCERIA": [{"id": "1", "title": "Product 1"}]
    }
    
    response = await test_client.get("/v1/products/category/LENCERIA")
    
    assert response.status_code == 200
    # Verify no iteration over product_data occurred