#!/usr/bin/env python3
"""
Script de diagnóstico para inspeccionar el modelo TF-IDF existente
================================================================

Inspecciona la estructura del modelo para entender cómo extraer los productos.
"""

import pickle
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def inspect_tfidf_model():
    """Inspeccionar la estructura del modelo TF-IDF"""
    model_path = "data/tfidf_model.pkl"
    
    if not os.path.exists(model_path):
        logger.error(f"❌ Modelo no encontrado: {model_path}")
        return
        
    try:
        logger.info("🔍 Inspeccionando modelo TF-IDF...")
        
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
            
        logger.info(f"📊 Tipo de modelo: {type(model_data)}")
        logger.info(f"📊 Atributos disponibles:")
        
        if hasattr(model_data, '__dict__'):
            for attr_name, attr_value in model_data.__dict__.items():
                attr_type = type(attr_value).__name__
                if hasattr(attr_value, '__len__'):
                    try:
                        attr_len = len(attr_value)
                        logger.info(f"   - {attr_name}: {attr_type} (length: {attr_len})")
                    except:
                        logger.info(f"   - {attr_name}: {attr_type}")
                else:
                    logger.info(f"   - {attr_name}: {attr_type}")
                    
        # Intentar buscar productos específicamente
        possible_product_attrs = ['product_data', 'products', 'data', 'catalog', 'items']
        
        for attr in possible_product_attrs:
            if hasattr(model_data, attr):
                products = getattr(model_data, attr)
                if products:
                    logger.info(f"🎯 ENCONTRADO: {attr} contiene {len(products)} elementos")
                    if len(products) > 0:
                        sample = products[0]
                        logger.info(f"   Muestra: {type(sample)} - {list(sample.keys()) if isinstance(sample, dict) else str(sample)[:100]}")
                    return products
                    
        logger.info("⚠️ No se encontraron productos en atributos esperados")
        
        # Si el modelo es de tipo TFIDFRecommender, intentar cargar usando el método normal
        logger.info("🔄 Intentando cargar con TFIDFRecommender...")
        
        # Importar sin warnings
        import warnings
        warnings.filterwarnings('ignore')
        
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        temp_rec = TFIDFRecommender(model_path)
        
        # Llamar al método load manualmente
        import asyncio
        result = asyncio.run(temp_rec.load())
        
        if result and hasattr(temp_rec, 'product_data') and temp_rec.product_data:
            logger.info(f"✅ Productos cargados via TFIDFRecommender: {len(temp_rec.product_data)}")
            return temp_rec.product_data
        else:
            logger.error("❌ No se pudieron cargar productos via TFIDFRecommender")
            
    except Exception as e:
        logger.error(f"❌ Error inspeccionando modelo: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
    return None

if __name__ == "__main__":
    if not os.path.exists("data/tfidf_model.pkl"):
        print("❌ Modelo no encontrado en data/tfidf_model.pkl")
    else:
        inspect_tfidf_model()
