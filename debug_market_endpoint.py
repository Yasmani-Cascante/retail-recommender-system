# debug_market_endpoint.py
"""
Endpoint de debug para verificar adaptación de mercado
Añadir temporalmente al router MCP
"""

@router.get("/v1/debug/market-test/{market_id}")
async def debug_market_adaptation(market_id: str):
    """Endpoint de debug para probar adaptación directamente"""
    
    # Producto de prueba
    test_product = {
        "id": "test123",
        "title": "Zapatos de Fiesta Elegantes",
        "description": "Zapatos elegantes para ocasiones especiales",
        "price": 59990.0,
        "currency": "COP",  # Originalmente en COP
        "score": 0.8
    }
    
    # Crear contexto de mercado
    market_context = {
        "market_id": market_id,
        "currency": {
            "US": "USD",
            "ES": "EUR",
            "MX": "MXN",
            "CO": "COP"
        }.get(market_id, "USD")
    }
    
    # Aplicar adaptación
    from src.api.mcp.utils.market_utils import market_adapter
    
    adapted_product = market_adapter.adapt_product_for_market(
        test_product.copy(),
        market_id
    )
    
    return {
        "market_id": market_id,
        "original_product": test_product,
        "adapted_product": adapted_product,
        "conversion_applied": adapted_product.get("price") != test_product["price"],
        "translation_applied": adapted_product.get("title") != test_product["title"]
    }
