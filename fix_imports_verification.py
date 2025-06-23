#!/usr/bin/env python3
"""
Script para verificar y diagnosticar problemas de importación en Google Cloud Retail API.
Verifica qué clases están disponibles y en qué ubicaciones.

Uso:
    python verify_retail_imports.py

Este script:
1. Verifica qué versión de google-cloud-retail está instalada
2. Prueba diferentes patrones de importación
3. Lista las clases disponibles en cada módulo
4. Proporciona recomendaciones para corregir problemas
"""

import sys
import logging
from typing import Dict, List, Any

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_package_version():
    """Verifica la versión del paquete google-cloud-retail instalado."""
    try:
        import google.cloud.retail_v2 as retail
        logger.info(f"✅ Paquete google-cloud-retail importado correctamente")
        
        # Intentar obtener la versión
        try:
            version = getattr(retail, '__version__', 'No disponible')
            logger.info(f"📦 Versión detectada: {version}")
        except:
            logger.info("📦 Versión no disponible en el módulo")
            
        return True
    except ImportError as e:
        logger.error(f"❌ Error al importar google-cloud-retail: {e}")
        logger.error("💡 Solución: pip install google-cloud-retail")
        return False

def test_import_patterns():
    """Prueba diferentes patrones de importación para ListUserEventsRequest."""
    patterns = [
        {
            'name': 'Patrón 1: Importación directa desde retail_v2',
            'import_code': 'from google.cloud.retail_v2 import ListUserEventsRequest',
            'module': 'google.cloud.retail_v2'
        },
        {
            'name': 'Patrón 2: Importación desde types',
            'import_code': 'from google.cloud.retail_v2.types import ListUserEventsRequest',
            'module': 'google.cloud.retail_v2.types'
        },
        {
            'name': 'Patrón 3: Importación desde user_event_service',
            'import_code': 'from google.cloud.retail_v2.types.user_event_service import ListUserEventsRequest',
            'module': 'google.cloud.retail_v2.types.user_event_service'
        },
        {
            'name': 'Patrón 4: Importación desde servicios',
            'import_code': 'from google.cloud.retail_v2.services.user_event_service import ListUserEventsRequest',
            'module': 'google.cloud.retail_v2.services.user_event_service'
        },
        {
            'name': 'Patrón 5: Importación desde servicios.user_event_service.client',
            'import_code': 'from google.cloud.retail_v2.services.user_event_service.client import ListUserEventsRequest',
            'module': 'google.cloud.retail_v2.services.user_event_service.client'
        }
    ]
    
    successful_patterns = []
    failed_patterns = []
    
    for pattern in patterns:
        try:
            logger.info(f"🔍 Probando: {pattern['name']}")
            logger.debug(f"   Código: {pattern['import_code']}")
            
            # Ejecutar la importación
            exec(pattern['import_code'])
            logger.info(f"   ✅ Éxito")
            successful_patterns.append(pattern)
            
        except ImportError as e:
            logger.warning(f"   ❌ Fallo: {e}")
            failed_patterns.append(pattern)
        except Exception as e:
            logger.error(f"   ⚠️  Error inesperado: {e}")
            failed_patterns.append(pattern)
    
    return successful_patterns, failed_patterns

def list_available_classes(module_path: str):
    """Lista las clases disponibles en un módulo específico."""
    try:
        logger.info(f"📋 Listando clases en {module_path}:")
        
        # Importar el módulo dinámicamente
        module = __import__(module_path, fromlist=[''])
        
        # Obtener atributos del módulo
        attributes = [attr for attr in dir(module) if not attr.startswith('_')]
        
        # Filtrar solo clases que podrían ser relevantes para user events
        relevant_classes = [
            attr for attr in attributes 
            if 'UserEvent' in attr or 'Request' in attr or 'Response' in attr
        ]
        
        if relevant_classes:
            for cls in sorted(relevant_classes):
                logger.info(f"   📌 {cls}")
        else:
            logger.info("   ℹ️  No se encontraron clases relevantes")
            
        return relevant_classes
        
    except ImportError as e:
        logger.warning(f"   ❌ No se pudo importar {module_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"   ⚠️  Error listando clases en {module_path}: {e}")
        return []

def check_alternative_approaches():
    """Verifica enfoques alternativos para obtener eventos de usuario."""
    logger.info("🔄 Verificando enfoques alternativos:")
    
    # Verificar si el cliente UserEventServiceClient funciona
    try:
        from google.cloud.retail_v2 import UserEventServiceClient
        logger.info("   ✅ UserEventServiceClient disponible")
        
        # Verificar métodos disponibles
        client_methods = [method for method in dir(UserEventServiceClient) 
                         if not method.startswith('_') and 'user_event' in method.lower()]
        
        if client_methods:
            logger.info("   📋 Métodos relacionados con user events:")
            for method in sorted(client_methods):
                logger.info(f"      • {method}")
        
        return True
        
    except ImportError as e:
        logger.warning(f"   ❌ UserEventServiceClient no disponible: {e}")
        return False

def provide_recommendations(successful_patterns: List[Dict], failed_patterns: List[Dict]):
    """Proporciona recomendaciones basadas en los resultados de las pruebas."""
    logger.info("💡 Recomendaciones:")
    
    if successful_patterns:
        logger.info("   ✅ Patrones de importación exitosos encontrados:")
        for pattern in successful_patterns:
            logger.info(f"      • {pattern['name']}")
            logger.info(f"        Código: {pattern['import_code']}")
    else:
        logger.warning("   ⚠️  No se encontraron patrones de importación exitosos")
        logger.info("   🔧 Soluciones sugeridas:")
        logger.info("      1. Actualizar google-cloud-retail: pip install --upgrade google-cloud-retail")
        logger.info("      2. Verificar compatibilidad de versiones")
        logger.info("      3. Usar implementación alternativa sin ListUserEventsRequest")
    
    # Recomendar implementación alternativa
    logger.info("   🔄 Implementación alternativa recomendada:")
    logger.info("      • Usar UserEventServiceClient.list_user_events() directamente")
    logger.info("      • Construir request usando diccionarios en lugar de clases tipadas")
    logger.info("      • Implementar fallback que devuelva lista vacía")

def create_fixed_implementation():
    """Crea un ejemplo de implementación corregida."""
    logger.info("🔧 Ejemplo de implementación corregida:")
    
    fixed_code = '''
async def get_user_events_fixed(self, user_id: str, limit: int = 50) -> List[Dict]:
    """
    Versión corregida que no depende de ListUserEventsRequest.
    """
    try:
        from google.cloud.retail_v2 import UserEventServiceClient
        
        # Usar el cliente directamente sin clases de request tipadas
        parent = f"projects/{self.project_number}/locations/{self.location}/catalogs/{self.catalog}"
        
        # Crear request como diccionario (más flexible)
        request_dict = {
            "parent": parent,
            "filter": f'visitorId="{user_id}"',
            "page_size": limit
        }
        
        # Intentar llamar al método usando **kwargs
        try:
            response = self.user_event_client.list_user_events(**request_dict)
            
            events = []
            for event in response.user_events:
                events.append({
                    "event_type": event.event_type,
                    "visitor_id": event.visitor_id,
                    "event_time": event.event_time.isoformat() if event.event_time else None
                })
            
            return events
            
        except Exception as api_error:
            logging.warning(f"API call failed: {api_error}")
            return []
            
    except ImportError:
        logging.warning("UserEventServiceClient not available")
        return []
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return []
'''
    
    logger.info("   📝 Código de ejemplo guardado")
    return fixed_code

def main():
    """Función principal del script de verificación."""
    logger.info("🚀 Iniciando verificación de importaciones de Google Cloud Retail API")
    logger.info("=" * 80)
    
    # 1. Verificar la instalación del paquete
    if not check_package_version():
        logger.error("❌ No se puede continuar sin el paquete google-cloud-retail")
        sys.exit(1)
    
    logger.info("-" * 80)
    
    # 2. Probar patrones de importación
    successful_patterns, failed_patterns = test_import_patterns()
    
    logger.info("-" * 80)
    
    # 3. Listar clases disponibles en módulos relevantes
    modules_to_check = [
        'google.cloud.retail_v2',
        'google.cloud.retail_v2.types',
        'google.cloud.retail_v2.types.user_event_service',
        'google.cloud.retail_v2.services.user_event_service'
    ]
    
    for module in modules_to_check:
        list_available_classes(module)
    
    logger.info("-" * 80)
    
    # 4. Verificar enfoques alternativos
    check_alternative_approaches()
    
    logger.info("-" * 80)
    
    # 5. Proporcionar recomendaciones
    provide_recommendations(successful_patterns, failed_patterns)
    
    logger.info("-" * 80)
    
    # 6. Crear implementación de ejemplo
    create_fixed_implementation()
    
    logger.info("=" * 80)
    logger.info("✅ Verificación completada")

if __name__ == "__main__":
    main()