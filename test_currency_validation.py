#!/usr/bin/env python3
"""
Script para probar la validación de códigos de moneda en eventos de compra
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

async def test_currency_validation():
    """Prueba la validación de códigos de moneda en eventos de compra."""
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
        
        # Casos de prueba
        test_cases = [
            {
                "name": "Moneda válida (USD)",
                "currency": "USD",
                "expected_result": "USD"
            },
            {
                "name": "Moneda válida (EUR)",
                "currency": "EUR",
                "expected_result": "EUR"
            },
            {
                "name": "Moneda inválida (XXX)",
                "currency": "XXX",
                "expected_result": "COP"  # Debería usar COP por defecto
            },
            {
                "name": "Moneda inválida (123)",
                "currency": "123",
                "expected_result": "COP"  # Debería usar COP por defecto
            },
            {
                "name": "Sin moneda especificada",
                "currency": None,
                "expected_result": "COP"  # Debería usar COP por defecto
            }
        ]
        
        print("\n=== PRUEBA DE VALIDACIÓN DE CÓDIGOS DE MONEDA ===\n")
        
        # Ejecutar casos de prueba
        for i, test_case in enumerate(test_cases):
            print(f"Caso {i+1}: {test_case['name']}")
            print(f"  Moneda de entrada: {test_case['currency']}")
            
            try:
                # Intentar registrar el evento con la moneda especificada
                result = await retail_recommender.record_user_event(
                    user_id=f"test_currency_{i}",
                    event_type="purchase-complete",
                    product_id="test_product_1",
                    purchase_amount=10.0,
                    currency_code=test_case['currency']
                )
                
                # Verificar el resultado
                if result.get("status") == "success":
                    currency_used = result.get("currency_used", "Desconocido")
                    print(f"  Resultado: Éxito")
                    print(f"  Moneda usada: {currency_used}")
                    
                    if currency_used == test_case['expected_result']:
                        print(f"  ✅ CORRECTO: Se usó la moneda esperada")
                    else:
                        print(f"  ❌ ERROR: Se esperaba {test_case['expected_result']}, se usó {currency_used}")
                else:
                    print(f"  ❌ ERROR: El evento no se registró correctamente")
                    print(f"  Error: {result.get('error', 'Desconocido')}")
            
            except Exception as e:
                print(f"  ❌ ERROR: Excepción durante la prueba: {str(e)}")
            
            print()
        
        return {"status": "success", "message": "Pruebas de validación de moneda completadas"}
        
    except Exception as e:
        logging.error(f"Error durante las pruebas: {e}")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    asyncio.run(test_currency_validation())
