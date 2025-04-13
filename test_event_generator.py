#!/usr/bin/env python3
"""
Script para probar el funcionamiento correcto del generador de eventos
con los cambios realizados para eventos de compra.
"""
import os
import logging
import asyncio
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.api.core.event_generator import EventGenerator
from src.api.core.sample_data import SAMPLE_PRODUCTS

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

async def test_event_generator():
    """
    Prueba el generador de eventos con los cambios realizados
    para asegurar que los eventos de compra incluyan el campo purchaseTransaction.
    """
    try:
        # Crear instancia del recomendador TF-IDF y entrenarla con datos de muestra
        tfidf_recommender = TFIDFRecommender()
        await tfidf_recommender.fit(SAMPLE_PRODUCTS)
        
        # Crear instancia de RetailAPIRecommender
        retail_recommender = RetailAPIRecommender(
            project_number=os.getenv("GOOGLE_PROJECT_NUMBER"),
            location=os.getenv("GOOGLE_LOCATION", "global"),
            catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
            serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
        )
        
        # Crear instancia del generador de eventos
        event_generator = EventGenerator(retail_recommender, tfidf_recommender)
        
        print("\n=== PRUEBA DE GENERADOR DE EVENTOS ===\n")
        
        # Generar un pequeño número de eventos para probar
        print("1. Generando eventos aleatorios (incluye eventos de compra):")
        result = await event_generator.generate_events(num_events=5)
        print(f"   Resultado: {result}")
        
        # Generar una sesión realista (incluye eventos de compra)
        print("\n2. Generando una sesión realista de usuario:")
        result = await event_generator.generate_realistic_user_sessions(num_sessions=1)
        print(f"   Resultado: {result}")
        
        # Generar eventos personalizados para un usuario específico
        print("\n3. Generando eventos personalizados para un usuario específico:")
        result = await event_generator.generate_personalized_events_for_user(
            user_id="test_event_gen_fix", 
            num_events=5
        )
        print(f"   Resultado: {result}")
        
        print("\n✅ Prueba completada. Verifica que no haya errores relacionados con el campo 'purchaseTransaction'.")
        
        return {"status": "success", "message": "Prueba de generador de eventos completada"}
        
    except Exception as e:
        logging.error(f"Error durante la prueba: {e}")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    asyncio.run(test_event_generator())
