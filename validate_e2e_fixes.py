#!/usr/bin/env python3
"""
Script de Validación E2E - Fase 3B
===================================

Este script valida todos los archivos corregidos manualmente.

Uso:
    python validate_e2e_fixes.py

Author: Claude + Yasmani
Date: 03 Diciembre 2025
"""

import os
import sys
import ast
from pathlib import Path
from typing import Dict, List, Tuple

# Colores para terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(title: str):
    """Imprime header formateado."""
    print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")

def check_mark(condition: bool) -> str:
    """Retorna ✅ o ❌ basado en condición."""
    return f"{Colors.GREEN}✅" if condition else f"{Colors.RED}❌"

def validate_env_test(base_path: Path) -> Dict[str, bool]:
    """Valida archivo .env.test"""
    print_header("VALIDACIÓN: .env.test")
    
    env_file = base_path / ".env.test"
    results = {}
    
    # Check 1: Archivo existe
    exists = env_file.exists()
    print(f"{check_mark(exists)} Archivo existe: {env_file}")
    results['exists'] = exists
    
    if not exists:
        return results
    
    # Check 2: Leer contenido
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check 3: Configuraciones críticas
    critical_configs = {
        'ENV=test': 'ENV configurado como test',
        'TEST_MODE=true': 'Test mode habilitado',
        'REDIS_PORT=6380': 'Redis puerto test (6380)',
        'REDIS_HOST=localhost': 'Redis host localhost',
        'ENABLE_MOCK_EXTERNAL_APIS=true': 'APIs externas mockeadas',
        'DEBUG=true': 'Debug habilitado',
        'MCP_ENABLED=false': 'MCP deshabilitado para tests',
    }
    
    for config, description in critical_configs.items():
        found = config in content
        print(f"{check_mark(found)} {description}")
        results[config] = found
    
    # Check 4: Seguridad - No debe tener credenciales reales
    dangerous_patterns = [
        'redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com',
        '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',
        'sk-ant-api03-',
    ]
    
    has_production_creds = any(pattern in content for pattern in dangerous_patterns)
    print(f"{check_mark(not has_production_creds)} Sin credenciales de producción")
    results['no_production_creds'] = not has_production_creds
    
    # Check 5: Tamaño razonable
    size = env_file.stat().st_size
    reasonable_size = 4000 < size < 10000
    print(f"{check_mark(reasonable_size)} Tamaño razonable: {size:,} bytes")
    results['reasonable_size'] = reasonable_size
    
    return results

def validate_conftest(base_path: Path) -> Dict[str, bool]:
    """Valida archivo conftest.py"""
    print_header("VALIDACIÓN: tests/e2e/conftest.py")
    
    conftest_file = base_path / "tests" / "e2e" / "conftest.py"
    results = {}
    
    # Check 1: Archivo existe
    exists = conftest_file.exists()
    print(f"{check_mark(exists)} Archivo existe: {conftest_file}")
    results['exists'] = exists
    
    if not exists:
        return results
    
    # Check 2: Leer contenido
    with open(conftest_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check 3: Imports correctos
    imports_checks = {
        'from src.api.main_unified_redis import app': 
            'Import app desde main_unified_redis',
        'from src.api.factories': 
            'Import ServiceFactory',
        'from src.api.core.redis_service import RedisService': 
            'Import RedisService desde core',
    }
    
    print(f"\n{Colors.BOLD}Imports:{Colors.RESET}")
    for import_line, description in imports_checks.items():
        found = import_line in content
        print(f"{check_mark(found)} {description}")
        results[f'import_{description}'] = found
    
    # Check 4: Imports incorrectos NO deben estar
    bad_imports = {
        'from src.main import app': 
            'NO debe tener import desde src.main',
        'from src.infrastructure.redis_service': 
            'NO debe tener import desde infrastructure',
    }
    
    print(f"\n{Colors.BOLD}Imports Incorrectos (NO deben estar):{Colors.RESET}")
    for bad_import, description in bad_imports.items():
        not_found = bad_import not in content
        print(f"{check_mark(not_found)} {description}")
        results[f'no_{description}'] = not_found
    
    # Check 5: Type annotations correctas
    type_checks = {
        'def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:':
            'event_loop con type annotation completa',
        'def app_with_overrides() -> Generator[FastAPI, None, None]:':
            'app_with_overrides con type annotation (opcional pero bueno)',
    }
    
    print(f"\n{Colors.BOLD}Type Annotations:{Colors.RESET}")
    for type_hint, description in type_checks.items():
        found = type_hint in content
        print(f"{check_mark(found)} {description}")
        results[f'type_{description}'] = found
    
    # Check 6: redis_service fixture usa ServiceFactory
    uses_factory = 'await ServiceFactory.get_redis_service()' in content
    no_manual_instance = 'service = RedisService(' not in content or \
                         '# service = RedisService(' in content
    
    print(f"\n{Colors.BOLD}Redis Service Pattern:{Colors.RESET}")
    print(f"{check_mark(uses_factory)} Usa ServiceFactory.get_redis_service()")
    print(f"{check_mark(no_manual_instance)} No instancia RedisService manualmente")
    results['uses_service_factory'] = uses_factory
    results['no_manual_redis'] = no_manual_instance
    
    # Check 7: Sintaxis Python válida
    try:
        ast.parse(content)
        syntax_valid = True
        print(f"\n{check_mark(True)} Sintaxis Python válida")
    except SyntaxError as e:
        syntax_valid = False
        print(f"\n{check_mark(False)} Error de sintaxis: {e}")
    
    results['syntax_valid'] = syntax_valid
    
    return results

def validate_test_file(test_file: Path, test_name: str) -> Dict[str, bool]:
    """Valida archivo de test individual."""
    print_header(f"VALIDACIÓN: {test_name}")
    
    results = {}
    
    # Check 1: Archivo existe
    exists = test_file.exists()
    print(f"{check_mark(exists)} Archivo existe: {test_file}")
    results['exists'] = exists
    
    if not exists:
        return results
    
    # Check 2: Leer contenido
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check 3: Tiene estructura de test válida
    checks = {
        'import pytest': 'Importa pytest',
        '@pytest.mark': 'Usa decoradores pytest',
        'async def test_': 'Tiene funciones de test async',
        'import asyncio': 'Importa asyncio',
    }
    
    print(f"\n{Colors.BOLD}Estructura Básica:{Colors.RESET}")
    for pattern, description in checks.items():
        found = pattern in content
        print(f"{check_mark(found)} {description}")
        results[f'structure_{description}'] = found
    
    # Check 4: NO debe tener código suelto (await fuera de función)
    lines = content.split('\n')
    has_loose_await = False
    loose_await_lines = []
    
    in_function = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Detectar inicio de función
        if stripped.startswith('def ') or stripped.startswith('async def '):
            in_function = True
        
        # Detectar fin de función (línea sin indentación después de función)
        if in_function and stripped and not line.startswith(' ') and not line.startswith('\t'):
            if not stripped.startswith('def ') and not stripped.startswith('async def '):
                in_function = False
        
        # Buscar await fuera de función
        if 'await ' in stripped and not in_function:
            # Ignorar comentarios y strings
            if not stripped.startswith('#') and not stripped.startswith('"""'):
                has_loose_await = True
                loose_await_lines.append((i, line))
    
    print(f"\n{Colors.BOLD}Validación Código:{Colors.RESET}")
    print(f"{check_mark(not has_loose_await)} No tiene 'await' fuera de funciones")
    
    if has_loose_await:
        print(f"\n{Colors.YELLOW}⚠️  Líneas con await fuera de función:{Colors.RESET}")
        for line_num, line in loose_await_lines[:5]:  # Mostrar máximo 5
            print(f"   Línea {line_num}: {line.strip()}")
    
    results['no_loose_await'] = not has_loose_await
    
    # Check 5: Sintaxis Python válida
    try:
        ast.parse(content)
        syntax_valid = True
        print(f"{check_mark(True)} Sintaxis Python válida")
    except SyntaxError as e:
        syntax_valid = False
        print(f"{check_mark(False)} Error de sintaxis: {e}")
    
    results['syntax_valid'] = syntax_valid
    
    # Check 6: Tamaño razonable (no vacío, no demasiado pequeño)
    size = test_file.stat().st_size
    reasonable_size = size > 100
    print(f"{check_mark(reasonable_size)} Tamaño razonable: {size:,} bytes")
    results['reasonable_size'] = reasonable_size
    
    return results

def generate_summary(all_results: Dict[str, Dict[str, bool]]):
    """Genera resumen final de todas las validaciones."""
    print_header("RESUMEN FINAL")
    
    total_checks = 0
    passed_checks = 0
    
    for file_name, results in all_results.items():
        total_checks += len(results)
        passed_checks += sum(1 for v in results.values() if v)
    
    percentage = (passed_checks / total_checks * 100) if total_checks > 0 else 0
    
    print(f"{Colors.BOLD}Estadísticas:{Colors.RESET}")
    print(f"  Total de validaciones: {total_checks}")
    print(f"  Validaciones pasadas:  {Colors.GREEN}{passed_checks}{Colors.RESET}")
    print(f"  Validaciones fallidas: {Colors.RED}{total_checks - passed_checks}{Colors.RESET}")
    print(f"  Porcentaje de éxito:   {Colors.BOLD}{percentage:.1f}%{Colors.RESET}")
    
    print(f"\n{Colors.BOLD}Estado por archivo:{Colors.RESET}")
    for file_name, results in all_results.items():
        file_passed = sum(1 for v in results.values() if v)
        file_total = len(results)
        file_percentage = (file_passed / file_total * 100) if file_total > 0 else 0
        
        status = f"{Colors.GREEN}✅" if file_percentage == 100 else \
                 f"{Colors.YELLOW}⚠️ " if file_percentage >= 80 else \
                 f"{Colors.RED}❌"
        
        print(f"  {status} {file_name}: {file_passed}/{file_total} ({file_percentage:.0f}%)")
    
    # Conclusión final
    print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
    if percentage == 100:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 TODAS LAS VALIDACIONES PASARON{Colors.RESET}")
    elif percentage >= 90:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  CASI PERFECTO - Revisar detalles arriba{Colors.RESET}")
    elif percentage >= 70:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  NECESITA AJUSTES - Ver errores específicos{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ REQUIERE CORRECCIONES IMPORTANTES{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")

def main():
    """Función principal."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║         VALIDACIÓN E2E - RETAIL RECOMMENDER SYSTEM - FASE 3B              ║")
    print("║                      Script de Validación Automática                       ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")
    
    # Base path del proyecto
    base_path = Path(r"C:\Users\yasma\Desktop\retail-recommender-system")
    
    if not base_path.exists():
        print(f"{Colors.RED}❌ Error: No se encuentra el directorio del proyecto{Colors.RESET}")
        print(f"   Buscado en: {base_path}")
        return 1
    
    print(f"{Colors.GREEN}✅ Proyecto encontrado: {base_path}{Colors.RESET}\n")
    
    # Ejecutar validaciones
    all_results = {}
    
    try:
        # 1. Validar .env.test
        all_results['.env.test'] = validate_env_test(base_path)
        
        # 2. Validar conftest.py
        all_results['conftest.py'] = validate_conftest(base_path)
        
        # 3. Validar test_user_journey_discovery.py
        all_results['test_user_journey_discovery.py'] = validate_test_file(
            base_path / "tests" / "e2e" / "test_user_journey_discovery.py",
            "test_user_journey_discovery.py"
        )
        
        # 4. Validar test_user_journey_purchase.py
        all_results['test_user_journey_purchase.py'] = validate_test_file(
            base_path / "tests" / "e2e" / "test_user_journey_purchase.py",
            "test_user_journey_purchase.py"
        )
        
        # Generar resumen
        generate_summary(all_results)
        
        return 0
        
    except Exception as e:
        print(f"\n{Colors.RED}❌ Error durante validación: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())