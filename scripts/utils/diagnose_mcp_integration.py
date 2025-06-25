#!/usr/bin/env python3
"""
Script de diagnóstico para verificar la integración MCP.
Verifica que todos los componentes estén correctamente configurados antes de ejecutar las pruebas.

Uso:
    python diagnose_mcp_integration.py

Este script:
1. Verifica importaciones y dependencias
2. Prueba la creación de componentes MCP
3. Valida la configuración del sistema
4. Proporciona recomendaciones de corrección
"""

import sys
import logging
import traceback
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_python_path():
    """Verifica que el path de Python incluya el directorio src."""
    current_dir = Path(__file__).parent.absolute()
    src_dir = current_dir / "src"
    
    if str(src_dir) not in sys.path:
        print(f"📁 Agregando {src_dir} al Python path")
        sys.path.insert(0, str(src_dir))
    else:
        print("✅ Python path configurado correctamente")

def check_imports():
    """Verifica que todas las importaciones necesarias funcionen."""
    print("\n🔍 Verificando importaciones...")
    
    imports_to_check = [
        ("src.api.factories", "MCPFactory"),
        ("src.api.factories", "RecommenderFactory"),
        ("src.recommenders.mcp_aware_hybrid", "MCPAwareHybridRecommender"),
        ("src.api.mcp.client.mcp_client", "MCPClient"),
        ("src.api.core.config", "get_settings"),
    ]
    
    failed_imports = []
    
    for module_name, class_name in imports_to_check:
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)
            print(f"   ✅ {module_name}.{class_name}")
        except ImportError as e:
            print(f"   ❌ {module_name}.{class_name}: {e}")
            failed_imports.append((module_name, class_name, str(e)))
        except AttributeError as e:
            print(f"   ❌ {module_name}.{class_name}: Clase no encontrada")
            failed_imports.append((module_name, class_name, f"Clase no encontrada: {e}"))
    
    return failed_imports

def check_configuration():
    """Verifica la configuración del sistema."""
    print("\n⚙️  Verificando configuración...")
    
    try:
        from src.api.core.config import get_settings
        settings = get_settings()
        
        # Verificar configuraciones MCP relevantes
        config_checks = [
            ("use_redis_cache", getattr(settings, 'use_redis_cache', False)),
            ("google_project_number", getattr(settings, 'google_project_number', None)),
            ("google_location", getattr(settings, 'google_location', 'global')),
            ("google_catalog", getattr(settings, 'google_catalog', 'default_catalog')),
        ]
        
        for config_name, config_value in config_checks:
            status = "✅" if config_value else "⚠️ "
            print(f"   {status} {config_name}: {config_value}")
            
        return True
        
    except Exception as e:
        print(f"   ❌ Error cargando configuración: {e}")
        return False

def test_mcp_factory_components():
    """Prueba la creación de componentes MCP individuales."""
    print("\n🧪 Probando creación de componentes MCP...")
    
    try:
        from src.api.factories import MCPFactory
        
        # Probar cada componente individualmente
        components = [
            ("MCP Client", MCPFactory.create_mcp_client),
            ("Market Manager", MCPFactory.create_market_manager),
            ("Market Cache", MCPFactory.create_market_cache),
        ]
        
        results = {}
        
        for component_name, factory_method in components:
            try:
                print(f"   🔧 Creando {component_name}...")
                component = factory_method()
                
                if component:
                    print(f"   ✅ {component_name}: Creado exitosamente")
                    results[component_name] = {"status": "success", "component": component}
                else:
                    print(f"   ⚠️  {component_name}: Creado pero es None (posible configuración faltante)")
                    results[component_name] = {"status": "warning", "component": None}
                    
            except Exception as e:
                print(f"   ❌ {component_name}: Error - {e}")
                results[component_name] = {"status": "error", "error": str(e)}
        
        return results
        
    except Exception as e:
        print(f"   ❌ Error importando MCPFactory: {e}")
        return {}

def test_recommender_factory_components():
    """Prueba la creación de componentes base del RecommenderFactory."""
    print("\n🔧 Probando componentes base del RecommenderFactory...")
    
    try:
        from src.api.factories import RecommenderFactory
        
        # Probar componentes base
        base_components = [
            ("Content Recommender", RecommenderFactory.create_content_recommender),
            ("Retail Recommender", RecommenderFactory.create_retail_recommender),
        ]
        
        results = {}
        
        for component_name, factory_method in base_components:
            try:
                print(f"   🔧 Creando {component_name}...")
                component = factory_method()
                
                if component:
                    print(f"   ✅ {component_name}: Creado exitosamente")
                    results[component_name] = {"status": "success", "component": component}
                else:
                    print(f"   ❌ {component_name}: Error en creación")
                    results[component_name] = {"status": "error", "component": None}
                    
            except Exception as e:
                print(f"   ❌ {component_name}: Error - {e}")
                results[component_name] = {"status": "error", "error": str(e)}
        
        return results
        
    except Exception as e:
        print(f"   ❌ Error importando RecommenderFactory: {e}")
        return {}

def test_mcp_recommender_creation():
    """Prueba la creación del MCPAwareHybridRecommender completo."""
    print("\n🎯 Probando creación del MCP Recommender completo...")
    
    try:
        from src.api.factories import MCPFactory
        
        print("   🔧 Ejecutando MCPFactory.create_mcp_recommender()...")
        mcp_recommender = MCPFactory.create_mcp_recommender()
        
        if mcp_recommender:
            print("   ✅ MCPAwareHybridRecommender creado exitosamente!")
            
            # Verificar capacidades
            if hasattr(mcp_recommender, 'get_metrics'):
                try:
                    metrics = mcp_recommender.get_metrics()
                    print(f"   📊 Métricas iniciales: {metrics}")
                except Exception as e:
                    print(f"   ⚠️  Error obteniendo métricas: {e}")
            
            return {"status": "success", "recommender": mcp_recommender}
        else:
            print("   ❌ MCPAwareHybridRecommender es None")
            return {"status": "error", "error": "Recommender es None"}
            
    except Exception as e:
        print(f"   ❌ Error creando MCP Recommender: {e}")
        print(f"   📝 Traceback: {traceback.format_exc()}")
        return {"status": "error", "error": str(e)}

def test_api_factory_functions():
    """Prueba las funciones factory del router."""
    print("\n🌐 Probando funciones factory del API router...")
    
    try:
        # Simular las importaciones del router
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        
        # Importar y probar las funciones como lo hace el router
        from src.api.factories import MCPFactory
        
        router_functions = [
            ("get_mcp_client", MCPFactory.create_mcp_client),
            ("get_market_manager", MCPFactory.create_market_manager),
            ("get_market_cache", MCPFactory.create_market_cache),
            ("get_mcp_recommender", MCPFactory.create_mcp_recommender),
        ]
        
        results = {}
        
        for func_name, factory_method in router_functions:
            try:
                print(f"   🔧 Probando {func_name}()...")
                result = factory_method()
                
                if result:
                    print(f"   ✅ {func_name}(): Exitoso")
                    results[func_name] = {"status": "success"}
                else:
                    print(f"   ⚠️  {func_name}(): Retorna None")
                    results[func_name] = {"status": "warning"}
                    
            except Exception as e:
                print(f"   ❌ {func_name}(): Error - {e}")
                results[func_name] = {"status": "error", "error": str(e)}
        
        return results
        
    except Exception as e:
        print(f"   ❌ Error en pruebas de router: {e}")
        return {}

def provide_recommendations(failed_imports, config_ok, component_results, recommender_result):
    """Proporciona recomendaciones basadas en los resultados del diagnóstico."""
    print("\n💡 Recomendaciones:")
    
    if failed_imports:
        print("\n   📦 Problemas de importación detectados:")
        for module, class_name, error in failed_imports:
            print(f"      • {module}.{class_name}: {error}")
        print("   ➡️  Acción: Verificar instalación de dependencias y estructura de archivos")
    
    if not config_ok:
        print("\n   ⚙️  Problemas de configuración detectados:")
        print("   ➡️  Acción: Revisar variables de entorno y configuración")
    
    # Analizar resultados de componentes
    mcp_components_ok = all(
        result.get("status") in ["success", "warning"] 
        for result in component_results.values()
    )
    
    if not mcp_components_ok:
        print("\n   🧩 Problemas en componentes MCP:")
        for component, result in component_results.items():
            if result.get("status") == "error":
                print(f"      • {component}: {result.get('error', 'Error desconocido')}")
        print("   ➡️  Acción: Verificar dependencias de Redis y configuración MCP")
    
    if recommender_result.get("status") == "error":
        print("\n   🎯 Problema en MCP Recommender:")
        print(f"      • Error: {recommender_result.get('error')}")
        print("   ➡️  Acción: Este es el error principal que está afectando las pruebas")
    
    # Recomendaciones generales
    print("\n   ✅ Próximos pasos sugeridos:")
    print("      1. Corregir errores de importación si los hay")
    print("      2. Verificar que Redis esté funcionando (si use_redis_cache=True)")
    print("      3. Ejecutar las pruebas MCP: python tests/mcp/test_mcp_bridge.py")
    print("      4. Verificar logs del servidor API para errores adicionales")

def main():
    """Función principal del diagnóstico."""
    print("🚀 Diagnóstico de Integración MCP")
    print("=" * 50)
    
    # 1. Configurar Python path
    check_python_path()
    
    # 2. Verificar importaciones
    failed_imports = check_imports()
    
    # 3. Verificar configuración
    config_ok = check_configuration()
    
    # 4. Probar componentes base
    base_results = test_recommender_factory_components()
    
    # 5. Probar componentes MCP
    mcp_results = test_mcp_factory_components()
    
    # 6. Probar creación del recomendador completo
    recommender_result = test_mcp_recommender_creation()
    
    # 7. Probar funciones del router
    router_results = test_api_factory_functions()
    
    # 8. Resumen y recomendaciones
    print("\n" + "=" * 50)
    print("📋 Resumen del diagnóstico:")
    
    total_issues = len(failed_imports)
    if not config_ok:
        total_issues += 1
    
    mcp_issues = sum(1 for r in mcp_results.values() if r.get("status") == "error")
    total_issues += mcp_issues
    
    if recommender_result.get("status") == "error":
        total_issues += 1
    
    if total_issues == 0:
        print("✅ ¡Todos los componentes funcionan correctamente!")
        print("   ➡️  Puedes ejecutar las pruebas MCP con confianza")
    else:
        print(f"⚠️  Se detectaron {total_issues} problemas")
        provide_recommendations(failed_imports, config_ok, mcp_results, recommender_result)
    
    print("\n🎯 Diagnóstico completado")

if __name__ == "__main__":
    main()
