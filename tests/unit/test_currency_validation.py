#!/usr/bin/env python3
"""
Script para probar la validación de códigos de moneda en eventos de compra
"""
import os
import asyncio
import logging
import pytest
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender

# ════════════════════════════════════════════════════════════════════
# NO ES UN TEST UNITARIO (19/10/2026, paso 2b de la SPEC E5 nivel 2)
# ════════════════════════════════════════════════════════════════════
# Este fichero es un SCRIPT MANUAL que quedo dentro de tests/unit. Pytest lo
# recogia y lo ejecutaba en cada pase de la suite (asyncio_mode = auto), con
# tres consecuencias, verificadas el 18-19/10/2026:
#
#   1. FUGA DE ENTORNO: el load_dotenv() estaba a nivel de modulo y se
#      ejecutaba durante la RECOLECCION, cargando el .env de la raiz en TODA
#      la sesion de pytest. Asi entraba RECS_VISUAL_POOL_BASE=100 y fallaban
#      6 tests de TestTamanoDelPoolVisual (pasaban ejecutados aislados).
#      Diagnosticado con un espia sobre os.environ: el primer SET de la
#      variable salia de la linea de load_dotenv() de este fichero.
#   2. ESCRITURAS REALES: si el entorno trae GOOGLE_PROJECT_NUMBER, crea un
#      RetailAPIRecommender real y envia 5 eventos purchase-complete FALSOS
#      (visitantes test_currency_0..4) a Google Retail API via
#      UserEventServiceClient.write_user_event.
#   3. NUNCA FALLA: no tiene asserts; los errores solo se imprimen. Como test,
#      siempre "pasaba" sin comprobar nada.
#
# Por eso: (a) pytest lo marca como omitido, con el motivo visible en el
# informe (no se oculta con __test__ = False: un skip queda registrado);
# (b) el .env solo se carga al ejecutarlo como script, en el bloque
# __main__ del final. Como script se comporta igual que antes: el import de
# RetailAPIRecommender ya ocurria ANTES de cargar el .env.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.google,
    pytest.mark.skip(
        reason="Script manual de integracion (escribe eventos reales en Google "
               "Retail API y no tiene asserts). Ejecutar a mano como script."
    ),
]

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
    # Cargar variables de entorno SOLO al ejecutarlo como script (antes estaba
    # a nivel de modulo y contaminaba toda la sesion de pytest: ver cabecera).
    load_dotenv()
    asyncio.run(test_currency_validation())
