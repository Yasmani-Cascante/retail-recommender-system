#!/usr/bin/env python3
"""
Script para probar el registro de eventos de compra con la corrección de currencyCode
"""
import os
import asyncio
import logging
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

async def test_purchase_event():
    """Prueba el registro de un evento de compra con currencyCode."""
    try:
        # Obtener variables de configuración
        project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
        location = os.getenv("GOOGLE_LOCATION", "global")
        catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
        
        if not project_number:
            logging.error("GOOGLE_PROJECT_NUMBER no está configurado en las variables de entorno")
            return {"status": "error", "error": "Configuración incompleta"}
        
        # Crear instancia del recomendador
        retail_recommender = RetailAPIRecommender(
            project_number=project_number,
            location=location,
            catalog=catalog
        )
        
        # Registrar un evento de compra de prueba
        logging.info("Registrando evento de compra de prueba...")
        
        # Probar con un código de moneda específico
        result = await retail_recommender.record_user_event(
            user_id="test_user_fixed",
            event_type="purchase-complete",
            product_id="test_product_1",
            purchase_amount=99.99,
            currency_code="USD"  # Usar USD como moneda para la prueba
        )
        
        # Mostrar resultado
        logging.info(f"Resultado del registro de evento: {result}")
        
        if result.get("status") == "success":
            print("\n✅ Prueba exitosa! El evento de compra ahora incluye currencyCode y se registró correctamente.")
        else:
            print("\n❌ La prueba falló. Revisa los errores para más detalles.")
        
        return result
        
    except Exception as e:
        logging.error(f"Error durante la prueba: {e}")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    asyncio.run(test_purchase_event())
