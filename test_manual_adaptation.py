# test_manual_adaptation.py
"""
Test manual para verificar que la adaptación funciona
"""

import asyncio
import sys
import os

# Añadir el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.mcp.utils.market_utils import market_adapter

def test_market_adapter():
    """Prueba directa del adaptador"""
    print("🧪 TEST DIRECTO DEL ADAPTADOR")
    print("="*60)
    
    # Producto de prueba (como viene del sistema)
    test_product = {
        "id": "123",
        "title": "AROS MAXI ARGOLLAS LUCIANA DORADO",
        "price": 12990.0,
        "currency": "USD",  # Incorrectamente marcado
        "description": "Aros de acero, antialérgicos",
        "score": 0.8
    }
    
    print("Producto original:")
    print(f"  Título: {test_product['title']}")
    print(f"  Precio: {test_product['price']} {test_product['currency']}")
    
    print("\nAdaptaciones por mercado:")
    print("-"*40)
    
    for market_id in ["US", "ES", "MX", "CO"]:
        adapted = market_adapter.adapt_product_for_market(
            test_product.copy(), 
            market_id
        )
        
        print(f"\nMercado {market_id}:")
        print(f"  Título: {adapted.get('title')}")
        print(f"  Precio: {adapted.get('price')} {adapted.get('currency')}")
        
        if adapted.get('original_price'):
            print(f"  Original: {adapted.get('original_price')} {adapted.get('original_currency')}")
        
        if adapted.get('original_title'):
            print(f"  Título Original: {adapted.get('original_title')}")
        
        print(f"  Adaptado: {adapted.get('market_adapted', False)}")

if __name__ == "__main__":
    test_market_adapter()
