"""
L2 Content Versioning — Backfill Script
========================================

Popula el campo content_hash en todos los registros de kb_contents que
tienen content_hash = NULL (estado post-migration 0002, pre-backfill).

CUÁNDO EJECUTAR:
    Una sola vez, inmediatamente después de aplicar la migration 0002:
        1. alembic upgrade head                                     # Aplica 0002
        2. python scripts/l2_backfill_content_hash.py --dry-run    # Verificar
        3. python scripts/l2_backfill_content_hash.py               # Ejecutar
        4. python scripts/l2_backfill_content_hash.py --verify      # Confirmar

POR QUÉ ES NECESARIO:
    La migration 0002 agrega content_hash como columna NULLABLE intencionalmente.
    Los registros existentes quedan con NULL hasta este backfill.
    Sin el backfill:
    - L2 tratará TODOS los registros como "cambio pendiente" en el primer ciclo
      (porque NULL != cualquier hash → fuerza un UPDATE innecesario en todos).
    - Esto es aceptable funcionalmente pero ineficiente (26 UPDATEs de golpe).
    El backfill calcula el SHA256 del contenido actual de cada registro
    y lo escribe directamente, dejando a L2 en un estado consistente.

IDEMPOTENCIA:
    El script solo actualiza filas con content_hash IS NULL.
    Ejecutarlo múltiples veces es seguro — las filas ya backfilled no se tocan.

OPCIONES:
    --dry-run           Mostrar cuántas filas se procesarían sin escribir nada.
    --batch-size N      Procesar en batches de N filas (default: 100).
    --verbose           Log detallado de cada fila procesada.
    --verify            Solo verificar el estado del backfill sin ejecutarlo.
    --database-url URL  DSN completo (override de las vars DB_* del .env).

RESOLUCIÓN DE CONEXIÓN (en orden de prioridad):
    1. --database-url postgresql://user:pass@host:5432/db   (argumento CLI)
    2. Variable de entorno DATABASE_URL                      (DSN completo)
    3. Variables individuales DB_HOST / DB_PORT / DB_USER /  (desde .env)
       DB_PASSWORD / DB_NAME                                 del proyecto

Autor: Retail Recommender System Team
Fecha: 2026-03-01
Fase: L2 — Content Versioning
"""

import argparse
import asyncio
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# CARGA DEL .env DEL PROYECTO
# ──────────────────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """
    Carga el archivo .env del proyecto (raíz del repositorio).

    Por qué lo hacemos nosotros en lugar de python-dotenv:
    - Queremos que el script sea auto-contenido sin dependencias extras.
    - El parsing que necesitamos es sencillo: KEY=VALUE por línea.
    - Solo cargamos variables que AÚN NO están en el entorno (no sobreescribimos
      lo que el usuario configuró explícitamente en su shell).

    Formato soportado:
      KEY=VALUE           → asignación simple
      KEY="VALUE CON ESPACIOS"  → comillas dobles
      KEY='VALUE'         → comillas simples
      # comentario        → ignorado
      (línea vacía)       → ignorada
    """
    # Buscar .env en la raíz del proyecto (2 niveles arriba desde scripts/)
    script_dir = Path(__file__).resolve().parent        # .../scripts/
    project_root = script_dir.parent                    # .../retail-recommender-system/
    dotenv_path = project_root / ".env"

    if not dotenv_path.exists():
        return  # Sin .env → continuar sin él, el usuario puede tener las vars en el shell

    with open(dotenv_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Ignorar líneas vacías y comentarios
            if not line or line.startswith("#"):
                continue
            # Ignorar líneas sin '='
            if "=" not in line:
                continue

            key, _, raw_value = line.partition("=")
            key = key.strip()
            raw_value = raw_value.strip()

            # Quitar comillas envolventes si las hay
            if len(raw_value) >= 2:
                if (raw_value[0] == '"' and raw_value[-1] == '"') or \
                   (raw_value[0] == "'" and raw_value[-1] == "'"):
                    raw_value = raw_value[1:-1]

            # Solo setear si la variable NO existe ya en el entorno
            # (respetamos lo que el usuario configuró explícitamente)
            if key and key not in os.environ:
                os.environ[key] = raw_value


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _sha256(content: str) -> str:
    """
    Calcula SHA256 del contenido Markdown.

    DEBE ser idéntico a ShopifyKBSyncService._compute_content_hash().
    Usamos la misma lógica directamente aquí para no importar el servicio
    entero (y sus dependencias de Shopify, Redis, etc.) en un script de backfill.

    Args:
        content: Contenido Markdown como string

    Returns:
        64 caracteres hexadecimales del SHA256
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _log(message: str, level: str = "INFO") -> None:
    """
    Logger minimalista para el script.

    No usamos structlog aquí para mantener el script independiente
    de la configuración de la aplicación.
    El timestamp en UTC facilita correlación con los logs de Cloud Run.
    """
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{ts}] [{level}] {message}", flush=True)


def _resolve_db_url(database_url: Optional[str] = None) -> str:
    """
    Resuelve la URL de conexión a PostgreSQL con la siguiente prioridad:

    1. database_url  → pasado como argumento CLI (--database-url)
    2. DATABASE_URL  → variable de entorno con DSN completo
    3. DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME
                     → variables individuales tal como están en el .env del proyecto

    Raises:
        SystemExit: Si no se puede determinar ninguna URL válida.
    """
    # Prioridad 1: argumento explícito CLI
    if database_url:
        _log(f"Usando --database-url proporcionado (... @{_redact_url(database_url)})")
        return database_url

    # Prioridad 2: DSN completo en el entorno
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        _log(f"Usando DATABASE_URL del entorno (@{_redact_url(env_url)})")
        return env_url

    # Prioridad 3: Variables individuales del .env del proyecto
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "5432")
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD", "")
    dbname   = os.getenv("DB_NAME")

    if host and user and dbname:
        url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        _log(f"URL ensamblada desde variables DB_*: @{host}:{port}/{dbname}")
        return url

    # Ninguna opción funcionó
    _log(
        "No se encontró configuración de base de datos. Opciones:\n"
        "  1. python scripts/l2_backfill_content_hash.py "
        "--database-url postgresql://user:pass@host:5432/db\n"
        "  2. export DATABASE_URL=postgresql://user:pass@host:5432/db\n"
        "  3. Definir DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME en el .env del proyecto",
        "ERROR"
    )
    sys.exit(1)


def _redact_url(url: str) -> str:
    """
    Oculta la contraseña en una URL de DB para logs seguros.

    Ejemplo:
        postgresql://postgres:admin@localhost:5432/db  →  localhost:5432/db
    """
    try:
        # Extraer solo host:port/db sin credenciales
        # "postgresql://user:pass@host:port/db" → dividir en '@'
        after_at = url.split("@", 1)[-1] if "@" in url else url
        return after_at
    except Exception:
        return "***"


# ──────────────────────────────────────────────────────────────────────────────
# CORE BACKFILL LOGIC
# ──────────────────────────────────────────────────────────────────────────────

async def run_backfill(
    dry_run: bool = False,
    batch_size: int = 100,
    verbose: bool = False,
    database_url: Optional[str] = None,
) -> int:
    """
    Ejecuta el backfill de content_hash en todos los registros con NULL.

    ALGORITMO:
    1. Contar filas con content_hash IS NULL (diagnóstico inicial).
    2. Fetch de filas en batches usando LIMIT/OFFSET para no bloquear la DB.
    3. Para cada fila: calcular SHA256 del campo 'content'.
    4. UPDATE en batch (una query con múltiples valores via unnest()).
    5. Reportar estadísticas finales.

    ATOMICIDAD POR BATCH:
    Cada batch se actualiza como una sola query (autocommit de asyncpg).
    Si el script se interrumpe, los batches completados quedan en DB
    y el script es idempotente (el próximo run retoma desde WHERE IS NULL).

    ESTRATEGIA unnest vs N UPDATEs individuales:
    unnest permite hacer un UPDATE masivo tipado que PostgreSQL ejecuta
    en un solo plan. Con solo 26 registros esto es overkill, pero es
    la práctica correcta para backfills más grandes.

    Args:
        dry_run:      Si True, solo cuenta y muestra sin escribir.
        batch_size:   Número de filas por batch de UPDATE.
        verbose:      Si True, logea cada fila procesada.
        database_url: URL de PostgreSQL. Si None, se resuelve automáticamente.

    Returns:
        Número de filas actualizadas (0 en dry-run).
    """
    try:
        import asyncpg
    except ImportError:
        _log("asyncpg no está instalado. Instalar: pip install asyncpg", "ERROR")
        sys.exit(1)

    db_url = _resolve_db_url(database_url)
    _log(f"Conectando a base de datos... (dry_run={dry_run})")

    # Usamos una conexión simple, no pool, porque el backfill es secuencial.
    try:
        conn = await asyncpg.connect(db_url)
        _log("Conexión establecida. ✅")
    except Exception as e:
        _log(f"No se pudo conectar a la DB: {e}", "ERROR")
        sys.exit(1)

    try:
        # ── PASO 1: Diagnóstico inicial ────────────────────────────────────
        total_records = await conn.fetchval("SELECT COUNT(*) FROM kb_contents")
        null_hash_count = await conn.fetchval(
            "SELECT COUNT(*) FROM kb_contents WHERE content_hash IS NULL"
        )
        already_backfilled = total_records - null_hash_count

        _log(f"Total registros en kb_contents:            {total_records}")
        _log(f"  Ya backfilled (content_hash NOT NULL):   {already_backfilled}")
        _log(f"  Pendientes de backfill (NULL):           {null_hash_count}")

        if null_hash_count == 0:
            _log("No hay registros pendientes de backfill. Nada que hacer. ✅")
            return 0

        if dry_run:
            _log(
                f"DRY RUN: Se actualizarían {null_hash_count} registros "
                f"en batches de {batch_size}. No se escribió nada."
            )
            return 0

        # ── Confirmación interactiva (si hay TTY) ─────────────────────────
        # En CI/CD el stdin no es TTY → se omite automáticamente.
        if sys.stdin.isatty():
            print(
                f"\n⚠️  Se van a calcular y escribir {null_hash_count} content_hash(es) "
                f"en kb_contents.\n"
                f"   Esta operación es segura (solo escribe en filas con NULL) y\n"
                f"   no afecta las columnas de contenido existentes.\n"
            )
            confirm = input("   ¿Continuar? (s/n): ").strip().lower()
            if confirm not in ("s", "si", "y", "yes"):
                _log("Backfill cancelado por el usuario.")
                return 0
            print()

        # ── PASO 2-4: Fetch → Calcular → UPDATE en batches ────────────────
        offset = 0
        total_updated = 0
        batch_number = 0
        started_at = datetime.utcnow()

        while True:
            batch_number += 1

            # Fetch del siguiente batch de filas sin hash.
            # ORDER BY id garantiza paginación estable aunque haya writes concurrentes.
            rows = await conn.fetch(
                """
                SELECT id, content, sub_intent, language
                FROM kb_contents
                WHERE content_hash IS NULL
                ORDER BY id
                LIMIT $1
                OFFSET $2
                """,
                batch_size,
                offset,
            )

            if not rows:
                break  # No quedan filas → terminamos

            # Calcular SHA256 en Python para cada fila del batch.
            # Es CPU puro (sin I/O) → no necesita ser async.
            updates: List[tuple] = []
            for row in rows:
                content = row["content"] or ""  # Defender contra content=NULL
                content_hash = _sha256(content)
                updates.append((str(row["id"]), content_hash))

                if verbose:
                    _log(
                        f"  [{row['sub_intent']}/{row['language']}] "
                        f"id={str(row['id'])[:8]}... "
                        f"hash={content_hash[:16]}...",
                        "DEBUG"
                    )

            # UPDATE masivo usando unnest — una sola query por batch.
            # unnest($1::uuid[], $2::varchar[]) crea una tabla virtual de pares
            # (id, hash) que PostgreSQL usa como fuente del UPDATE en un solo plan.
            ids    = [u[0] for u in updates]
            hashes = [u[1] for u in updates]

            updated_count = await conn.execute(
                """
                UPDATE kb_contents AS kc
                SET content_hash = v.hash
                FROM unnest($1::uuid[], $2::varchar[]) AS v(id, hash)
                WHERE kc.id = v.id
                  AND kc.content_hash IS NULL
                """,
                ids,
                hashes,
            )

            # asyncpg.execute() retorna un string como "UPDATE 26" — parseamos el número.
            try:
                batch_updated = int(updated_count.split()[-1])
            except (ValueError, IndexError, AttributeError):
                batch_updated = len(updates)  # Fallback conservador

            total_updated += batch_updated
            offset += batch_size

            _log(
                f"Batch {batch_number}: {len(rows)} filas leídas, "
                f"{batch_updated} actualizadas. "
                f"Acumulado: {total_updated}/{null_hash_count}"
            )

        # ── PASO 5: Reporte final ──────────────────────────────────────────
        duration = (datetime.utcnow() - started_at).total_seconds()
        remaining_null = await conn.fetchval(
            "SELECT COUNT(*) FROM kb_contents WHERE content_hash IS NULL"
        )

        _log("─" * 60)
        _log(f"Backfill completado en {duration:.1f}s")
        _log(f"  Filas actualizadas:              {total_updated}")
        _log(f"  Filas con hash NULL restantes:   {remaining_null}")

        if remaining_null == 0:
            _log("✅ Todos los registros tienen content_hash. L2 listo para activar.")
        else:
            _log(
                f"⚠️  Quedan {remaining_null} registros con content_hash=NULL. "
                "Posibles causas: content=NULL en esas filas, o interrupción del script.",
                "WARN"
            )

        return total_updated

    finally:
        await conn.close()
        _log("Conexión cerrada.")


# ──────────────────────────────────────────────────────────────────────────────
# VERIFICACIÓN POST-BACKFILL
# ──────────────────────────────────────────────────────────────────────────────

async def verify_backfill(database_url: Optional[str] = None) -> None:
    """
    Verifica el estado del backfill y muestra estadísticas detalladas.

    Muestra:
    - Total de registros y cuántos tienen content_hash
    - Distribución por idioma
    - Muestra de los primeros 3 hashes (para debugging)
    - Existencia y conteo de kb_content_versions
    """
    try:
        import asyncpg
    except ImportError:
        _log("asyncpg no disponible.", "ERROR")
        return

    db_url = _resolve_db_url(database_url)
    conn = await asyncpg.connect(db_url)

    try:
        _log("── Verificación post-backfill ──────────────────────────────")

        # Estadísticas generales
        stats = await conn.fetch(
            """
            SELECT
                COUNT(*)                    AS total,
                COUNT(content_hash)         AS with_hash,
                COUNT(*) - COUNT(content_hash) AS without_hash,
                COUNT(DISTINCT content_hash)   AS unique_hashes
            FROM kb_contents
            """
        )
        row = stats[0]
        _log(f"Total registros:          {row['total']}")
        _log(f"Con content_hash:         {row['with_hash']}")
        _log(f"Sin content_hash (NULL):  {row['without_hash']}")
        _log(f"Hashes únicos:            {row['unique_hashes']}")

        # Distribución por idioma
        _log("")
        _log("Distribución por idioma:")
        by_lang = await conn.fetch(
            """
            SELECT language,
                   COUNT(*) AS total,
                   COUNT(content_hash) AS with_hash
            FROM kb_contents
            GROUP BY language
            ORDER BY language
            """
        )
        for lang_row in by_lang:
            ok = lang_row["total"] == lang_row["with_hash"]
            status = "✅" if ok else "⚠️"
            _log(
                f"  {status} {lang_row['language']}: "
                f"{lang_row['with_hash']}/{lang_row['total']} con hash"
            )

        # Muestra de hashes para debugging
        _log("")
        _log("Muestra de hashes (primeros 3 registros):")
        samples = await conn.fetch(
            """
            SELECT sub_intent, language, content_hash, content_version
            FROM kb_contents
            WHERE content_hash IS NOT NULL
            ORDER BY sub_intent, language
            LIMIT 3
            """
        )
        for s in samples:
            _log(
                f"  [{s['sub_intent']}/{s['language']}] "
                f"hash={s['content_hash'][:20]}... "
                f"version={s['content_version']}"
            )

        # Verificar tabla kb_content_versions
        _log("")
        versions_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'kb_content_versions'
            )
            """
        )
        if versions_exists:
            versions_count = await conn.fetchval("SELECT COUNT(*) FROM kb_content_versions")
            _log(f"Tabla kb_content_versions: ✅ existe ({versions_count} filas)")
        else:
            _log(
                "Tabla kb_content_versions: ❌ NO EXISTE. "
                "¿Se aplicó la migration 0002? → alembic upgrade head",
                "WARN"
            )

        _log("── Fin de verificación ─────────────────────────────────────")

    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "L2 Content Versioning — Backfill de content_hash en kb_contents.\n"
            "Ejecutar UNA VEZ después de aplicar la migration 0002."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Flujo recomendado:
  1. alembic upgrade head
  2. python scripts/l2_backfill_content_hash.py --dry-run
  3. python scripts/l2_backfill_content_hash.py
  4. python scripts/l2_backfill_content_hash.py --verify
  5. Agregar KB_CONTENT_VERSIONING=true al .env y reiniciar el servicio
        """
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Mostrar impacto sin escribir nada.")
    parser.add_argument("--batch-size", type=int, default=100, metavar="N",
                        help="Filas por batch (default: 100).")
    parser.add_argument("--verbose",  action="store_true",
                        help="Log detallado de cada fila.")
    parser.add_argument("--verify",   action="store_true",
                        help="Solo verificar el estado, no ejecutar backfill.")
    parser.add_argument("--database-url", type=str, default=None, metavar="URL",
                        help="DSN completo de PostgreSQL (override de vars DB_* / DATABASE_URL).")

    args = parser.parse_args()

    # Cargar .env del proyecto ANTES de resolver la URL
    # (para que DB_HOST, DB_USER, etc. estén disponibles en os.environ)
    _load_dotenv()

    if args.verify:
        asyncio.run(verify_backfill(database_url=args.database_url))
    else:
        asyncio.run(
            run_backfill(
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                verbose=args.verbose,
                database_url=args.database_url,
            )
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
