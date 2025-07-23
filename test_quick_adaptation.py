"""
Test rápido de adaptación de mercado
"""

import asyncio
from src.core.market.adapter import get_market_adapter

async def test_quick():
    adapter = get_market_adapter()
    
    # Producto de prueba
    test_product = {
        "id": "123",
        "title": "Aros de oro",
        "price": 59990,
        "currency": "COP",
        "description": "Hermosos aros de oro"
    }
    
    print("🧪 TEST RÁPIDO DE ADAPTACIÓN")
    print("=" * 40)
    
    # Probar con mercado US
    us_product = await adapter.adapt_product(test_product.copy(), "US")
    print(f"\nMercado US:")
    print(f"  Precio: ${us_product['price']} {us_product['currency']}")
    print(f"  Título: {us_product.get('title')}")
    print(f"  Adaptado: {us_product.get('market_adapted', False)}")
    
    # Probar con mercado default
    default_product = await adapter.adapt_product(test_product.copy(), "default")
    print(f"\nMercado default:")
    print(f"  Precio: ${default_product['price']} {default_product['currency']}")
    print(f"  Título: {default_product.get('title')}")
    print(f"  Adaptado: {default_product.get('market_adapted', False)}")

if __name__ == "__main__":
    asyncio.run(test_quick())
