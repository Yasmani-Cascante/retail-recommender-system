"""
Script de prueba CORREGIDO para verificar la adaptación de mercado
"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def test_market_adaptation():
    """Prueba la adaptación de mercado con el formato correcto"""
    
    # URL de tu API
    API_URL = "http://localhost:8000/v1/mcp/conversation"
    API_KEY = "2fed9999056fab6dac5654238f0cae1c"
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    # Probar diferentes mercados
    markets = ["US", "ES", "MX", "CO"]
    
    for market_id in markets:
        print(f"\n{'='*50}")
        print(f"Testing market: {market_id}")
        print('='*50)
        
        # Request body CORREGIDO - usar "query" en lugar de "user_message"
        data = {
            "query": "Busco algo especial para regalar",  # CORREGIDO: query en lugar de user_message
            "session_id": f"test_session_{market_id}_{int(datetime.now().timestamp())}",
            "market_id": market_id,
            "user_id": "test_user",
            "include_recommendations": True,
            "num_recommendations": 5
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        print(f"\n✅ Respuesta exitosa!")
                        
                        # Verificar estructura de respuesta
                        conversation_response = result.get("conversation_response", "")
                        print(f"\nRespuesta conversacional: {conversation_response[:100]}...")
                        
                        # Verificar recomendaciones
                        recommendations = result.get("recommendations", [])
                        print(f"\nRecomendaciones recibidas: {len(recommendations)}")
                        
                        # Mostrar primeras 2 recomendaciones
                        for i, rec in enumerate(recommendations[:2]):
                            print(f"\n--- Recomendación {i+1} ---")
                            print(f"  Título: {rec.get('title', 'N/A')}")
                            
                            # Verificar si hay título original (traducción aplicada)
                            if rec.get('original_title'):
                                print(f"  Título Original: {rec.get('original_title')}")
                                print(f"  ✓ Traducción aplicada")
                            
                            # Precios
                            price = rec.get('price', 0)
                            currency = rec.get('currency', 'N/A')
                            print(f"  Precio: {price:.2f} {currency}")
                            
                            # Verificar conversión
                            if rec.get('original_price'):
                                orig_price = rec.get('original_price', 0)
                                orig_currency = rec.get('original_currency', 'COP')
                                print(f"  Precio Original: {orig_price:.2f} {orig_currency}")
                                
                                # Calcular tasa aplicada
                                if orig_price > 0:
                                    rate = price / orig_price
                                    print(f"  Tasa de cambio aplicada: {rate:.6f}")
                                    
                                    # Verificar que la tasa sea correcta
                                    expected_rates = {
                                        "US": 0.00025,  # COP to USD
                                        "ES": 0.00023,  # COP to EUR
                                        "MX": 0.0043,   # COP to MXN
                                        "CO": 1.0       # COP to COP
                                    }
                                    
                                    expected_rate = expected_rates.get(market_id, 1.0)
                                    if abs(rate - expected_rate) < 0.0001:
                                        print(f"  ✅ Tasa correcta para {market_id}")
                                    else:
                                        print(f"  ⚠️ Tasa incorrecta. Esperada: {expected_rate}")
                            
                            # Verificar flag de adaptación
                            if rec.get('market_adapted'):
                                print(f"  ✓ Flag de adaptación presente")
                            
                            # Otros campos
                            if rec.get('description'):
                                desc = rec.get('description', '')[:50]
                                print(f"  Descripción: {desc}...")
                        
                        # Verificar contexto de mercado
                        market_context = result.get("market_context", {})
                        if market_context:
                            print(f"\n📍 Contexto de mercado:")
                            print(f"  Market ID: {market_context.get('market_id')}")
                            print(f"  Currency: {market_context.get('currency')}")
                            
                    else:
                        print(f"❌ Error: Status {response.status}")
                        error_text = await response.text()
                        print(error_text)
                        
        except Exception as e:
            print(f"❌ Error en la prueba: {e}")
            import traceback
            traceback.print_exc()

async def test_simple_request():
    """Prueba simple para verificar que el endpoint funciona"""
    print("\n" + "="*60)
    print("PRUEBA SIMPLE - Verificando endpoint")
    print("="*60)
    
    API_URL = "http://localhost:8000/v1/mcp/conversation"
    API_KEY = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    # Request mínimo
    data = {
        "query": "Hola, busco un regalo",
        "market_id": "US"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=headers, json=data) as response:
                print(f"Status: {response.status}")
                if response.status == 200:
                    result = await response.json()
                    print("✅ Endpoint funcionando correctamente")
                    print(f"Respuesta tiene {len(result.get('recommendations', []))} recomendaciones")
                else:
                    print(f"❌ Error: {await response.text()}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        print("\n⚠️ Asegúrate de que el servidor esté corriendo:")
        print("python -m uvicorn src.api.main_unified_redis:app --reload --port 8000")

if __name__ == "__main__":
    print("🧪 Iniciando pruebas de adaptación de mercado...")
    print("\n⚠️ IMPORTANTE: Asegúrate de que el servidor esté corriendo")
    
    # Primero prueba simple
    asyncio.run(test_simple_request())
    
    # Luego pruebas completas
    asyncio.run(test_market_adaptation())
    
    print("\n✅ Pruebas completadas")
    
    print("\n📋 Resumen de verificaciones:")
    print("1. ✓ El endpoint debe responder con status 200")
    print("2. ✓ Los precios deben estar convertidos (ej: ~15 USD, no 59000)")
    print("3. ✓ Los títulos en US deben estar en inglés (si aplica)")
    print("4. ✓ Debe preservar valores originales en campos original_*")
    print("5. ✓ Las tasas de cambio deben ser correctas")
