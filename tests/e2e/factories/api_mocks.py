"""
API Mock Factories for E2E Testing
==================================

This module provides mock factories for external APIs used in the system:
- Claude/Anthropic API (conversational AI)
- Google Cloud Retail API (collaborative filtering)
- Shopify API (product catalog)

These mocks ensure predictable, fast, and isolated E2E tests without
depending on external services or consuming API quotas.

Usage:
    from tests.e2e.factories.api_mocks import (
        ClaudeAPIMockFactory,
        RetailAPIMockFactory,
        ShopifyAPIMockFactory,
        create_test_product_catalog
    )

Author: Senior Architecture Team
Date: Diciembre 2025
Version: 1.0.0 - Fase 3B
"""

import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import uuid4


# ==============================================================================
# CLAUDE/ANTHROPIC API MOCK FACTORY
# ==============================================================================

class ClaudeAPIMockFactory:
    """
    Factory for creating mock Claude/Anthropic API responses.
    
    Provides realistic conversational AI responses for testing
    recommendation flows without actual API calls.
    """
    
    @staticmethod
    def create_conversation_response(
        message: str,
        recommendations: Optional[List[Dict[str, Any]]] = None,
        conversation_id: Optional[str] = None,
        include_reasoning: bool = True
    ) -> Dict[str, Any]:
        """
        Create a mock Claude conversation response.
        
        Args:
            message: The user's message
            recommendations: List of product recommendations to include
            conversation_id: Conversation ID (generates if None)
            include_reasoning: Whether to include AI reasoning
            
        Returns:
            Mock Claude API response structure
        """
        if recommendations is None:
            recommendations = []
        
        if conversation_id is None:
            conversation_id = f"conv_{uuid4().hex[:16]}"
        
        # Build response content
        response_text = f"Based on your interest in '{message}', "
        
        if recommendations:
            response_text += f"I found {len(recommendations)} great options for you:\n\n"
            for i, rec in enumerate(recommendations, 1):
                response_text += f"{i}. {rec.get('title', 'Product')} "
                if 'price' in rec:
                    response_text += f"(${rec['price']:.2f})"
                response_text += "\n"
        else:
            response_text += "let me help you find the perfect items."
        
        # Add reasoning if requested
        reasoning = ""
        if include_reasoning:
            reasoning = (
                "I considered your preferences, browsing history, "
                "and current trends to curate these recommendations."
            )
        
        return {
            "id": f"msg_{uuid4().hex[:16]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": response_text
                }
            ],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": len(message.split()) * 4,  # Rough estimate
                "output_tokens": len(response_text.split()) * 4
            },
            "metadata": {
                "conversation_id": conversation_id,
                "recommendations_count": len(recommendations),
                "reasoning": reasoning
            }
        }
    
    @staticmethod
    def create_error_response(
        error_type: str = "rate_limit",
        error_message: str = "Rate limit exceeded"
    ) -> Dict[str, Any]:
        """
        Create a mock Claude API error response.
        
        Args:
            error_type: Type of error (rate_limit, authentication, etc.)
            error_message: Error message
            
        Returns:
            Mock error response
        """
        return {
            "type": "error",
            "error": {
                "type": error_type,
                "message": error_message
            }
        }
    
    @staticmethod
    def create_streaming_chunk(
        text: str,
        index: int = 0,
        is_final: bool = False
    ) -> Dict[str, Any]:
        """
        Create a mock streaming response chunk.
        
        Args:
            text: Text content for this chunk
            index: Chunk index
            is_final: Whether this is the final chunk
            
        Returns:
            Mock streaming chunk
        """
        return {
            "type": "content_block_delta",
            "index": index,
            "delta": {
                "type": "text_delta",
                "text": text
            },
            "is_final": is_final
        }


# ==============================================================================
# GOOGLE CLOUD RETAIL API MOCK FACTORY
# ==============================================================================

class RetailAPIMockFactory:
    """
    Factory for creating mock Google Cloud Retail API responses.
    
    Provides collaborative filtering recommendations without actual
    Google Cloud API calls.
    """
    
    @staticmethod
    def create_predict_response(
        user_id: str,
        n_recommendations: int = 5,
        page_categories: Optional[List[str]] = None,
        filter_string: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a mock Retail API prediction response.
        
        Args:
            user_id: User identifier
            n_recommendations: Number of recommendations to generate
            page_categories: Product categories to focus on
            filter_string: Filter to apply
            
        Returns:
            Mock prediction response
        """
        if page_categories is None:
            page_categories = ["shoes", "clothing", "accessories"]
        
        # Generate mock product recommendations
        results = []
        for i in range(n_recommendations):
            product_id = f"prod_{uuid4().hex[:12]}"
            results.append({
                "id": product_id,
                "product": {
                    "id": product_id,
                    "title": f"Recommended Product {i+1}",
                    "categories": [random.choice(page_categories)],
                    "priceInfo": {
                        "price": round(random.uniform(19.99, 299.99), 2),
                        "currencyCode": "USD"
                    },
                    "availability": "IN_STOCK",
                    "uri": f"https://example.com/products/{product_id}"
                },
                "matchingVariantFields": [],
                "metadata": {
                    "score": round(random.uniform(0.7, 0.99), 3),
                    "reason": "collaborative_filtering"
                }
            })
        
        return {
            "results": results,
            "attributionToken": f"token_{uuid4().hex[:32]}",
            "nextPageToken": f"page_{uuid4().hex[:16]}" if n_recommendations >= 10 else None,
            "metadata": {
                "user_id": user_id,
                "filter": filter_string,
                "page_categories": page_categories,
                "total_results": n_recommendations
            }
        }
    
    @staticmethod
    def create_user_event_response(
        event_type: str,
        product_id: str,
        user_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a mock user event write response.
        
        Args:
            event_type: Type of event (detail-page-view, add-to-cart, etc.)
            product_id: Product identifier
            user_id: User identifier
            session_id: Session identifier
            
        Returns:
            Mock event write response
        """
        if session_id is None:
            session_id = f"sess_{uuid4().hex[:16]}"
        
        return {
            "userEvent": {
                "eventType": event_type,
                "visitorId": user_id,
                "sessionId": session_id,
                "eventTime": datetime.now().isoformat() + "Z",
                "productDetails": [
                    {
                        "product": {
                            "id": product_id
                        },
                        "quantity": 1
                    }
                ],
                "attributionToken": f"token_{uuid4().hex[:32]}"
            },
            "status": "success",
            "message": "Event recorded successfully"
        }
    
    @staticmethod
    def create_product_import_response(
        products_count: int,
        success: bool = True
    ) -> Dict[str, Any]:
        """
        Create a mock product import response.
        
        Args:
            products_count: Number of products imported
            success: Whether import was successful
            
        Returns:
            Mock import response
        """
        return {
            "name": f"operations/{uuid4().hex}",
            "metadata": {
                "createTime": datetime.now().isoformat() + "Z",
                "updateTime": (datetime.now() + timedelta(seconds=30)).isoformat() + "Z",
                "successCount": products_count if success else 0,
                "failureCount": 0 if success else products_count,
                "requestId": f"req_{uuid4().hex[:16]}"
            },
            "done": True,
            "response": {
                "successCount": products_count if success else 0,
                "failureCount": 0 if success else products_count
            }
        }


# ==============================================================================
# SHOPIFY API MOCK FACTORY
# ==============================================================================

class ShopifyAPIMockFactory:
    """
    Factory for creating mock Shopify API responses.
    
    Provides product catalog data without actual Shopify API calls.
    """
    
    @staticmethod
    def create_product_response(
        product_id: str,
        title: str = "Test Product",
        price: float = 99.99,
        category: str = "clothing",
        in_stock: bool = True,
        images: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a mock Shopify product response.
        
        Args:
            product_id: Product identifier
            title: Product title
            price: Product price
            category: Product category
            in_stock: Whether product is in stock
            images: List of image URLs
            
        Returns:
            Mock product response
        """
        if images is None:
            images = [f"https://example.com/images/{product_id}_1.jpg"]
        
        return {
            "product": {
                "id": product_id,
                "title": title,
                "body_html": f"<p>Description for {title}</p>",
                "vendor": "Test Vendor",
                "product_type": category,
                "created_at": (datetime.now() - timedelta(days=30)).isoformat(),
                "updated_at": datetime.now().isoformat(),
                "published_at": (datetime.now() - timedelta(days=30)).isoformat(),
                "status": "active",
                "tags": f"{category}, test, mock",
                "variants": [
                    {
                        "id": f"var_{uuid4().hex[:12]}",
                        "product_id": product_id,
                        "title": "Default Title",
                        "price": str(price),
                        "sku": f"SKU-{product_id[:8].upper()}",
                        "position": 1,
                        "inventory_policy": "deny",
                        "compare_at_price": str(price * 1.2),
                        "fulfillment_service": "manual",
                        "inventory_management": "shopify",
                        "option1": "Default Title",
                        "option2": None,
                        "option3": None,
                        "taxable": True,
                        "barcode": f"BAR{random.randint(100000, 999999)}",
                        "grams": 500,
                        "weight": 0.5,
                        "weight_unit": "kg",
                        "inventory_quantity": 100 if in_stock else 0,
                        "requires_shipping": True
                    }
                ],
                "options": [
                    {
                        "id": f"opt_{uuid4().hex[:12]}",
                        "product_id": product_id,
                        "name": "Title",
                        "position": 1,
                        "values": ["Default Title"]
                    }
                ],
                "images": [
                    {
                        "id": f"img_{uuid4().hex[:12]}",
                        "product_id": product_id,
                        "position": idx + 1,
                        "src": img,
                        "width": 1000,
                        "height": 1000
                    }
                    for idx, img in enumerate(images)
                ]
            }
        }
    
    @staticmethod
    def create_products_list_response(
        count: int = 10,
        page: int = 1,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Create a mock Shopify products list response.
        
        Args:
            count: Number of products to generate
            page: Page number
            limit: Products per page
            
        Returns:
            Mock products list response
        """
        products = []
        
        categories = ["shoes", "clothing", "accessories", "electronics", "home"]
        
        for i in range(count):
            product_id = f"prod_{uuid4().hex[:12]}"
            category = random.choice(categories)
            price = round(random.uniform(19.99, 299.99), 2)
            
            products.append(
                ShopifyAPIMockFactory.create_product_response(
                    product_id=product_id,
                    title=f"Product {i+1} - {category.title()}",
                    price=price,
                    category=category,
                    in_stock=random.choice([True, True, True, False])  # 75% in stock
                )["product"]
            )
        
        return {
            "products": products,
            "metadata": {
                "page": page,
                "limit": limit,
                "total_count": count,
                "has_next_page": count >= limit
            }
        }
    
    @staticmethod
    def create_inventory_response(
        product_id: str,
        variant_id: str,
        quantity: int = 100
    ) -> Dict[str, Any]:
        """
        Create a mock Shopify inventory level response.
        
        Args:
            product_id: Product identifier
            variant_id: Variant identifier
            quantity: Available quantity
            
        Returns:
            Mock inventory response
        """
        return {
            "inventory_level": {
                "inventory_item_id": f"inv_{uuid4().hex[:12]}",
                "location_id": f"loc_{uuid4().hex[:12]}",
                "available": quantity,
                "updated_at": datetime.now().isoformat()
            }
        }


# ==============================================================================
# TEST DATA GENERATORS
# ==============================================================================

def create_test_product_catalog(
    count: int = 50,
    seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Generate a realistic test product catalog.
    
    Creates a diverse set of products across multiple categories
    with realistic pricing, descriptions, and attributes.
    
    Args:
        count: Number of products to generate
        seed: Random seed for reproducibility
        
    Returns:
        List of product dictionaries
    """
    if seed is not None:
        random.seed(seed)
    
    products = []
    
    # Product templates
    templates = {
        "shoes": {
            "titles": ["Running Shoes", "Casual Sneakers", "Hiking Boots", "Sandals", "Dress Shoes"],
            "brands": ["Nike", "Adidas", "Puma", "New Balance", "Skechers"],
            "price_range": (39.99, 199.99)
        },
        "clothing": {
            "titles": ["T-Shirt", "Jeans", "Jacket", "Sweater", "Dress"],
            "brands": ["Levi's", "H&M", "Zara", "Gap", "Uniqlo"],
            "price_range": (19.99, 149.99)
        },
        "electronics": {
            "titles": ["Headphones", "Smartwatch", "Tablet", "Camera", "Speaker"],
            "brands": ["Apple", "Samsung", "Sony", "Bose", "Canon"],
            "price_range": (49.99, 999.99)
        },
        "accessories": {
            "titles": ["Watch", "Sunglasses", "Belt", "Hat", "Bag"],
            "brands": ["Ray-Ban", "Fossil", "Coach", "Gucci", "Prada"],
            "price_range": (29.99, 499.99)
        },
        "home": {
            "titles": ["Lamp", "Pillow", "Blanket", "Vase", "Mirror"],
            "brands": ["IKEA", "West Elm", "Crate & Barrel", "CB2", "Pottery Barn"],
            "price_range": (19.99, 299.99)
        }
    }
    
    for i in range(count):
        # Select random category
        category = random.choice(list(templates.keys()))
        template = templates[category]
        
        # Generate product
        product_id = f"prod_{uuid4().hex[:12]}"
        title_base = random.choice(template["titles"])
        brand = random.choice(template["brands"])
        price = round(random.uniform(*template["price_range"]), 2)
        
        product = {
            "id": product_id,
            "title": f"{brand} {title_base}",
            "description": f"High-quality {title_base.lower()} from {brand}. Perfect for everyday use.",
            "category": category,
            "brand": brand,
            "price": price,
            "currency": "USD",
            "in_stock": random.choice([True, True, True, False]),  # 75% in stock
            "stock_quantity": random.randint(0, 200) if random.choice([True, True, True, False]) else 0,
            "rating": round(random.uniform(3.5, 5.0), 1),
            "reviews_count": random.randint(10, 500),
            "images": [
                f"https://example.com/images/{product_id}_1.jpg",
                f"https://example.com/images/{product_id}_2.jpg"
            ],
            "tags": [category, brand.lower(), title_base.lower().replace(" ", "-")],
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": {
                "test_product": True,
                "catalog_index": i
            }
        }
        
        products.append(product)
    
    return products


def create_test_user_events(
    user_id: str,
    product_ids: List[str],
    event_count: int = 10
) -> List[Dict[str, Any]]:
    """
    Generate test user interaction events.
    
    Creates realistic user behavior patterns for testing
    recommendation algorithms.
    
    Args:
        user_id: User identifier
        product_ids: List of product IDs to interact with
        event_count: Number of events to generate
        
    Returns:
        List of user event dictionaries
    """
    events = []
    event_types = [
        "detail-page-view",
        "detail-page-view",  # More views
        "detail-page-view",
        "add-to-cart",
        "purchase"
    ]
    
    session_id = f"sess_{uuid4().hex[:16]}"
    
    for i in range(event_count):
        event = {
            "event_type": random.choice(event_types),
            "user_id": user_id,
            "session_id": session_id,
            "product_id": random.choice(product_ids),
            "timestamp": (datetime.now() - timedelta(minutes=event_count - i)).isoformat(),
            "metadata": {
                "source": "test_generator",
                "index": i
            }
        }
        events.append(event)
    
    return events


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def get_mock_api_key(service: str = "claude") -> str:
    """
    Get a mock API key for testing.
    
    Args:
        service: Service name (claude, google, shopify)
        
    Returns:
        Mock API key string
    """
    prefixes = {
        "claude": "sk-ant-test-",
        "google": "AIza",
        "shopify": "shpat_test_"
    }
    
    prefix = prefixes.get(service, "test_")
    return f"{prefix}{uuid4().hex[:32]}"


def simulate_api_latency(min_ms: int = 50, max_ms: int = 200) -> float:
    """
    Simulate API call latency for realistic testing.
    
    Args:
        min_ms: Minimum latency in milliseconds
        max_ms: Maximum latency in milliseconds
        
    Returns:
        Simulated latency in seconds
    """
    import time
    latency = random.uniform(min_ms, max_ms) / 1000
    time.sleep(latency)
    return latency


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    # Factories
    "ClaudeAPIMockFactory",
    "RetailAPIMockFactory",
    "ShopifyAPIMockFactory",
    
    # Generators
    "create_test_product_catalog",
    "create_test_user_events",
    
    # Utilities
    "get_mock_api_key",
    "simulate_api_latency"
]


# ==============================================================================
# NOTES:
# ==============================================================================
# - All mocks return realistic data structures matching actual APIs
# - Random data is generated for variety in tests
# - Use seed parameter for reproducible test data
# - Mocks are fast (no network calls) and reliable (no quota limits)
# - Compatible with all fixtures in conftest.py
# ==============================================================================