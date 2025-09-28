#!/usr/bin/env python3
"""
Script para aplicar correcciones críticas a mcp_router.py
Resuelve los errores persistentes de session management
"""

import re
import os
import sys

def apply_mcp_router_fixes():
    """Aplicar todas las correcciones a mcp_router.py"""
    
    file_path = "src/api/routers/mcp_router.py"
    
    # Verificar que el archivo existe
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} no encontrado")
        return False
    
    # Leer archivo
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    fixes_applied = 0
    
    print("🔧 Aplicando correcciones a mcp_router.py...")
    
    # CORRECCIÓN #1: Eliminar 'session=' de llamadas add_conversation_turn
    # Buscar patrón: session=conversation_session,
    pattern1 = r'session=conversation_session,'
    replacement1 = 'conversation_session,'
    
    if re.search(pattern1, content):
        content = re.sub(pattern1, replacement1, content)
        fixes_applied += 1
        print("✅ Corrección #1: Eliminado 'session=' de llamadas")
    
    # CORRECCIÓN #2: Buscar llamadas con user_query=
    pattern2 = r'user_query=conversation\.query,'
    replacement2 = 'conversation.query,'
    
    if re.search(pattern2, content):
        content = re.sub(pattern2, replacement2, content)
        fixes_applied += 1
        print("✅ Corrección #2: Eliminado 'user_query=' de llamadas")
    
    # CORRECCIÓN #3: Buscar llamadas con ai_response=
    pattern3 = r'ai_response=([^,\n]+),'
    replacement3 = r'\1,'
    
    if re.search(pattern3, content):
        content = re.sub(pattern3, replacement3, content)
        fixes_applied += 1
        print("✅ Corrección #3: Eliminado 'ai_response=' de llamadas")
    
    # CORRECCIÓN #4: Añadir verificación de tipo después de get_or_create_session
    verification_code = '''
        # ✅ VERIFICACIÓN CRÍTICA: Asegurar que conversation_session es objeto
        logger.debug(f"✅ Session object type: {type(conversation_session)}")
        logger.debug(f"✅ Session object has session_id: {hasattr(conversation_session, 'session_id')}")
        logger.debug(f"✅ Session object has turn_count: {hasattr(conversation_session, 'turn_count')}")
        
        if isinstance(conversation_session, str):
            logger.error(f"❌ CRITICAL: conversation_session is string when should be object: {conversation_session}")
            # Re-intentar obtener sesión
            conversation_session = await state_manager.get_or_create_session(
                session_id=None,  # Forzar creación de nueva sesión
                user_id=validated_user_id,
                market_id=conversation.market_id
            )
            logger.info(f"✅ Re-created session as object: {type(conversation_session)}")
'''
    
    # Buscar donde insertar la verificación
    session_creation_pattern = r'(conversation_session = await state_manager\.get_or_create_session\([^)]+\))'
    
    if re.search(session_creation_pattern, content):
        content = re.sub(
            session_creation_pattern, 
            r'\1' + verification_code,
            content
        )
        fixes_applied += 1
        print("✅ Corrección #4: Añadida verificación de tipo de session")
    
    # CORRECCIÓN #5: Envolver add_conversation_turn en try-catch específico
    try_catch_wrapper = '''
        try:
            logger.info(f"🔄 Adding conversation turn - Session type: {type(conversation_session)}")
            
            updated_session = await state_manager.add_conversation_turn(
                conversation_session,
                conversation.query,
                final_ai_response,
                metadata={
                    "recommendations_count": len(safe_recommendations),
                    "source": "mcp_conversation",
                    "processing_time_ms": (time.time() - start_time) * 1000,
                    "mcp_available": True
                }
            )
            
            # Actualizar información final de sesión
            real_session_id = updated_session.session_id
            turn_number = updated_session.turn_count
            state_persisted = True
            
            logger.info(f"✅ MCP turn recorded successfully: session {real_session_id}, turn {turn_number}")
            
        except Exception as turn_error:
            logger.error(f"❌ Error recording MCP turn: {turn_error}")
            logger.error(f"   Session type: {type(conversation_session)}")
            logger.error(f"   Session value: {conversation_session}")
            logger.error(f"   Query type: {type(conversation.query)}")
            logger.error(f"   AI response type: {type(final_ai_response)}")
            
            # No es crítico para la respuesta, continuar sin guardar turn
            state_persisted = False'''
    
    # Buscar llamadas existentes a add_conversation_turn para reemplazarlas
    add_turn_pattern = r'updated_session = await state_manager\.add_conversation_turn\([^}]+\}[^)]*\)'
    
    if re.search(add_turn_pattern, content, re.DOTALL):
        content = re.sub(
            add_turn_pattern,
            try_catch_wrapper.strip(),
            content,
            flags=re.DOTALL
        )
        fixes_applied += 1
        print("✅ Corrección #5: Añadido try-catch específico para add_conversation_turn")
    
    # Verificar si se aplicaron cambios
    if content != original_content:
        # Crear backup
        backup_path = f"{file_path}.backup_{int(time.time())}"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"📦 Backup creado: {backup_path}")
        
        # Escribir archivo corregido
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ {fixes_applied} correcciones aplicadas exitosamente a {file_path}")
        return True
    else:
        print("ℹ️ No se encontraron patrones para corregir")
        return False

if __name__ == "__main__":
    import time
    
    print("🚀 INICIANDO CORRECCIONES CRÍTICAS MCP ROUTER")
    print("=" * 60)
    
    success = apply_mcp_router_fixes()
    
    if success:
        print("\n🎯 PRÓXIMOS PASOS:")
        print("1. Ejecutar: python integrity_validator.py")
        print("2. Ejecutar: python validate_phase2_complete.py")
        print("3. Verificar que no hay más errores de session management")
    else:
        print("\n⚠️ Verificar manualmente los archivos y patrones")
    
    print("\n✅ Script completado")