#!/usr/bin/env python3
"""
🧪 SCRIPT DE PRUEBA: Google Retail API con Usuario con Historial

Este script prueba directamente si Google Retail API funciona con usuarios que tienen historial.
"""

import asyncio
import os
import sys
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.recommenders.retail_api import RetailAPIRecommender

async def test_retail_api_with_history():
    """
    Prueba Google Retail API con usuario con historial vs usuario anónimo
    """
    try:
        print("🧪 INICIANDO PRUEBA DE GOOGLE RETAIL API")
        print("="*60)
        
        # Crear recomendador
        retail_recommender = RetailAPIRecommender(
            project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
            location=os.getenv("GOOGLE_LOCATION", "global"),
            catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
            serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
        )
        
        # Configuración de prueba
        user_with_history = "8816287056181"
        product_id = "9978479903029"
        anonymous_user = "anonymous"
        
        print(f"📋 CONFIGURACIÓN:")
        print(f"   Usuario con historial: {user_with_history}")
        print(f"   Usuario anónimo: {anonymous_user}")
        print(f"   Producto: {product_id}")
        print()
        
        # PRUEBA 1: Usuario con historial
        print("🔍 PRUEBA 1: Usuario con historial")
        recommendations_with_history = await retail_recommender.get_recommendations(
            user_id=user_with_history,
            product_id=product_id,
            n_recommendations=5
        )
        print(f"   Resultados: {len(recommendations_with_history)} recomendaciones")
        if recommendations_with_history:
            for i, rec in enumerate(recommendations_with_history[:3]):
                print(f"   {i+1}. ID={rec.get('id')}, Título={rec.get('title', '')[:40]}...")
        print()
        
        # PRUEBA 2: Usuario anónimo
        print("🔍 PRUEBA 2: Usuario anónimo (control)")
        recommendations_anonymous = await retail_recommender.get_recommendations(
            user_id=anonymous_user,
            product_id=product_id,
            n_recommendations=5
        )
        print(f"   Resultados: {len(recommendations_anonymous)} recomendaciones")
        if recommendations_anonymous:
            for i, rec in enumerate(recommendations_anonymous[:3]):
                print(f"   {i+1}. ID={rec.get('id')}, Título={rec.get('title', '')[:40]}...")
        print()
        
        # PRUEBA 3: Recomendaciones generales para usuario con historial
        print("🔍 PRUEBA 3: Recomendaciones generales (sin producto específico)")
        user_recommendations = await retail_recommender.get_recommendations(
            user_id=user_with_history,
            product_id=None,  # Sin producto específico
            n_recommendations=5
        )
        print(f"   Resultados: {len(user_recommendations)} recomendaciones")
        if user_recommendations:
            for i, rec in enumerate(user_recommendations[:3]):
                print(f"   {i+1}. ID={rec.get('id')}, Título={rec.get('title', '')[:40]}...")
        print()
        
        # ANÁLISIS
        print("📊 ANÁLISIS DE RESULTADOS:")
        print("="*60)
        
        google_works = len(recommendations_with_history) > 0 or len(user_recommendations) > 0
        history_matters = len(recommendations_with_history) > len(recommendations_anonymous)
        personalization_works = len(user_recommendations) > 0
        
        print(f"Google Retail API funcionando: {'✅ SÍ' if google_works else '❌ NO'}")
        print(f"El historial de usuario importa: {'✅ SÍ' if history_matters else '❌ NO'}")
        print(f"Personalización activa: {'✅ SÍ' if personalization_works else '❌ NO'}")
        print()
        
        # DIAGNÓSTICO
        if len(recommendations_with_history) > 0:
            diagnosis = "✅ ÉXITO: Google Retail API funciona con usuarios con historial"
        elif len(user_recommendations) > 0:
            diagnosis = "⚠️ PARCIAL: Funciona para recomendaciones generales, no específicas por producto"
        else:
            diagnosis = "❌ PROBLEMA: Google Retail API no funciona incluso con usuarios con historial"
        
        print(f"🎯 DIAGNÓSTICO: {diagnosis}")
        print()
        
        # RECOMENDACIONES
        print("💡 RECOMENDACIONES:")
        if google_works:
            print("   • Usar usuarios con historial para obtener recomendaciones personalizadas")
            print("   • Implementar tracking de eventos de usuario en la aplicación")
            print("   • El sistema híbrido funcionará correctamente")
        else:
            print("   • Revisar configuración de serving config")
            print("   • Verificar que los eventos de usuario se estén registrando correctamente")
            print("   • Considerar usar solo TF-IDF hasta resolver el problema")
        
        return {
            "google_retail_working": google_works,
            "history_matters": history_matters,
            "personalization_active": personalization_works,
            "diagnosis": diagnosis
        }
        
    except Exception as e:
        print(f"❌ ERROR EN PRUEBA: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    asyncio.run(test_retail_api_with_history())
