#!/usr/bin/env python
"""
Script para probar las recomendaciones de usuario y diagnosticar problemas.

Este script enviará una solicitud directa al sistema de recomendaciones
para el usuario proporcionado, y mostrará información detallada sobre
la respuesta, incluidos los detalles de los productos recomendados.
"""

import asyncio
import os
import json
import logging
import sys
from typing import Optional
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Importar componentes necesarios
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from src.recommenders.hybrid import HybridRecommender
from src.api.core.store import init_shopify

async def load_shopify_products():
    """Carga productos desde Shopify."""
    try:
        # Inicializar cliente Shopify
        client = init_shopify()
        if client:
            products = client.get_products()
            logger.info(f"Cargados {len(products)} productos desde Shopify")
            if products:
                logger.info(f"Primer producto: {products[0].get('title', 'No title')}")
            return products
        else:
            logger.warning("No se pudo inicializar el cliente de Shopify, intentando cargar productos de muestra")
    except Exception as e:
        logger.error(f"Error cargando productos desde Shopify: {e}")
    
    # Si falla Shopify, intentar cargar productos de muestra
    logger.info("Cargando datos de muestra...")
    try:
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        if SAMPLE_PRODUCTS:
            logger.info(f"Cargados {len(SAMPLE_PRODUCTS)} productos de muestra")
            return SAMPLE_PRODUCTS
    except Exception as e:
        logger.error(f"Error cargando datos de muestra: {e}")
    
    logger.error("No se pudieron cargar productos de ninguna fuente")
    return []

async def main(user_id: str, n_recommendations: int = 5):
    """
    Función principal para probar recomendaciones de usuario.
    
    Args:
        user_id: ID del usuario para el cual obtener recomendaciones
        n_recommendations: Número de recomendaciones a solicitar
    """
    logger.info(f"Iniciando prueba de recomendaciones para usuario {user_id}")
    
    # Crear recomendadores
    tfidf_recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")
    retail_recommender = RetailAPIRecommender(
        project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
        location=os.getenv("GOOGLE_LOCATION", "global"),
        catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
        serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
    )
    
    # Cargar productos
    products = await load_shopify_products()
    if not products:
        logger.error("No se pudieron cargar productos. Abortando.")
        return
    
    # Entrenar recomendador TF-IDF
    logger.info("Entrenando recomendador TF-IDF...")
    success = await tfidf_recommender.fit(products)
    if not success:
        logger.error("Error entrenando recomendador TF-IDF")
        return
    
    # Crear recomendador híbrido
    hybrid_recommender = HybridRecommender(tfidf_recommender, retail_recommender)
    
    # Verificar catálogo
    logger.info(f"Catálogo cargado: {len(tfidf_recommender.product_data)} productos")
    if tfidf_recommender.product_data and len(tfidf_recommender.product_data) > 0:
        sample_product = tfidf_recommender.product_data[0]
        logger.info(f"Muestra de producto: ID={sample_product.get('id')}, Título={sample_product.get('title')}")
    
    # Obtener recomendaciones
    logger.info(f"Solicitando recomendaciones para usuario {user_id}...")
    try:
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n_recommendations
        )
        
        if not recommendations:
            logger.error("No se obtuvieron recomendaciones")
            return
        
        # Mostrar resultados
        logger.info(f"Se obtuvieron {len(recommendations)} recomendaciones para usuario {user_id}:")
        for i, rec in enumerate(recommendations):
            logger.info(f"Recomendación {i+1}:")
            for key, value in rec.items():
                # Limitar longitud para campos de texto largo
                if key in ["description"] and isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                logger.info(f"  {key}: {value}")
            logger.info("  " + "-" * 40)
        
        # Guardar resultados en archivo
        output_file = f"recommendations_{user_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "user_id": user_id,
                "recommendations": recommendations
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Resultados guardados en {output_file}")
        
    except Exception as e:
        logger.error(f"Error obteniendo recomendaciones: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    user_id = "8831066177845"  # Usuario de prueba por defecto
    n_recommendations = 5
    
    # Permitir sobrescribir por línea de comandos
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            n_recommendations = int(sys.argv[2])
        except ValueError:
            logger.warning(f"Valor inválido para n_recommendations: {sys.argv[2]}, usando valor por defecto: 5")
    
    asyncio.run(main(user_id, n_recommendations))
