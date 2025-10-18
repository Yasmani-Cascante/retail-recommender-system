#!/usr/bin/env python3
"""
Script de verificación de sintaxis para archivos modificados
"""
import sys
import py_compile

files_to_check = [
    r"C:\Users\yasma\Desktop\retail-recommender-system\src\api\dependencies.py",
    r"C:\Users\yasma\Desktop\retail-recommender-system\src\api\routers\products_router.py"
]

print("🔍 Verificando sintaxis de archivos Python...")
print("=" * 60)

all_ok = True
for file_path in files_to_check:
    try:
        print(f"\n📄 Verificando: {file_path}")
        py_compile.compile(file_path, doraise=True)
        print(f"✅ CORRECTO - Sin errores de sintaxis")
    except py_compile.PyCompileError as e:
        print(f"❌ ERROR de sintaxis:")
        print(f"   {e}")
        all_ok = False
    except Exception as e:
        print(f"⚠️ ERROR al verificar archivo:")
        print(f"   {e}")
        all_ok = False

print("\n" + "=" * 60)
if all_ok:
    print("🎉 TODOS LOS ARCHIVOS TIENEN SINTAXIS CORRECTA")
    sys.exit(0)
else:
    print("❌ SE ENCONTRARON ERRORES - Revisar arriba")
    sys.exit(1)
