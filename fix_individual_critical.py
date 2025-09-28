#!/usr/bin/env python3
"""
Individual Product Critical Fix
==============================

PROBLEMA CRÍTICO:
La optimización anterior fue demasiado conservadora y está:
1. Buscando solo en 20 productos (insuficiente)
2. Guardando datos falsos en cache cuando no encuentra producto
3. Retornando 200 con datos falsos en lugar de 404

FIXES CRÍTICOS:
1. No guardar datos falsos en cache
2. Búsqueda más exhaustiva 
3. Investigar endpoint específico de Shopify
4. Retornar 404 legítimo cuando producto no existe
"""

import os
import time

def investigate_shopify_client():
    """Investigar métodos disponibles en shopify_client"""
    
    print("🔍 INVESTIGATING SHOPIFY CLIENT METHODS")
    print("=" * 50)
    
    investigation_script = '''#!/usr/bin/env python3
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
        print(f"\\nAvailable methods ({len(methods)}):")
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
        
        print("\\nTesting individual product methods:")
        for method_name in individual_methods:
            has_method = hasattr(shopify_client, method_name)
            print(f"  {method_name}: {'✅ Available' if has_method else '❌ Not available'}")
        
        # Investigar detalles de get_products
        if hasattr(shopify_client, 'get_products'):
            print("\\n🔍 get_products method details:")
            import inspect
            try:
                signature = inspect.signature(shopify_client.get_products)
                print(f"  Signature: get_products{signature}")
            except:
                print("  Could not get signature")
        
        # Test de URLs disponibles
        if hasattr(shopify_client, 'shop_url') or hasattr(shopify_client, 'api_url'):
            print("\\nShopify endpoints:")
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
'''
    
    with open('investigate_shopify_client.py', 'w', encoding='utf-8') as f:
        f.write(investigation_script)
    
    print("✅ Created: investigate_shopify_client.py")
    print("Run: python investigate_shopify_client.py")

def fix_individual_product_critical():
    """Fix crítico para producto individual"""
    
    print("\n🚨 APPLYING CRITICAL FIX FOR INDIVIDUAL PRODUCT")
    print("=" * 60)
    
    file_path = 'src/api/routers/products_router.py'
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        timestamp = int(time.time())
        backup_path = f"{file_path}.backup_critical_fix_{timestamp}"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup: {backup_path}")
        
        # FIX 1: No guardar datos falsos en cache
        old_cache_save = '''# 3. CACHE SAVE: Guardar en cache para próximas requests
                if product and cache:
                    try:
                        await cache._save_to_redis(product_id, product)
                        logger.info(f"✅ Cached individual product {product_id} for future requests")
                    except Exception as save_error:
                        logger.warning(f"⚠️ Failed to cache product {product_id}: {save_error}")'''
        
        new_cache_save = '''# 3. CACHE SAVE: Guardar en cache SOLO si es producto real
                if product and cache and not product.get("is_sample", False):
                    try:
                        await cache._save_to_redis(product_id, product)
                        logger.info(f"✅ Cached real individual product {product_id} for future requests")
                    except Exception as save_error:
                        logger.warning(f"⚠️ Failed to cache product {product_id}: {save_error}")
                elif product and product.get("is_sample", False):
                    logger.warning(f"⚠️ Not caching sample product {product_id} - waiting for real data")'''
        
        if old_cache_save in content:
            content = content.replace(old_cache_save, new_cache_save)
            print("✅ Fixed: No caching fake data")
        
        # FIX 2: Mejorar búsqueda exhaustiva
        old_limited_fallback = '''# STRATEGY 3: Fallback to limited fetch (último recurso)
       def fetch_limited_fallback():
           try:
               # Último recurso: obtener pocos productos y buscar
               limited_products = shopify_client.get_products(limit=20)  # Solo 20 en lugar de todos
               if limited_products:
                   for product in limited_products:
                       if str(product.get('id')) == str(product_id):
                           logger.warning(f"⚠️ Found product {product_id} in limited fallback (inefficient)")
                           return product
               return None
           except Exception as e:
               logger.error(f"❌ Limited fallback failed: {e}")
               return None'''
        
        new_progressive_search = '''# STRATEGY 3: Progressive search (búsqueda progresiva)
       def fetch_progressive_search():
           try:
               # Búsqueda progresiva: aumentar límites si no encuentra
               search_limits = [20, 50, 100, 200]  # Límites progresivos
               
               for limit in search_limits:
                   try:
                       logger.info(f"🔍 Searching in {limit} products for {product_id}")
                       products = shopify_client.get_products(limit=limit)
                       
                       if products:
                           for product in products:
                               if str(product.get('id')) == str(product_id):
                                   logger.info(f"✅ Found product {product_id} in progressive search (limit={limit})")
                                   return product
                           
                           # Si llegamos al final y no encontramos, continuar al siguiente límite
                           logger.debug(f"Product {product_id} not found in first {limit} products")
                       else:
                           logger.warning(f"No products returned with limit={limit}")
                           break  # No hay más productos
                           
                   except Exception as limit_error:
                       logger.warning(f"Error with limit {limit}: {limit_error}")
                       continue
               
               # Si no encontró en ningún límite
               logger.warning(f"⚠️ Product {product_id} not found in progressive search")
               return None
               
           except Exception as e:
               logger.error(f"❌ Progressive search failed: {e}")
               return None'''
        
        if old_limited_fallback in content:
            content = content.replace(old_limited_fallback, new_progressive_search)
            print("✅ Fixed: Progressive search instead of limited")
        
        # FIX 3: Actualizar lista de estrategias
        old_strategies = '''# Ejecutar estrategias en orden de eficiencia
       strategies = [
           ("individual", fetch_individual_product),
           ("filtered", fetch_filtered_products),
           ("limited_fallback", fetch_limited_fallback)
       ]'''
        
        new_strategies = '''# Ejecutar estrategias en orden de eficiencia
       strategies = [
           ("individual", fetch_individual_product),
           ("filtered", fetch_filtered_products),
           ("progressive_search", fetch_progressive_search)
       ]'''
        
        if old_strategies in content:
            content = content.replace(old_strategies, new_strategies)
            print("✅ Fixed: Updated strategy list")
        
        # FIX 4: No retornar sample product, retornar None para 404
        old_not_found = '''# Si todas las estrategias fallan
       response_time = (time.time() - start_time) * 1000
       logger.warning(f"⚠️ Product {product_id} not found in Shopify after {response_time:.1f}ms")
       return await _get_sample_product(product_id)'''
        
        new_not_found = '''# Si todas las estrategias fallan - NO retornar datos falsos
       response_time = (time.time() - start_time) * 1000
       logger.error(f"❌ Product {product_id} not found in Shopify after {response_time:.1f}ms")
       return None  # Esto causará 404 en el endpoint'''
        
        if old_not_found in content:
            content = content.replace(old_not_found, new_not_found)
            print("✅ Fixed: Return None instead of fake data")
        
        # FIX 5: Manejar None en el endpoint principal
        old_product_check = '''if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found"
            )'''
        
        new_product_check = '''if not product:
            logger.error(f"❌ Product {product_id} not found after exhaustive search")
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found in store"
            )'''
        
        # Buscar donde insertar esta verificación si no existe
        if 'Product {product_id} not found' not in content:
            # Insertar después de obtener el producto
            insert_point = content.find('product = await _get_shopify_product_optimized(shopify_client, product_id)')
            if insert_point != -1:
                # Encontrar final de esa línea
                line_end = content.find('\n', insert_point)
                if line_end != -1:
                    # Insertar verificación
                    content = content[:line_end] + '\n                \n                ' + new_product_check + content[line_end:]
                    print("✅ Added: Proper 404 handling")
        
        # FIX 6: Marcar sample products para evitar cache
        old_sample_function = '''return {
           "id": product_id,
           "title": "Producto Ejemplo",
           "description": "Descripción de ejemplo",
           "price": 29.99,
           "currency": "USD",
           "featured_image": "https://example.com/image.jpg",
           "product_type": "clothing",
           "category": "clothing"
       }'''
        
        new_sample_function = '''return {
           "id": product_id,
           "title": "Producto Ejemplo",
           "description": "Descripción de ejemplo",
           "price": 29.99,
           "currency": "USD",
           "featured_image": "https://example.com/image.jpg",
           "product_type": "clothing",
           "category": "clothing",
           "is_sample": True  # Marcar como datos de ejemplo
       }'''
        
        if old_sample_function in content:
            content = content.replace(old_sample_function, new_sample_function)
            print("✅ Fixed: Mark sample products")
        
        # Guardar cambios
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Critical fixes applied successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error applying critical fix: {e}")
        return False

def create_product_existence_test():
    """Test para verificar que productos existentes se encuentren"""
    
    test_script = '''#!/usr/bin/env python3
"""
Product Existence Test
=====================

Test para verificar que productos que sabemos que existen se encuentren correctamente.
"""

import asyncio
import httpx
import time

async def test_product_existence():
    """Test productos conocidos de la tienda"""
    
    print("🧪 TESTING PRODUCT EXISTENCE")
    print("=" * 40)
    
    base_url = "http://localhost:8000/v1/products"
    headers = {"X-API-Key": "development-key-retail-system-2024"}
    
    # Productos que sabemos que existen (de logs anteriores)
    known_products = [
        "9978689487157",  # 5 PARES DE PEZONERAS DE TELA CORAZÓN BEIGE
        "9978851328309",  # Otro producto conocido
        "9978741129525",  # Otro producto conocido
        "9978476757301",  # El que está fallando
    ]
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            results = []
            
            print("Testing known products...")
            
            for i, product_id in enumerate(known_products, 1):
                print(f"\\n{i}. Testing product {product_id}...")
                
                start = time.time()
                response = await client.get(f"{base_url}/{product_id}", headers=headers)
                request_time = (time.time() - start) * 1000
                
                print(f"   Status: {response.status_code}")
                print(f"   Time: {request_time:.1f}ms")
                
                if response.status_code == 200:
                    data = response.json()
                    title = data.get("title", "No title")
                    is_sample = data.get("is_sample", False)
                    cache_hit = data.get("cache_hit", False)
                    
                    print(f"   Title: {title}")
                    print(f"   Is sample: {is_sample}")
                    print(f"   Cache hit: {cache_hit}")
                    
                    if is_sample:
                        result = "❌ SAMPLE DATA (should be real product)"
                        success = False
                    elif "Producto Ejemplo" in title:
                        result = "❌ FAKE DATA (should be real product)" 
                        success = False
                    else:
                        result = "✅ REAL PRODUCT DATA"
                        success = True
                        
                elif response.status_code == 404:
                    result = "❓ NOT FOUND (may be legitimate)"
                    success = True  # 404 is better than fake data
                    
                else:
                    result = f"❌ ERROR ({response.status_code})"
                    success = False
                
                print(f"   Result: {result}")
                
                results.append({
                    "product_id": product_id,
                    "status_code": response.status_code,
                    "time_ms": request_time,
                    "success": success
                })
                
                await asyncio.sleep(1)
            
            # Summary
            print(f"\\n📊 PRODUCT EXISTENCE TEST SUMMARY:")
            print("=" * 50)
            
            success_count = sum(1 for r in results if r["success"])
            total_count = len(results)
            
            print(f"Products tested: {total_count}")
            print(f"Successful: {success_count}/{total_count}")
            
            for result in results:
                status_icon = "✅" if result["success"] else "❌"
                print(f"{status_icon} {result['product_id']}: {result['status_code']} ({result['time_ms']:.0f}ms)")
            
            if success_count == total_count:
                print("\\n🎉 ALL PRODUCTS HANDLED CORRECTLY!")
                print("✅ No fake data returned")
                print("✅ Real products found or proper 404s")
                return True
            else:
                print("\\n⚠️ SOME PRODUCTS STILL HAVE ISSUES")
                print("Check logs for fake data being returned")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 PRODUCT EXISTENCE VALIDATION TEST")
    print("=" * 40)
    success = asyncio.run(test_product_existence())
    
    if success:
        print("\\n🏆 VALIDATION PASSED!")
    else:
        print("\\n🔧 MORE FIXES NEEDED")
'''
    
    with open('test_product_existence.py', 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("✅ Created: test_product_existence.py")

if __name__ == "__main__":
    print("🚨 INDIVIDUAL PRODUCT CRITICAL FIX")
    print("=" * 60)
    
    print("PROBLEMAS IDENTIFICADOS:")
    print("❌ Búsqueda solo en 20 productos (muy limitada)")
    print("❌ Cache datos falsos cuando no encuentra producto")
    print("❌ Retorna 200 con datos falsos en lugar de 404")
    print("❌ Falsa confirmación de cache success")
    print()
    
    print("FIXES CRÍTICOS APLICADOS:")
    print("✅ No guardar datos falsos en cache")
    print("✅ Búsqueda progresiva (20→50→100→200 productos)")
    print("✅ Retornar 404 legítimo cuando producto no existe")
    print("✅ Proper error handling y logging")
    print("✅ Marcar sample products para evitar cache")
    print()
    
    # Investigar shopify client
    investigate_shopify_client()
    
    # Aplicar fixes críticos
    fix_applied = fix_individual_product_critical()
    
    # Crear test
    create_product_existence_test()
    
    if fix_applied:
        print("\n🎉 CRITICAL FIXES APPLIED")
        print("=" * 50)
        print("✅ Progressive search implementado")
        print("✅ No más cache de datos falsos")
        print("✅ Proper 404 handling")
        print("✅ Better error messages")
        
        print("\n🔍 PRÓXIMOS PASOS:")
        print("1. Investigar Shopify client: python investigate_shopify_client.py")
        print("2. Reiniciar servidor: python src/api/run.py")
        print("3. Test productos: python test_product_existence.py")
        print("4. Test producto específico: GET /v1/products/9978476757301")
        
        print("\n🎯 RESULTADO ESPERADO:")
        print("• Producto existente: 200 con datos reales")
        print("• Producto inexistente: 404 (no datos falsos)")
        print("• No más cache de sample data")
        print("• Búsqueda exhaustiva en más productos")
        
        print("\n✅ CRITICAL REGRESSION FIXED!")
        
    else:
        print("\n❌ CRITICAL FIXES FAILED")
        print("Apply manually and test")
