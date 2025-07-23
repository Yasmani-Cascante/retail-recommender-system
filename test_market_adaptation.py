"""
Script de prueba para verificar la adaptación de mercado
"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def test_market_adaptation():
    """Prueba la adaptación de mercado"""
    
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
        
        # Request body
        data = {
            "user_message": "Busco algo especial para regalar",
            "session_id": f"test_session_{market_id}_{int(datetime.now().timestamp())}",
            "market_id": market_id,
            "include_recommendations": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Verificar recomendaciones
                        recommendations = result.get("recommendations", [])
                        print(f"\nRecomendaciones recibidas: {len(recommendations)}")
                        
                        # Mostrar primera recomendación
                        if recommendations:
                            first_rec = recommendations[0]
                            print(f"\nPrimera recomendación:")
                            print(f"  Título: {first_rec.get('title', 'N/A')}")
                            print(f"  Título Original: {first_rec.get('original_title', 'N/A')}")
                            print(f"  Precio: {first_rec.get('price', 'N/A')} {first_rec.get('currency', 'N/A')}")
                            print(f"  Precio Original: {first_rec.get('original_price', 'N/A')} {first_rec.get('original_currency', 'N/A')}")
                            print(f"  Adaptado: {first_rec.get('market_adapted', False)}")
                            
                            # Verificar conversión correcta
                            if first_rec.get('original_price') and first_rec.get('price'):
                                orig = first_rec['original_price']
                                conv = first_rec['price']
                                rate = conv / orig if orig > 0 else 0
                                print(f"  Tasa de cambio aplicada: {rate:.6f}")
                    else:
                        print(f"❌ Error: Status {response.status}")
                        print(await response.text())
                        
        except Exception as e:
            print(f"❌ Error en la prueba: {e}")

if __name__ == "__main__":
    print("🧪 Iniciando pruebas de adaptación de mercado...")
    asyncio.run(test_market_adaptation())
    print("\n✅ Pruebas completadas")
