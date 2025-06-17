#!/usr/bin/env python
"""
Script de verificación para validar las correcciones implementadas.

Este script verifica específicamente:
1. La importación correcta de los módulos de la arquitectura unificada
2. La existencia de las clases necesarias para las pruebas
3. La correcta configuración de la autenticación para pruebas
"""

import sys
import os
import importlib
import inspect
from typing import List, Dict, Any, Tuple
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_module_imports() -> List[Dict[str, Any]]:
    """
    Verifica la importación de módulos clave.
    
    Returns:
        List[Dict]: Lista de resultados de verificación
    """
    results = []
    
    # Lista de módulos a verificar
    modules_to_verify = [
        {"name": "src.api.core.hybrid_recommender", "classes": ["HybridRecommender", "HybridRecommenderWithExclusion"]},
        {"name": "src.api.factories", "classes": ["RecommenderFactory"]},
        {"name": "src.api.security", "functions": ["get_api_key", "get_current_user"]},
    ]
    
    for module_info in modules_to_verify:
        module_name = module_info["name"]
        try:
            # Intentar importar el módulo
            module = importlib.import_module(module_name)
            
            # Verificar clases si están especificadas
            missing_classes = []
            if "classes" in module_info:
                for class_name in module_info["classes"]:
                    if not hasattr(module, class_name):
                        missing_classes.append(class_name)
            
            # Verificar funciones si están especificadas
            missing_functions = []
            if "functions" in module_info:
                for func_name in module_info["functions"]:
                    if not hasattr(module, func_name):
                        missing_functions.append(func_name)
            
            # Registrar resultados
            results.append({
                "module": module_name,
                "imported": True,
                "missing_classes": missing_classes,
                "missing_functions": missing_functions,
                "status": "PASS" if not missing_classes and not missing_functions else "WARN"
            })
            
        except ImportError as e:
            results.append({
                "module": module_name,
                "imported": False,
                "error": str(e),
                "status": "FAIL"
            })
    
    # Verificar también que src.recommenders.hybrid NO exista (para confirmar eliminación)
    try:
        importlib.import_module("src.recommenders.hybrid")
        results.append({
            "module": "src.recommenders.hybrid",
            "imported": True,
            "status": "WARN",
            "message": "Este módulo debería haber sido eliminado en la migración a arquitectura unificada"
        })
    except ImportError:
        results.append({
            "module": "src.recommenders.hybrid",
            "imported": False,
            "status": "PASS",
            "message": "Módulo correctamente eliminado como parte de la migración"
        })
    
    return results

def verify_factories_implementation() -> Dict[str, Any]:
    """
    Verifica la implementación específica de las fábricas.
    
    Returns:
        Dict: Resultado de la verificación
    """
    try:
        from src.api.factories import RecommenderFactory
        
        # Verificar que el método create_hybrid_recommender existe
        if not hasattr(RecommenderFactory, "create_hybrid_recommender"):
            return {
                "status": "FAIL",
                "message": "Método create_hybrid_recommender no encontrado en RecommenderFactory"
            }
        
        # Obtener el código fuente del método
        source = inspect.getsource(RecommenderFactory.create_hybrid_recommender)
        
        # Verificar si intenta importar desde src.recommenders.hybrid
        if "from src.recommenders.hybrid import" in source:
            return {
                "status": "WARN",
                "message": "El método create_hybrid_recommender todavía intenta importar desde src.recommenders.hybrid"
            }
        
        return {
            "status": "PASS",
            "message": "Implementación de fábricas correcta para arquitectura unificada"
        }
        
    except ImportError as e:
        return {
            "status": "FAIL",
            "message": f"No se pudo importar RecommenderFactory: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "FAIL",
            "message": f"Error verificando implementación de fábricas: {str(e)}"
        }

def verify_test_client_no_auth() -> Dict[str, Any]:
    """
    Verifica la implementación del fixture test_client_no_auth.
    
    Returns:
        Dict: Resultado de la verificación
    """
    try:
        # Verificar el archivo conftest.py
        with open("tests/conftest.py", "r", encoding="utf-8") as f:
            conftest_content = f.read()
        
        # Verificar que se esté forzando el código 403
        if "HTTPException(status_code=403" not in conftest_content:
            return {
                "status": "WARN",
                "message": "El fixture test_client_no_auth podría no estar forzando un error 403 correctamente"
            }
        
        # Verificar que se estén limpiando los headers
        if "headers.clear()" not in conftest_content and "del client.headers" not in conftest_content:
            return {
                "status": "WARN",
                "message": "El fixture test_client_no_auth no parece limpiar los headers del cliente"
            }
        
        # Verificar que se estén aplicando los overrides correctamente
        if "dependency_overrides[get_api_key]" not in conftest_content:
            return {
                "status": "WARN",
                "message": "El fixture test_client_no_auth no parece aplicar el override para get_api_key"
            }
        
        return {
            "status": "PASS",
            "message": "Fixture test_client_no_auth implementado correctamente"
        }
        
    except FileNotFoundError:
        return {
            "status": "FAIL",
            "message": "No se encontró el archivo tests/conftest.py"
        }
    except Exception as e:
        return {
            "status": "FAIL",
            "message": f"Error verificando fixture test_client_no_auth: {str(e)}"
        }

def verify_test_factories() -> Dict[str, Any]:
    """
    Verifica los tests de fábricas.
    
    Returns:
        Dict: Resultado de la verificación
    """
    try:
        # Verificar el archivo test_factories.py
        with open("tests/unit/test_factories.py", "r", encoding="utf-8") as f:
            test_factories_content = f.read()
        
        # Verificar que no se use src.recommenders.hybrid
        if "src.recommenders.hybrid" in test_factories_content:
            if "patch('src.recommenders.hybrid" in test_factories_content:
                return {
                    "status": "WARN",
                    "message": "test_factories.py todavía contiene referencias a src.recommenders.hybrid en patches"
                }
        
        # Verificar test_create_hybrid_recommender_fallback
        if "pytest.raises(ImportError)" not in test_factories_content:
            return {
                "status": "WARN",
                "message": "test_create_hybrid_recommender_fallback no parece verificar que se lance ImportError"
            }
        
        # Verificar que los parametros se muestran correctamente
        hybrid_test_count = test_factories_content.count("mock_hybrid_with_exclusion.assert_called_once_with")
        if hybrid_test_count == 0:
            return {
                "status": "WARN",
                "message": "No se encontró validación de llamada a mock_hybrid_with_exclusion.assert_called_once_with"
            }
        
        # Verificar que se incluye product_cache en la verificación
        if "product_cache=None" not in test_factories_content:
            return {
                "status": "WARN",
                "message": "Los tests no parecen verificar el parámetro product_cache"
            }
        
        return {
            "status": "PASS",
            "message": "Tests de fábricas implementados correctamente"
        }
        
    except FileNotFoundError:
        return {
            "status": "FAIL",
            "message": "No se encontró el archivo tests/unit/test_factories.py"
        }
    except Exception as e:
        return {
            "status": "FAIL",
            "message": f"Error verificando tests de fábricas: {str(e)}"
        }

def run_verifications() -> Tuple[bool, Dict[str, Any]]:
    """
    Ejecuta todas las verificaciones.
    
    Returns:
        Tuple[bool, Dict]: Estado global (True si todo ok) y resultados detallados
    """
    all_passed = True
    results = {}
    
    # Verificar importaciones
    logger.info("Verificando importaciones de módulos...")
    imports_results = verify_module_imports()
    results["imports"] = imports_results
    
    for result in imports_results:
        if result["status"] == "FAIL":
            all_passed = False
            logger.error(f"❌ Error en módulo {result['module']}: {result.get('error', 'No importado')}")
        elif result["status"] == "WARN":
            logger.warning(f"⚠️ Advertencia en módulo {result['module']}: {result.get('message', '')}")
        else:
            logger.info(f"✅ Módulo {result['module']} verificado correctamente")
    
    # Verificar implementación de fábricas
    logger.info("\nVerificando implementación de fábricas...")
    factories_result = verify_factories_implementation()
    results["factories"] = factories_result
    
    if factories_result["status"] == "FAIL":
        all_passed = False
        logger.error(f"❌ Error en fábricas: {factories_result['message']}")
    elif factories_result["status"] == "WARN":
        logger.warning(f"⚠️ Advertencia en fábricas: {factories_result['message']}")
    else:
        logger.info(f"✅ Implementación de fábricas verificada correctamente")
    
    # Verificar fixture test_client_no_auth
    logger.info("\nVerificando fixture test_client_no_auth...")
    client_result = verify_test_client_no_auth()
    results["test_client_no_auth"] = client_result
    
    if client_result["status"] == "FAIL":
        all_passed = False
        logger.error(f"❌ Error en fixture test_client_no_auth: {client_result['message']}")
    elif client_result["status"] == "WARN":
        logger.warning(f"⚠️ Advertencia en fixture test_client_no_auth: {client_result['message']}")
    else:
        logger.info(f"✅ Fixture test_client_no_auth verificado correctamente")
    
    # Verificar tests de fábricas
    logger.info("\nVerificando tests de fábricas...")
    test_factories_result = verify_test_factories()
    results["test_factories"] = test_factories_result
    
    if test_factories_result["status"] == "FAIL":
        all_passed = False
        logger.error(f"❌ Error en tests de fábricas: {test_factories_result['message']}")
    elif test_factories_result["status"] == "WARN":
        logger.warning(f"⚠️ Advertencia en tests de fábricas: {test_factories_result['message']}")
    else:
        logger.info(f"✅ Tests de fábricas verificados correctamente")
    
    # Resumen
    if all_passed:
        logger.info("\n✅ Todas las verificaciones pasaron correctamente")
    else:
        logger.error("\n❌ Algunas verificaciones fallaron. Revisa los errores anteriores.")
    
    return all_passed, results

if __name__ == "__main__":
    logger.info("Iniciando verificación de correcciones...")
    success, _ = run_verifications()
    sys.exit(0 if success else 1)
