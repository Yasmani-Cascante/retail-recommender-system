"""
Script de Validacion y Activacion -- Fase M5: Alembic Migrations
=================================================================

Proposito:
    Verificar que el entorno esta correctamente configurado y aplicar
    el 'alembic stamp 0001' en los environments TEST y PROD.

Uso (desde la raiz del proyecto):
    # Solo verificar prerequisitos sin aplicar nada
    python scripts/m5_alembic_setup.py --check

    # Verificar Y aplicar stamp (environment DEFAULT, usa .env)
    python scripts/m5_alembic_setup.py --stamp

    # Verificar Y aplicar stamp en TEST (usa .env.test)
    python scripts/m5_alembic_setup.py --stamp --env test

    # Ver estado actual de Alembic en la DB
    python scripts/m5_alembic_setup.py --status

Prerequisitos:
    pip install alembic sqlalchemy asyncpg python-dotenv

Ejecutar siempre desde la raiz del proyecto:
    cd C:\\Users\\yasma\\Desktop\\retail-recommender-system
    python scripts/m5_alembic_setup.py --check

Nota sobre 'alembic check':
    Este script usa 'alembic heads' en lugar de 'alembic check' para
    verificar migrations pendientes. Razon: 'alembic check' requiere
    target_metadata con modelos SQLAlchemy ORM (modo autogenerate).
    Nuestra estrategia es script-only (target_metadata = None), por lo
    que 'alembic check' siempre reporta un error esperado pero confuso.
    'alembic heads' es el comando correcto para modo script-only.
"""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Agregar la raiz del proyecto al Python path.
# Necesario para que los imports del proyecto funcionen correctamente.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ==============================================================================
# Carga de variables de entorno
# ==============================================================================

def load_environment(env_name: str = "default") -> None:
    """
    Carga el archivo .env correspondiente al environment solicitado.

    Args:
        env_name: 'default' -> .env  |  'test' -> .env.test
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("ERROR: python-dotenv no instalado.")
        print("       Ejecutar: pip install python-dotenv")
        sys.exit(1)

    env_file = PROJECT_ROOT / (".env.test" if env_name == "test" else ".env")

    if not env_file.exists():
        print(f"ERROR: Archivo de entorno no encontrado: {env_file}")
        sys.exit(1)

    load_dotenv(dotenv_path=env_file, override=True)
    print(f"  Variables cargadas desde: {env_file.name}")


def get_db_url_display() -> str:
    """
    Construye y muestra la URL de conexion con el password enmascarado.
    Retorna la URL real (sin enmascarar) para uso interno.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        import re
        masked = re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', database_url)
        print(f"  DB URL (DATABASE_URL): {masked}")
        url = database_url.replace("postgres://", "postgresql+asyncpg://")
        url = url.replace("postgresql://", "postgresql+asyncpg://")
        return url

    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD", "")

    missing = [v for v, val in [("DB_HOST", host), ("DB_NAME", name), ("DB_USER", user)] if not val]
    if missing:
        print(f"ERROR: Faltan variables en .env: {missing}")
        sys.exit(1)

    print(f"  DB URL: postgresql+asyncpg://{user}:****@{host}:{port}/{name}")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


# ==============================================================================
# Verificacion de prerequisitos
# ==============================================================================

async def check_prerequisites() -> bool:
    """
    Verifica todos los prerequisitos antes de proceder con el stamp.

    Checks realizados:
        1. Dependencias Python (alembic, sqlalchemy, asyncpg, dotenv)
        2. Variables de entorno requeridas en .env
        3. Archivos de Alembic (alembic.ini, env.py, script.py.mako, baseline)
        4. Conectividad a PostgreSQL + existencia de tablas requeridas

    Returns:
        bool: True si todos los checks pasan, False si alguno falla.
    """
    print()
    print("=" * 62)
    print("  VERIFICACION DE PREREQUISITOS -- M5 Alembic")
    print("=" * 62)

    all_ok = True

    # Check 1: Dependencias Python
    print("\n[1] Dependencias Python:")
    deps = [
        ("alembic", "alembic>=1.13.0"),
        ("sqlalchemy", "sqlalchemy>=2.0.35"),
        ("asyncpg", "asyncpg>=0.29.0"),
        ("dotenv", "python-dotenv>=1.0.0"),
    ]
    for module, package in deps:
        try:
            __import__(module)
            print(f"    OK  {package}")
        except ImportError:
            print(f"    FAIL {package} -- pip install {package.split('>=')[0]}")
            all_ok = False

    # Check 2: Variables de entorno
    print("\n[2] Variables de entorno (.env):")
    required_vars = ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"]
    for var in required_vars:
        value = os.getenv(var)
        if value:
            display = value[:25] + "..." if len(value) > 25 else value
            print(f"    OK  {var} = {display}")
        else:
            print(f"    FAIL {var} -- no definida en .env")
            all_ok = False

    password_val = os.getenv("DB_PASSWORD")
    if password_val is not None:
        print(f"    OK  DB_PASSWORD = ****")
    else:
        print(f"    WARN DB_PASSWORD -- no definida (intentando sin contrasena)")

    # Check 3: Archivos de Alembic
    print("\n[3] Estructura de archivos Alembic:")
    required_files = {
        "alembic.ini": PROJECT_ROOT / "alembic.ini",
        "alembic/env.py": PROJECT_ROOT / "alembic" / "env.py",
        "alembic/script.py.mako": PROJECT_ROOT / "alembic" / "script.py.mako",
        "alembic/versions/0001_baseline_post_h2_schema.py": (
            PROJECT_ROOT / "alembic" / "versions" / "0001_baseline_post_h2_schema.py"
        ),
    }
    for display_name, path in required_files.items():
        if path.exists():
            print(f"    OK  {display_name}")
        else:
            print(f"    FAIL {display_name} -- no encontrado en {path}")
            all_ok = False

    # Check 4: Conectividad a PostgreSQL
    print("\n[4] Conectividad a PostgreSQL:")
    try:
        import asyncpg

        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5432"))
        name_db = os.getenv("DB_NAME", "retail_recommender_db")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")

        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=name_db,
            user=user,
            password=password,
            timeout=10,
        )

        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        table_names = [row["table_name"] for row in tables]
        print(f"    OK  Conexion exitosa a {host}:{port}/{name_db}")
        print(f"    Tablas encontradas: {', '.join(table_names) if table_names else 'ninguna'}")

        required_tables = ["kb_contents", "schema_migrations"]
        for table in required_tables:
            if table in table_names:
                print(f"    OK  Tabla '{table}' existe")
            else:
                print(f"    FAIL Tabla '{table}' NO existe")
                print(f"         Aplicar primero: migrations/001 y 002")
                all_ok = False

        if "alembic_version" in table_names:
            row = await conn.fetchrow(
                "SELECT version_num FROM alembic_version LIMIT 1;"
            )
            version_num = row["version_num"] if row else "vacia"
            print(f"    INFO 'alembic_version' ya existe con version: {version_num}")
            print(f"         El stamp ya fue aplicado en este environment.")
        else:
            print(f"    INFO 'alembic_version' no existe -- stamp la creara")

        await conn.close()

    except Exception as e:
        print(f"    FAIL Error de conexion: {e}")
        print(f"         Verificar DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME en .env")
        all_ok = False

    print()
    print("-" * 62)
    if all_ok:
        print("  RESULTADO: TODOS LOS PREREQUISITOS SATISFECHOS")
    else:
        print("  RESULTADO: HAY PREREQUISITOS FALLIDOS -- corregir antes de stamp")
    print("-" * 62)

    return all_ok


# ==============================================================================
# Stamp: Registrar baseline sin DDL
# ==============================================================================

def run_alembic_command(cmd: list, description: str) -> subprocess.CompletedProcess:
    """
    Ejecuta un comando alembic con encoding UTF-8 forzado.

    Razon del encoding explicito:
        En Windows, subprocess hereda el encoding del locale del sistema
        (tipicamente CP1252). Los mensajes de Alembic pueden contener
        caracteres fuera de CP1252, causando UnicodeDecodeError.
        Forzar UTF-8 previene este error en todos los casos.

    Args:
        cmd:         Lista de argumentos (ej: ["alembic", "stamp", "0001"])
        description: Descripcion para logging

    Returns:
        CompletedProcess con stdout/stderr como strings UTF-8
    """
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",   # Forzar UTF-8 (evita CP1252 default en Windows)
        errors="replace",   # Reemplazar bytes invalidos en lugar de crash
    )


def run_alembic_stamp(revision: str = "0001") -> bool:
    """
    Ejecuta 'alembic stamp <revision>' para registrar el baseline
    en la tabla alembic_version sin ejecutar ningun DDL.

    Este es el comando clave de la activacion inicial de M5.
    Solo debe ejecutarse UNA VEZ por environment.

    Args:
        revision: ID de la revision a marcar (default: '0001')

    Returns:
        bool: True si el stamp fue exitoso.
    """
    print(f"\n  Ejecutando: alembic stamp {revision}")
    print("  (Registra el baseline en alembic_version sin DDL)")

    result = run_alembic_command(
        ["alembic", "stamp", revision],
        description=f"stamp {revision}"
    )

    if result.returncode == 0:
        print(f"  OK  Stamp aplicado correctamente")
        if result.stdout.strip():
            print(f"      Output: {result.stdout.strip()}")
        return True
    else:
        print(f"  FAIL Error al aplicar stamp:")
        if result.stdout.strip():
            print(f"       stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"       stderr: {result.stderr.strip()}")
        return False


# ==============================================================================
# Status: Estado actual de Alembic
# ==============================================================================

def run_alembic_status() -> None:
    """
    Muestra el estado actual de Alembic: version activa, historial y
    si la DB esta al dia respecto a los scripts de migration.

    Comandos usados:
        alembic current -> version registrada en alembic_version de la DB
        alembic heads   -> ultima revision disponible en alembic/versions/
        alembic history -> historial completo de todas las revisions

    Por que NO se usa 'alembic check':
        'alembic check' ejecuta internamente --autogenerate, que requiere
        target_metadata con modelos SQLAlchemy ORM para comparar schemas.
        Nuestra estrategia es script-only (target_metadata = None), lo que
        causa que 'alembic check' siempre falle con un error esperado pero
        visualmente alarmante.

        La forma correcta de verificar pendientes en modo script-only es
        comparar 'alembic current' con 'alembic heads':
            current == heads  -> DB al dia
            current != heads  -> hay migrations sin aplicar
    """
    print()
    print("=" * 62)
    print("  ESTADO ACTUAL DE ALEMBIC")
    print("=" * 62)

    # alembic current: version registrada en la DB
    print("\n  Version activa en DB (alembic current):")
    result = run_alembic_command(["alembic", "current"], "current")
    current_output = result.stdout.strip()
    if not current_output:
        current_output = "Sin version registrada (stamp no aplicado aun)"
    print(f"    {current_output}")

    # Mostrar solo errores reales (no mensajes INFO de inicializacion)
    if result.stderr.strip():
        real_errors = [
            line for line in result.stderr.strip().split("\n")
            if "ERROR" in line or ("WARN" in line and "INFO" not in line)
        ]
        for err in real_errors:
            print(f"    WARN: {err}")

    # alembic heads: ultima revision disponible en /versions/
    print("\n  Ultima revision disponible (alembic heads):")
    result = run_alembic_command(["alembic", "heads"], "heads")
    heads_output = result.stdout.strip()
    if heads_output:
        print(f"    {heads_output}")
    else:
        print("    Sin revisiones definidas en alembic/versions/")

    # Evaluar si hay migrations pendientes comparando current vs heads
    print("\n  Migrations pendientes:")
    if "(head)" in current_output:
        print("    OK -- DB al dia, ninguna migration pendiente")
    elif current_output.startswith("Sin version"):
        print("    WARN -- stamp no aplicado.")
        print("    Ejecutar: python scripts/m5_alembic_setup.py --stamp")
    else:
        # Hay una version registrada pero no es (head): hay migrations sin aplicar
        print("    PENDIENTES -- hay migrations sin aplicar.")
        print("    Ejecutar: alembic upgrade head")

    # alembic history: historial completo
    print("\n  Historial completo (alembic history --verbose):")
    result = run_alembic_command(["alembic", "history", "--verbose"], "history")
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    else:
        print("    Sin historial disponible")


# ==============================================================================
# Main
# ==============================================================================

async def main(args: argparse.Namespace) -> None:
    """Funcion principal del script de setup."""

    print()
    print("  Fase M5 -- Alembic Migrations: Script de Activacion")
    print(f"  Environment: {'TEST (.env.test)' if args.env == 'test' else 'DEFAULT (.env)'}")

    load_environment(args.env)
    print()
    get_db_url_display()

    if args.check:
        ok = await check_prerequisites()
        sys.exit(0 if ok else 1)

    elif args.stamp:
        ok = await check_prerequisites()
        if not ok:
            print("\n  ABORT: Corregir los prerequisitos antes de aplicar stamp.")
            sys.exit(1)

        print()
        print("=" * 62)
        print("  APLICANDO STAMP")
        print("=" * 62)
        success = run_alembic_stamp("0001")

        if success:
            print("\n  Verificando estado final...")
            run_alembic_status()
            print()
            print("  M5 activado correctamente en este environment.")
            print("  Proximos pasos:")
            if args.env == "test":
                print("    1. Aplicar stamp en DEFAULT (PROD): python scripts/m5_alembic_setup.py --stamp")
            else:
                print("    1. Aplicar stamp en TEST si no se hizo: python scripts/m5_alembic_setup.py --stamp --env test")
            print("    2. Para crear una nueva migration:")
            print("       alembic revision -m \"descripcion_del_cambio\"")
            print("       (Editar el archivo generado, luego: alembic upgrade head)")
        else:
            print("\n  FAIL: El stamp fallo. Ver errores arriba.")
            sys.exit(1)

    elif args.status:
        run_alembic_status()

    else:
        print()
        print("  Uso:")
        print("    python scripts/m5_alembic_setup.py --check             Verificar prerequisitos")
        print("    python scripts/m5_alembic_setup.py --stamp             Aplicar stamp (PROD)")
        print("    python scripts/m5_alembic_setup.py --stamp --env test  Aplicar stamp (TEST)")
        print("    python scripts/m5_alembic_setup.py --status            Ver estado actual")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Script de validacion y activacion de Alembic -- Fase M5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/m5_alembic_setup.py --check
  python scripts/m5_alembic_setup.py --stamp
  python scripts/m5_alembic_setup.py --stamp --env test
  python scripts/m5_alembic_setup.py --status
        """,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Solo verificar prerequisitos sin aplicar nada",
    )
    parser.add_argument(
        "--stamp",
        action="store_true",
        help="Verificar prerequisitos y aplicar 'alembic stamp 0001'",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Mostrar estado actual de Alembic (current, history, migrations pendientes)",
    )
    parser.add_argument(
        "--env",
        choices=["default", "test"],
        default="default",
        help="Environment: 'default' usa .env, 'test' usa .env.test",
    )

    args = parser.parse_args()
    asyncio.run(main(args))
