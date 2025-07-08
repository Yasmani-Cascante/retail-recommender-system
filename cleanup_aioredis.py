#!/usr/bin/env python3
"""
Script para limpiar aioredis y verificar que el OptimizedConversationAIManager funciona correctamente
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Ejecuta un comando y reporta el resultado"""
    print(f"🔍 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} - ÉXITO")
            if result.stdout.strip():
                print(f"   Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ {description} - FALLÓ")
            if result.stderr.strip():
                print(f"   Error: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ {description} - EXCEPCIÓN: {e}")
        return False

def check_aioredis_references():
    """Busca referencias a aioredis en el código fuente"""
    print("🔍 Verificando referencias a aioredis en código fuente...")
    
    src_dir = Path("src")
    references_found = []
    
    if src_dir.exists():
        for py_file in src_dir.rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'aioredis' in content:
                        lines_with_aioredis = []
                        for i, line in enumerate(content.split('\n'), 1):
                            if 'aioredis' in line:
                                lines_with_aioredis.append(f"  Line {i}: {line.strip()}")
                        
                        if lines_with_aioredis:
                            references_found.append((str(py_file), lines_with_aioredis))
            except Exception as e:
                print(f"⚠️ Error leyendo {py_file}: {e}")
    
    if references_found:
        print("❌ Referencias a aioredis encontradas:")
        for file_path, lines in references_found:
            print(f"  📄 {file_path}:")
            for line in lines:
                print(f"    {line}")
        return False
    else:
        print("✅ No se encontraron referencias a aioredis en código fuente")
        return True

def test_optimized_manager_import():
    """Testa la importación del OptimizedConversationAIManager"""
    print("🔍 Testando importación de OptimizedConversationAIManager...")
    
    try:
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        print("✅ OptimizedConversationAIManager importado exitosamente")
        return True
    except Exception as e:
        print(f"❌ Error importando OptimizedConversationAIManager: {e}")
        return False

def test_redis_client_import():
    """Testa la importación del RedisClient"""
    print("🔍 Testando importación de RedisClient...")
    
    try:
        from src.api.core.redis_client import RedisClient
        print("✅ RedisClient importado exitosamente")
        return True
    except Exception as e:
        print(f"❌ Error importando RedisClient: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 LIMPIEZA Y VERIFICACIÓN DE AIOREDIS")
    print("=" * 50)
    
    all_checks_passed = True
    
    # 1. Verificar referencias en código
    if not check_aioredis_references():
        all_checks_passed = False
    
    # 2. Remover aioredis del entorno
    if run_command("pip uninstall aioredis -y", "Desinstalando aioredis"):
        print("   ℹ️ aioredis desinstalado exitosamente")
    
    # 3. Asegurar que redis está instalado
    if not run_command("pip install redis>=4.6.0", "Instalando redis>=4.6.0"):
        all_checks_passed = False
    
    # 4. Test de importaciones
    if not test_redis_client_import():
        all_checks_passed = False
    
    if not test_optimized_manager_import():
        all_checks_passed = False
    
    # 5. Test de redis.asyncio
    try:
        import redis.asyncio as redis
        print("✅ redis.asyncio disponible")
    except Exception as e:
        print(f"❌ Error con redis.asyncio: {e}")
        all_checks_passed = False
    
    print("\n" + "=" * 50)
    print("📊 RESUMEN DE VERIFICACIÓN")
    print("=" * 50)
    
    if all_checks_passed:
        print("🎉 ¡Todas las verificaciones pasaron!")
        print("✅ OptimizedConversationAIManager listo para testing")
        print("\n🚀 PRÓXIMOS PASOS:")
        print("1. Ejecutar: pytest tests/phase0_consolidation/test_optimized_conversation_manager.py -v")
        print("2. Verificar que todos los tests pasan")
        print("3. Continuar con Fase 0 del roadmap")
        return True
    else:
        print("⚠️ Algunas verificaciones fallaron")
        print("🔧 Revisar los errores reportados arriba")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
