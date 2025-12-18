"""
E2E Test Template
=================

This is a template for creating new E2E tests. Copy this file and modify
it according to your specific test scenario.

Usage:
    1. Copy this file: cp test_template.py test_my_feature.py
    2. Replace FEATURE_NAME with your feature name
    3. Implement test scenarios following the structure below
    4. Run: pytest tests/e2e/test_my_feature.py -v
"""

import pytest
import time
from typing import Dict, Any

# Import custom assertions and helpers
from tests.e2e.helpers import (
    assert_valid_product_response,
    assert_performance_acceptable,
    assert_market_data_correct,
    measure_response_time,
)

# Import fixtures utilities if needed
from tests.e2e.fixtures import get_test_products, get_test_product_by_id


# =============================================================================
# TEST SUITE: FEATURE_NAME
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_feature_happy_path(
    test_client_with_warmup,
    mock_auth
):
    """
    Test the happy path for FEATURE_NAME.
    
    Scenario:
        User does X
        System responds with Y
        
    Expected Outcome:
        - Response status: 200 OK
        - Response contains required fields
        - Performance is acceptable
        
    Example:
        This tests the main success scenario where everything works as expected.
    """
    # STEP 1: Setup
    # Prepare any necessary data or state
    test_query = "example search"
    
    # STEP 2: Execute
    # Make the API call
    start_time = time.time()
    response = await test_client_with_warmup.get(
        "/v1/your-endpoint",
        params={"q": test_query}
    )
    elapsed_ms = (time.time() - start_time) * 1000
    
    # STEP 3: Assert - Status Code
    assert response.status_code == 200, \
        f"Expected 200 OK, got {response.status_code}"
    
    # STEP 4: Assert - Response Structure
    data = response.json()
    assert "expected_key" in data, "Response missing 'expected_key'"
    
    # STEP 5: Assert - Performance
    assert_performance_acceptable(
        elapsed_ms,
        max_time_ms=2000,
        operation_name="FEATURE_NAME Happy Path"
    )
    
    # STEP 6: Log Success
    print(f"\n✅ Happy path completed in {elapsed_ms:.2f}ms")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_feature_edge_case_empty_result(
    test_client_with_warmup,
    mock_auth
):
    """
    Test edge case: Empty results.
    
    Scenario:
        User searches for something that doesn't exist
        System returns empty results gracefully
        
    Expected Outcome:
        - Response status: 200 OK (not 404)
        - Empty array or appropriate empty response
        - No crashes or errors
        
    Example:
        Searching for "nonexistent_xyz_123" should return empty, not error.
    """
    # Execute
    response = await test_client_with_warmup.get(
        "/v1/your-endpoint",
        params={"q": "nonexistent_xyz_123"}
    )
    
    # Assert
    assert response.status_code == 200, \
        "Empty results should still return 200 OK"
    
    data = response.json()
    assert "results" in data, "Response should have 'results' key"
    assert len(data["results"]) == 0, "Results should be empty"
    
    print("\n✅ Empty result edge case handled gracefully")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_feature_error_handling_invalid_input(
    test_client_with_warmup,
    mock_auth
):
    """
    Test error handling for invalid input.
    
    Scenario:
        User provides invalid parameters
        System returns appropriate error message
        
    Expected Outcome:
        - Response status: 400 Bad Request or 422 Unprocessable Entity
        - Clear error message
        - System doesn't crash
        
    Example:
        Sending invalid product ID format should return clear error.
    """
    # Execute with invalid input
    response = await test_client_with_warmup.get(
        "/v1/your-endpoint/INVALID_ID_FORMAT"
    )
    
    # Assert
    assert response.status_code in [400, 404, 422], \
        f"Expected error status, got {response.status_code}"
    
    data = response.json()
    assert "detail" in data or "error" in data, \
        "Error response should contain error message"
    
    print(f"\n✅ Invalid input handled with status {response.status_code}")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_feature_performance_under_load(
    test_client_with_warmup,
    mock_auth
):
    """
    Test performance with multiple requests.
    
    Scenario:
        Multiple users access the feature simultaneously
        System maintains acceptable performance
        
    Expected Outcome:
        - All requests complete successfully
        - Average response time acceptable
        - No degradation in quality
        
    Example:
        Simulates 10 concurrent users accessing the feature.
    """
    import asyncio
    
    num_requests = 10
    max_avg_time_ms = 3000  # 3 seconds average acceptable
    
    # Execute multiple requests concurrently
    async def make_request():
        start = time.time()
        response = await test_client_with_warmup.get("/v1/your-endpoint")
        elapsed = (time.time() - start) * 1000
        return response.status_code, elapsed
    
    # Run requests concurrently
    results = await asyncio.gather(*[make_request() for _ in range(num_requests)])
    
    # Analyze results
    status_codes = [r[0] for r in results]
    times_ms = [r[1] for r in results]
    
    success_count = sum(1 for code in status_codes if code == 200)
    avg_time_ms = sum(times_ms) / len(times_ms)
    max_time_ms = max(times_ms)
    
    # Assert
    assert success_count == num_requests, \
        f"Expected all {num_requests} requests to succeed, got {success_count}"
    
    assert avg_time_ms <= max_avg_time_ms, \
        f"Average time {avg_time_ms:.2f}ms exceeds limit {max_avg_time_ms}ms"
    
    print(f"\n✅ Load test passed:")
    print(f"   Requests: {num_requests}")
    print(f"   Success rate: 100%")
    print(f"   Avg time: {avg_time_ms:.2f}ms")
    print(f"   Max time: {max_time_ms:.2f}ms")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_feature_multi_market_support(
    test_client_with_warmup,
    mock_auth
):
    """
    Test multi-market functionality.
    
    Scenario:
        User from different markets access the same feature
        System returns appropriate data for each market
        
    Expected Outcome:
        - Correct currency for each market
        - Correct pricing conversions
        - Market-specific content when applicable
        
    Example:
        US user sees USD prices, MX user sees MXN prices.
    """
    markets = [
        ("US", "USD"),
        ("MX", "MXN"),
        ("ES", "EUR"),
    ]
    
    for market, expected_currency in markets:
        # Execute
        response = await test_client_with_warmup.get(
            "/v1/your-endpoint",
            params={"market": market}
        )
        
        # Assert
        assert response.status_code == 200, \
            f"Failed for market {market}"
        
        data = response.json()
        
        # Verify market-specific data
        if "products" in data:
            for product in data["products"][:5]:  # Check first 5
                assert_market_data_correct(
                    product,
                    expected_market=market,
                    expected_currency=expected_currency
                )
        
        print(f"   ✅ Market {market} validated ({expected_currency})")
    
    print(f"\n✅ Multi-market test passed for {len(markets)} markets")


# =============================================================================
# HELPER FUNCTIONS (Optional)
# =============================================================================

def prepare_test_data() -> Dict[str, Any]:
    """
    Prepare test data specific to this test suite.
    
    Returns:
        Dictionary with test data
    """
    return {
        "sample_id": "TEST_123",
        "sample_query": "example",
        # Add more test data as needed
    }


# =============================================================================
# FIXTURES (Optional - for suite-specific fixtures)
# =============================================================================

@pytest.fixture
def feature_test_data():
    """
    Fixture providing test data for this feature.
    
    Usage:
        async def test_something(feature_test_data):
            test_id = feature_test_data["sample_id"]
    """
    return prepare_test_data()


# =============================================================================
# NOTES FOR TEST DEVELOPMENT
# =============================================================================
"""
Best Practices for E2E Tests:

1. **Test Structure**
   - Arrange (Setup)
   - Act (Execute)
   - Assert (Verify)

2. **Naming Convention**
   - test_feature_scenario_expected_outcome
   - Example: test_search_empty_query_returns_validation_error

3. **Use Custom Assertions**
   - Leverage helpers from tests.e2e.helpers
   - Makes tests more readable and maintainable

4. **Performance Testing**
   - Always measure response times
   - Use assert_performance_acceptable()
   - Set realistic thresholds

5. **Error Handling**
   - Test both success and failure paths
   - Verify error messages are clear
   - Ensure no crashes on invalid input

6. **Documentation**
   - Every test should have a docstring
   - Explain the scenario being tested
   - Document expected outcomes

7. **Markers**
   - Use @pytest.mark.e2e for all E2E tests
   - Use @pytest.mark.slow for long-running tests
   - Use @pytest.mark.skip("reason") to skip temporarily

8. **Debugging**
   - Add print statements for visibility
   - Use -v and -s flags when running: pytest -vs
   - Check logs in captured output

9. **Isolation**
   - Each test should be independent
   - Don't rely on execution order
   - Use fixtures for shared setup

10. **Realistic Scenarios**
    - Test real user workflows
    - Use realistic test data
    - Consider edge cases and errors

Remember: E2E tests verify the entire system works together.
They should test real user journeys, not implementation details.
"""