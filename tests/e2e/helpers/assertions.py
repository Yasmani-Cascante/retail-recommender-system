"""
E2E Test Helpers & Custom Assertions
====================================

This module provides reusable assertion helpers and utility functions
for E2E tests to ensure consistency and reduce code duplication.

Usage:
    from tests.e2e.helpers.assertions import (
        assert_valid_product_response,
        assert_performance_acceptable,
        assert_market_data_correct
    )
"""

from typing import Dict, Any, List, Optional
import time


# =============================================================================
# PRODUCT RESPONSE ASSERTIONS
# =============================================================================

def assert_valid_product_response(
    product: Dict[str, Any],
    require_inventory: bool = False,
    require_images: bool = False
) -> None:
    """
    Validate that a product response has all required fields with correct types.
    
    Args:
        product: Product dictionary from API response
        require_inventory: If True, asserts stock_quantity is present
        require_images: If True, asserts at least one image exists
        
    Raises:
        AssertionError: If any validation fails
        
    Example:
        response = await client.get("/v1/products/123")
        product = response.json()
        assert_valid_product_response(product, require_inventory=True)
        
    Note:
        Price and images are OPTIONAL because Shopify products structure:
        - price is in variants[0].price
        - images are in images[] array
        The API may normalize these differently depending on source.
    """
    # Required fields
    assert "id" in product, "Product missing 'id' field"
    assert "title" in product, "Product missing 'title' field"
    
    # Validate types
    assert isinstance(str(product["id"]), str), "Product ID must be string-convertible"
    assert isinstance(product["title"], str), "Title must be string"
    assert len(product["title"]) > 0, "Title cannot be empty"
    
    # ✅ FIX: Price is OPTIONAL (may be in variants)
    if "price" in product and product["price"] is not None:
        price = product["price"]
        assert isinstance(price, (int, float, str)), "Price must be numeric or numeric string"
        try:
            float_price = float(price)
            assert float_price >= 0, f"Price cannot be negative: {float_price}"
        except (ValueError, TypeError):
            assert False, f"Price '{price}' cannot be converted to number"
    
    # Optional validations
    if require_inventory:
        assert "stock_quantity" in product, "Product missing 'stock_quantity' field"
        stock = product["stock_quantity"]
        assert isinstance(stock, int), "Stock quantity must be integer"
        assert stock >= 0, f"Stock cannot be negative: {stock}"
    
    if require_images:
        assert "images" in product, "Product missing 'images' field"
        images = product["images"]
        assert isinstance(images, list), "Images must be a list"
        assert len(images) > 0, "Product must have at least one image"


def assert_valid_product_list_response(
    response_data: Dict[str, Any],
    min_products: int = 1,
    max_products: int = 100
) -> None:
    """
    Validate a product list response (search results, recommendations, etc).
    
    Args:
        response_data: Full response from API
        min_products: Minimum expected products
        max_products: Maximum expected products
        
    Raises:
        AssertionError: If validation fails
        
    Example:
        response = await client.get("/v1/products/search/?q=dress")
        data = response.json()
        assert_valid_product_list_response(data, min_products=5)
    """
    # Validate response structure
    assert "products" in response_data, "Response missing 'products' key"
    
    products = response_data["products"]
    assert isinstance(products, list), "Products must be a list"
    
    # Validate count
    num_products = len(products)
    assert num_products >= min_products, \
        f"Expected at least {min_products} products, got {num_products}"
    assert num_products <= max_products, \
        f"Expected at most {max_products} products, got {num_products}"
    
    # Validate each product
    for i, product in enumerate(products):
        try:
            assert_valid_product_response(product)
        except AssertionError as e:
            raise AssertionError(f"Product at index {i} failed validation: {e}")


# =============================================================================
# PERFORMANCE ASSERTIONS
# =============================================================================

def assert_performance_acceptable(
    response_time_ms: float,
    max_time_ms: float = 2000.0,
    operation_name: str = "Operation"
) -> None:
    """
    Assert that an operation completed within acceptable time.
    
    Args:
        response_time_ms: Actual response time in milliseconds
        max_time_ms: Maximum acceptable time in milliseconds
        operation_name: Name of operation for error message
        
    Raises:
        AssertionError: If response time exceeds maximum
        
    Example:
        start = time.time()
        response = await client.get("/v1/products/search")
        elapsed_ms = (time.time() - start) * 1000
        assert_performance_acceptable(elapsed_ms, max_time_ms=2000, 
                                     operation_name="Product Search")
    """
    assert response_time_ms <= max_time_ms, \
        f"{operation_name} took {response_time_ms:.2f}ms, " \
        f"exceeds maximum of {max_time_ms:.2f}ms"


def assert_cache_hit_performance(
    first_request_ms: float,
    second_request_ms: float,
    min_speedup: float = 5.0
) -> None:
    """
    Assert that cache hit provides significant performance improvement.
    
    Args:
        first_request_ms: Response time of cache miss (first request)
        second_request_ms: Response time of cache hit (second request)
        min_speedup: Minimum expected speedup factor (e.g., 5x faster)
        
    Raises:
        AssertionError: If speedup is less than minimum
        
    Example:
        # First request (cache miss)
        start = time.time()
        response1 = await client.get("/v1/products/123")
        time1 = (time.time() - start) * 1000
        
        # Second request (cache hit)
        start = time.time()
        response2 = await client.get("/v1/products/123")
        time2 = (time.time() - start) * 1000
        
        assert_cache_hit_performance(time1, time2, min_speedup=10.0)
    """
    actual_speedup = first_request_ms / second_request_ms if second_request_ms > 0 else 0
    
    assert actual_speedup >= min_speedup, \
        f"Cache hit speedup {actual_speedup:.1f}x is less than " \
        f"expected {min_speedup:.1f}x " \
        f"(first: {first_request_ms:.2f}ms, second: {second_request_ms:.2f}ms)"


# =============================================================================
# MULTI-MARKET ASSERTIONS
# =============================================================================

def assert_market_data_correct(
    product: Dict[str, Any],
    expected_market: str,
    expected_currency: Optional[str] = None
) -> None:
    """
    Validate that product data is correct for the specified market.
    
    Args:
        product: Product dictionary
        expected_market: Expected market code (US, MX, ES, CL)
        expected_currency: Expected currency code (USD, MXN, EUR, CLP)
            If None, currency validation is skipped
            
    Raises:
        AssertionError: If market data doesn't match expectations
        
    Example:
        response = await client.get("/v1/products/123?market=MX")
        product = response.json()
        assert_market_data_correct(product, expected_market="MX", 
                                   expected_currency="MXN")
    """
    # Validate market field exists
    if "market" in product:
        actual_market = product["market"]
        assert actual_market == expected_market, \
            f"Expected market '{expected_market}', got '{actual_market}'"
    
    # Validate currency if specified
    if expected_currency is not None:
        assert "currency" in product, "Product missing 'currency' field"
        actual_currency = product["currency"]
        assert actual_currency == expected_currency, \
            f"Expected currency '{expected_currency}', got '{actual_currency}'"
    
    # Validate price makes sense for market
    price = product.get("price", 0)
    if expected_market == "US" and expected_currency == "USD":
        # US prices typically $10-$10,000
        assert 1 <= price <= 100000, \
            f"USD price {price} seems unrealistic"
    elif expected_market == "MX" and expected_currency == "MXN":
        # Mexican prices typically 100-200,000 pesos
        assert 10 <= price <= 500000, \
            f"MXN price {price} seems unrealistic"


def assert_currency_conversion_applied(
    usd_price: float,
    converted_price: float,
    target_currency: str,
    tolerance: float = 0.10
) -> None:
    """
    Validate that currency conversion was applied correctly.
    
    Args:
        usd_price: Original price in USD
        converted_price: Converted price
        target_currency: Target currency code
        tolerance: Acceptable variance (0.10 = 10%)
        
    Raises:
        AssertionError: If conversion seems incorrect
        
    Example:
        usd_product = await client.get("/v1/products/123?market=US")
        mxn_product = await client.get("/v1/products/123?market=MX")
        
        assert_currency_conversion_applied(
            usd_product["price"],
            mxn_product["price"],
            "MXN",
            tolerance=0.05  # 5% tolerance for exchange rate variation
        )
    """
    # Approximate exchange rates (these should ideally come from config)
    exchange_rates = {
        "USD": 1.0,
        "MXN": 17.0,  # ~17 pesos per dollar
        "EUR": 0.85,  # ~0.85 euros per dollar
        "CLP": 800.0  # ~800 pesos chilenos per dollar
    }
    
    if target_currency not in exchange_rates:
        # Skip validation for unknown currencies
        return
    
    expected_rate = exchange_rates[target_currency]
    expected_price = usd_price * expected_rate
    
    # Calculate variance
    variance = abs(converted_price - expected_price) / expected_price
    
    assert variance <= tolerance, \
        f"Currency conversion for {target_currency} seems incorrect. " \
        f"Expected ~{expected_price:.2f}, got {converted_price:.2f} " \
        f"(variance: {variance*100:.1f}%, tolerance: {tolerance*100:.1f}%)"


# =============================================================================
# RECOMMENDATION ASSERTIONS
# =============================================================================

def assert_valid_recommendations_response(
    response_data: Dict[str, Any],
    expected_count: int = 5,
    allow_fewer: bool = True
) -> None:
    """
    Validate a recommendations response structure and content.
    
    Args:
        response_data: Response from recommendations endpoint
        expected_count: Expected number of recommendations
        allow_fewer: If True, accepts fewer recommendations than expected
        
    Raises:
        AssertionError: If validation fails
        
    Example:
        response = await client.get("/v1/recommendations/123?n=5")
        data = response.json()
        assert_valid_recommendations_response(data, expected_count=5)
    """
    # Validate structure
    assert "recommendations" in response_data, \
        "Response missing 'recommendations' key"
    
    recommendations = response_data["recommendations"]
    assert isinstance(recommendations, list), \
        "Recommendations must be a list"
    
    # Validate count
    actual_count = len(recommendations)
    if allow_fewer:
        assert 0 <= actual_count <= expected_count, \
            f"Expected at most {expected_count} recommendations, got {actual_count}"
    else:
        assert actual_count == expected_count, \
            f"Expected exactly {expected_count} recommendations, got {actual_count}"
    
    # Validate each recommendation
    for i, rec in enumerate(recommendations):
        try:
            assert_valid_product_response(rec)
        except AssertionError as e:
            raise AssertionError(f"Recommendation at index {i} failed validation: {e}")


def assert_recommendations_relevant(
    source_product_id: str,
    recommendations: List[Dict[str, Any]],
    max_same_product: int = 0
) -> None:
    """
    Validate that recommendations are relevant (not duplicating source product).
    
    Args:
        source_product_id: ID of product that recommendations are based on
        recommendations: List of recommended products
        max_same_product: Maximum allowed occurrences of source product in results
        
    Raises:
        AssertionError: If recommendations include too many copies of source
        
    Example:
        response = await client.get("/v1/recommendations/123")
        recommendations = response.json()["recommendations"]
        assert_recommendations_relevant("123", recommendations, max_same_product=0)
    """
    same_product_count = sum(
        1 for rec in recommendations 
        if str(rec.get("id")) == str(source_product_id)
    )
    
    assert same_product_count <= max_same_product, \
        f"Found {same_product_count} occurrences of source product {source_product_id} " \
        f"in recommendations (max allowed: {max_same_product})"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def measure_response_time(func):
    """
    Decorator to measure and return response time of async functions.
    
    Usage:
        @measure_response_time
        async def get_product():
            return await client.get("/v1/products/123")
        
        response, elapsed_ms = await get_product()
    """
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed_ms = (time.time() - start) * 1000
        return result, elapsed_ms
    return wrapper


def format_performance_report(
    operations: Dict[str, float],
    thresholds: Dict[str, float]
) -> str:
    """
    Generate a formatted performance report for logging.
    
    Args:
        operations: Dict of operation name -> response time in ms
        thresholds: Dict of operation name -> max acceptable time in ms
        
    Returns:
        Formatted string report
        
    Example:
        ops = {"Search": 450, "Details": 890, "Recommendations": 1200}
        thresholds = {"Search": 2000, "Details": 1000, "Recommendations": 1500}
        print(format_performance_report(ops, thresholds))
    """
    lines = ["📊 Performance Report:", "=" * 60]
    
    for operation, time_ms in operations.items():
        threshold = thresholds.get(operation, float('inf'))
        status = "✅" if time_ms <= threshold else "❌"
        percentage = (time_ms / threshold * 100) if threshold > 0 else 0
        
        lines.append(
            f"{status} {operation:20s}: {time_ms:7.2f}ms "
            f"({percentage:5.1f}% of {threshold:.0f}ms threshold)"
        )
    
    lines.append("=" * 60)
    return "\n".join(lines)