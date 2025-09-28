#!/usr/bin/env python3
"""
Shopify Client Investigation
===========================

Script para investigar qué métodos tiene disponible el shopify_client.
"""

import sys
sys.path.append('src')

try:
    from src.api.core.store import get_shopify_client
    
    print("🔍 INVESTIGATING SHOPIFY CLIENT")
    print("=" * 40)
    
    shopify_client = get_shopify_client()
    
    if shopify_client:
        print("✅ Shopify client available")
        
        # Investigar métodos
        methods = [attr for attr in dir(shopify_client) if not attr.startswith('_')]
        print(f"\nAvailable methods ({len(methods)}):")
        for method in sorted(methods):
            print(f"  - {method}")
        
        # Test específicos para productos individuales
        individual_methods = [
            'get_product',
            'get_product_by_id', 
            'fetch_product',
            'product_by_id',
            'single_product'
        ]
        
        print("\nTesting individual product methods:")
        for method_name in individual_methods:
            has_method = hasattr(shopify_client, method_name)
            print(f"  {method_name}: {'✅ Available' if has_method else '❌ Not available'}")
        
        # Investigar detalles de get_products
        if hasattr(shopify_client, 'get_products'):
            print("\n🔍 get_products method details:")
            import inspect
            try:
                signature = inspect.signature(shopify_client.get_products)
                print(f"  Signature: get_products{signature}")
            except:
                print("  Could not get signature")
        
        # Test de URLs disponibles
        if hasattr(shopify_client, 'shop_url') or hasattr(shopify_client, 'api_url'):
            print("\nShopify endpoints:")
            shop_url = getattr(shopify_client, 'shop_url', 'unknown')
            api_url = getattr(shopify_client, 'api_url', 'unknown')
            print(f"  Shop URL: {shop_url}")
            print(f"  API URL: {api_url}")
            
            # Construir URL para producto individual
            if 'admin/api' in str(api_url):
                individual_url = f"{api_url.rstrip('/')}/products/{{product_id}}.json"
                print(f"  Individual product URL pattern: {individual_url}")
        
    else:
        print("❌ Shopify client not available")
        
except Exception as e:
    print(f"❌ Investigation failed: {e}")
    import traceback
    print(traceback.format_exc())
