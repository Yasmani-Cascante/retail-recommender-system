"""
E2E Test Helpers Module
=======================

Provides reusable utilities and assertions for E2E tests.
"""

from .assertions import (
    # Product assertions
    assert_valid_product_response,
    assert_valid_product_list_response,
    
    # Performance assertions
    assert_performance_acceptable,
    assert_cache_hit_performance,
    
    # Multi-market assertions
    assert_market_data_correct,
    assert_currency_conversion_applied,
    
    # Recommendation assertions
    assert_valid_recommendations_response,
    assert_recommendations_relevant,
    
    # Utilities
    measure_response_time,
    format_performance_report,
)

__all__ = [
    # Product assertions
    "assert_valid_product_response",
    "assert_valid_product_list_response",
    
    # Performance assertions
    "assert_performance_acceptable",
    "assert_cache_hit_performance",
    
    # Multi-market assertions
    "assert_market_data_correct",
    "assert_currency_conversion_applied",
    
    # Recommendation assertions
    "assert_valid_recommendations_response",
    "assert_recommendations_relevant",
    
    # Utilities
    "measure_response_time",
    "format_performance_report",
]