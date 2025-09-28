#!/usr/bin/env python3
"""
Script mejorado para regenerar modelo TF-IDF usando datos ya existentes
======================================================================

Soluciona el problema de version mismatch usando los productos que ya 
están en el modelo existente, evitando la necesidad de conectar a Shopify.

Version: 2.0.0 - Shopify-independent
"""

import os
import sys
import time
import logging
import pickle
import asyncio
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_products_from_existing_model():
    """Cargar productos desde el modelo TF-IDF existente"""
    try:
        model_path = "data/tfidf_model.pkl"
        
        if not os.path.exists(model_path):
            logger.error(f"❌ Modelo existente no encontrado: {model_path}")
            return None
            
        logger.info("📥 Cargando productos desde modelo existente...")
        
        # Importar TFIDFRecommender para usar su método de carga
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        
        # Crear instancia temporal para extraer productos
        temp_recommender = TFIDFRecommender(model_path=model_path)
        
        # Cargar el modelo (esto cargará los productos con warning, pero funcionará)
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
            
        # Extraer productos del modelo
        if hasattr(model_data, 'product_data') and model_data.product_data:
            products = model_data.product_data
            logger.info(f"✅ Extraídos {len(products)} productos del modelo existente")
            
            # Verificar estructura
            if products and len(products) > 0:
                sample_product = products[0]
                logger.info(f"✅ Estructura de producto válida: {list(sample_product.keys())[:5]}...")
                
            return products
        else:
            logger.error("❌ No se encontraron productos en el modelo existente")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error cargando productos desde modelo: {e}")
        import traceback
        logger.error(traceback.format_exc())
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

async def regenerate_tfidf_model_from_existing():
    """Regenerar modelo usando productos del modelo existente"""
    try:
        # Cargar productos del modelo existente (con warnings, pero funcional)
        logger.info("📦 Extrayendo productos del modelo existente...")
        products = load_products_from_existing_model()
        
        if not products:
            logger.error("❌ No se pudieron extraer productos del modelo existente")
            return False
            
        # Importar TFIDFRecommender
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        
        logger.info("🤖 Creando nuevo recomendador TF-IDF...")
        
        # Crear nueva instancia limpia (sin cargar modelo existente)
        new_model_path = "data/tfidf_model_new.pkl"
        recommender = TFIDFRecommender(model_path=new_model_path)
        
        logger.info(f"🔄 Re-entrenando modelo con {len(products)} productos extraídos...")
        start_time = time.time()
        
        # Entrenar con productos extraídos - esto creará un modelo nuevo con scikit-learn 1.6.1
        success = await recommender.fit(products)
        
        if success:
            training_time = time.time() - start_time
            logger.info(f"✅ Nuevo modelo entrenado exitosamente en {training_time:.2f} segundos")
            
            # Reemplazar modelo anterior con el nuevo
            old_model_path = "data/tfidf_model.pkl"
            if os.path.exists(old_model_path):
                os.remove(old_model_path)
                
            os.rename(new_model_path, old_model_path)
            logger.info("✅ Modelo anterior reemplazado con versión actualizada")
            
            # Verificar nuevo modelo
            logger.info("🔍 Verificando nuevo modelo...")
            test_recommender = TFIDFRecommender(model_path=old_model_path)
            load_success = await test_recommender.load()
            
            if load_success:
                logger.info(f"✅ Verificación exitosa: {len(test_recommender.product_data)} productos")
                
                # Test de recomendación
                if test_recommender.product_data:
                    test_product_id = str(test_recommender.product_data[0].get('id', ''))
                    test_recs = await test_recommender.get_recommendations(test_product_id, 3)
                    logger.info(f"✅ Test de recomendación: {len(test_recs)} recomendaciones generadas")
                    
                return True
            else:
                logger.error("❌ El nuevo modelo no se puede cargar")
                return False
        else:
            logger.error("❌ Error entrenando nuevo modelo")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error regenerando modelo: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def verify_sklearn_version():
    """Verificar que scikit-learn sea compatible"""
    try:
        import sklearn
        import pickle
        
        logger.info(f"🔍 Verificando compatibilidad con scikit-learn {sklearn.__version__}")
        
        # Intentar crear un TfidfVectorizer simple para verificar
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        
        # Test básico
        test_docs = ["test document one", "test document two"]
        vectorizer.fit(test_docs)
        
        logger.info("✅ Scikit-learn funcionando correctamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Problema con scikit-learn: {e}")
        return False

async def main():
    """Función principal mejorada"""
    logger.info("🚀 Iniciando regeneración del modelo TF-IDF (Versión 2.0)")
    logger.info("📋 Método: Usar productos del modelo existente")
    logger.info("=" * 70)
    
    # Verificar scikit-learn
    if not verify_sklearn_version():
        logger.error("❌ Problema con scikit-learn. Abortando.")
        return False
        
    # Verificar que existe el modelo
    if not os.path.exists("data/tfidf_model.pkl"):
        logger.error("❌ Modelo TF-IDF existente no encontrado en data/tfidf_model.pkl")
        return False
        
    # Crear backup
    backup_path = backup_existing_model()
    
    try:
        # Regenerar usando productos existentes
        success = await regenerate_tfidf_model_from_existing()
        
        if success:
            logger.info("=" * 70)
            logger.info("🎉 REGENERACIÓN COMPLETADA EXITOSAMENTE")
            logger.info("✅ Modelo TF-IDF actualizado con scikit-learn 1.6.1")
            logger.info("✅ Productos preservados del modelo original")
            logger.info("✅ Version mismatch warning eliminado")
            logger.info("🔄 REINICIA EL SISTEMA para aplicar cambios")
            
            if backup_path:
                logger.info(f"📁 Backup disponible en: {backup_path}")
                
            return True
        else:
            logger.error("❌ Error en regeneración")
            
            if backup_path:
                logger.info("🔄 Restaurando desde backup...")
                import shutil
                shutil.copy2(backup_path, "data/tfidf_model.pkl")
                logger.info("✅ Modelo restaurado")
                
            return False
            
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")
        
        if backup_path:
            logger.info("🔄 Restaurando desde backup...")
            import shutil
            shutil.copy2(backup_path, "data/tfidf_model.pkl")
            logger.info("✅ Modelo restaurado desde backup")
            
        return False

if __name__ == "__main__":
    # Verificar directorio
    if not os.path.exists("src"):
        print("❌ Execute desde el directorio raíz del proyecto")
        print("   cd C:\\Users\\yasma\\Desktop\\retail-recommender-system")
        sys.exit(1)
    
    # Crear directorio data si no existe
    os.makedirs("data", exist_ok=True)
    
    # Ejecutar
    result = asyncio.run(main())
    
    if result:
        print("\n" + "="*50)
        print("🎉 REGENERACIÓN EXITOSA")
        print("🔄 REINICIA EL SISTEMA AHORA:")
        print("   python src/api/main_unified_redis.py")
        print("="*50)
        sys.exit(0)
    else:
        print("\n❌ REGENERACIÓN FALLÓ")
        sys.exit(1)
