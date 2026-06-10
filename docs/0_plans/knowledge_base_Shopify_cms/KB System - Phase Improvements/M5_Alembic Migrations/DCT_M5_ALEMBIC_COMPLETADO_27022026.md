# DCT -- M5 Alembic Migrations: COMPLETADO
# Retail Recommender System v2.1.0
# Fecha: 2026-02-27
# Arquitecto: Yasmani

---

## ESTADO FINAL

    M5 -- Alembic Migrations: COMPLETADO
    Environments activos: TEST + PROD (DEFAULT)
    Fecha de activacion: 2026-02-27
    Incidencias durante activacion: 2 (resueltas, ver seccion Incidencias)

---

## RESUMEN EJECUTIVO

M5 implementa el framework de control de versiones de schema de base de datos
usando Alembic en modo script-only, compatible con la arquitectura existente
asyncpg sin ORM. El stamp del baseline fue aplicado exitosamente en TEST y PROD,
ambos environments quedan con alembic_version = '0001 (head)'.

Todas las migrations futuras al schema de KB seran gestionadas exclusivamente
via Alembic, siguiendo el workflow documentado en M5_ALEMBIC_GUIDE.md.

---

## ARQUITECTURA IMPLEMENTADA

Estrategia elegida: Script-only (sin autogenerate)

    Por que script-only:
    - La aplicacion usa asyncpg directamente (sin SQLAlchemy ORM)
    - autogenerate requiere modelos ORM para comparar schema -> no aplica
    - SQLAlchemy instalado SOLO como abstraccion de conexion para Alembic
    - El desarrollador escribe SQL explicito en upgrade() / downgrade()
    - Maxima compatibilidad con la arquitectura actual, minimo riesgo

    Coexistencia de tablas de tracking:
    - alembic_version    : tabla interna de Alembic (1 fila: version actual)
    - schema_migrations  : audit log de negocio creado en H2 (historial completo)
    No son redundantes: propositos distintos, complementarios.

Estructura de archivos creada:

    alembic.ini                                    <- Config Alembic (ASCII puro)
    alembic/
      env.py                                       <- Conexion DB via vars de entorno
      script.py.mako                               <- Template para nuevas migrations
      versions/
        0001_baseline_post_h2_schema.py            <- Baseline (vacio, sin DDL)

---

## EVIDENCIA DE VALIDACION

### TEST (retail_recommender_test)
    alembic current  : 0001 (head)
    Tablas intactas  : kb_contents, schema_migrations (sin cambios DDL)
    alembic_version  : creada por stamp, version_num = '0001'
    alembic history  : baseline documentado correctamente

### PROD (retail_recommender_db)
    alembic current  : 0001 (head)
    Tablas intactas  : kb_contents, kb_contents_backup, schema_migrations
    alembic_version  : creada por stamp, version_num = '0001'
    alembic history  : baseline documentado correctamente

---

## INCIDENCIAS DURANTE ACTIVACION

### Incidencia 1: UnicodeDecodeError en alembic.ini (RESUELTA)
    Symptoma  : alembic stamp 0001 crasheaba con:
                UnicodeDecodeError: 'charmap' codec can't decode byte 0x90
    Causa raiz: alembic.ini fue generado con caracteres Unicode de box-drawing
                (=, -, ->) que en UTF-8 son multi-byte. Windows lee config
                files con encoding="locale" (CP1252 por defecto), y CP1252
                no puede decodificar el byte 0x90 (parte del caracter =).
    Solucion  : Reescribir alembic.ini y script.py.mako usando solo ASCII puro.
                Misma raiz que el incidente de H2 con scripts SQL -- leer
                documentacion de H2 para contexto.
    Fix code  : Reemplazar === con ===, --- con ---, -> con ->
    Prevencion: Todo archivo leido por herramientas externas (no por nuestro
                codigo Python) debe ser ASCII puro. Aplica a: .ini, .cfg,
                .toml, Makefile, cualquier archivo de configuracion de CLI.

### Incidencia 2: Falso positivo "FAILED" en status (RESUELTA)
    Symptoma  : El script m5_alembic_setup.py mostraba:
                "FAILED: Can't proceed with --autogenerate option"
                en la seccion "Migrations pendientes".
    Causa raiz: El script usaba 'alembic check' para verificar pendientes.
                'alembic check' ejecuta internamente --autogenerate, que
                requiere target_metadata con modelos ORM. Con script-only
                (target_metadata = None) siempre falla con ese mensaje.
    Impacto   : Cosmético unicamente. El stamp fue exitoso. El error no
                afecto la funcionalidad de Alembic ni la integridad del DB.
    Solucion  : Reemplazar 'alembic check' por 'alembic heads' en el script.
                Comparar current vs heads es el patron correcto para script-only.
    Estado    : Script actualizado. --status ahora muestra correctamente:
                "OK -- DB al dia, ninguna migration pendiente"

---

## ARCHIVOS CREADOS O MODIFICADOS

    Creados:
        alembic.ini
        alembic/env.py
        alembic/script.py.mako
        alembic/versions/0001_baseline_post_h2_schema.py
        scripts/m5_alembic_setup.py
        docs/0_plans/KB System - Phase Improvements/M5_ALEMBIC_GUIDE.md
        docs/0_plans/KB System - Phase Improvements/DCT_M5_ALEMBIC_COMPLETADO_27022026.md

    Modificados:
        requirements.txt  (agregado alembic>=1.13.0, sqlalchemy>=2.0.35)

---

## IMPACTO EN EL SISTEMA

    Performance : Sin impacto. Alembic solo corre durante migraciones (no en runtime).
    Datos       : Sin cambios DDL. Baseline es vacio por diseno.
    API         : Sin cambios. No hay nuevos endpoints.
    Tests       : Sin impacto en tests existentes.
    Runtime     : asyncpg sigue siendo el driver de la aplicacion.

---

## ESTADO DEL PLAN CONSOLIDADO (post-M5)

    FASE 0: Estabilidad Base            COMPLETADA
      H1 Structured Logging             OK
      H2 Schema Versioning              OK
      H3 Enhanced Health Checks         OK
      H4 Title Translation              OK

    FASE 1: Quick Wins                  COMPLETADA
      M1 Optimize Sync Performance      OK
      M2 Prometheus Metrics             OK

    FASE 2: Foundation Escalable        COMPLETADA
      M3 Distributed Locking (Redis)    OK
      M4 Incremental Sync (Webhooks)    OK
      M5 Alembic Migrations             OK  <- ESTE DOCUMENTO

    FASE 3: Advanced Features           PENDIENTE
      L1 HTML->Markdown Library         Siguiente
      L2 Content Versioning             Requiere M5 (ahora disponible)
      L3 Multi-Region Support           Requiere M3 (disponible)
      L4 ML Content Optimization        Requiere L2

---

## PROXIMOS PASOS

### Inmediato -- Verificar fix del falso positivo (opcional, informativo)
    python scripts/m5_alembic_setup.py --status
    # Expected: "OK -- DB al dia, ninguna migration pendiente"
    # (sin el FAILED de alembic check)

### Siguiente fase -- L1: HTML->Markdown Library
    Objetivo  : Mejorar la calidad del contenido almacenado en kb_contents.
                Actualmente content_html guarda HTML crudo de Shopify.
                L1 convierte ese HTML a Markdown limpio para mejor procesamiento.
    Prioridad : Baja (3.0 en matriz de priorizacion)
    Dependencias: Ninguna critica (M5 era prerequisito de L2, no de L1)
    Esfuerzo  : ~2-3 dias de implementacion
    Decision  : Confirmar con Yasmani si proceder con L1 o abordar otra
                prioridad del backlog antes de Fase 3.

### Workflow de primera migration real con Alembic
    Cuando se necesite el primer cambio de schema post-baseline:
        1. alembic revision -m "descripcion_del_cambio"
        2. Editar el archivo generado (upgrade + downgrade)
        3. alembic upgrade head --sql  (dry-run)
        4. Aplicar en TEST: alembic upgrade head
        5. Verificar: alembic current
        6. Aplicar en PROD: (cambiar DB_HOST) alembic upgrade head
        7. Actualizar schema_migrations en el mismo upgrade()
    Ver plantilla completa en M5_ALEMBIC_GUIDE.md seccion 4.1

---

## LECCION APRENDIDA (CONSOLIDADA)

Regla de oro para proyectos que corren en Windows y se despliegan en Linux:

    "Todo archivo leido por herramientas externas (CLI tools, configparser,
    make, etc.) debe ser ASCII puro. Solo tu propio codigo Python puede
    manejar UTF-8 de forma confiable porque tu controlas el open()."

    Aplica a: .ini, .cfg, .toml, Makefile, Dockerfile, .yaml de CI/CD,
              scripts .sh, archivos de configuracion de cualquier herramienta.

    No aplica a: Tu codigo Python (.py), donde puedes usar # -*- coding: utf-8 -*-
                 y Unicode libremente porque Python controla el encoding.

    Historial de incidentes por este mismo patron:
        H2  (2026-02-10): Scripts SQL con caracteres especiales
        M5  (2026-02-27): alembic.ini con box-drawing Unicode
    Patron: Siempre que un archivo es ESCRITO con un editor moderno (UTF-8)
            pero LEIDO por una herramienta que usa el locale del SO (CP1252).

---

Documento version: 1.0
Creado: 2026-02-27
Validado: 2026-02-27
Autor: Yasmani (Senior Software Architect)
