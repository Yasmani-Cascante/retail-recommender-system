#!/usr/bin/env python3
# Script para monitorear la integración MCP y depurar problemas
# Ejecuta este script para tener un seguimiento detallado de lo que sucede

import sys
import os
import json
import time
import logging
import requests
from typing import Dict, Optional, Any

# Configuración básica de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler("mcp_debug.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("mcp_debug")

# Configuración
BRIDGE_URL = "http://localhost:3001"
API_URL = "http://localhost:8000"
API_KEY = "2fed9999056fab6dac5654238f0cae1c"  # Reemplaza con tu API key real

def pretty_json(data):
    """Formatea JSON para mejor legibilidad"""
    return json.dumps(data, indent=2, ensure_ascii=False)

def test_health():
    """Prueba el estado de salud del bridge MCP"""
    logger.info("Verificando estado del bridge MCP...")
    try:
        response = requests.get(f"{BRIDGE_URL}/health")
        logger.info(f"Estado del bridge: {response.status_code}")
        logger.info(pretty_json(response.json()))
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error al verificar estado del bridge: {e}")
        return False

def test_direct_conversation():
    """Prueba una consulta directa al bridge MCP"""
    logger.info("Probando consulta directa al bridge MCP...")
    try:
        payload = {
            "query": "Busco una camisa azul",
            "sessionId": f"test-session-{int(time.time())}"
        }
        logger.debug(f"Payload enviado al bridge: {pretty_json(payload)}")
        
        response = requests.post(f"{BRIDGE_URL}/api/mcp/conversation", json=payload)
        logger.info(f"Respuesta del bridge: {response.status_code}")
        logger.info(pretty_json(response.json()))
        
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error en consulta directa al bridge: {e}")
        return False

def test_api_integration():
    """Prueba la integración a través de la API principal"""
    logger.info("Probando integración con API principal...")
    try:
        payload = {
            "query": "Busco una camisa azul",
            "user_id": "test_user",
            "market_id": "ES",
            "n_recommendations": 3
        }
        headers = {"X-API-Key": API_KEY}
        
        logger.debug(f"Payload enviado a la API: {pretty_json(payload)}")
        logger.debug(f"Headers: {headers}")
        
        response = requests.post(
            f"{API_URL}/v1/mcp/conversation", 
            json=payload, 
            headers=headers
        )
        
        logger.info(f"Respuesta de la API: {response.status_code}")
        response_data = response.json()
        logger.info(pretty_json(response_data))
        
        # Analizar resultados
        recommendation_count = len(response_data.get("recommendations", []))
        logger.info(f"Número de recomendaciones recibidas: {recommendation_count}")
        
        # Verificar mensaje de respuesta
        answer = response_data.get("answer", "")
        logger.info(f"Respuesta conversacional: {answer}")
        
        # Analizar metadatos
        metadata = response_data.get("metadata", {})
        source = metadata.get("source", "unknown")
        logger.info(f"Fuente de las recomendaciones: {source}")
        
        return recommendation_count > 0
    except Exception as e:
        logger.error(f"Error en integración con API: {e}")
        return False

def test_markets():
    """Prueba el endpoint de mercados soportados"""
    logger.info("Verificando mercados soportados...")
    try:
        headers = {"X-API-Key": API_KEY}
        response = requests.get(f"{API_URL}/v1/mcp/markets", headers=headers)
        logger.info(f"Respuesta de mercados: {response.status_code}")
        logger.info(pretty_json(response.json()))
        
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error al verificar mercados: {e}")
        return False

def analyze_system_configuration():
    """Analiza la configuración del sistema"""
    logger.info("Analizando configuración del sistema...")
    
    # Verificar disponibilidad de modelo TF-IDF
    try:
        model_path = "data/tfidf_model.pkl"
        full_path = os.path.join(os.getcwd(), model_path)
        
        if os.path.exists(full_path):
            file_size = os.path.getsize(full_path) / (1024 * 1024)  # MB
            logger.info(f"Modelo TF-IDF encontrado: {full_path} ({file_size:.2f} MB)")
        else:
            logger.warning(f"Modelo TF-IDF no encontrado en: {full_path}")
            
            # Buscar modelos en directorio data
            data_dir = os.path.join(os.getcwd(), "data")
            if os.path.exists(data_dir):
                models = [f for f in os.listdir(data_dir) if f.endswith('.pkl')]
                logger.info(f"Modelos disponibles en data/: {models}")
            else:
                logger.warning(f"Directorio data/ no encontrado")
    except Exception as e:
        logger.error(f"Error al verificar modelo TF-IDF: {e}")

def debug_content_recommender():
    """Realiza una prueba específica para depurar el recomendador de contenido"""
    logger.info("Depurando recomendador de contenido...")
    
    try:
        headers = {"X-API-Key": API_KEY}
        response = requests.get(f"{API_URL}/health", headers=headers)
        
        if response.status_code == 200:
            health_data = response.json()
            recommenders = health_data.get("recommenders", {})
            
            if "tfidf_recommender" in recommenders:
                tfidf_info = recommenders["tfidf_recommender"]
                logger.info(f"Estado de TF-IDF: {tfidf_info}")
                
                # Verificar productos cargados
                products_count = tfidf_info.get("products_count", 0)
                logger.info(f"Productos cargados en TF-IDF: {products_count}")
                
                if products_count == 0:
                    logger.error("⚠️ NO HAY PRODUCTOS CARGADOS EN EL RECOMENDADOR")
                    logger.error("Esto explicaría por qué no hay recomendaciones")
            else:
                logger.warning("No se encontró información del recomendador TF-IDF")
        else:
            logger.warning(f"No se pudo obtener estado de salud: {response.status_code}")
    except Exception as e:
        logger.error(f"Error al depurar recomendador de contenido: {e}")

def main():
    """Función principal"""
    print("\n" + "="*50)
    print("🔍 DEPURACIÓN DE INTEGRACIÓN MCP")
    print("="*50 + "\n")
    
    # Analizar configuración
    analyze_system_configuration()
    
    # Depurar recomendador de contenido
    debug_content_recommender()
    
    # Probar componentes
    bridge_ok = test_health()
    direct_ok = test_direct_conversation()
    api_ok = test_api_integration()
    markets_ok = test_markets()
    
    # Resumen
    print("\n" + "="*50)
    print("📊 RESUMEN DE PRUEBAS")
    print("="*50)
    print(f"Estado del bridge: {'✅' if bridge_ok else '❌'}")
    print(f"Consulta directa al bridge: {'✅' if direct_ok else '❌'}")
    print(f"Integración con API: {'✅' if api_ok else '❌'}")
    print(f"Endpoint de mercados: {'✅' if markets_ok else '❌'}")
    print("="*50 + "\n")
    
    # Conclusión
    if not api_ok:
        print("❌ La integración con la API principal NO está funcionando correctamente.")
        print("📝 Revisa el archivo 'mcp_debug.log' para más detalles.")
    else:
        print("✅ La integración con la API principal está funcionando correctamente.")
    
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
