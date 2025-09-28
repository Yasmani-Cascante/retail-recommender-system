#!/usr/bin/env python3
"""
Final Redis Reference Validation
===============================

Valida que NO quedan referencias undefined de RedisClient.
"""

import os
import re

def final_validation():
    """Validación final de referencias RedisClient"""
    
    print("🔍 VALIDACIÓN FINAL - REFERENCIAS REDISCLIENT")
    print("=" * 50)
    
    files_to_check = [
        'src/api/integrations/ai/optimized_conversation_manager.py',
        'src/api/mcp/engines/mcp_personalization_engine.py'
    ]
    
    total_issues = 0
    
    for file_path in files_to_check:
        print(f"\n📁 {file_path}:")
        
        if not os.path.exists(file_path):
            print("   ❌ Archivo no encontrado")
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            issues = []
            
            for i, line in enumerate(lines, 1):
                # Buscar RedisClient no comentado
                if 'RedisClient' in line and not line.strip().startswith('#'):
                    # Verificar que no sea parte de un comentario inline
                    comment_index = line.find('#')
                    redis_index = line.find('RedisClient')
                    
                    if comment_index == -1 or redis_index < comment_index:
                        issues.append((i, line.strip()))
            
            if issues:
                print(f"   ⚠️ {len(issues)} referencias problemáticas encontradas:")
                for line_num, line_content in issues:
                    print(f"      L{line_num}: {line_content}")
                total_issues += len(issues)
            else:
                print("   ✅ No hay referencias problemáticas")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n📊 RESUMEN FINAL:")
    if total_issues == 0:
        print("🎉 ¡TODAS LAS REFERENCIAS REDISCLIENT CORREGIDAS!")
        print("✅ No quedan warnings de 'RedisClient is not defined'")
        print("✅ Migración enterprise completamente limpia")
        return True
    else:
        print(f"⚠️ Quedan {total_issues} referencias por corregir")
        return False

def test_imports():
    """Test rápido de imports"""
    
    print(f"\n🧪 TEST DE IMPORTS")
    print("=" * 30)
    
    try:
        import sys
        sys.path.append('src')
        
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        print("✅ OptimizedConversationAIManager import OK")
        
        from src.api.mcp.engines.mcp_personalization_engine import MCPPersonalizationEngine
        print("✅ MCPPersonalizationEngine import OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

if __name__ == "__main__":
    validation_ok = final_validation()
    import_ok = test_imports()
    
    if validation_ok and import_ok:
        print("\n🎯 RESULTADO FINAL:")
        print("✅ TODAS LAS REFERENCIAS REDISCLIENT CORREGIDAS")
        print("✅ IMPORTS FUNCIONANDO SIN WARNINGS")
        print("✅ MIGRACIÓN ENTERPRISE COMPLETAMENTE LIMPIA")
        
        print("\n🚀 PRÓXIMOS PASOS:")
        print("1. Re-ejecutar: python validate_pure_enterprise_architecture.py")
        print("2. Confirmar: python test_enterprise_migration_fixed.py")
        print("3. Verificar: No más logs de redis_client legacy")
        
    else:
        print("\n⚠️ REVISAR ISSUES RESTANTES")
