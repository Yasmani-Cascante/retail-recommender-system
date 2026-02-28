"""
Alembic Migration Environment — Retail Recommender System
==========================================================

Fase:      M5 — Alembic Migrations
Estrategia: Script-only (sin autogenerate, sin SQLAlchemy ORM)

Por qué script-only:
    La aplicación usa asyncpg directamente (no SQLAlchemy ORM).
    El autogenerate de Alembic requiere modelos SQLAlchemy para comparar
    el schema real vs los modelos. Como no tenemos esos modelos, escribimos
    las migrations como SQL explícito en los scripts Python.
    SQLAlchemy se usa SOLO para que Alembic gestione la conexión y la tabla
    de control de versiones (alembic_version).

Variables de entorno requeridas (definidas en .env):
    DB_HOST     -> host de PostgreSQL (ej: localhost, o IP de Cloud SQL)
    DB_PORT     -> puerto (default: 5432)
    DB_USER     -> usuario de la base de datos
    DB_PASSWORD -> contrasena
    DB_NAME     -> nombre de la base de datos

    Alternativa: DATABASE_URL (URL completa, tiene prioridad si esta definida)

Compatibilidad con Cloud SQL (planes futuros):
    Solo cambiar DB_HOST en .env apuntando a la IP/socket de Cloud SQL.
    Este archivo no requiere ningun cambio.

Tabla de control de Alembic:
    'alembic_version' separada de 'schema_migrations' (nuestro audit log propio).
    Coexisten sin conflicto. Ver M5_ALEMBIC_GUIDE.md para detalles.
"""

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# ── 1. Cargar .env antes de leer cualquier variable ─────────────────────────
# Usamos python-dotenv (ya en requirements.txt).
# Path resuelto desde alembic/ hacia la raiz del proyecto.
try:
    from dotenv import load_dotenv

    # Ruta absoluta al .env: subir un nivel desde /alembic/ -> raiz del proyecto
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
    else:
        # Fallback: buscar .env en el directorio de trabajo actual
        load_dotenv()
except ImportError:
    # python-dotenv no disponible; las variables deben estar ya en el entorno
    pass

# ── 2. Objeto de configuracion de Alembic (lee alembic.ini) ─────────────────
config = context.config

# Configurar logging desde alembic.ini (secciones [loggers], [handlers], etc.)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ── 3. Construir URL de conexion desde variables de entorno ─────────────────
def get_database_url() -> str:
    """
    Construye la URL de conexion PostgreSQL async desde variables de entorno.

    Prioridad:
        1. DATABASE_URL (URL completa, si esta definida)
        2. Variables individuales: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

    El driver usado es 'postgresql+asyncpg' necesario para el template async
    y compatible con el asyncpg que ya usa la aplicacion en runtime.

    Returns:
        str: URL completa en formato SQLAlchemy async.
             Ej: postgresql+asyncpg://postgres:admin@localhost:5432/retail_recommender_db

    Raises:
        ValueError: Si no hay suficientes variables para construir la URL.
    """
    # Opcion 1: URL completa (util para Cloud Run, Cloud SQL con socket, etc.)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Normalizar el scheme al formato asyncpg que espera SQLAlchemy
        url = database_url.replace("postgres://", "postgresql+asyncpg://")
        url = url.replace("postgresql://", "postgresql+asyncpg://")
        return url

    # Opcion 2: Variables individuales (configuracion actual del proyecto en .env)
    # Valores leidos directamente del .env:
    #   DB_HOST=localhost
    #   DB_PORT=5432
    #   DB_USER=postgres
    #   DB_PASSWORD=admin
    #   DB_NAME=retail_recommender_db
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD", "")

    # Validar que las variables criticas existen
    missing = [
        var for var, val in [
            ("DB_HOST", host),
            ("DB_NAME", name),
            ("DB_USER", user),
        ]
        if not val
    ]

    if missing:
        raise ValueError(
            f"Alembic env.py: Faltan variables de entorno: {missing}. "
            f"Verifica que el archivo .env esta en la raiz del proyecto y "
            f"contiene DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME."
        )

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


# ── 4. target_metadata = None (estrategia script-only) ──────────────────────
# En modo autogenerate, aqui iria el MetaData de los modelos SQLAlchemy.
# Como usamos script-only, no hay modelos ORM que comparar.
# Cada migration es SQL explicito escrito por el desarrollador.
target_metadata = None


# ── 5. Modo OFFLINE: genera SQL sin conectar a la DB ────────────────────────
def run_migrations_offline() -> None:
    """
    Ejecuta las migrations en modo 'offline'.

    Util para:
    - Revisar el SQL que se va a aplicar antes de ejecutarlo (dry-run)
    - CI/CD pipelines que solo validan sintaxis
    - Ambientes sin acceso directo a la DB

    Uso: alembic upgrade head --sql
    """
    url = get_database_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Tabla de control de versiones de Alembic (separada de schema_migrations)
        version_table="alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


# ── 6. Modo ONLINE: aplica las migrations conectando a la DB ─────────────────
def do_run_migrations(connection) -> None:
    """
    Configura el contexto y ejecuta las migrations con una conexion activa.

    Este metodo es llamado por run_async_migrations() dentro del contexto
    async, pasando la conexion ya establecida.

    Args:
        connection: Conexion SQLAlchemy activa (asyncpg bajo el capo).
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Tabla de control exclusiva de Alembic.
        # NOTA: 'schema_migrations' es nuestro audit log propio (distinta tabla).
        version_table="alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Crea el engine async y ejecuta las migrations.

    Usa NullPool deliberadamente: en scripts de migration no queremos
    reutilizar conexiones. Cada ejecucion abre y cierra su propia conexion,
    evitando conexiones huerfanas que podrian bloquear el schema durante
    ALTER TABLE o CREATE TABLE.

    NullPool + asyncpg = patron recomendado para migration runners.
    """
    # Obtener configuracion base de alembic.ini y agregar la URL de DB
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    # Crear engine async con NullPool (sin pool de conexiones para migrations)
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Critico: no reutilizar conexiones en migrations
    )

    # Conectar y ejecutar migrations dentro del contexto async
    async with connectable.connect() as connection:
        # run_sync permite ejecutar codigo sincrono (do_run_migrations)
        # dentro de un contexto async: patron estandar de Alembic async
        await connection.run_sync(do_run_migrations)

    # Liberar el engine despues de usarlo
    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Entry point para el modo online.

    Llama a run_async_migrations() usando asyncio.run() para ejecutar
    el codigo async desde el contexto sincrono de Alembic.
    """
    asyncio.run(run_async_migrations())


# ── 7. Entry point: Alembic determina el modo automaticamente ───────────────
# Alembic llama a este modulo directamente.
# context.is_offline_mode() retorna True cuando se usa --sql (dry-run),
# False para ejecucion normal (conecta a la DB y aplica migrations).
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
