#!/usr/bin/env python3
# Script para verificar que la fuente de las recomendaciones se muestra correctamente
# Este script prueba los diferentes tipos de origen de recomendaciones

import sys
import os
import json
import requests
from typing import Dict, List, Any

# Configuración básica de logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("source_verification")

# Configuración
API_URL = "http://localhost:8000"
API_KEY = "2fed9999056fab6dac5654238f0cae1c"  # Reemplaza con tu API key real

def pretty_json(data):
    """Formatea JSON para mejor legibilidad"""
    return json.dumps(data, indent=2, ensure_ascii=False)

def test_mcp_conversation():
    """Prueba el endpoint de conversación MCP para verificar fuentes"""
    logger.info("Probando endpoint de conversación MCP...")
    
    try:
        # Crear una consulta para probar
        payload = {
            "query": "Busco una camisa azul",
            "user_id": "test_user",
            "market_id": "ES",
            "n_recommendations": 3
        }
        
        headers = {"X-API-Key": API_KEY}
        
        # Realizar la petición
        response = requests.post(
            f"{API_URL}/v1/mcp/conversation",
            json=payload,
            headers=headers
        )
        
        # Verificar respuesta
        logger.info(f"Respuesta: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            recommendations = data.get("recommendations", [])
            
            # Mostrar recomendaciones con sus fuentes
            logger.info(f"Se encontraron {len(recommendations)} recomendaciones:")
            
            for i, rec in enumerate(recommendations):
                title = rec.get("title", "Sin título")
                source = rec.get("source", "desconocida")
                logger.info(f"  {i+1}. {title} - Fuente: {source}")
            
            return len(recommendations) > 0, recommendations
        else:
            logger.error(f"Error en la petición: {response.status_code}")
            logger.error(response.text)
            return False, []
            
    except Exception as e:
        logger.error(f"Error en la prueba: {e}")
        return False, []

def print_detailed_info(recommendations: List[Dict[str, Any]]):
    """Imprime información detallada sobre las recomendaciones"""
    print("\n" + "="*70)
    print("📋 INFORMACIÓN DETALLADA DE RECOMENDACIONES")
    print("="*70)
    
    for i, rec in enumerate(recommendations):
        print(f"\n🔹 Recomendación #{i+1}:")
        print(f"  Título: {rec.get('title', 'Sin título')}")
        print(f"  ID: {rec.get('id', 'Sin ID')}")
        print(f"  Fuente: {rec.get('source', 'desconocida')}")
        print(f"  Puntuación: {rec.get('score', 0)}")
        print(f"  Razón: {rec.get('reason', 'Sin razón')}")
        
        # Información adicional si está disponible
        if "description" in rec and rec["description"]:
            print(f"  Descripción: {rec['description'][:100]}...")
        
        if "images" in rec:
            print(f"  Imágenes: {len(rec['images'])} disponibles")
        
        if "market_adapted" in rec:
            print(f"  Adaptado al mercado: {'Sí' if rec['market_adapted'] else 'No'}")
    
    print("\n" + "="*70)

def main():
    """Función principal"""
    print("\n" + "="*50)
    print("🔍 VERIFICACIÓN DE FUENTES DE RECOMENDACIONES")
    print("="*50 + "\n")
    
    # Probar endpoint de conversación
    success, recommendations = test_mcp_conversation()
    
    # Mostrar información detallada
    if success and recommendations:
        print_detailed_info(recommendations)
        
        # Verificar si todas las recomendaciones tienen fuente
        all_have_source = all("source" in rec for rec in recommendations)
        
        print("\n" + "="*50)
        if all_have_source:
            print("✅ TODAS LAS RECOMENDACIONES TIENEN FUENTE")
            print("La mejora ha sido implementada correctamente.")
        else:
            print("❌ ALGUNAS RECOMENDACIONES NO TIENEN FUENTE")
            print("La implementación puede no estar completa.")
    else:
        print("\n" + "="*50)
        print("❌ NO SE PUDIERON OBTENER RECOMENDACIONES")
        print("Verifica que el servidor esté funcionando correctamente.")
    
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
