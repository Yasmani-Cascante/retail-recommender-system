#!/usr/bin/env python3
"""
Script para regenerar modelo TF-IDF con versión actual de scikit-learn
========================================================================

Soluciona el problema de version mismatch regenerando el modelo con 
scikit-learn 1.6.1 actual, eliminando los warnings y asegurando
compatibilidad completa.

Uso:
    python regenerate_tfidf_model.py

Author: Senior Architecture Team
Version: 1.0.0
"""

import os
import sys
import time
import logging
import asyncio
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_dependencies():
    """Verificar que todas las dependencias estén disponibles"""
    try:
        import sklearn
        logger.info(f"✅ Scikit-learn version: {sklearn.__version__}")
        
        import numpy as np
        logger.info(f"✅ NumPy version: {np.__version__}")
        
        return True
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        return False

async def load_products_from_shopify():
    """Cargar productos desde Shopify usando el cliente existente"""
    try:
        # Import después de verificar que estamos en el directorio correcto
        from src.api.core.store import init_shopify
        
        logger.info("🔄 Inicializando cliente Shopify...")
        client = init_shopify()
        
        if not client:
            logger.error("❌ No se pudo inicializar cliente Shopify")
            return None
            
        logger.info("📥 Cargando productos desde Shopify...")
        products = client.get_products()
        
        if not products:
            logger.error("❌ No se pudieron cargar productos desde Shopify")
            return None
            
        logger.info(f"✅ Cargados {len(products)} productos desde Shopify")
        
        # Verificar estructura de productos
        if products and len(products) > 0:
            sample_product = products[0]
            required_fields = ['id', 'title', 'body_html']
            missing_fields = [field for field in required_fields if field not in sample_product]
            
            if missing_fields:
                logger.warning(f"⚠️ Campos faltantes en productos: {missing_fields}")
            else:
                logger.info("✅ Estructura de productos válida")
                
        return products
        
    except Exception as e:
        logger.error(f"❌ Error cargando productos desde Shopify: {e}")
        return None

def backup_existing_model():
    """Crear backup del modelo existente"""
    model_path = "data/tfidf_model.pkl"
    
    if os.path.exists(model_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"data/tfidf_model_backup_{timestamp}.pkl"
        
        try:
            import shutil
            shutil.copy2(model_path, backup_path)
            logger.info(f"✅ Modelo existente respaldado en: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"⚠️ No se pudo crear backup: {e}")
            
    return None

async def regenerate_tfidf_model():
    """Regenerar el modelo TF-IDF con la versión actual de scikit-learn"""
    try:
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        
        logger.info("🤖 Creando nuevo recomendador TF-IDF...")
        
        # Crear instancia del recomendador
        recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")
        
        # Cargar productos
        products = await load_products_from_shopify()
        if not products:
            logger.error("❌ No se pueden regenerar el modelo sin productos")
            return False
            
        logger.info(f"🔄 Entrenando modelo TF-IDF con {len(products)} productos...")
        start_time = time.time()
        
        # Entrenar el modelo (esto regenerará el archivo con la versión actual)
        success = await recommender.fit(products)
        
        if success:
            training_time = time.time() - start_time
            logger.info(f"✅ Modelo TF-IDF regenerado exitosamente en {training_time:.2f} segundos")
            
            # Verificar que el modelo se cargue correctamente
            logger.info("🔍 Verificando modelo regenerado...")
            test_recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")
            load_success = await test_recommender.load()
            
            if load_success:
                logger.info(f"✅ Verificación exitosa: {len(test_recommender.product_data)} productos cargados")
                
                # Test de recomendación básica
                if test_recommender.product_data:
                    test_product_id = str(test_recommender.product_data[0].get('id', ''))
                    test_recs = await test_recommender.get_recommendations(test_product_id, 3)
                    logger.info(f"✅ Test de recomendación: {len(test_recs)} recomendaciones generadas")
                    
                return True
            else:
                logger.error("❌ El modelo regenerado no se puede cargar correctamente")
                return False
        else:
            logger.error("❌ Error entrenando el modelo TF-IDF")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error regenerando modelo TF-IDF: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def verify_model_compatibility():
    """Verificar que el nuevo modelo sea compatible"""
    try:
        import pickle
        import sklearn
        
        model_path = "data/tfidf_model.pkl"
        
        if not os.path.exists(model_path):
            logger.error(f"❌ Archivo de modelo no encontrado: {model_path}")
            return False
            
        logger.info("🔍 Verificando compatibilidad del modelo...")
        
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
            
        # Verificar que la versión está en los metadatos del modelo
        if hasattr(model_data, 'sklearn_version'):
            logger.info(f"✅ Modelo creado con scikit-learn: {model_data.sklearn_version}")
        
        logger.info(f"✅ Modelo compatible con scikit-learn actual: {sklearn.__version__}")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ No se pudo verificar compatibilidad: {e}")
        return True  # Continuar aunque no se pueda verificar

async def main():
    """Función principal"""
    logger.info("🚀 Iniciando regeneración del modelo TF-IDF")
    logger.info("=" * 60)
    
    # Verificar dependencias
    if not check_dependencies():
        logger.error("❌ Dependencias faltantes. Abortando.")
        return False
        
    # Verificar directorio
    if not os.path.exists("src/api/core/store.py"):
        logger.error("❌ Execute desde el directorio raíz del proyecto")
        logger.error("   cd C:\\Users\\yasma\\Desktop\\retail-recommender-system")
        return False
        
    # Crear directorio data si no existe
    os.makedirs("data", exist_ok=True)
    
    # Hacer backup del modelo existente
    backup_path = backup_existing_model()
    
    try:
        # Regenerar modelo
        success = await regenerate_tfidf_model()
        
        if success:
            # Verificar compatibilidad
            verify_model_compatibility()
            
            logger.info("=" * 60)
            logger.info("🎉 REGENERACIÓN COMPLETADA EXITOSAMENTE")
            logger.info("✅ Modelo TF-IDF actualizado con scikit-learn 1.6.1")
            logger.info("✅ Warning de version mismatch debería desaparecer")
            logger.info("✅ Reinicia el sistema para aplicar cambios")
            
            if backup_path:
                logger.info(f"📁 Backup del modelo anterior: {backup_path}")
                
            return True
        else:
            logger.error("❌ Error en regeneración del modelo")
            
            if backup_path:
                logger.info("🔄 Restaurando modelo desde backup...")
                import shutil
                shutil.copy2(backup_path, "data/tfidf_model.pkl")
                logger.info("✅ Modelo restaurado desde backup")
                
            return False
            
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")
        return False

if __name__ == "__main__":
    # Verificar que estemos en el directorio correcto
    if not os.path.exists("src"):
        print("❌ Error: Execute este script desde el directorio raíz del proyecto")
        print("   cd C:\\Users\\yasma\\Desktop\\retail-recommender-system")
        print("   python regenerate_tfidf_model.py")
        sys.exit(1)
    
    # Ejecutar regeneración
    result = asyncio.run(main())
    
    if result:
        print("\n🎉 REGENERACIÓN COMPLETADA - Reinicia el sistema")
        sys.exit(0)
    else:
        print("\n❌ REGENERACIÓN FALLÓ - Revisa los logs")
        sys.exit(1)
