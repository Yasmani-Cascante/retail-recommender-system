"""
E2E Test Fixtures Module
========================

Provides static test data (JSON fixtures) for E2E tests.
"""

import json
from pathlib import Path
from typing import Dict, List, Any

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent


def load_fixture(filename: str) -> Dict[str, Any]:
    """
    Load a JSON fixture file.
    
    Args:
        filename: Name of the fixture file (e.g., 'products.json')
        
    Returns:
        Parsed JSON data as dictionary
        
    Example:
        from tests.e2e.fixtures import load_fixture
        products_data = load_fixture('products.json')
        products = products_data['products']
    """
    filepath = FIXTURES_DIR / filename
    
    if not filepath.exists():
        raise FileNotFoundError(f"Fixture file not found: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_test_products() -> List[Dict[str, Any]]:
    """
    Get list of test products from fixtures.
    
    Returns:
        List of product dictionaries
    """
    data = load_fixture('products.json')
    return data['products']


def get_test_product_by_id(product_id: str) -> Dict[str, Any]:
    """
    Get a specific test product by ID.
    
    Args:
        product_id: Product ID to search for
        
    Returns:
        Product dictionary
        
    Raises:
        ValueError: If product ID not found
    """
    products = get_test_products()
    
    for product in products:
        if product['id'] == product_id:
            return product
    
    raise ValueError(f"Test product with ID '{product_id}' not found")


def get_test_products_by_market(market: str) -> List[Dict[str, Any]]:
    """
    Get test products filtered by market.
    
    Args:
        market: Market code (US, MX, ES, CL)
        
    Returns:
        List of products for that market
    """
    products = get_test_products()
    return [p for p in products if p.get('market') == market]


def get_test_products_by_category(category: str) -> List[Dict[str, Any]]:
    """
    Get test products filtered by category.
    
    Args:
        category: Category name (e.g., 'Clothing', 'Electronics')
        
    Returns:
        List of products in that category
    """
    products = get_test_products()
    return [p for p in products if p.get('category') == category]


__all__ = [
    'load_fixture',
    'get_test_products',
    'get_test_product_by_id',
    'get_test_products_by_market',
    'get_test_products_by_category',
]