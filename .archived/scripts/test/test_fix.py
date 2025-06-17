"""
Script para verificar la solución a la falta de información completa en las recomendaciones de usuario.

Este script:
1. Crea una instancia de los recomendadores (TF-IDF, Retail API, e Híbrido)
2. Obtiene recomendaciones para un usuario específico
3. Imprime los resultados para verificar que la información completa está siendo incluida

Uso:
    python test_fix.py [user_id]
"""

import asyncio
import os
import logging
import sys
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Cargar datos de prueba
def load_sample_data():
    """Carga datos de muestra para pruebas."""
    try:
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        return SAMPLE_PRODUCTS
    except ImportError:
        logger.error("No se pudieron cargar los datos de muestra")
        # Crear algunos datos mínimos para pruebas
        return [
            {
                "id": "9978540327221",
                "title": "Alas de Novia Isidora Ivory 3 Metros",
                "body_html": "Las alas de Novia son un complemento ideal para tu vestido. Placart estas combinan perfecto con nuestros diseños de gasa, que son ideales para sentirte cómoda ese día.",
                "product_type": "Accesorios de Novia"
            },
            {
                "id": "9978666713397",
                "title": "AROS ABANICO Y PIEDRA ROSADO",
                "body_html": "Aros de acrílico estratégicos y fibra de níquel. El diseño de estos aros está compuesto de una pequeña piedra de color rosado, desde donde nacen rayos de color dorado que dan forma a un abanico.",
                "product_type": "Accesorios"
            },
            {
                "id": "9978503037237",
                "title": "Aros Aitana Piedras y Strass Plateado",
                "body_html": "El diseño es parecido a la figura una flor formada de circonas brillantes en color plateado, desde este cuelgan hilos de strass, que sin duda llamaran la atención.",
                "product_type": "Accesorios"
            }
        ]

async def test_user_recommendations(user_id: str):
    """
    Prueba la obtención de recomendaciones para un usuario.
    
    Args:
        user_id: ID del usuario para el cual obtener recomendaciones
    """
    # Importar los recomendadores
    try:
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        from src.recommenders.retail_api import RetailAPIRecommender
        from src.recommenders.hybrid import HybridRecommender
    except ImportError as e:
        logger.error(f"Error importando recomendadores: {e}")
        return
    
    # Configurar recomendadores
    logger.info("Configurando recomendadores...")
    
    # Recomendador TF-IDF
    tfidf_recommender = TFIDFRecommender()
    
    # Recomendador Retail API
    retail_recommender = RetailAPIRecommender(
        project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
        location=os.getenv("GOOGLE_LOCATION", "global"),
        catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
        serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
    )
    
    # Recomendador Híbrido
    hybrid_recommender = HybridRecommender(tfidf_recommender, retail_recommender)
    
    # Cargar datos de prueba
    sample_data = load_sample_data()
    
    # Entrenar el recomendador TF-IDF
    logger.info("Entrenando recomendador TF-IDF...")
    await tfidf_recommender.fit(sample_data)
    
    # Verificar el estado del catálogo
    catalog_available = hasattr(tfidf_recommender, 'product_data') and tfidf_recommender.product_data
    catalog_size = len(tfidf_recommender.product_data) if catalog_available else 0
    logger.info(f"Catálogo disponible: {catalog_available}, Tamaño: {catalog_size}")
    
    if catalog_available and catalog_size > 0:
        logger.info(f"Muestra de producto: {tfidf_recommender.product_data[0].get('id')} - {tfidf_recommender.product_data[0].get('title')}")
    
    # Obtener recomendaciones
    logger.info(f"Obteniendo recomendaciones para usuario: {user_id}")
    
    try:
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=5
        )
        
        logger.info(f"Se obtuvieron {len(recommendations)} recomendaciones")
        
        # Imprimir recomendaciones
        for i, rec in enumerate(recommendations):
            logger.info(f"Recomendación {i+1}:")
            logger.info(f"  ID: {rec.get('id')}")
            logger.info(f"  Título: {rec.get('title')}")
            logger.info(f"  Descripción: {rec.get('description', '')[:50]}...")
            logger.info(f"  Categoría: {rec.get('category')}")
            logger.info(f"  Precio: {rec.get('price')}")
            logger.info(f"  Score: {rec.get('score')}")
            logger.info(f"  Fuente: {rec.get('source')}")
            logger.info("-" * 50)
        
        # Verificar si la información está completa
        complete_info = all(rec.get('title') != "Producto" for rec in recommendations)
        
        if complete_info:
            logger.info("✅ ÉXITO: Las recomendaciones contienen información completa de productos")
        else:
            logger.error("❌ ERROR: Algunas recomendaciones no tienen información completa")
            
        # Devolver resultado para facilitar pruebas
        return {
            "success": complete_info,
            "recommendations": recommendations
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo recomendaciones: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }

async def main():
    """Función principal."""
    # Usuario de prueba por defecto
    user_id = "8831066177845"
    
    # Permitir sobrescribir por línea de comandos
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    
    logger.info(f"Iniciando prueba para usuario: {user_id}")
    result = await test_user_recommendations(user_id)
    
    if result and result.get("success"):
        logger.info("✅ La prueba fue exitosa")
    else:
        logger.error("❌ La prueba falló")
    
    return result

if __name__ == "__main__":
    asyncio.run(main())
