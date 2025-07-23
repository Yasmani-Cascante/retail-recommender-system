#!/usr/bin/env python3
"""
Patch aplicator para correcciones críticas en MCP Router
=======================================================

Este script aplica las correcciones críticas de conversión de moneda
y traducción directamente al router MCP existente.
"""

import os
import re
import shutil
from datetime import datetime

def apply_critical_patches():
    """Aplica las correcciones críticas al router MCP"""
    
    router_path = r"C:\Users\yasma\Desktop\retail-recommender-system\src\api\routers\mcp_router.py"
    backup_path = f"{router_path}.backup_{int(datetime.now().timestamp())}"
    
    try:
        # 1. Crear backup
        shutil.copy2(router_path, backup_path)
        print(f"✅ Backup creado: {backup_path}")
        
        # 2. Leer archivo original
        with open(router_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 3. Aplicar parches
        patched_content = apply_patches_to_content(content)
        
        # 4. Escribir archivo modificado
        with open(router_path, 'w', encoding='utf-8') as f:
            f.write(patched_content)
        
        print(f"✅ Parches aplicados exitosamente a {router_path}")
        print("✅ Correcciones críticas implementadas:")
        print("   - Conversión automática COP -> USD")
        print("   - Traducción básica español -> inglés")
        print("   - Validación de estructura de datos")
        
        return True
        
    except Exception as e:
        print(f"❌ Error aplicando parches: {e}")
        # Restaurar backup si existe
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, router_path)
            print(f"✅ Backup restaurado")
        return False

def apply_patches_to_content(content: str) -> str:
    """
    Aplica las modificaciones de parche al contenido del archivo.
    
    Args:
        content: Contenido original del archivo
        
    Returns:
        Contenido modificado con parches aplicados
    """
    
    # PATCH 1: Agregar imports de las utilidades de mercado
    import_patch = '''
# 🔧 CRITICAL MARKET ADAPTATIONS IMPORTS
from src.api.utils.market_adaptations_patch import apply_market_adaptations
from src.api.utils.market_processor import get_processing_stats
'''
    
    # Buscar la línea de imports y agregar nuestros imports
    logger_import_pattern = r'(logger = logging\.getLogger\(__name__\))'
    content = re.sub(
        logger_import_pattern,
        f'{import_patch}\n\\1',
        content,
        count=1
    )
    
    # PATCH 2: Modificar la función que transforma recomendaciones
    transform_function_patch = '''
        # 🔧 CORRECCIÓN CRÍTICA: Aplicar adaptaciones de mercado antes de transformar
        try:
            # Aplicar correcciones de moneda y traducción
            market_adapted_recommendations = apply_market_adaptations(
                recommendations=safe_recommendations,
                market_id=conversation.market_id,
                user_query=conversation.query,
                source="mcp_conversation_endpoint"
            )
            
            # Usar recomendaciones adaptadas en lugar de las originales
            safe_recommendations = market_adapted_recommendations
            logger.info(f"✅ Aplicadas adaptaciones de mercado: {len(safe_recommendations)} productos procesados")
            
        except Exception as adaptation_error:
            logger.error(f"❌ Error en adaptaciones de mercado: {adaptation_error}")
            # Continuar con recomendaciones originales si falla la adaptación
            pass
'''
    
    # Buscar donde se procesan las recomendaciones y agregar el parche
    recommendation_processing_pattern = r'(# Aplicar transformación segura a todas las recomendaciones\s+safe_recommendations = \[\])'
    content = re.sub(
        recommendation_processing_pattern,
        f'{transform_function_patch}\n\n\\1',
        content,
        count=1,
        flags=re.MULTILINE | re.DOTALL
    )
    
    # PATCH 3: Agregar endpoint para estadísticas de adaptación
    stats_endpoint_patch = '''

@router.get("/market/adaptation-stats", response_model=Dict)
async def get_market_adaptation_stats(
    current_user: str = Depends(get_current_user)
):
    """
    🔧 NUEVO ENDPOINT: Obtiene estadísticas de adaptaciones de mercado aplicadas
    """
    try:
        from src.api.utils.market_processor import get_processing_stats
        
        stats = get_processing_stats()
        
        return {
            "status": "success",
            "adaptation_stats": stats,
            "timestamp": time.time(),
            "message": "Market adaptation statistics retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error getting adaptation stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving adaptation stats: {str(e)}"
        )
'''
    
    # Agregar el endpoint al final del archivo, antes del último comentario o función
    content = content.rstrip() + stats_endpoint_patch + '\n'
    
    return content

if __name__ == "__main__":
    print("🔧 Aplicando correcciones críticas al Router MCP...")
    success = apply_critical_patches()
    
    if success:
        print("\n✅ CORRECCIONES APLICADAS EXITOSAMENTE")
        print("\n🎯 CAMBIOS REALIZADOS:")
        print("1. ✅ Conversión automática de precios COP -> USD para mercado US")
        print("2. ✅ Traducción básica de títulos y descripciones español -> inglés")
        print("3. ✅ Validación y limpieza de estructura de datos")
        print("4. ✅ Logging mejorado para debugging")
        print("5. ✅ Endpoint nuevo: /v1/mcp/market/adaptation-stats")
        print("\n🚀 PRÓXIMO PASO: Reinicia el servidor backend para aplicar cambios")
        
    else:
        print("\n❌ ERROR EN APLICACIÓN DE PARCHES")
        print("Revisa los logs arriba para más detalles")
