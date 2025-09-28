#!/usr/bin/env python3
"""
Debugging script para investigar el contenido de turn.recommendations_provided
===========================================================================

Este script agrega logging detallado en mcp_conversation_handler.py para verificar:
1. Qué contienen exactamente los turns existentes
2. Si recommendations_provided está presente y poblado
3. Por qué shown_products resulta en 0 cuando debería tener datos
"""

import os
import shutil
from datetime import datetime

def add_detailed_logging_to_handler():
    """Agrega logging detallado a mcp_conversation_handler.py"""
    
    handler_path = "src/api/core/mcp_conversation_handler.py"
    backup_path = f"src/api/core/mcp_conversation_handler.py.backup_debug_{int(datetime.now().timestamp())}"
    
    # Crear backup
    shutil.copy2(handler_path, backup_path)
    print(f"✅ Backup created: {backup_path}")
    
    # Leer archivo actual
    with open(handler_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Encontrar y reemplazar la sección de diversification checking
    old_diversification_check = '''                if mcp_context and mcp_context.total_turns > 1:
                    # Extraer productos ya mostrados en turns anteriores
                    for turn in mcp_context.turns:
                        if hasattr(turn, 'recommendations_provided') and turn.recommendations_provided:
                            shown_products.update(turn.recommendations_provided)
                    
                    use_diversification = len(shown_products) > 0
                    logger.info(f"🔄 Diversification needed: {use_diversification}, shown_products: {len(shown_products)}")'''
    
    new_diversification_check = '''                if mcp_context and mcp_context.total_turns > 1:
                    # ✅ DEBUGGING: Logging detallado del contexto conversacional
                    logger.info(f"🔍 DEBUG: MCP Context Investigation")
                    logger.info(f"    Session ID: {mcp_context.session_id}")
                    logger.info(f"    Total turns: {mcp_context.total_turns}")
                    logger.info(f"    Turns list length: {len(mcp_context.turns)}")
                    
                    # ✅ DEBUGGING: Investigar cada turn individualmente
                    for i, turn in enumerate(mcp_context.turns):
                        logger.info(f"🔍 DEBUG: Turn {i+1} Investigation:")
                        logger.info(f"    Turn type: {type(turn)}")
                        logger.info(f"    Turn attributes: {dir(turn)}")
                        logger.info(f"    Has recommendations_provided attr: {hasattr(turn, 'recommendations_provided')}")
                        
                        if hasattr(turn, 'recommendations_provided'):
                            recs = turn.recommendations_provided
                            logger.info(f"    recommendations_provided type: {type(recs)}")
                            logger.info(f"    recommendations_provided value: {recs}")
                            logger.info(f"    recommendations_provided length: {len(recs) if recs else 'None/Empty'}")
                            
                            if recs:
                                logger.info(f"    First 3 recommendations: {recs[:3]}")
                                shown_products.update(recs)
                        else:
                            logger.warning(f"    ❌ Turn {i+1} missing recommendations_provided attribute")
                        
                        # ✅ DEBUGGING: Otros atributos relevantes
                        if hasattr(turn, 'user_query'):
                            logger.info(f"    user_query: {turn.user_query}")
                        if hasattr(turn, 'turn_number'):
                            logger.info(f"    turn_number: {turn.turn_number}")
                        if hasattr(turn, 'timestamp'):
                            logger.info(f"    timestamp: {turn.timestamp}")
                    
                    use_diversification = len(shown_products) > 0
                    logger.info(f"🔄 FINAL RESULT: Diversification needed: {use_diversification}")
                    logger.info(f"🔄 FINAL RESULT: shown_products count: {len(shown_products)}")
                    logger.info(f"🔄 FINAL RESULT: shown_products content: {list(shown_products)[:5]}...")  # Primeros 5'''
    
    # Reemplazar el contenido
    if old_diversification_check in content:
        content = content.replace(old_diversification_check, new_diversification_check)
        print("✅ Found and replaced diversification checking section")
    else:
        print("❌ Could not find exact diversification checking section")
        print("🔍 Searching for alternative patterns...")
        
        # Buscar patrones alternativos
        if "shown_products.update(turn.recommendations_provided)" in content:
            print("✅ Found recommendations_provided usage pattern")
        else:
            print("❌ recommendations_provided pattern not found")
        
        return False
    
    # También agregar logging en la sección donde se crea el nuevo turn
    old_turn_creation = '''                            new_turn = ConversationTurn(
                                turn_number=mcp_context.total_turns + 1,
                                timestamp=time.time(),
                                user_query=conversation_query,
                                user_intent="product_recommendation",
                                intent_confidence=0.9,
                                intent_entities=[],
                                ai_response=final_response["ai_response"],
                                recommendations_provided=new_recommendation_ids,
                                market_context={"market_id": market_id},
                                processing_time_ms=(time.time() - start_time) * 1000
                            )'''
    
    new_turn_creation = '''                            # ✅ DEBUGGING: Logging turn creation
                            logger.info(f"🆕 DEBUG: Creating new ConversationTurn")
                            logger.info(f"    turn_number: {mcp_context.total_turns + 1}")
                            logger.info(f"    new_recommendation_ids: {new_recommendation_ids}")
                            logger.info(f"    new_recommendation_ids length: {len(new_recommendation_ids)}")
                            logger.info(f"    final_response recommendations count: {len(final_response['recommendations'])}")
                            
                            new_turn = ConversationTurn(
                                turn_number=mcp_context.total_turns + 1,
                                timestamp=time.time(),
                                user_query=conversation_query,
                                user_intent="product_recommendation",
                                intent_confidence=0.9,
                                intent_entities=[],
                                ai_response=final_response["ai_response"],
                                recommendations_provided=new_recommendation_ids,
                                market_context={"market_id": market_id},
                                processing_time_ms=(time.time() - start_time) * 1000
                            )
                            
                            # ✅ DEBUGGING: Verificar turn después de creación
                            logger.info(f"✅ DEBUG: ConversationTurn created successfully")
                            logger.info(f"    turn.recommendations_provided: {new_turn.recommendations_provided}")
                            logger.info(f"    turn.turn_number: {new_turn.turn_number}")'''
    
    # Reemplazar creación de turn
    if old_turn_creation in content:
        content = content.replace(old_turn_creation, new_turn_creation)
        print("✅ Found and replaced turn creation section")
    else:
        print("⚠️ Could not find exact turn creation section - continuing with diversification debugging")
    
    # Guardar archivo modificado
    with open(handler_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Detailed logging added to mcp_conversation_handler.py")
    return True

def create_debugging_test():
    """Crea un test específico para ejecutar y ver los logs detallados"""
    
    test_content = '''#!/usr/bin/env python3
"""
Test específico para debugging de turn.recommendations_provided
==============================================================

Ejecuta dos llamadas consecutivas y captura logs detallados
"""

import asyncio
import json
import time
import requests

async def test_turn_debugging():
    """Test específico con logging detallado"""
    
    base_url = "http://localhost:8000"
    session_id = f"debug_session_{int(time.time())}"
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c"
    }
    
    print("🧪 DEBUGGING TURN RECOMMENDATIONS - DETAILED ANALYSIS")
    print("=" * 60)
    
    # Primera llamada
    print("\\n1️⃣ PRIMERA LLAMADA - Initial recommendations")
    print("-" * 40)
    
    payload1 = {
        "query": "show me some recommendations",
        "market_id": "US",
        "session_id": session_id,
        "user_id": "debug_user"
    }
    
    try:
        response1 = requests.post(f"{base_url}/v1/mcp/conversation", json=payload1, headers=headers)
        print(f"Status: {response1.status_code}")
        
        if response1.status_code == 200:
            data1 = response1.json()
            rec_count = len(data1.get('recommendations', []))
            print(f"Recommendations: {rec_count}")
            
            # Extraer IDs para verification
            rec_ids_1 = [r.get('id') for r in data1.get('recommendations', []) if r.get('id')]
            print(f"Recommendation IDs: {rec_ids_1}")
        else:
            print(f"Error: {response1.text}")
            return
            
    except Exception as e:
        print(f"Error en primera llamada: {e}")
        return
    
    # Pausa
    await asyncio.sleep(2)
    
    # Segunda llamada - aquí deberíamos ver diversification
    print("\\n2️⃣ SEGUNDA LLAMADA - Should trigger diversification")
    print("-" * 40)
    
    payload2 = {
        "query": "show me more",
        "market_id": "US", 
        "session_id": session_id,
        "user_id": "debug_user"
    }
    
    try:
        response2 = requests.post(f"{base_url}/v1/mcp/conversation", json=payload2, headers=headers)
        print(f"Status: {response2.status_code}")
        
        if response2.status_code == 200:
            data2 = response2.json()
            rec_count = len(data2.get('recommendations', []))
            print(f"Recommendations: {rec_count}")
            
            # Extraer IDs para comparison
            rec_ids_2 = [r.get('id') for r in data2.get('recommendations', []) if r.get('id')]
            print(f"Recommendation IDs: {rec_ids_2}")
            
            # Análisis de overlap
            overlap = len(set(rec_ids_1) & set(rec_ids_2))
            print(f"\\n📊 OVERLAP ANALYSIS:")
            print(f"   Primera llamada: {len(rec_ids_1)} productos")
            print(f"   Segunda llamada: {len(rec_ids_2)} productos") 
            print(f"   Productos en común: {overlap}")
            print(f"   Porcentaje overlap: {overlap/len(rec_ids_1)*100:.1f}%")
            
            # Extraer metadata relevante
            metadata = data2.get('metadata', {})
            print(f"\\n🔍 METADATA ANALYSIS:")
            print(f"   Diversification applied: {metadata.get('diversification_applied', 'N/A')}")
            print(f"   Cache hit: {metadata.get('cache_hit', 'N/A')}")
            print(f"   Personalization applied: {metadata.get('personalization_applied', 'N/A')}")
            
        else:
            print(f"Error: {response2.text}")
            
    except Exception as e:
        print(f"Error en segunda llamada: {e}")
    
    print("\\n🔍 IMPORTANT: Check server logs for detailed turn debugging info")
    print("Look for lines starting with '🔍 DEBUG:' to see turn investigation details")

if __name__ == "__main__":
    asyncio.run(test_turn_debugging())
'''
    
    with open("debug_turn_recommendations_test.py", "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print("✅ Created debug_turn_recommendations_test.py")

if __name__ == "__main__":
    print("🔍 ADDING DETAILED LOGGING FOR TURN DEBUGGING")
    print("=" * 50)
    
    if add_detailed_logging_to_handler():
        create_debugging_test()
        
        print("\\n📋 NEXT STEPS:")
        print("1. Restart the server:")
        print("   uvicorn src.api.main_unified_redis:app --reload --port 8000")
        print("\\n2. Run debugging test:")
        print("   python debug_turn_recommendations_test.py")
        print("\\n3. Check server console for detailed logs starting with '🔍 DEBUG:'")
        print("\\n4. Look for:")
        print("   - Turn attributes and content")
        print("   - recommendations_provided presence and content")
        print("   - Why shown_products results in 0")
        
    else:
        print("❌ Failed to add detailed logging")
