#!/usr/bin/env python
"""
Script de prueba para diagnosticar el problema de importación del RecommenderFactory.
"""

import os
import sys
import traceback

def test_import_factory():
    """
    Prueba importar RecommenderFactory para diagnosticar el problema.
    """
    print("🔍 Diagnóstico de importación de RecommenderFactory")
    print("=" * 60)
    
    # 1. Verificar directorio actual
    print(f"📁 Directorio actual: {os.getcwd()}")
    
    # 2. Verificar Python path
    print(f"🐍 Python path:")
    for i, path in enumerate(sys.path):
        print(f"  {i}: {path}")
    
    # 3. Intentar importar paso a paso
    print("\n📦 Intentando importaciones paso a paso:")
    
    try:
        print("  Importando src...")
        import src
        print("  ✅ src importado correctamente")
    except Exception as e:
        print(f"  ❌ Error importando src: {e}")
        traceback.print_exc()
        return False
    
    try:
        print("  Importando src.api...")
        import src.api
        print("  ✅ src.api importado correctamente")
    except Exception as e:
        print(f"  ❌ Error importando src.api: {e}")
        traceback.print_exc()
        return False
    
    try:
        print("  Importando src.api.core...")
        import src.api.core
        print("  ✅ src.api.core importado correctamente")
    except Exception as e:
        print(f"  ❌ Error importando src.api.core: {e}")
        traceback.print_exc()
        return False
    
    try:
        print("  Importando src.api.core.config...")
        from src.api.core.config import get_settings
        print("  ✅ src.api.core.config importado correctamente")
    except Exception as e:
        print(f"  ❌ Error importando src.api.core.config: {e}")
        traceback.print_exc()
        return False
    
    try:
        print("  Importando src.api.factories...")
        import src.api.factories
        print("  ✅ src.api.factories importado correctamente")
    except Exception as e:
        print(f"  ❌ Error importando src.api.factories: {e}")
        traceback.print_exc()
        return False
    
    try:
        print("  Importando RecommenderFactory...")
        from src.api.factories import RecommenderFactory
        print("  ✅ RecommenderFactory importado correctamente")
    except Exception as e:
        print(f"  ❌ Error importando RecommenderFactory: {e}")
        traceback.print_exc()
        return False
    
    # 4. Verificar métodos
    print(f"\n🔧 Verificando métodos de RecommenderFactory:")
    required_methods = ["create_redis_client", "create_product_cache"]
    
    for method in required_methods:
        if hasattr(RecommenderFactory, method):
            print(f"  ✅ {method} está presente")
        else:
            print(f"  ❌ {method} NO está presente")
            return False
    
    # 5. Probar creación de cliente Redis (sin conexión real)
    print(f"\n⚙️ Probando creación de cliente Redis:")
    try:
        # Primero verificar si pydantic está instalado
        import pydantic
        print(f"  ✅ pydantic está instalado (versión: {pydantic.__version__})")
    except ImportError:
        print(f"  ❌ pydantic NO está instalado")
        return False
    
    try:
        # Configurar entorno mínimo para prueba
        os.environ["USE_REDIS_CACHE"] = "true"
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6379"
        
        # Intentar crear cliente Redis (sin conexión)
        redis_client = RecommenderFactory.create_redis_client()
        if redis_client is not None:
            print(f"  ✅ create_redis_client() funciona correctamente")
        else:
            print(f"  ⚠️ create_redis_client() retornó None (normal si USE_REDIS_CACHE=false)")
    except Exception as e:
        print(f"  ❌ Error en create_redis_client(): {e}")
        traceback.print_exc()
        return False
    
    print(f"\n🎉 ¡Todas las importaciones y métodos funcionan correctamente!")
    return True

if __name__ == "__main__":
    success = test_import_factory()
    if success:
        print("\n✅ El problema NO está en RecommenderFactory")
        print("💡 El problema debe estar en el script verify_cache_system.py")
    else:
        print("\n❌ Se encontró un problema en RecommenderFactory")
        print("💡 Necesita corregirse antes de continuar")
    
    sys.exit(0 if success else 1)
