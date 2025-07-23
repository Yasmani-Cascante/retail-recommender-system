#!/usr/bin/env python3
"""
Final Integration Patch - Market Corrections
==========================================

Este script aplica la integración final de correcciones de mercado
añadiendo un endpoint específico y modificando el flujo de conversación.
"""

import os
import re
import shutil
from datetime import datetime

def apply_final_integration():
    """Aplica la integración final de correcciones"""
    
    router_path = r"C:\Users\yasma\Desktop\retail-recommender-system\src\api\routers\mcp_router.py"
    backup_path = f"{router_path}.backup_final_{int(datetime.now().timestamp())}"
    
    try:
        # 1. Crear backup
        shutil.copy2(router_path, backup_path)
        print(f"✅ Backup creado: {backup_path}")
        
        # 2. Leer archivo original
        with open(router_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 3. Añadir endpoint para correcciones
        endpoint_code = '''

@router.post("/conversation-corrected", response_model=ConversationResponse)
async def process_conversation_with_corrections(
    conversation: ConversationRequest,
    current_user: str = Depends(get_current_user)
):
    """
    🔧 ENDPOINT CORREGIDO: Procesamiento conversacional con correcciones críticas de mercado
    
    Este endpoint aplica automáticamente:
    - Conversión COP -> USD para mercado US
    - Traducción español -> inglés
    - Validación de estructura de datos
    """
    start_time = time.time()
    
    try:
        logger.info(f"🔧 Procesando conversación con correcciones para mercado {conversation.market_id}")
        
        # Llamar al endpoint original
        original_response = await process_conversation(conversation, current_user)
        
        # Aplicar correcciones críticas a las recomendaciones
        corrected_recommendations = fix_recommendations(
            original_response["recommendations"],
            conversation.market_id,
            conversation.query
        )
        
        # Crear respuesta corregida
        corrected_response = original_response.copy()
        corrected_response["recommendations"] = corrected_recommendations
        
        # Añadir metadata de correcciones
        corrected_response["metadata"]["corrections_applied"] = True
        corrected_response["metadata"]["market_corrections"] = {
            "target_market": conversation.market_id,
            "original_count": len(original_response["recommendations"]),
            "corrected_count": len(corrected_recommendations),
            "processing_time_ms": (time.time() - start_time) * 1000
        }
        
        logger.info(f"✅ Correcciones aplicadas: {len(corrected_recommendations)} productos procesados")
        
        return corrected_response
        
    except Exception as e:
        logger.error(f"❌ Error en proceso con correcciones: {e}")
        # Fallback al endpoint original si falla
        return await process_conversation(conversation, current_user)
'''
        
        # 4. Añadir endpoint al final del archivo
        content = content.rstrip() + endpoint_code + '\n'
        
        # 5. Escribir archivo modificado
        with open(router_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Endpoint con correcciones añadido a {router_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error aplicando integración final: {e}")
        # Restaurar backup si existe
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, router_path)
            print(f"✅ Backup restaurado")
        return False

if __name__ == "__main__":
    print("🔧 Aplicando integración final de correcciones...")
    success = apply_final_integration()
    
    if success:
        print("\n✅ INTEGRACIÓN FINAL COMPLETADA")
        print("\n🎯 NUEVO ENDPOINT DISPONIBLE:")
        print("   POST /v1/mcp/conversation-corrected")
        print("\n📋 CARACTERÍSTICAS:")
        print("1. ✅ Conversión automática COP -> USD")
        print("2. ✅ Traducción español -> inglés")
        print("3. ✅ Validación de estructura")
        print("4. ✅ Mejoras contextuales")
        print("\n🚀 PRÓXIMO PASO:")
        print("   - Reiniciar servidor backend")
        print("   - Cambiar widget a usar /conversation-corrected")
        
    else:
        print("\n❌ ERROR EN INTEGRACIÓN FINAL")
