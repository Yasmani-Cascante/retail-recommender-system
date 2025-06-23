# quick_status_check.py
"""
Verificación rápida del estado del sistema sin necesidad de levantar servidor completo.
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Configuración
load_dotenv()
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

async def check_recommender_status():
    """Verificar estado del recomendador TF-IDF"""
    print("🔍 Verificando TFIDFRecommender...")
    
    try:
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        
        recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")
        
        # Verificar si existe modelo pre-entrenado
        if os.path.exists("data/tfidf_model.pkl"):
            print("📁 Modelo pre-entrenado encontrado, intentando cargar...")
            loaded = await recommender.load()
            
            if loaded:
                print("✅ Modelo TF-IDF cargado desde archivo")
                health = await recommender.health_check()
                print(f"   Estado: {health}")
                return True
            else:
                print("❌ Error cargando modelo pre-entrenado")
        else:
            print("📁 No existe modelo pre-entrenado")
        
        # Intentar entrenar con datos de muestra
        print("🏗️ Entrenando con datos de muestra...")
        
        sample_products = [
            {"id": "prod1", "title": "Camiseta Azul", "body_html": "Camiseta de algodón azul", "product_type": "Ropa"},
            {"id": "prod2", "title": "Pantalón Negro", "body_html": "Pantalón negro elegante", "product_type": "Ropa"},
            {"id": "prod3", "title": "Zapatos Deportivos", "body_html": "Zapatos para correr", "product_type": "Calzado"}
        ]
        
        success = await recommender.fit(sample_products)
        
        if success:
            print("✅ Recomendador entrenado exitosamente con datos de muestra")
            health = await recommender.health_check()
            print(f"   Estado: {health}")
            return True
        else:
            print("❌ Error entrenando recomendador")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando recomendador: {e}")
        return False

async def check_shopify_connection():
    """Verificar conexión a Shopify"""
    print("\n🔍 Verificando conexión a Shopify...")
    
    try:
        from src.api.core.store import init_shopify
        
        client = init_shopify()
        
        if client:
            print("✅ Cliente Shopify inicializado")
            
            # Test básico de conexión
            try:
                products = client.get_products()
                print(f"✅ Conectado a Shopify - {len(products)} productos disponibles")
                return True
            except Exception as e:
                print(f"⚠️ Cliente inicializado pero error obteniendo productos: {e}")
                return False
        else:
            print("❌ No se pudo inicializar cliente Shopify")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando Shopify: {e}")
        return False

async def check_environment():
    """Verificar variables de entorno"""
    print("\n🔍 Verificando variables de entorno...")
    
    required_vars = {
        "REDIS_HOST": os.getenv("REDIS_HOST"),
        "REDIS_PORT": os.getenv("REDIS_PORT"),
        "REDIS_PASSWORD": os.getenv("REDIS_PASSWORD"),
        "SHOPIFY_SHOP_URL": os.getenv("SHOPIFY_SHOP_URL"),
        "SHOPIFY_ACCESS_TOKEN": os.getenv("SHOPIFY_ACCESS_TOKEN"),
        "API_KEY": os.getenv("API_KEY")
    }
    
    missing = []
    present = []
    
    for var, value in required_vars.items():
        if value:
            present.append(var)
        else:
            missing.append(var)
    
    for var in present:
        print(f"✅ {var}: Configurado")
    
    for var in missing:
        print(f"❌ {var}: Faltante")
    
    return len(missing) == 0

async def main():
    print("🚀 Verificación rápida del estado del sistema\n")
    
    # Verificaciones
    env_ok = await check_environment()
    shopify_ok = await check_shopify_connection()
    recommender_ok = await check_recommender_status()
    
    # Resumen
    print("\n" + "="*50)
    print("📊 RESUMEN DE VERIFICACIONES")
    print("="*50)
    
    results = [
        ("Variables de entorno", env_ok),
        ("Conexión Shopify", shopify_ok),
        ("TFIDFRecommender", recommender_ok)
    ]
    
    passed = 0
    for name, status in results:
        icon = "✅" if status else "❌"
        print(f"{icon} {name}")
        if status:
            passed += 1
    
    print(f"\n📈 Resultado: {passed}/{len(results)} verificaciones pasaron")
    
    if passed == len(results):
        print("\n🎉 ¡Sistema en buen estado!")
        print("🚀 Deberías poder ejecutar: python src/api/run.py")
    else:
        print("\n⚠️ Hay problemas que resolver antes de ejecutar el sistema")
        
        if not env_ok:
            print("   - Revisar variables de entorno en .env")
        if not shopify_ok:
            print("   - Verificar credenciales de Shopify")
        if not recommender_ok:
            print("   - Resolver problemas del recomendador TF-IDF")

if __name__ == "__main__":
    asyncio.run(main())
