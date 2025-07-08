#!/usr/bin/env python3
"""
Validador post-setup para verificar que todo está configurado correctamente
"""

import os
import sys
from pathlib import Path

def validate_setup():
    print("🔍 VALIDANDO SETUP CLAUDE INTEGRATION")
    print("=" * 45)
    
    issues = []
    checks_passed = 0
    total_checks = 8
    
    # Check 1: Estructura de directorios
    required_dirs = [
        "src/api/integrations/ai",
        "src/api/integrations/ai/prompts", 
        "src/api/integrations/ai/models",
        "docs/ai_integration"
    ]
    
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            checks_passed += 1
            print(f"✅ Directorio {dir_path} existe")
        else:
            issues.append(f"Directorio faltante: {dir_path}")
            print(f"❌ Directorio {dir_path} NO existe")
    
    # Check 2: Archivo principal de integración
    ai_manager_path = "src/api/integrations/ai/ai_conversation_manager.py"
    if Path(ai_manager_path).exists():
        checks_passed += 1
        print(f"✅ {ai_manager_path} existe")
    else:
        issues.append(f"Archivo faltante: {ai_manager_path}")
        print(f"❌ {ai_manager_path} NO existe")
    
    # Check 3: Configuración en .env
    if Path(".env").exists():
        with open(".env", "r") as f:
            env_content = f.read()
            
        if "ANTHROPIC_API_KEY" in env_content:
            checks_passed += 1
            print("✅ ANTHROPIC_API_KEY configurado en .env")
        else:
            issues.append("ANTHROPIC_API_KEY no encontrado en .env")
            print("❌ ANTHROPIC_API_KEY NO configurado en .env")
            
        if "AI_CONVERSATION_ENABLED" in env_content:
            checks_passed += 1
            print("✅ AI_CONVERSATION_ENABLED configurado en .env")
        else:
            issues.append("AI_CONVERSATION_ENABLED no encontrado en .env")
            print("❌ AI_CONVERSATION_ENABLED NO configurado en .env")
    else:
        issues.append("Archivo .env no existe")
        print("❌ Archivo .env NO existe")
    
    # Check 4: Requirements.txt actualizado
    if Path("requirements.txt").exists():
        with open("requirements.txt", "r") as f:
            req_content = f.read()
            
        if "anthropic" in req_content:
            checks_passed += 1
            print("✅ anthropic agregado a requirements.txt")
        else:
            issues.append("anthropic no encontrado en requirements.txt")
            print("❌ anthropic NO está en requirements.txt")
    
    # Check 5: Scripts de testing
    test_files = ["test_claude_quick.py", "test_claude_integration.py"]
    test_files_exist = sum(1 for f in test_files if Path(f).exists())
    
    if test_files_exist >= 1:
        checks_passed += 1
        print(f"✅ Scripts de testing disponibles ({test_files_exist}/{len(test_files)})")
    else:
        issues.append("Scripts de testing no encontrados")
        print("❌ Scripts de testing NO encontrados")
    
    # Resumen
    print("\n" + "=" * 45)
    print(f"📊 RESUMEN: {checks_passed}/{total_checks} checks pasaron")
    
    if issues:
        print("\n🚨 PROBLEMAS ENCONTRADOS:")
        for issue in issues:
            print(f"  - {issue}")
    
    if checks_passed == total_checks:
        print("\n🎉 ¡Setup completado exitosamente!")
        print("\n📝 PRÓXIMOS PASOS:")
        print("1. Configurar ANTHROPIC_API_KEY real en .env")
        print("2. Configurar AI_CONVERSATION_ENABLED=true en .env")
        print("3. Ejecutar: python test_claude_quick.py")
        print("4. Ejecutar: python test_claude_integration.py")
        return True
    else:
        print(f"\n⚠️ Setup incompleto ({checks_passed}/{total_checks})")
        print("Ejecutar setup_claude_integration.sh de nuevo")
        return False

if __name__ == "__main__":
    validate_setup()
