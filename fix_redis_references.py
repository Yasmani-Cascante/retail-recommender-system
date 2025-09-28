#!/usr/bin/env python3
"""
Redis Reference Fixes
====================

Corrige todas las referencias undefined de RedisClient después de la migración enterprise.
"""

import os
import time

def fix_optimized_conversation_manager():
    """Corrige references en optimized_conversation_manager.py"""
    
    file_path = 'src/api/integrations/ai/optimized_conversation_manager.py'
    print(f"🔧 Corrigiendo: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"   ❌ Archivo no encontrado")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        timestamp = int(time.time())
        backup_path = f"{file_path}.backup_redis_refs_{timestamp}"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"   ✅ Backup: {backup_path}")
        
        # Fixes específicos
        fixes = [
            # Fix 1: Constructor parameter type hint
            ('redis_client: Optional[RedisClient] = None,', 
             'redis_client = None,  # Legacy compatibility - will use ServiceFactory'),
            
            # Fix 2: Si hay alguna referencia adicional de tipo
            ('Optional[RedisClient]', 'Optional[Any]  # Legacy compatibility'),
            
            # Fix 3: Import Any si no está presente
            ('from typing import Dict, List, Optional, Any',
             'from typing import Dict, List, Optional, Any')  # Keep as is if present
        ]
        
        modified_content = content
        changes_applied = 0
        
        for old_text, new_text in fixes:
            if old_text in modified_content and old_text != new_text:
                modified_content = modified_content.replace(old_text, new_text)
                changes_applied += 1
                print(f"   ✅ Fix aplicado: {old_text[:40]}...")
        
        # Asegurar que Any está importado
        if 'from typing import' in modified_content and ', Any' not in modified_content:
            modified_content = modified_content.replace(
                'from typing import Dict, List, Optional',
                'from typing import Dict, List, Optional, Any'
            )
            changes_applied += 1
            print(f"   ✅ Any agregado a imports")
        
        # Guardar cambios
        if changes_applied > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            print(f"   ✅ {changes_applied} cambios guardados")
            return True
        else:
            print(f"   ℹ️ No se requirieron cambios")
            return True
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def fix_mcp_personalization_engine():
    """Corrige references en mcp_personalization_engine.py"""
    
    file_path = 'src/api/mcp/engines/mcp_personalization_engine.py'
    print(f"\n🔧 Corrigiendo: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"   ❌ Archivo no encontrado")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        timestamp = int(time.time())
        backup_path = f"{file_path}.backup_redis_refs_{timestamp}"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"   ✅ Backup: {backup_path}")
        
        # Fixes específicos
        fixes = [
            # Fix 1: Constructor parameter type hint (línea ~96)
            ('redis_client: RedisClient = None,  # Legacy compatibility',
             'redis_client = None,  # Legacy compatibility - will use ServiceFactory'),
            
            # Fix 2: Constructor parameter alternative format
            ('redis_client: RedisClient = None,',
             'redis_client = None,  # Legacy compatibility'),
            
            # Fix 3: Any type hint if needed
            ('Optional[RedisClient]', 'Optional[Any]  # Legacy compatibility'),
            
            # Fix 4: Variable assignments
            ('= RedisClient(', '= None  # RedisClient('),
        ]
        
        modified_content = content
        changes_applied = 0
        
        for old_text, new_text in fixes:
            if old_text in modified_content:
                modified_content = modified_content.replace(old_text, new_text)
                changes_applied += 1
                print(f"   ✅ Fix aplicado: {old_text[:40]}...")
        
        # Guardar cambios
        if changes_applied > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            print(f"   ✅ {changes_applied} cambios guardados")
            return True
        else:
            print(f"   ℹ️ No se requirieron cambios")
            return True
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def validate_fixes():
    """Valida que los fixes se aplicaron correctamente"""
    
    print(f"\n🔍 VALIDANDO FIXES")
    print("=" * 40)
    
    files_to_check = [
        'src/api/integrations/ai/optimized_conversation_manager.py',
        'src/api/mcp/engines/mcp_personalization_engine.py'
    ]
    
    all_good = True
    
    for file_path in files_to_check:
        print(f"\n📁 {file_path}:")
        
        if not os.path.exists(file_path):
            print("   ❌ Archivo no encontrado")
            all_good = False
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Buscar referencias problemáticas
            lines = content.split('\n')
            redis_client_refs = []
            
            for i, line in enumerate(lines, 1):
                if 'RedisClient' in line and not line.strip().startswith('#'):
                    redis_client_refs.append((i, line.strip()))
            
            if redis_client_refs:
                print(f"   ⚠️ Aún quedan {len(redis_client_refs)} referencias a RedisClient:")
                for line_num, line_content in redis_client_refs[:3]:  # Mostrar solo primeras 3
                    print(f"      L{line_num}: {line_content}")
                all_good = False
            else:
                print("   ✅ No hay referencias problemáticas a RedisClient")
                
        except Exception as e:
            print(f"   ❌ Error validando: {e}")
            all_good = False
    
    return all_good

def create_test_import():
    """Crea test para verificar que los imports funcionan"""
    
    test_script = '''#!/usr/bin/env python3
"""
Test Import After Redis Fixes
=============================

Verifica que los imports funcionan después de corregir referencias a RedisClient.
"""

import sys
sys.path.append('src')

def test_imports():
    """Test que los imports funcionan sin errores"""
    
    print("🧪 TESTING IMPORTS POST-FIX")
    print("=" * 40)
    
    try:
        print("1. Testing optimized_conversation_manager...")
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        print("   ✅ Import successful")
        
        # Test constructor
        try:
            manager = OptimizedConversationAIManager('test_key')
            print("   ✅ Constructor successful")
        except Exception as e:
            print(f"   ⚠️ Constructor issue: {e}")
        
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
    
    try:
        print("\\n2. Testing mcp_personalization_engine...")
        from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine
        print("   ✅ Import successful")
        
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
    
    print("\\n✅ IMPORT TEST COMPLETED")

if __name__ == "__main__":
    test_imports()
'''
    
    with open('test_imports_post_fix.py', 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("🧪 Test de imports creado: test_imports_post_fix.py")

if __name__ == "__main__":
    print("🚨 CORRIGIENDO REFERENCIAS UNDEFINED DE REDISCLIENT")
    print("=" * 60)
    
    print("PROBLEMA:")
    print("- Fixes automáticos eliminaron imports de RedisClient")
    print("- Quedaron referencias undefined en el código")
    print("- Causando warnings en líneas específicas")
    print()
    
    # Aplicar fixes
    fix1 = fix_optimized_conversation_manager()
    fix2 = fix_mcp_personalization_engine()
    
    # Validar fixes
    validation = validate_fixes()
    
    # Crear test
    create_test_import()
    
    if fix1 and fix2 and validation:
        print("\n🎉 FIXES DE REFERENCIAS COMPLETADOS")
        print("=" * 50)
        print("✅ optimized_conversation_manager.py corregido")
        print("✅ mcp_personalization_engine.py corregido")
        print("✅ Validación exitosa")
        
        print("\n🎯 PRÓXIMOS PASOS:")
        print("1. Ejecutar: python test_imports_post_fix.py")
        print("2. Verificar que no hay más warnings de RedisClient")
        print("3. Re-ejecutar tests de migración enterprise")
        
    else:
        print("\n❌ ALGUNOS FIXES FALLARON")
        print("Revisar errores arriba y aplicar fixes manuales")
