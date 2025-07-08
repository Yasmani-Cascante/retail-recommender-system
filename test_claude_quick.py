#!/usr/bin/env python3
"""
Script de prueba rápida para verificar integración Claude
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Agregar path del proyecto
sys.path.append(os.path.dirname(__file__))

async def quick_test():
    print("🧪 PRUEBA RÁPIDA CLAUDE INTEGRATION")
    print("=" * 40)
    
    # Test 1: Verificar configuración
    api_key = os.getenv("ANTHROPIC_API_KEY")
    ai_enabled = os.getenv("AI_CONVERSATION_ENABLED", "false").lower() == "true"
    
    print(f"API Key configurado: {'✅' if api_key and api_key != 'your_anthropic_api_key_here' else '❌'}")
    print(f"AI habilitado: {'✅' if ai_enabled else '❌'}")
    
    # Test 2: Verificar imports
    try:
        from src.api.core.config import get_settings
        settings = get_settings()
        print(f"Configuración cargada: ✅")
        print(f"Claude disponible: {'✅' if settings.claude_available else '❌'}")
    except ImportError as e:
        print(f"Error de import: ❌ {e}")
        return
    
    # Test 3: Verificar AI Manager (si está configurado)
    if settings.claude_available:
        try:
            from src.api.core.ai_factory import get_ai_manager
            ai_manager = get_ai_manager()
            
            if ai_manager:
                print("AI Manager inicializado: ✅")
                
                # Test simple de conversación
                from src.api.integrations.ai.conversation_context_builder import create_minimal_context
                context = create_minimal_context()
                
                response = await ai_manager.process_conversation(
                    "Hola, esto es una prueba",
                    context,
                    include_recommendations=False
                )
                
                print(f"Conversación de prueba: ✅")
                print(f"Respuesta: {response['conversation_response'][:50]}...")
                
            else:
                print("AI Manager no pudo inicializarse: ❌")
                
        except Exception as e:
            print(f"Error en test de conversación: ❌ {e}")
    else:
        print("Claude no disponible - verificar ANTHROPIC_API_KEY y AI_CONVERSATION_ENABLED")
    
    print("\n" + "=" * 40)
    print("Prueba completada. Para configurar:")
    print("1. Agregar ANTHROPIC_API_KEY real en .env")
    print("2. Configurar AI_CONVERSATION_ENABLED=true en .env")
    print("3. Ejecutar: python test_claude_integration.py")

if __name__ == "__main__":
    asyncio.run(quick_test())
