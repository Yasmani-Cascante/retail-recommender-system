#!/usr/bin/env python3
"""
Script para probar el uso del código de moneda predeterminado desde variables de entorno
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

async def test_default_currency():
    """Prueba el uso del código de moneda predeterminado desde variables de entorno."""
    try:
        # Configurar una moneda predeterminada usando variables de entorno
        print("\n=== CONFIGURACIÓN DE MONEDA PREDETERMINADA ===\n")
        
        # Guardar el valor original de DEFAULT_CURRENCY si existe
        original_value = os.getenv("DEFAULT_CURRENCY")
        
        print(f"Valor original de DEFAULT_CURRENCY: {original_value or 'No configurado'}")
        
        # Probar con diferentes valores de DEFAULT_CURRENCY
        test_currencies = [
            "EUR",   # Euro
            "USD",   # Dólar estadounidense
            "INVALID_CODE",  # Código no válido para probar validación
            None     # Sin configuración
        ]
        
        # Obtener variables de configuración para RetailAPIRecommender
        project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
        location = os.getenv("GOOGLE_LOCATION", "global")
        catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
        
        if not project_number:
            logging.error("GOOGLE_PROJECT_NUMBER no está configurado en las variables de entorno")
            return {"status": "error", "error": "Configuración incompleta"}
            
        print("\n--- Ejecutando pruebas con diferentes valores de DEFAULT_CURRENCY ---\n")
        
        for i, currency in enumerate(test_currencies):
            # Configurar la variable de entorno
            if currency is None:
                if "DEFAULT_CURRENCY" in os.environ:
                    del os.environ["DEFAULT_CURRENCY"]
                curr_display = "Eliminada"
            else:
                os.environ["DEFAULT_CURRENCY"] = currency
                curr_display = currency
                
            print(f"Prueba {i+1}: DEFAULT_CURRENCY = {curr_display}")
            
            # Crear instancia del recomendador
            retail_recommender = RetailAPIRecommender(
                project_number=project_number,
                location=location,
                catalog=catalog
            )
            
            # Intentar registrar un evento de compra sin especificar moneda
            result = await retail_recommender.record_user_event(
                user_id=f"test_default_currency_{i}",
                event_type="purchase-complete",
                product_id="test_product_1",
                purchase_amount=10.0
                # No especificamos currency_code para probar el valor predeterminado
            )
            
            # Verificar el resultado
            if result.get("status") == "success":
                currency_used = result.get("currency_used", "Desconocido")
                print(f"  Evento registrado con éxito")
                print(f"  Moneda utilizada: {currency_used}")
                
                # Para códigos inválidos, debería usar COP como fallback
                expected = "COP" if currency == "INVALID_CODE" else (currency or "COP")
                
                if currency_used == expected:
                    print(f"  ✅ CORRECTO: Se utilizó la moneda esperada")
                else:
                    print(f"  ❌ ERROR: Se esperaba {expected}, se utilizó {currency_used}")
            else:
                print(f"  ❌ ERROR: El evento no se registró correctamente")
                print(f"  Error: {result.get('error', 'Desconocido')}")
                
            print()
        
        # Restaurar el valor original
        if original_value is not None:
            os.environ["DEFAULT_CURRENCY"] = original_value
            print(f"Restaurado DEFAULT_CURRENCY a su valor original: {original_value}")
        elif "DEFAULT_CURRENCY" in os.environ:
            del os.environ["DEFAULT_CURRENCY"]
            print("Eliminada la variable DEFAULT_CURRENCY")
        
        return {"status": "success", "message": "Pruebas de moneda predeterminada completadas"}
        
    except Exception as e:
        logging.error(f"Error durante las pruebas: {e}")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    asyncio.run(test_default_currency())
