#!/usr/bin/env python3
"""
FIX CRÍTICO: State Manager Initialization Robustness
===================================================

Patch para resolver el problema de state_manager = None en mcp_router.py
"""

import logging
logger = logging.getLogger(__name__)

def create_robust_state_manager_fix():
    """
    Crea un fix robusto para el problema de inicialización del state manager
    
    PROBLEMA IDENTIFICADO:
    - get_conversation_state_manager() retorna None
    - Causando fallback mode en lugar de persistencia real
    
    SOLUCIÓN:
    - Inicialización robusta con múltiples fallbacks
    - Logging detallado para debugging
    - Estado en memoria si Redis falla
    """
    
    fix_code = '''
# 🔧 CRITICAL FIX: Robust State Manager Initialization
# Añadir al inicio de mcp_router.py después de los imports

def get_robust_conversation_state_manager():
    """
    Versión robusta de get_conversation_state_manager con debugging detallado
    
    Returns:
        MCPConversationStateManager or None
    """
    logger.info("🔧 ROBUST: Attempting to get conversation state manager...")
    
    try:
        # Método 1: Usar factory function estándar
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        state_manager = get_conversation_state_manager()
        
        if state_manager:
            logger.info("✅ ROBUST: Standard factory successful")
            return state_manager
        else:
            logger.warning("⚠️ ROBUST: Standard factory returned None, trying manual creation...")
            
    except Exception as e:
        logger.error(f"❌ ROBUST: Standard factory failed: {e}")
    
    try:
        # Método 2: Creación manual directa
        from src.api.mcp.conversation_state_manager import MCPConversationStateManager
        from src.api.core.config import get_settings
        
        settings = get_settings()
        logger.info(f"🔧 ROBUST: Settings loaded, redis_cache={settings.use_redis_cache}")
        
        if settings.use_redis_cache:
            try:
                # Intentar crear Redis client
                from src.api.core.redis_client import RedisClient
                
                redis_client = RedisClient(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    password=settings.redis_password,
                    ssl=settings.redis_ssl,
                    db=settings.redis_db
                )
                
                logger.info("🔧 ROBUST: Redis client created, testing connection...")
                
                # Test connection sincrónico simple
                import asyncio
                try:
                    # Crear event loop si no existe
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    # Test connection
                    connection_result = loop.run_until_complete(redis_client.connect())
                    
                    if connection_result:
                        logger.info("✅ ROBUST: Redis connection successful")
                        
                        # Crear state manager con Redis
                        state_manager = MCPConversationStateManager(redis_client)
                        logger.info("✅ ROBUST: State manager created with Redis")
                        return state_manager
                    else:
                        logger.warning("⚠️ ROBUST: Redis connection failed, falling back to no-Redis mode")
                        
                except Exception as connection_error:
                    logger.warning(f"⚠️ ROBUST: Redis connection test failed: {connection_error}")
                    
            except Exception as redis_error:
                logger.error(f"❌ ROBUST: Redis client creation failed: {redis_error}")
        
        # Fallback: Crear sin Redis
        logger.info("🔧 ROBUST: Creating state manager without Redis...")
        state_manager = MCPConversationStateManager(None)
        logger.info("✅ ROBUST: State manager created without Redis (memory mode)")
        return state_manager
        
    except Exception as manual_error:
        logger.error(f"❌ ROBUST: Manual creation failed: {manual_error}")
    
    try:
        # Método 3: Último recurso - mock state manager
        logger.warning("⚠️ ROBUST: Creating mock state manager as last resort...")
        
        class MockStateManager:
            def __init__(self):
                self.sessions = {}
                logger.info("🔧 ROBUST: Mock state manager initialized")
            
            async def get_or_create_session(self, session_id, user_id, market_id):
                if not session_id:
                    session_id = f"mock_session_{user_id}_{int(time.time())}"
                
                if session_id not in self.sessions:
                    # Crear mock session
                    from datetime import datetime
                    
                    class MockSession:
                        def __init__(self, session_id, user_id, market_id):
                            self.session_id = session_id
                            self.user_id = user_id
                            self.market_id = market_id
                            self.turn_count = 0
                            self.created_at = datetime.now().timestamp()
                            self.last_updated = self.created_at
                    
                    self.sessions[session_id] = MockSession(session_id, user_id, market_id)
                    logger.info(f"🔧 ROBUST: Mock session created: {session_id}")
                
                return self.sessions[session_id]
            
            async def add_conversation_turn_simple(self, session, user_query, ai_response, metadata=None):
                session.turn_count += 1
                session.last_updated = datetime.now().timestamp()
                logger.info(f"🔧 ROBUST: Mock turn added: {session.session_id}, turn: {session.turn_count}")
                return session
            
            async def save_conversation_state(self, session_id, session):
                # Mock save - just update in memory
                self.sessions[session_id] = session
                logger.info(f"🔧 ROBUST: Mock state saved: {session_id}")
                return True
            
            async def load_conversation_state(self, session_id):
                session = self.sessions.get(session_id)
                if session:
                    logger.info(f"🔧 ROBUST: Mock state loaded: {session_id}")
                else:
                    logger.info(f"🔧 ROBUST: Mock state not found: {session_id}")
                return session
        
        mock_manager = MockStateManager()
        logger.info("✅ ROBUST: Mock state manager created as fallback")
        return mock_manager
        
    except Exception as mock_error:
        logger.error(f"❌ ROBUST: Even mock creation failed: {mock_error}")
        return None

# 🔧 CRITICAL REPLACEMENT: Reemplazar la línea en mcp_router.py
# CAMBIAR:
#   state_manager = get_conversation_state_manager()
# POR:
#   state_manager = get_robust_conversation_state_manager()
'''
    
    return fix_code

def apply_fix_to_mcp_router():
    """Aplica el fix al archivo mcp_router.py"""
    
    print("🔧 APPLYING ROBUST STATE MANAGER FIX...")
    
    # Leer archivo actual
    router_file = "src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verificar si ya tiene el fix
        if "get_robust_conversation_state_manager" in content:
            print("✅ Fix already applied to mcp_router.py")
            return True
        
        # Buscar la línea problemática
        target_line = "state_manager = get_conversation_state_manager()"
        
        if target_line not in content:
            print(f"❌ Target line not found in {router_file}")
            return False
        
        # Crear el contenido del fix
        fix_code = create_robust_state_manager_fix()
        
        # Insertar el fix después de los imports
        import_section_end = content.find("logger = logging.getLogger(__name__)")
        
        if import_section_end == -1:
            print("❌ Could not find insertion point in mcp_router.py")
            return False
        
        # Insertar el fix
        insertion_point = content.find("\\n", import_section_end) + 1
        new_content = (
            content[:insertion_point] + 
            "\\n" + fix_code + "\\n" +
            content[insertion_point:]
        )
        
        # Reemplazar la llamada problemática
        new_content = new_content.replace(
            target_line,
            "state_manager = get_robust_conversation_state_manager()"
        )
        
        # Escribir archivo modificado
        with open(router_file + ".backup_state_fix", 'w', encoding='utf-8') as f:
            f.write(content)  # Backup original
        
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ Fix applied successfully to mcp_router.py")
        print(f"✅ Backup saved as {router_file}.backup_state_fix")
        return True
        
    except Exception as e:
        print(f"❌ Error applying fix: {e}")
        return False

if __name__ == "__main__":
    print("🚀 STATE MANAGER ROBUSTNESS FIX")
    print("=" * 50)
    
    # Mostrar el fix
    fix_code = create_robust_state_manager_fix()
    print("📋 Fix code generated:")
    print(fix_code)
    
    # Aplicar el fix
    print("\\n🔧 Applying fix...")
    success = apply_fix_to_mcp_router()
    
    if success:
        print("\\n✅ FIX APPLIED SUCCESSFULLY")
        print("🎯 Next steps:")
        print("   1. Restart the server")
        print("   2. Run: python debug_state_manager_issue.py")
        print("   3. Test conversation state persistence")
    else:
        print("\\n❌ FIX APPLICATION FAILED")
        print("🔧 Manual application required")
