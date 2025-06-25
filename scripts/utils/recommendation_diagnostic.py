#!/usr/bin/env python3
"""
Script de diagnóstico para sistema de recomendaciones
Prueba diferentes escenarios para identificar problemas de personalización
"""

import requests
import json
import time
from typing import Dict, List, Optional

class RecommendationDiagnostic:
    """Herramienta de diagnóstico para el sistema de recomendaciones"""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "2fed9999056fab6dac5654238f0cae1c"):
        self.base_url = base_url
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def test_scenario(self, scenario_name: str, product_id: str, user_id: Optional[str] = None):
        """Prueba un escenario específico y reporta resultados"""
        print(f"\n{'='*60}")
        print(f"🧪 PRUEBA: {scenario_name}")
        print(f"   Product ID: {product_id}")
        print(f"   User ID: {user_id or 'None'}")
        print(f"{'='*60}")
        
        # Construir URL
        url = f"{self.base_url}/v1/recommendations/{product_id}"
        params = {"n": 5}
        
        # Añadir user_id como header si se proporciona
        headers = self.headers.copy()
        if user_id:
            headers["user-id"] = user_id
        
        try:
            # Realizar petición
            start_time = time.time()
            response = requests.get(url, headers=headers, params=params)
            duration = time.time() - start_time
            
            print(f"⏱️  Tiempo de respuesta: {duration:.2f}s")
            print(f"📡 Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                recommendations = data.get("recommendations", [])
                metadata = data.get("metadata", {})
                
                print(f"✅ Recomendaciones recibidas: {len(recommendations)}")
                print(f"🔧 Fuente: {metadata.get('source', 'unknown')}")
                print(f"⚖️  Content weight: {metadata.get('content_weight', 'N/A')}")
                
                # Mostrar primeras 3 recomendaciones
                print(f"\n📋 Primeras recomendaciones:")
                for i, rec in enumerate(recommendations[:3], 1):
                    title = rec.get("title", "Sin título")[:40]
                    score = rec.get("score", 0)
                    rec_id = rec.get("id", "N/A")
                    print(f"   {i}. [{rec_id}] {title}... (Score: {score:.4f})")
                
                return {
                    "success": True,
                    "count": len(recommendations),
                    "recommendations": recommendations,
                    "metadata": metadata,
                    "duration": duration
                }
            else:
                print(f"❌ Error: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Mensaje: {error_data.get('detail', 'Unknown error')}")
                except:
                    print(f"   Respuesta: {response.text}")
                
                return {
                    "success": False,
                    "error": response.status_code,
                    "message": response.text
                }
        
        except Exception as e:
            print(f"💥 Excepción: {str(e)}")
            return {
                "success": False,
                "exception": str(e)
            }
    
    def run_comprehensive_test(self):
        """Ejecuta pruebas comprehensivas para diagnosticar problemas"""
        print("🚀 INICIANDO DIAGNÓSTICO COMPREHENSIVO")
        print("🎯 Objetivo: Identificar por qué las recomendaciones no se personalizan")
        
        # Obtener productos disponibles primero
        print("\n🔍 Obteniendo productos disponibles...")
        try:
            response = requests.get(f"{self.base_url}/v1/products", headers=self.headers, params={"page_size": 10})
            if response.status_code == 200:
                products_data = response.json()
                products = products_data.get("products", [])
                if products:
                    test_product_id = str(products[0].get("id"))
                    print(f"✅ Usando producto de prueba: {test_product_id} - {products[0].get('title', 'Sin título')}")
                else:
                    print("⚠️ No se encontraron productos. Usando ID de prueba.")
                    test_product_id = "9978576896309"  # ID del documento de ejemplo
            else:
                print("⚠️ Error obteniendo productos. Usando ID de prueba.")
                test_product_id = "9978576896309"
        except Exception as e:
            print(f"⚠️ Excepción obteniendo productos: {e}. Usando ID de prueba.")
            test_product_id = "9978576896309"
        
        # Escenarios de prueba
        scenarios = [
            {
                "name": "Sin usuario (anonymous)",
                "product_id": test_product_id,
                "user_id": None
            },
            {
                "name": "Usuario genérico",
                "product_id": test_product_id,
                "user_id": "user123"
            },
            {
                "name": "Usuario específico A",
                "product_id": test_product_id,
                "user_id": "customer_001"
            },
            {
                "name": "Usuario específico B",
                "product_id": test_product_id,
                "user_id": "customer_002"
            },
            {
                "name": "Usuario de prueba",
                "product_id": test_product_id,
                "user_id": "test_user_synthetic"
            }
        ]
        
        # Ejecutar escenarios
        results = []
        for scenario in scenarios:
            result = self.test_scenario(
                scenario["name"],
                scenario["product_id"],
                scenario["user_id"]
            )
            result["scenario"] = scenario
            results.append(result)
            time.sleep(1)  # Evitar saturar el servidor
        
        # Analizar resultados
        print(f"\n{'='*60}")
        print("📊 ANÁLISIS DE RESULTADOS")
        print(f"{'='*60}")
        
        successful_results = [r for r in results if r.get("success")]
        
        if not successful_results:
            print("❌ TODAS las pruebas fallaron")
            return results
        
        # Comparar recomendaciones entre escenarios
        print(f"\n🔍 COMPARACIÓN DE RECOMENDACIONES:")
        
        recommendation_sets = {}
        sources_used = set()
        
        for result in successful_results:
            scenario_name = result["scenario"]["name"]
            recommendations = result.get("recommendations", [])
            rec_ids = [rec.get("id") for rec in recommendations]
            recommendation_sets[scenario_name] = set(rec_ids)
            
            # Analizar fuente de recomendaciones
            source = result.get("metadata", {}).get("source", "unknown")
            sources_used.add(source)
            
            print(f"\n   📋 {scenario_name}:")
            print(f"      Cantidad: {len(recommendations)}")
            print(f"      IDs: {rec_ids[:3]}...")
            print(f"      Fuente: {source}")
        
        # Detectar si las recomendaciones son idénticas
        print(f"\n🎯 DIAGNÓSTICO DETALLADO:")
        print(f"   📡 Fuentes utilizadas: {sources_used}")
        
        all_sets = list(recommendation_sets.values())
        if len(all_sets) > 1:
            sets_identical = all(s == all_sets[0] for s in all_sets[1:])
            
            if sets_identical:
                print("❌ PROBLEMA CONFIRMADO: Todas las recomendaciones son IDÉNTICAS")
                print("   🔍 Posibles causas:")
                
                # Análisis específico basado en la fuente
                if "hybrid_tfidf_redis" in sources_used and len(sources_used) == 1:
                    print("      1. ✅ Sistema híbrido funcionando PERO:")
                    print("      2. ❌ Google Retail API probablemente sin datos de usuario")
                    print("      3. ❌ Fallback a TF-IDF en todos los casos")
                    print("      4. ❌ Sin personalización real activada")
                    print("")
                    print("   💡 SEGÚN DOCUMENTACIÓN SHOPIFY MCP:")
                    print("      • Google Retail API perdió capacidades de eventos de usuario")
                    print("      • Métodos list_user_events() y get_user_events() fueron removidos")
                    print("      • Sistema depende de BigQuery export (latencia 24h)")
                    print("      • Sin datos de usuario = sin personalización")
                
                elif "mcp_aware_hybrid" in sources_used:
                    print("      1. ✅ Sistema MCP funcionando")
                    print("      2. ❌ Shopify MCP no tiene historial de usuario consultable")
                    print("      3. ❌ Solo procesamiento en tiempo real, sin datos históricos")
                
                print("\n   🎯 RECOMENDACIONES DE ACCIÓN:")
                print("      1. 🔄 Migrar a arquitectura híbrida Shopify MCP + Google Retail")
                print("      2. 📊 Implementar captura de eventos en tiempo real")
                print("      3. 💾 Configurar almacenamiento de eventos personalizado")
                print("      4. 🧪 Probar con usuarios que tengan historial registrado")
                
            else:
                print("✅ CORRECTO: Las recomendaciones son DIFERENTES entre usuarios")
                print("   🎉 El sistema está personalizando correctamente")
                
                # Mostrar diferencias
                scenario_names = list(recommendation_sets.keys())
                for i, name1 in enumerate(scenario_names):
                    for name2 in scenario_names[i+1:]:
                        set1, set2 = recommendation_sets[name1], recommendation_sets[name2]
                        intersection = len(set1 & set2)
                        union = len(set1 | set2)
                        similarity = intersection / union if union > 0 else 0
                        print(f"   📊 {name1} vs {name2}: {similarity:.2%} similitud")
        
        return results
    
    def test_user_events(self, user_id: str, product_id: str):
        """Prueba el registro de eventos de usuario"""
        print(f"\n🎯 PROBANDO REGISTRO DE EVENTOS")
        print(f"   User ID: {user_id}")
        print(f"   Product ID: {product_id}")
        
        # Registrar algunos eventos
        events = [
            {"event_type": "detail-page-view", "description": "Vista de producto"},
            {"event_type": "add-to-cart", "description": "Añadir al carrito"},
            {"event_type": "purchase-complete", "description": "Compra completada", "purchase_amount": 99.99}
        ]
        
        for event in events:
            print(f"\n   📝 Registrando: {event['description']}")
            
            url = f"{self.base_url}/v1/events/user/{user_id}"
            params = {
                "event_type": event["event_type"],
                "product_id": product_id
            }
            
            if "purchase_amount" in event:
                params["purchase_amount"] = event["purchase_amount"]
            
            try:
                response = requests.post(url, headers=self.headers, params=params)
                
                if response.status_code == 200:
                    print(f"      ✅ Éxito: {response.status_code}")
                else:
                    print(f"      ❌ Error: {response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"         Mensaje: {error_data.get('detail', 'Unknown error')}")
                    except:
                        print(f"         Respuesta: {response.text}")
                        
            except Exception as e:
                print(f"      💥 Excepción: {str(e)}")
            
            time.sleep(0.5)

def main():
    """Función principal del diagnóstico"""
    print("🔧 HERRAMIENTA DE DIAGNÓSTICO - SISTEMA DE RECOMENDACIONES")
    print("=" * 70)
    
    # Crear instancia del diagnóstico
    diagnostic = RecommendationDiagnostic()
    
    # Ejecutar pruebas comprehensivas
    results = diagnostic.run_comprehensive_test()
    
    # Probar eventos de usuario si se detectan problemas
    successful_results = [r for r in results if r.get("success")]
    if successful_results:
        # Usar el primer resultado exitoso para probar eventos
        test_scenario = successful_results[0]["scenario"]
        product_id = test_scenario["product_id"]
        
        print(f"\n🧪 PROBANDO EVENTOS DE USUARIO...")
        diagnostic.test_user_events("test_diagnostic_user", product_id)
        
        # Esperar un poco y probar recomendaciones nuevamente
        print(f"\n⏳ Esperando 5 segundos para que se procesen los eventos...")
        time.sleep(5)
        
        print(f"\n🔄 REPROBANDO RECOMENDACIONES DESPUÉS DE EVENTOS...")
        new_result = diagnostic.test_scenario(
            "Usuario con eventos registrados",
            product_id,
            "test_diagnostic_user"
        )
        
        if new_result.get("success"):
            print(f"\n📊 COMPARACIÓN PRE/POST EVENTOS:")
            original = successful_results[0]
            original_ids = set(rec.get("id") for rec in original.get("recommendations", []))
            new_ids = set(rec.get("id") for rec in new_result.get("recommendations", []))
            
            if original_ids != new_ids:
                print("✅ Las recomendaciones CAMBIARON después de registrar eventos")
                print("   🎉 El sistema está aprendiendo de los eventos de usuario")
            else:
                print("⚠️ Las recomendaciones NO cambiaron después de registrar eventos")
                print("   🔍 Posibles causas:")
                print("      1. Los eventos tardan más en procesarse")
                print("      2. Google Cloud Retail API requiere más datos")
                print("      3. El sistema no está conectado correctamente")
    
    # Resumen final
    print(f"\n{'='*70}")
    print("📋 RESUMEN EJECUTIVO")
    print(f"{'='*70}")
    
    total_tests = len(results)
    successful_tests = len(successful_results)
    
    print(f"🎯 Pruebas ejecutadas: {total_tests}")
    print(f"✅ Pruebas exitosas: {successful_tests}")
    print(f"❌ Pruebas fallidas: {total_tests - successful_tests}")
    
    if successful_tests == 0:
        print(f"\n🚨 CRÍTICO: El sistema no está funcionando")
        print("   📋 Acciones recomendadas:")
        print("      1. Verificar que el servidor esté ejecutándose")
        print("      2. Comprobar la API key")
        print("      3. Revisar logs del servidor")
    
    elif successful_tests > 0:
        # Analizar si hay personalización
        if len(successful_results) > 1:
            recommendation_sets = {}
            for result in successful_results:
                scenario_name = result["scenario"]["name"]
                recommendations = result.get("recommendations", [])
                rec_ids = tuple(rec.get("id") for rec in recommendations)  # tuple para hashable
                recommendation_sets[scenario_name] = rec_ids
            
            unique_sets = set(recommendation_sets.values())
            
            if len(unique_sets) == 1:
                print(f"\n❌ PROBLEMA: No hay personalización")
                print("   📋 Acciones recomendadas:")
                print("      1. Revisar logs del servidor con logging detallado activado")
                print("      2. Verificar conexión con Google Cloud Retail API")
                print("      3. Comprobar si hay eventos de usuario registrados")
                print("      4. Verificar configuración de content_weight")
                print("      5. Probar registrar eventos y esperar más tiempo")
            else:
                print(f"\n✅ ÉXITO: El sistema está personalizando correctamente")
                print(f"   🎉 Se detectaron {len(unique_sets)} patrones diferentes de recomendaciones")
        
        # Mostrar métricas de rendimiento
        durations = [r.get("duration", 0) for r in successful_results if r.get("duration")]
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            min_duration = min(durations)
            
            print(f"\n⏱️ RENDIMIENTO:")
            print(f"   📊 Tiempo promedio: {avg_duration:.2f}s")
            print(f"   📈 Tiempo máximo: {max_duration:.2f}s")
            print(f"   📉 Tiempo mínimo: {min_duration:.2f}s")
            
            if avg_duration > 2.0:
                print("   ⚠️ Tiempos de respuesta altos detectados")
            else:
                print("   ✅ Tiempos de respuesta aceptables")
    
    print(f"\n🏁 DIAGNÓSTICO COMPLETADO")
    print("💡 Tip: Ejecuta este script después de hacer cambios para verificar mejoras")
    
    return results

if __name__ == "__main__":
    main()