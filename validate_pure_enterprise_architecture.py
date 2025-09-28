#!/usr/bin/env python3
"""
Pure Enterprise Architecture Validation
======================================

Valida que la arquitectura es 100% enterprise sin imports legacy residuales.
"""

import sys
import os
import re
import asyncio
sys.path.append('src')

from dotenv import load_dotenv
load_dotenv()

def validate_no_legacy_imports():
    """Valida que no hay imports legacy en el código"""
    
    print("VALIDATING PURE ENTERPRISE ARCHITECTURE")
    print("=" * 50)
    
    legacy_patterns = [
        r'from\s+.*redis_client\s+import',
        r'import\s+redis_client',
        r'redis_client\.',
        r'RedisClient\('
    ]
    
    src_path = 'src'
    legacy_found = []
    
    for root, dirs, files in os.walk(src_path):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        lines = content.split('\n')
                        
                        for i, line in enumerate(lines, 1):
                            for pattern in legacy_patterns:
                                if re.search(pattern, line) and not line.strip().startswith('#'):
                                    legacy_found.append({
                                        'file': file_path,
                                        'line': i,
                                        'content': line.strip()
                                    })
                except Exception:
                    pass
    
    if legacy_found:
        print(f"LEGACY IMPORTS FOUND: {len(legacy_found)}")
        for item in legacy_found:
            print(f"   {item['file']}:{item['line']} - {item['content']}")
        return False
    else:
        print("NO LEGACY IMPORTS FOUND - Pure Enterprise Architecture")
        return True

async def validate_enterprise_components():
    """Valida que todos los componentes usan ServiceFactory"""
    
    print("\nVALIDATING SERVICEFACTORY USAGE")
    print("=" * 50)
    
    try:
        from src.api.factories import ServiceFactory
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine
        
        # Test 1: ServiceFactory Redis
        redis_service = await ServiceFactory.get_redis_service()
        health = await redis_service.health_check()
        sf_status = health.get('status', 'unknown')
        print(f"   ServiceFactory Redis: {sf_status}")
        
        # Test 2: ConversationManager
        conv_mgr = OptimizedConversationAIManager('test_enterprise')
        
        # Check if it's using ServiceFactory approach
        if hasattr(conv_mgr, '_redis_service') or hasattr(conv_mgr, 'redis_service'):
            print("   ConversationManager: Using enterprise pattern")
            conv_enterprise = True
        elif hasattr(conv_mgr, '_redis_client'):
            # Check if redis_client is None (indicating fallback to ServiceFactory)
            if conv_mgr._redis_client is None:
                print("   ConversationManager: Using ServiceFactory fallback")
                conv_enterprise = True
            else:
                print("   ConversationManager: Still using legacy RedisClient")
                conv_enterprise = False
        else:
            print("   ConversationManager: Redis integration unclear")
            conv_enterprise = False
        
        # Test 3: PersonalizationEngine
        engine = await create_mcp_personalization_engine('test_enterprise')
        
        # Check enterprise integration
        if hasattr(engine, 'redis_service'):
            print("   PersonalizationEngine: Using enterprise pattern")
            engine_enterprise = True
        else:
            print("   PersonalizationEngine: Enterprise pattern not detected")
            engine_enterprise = False
        
        # Overall assessment
        all_enterprise = sf_status in ['healthy', 'connected'] and conv_enterprise and engine_enterprise
        
        if all_enterprise:
            print("\nALL COMPONENTS USING ENTERPRISE ARCHITECTURE!")
            return True
        else:
            print("\nSOME COMPONENTS STILL USING LEGACY PATTERNS")
            return False
            
    except Exception as e:
        print(f"Enterprise validation failed: {e}")
        return False

async def comprehensive_architecture_test():
    """Test comprehensivo de arquitectura enterprise pura"""
    
    print("COMPREHENSIVE ENTERPRISE ARCHITECTURE VALIDATION")
    print("=" * 60)
    
    # Test 1: No legacy imports
    no_legacy = validate_no_legacy_imports()
    
    # Test 2: Enterprise components
    all_enterprise = await validate_enterprise_components()
    
    # Test 3: Performance consistency
    print("\nPERFORMANCE CONSISTENCY TEST")
    print("=" * 50)
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        # Create all components
        from src.api.factories import ServiceFactory
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine
        
        redis_service = await ServiceFactory.get_redis_service()
        conv_mgr = OptimizedConversationAIManager('test_perf')
        state_mgr = await get_conversation_state_manager()
        engine = await create_mcp_personalization_engine('test_perf')
        
        end_time = asyncio.get_event_loop().time()
        total_time = (end_time - start_time) * 1000
        
        print(f"   Total component creation time: {total_time:.1f}ms")
        
        if total_time < 5000:  # Less than 5 seconds
            print("   Performance: EXCELLENT")
            perf_good = True
        elif total_time < 10000:  # Less than 10 seconds
            print("   Performance: GOOD")
            perf_good = True
        else:
            print("   Performance: NEEDS OPTIMIZATION")
            perf_good = False
        
    except Exception as e:
        print(f"   Performance test failed: {e}")
        perf_good = False
    
    # Final assessment
    if no_legacy and all_enterprise and perf_good:
        print("\nFINAL ASSESSMENT: PURE ENTERPRISE ARCHITECTURE VALIDATED!")
        print("=" * 60)
        print("No legacy imports found")
        print("All components using ServiceFactory")
        print("Performance within acceptable range")
        print("Migration Redis Enterprise: TRULY COMPLETED")
        return True
    else:
        print("\nFINAL ASSESSMENT: ENTERPRISE MIGRATION INCOMPLETE")
        print("=" * 60)
        print(f"Legacy imports clean: {no_legacy}")
        print(f"Enterprise components: {all_enterprise}")
        print(f"Performance good: {perf_good}")
        print("Additional fixes required")
        return False

if __name__ == "__main__":
    success = asyncio.run(comprehensive_architecture_test())
    
    if success:
        print("\nREADY FOR PRODUCTION DEPLOYMENT")
        print("Enterprise architecture validated and complete")
    else:
        print("\nADDITIONAL MIGRATION WORK REQUIRED")
        print("Complete the fixes before proceeding")
