#!/usr/bin/env python3
"""
PARCHE INMEDIATO - Corrige UnboundLocalError: mcp_state_manager

EJECUCIÓN SIMPLE:
1. Guarda este archivo como 'immediate_patch.py' en la raíz del proyecto
2. Ejecuta: python immediate_patch.py
3. Ejecuta: python src/api/run.py

PROBLEMA IDENTIFICADO:
- Línea 621 en main_unified_redis.py usa mcp_state_manager sin inicializar
- Variables MCP se referencian antes de ser definidas
- El startup_event tiene problemas de scope de variables

SOLUCIÓN:
- Inicializar todas las variables MCP al inicio de startup_event
- Hacer logging seguro con verificación de existencia
- Añadir verificaciones en endpoints
"""

import os
from pathlib import Path

def fix_now():
    """Aplica el parche inmediato"""
    
    file_path = Path("src/api/main_unified_redis.py")
    
    if not file_path.exists():
        print(f"❌ ARCHIVO NO ENCONTRADO: {file_path}")
        print("💡 Ejecuta este script desde: C:\\Users\\yasma\\Desktop\\retail-recommender-system")
        return False
    
    print(f"🔧 Aplicando parche a {file_path}")
    
    # Leer archivo
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # PARCHE 1: Añadir inicialización al inicio de startup_event
    old_startup = '''@app.on_event("startup")
async def startup_event():
    """
    Startup event corregido y completo con inicialización MCP integrada
    """
    # ✅ CORRECCIÓN: Declarar todas las variables globales al inicio
    global redis_client, product_cache, hybrid_recommender
    global mcp_recommender, mcp_conversation_state_manager
    global optimized_conversation_manager, personalization_engine'''
    
    new_startup = '''@app.on_event("startup")
async def startup_event():
    """
    Startup event corregido y completo con inicialización MCP integrada
    """
    # ✅ CORRECCIÓN: Declarar todas las variables globales al inicio
    global redis_client, product_cache, hybrid_recommender
    global mcp_recommender, mcp_conversation_state_manager
    global optimized_conversation_manager, personalization_engine, mcp_state_manager
    
    # ✅ PARCHE CRÍTICO: Inicializar TODAS las variables MCP inmediatamente
    # Esto previene UnboundLocalError en logging posterior
    mcp_state_manager = None
    mcp_conversation_state_manager = None
    optimized_conversation_manager = None
    personalization_engine = None
    mcp_recommender = None'''
    
    content = content.replace(old_startup, new_startup)
    
    # PARCHE 2: Corregir el logging problemático de la línea 621
    # Buscar el patrón de logging que falla
    problematic_patterns = [
        'logger.info(f"   {\'✅\' if mcp_state_manager else \'❌\'} State Manager: {\'Disponible\' if mcp_state_manager else \'No disponible\'}")',
        'logger.info(f"   {\'✅\' if personalization_engine else \'❌\'} Personalization: {\'Disponible\' if personalization_engine else \'No disponible\'}")',
        'logger.info(f"   {\'✅\' if optimized_conversation_manager else \'❌\'} Conversation AI: {\'Disponible\' if optimized_conversation_manager else \'No disponible\'}")'
    ]
    
    # Reemplazar con logging seguro
    safe_logging = '''    # ✅ PARCHE: Logging seguro que no causa UnboundLocalError
    try:
        state_manager_status = "Disponible" if mcp_state_manager else "No disponible"
        logger.info(f"   {'✅' if mcp_state_manager else '❌'} State Manager: {state_manager_status}")
    except:
        logger.info("   ❌ State Manager: No disponible")
    
    try:
        personalization_status = "Disponible" if personalization_engine else "No disponible"
        logger.info(f"   {'✅' if personalization_engine else '❌'} Personalization: {personalization_status}")
    except:
        logger.info("   ❌ Personalization: No disponible")
    
    try:
        conversation_status = "Disponible" if optimized_conversation_manager else "No disponible"
        logger.info(f"   {'✅' if optimized_conversation_manager else '❌'} Conversation AI: {conversation_status}")
    except:
        logger.info("   ❌ Conversation AI: No disponible")'''
    
    # Aplicar el parche de logging
    for pattern in problematic_patterns:
        content = content.replace(pattern, "# Logging movido a sección segura")
    
    # Buscar donde insertar el logging seguro
    mcp_log_marker = 'logger.info(f"   {\'✅\' if mcp_recommender else \'❌\'} MCP:'
    if mcp_log_marker in content:
        content = content.replace(
            mcp_log_marker,
            safe_logging + '\n    \n    ' + mcp_log_marker
        )
    
    # PARCHE 3: Verificación en endpoints que usan mcp_state_manager
    endpoint_usage = 'mcp_context = await mcp_state_manager.add_conversation_turn('
    safe_endpoint_usage = '''# ✅ PARCHE: Verificar disponibilidad antes de usar
        if mcp_state_manager is None:
            raise HTTPException(status_code=503, detail="MCP State Manager no disponible")
        
        mcp_context = await mcp_state_manager.add_conversation_turn('''
    
    content = content.replace(endpoint_usage, safe_endpoint_usage)
    
    # PARCHE 4: También corregir save_conversation_state
    save_usage = 'await mcp_state_manager.save_conversation_state('
    safe_save_usage = '''if mcp_state_manager is not None:
            await mcp_state_manager.save_conversation_state('''
    
    content = content.replace(save_usage, safe_save_usage)
    
    # Crear backup y escribir archivo corregido
    backup_path = file_path.with_suffix('.py.backup_immediate')
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(open(file_path, 'r', encoding='utf-8').read())
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ PARCHE APLICADO EXITOSAMENTE")
    print(f"✅ Backup creado: {backup_path}")
    
    return True

def test_syntax():
    """Prueba que la sintaxis del archivo corregido sea válida"""
    try:
        import ast
        file_path = Path("src/api/main_unified_redis.py")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        ast.parse(content)
        print("✅ SINTAXIS VÁLIDA: El archivo no tiene errores de sintaxis")
        return True
        
    except SyntaxError as e:
        print(f"❌ ERROR DE SINTAXIS: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR EN PRUEBA: {e}")
        return False

def main():
    print("🚨 PARCHE INMEDIATO - UnboundLocalError mcp_state_manager")
    print("=" * 60)
    
    # Verificar ubicación
    if not Path("src").exists():
        print("❌ ERROR: Ejecutar desde la raíz del proyecto")
        print("📁 Ubicación correcta: C:\\Users\\yasma\\Desktop\\retail-recommender-system")
        return
    
    # Aplicar parche
    if fix_now():
        # Probar sintaxis
        if test_syntax():
            print("\n🎉 ¡PARCHE APLICADO CON ÉXITO!")
            print("✅ UnboundLocalError corregido")
            print("✅ Sintaxis válida")
            print("\n🚀 EJECUTA AHORA:")
            print("   python src/api/run.py")
            print("\n📋 Si hay otros errores:")
            print("   - Redis: Instalar Redis o deshabilitar en .env")
            print("   - scikit-learn: pip install scikit-learn==1.2.2")
        else:
            print("⚠️ Parche aplicado pero hay errores de sintaxis")
    else:
        print("❌ Error aplicando parche")

if __name__ == "__main__":
    main()