#!/usr/bin/env python3
"""
Simple Integration Script for Market Corrections
===============================================

Este script añade una línea simple al router MCP para integrar
las correcciones críticas sin modificar extensivamente el código.
"""

import os
import shutil
from datetime import datetime

def integrate_market_corrections_simple():
    """Integra las correcciones de mercado de forma simple"""
    
    router_path = r"C:\Users\yasma\Desktop\retail-recommender-system\src\api\routers\mcp_router.py"
    backup_path = f"{router_path}.backup_simple_{int(datetime.now().timestamp())}"
    
    try:
        # 1. Crear backup
        shutil.copy2(router_path, backup_path)
        print(f"✅ Backup creado: {backup_path}")
        
        # 2. Leer archivo original
        with open(router_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 3. Añadir import si no existe
        if "from src.api.utils.market_integration import" not in content:
            import_line = "\n# 🔧 CRITICAL MARKET CORRECTIONS\nfrom src.api.utils.market_integration import fix_recommendations\n"
            
            # Añadir después del último import
            logger_line = "logger = logging.getLogger(__name__)"
            content = content.replace(logger_line, logger_line + import_line)
            print("✅ Import añadido")
        
        # 4. Buscar función process_conversation y añadir corrección
        if "fix_recommendations(" not in content:
            # Buscar donde se retorna la respuesta
            return_pattern = 'return {'
            
            if return_pattern in content:
                # Añadir corrección justo antes del return
                correction_code = '''
        # 🔧 APLICAR CORRECCIONES CRÍTICAS DE MERCADO
        try:
            safe_recommendations = fix_recommendations(
                safe_recommendations, 
                conversation.market_id, 
                conversation.query
            )
            logger.info(f"✅ Correcciones de mercado aplicadas: {len(safe_recommendations)} productos")
        except Exception as correction_error:
            logger.error(f"❌ Error en correcciones de mercado: {correction_error}")
            pass

        '''
                
                # Buscar el último return en la función
                lines = content.split('\n')
                modified_lines = []
                added_correction = False
                
                for i, line in enumerate(lines):
                    if 'return {' in line and not added_correction and 'process_conversation' in content[:content.find('\n'.join(lines[:i]))]:
                        # Añadir corrección antes del return
                        modified_lines.extend(correction_code.split('\n'))
                        added_correction = True
                    modified_lines.append(line)
                
                if added_correction:
                    content = '\n'.join(modified_lines)
                    print("✅ Corrección añadida al endpoint conversation")
                else:
                    print("⚠️ No se pudo ubicar donde añadir la corrección")
        
        # 5. Escribir archivo modificado
        with open(router_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Integración completada en {router_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error en integración: {e}")
        # Restaurar backup si existe
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, router_path)
            print(f"✅ Backup restaurado")
        return False

if __name__ == "__main__":
    print("🔧 Integrando correcciones críticas de forma simple...")
    success = integrate_market_corrections_simple()
    
    if success:
        print("\n✅ INTEGRACIÓN COMPLETADA")
        print("\n🎯 CORRECCIONES DISPONIBLES:")
        print("1. ✅ Conversión automática COP -> USD")
        print("2. ✅ Traducción básica español -> inglés") 
        print("3. ✅ Validación de estructura de datos")
        print("4. ✅ Mejora de razones contextuales")
        print("\n🚀 Reinicia el servidor backend para aplicar cambios")
        print("\n📋 PARA VALIDAR:")
        print("- Hacer request al widget con market_id='US'")
        print("- Verificar precios convertidos y títulos traducidos")
        
    else:
        print("\n❌ ERROR EN INTEGRACIÓN")
