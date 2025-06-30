#!/usr/bin/env python3
# setup_and_run_mcp_tests.py
"""
Script de configuración y ejecución de tests MCP

Este script:
1. Verifica la configuración del entorno
2. Instala dependencias si es necesario  
3. Ejecuta validación rápida
4. Proporciona próximos pasos

Uso: python setup_and_run_mcp_tests.py
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def print_header():
    """Imprimir cabecera del script"""
    print("🚀 CONFIGURACIÓN Y VALIDACIÓN DEL SISTEMA MCP")
    print("=" * 60)
    print("Este script configurará y validará el sistema de testing MCP")
    print("=" * 60)

def check_python_version():
    """Verificar versión de Python"""
    print("\n🐍 Verificando Python...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} - Compatible")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} - Se requiere Python 3.9+")
        return False

def check_project_structure():
    """Verificar estructura del proyecto"""
    print("\n📁 Verificando estructura del proyecto...")
    
    required_paths = [
        "src/api",
        "src/recommenders",
        "tests/mcp",
    ]
    
    missing = []
    for path in required_paths:
        if not Path(path).exists():
            missing.append(path)
    
    if missing:
        print(f"❌ Directorios faltantes: {missing}")
        print("Asegúrate de ejecutar desde el directorio raíz del proyecto")
        return False
    
    print("✅ Estructura del proyecto verificada")
    return True

def install_testing_dependencies():
    """Instalar dependencias de testing"""
    print("\n📦 Verificando dependencias de testing...")
    
    required_packages = [
        "pytest>=7.0.0",
        "pytest-asyncio>=0.21.0", 
        "psutil>=5.9.0"
    ]
    
    try:
        for package in required_packages:
            print(f"   Verificando {package.split('>=')[0]}...")
            try:
                __import__(package.split('>=')[0].replace('-', '_'))
                print(f"   ✅ {package.split('>=')[0]} disponible")
            except ImportError:
                print(f"   📦 Instalando {package}...")
                subprocess.run([
                    sys.executable, "-m", "pip", "install", package
                ], check=True, capture_output=True)
                print(f"   ✅ {package} instalado")
        
        print("✅ Dependencias verificadas/instaladas")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error instalando dependencias: {e}")
        return False
    except Exception as e:
        print(f"⚠️ Error verificando dependencias: {e}")
        print("Continuando sin instalar...")
        return True

def run_quick_validation():
    """Ejecutar validación rápida"""
    print("\n🧪 Ejecutando validación rápida del sistema MCP...")
    
    try:
        # Ejecutar validación rápida
        result = subprocess.run([
            sys.executable, "tests/mcp/quick_validation.py"
        ], capture_output=True, text=True, timeout=60)
        
        print("📊 RESULTADOS DE VALIDACIÓN:")
        print(result.stdout)
        
        if result.stderr:
            print("⚠️ ADVERTENCIAS/ERRORES:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("⏰ Validación tardó más de 60 segundos - puede haber problemas")
        return False
    except FileNotFoundError:
        print("❌ No se encontró el script de validación rápida")
        print("Verificando si existe...")
        if Path("tests/mcp/quick_validation.py").exists():
            print("✅ Archivo existe, problema de ejecución")
        else:
            print("❌ Archivo no existe")
        return False
    except Exception as e:
        print(f"❌ Error ejecutando validación: {e}")
        return False

def show_next_steps(validation_success):
    """Mostrar próximos pasos"""
    print("\n" + "=" * 60)
    print("🎯 PRÓXIMOS PASOS RECOMENDADOS")
    print("=" * 60)
    
    if validation_success:
        print("🎉 ¡Validación exitosa! El sistema está listo.")
        print("\n📋 Opciones disponibles:")
        print("1. 🧪 Tests de integración básicos:")
        print("   python tests/mcp/integration/test_mcp_resilient_integration.py")
        print("\n2. 🔧 Con pytest (si está disponible):")
        print("   pytest tests/mcp/ -v")
        print("\n3. 📊 Suite completa (cuando esté listo):")
        print("   python tests/mcp/run_mcp_validation_suite.py --mode=all")
        
    else:
        print("⚠️ Validación con problemas. Revisar configuración.")
        print("\n📋 Acciones recomendadas:")
        print("1. 🔍 Revisar errores mostrados arriba")
        print("2. 🛠️ Corregir problemas de configuración")
        print("3. 🔄 Re-ejecutar: python setup_and_run_mcp_tests.py")
    
    print("\n📚 Documentación disponible:")
    print("   📄 tests/mcp/README.md - Documentación completa")
    print("   🔧 tests/mcp/quick_validation.py - Validación rápida")

def main():
    """Función principal"""
    print_header()
    
    # Verificar prerrequisitos
    if not check_python_version():
        sys.exit(1)
    
    if not check_project_structure():
        sys.exit(1)
    
    # Instalar dependencias
    deps_ok = install_testing_dependencies()
    if not deps_ok:
        print("⚠️ Problemas con dependencias, pero continuando...")
    
    # Ejecutar validación
    print(f"\n{'='*60}")
    validation_success = run_quick_validation()
    
    # Mostrar próximos pasos
    show_next_steps(validation_success)
    
    print(f"\n{'='*60}")
    if validation_success:
        print("✅ CONFIGURACIÓN COMPLETADA EXITOSAMENTE")
        sys.exit(0)
    else:
        print("⚠️ CONFIGURACIÓN COMPLETADA CON ADVERTENCIAS")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ Interrumpido por el usuario")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Error inesperado: {e}")
        sys.exit(1)
