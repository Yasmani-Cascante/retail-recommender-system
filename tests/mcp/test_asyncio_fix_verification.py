# tests/mcp/test_asyncio_fix_verification.py
"""
Verificación de la corrección del problema de asyncio event loop

Este script verifica que la corrección aplicada resuelve el problema
de "asyncio.run() cannot be called from a running event loop"
"""

import asyncio
import sys
from pathlib import Path

# Agregar el directorio raíz al path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def verify_asyncio_fix():
    """Verificar que la corrección de asyncio funciona"""
    print("🔍 Verificando corrección de asyncio event loop...")
    
    try:
        # Importar el validador corregido
        from tests.mcp.quick_validation import QuickMCPValidator
        
        # Crear instancia
        validator = QuickMCPValidator()
        
        # Probar solo los métodos que fallaban antes
        print("🧪 Probando test_basic_recommender...")
        basic_result = await validator.test_basic_recommender()
        
        print("🧪 Probando test_mock_integration...")  
        integration_result = await validator.test_mock_integration()
        
        # Verificar resultados
        success = (
            basic_result.get("status") == "success" and
            integration_result.get("status") == "success"
        )
        
        if success:
            print("✅ CORRECCIÓN EXITOSA!")
            print("✅ Los métodos async funcionan correctamente")
            print("✅ No hay conflicto de event loops")
            
            # Verificar que tienen el flag de corrección
            if (basic_result.get("async_fixed") and 
                integration_result.get("async_fixed")):
                print("✅ Flag async_fixed confirmado")
            
            return True
        else:
            print("❌ Corrección no funcionó completamente")
            print(f"Basic result: {basic_result}")
            print(f"Integration result: {integration_result}")
            return False
            
    except Exception as e:
        print(f"❌ Error en verificación: {e}")
        return False

async def main():
    """Función principal"""
    print("🚀 Verificación de Corrección AsyncIO")
    print("=" * 40)
    
    success = await verify_asyncio_fix()
    
    print("\n" + "=" * 40)
    if success:
        print("🎉 CORRECCIÓN VERIFICADA EXITOSAMENTE")
        print("📋 Ahora puedes ejecutar:")
        print("   python tests/mcp/quick_validation.py")
        sys.exit(0)
    else:
        print("❌ VERIFICACIÓN FALLÓ - Revisar implementación")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
