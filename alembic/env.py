"""
Alembic Migration Environment -- Retail Recommender System
==========================================================

Fase:      M5 -- Alembic Migrations
Estrategia: Script-only (sin autogenerate, sin SQLAlchemy ORM)

Variables de entorno requeridas:
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
    Alternativa: DATABASE_URL (URL completa, tiene prioridad)

Compatibilidad con Neon / Cloud Run / Cloud SQL:
    Este archivo detecta automaticamente si se necesita SSL
    y lo configura de forma compatible con asyncpg.

NOTA SOBRE IMPORTS EN EL EDITOR:
    Si el editor muestra "Import sqlalchemy could not be resolved",
    verificar que el interprete de Python apunta al venv del proyecto:
        .\\venv\\Scripts\\python.exe  (Windows)
    SQLAlchemy esta instalado en el venv. Los imports son correctos
    en runtime -- es un falso positivo del editor sin venv configurado.
"""

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool                                   # type: ignore[import]
from sqlalchemy.ext.asyncio import async_engine_from_config  # type: ignore[import]
from alembic import context

# -- 1. Cargar .env -----------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
    else:
        load_dotenv()
except ImportError:
    pass

# -- 2. Configuracion de Alembic ----------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -- 3. Parametros incompatibles con asyncpg ----------------------------------
# asyncpg NO acepta estos parametros como query params en la URL.
# Son propios de psycopg2/libpq. Si se pasan, asyncpg lanza:
#   TypeError: connect() got an unexpected keyword argument 'sslmode'
# Solucion: removerlos de la URL y pasar SSL via connect_args={"ssl": "require"}
_ASYNCPG_INCOMPATIBLE_PARAMS = {"sslmode", "channel_binding"}


def get_database_url() -> tuple:
    """
    Retorna (url_limpia, connect_args) compatibles con asyncpg.

    CAMBIO respecto a version anterior:
        Antes: retornaba str (solo la URL)
        Ahora: retorna tuple (url, connect_args)

    Por que el cambio:
        La URL de Neon incluye ?sslmode=require&channel_binding=require
        asyncpg no entiende 'sslmode' como query param (es de psycopg2).
        La solucion es limpiar esos params de la URL y pasar SSL como
        connect_args={"ssl": "require"}, que asyncpg si entiende.

    Retrocompatible con localhost:
        Cuando no hay sslmode en la URL, connect_args es {}
        y el comportamiento es identico a la version anterior.

    Returns:
        tuple: (url: str, connect_args: dict)
    """
    def _clean_url_for_asyncpg(raw_url: str) -> tuple:
        # Normalizar scheme para SQLAlchemy + asyncpg
        url = raw_url.replace("postgres://", "postgresql+asyncpg://")
        url = url.replace("postgresql://", "postgresql+asyncpg://")

        # Detectar SSL en la URL ORIGINAL antes de modificarla
        needs_ssl = any(
            marker in raw_url
            for marker in (
                "sslmode=require",
                "sslmode=verify-full",
                "sslmode=verify-ca",
            )
        )

        # Remover query params incompatibles con asyncpg
        if "?" in url:
            base, query_string = url.split("?", 1)
            clean_params = [
                p for p in query_string.split("&")
                if p and not any(
                    p.startswith(bad)
                    for bad in _ASYNCPG_INCOMPATIBLE_PARAMS
                )
            ]
            url = f"{base}?{'&'.join(clean_params)}" if clean_params else base

        connect_args = {"ssl": "require"} if needs_ssl else {}
        return url, connect_args

    # Opcion 1: DATABASE_URL completa (Neon, Cloud Run, Cloud SQL)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return _clean_url_for_asyncpg(database_url)

    # Opcion 2: Variables individuales (localhost / desarrollo local)
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "5432")
    name     = os.getenv("DB_NAME")
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD", "")

    missing = [
        var for var, val in [
            ("DB_HOST", host), ("DB_NAME", name), ("DB_USER", user),
        ]
        if not val
    ]
    if missing:
        raise ValueError(
            f"Alembic env.py: Faltan variables de entorno: {missing}. "
            f"Verifica que el archivo .env contiene DB_HOST, DB_PORT, "
            f"DB_USER, DB_PASSWORD, DB_NAME."
        )

    url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
    return url, {}  # localhost: sin SSL


# -- 4. target_metadata = None (script-only) ----------------------------------
target_metadata = None


# -- 5. Modo OFFLINE ----------------------------------------------------------
def run_migrations_offline() -> None:
    """Genera SQL sin conectar a la DB. Uso: alembic upgrade head --sql"""
    url, _connect_args = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


# -- 6. Modo ONLINE -----------------------------------------------------------
def do_run_migrations(connection) -> None:
    """Ejecuta las migrations con una conexion activa."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Crea el engine async y aplica las migrations.

    NullPool: no reutilizar conexiones (evita bloqueos en ALTER/CREATE TABLE).
    connect_args: {"ssl": "require"} para Neon/Cloud, {} para localhost.
    """
    db_url, connect_args = get_database_url()

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = db_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,    # no pool para migrations
        connect_args=connect_args,  # SSL para Neon; {} para localhost
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point online."""
    asyncio.run(run_async_migrations())


# -- 7. Entry point -----------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()