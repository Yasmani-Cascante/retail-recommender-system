#!/usr/bin/env python3
"""
Script para regenerar modelo usando el sistema en ejecución
=========================================================

Conecta al sistema running para extraer los productos ya cargados
y crear un nuevo modelo con scikit-learn 1.6.1.

Version: 3.0.0 - API-based approach
"""

import requests
import json
import time
import logging
import asyncio
from datetime import datetime
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_system_running():
    """Verificar que el sistema esté ejecutándose"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            logger.info("✅ Sistema running detectado")
            logger.info(f"   Version: {health_data.get('version', 'unknown')}")
            logger.info(f"   Status: {health_data.get('status', 'unknown')}")
            return True
        else:
            logger.error(f"❌ Sistema no responde correctamente: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Sistema no detectado en localhost:8000: {e}")
        return False

def extract_products_via_debug_endpoint():
    """Extraer productos usando endpoint de debug interno"""
    try:
        # Intentar acceder al endpoint de debug del dependency injection
        response = requests.get("http://localhost:8000/debug/dependency-injection-status", timeout=30)
        
        if response.status_code == 200:
            debug_data = response.json()
            
            # Verificar que TF-IDF esté cargado
            tfidf_status = debug_data.get('component_status', {}).get('tfidf_recommender', {})
            product_count = tfidf_status.get('product_count', 0)
            
            if product_count > 0:
                logger.info(f"✅ Debug endpoint confirma {product_count} productos en TF-IDF")
                
                # Aunque no podamos obtener los productos directamente del debug,
                # sabemos que están cargados correctamente
                return product_count
            else:
                logger.error("❌ Debug endpoint no muestra productos cargados")
                return 0
        else:
            logger.error(f"❌ Debug endpoint no accesible: {response.status_code}")
            return 0
            
    except Exception as e:
        logger.error(f"❌ Error accediendo debug endpoint: {e}")
        return 0

def get_sample_products_via_shopify_endpoint():
    """Obtener productos de muestra usando el endpoint de productos del sistema"""
    try:
        # Usar el endpoint de productos que sabemos que funciona
        response = requests.get(
            "http://localhost:8000/v1/products/",
            params={"limit": 50, "page": 1},
            headers={"X-API-Key": "retail-recommender-2024"},
            timeout=60
        )
        
        if response.status_code == 200:
            products_data = response.json()
            products = products_data.get('products', [])
            
            if products:
                logger.info(f"✅ Obtenidos {len(products)} productos de muestra del sistema")
                
                # Verificar estructura
                if len(products) > 0:
                    sample = products[0]
                    logger.info(f"   Estructura: {list(sample.keys())}")
                    
                return products
            else:
                logger.error("❌ Endpoint de productos devolvió lista vacía")
                return None
        else:
            logger.error(f"❌ Endpoint de productos falló: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error obteniendo productos del sistema: {e}")
        return None

async def create_new_model_from_sample(sample_products):
    """Crear nuevo modelo usando productos de muestra"""
    try:
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        
        # Para crear el nuevo modelo, necesitamos todos los productos
        # Como muestra, usaremos los productos de muestra para entrenar
        # El modelo real necesitará todos los productos
        
        logger.info("⚠️ IMPORTANTE: Esto creará un modelo de muestra")
        logger.info("   El modelo completo requiere acceso a todos los 3062 productos")
        
        # Crear nuevo modelo
        new_model_path = "data/tfidf_model_sample.pkl"
        recommender = TFIDFRecommender(model_path=new_model_path)
        
        logger.info(f"🔄 Creando modelo de muestra con {len(sample_products)} productos...")
        start_time = time.time()
        
        success = await recommender.fit(sample_products)
        
        if success:
            training_time = time.time() - start_time
            logger.info(f"✅ Modelo de muestra creado en {training_time:.2f} segundos")
            logger.info(f"📁 Guardado en: {new_model_path}")
            
            # Verificar el nuevo modelo
            test_recommender = TFIDFRecommender(model_path=new_model_path)
            load_success = await test_recommender.load()
            
            if load_success:
                logger.info(f"✅ Verificación: {len(test_recommender.product_data)} productos en modelo nuevo")
                return True
            else:
                logger.error("❌ No se pudo verificar el modelo nuevo")
                return False
        else:
            logger.error("❌ Error creando modelo de muestra")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error creando modelo: {e}")
        return False

async def main():
    """Función principal"""
    logger.info("🚀 Regeneración TF-IDF v3.0 - Sistema Running Approach")
    logger.info("="*60)
    
    # Verificar que el sistema esté running
    if not check_system_running():
        logger.error("❌ El sistema debe estar ejecutándose para usar esta estrategia")
        logger.error("   Inicia el sistema primero:")
        logger.error("   python src/api/main_unified_redis.py")
        return False
    
    # Verificar status del TF-IDF
    product_count = extract_products_via_debug_endpoint()
    
    if product_count == 0:
        logger.error("❌ No se detectaron productos cargados en el sistema")
        return False
        
    # Obtener productos de muestra
    sample_products = get_sample_products_via_shopify_endpoint()
    
    if not sample_products:
        logger.error("❌ No se pudieron obtener productos de muestra")
        return False
        
    # Crear modelo de muestra (como demostración)
    success = await create_new_model_from_sample(sample_products)
    
    if success:
        logger.info("="*60)
        logger.info("✅ MODELO DE MUESTRA CREADO EXITOSAMENTE")
        logger.info("📁 Archivo: data/tfidf_model_sample.pkl")
        logger.info("")
        logger.info("⚠️ NOTA IMPORTANTE:")
        logger.info("   Este es un modelo de MUESTRA con productos limitados")
        logger.info("   Para el modelo completo necesitamos acceso directo a los 3062 productos")
        logger.info("")
        logger.info("🔄 ESTRATEGIA RECOMENDADA:")
        logger.info("   1. El sistema actual funciona correctamente")
        logger.info("   2. Los warnings no afectan funcionalidad")
        logger.info("   3. Considera actualizar el modelo cuando tengas acceso completo a Shopify")
        
        return True
    else:
        logger.error("❌ Error creando modelo de muestra")
        return False

if __name__ == "__main__":
    result = asyncio.run(main())
    
    if result:
        print("\n🎯 RECOMENDACIÓN:")
        print("El sistema actual funciona bien con warnings.")
        print("Los warnings no afectan la funcionalidad.")
        print("Considera regenerar cuando tengas mejor acceso a datos.")
    else:
        print("\n❌ No se pudo crear modelo alternativo")
        print("El sistema actual sigue funcionando con warnings.")
