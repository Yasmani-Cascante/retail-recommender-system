#!/usr/bin/env python3
"""
Prueba rápida para verificar que la API key funciona correctamente
"""

import requests
import json

def test_api_key():
    """Prueba la API key encontrada en el archivo .env"""
    
    # API key encontrada en .env
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    base_url = "http://localhost:8000"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    print("🔑 PRUEBA DE API KEY")
    print("=" * 40)
    print(f"🔗 URL: {base_url}")
    print(f"🔑 API Key: {api_key}")
    print()
    
    # 1. Probar endpoint básico (sin autenticación)
    print("1️⃣ Probando endpoint básico (sin auth)...")
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200:
            print("   ✅ Endpoint básico funciona")
        else:
            print(f"   ❌ Error en endpoint básico: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # 2. Probar health check (sin autenticación)
    print("\n2️⃣ Probando health check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            print("   ✅ Health check funciona")
        else:
            print(f"   ❌ Error en health check: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 3. Probar endpoint que requiere API key
    print("\n3️⃣ Probando endpoint con API key...")
    try:
        response = requests.get(f"{base_url}/v1/products", headers=headers, params={"page_size": 5}, timeout=10)
        
        print(f"   📡 Status code: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ API key VÁLIDA")
            data = response.json()
            total = data.get("total", 0)
            print(f"   📦 Productos disponibles: {total}")
            return True
            
        elif response.status_code == 403:
            print("   ❌ API key INVÁLIDA")
            try:
                error_data = response.json()
                print(f"   📋 Mensaje: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   📋 Respuesta: {response.text}")
            return False
            
        else:
            print(f"   ⚠️ Respuesta inesperada: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   📋 Mensaje: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   📋 Respuesta: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_recommendation_endpoint():
    """Prueba específica del endpoint de recomendaciones"""
    
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    base_url = "http://localhost:8000"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    print("\n4️⃣ Probando endpoint de recomendaciones...")
    
    # Primero obtener un producto de prueba
    try:
        response = requests.get(f"{base_url}/v1/products", headers=headers, params={"page_size": 1}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            products = data.get("products", [])
            
            if products:
                test_product_id = str(products[0].get("id"))
                product_title = products[0].get("title", "Sin título")
                
                print(f"   🎯 Producto de prueba: {test_product_id} - {product_title[:30]}...")
                
                # Probar recomendaciones SIN user_id
                print(f"\n   📋 Probando SIN user_id...")
                response = requests.get(
                    f"{base_url}/v1/recommendations/{test_product_id}",
                    headers=headers,
                    params={"n": 3},
                    timeout=15
                )
                
                if response.status_code == 200:
                    rec_data = response.json()
                    recommendations = rec_data.get("recommendations", [])
                    metadata = rec_data.get("metadata", {})
                    
                    print(f"      ✅ Éxito: {len(recommendations)} recomendaciones")
                    print(f"      🔧 Fuente: {metadata.get('source', 'unknown')}")
                    
                    rec_ids_without_user = [rec.get("id") for rec in recommendations]
                    
                else:
                    print(f"      ❌ Error: {response.status_code}")
                    return False
                
                # Probar recomendaciones CON user_id
                print(f"\n   👤 Probando CON user_id...")
                headers_with_user = headers.copy()
                headers_with_user["user-id"] = "test_user_123"
                
                response = requests.get(
                    f"{base_url}/v1/recommendations/{test_product_id}",
                    headers=headers_with_user,
                    params={"n": 3},
                    timeout=15
                )
                
                if response.status_code == 200:
                    rec_data = response.json()
                    recommendations = rec_data.get("recommendations", [])
                    metadata = rec_data.get("metadata", {})
                    
                    print(f"      ✅ Éxito: {len(recommendations)} recomendaciones")
                    print(f"      🔧 Fuente: {metadata.get('source', 'unknown')}")
                    
                    rec_ids_with_user = [rec.get("id") for rec in recommendations]
                    
                    # Comparar resultados
                    print(f"\n   🔍 COMPARACIÓN:")
                    print(f"      Sin usuario: {rec_ids_without_user}")
                    print(f"      Con usuario: {rec_ids_with_user}")
                    
                    if rec_ids_without_user == rec_ids_with_user:
                        print(f"      ⚠️ PROBLEMA: Recomendaciones IDÉNTICAS")
                        print(f"      💡 No hay personalización detectada")
                    else:
                        print(f"      ✅ CORRECTO: Recomendaciones DIFERENTES")
                        print(f"      🎉 Personalización funcionando")
                    
                    return True
                    
                else:
                    print(f"      ❌ Error con user_id: {response.status_code}")
                    return False
                    
            else:
                print(f"   ⚠️ No hay productos disponibles para probar")
                return False
                
        else:
            print(f"   ❌ Error obteniendo productos: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    """Función principal"""
    
    success = test_api_key()
    
    if success:
        test_recommendation_endpoint()
        print(f"\n✅ PRUEBA COMPLETADA")
        print(f"💡 Si detectaste problemas de personalización, ejecuta:")
        print(f"   python recommendation_diagnostic.py")
    else:
        print(f"\n❌ PRUEBA FALLIDA")
        print(f"💡 Verifica que el servidor esté ejecutándose")
        print(f"💡 Comando: python src/api/run.py")

if __name__ == "__main__":
    main()