#!/usr/bin/env python3
"""
Shopify Client Deep Investigation
================================

Investigación completa del shopify_client para encontrar o implementar
el método correcto para obtener productos individuales por ID.
"""

import sys
sys.path.append('src')

def investigate_shopify_client_deep():
    """Investigación profunda del shopify client"""
    
    print("🔍 DEEP SHOPIFY CLIENT INVESTIGATION")
    print("=" * 50)
    
    try:
        from src.api.core.store import get_shopify_client
        
        client = get_shopify_client()
        
        if not client:
            print("❌ Shopify client not available")
            return
        
        print("✅ Shopify client available")
        print(f"Client type: {type(client).__name__}")
        print(f"Client module: {type(client).__module__}")
        
        # 1. INVESTIGAR MÉTODOS DISPONIBLES
        print("\n📋 AVAILABLE METHODS:")
        print("-" * 30)
        
        all_methods = [attr for attr in dir(client) if not attr.startswith('_')]
        
        # Categorizar métodos
        product_methods = [m for m in all_methods if 'product' in m.lower()]
        get_methods = [m for m in all_methods if m.startswith('get')]
        fetch_methods = [m for m in all_methods if 'fetch' in m.lower()]
        
        print("Product-related methods:")
        for method in product_methods:
            print(f"  - {method}")
        
        print("\nGet methods:")
        for method in get_methods:
            print(f"  - {method}")
        
        print("\nFetch methods:")
        for method in fetch_methods:
            print(f"  - {method}")
        
        # 2. INVESTIGAR get_products EN DETALLE
        print("\n🔍 GET_PRODUCTS METHOD ANALYSIS:")
        print("-" * 40)
        
        if hasattr(client, 'get_products'):
            import inspect
            
            try:
                signature = inspect.signature(client.get_products)
                print(f"Signature: get_products{signature}")
                
                # Ver documentación si existe
                if client.get_products.__doc__:
                    print(f"Documentation: {client.get_products.__doc__}")
                
                # Analizar código fuente si es posible
                try:
                    source = inspect.getsource(client.get_products)
                    print("Source code preview:")
                    lines = source.split('\n')[:10]  # Primeras 10 líneas
                    for i, line in enumerate(lines):
                        print(f"  {i+1}: {line}")
                    if len(source.split('\n')) > 10:
                        print("  ... (truncated)")
                except:
                    print("Source code not available")
                    
            except Exception as e:
                print(f"Could not analyze get_products: {e}")
        
        # 3. INVESTIGAR PROPIEDADES DEL CLIENT
        print("\n🔧 CLIENT PROPERTIES:")
        print("-" * 25)
        
        properties = ['shop_url', 'api_url', 'base_url', 'endpoint', 'access_token']
        
        for prop in properties:
            if hasattr(client, prop):
                value = getattr(client, prop)
                if 'token' in prop.lower():
                    # Ocultar token por seguridad
                    value = str(value)[:8] + "..." if value else "None"
                print(f"  {prop}: {value}")
        
        # 4. CONSTRUIR URL PARA PRODUCTO INDIVIDUAL
        print("\n🌐 INDIVIDUAL PRODUCT URL CONSTRUCTION:")
        print("-" * 45)
        
        if hasattr(client, 'api_url') or hasattr(client, 'shop_url'):
            base_url = getattr(client, 'api_url', None) or getattr(client, 'shop_url', None)
            
            if base_url:
                # Construir URL para producto individual
                if '/admin/api/' in str(base_url):
                    individual_url = f"{str(base_url).rstrip('/')}/products/{{product_id}}.json"
                    print(f"Individual product URL pattern: {individual_url}")
                    
                    # URL de ejemplo
                    example_url = individual_url.replace('{product_id}', '9978689487157')
                    print(f"Example URL: {example_url}")
                else:
                    print(f"Base URL: {base_url}")
                    print("Could not determine individual product URL pattern")
        
        # 5. TEST SI PODEMOS HACER LLAMADA DIRECTA
        print("\n🧪 TESTING DIRECT API CALL CAPABILITY:")
        print("-" * 42)
        
        # Ver si el client tiene método para hacer requests HTTP
        http_methods = ['request', 'get', 'post', '_request', '_get', '_make_request']
        
        available_http_methods = []
        for method in http_methods:
            if hasattr(client, method):
                available_http_methods.append(method)
        
        if available_http_methods:
            print("Available HTTP methods:")
            for method in available_http_methods:
                print(f"  - {method}")
        else:
            print("No obvious HTTP methods found")
        
        # 6. BUSCAR MÉTODOS PARA PRODUCTO INDIVIDUAL
        print("\n🎯 SEARCHING FOR INDIVIDUAL PRODUCT METHODS:")
        print("-" * 48)
        
        # Posibles nombres para método individual
        individual_method_names = [
            'get_product', 'get_product_by_id', 'fetch_product', 
            'product_by_id', 'single_product', 'find_product',
            'retrieve_product', 'load_product'
        ]
        
        found_methods = []
        for method_name in individual_method_names:
            if hasattr(client, method_name):
                method = getattr(client, method_name)
                found_methods.append((method_name, method))
        
        if found_methods:
            print("✅ Found potential individual product methods:")
            for name, method in found_methods:
                try:
                    signature = inspect.signature(method)
                    print(f"  - {name}{signature}")
                except:
                    print(f"  - {name}()")
        else:
            print("❌ No individual product methods found")
        
        # 7. CONCLUSIONES Y RECOMENDACIONES
        print("\n📋 INVESTIGATION CONCLUSIONS:")
        print("-" * 35)
        
        if found_methods:
            print("✅ SOLUTION: Use existing individual product method")
            print(f"   Recommended: {found_methods[0][0]}()")
        elif available_http_methods:
            print("✅ SOLUTION: Implement direct API call using available HTTP method")
            print(f"   Use: {available_http_methods[0]}() with individual product URL")
        else:
            print("⚠️ SOLUTION: Implement custom HTTP request for individual product")
            print("   Need to create new method using requests library")
        
    except Exception as e:
        print(f"❌ Investigation failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    investigate_shopify_client_deep()
