#!/usr/bin/env python3
"""
Script para corregir el modelo Claude deprecado
===============================================

Este script actualiza automáticamente la configuración del modelo Claude
en el archivo .env para usar el modelo actual disponible.
"""

import os
import re
import shutil
from datetime import datetime

def fix_claude_model():
    """Corrige el modelo Claude en el archivo .env"""
    
    env_path = "C:/Users/yasma/Desktop/retail-recommender-system/.env"
    backup_path = f"{env_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print("🔧 CORRECCIÓN DEL MODELO CLAUDE")
    print("=" * 50)
    
    # 1. Crear backup
    try:
        shutil.copy2(env_path, backup_path)
        print(f"✅ Backup creado: {backup_path}")
    except Exception as e:
        print(f"❌ Error creando backup: {e}")
        return False
    
    # 2. Leer archivo actual
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print("✅ Archivo .env leído correctamente")
    except Exception as e:
        print(f"❌ Error leyendo .env: {e}")
        return False
    
    # 3. Identificar línea problemática
    old_model = "claude-3-sonnet-20240229"
    new_model = "claude-sonnet-4-20250514"
    
    if old_model not in content:
        print(f"⚠️ No se encontró el modelo problemático: {old_model}")
        print("El archivo podría ya estar corregido o usar un modelo diferente")
        
        # Mostrar configuración actual
        for line_num, line in enumerate(content.split('\n'), 1):
            if 'CLAUDE_MODEL' in line and not line.strip().startswith('#'):
                print(f"Configuración actual (línea {line_num}): {line}")
        return True
    
    # 4. Realizar reemplazo
    original_content = content
    
    # Reemplazar el modelo específico
    content = content.replace(
        f"CLAUDE_MODEL={old_model}",
        f"CLAUDE_MODEL={new_model}"
    )
    
    # Verificar que el cambio se realizó
    if content == original_content:
        print("❌ No se pudo realizar el reemplazo")
        return False
    
    # 5. Escribir archivo corregido
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Archivo .env actualizado correctamente")
    except Exception as e:
        print(f"❌ Error escribiendo .env: {e}")
        # Restaurar backup
        try:
            shutil.copy2(backup_path, env_path)
            print("✅ Backup restaurado")
        except:
            print("❌ Error restaurando backup")
        return False
    
    # 6. Mostrar cambios realizados
    print("\n📋 CAMBIOS REALIZADOS:")
    print("-" * 30)
    print(f"❌ ANTES: CLAUDE_MODEL={old_model}")
    print(f"✅ AHORA: CLAUDE_MODEL={new_model}")
    
    # 7. Verificar otras configuraciones Claude
    print("\n🔍 OTRAS CONFIGURACIONES CLAUDE:")
    print("-" * 35)
    
    claude_configs = []
    for line_num, line in enumerate(content.split('\n'), 1):
        if ('CLAUDE_' in line or 'ANTHROPIC_' in line) and not line.strip().startswith('#') and '=' in line:
            claude_configs.append((line_num, line.strip()))
    
    for line_num, config in claude_configs:
        print(f"  {line_num:3d}: {config}")
    
    print(f"\n✅ CORRECCIÓN COMPLETADA")
    print(f"📁 Backup disponible en: {backup_path}")
    print("\n🚀 PRÓXIMOS PASOS:")
    print("1. Reiniciar el servidor de desarrollo")
    print("2. Probar el endpoint /v1/mcp/conversation")
    print("3. Verificar que no hay más errores 404 de Claude")
    
    return True

def validate_claude_configuration():
    """Valida la configuración actual de Claude"""
    
    print("\n🔍 VALIDACIÓN DE CONFIGURACIÓN CLAUDE")
    print("=" * 45)
    
    env_path = "C:/Users/yasma/Desktop/retail-recommender-system/.env"
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error leyendo .env: {e}")
        return False
    
    # Validaciones
    validations = [
        {
            'name': 'Modelo Claude configurado',
            'pattern': r'CLAUDE_MODEL=([^\s\n]+)',
            'expected': ['claude-sonnet-4-20250514', 'claude-opus-4'],
            'critical': True
        },
        {
            'name': 'API Key presente',
            'pattern': r'ANTHROPIC_API_KEY=([^\s\n]+)',
            'expected': ['sk-ant-api03-'],
            'critical': True
        },
        {
            'name': 'Max tokens configurado',
            'pattern': r'CLAUDE_MAX_TOKENS=([^\s\n]+)',
            'expected': ['1000', '2000', '4000'],
            'critical': False
        },
        {
            'name': 'Temperature configurada',
            'pattern': r'CLAUDE_TEMPERATURE=([^\s\n]+)',
            'expected': ['0.7', '0.3', '0.5'],
            'critical': False
        }
    ]
    
    all_good = True
    
    for validation in validations:
        match = re.search(validation['pattern'], content)
        
        if not match:
            status = "❌ MISSING"
            all_good = False
        else:
            value = match.group(1)
            
            # Verificar si el valor está en los esperados
            if any(expected in value for expected in validation['expected']):
                status = f"✅ OK ({value})"
            else:
                status = f"⚠️ REVISAR ({value})"
                if validation['critical']:
                    all_good = False
        
        criticality = "🔴 CRÍTICO" if validation['critical'] else "🟡 OPCIONAL"
        print(f"{status:<25} {validation['name']:<25} {criticality}")
    
    print("\n" + "=" * 45)
    if all_good:
        print("✅ CONFIGURACIÓN VÁLIDA")
    else:
        print("❌ CONFIGURACIÓN REQUIERE CORRECCIÓN")
    
    return all_good

if __name__ == "__main__":
    print("🔧 CORRECTOR DE MODELO CLAUDE")
    print("Solucionando error 404: model 'claude-3-sonnet-20240229'\n")
    
    # Ejecutar corrección
    success = fix_claude_model()
    
    if success:
        print("\n" + "="*60)
        validate_claude_configuration()
        
        print("\n💡 INFORMACIÓN ADICIONAL:")
        print("- El modelo claude-3-sonnet-20240229 fue deprecado por Anthropic")
        print("- El nuevo modelo claude-sonnet-4-20250514 ofrece mejor performance")
        print("- Los warnings de precios sospechosos son comportamiento normal")
        print("- El sistema tiene fallbacks que permiten que funcione sin Claude")
    else:
        print("\n❌ CORRECCIÓN FALLÓ")
        print("Revisar manualmente el archivo .env")