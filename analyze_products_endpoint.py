#!/usr/bin/env python3
"""
Products Router Endpoint Analyzer
=================================

Busca y analiza el endpoint específico de productos para identificar
el problema del timeout con Shopify.
"""

def find_products_endpoint():
    """Encuentra el endpoint específico de productos"""
    
    file_path = 'src/api/routers/products_router.py'
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        print("🔍 ANALIZANDO ENDPOINT DE PRODUCTOS")
        print("=" * 50)
        
        # Buscar el endpoint GET
        for i, line in enumerate(lines):
            if '@router.get' in line and ('products' in line or '/v1/' in line):
                print(f"📍 ENDPOINT ENCONTRADO en línea {i+1}:")
                print()
                
                # Mostrar el endpoint completo
                start = max(0, i - 2)
                end = min(len(lines), i + 80)
                
                for j in range(start, end):
                    print(f"{j+1:4d}: {lines[j]}")
                    
                    # Parar en el siguiente endpoint
                    if j > i + 10 and ('@router.' in lines[j] or ('async def ' in lines[j] and not lines[j].startswith('    '))):
                        break
                
                print("\n" + "="*50)
                return True
        
        print("❌ No se encontró endpoint GET /products/")
        
        # Buscar cualquier función relacionada con productos
        print("\n🔍 FUNCIONES RELACIONADAS CON PRODUCTOS:")
        for i, line in enumerate(lines):
            if 'def ' in line and 'product' in line.lower():
                print(f"{i+1}: {line.strip()}")
        
        return False
        
    except Exception as e:
        print(f"❌ Error leyendo archivo: {e}")
        return False

def analyze_shopify_client():
    """Analiza la configuración del cliente Shopify"""
    
    print("\n🔍 ANALIZANDO CONFIGURACIÓN SHOPIFY CLIENT")
    print("=" * 50)
    
    try:
        # Verificar store.py
        store_path = 'src/api/core/store.py'
        with open(store_path, 'r', encoding='utf-8') as f:
            store_content = f.read()
        
        print("📁 src/api/core/store.py:")
        lines = store_content.split('\n')
        
        for i, line in enumerate(lines):
            if 'timeout' in line.lower() or 'shopify' in line.lower():
                print(f"{i+1}: {line.strip()}")
        
        print("\n" + "="*30)
        
        # Buscar configuraciones de timeout
        for i, line in enumerate(lines):
            if 'def get_shopify_client' in line:
                start = i
                end = min(len(lines), i + 30)
                
                print(f"📍 FUNCIÓN get_shopify_client (línea {i+1}):")
                for j in range(start, end):
                    print(f"{j+1:4d}: {lines[j]}")
                    if 'return' in lines[j] and j > start + 5:
                        break
                break
        
    except Exception as e:
        print(f"❌ Error analizando store.py: {e}")

def check_timeout_configuration():
    """Verifica configuraciones de timeout en el sistema"""
    
    print("\n🔍 VERIFICANDO CONFIGURACIONES DE TIMEOUT")
    print("=" * 50)
    
    # Archivos a verificar
    files_to_check = [
        'src/api/core/store.py',
        'src/api/routers/products_router.py',
        '.env'
    ]
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"\n📁 {file_path}:")
            lines = content.split('\n')
            
            timeout_lines = []
            for i, line in enumerate(lines):
                if any(keyword in line.lower() for keyword in ['timeout', 'retry', 'limit', 'delay']):
                    timeout_lines.append((i+1, line.strip()))
            
            if timeout_lines:
                for line_num, line_content in timeout_lines[:10]:  # Solo primeras 10
                    print(f"  {line_num}: {line_content}")
            else:
                print("  ℹ️ No se encontraron configuraciones de timeout")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 ANÁLISIS DEL PROBLEMA SHOPIFY TIMEOUT")
    print("=" * 60)
    
    # Paso 1: Encontrar endpoint
    endpoint_found = find_products_endpoint()
    
    # Paso 2: Analizar cliente Shopify
    analyze_shopify_client()
    
    # Paso 3: Verificar configuraciones
    check_timeout_configuration()
    
    print("\n📊 PRÓXIMOS PASOS:")
    print("1. Revisar lógica del endpoint encontrado")
    print("2. Verificar timeouts de Shopify client")
    print("3. Analizar condiciones de fallback")
    print("4. Verificar rate limiting y circuit breaker")
