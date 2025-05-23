#!/usr/bin/env python
"""
Script de diagnóstico para verificar la instalación de Pydantic.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

def diagnose_pydantic():
    """Diagnostica problemas con Pydantic."""
    print("🔍 Diagnosticando instalación de Pydantic...")
    
    # 1. Verificar versión de Python
    print(f"Python version: {sys.version}")
    
    # 2. Verificar instalación de pydantic
    try:
        import pydantic
        print(f"✅ Pydantic versión: {pydantic.__version__}")
    except ImportError as e:
        print(f"❌ Error importando pydantic: {e}")
        return
    
    # 3. Verificar instalación de pydantic-settings
    try:
        import pydantic_settings
        print(f"✅ pydantic-settings versión: {pydantic_settings.__version__}")
    except ImportError as e:
        print(f"❌ Error importando pydantic-settings: {e}")
        print("💡 Solución: pip install pydantic-settings")
        return
    
    # 4. Verificar importación de BaseSettings
    try:
        from pydantic_settings import BaseSettings
        print("✅ BaseSettings se puede importar desde pydantic_settings")
    except ImportError as e:
        print(f"❌ Error importando BaseSettings desde pydantic_settings: {e}")
        return
    
    # 5. Verificar importación de config.py
    try:
        from src.api.core.config import get_settings
        print("✅ config.py se puede importar correctamente")
        
        # Intentar obtener configuración
        settings = get_settings()
        print(f"✅ get_settings() funciona: {settings.app_name}")
        
    except ImportError as e:
        print(f"❌ Error importando config.py: {e}")
        return
    except Exception as e:
        print(f"❌ Error ejecutando get_settings(): {e}")
        return
    
    # 6. Verificar importación de factories.py
    try:
        from src.api.factories import RecommenderFactory
        print("✅ RecommenderFactory se puede importar correctamente")
        
        # Verificar métodos
        methods = ["create_redis_client", "create_product_cache"]
        for method in methods:
            if hasattr(RecommenderFactory, method):
                print(f"✅ Método {method} existe")
            else:
                print(f"❌ Método {method} no existe")
                
    except ImportError as e:
        print(f"❌ Error importando RecommenderFactory: {e}")
        return
    except Exception as e:
        print(f"❌ Error verificando RecommenderFactory: {e}")
        return
    
    print("🎉 Diagnóstico completo: Todo está funcionando correctamente")

if __name__ == "__main__":
    diagnose_pydantic()
