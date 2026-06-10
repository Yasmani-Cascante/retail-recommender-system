**RETAIL RECOMMENDER SYSTEM**

**Documento de Cierre — Migración a Neon**

Infraestructura PostgreSQL Serverless · Producción Validada

| **Versión del Sistema** | v2.1.0 (Async-First Architecture) |
| --- | --- |
| **Estado del Documento** | FINAL — Aprobado para Archivo |
| **Fecha de Cierre** | 04 de Marzo de 2026 |
| **Arquitecto Responsable** | Yasmani (Senior Software Architect) |
| **Plataforma de Destino** | Neon Pro (PostgreSQL 16 Serverless) |
| **Entorno de Ejecución** | Google Cloud Run (FastAPI · asyncpg) |
| **Artefacto de Validación** | Smoke Test v2.3 — 79 PASS / 3 WARN / 0 FAIL |
| **Siguiente Fase** | L4 — ML Content Optimization |

Retail Recommender System · docs/migrations/neon/

**1\. Contexto y Motivación**

**1.1 Situación Anterior**

Durante las fases iniciales del proyecto (v1.x), el sistema utilizaba una instancia de PostgreSQL local ejecutándose en la máquina de desarrollo del arquitecto. Esta configuración fue suficiente para las fases de prototipo y validación inicial del sistema de recomendaciones, pero representaba una dependencia estructural que impedía avanzar hacia un entorno verdaderamente productivo.

La base de datos local almacenaba el Knowledge Base del sistema conversacional: 26 registros en la tabla kb\_contents (13 en inglés, 13 en español), organizados en 13 sub-intents que cubren desde políticas comerciales hasta información de producto. Esta información era servida en tiempo real a Claude AI para generar respuestas contextualizadas.

**1.2 Limitaciones Detectadas**

Se identificaron cinco limitaciones críticas que bloqueaban el avance hacia producción:

-   **Imposibilidad de despliegue en Cloud Run:** Google Cloud Run ejecuta contenedores efímeros sin acceso a la red local del desarrollador. Una base de datos en localhost:5432 es invisible para cualquier instancia de Cloud Run, lo que hacía el despliegue real técnicamente inviable.
-   **Ausencia de alta disponibilidad:** Un servidor PostgreSQL local carece de mecanismos de failover, backups automáticos o replicación. Un reinicio del equipo de desarrollo interrumpía el servicio completo.
-   **Bloqueo para multi-instancia:** Cloud Run escala horizontalmente creando múltiples instancias del contenedor. Con una DB local, todas las instancias apuntarían a la misma máquina física, creando un cuello de botella y un punto único de fallo.
-   **Falta de aislamiento de ambientes:** No existía separación formal entre el entorno de desarrollo (local) y el entorno de producción. Los datos de prueba convivían con datos reales, dificultando la trazabilidad y el control de calidad.
-   **Impedimento para la automatización:** Pipelines de CI/CD y smoke tests automatizados no podían conectarse a una base de datos local, lo que limitaba la capacidad de validar el sistema de forma continua e independiente del desarrollador.

**1.3 Necesidad Estratégica de Migración**

La migración a una base de datos cloud-native no era opcional ni meramente conveniente: era el prerequisito técnico que desbloqueaba el resto del roadmap. Sin ella, las fases M4 (Incremental Sync vía Webhooks), M5 (Alembic Migrations), L1 (HTML→Markdown), L2 (Content Versioning) y la futura L4 (ML Content Optimization) no podían ejecutarse en un entorno productivo real.

| **Principio arquitectónico aplicado**   La base de datos como infraestructura gestionada (DBaaS) es condición necesaria para cualquier arquitectura cloud-native. Mantener una DB local en un sistema distribuido introduce una dependencia física que ningún patrón de arquitectura puede compensar. La migración fue tratada como deuda técnica de alta prioridad, no como una mejora opcional. |
| --- |

**2\. Decisión Arquitectónica**

**2.1 Por Qué Se Eligió Neon**

Neon Pro es una plataforma de PostgreSQL serverless construida sobre el modelo de separación compute/storage. A diferencia de un servidor PostgreSQL tradicional, Neon no mantiene procesos persistentes: escala el cómputo a cero cuando no hay actividad y lo activa en milisegundos al recibir una conexión. Esto lo hace idóneo para sistemas como el nuestro, que alternan entre períodos de alta actividad (requests de usuarios) y períodos de baja actividad (sincronizaciones programadas).

La elección de Neon se fundamentó en cuatro características diferenciadoras respecto a alternativas como Cloud SQL:

-   **Compatibilidad total con asyncpg:** El sistema ya usaba asyncpg como driver de conexión asíncrona. Neon expone un endpoint PostgreSQL estándar compatible con cualquier cliente PostgreSQL, incluyendo asyncpg con sslmode=require. No se requirió ningún cambio en el código de acceso a datos.
-   **Branching de base de datos:** Neon permite crear branches del estado de la DB en milisegundos, similar a git branches. Esto habilita workflows de desarrollo donde cada feature branch tiene su propia DB aislada sin coste adicional de almacenamiento.
-   **Modelo de costos predecible:** El tier Pro cobra por cómputo activo, no por instancia persistente. Para un sistema con tráfico moderado, esto resulta en costos significativamente inferiores a una instancia Cloud SQL que factura por uptime continuo.
-   **Alineación con el roadmap de microservicios:** En la evolución hacia microservicios (planificada para el Q3 2026), cada servicio tendrá su propia base de datos. El modelo serverless de Neon permite crear múltiples databases dentro del mismo proyecto sin el overhead operativo de gestionar múltiples instancias.

**2.2 Comparación Estratégica: Neon vs Cloud SQL**

| **Criterio** | **Neon Pro** | **Cloud SQL (PostgreSQL)** |
| --- | --- | --- |
| Modelo de facturación | Por cómputo activo (pay-per-use) | Por instancia activa (uptime continuo) |
| Costo estimado (carga baja) | ~$19–50/mes | ~$70–150/mes (db-f1-micro) |
| Cold start | 50–500ms primera conexión | Sin cold start (instancia siempre activa) |
| Latencia con Cloud Run (mismo proyecto) | ~10–30ms (TCP directo) | ~1–5ms (Cloud SQL Auth Proxy) |
| Escalado de cómputo | Automático (scale to zero) | Manual o autoscaling limitado |
| Branching / entornos de desarrollo | Nativo (git-like branches) | No disponible sin instancias adicionales |
| Managed backups | Automáticos (Point-in-Time Recovery) | Automáticos configurables |
| Alta disponibilidad | Replicación transparente | HA configuración explícita (+costo) |
| Conexiones máximas | Configurable + pgBouncer nativo | Configurable + Cloud SQL Proxy |
| Compatibilidad asyncpg | Total (PostgreSQL estándar) | Total (PostgreSQL estándar) |
| Curva de operación | Baja (serverless managed) | Media (requiere gestión de instancia) |
| Alineación microservicios | Alta (multi-DB sin overhead) | Media (instancia compartida o N instancias) |

**2.3 Criterios de Decisión Considerados**

La selección final ponderó seis criterios evaluados en el contexto específico del proyecto:

| **Criterio** | **Evaluación y Justificación** |
| --- | --- |

| **Criterio** | **Peso** | **Evaluación** |
| --- | --- | --- |
| Costo operativo | Alto | Neon superior: 60-70% menos costo estimado en etapa actual del proyecto |
| Compatibilidad técnica | Alto | Ambas opciones totalmente compatibles. Sin cambios de código requeridos |
| Complejidad operativa | Alto | Neon inferior: sin gestión de instancias, patches, ni configuración de red VPC |
| Velocidad de adopción | Medio | Neon superior: disponible en minutos vs Cloud SQL que requiere VPC y proxy setup |
| Alineación con microservicios | Medio | Neon superior: branching nativo facilita la evolución hacia DB-per-service |
| Etapa del proyecto | Alto | Neon óptimo para etapa actual: productivo sin complejidad enterprise prematura |

| **Decisión final**   Neon Pro fue seleccionado como la plataforma de base de datos de producción del sistema. La decisión fue unánime considerando que el mayor beneficio de Cloud SQL (latencia sub-5ms con Cloud SQL Auth Proxy) no justifica en esta etapa el incremento de costo y complejidad operativa. Esta decisión puede revisarse cuando el volumen de tráfico justifique la inversión en infraestructura dedicada, tipicamente al superar las 10.000 requests/hora sostenidas. |
| --- |

**3\. Arquitectura Resultante**

**3.1 Visión General del Sistema**

La arquitectura resultante sigue el modelo cloud-native estándar: aplicación stateless en Cloud Run conectada a servicios gestionados externos. La base de datos nunca reside en el mismo proceso que la aplicación ni en la misma máquina. Cada capa tiene responsabilidades claramente delimitadas.

**3.2 Diagrama Conceptual (Descripción Textual)**

El flujo completo desde el cliente hasta la base de datos sigue esta topología:

| **Capa** | **Componente** | **Tecnología** | **Rol** |
| --- | --- | --- | --- |
| Cliente | App / Widget Frontend | HTTP/HTTPS | Origina requests de recomendaciones y conversación |
| Gateway | Cloud Run (FastAPI) | Python 3.11 · asyncpg | Orquesta la lógica de negocio, autenticación y routing |
| Cache | Redis Enterprise | redis-py async | Cache de productos, sesiones, distributed locks |
| Base de datos | Neon Pro | PostgreSQL 16 serverless | Persiste el Knowledge Base (kb_contents, versiones) |
| Recomendaciones | TF-IDF + GCP Retail API | scikit-learn · google-cloud-retail | Genera y rankea recomendaciones de productos |
| Contenido | Shopify API | shopify-python-api | Fuente autoritativa de páginas KB y catálogo |

**3.3 Flujo de Conexión: Aplicación → Neon**

La conexión entre Cloud Run y Neon utiliza el protocolo PostgreSQL estándar sobre TLS 1.3. No existe un proxy intermedio ni un agente de autenticación: la conexión es directa TCP sobre internet, protegida por sslmode=require y las credenciales en la connection string.

El ciclo de vida de una conexión en el sistema sigue estos pasos:

1.  **Startup del contenedor:** Al iniciar, FastAPI crea un pool asyncpg con min\_size=5. Neon activa el cómputo si estaba en modo sleep (cold start de 50-500ms, ocurre solo en la primera conexión tras inactividad).
2.  **Request entrante:** El handler async del router adquiere una conexión del pool (operación O(1), sin latencia de nueva conexión TCP). El pool mantiene las conexiones TCP abiertas entre requests.
3.  **Query execution:** asyncpg envía la query en formato PostgreSQL wire protocol. Neon ejecuta en su compute layer y retorna resultados. La latencia round-trip desde Cloud Run (us-central1) a Neon (us-east-1) es aproximadamente 15-30ms.
4.  **Liberación:** El handler libera la conexión de vuelta al pool. No hay cierre TCP: la conexión persiste para el siguiente request.
5.  **Idle keepalive:** asyncpg envía keepalive pings periódicos para mantener las conexiones activas. Neon mantiene el cómputo activo mientras existan conexiones abiertas.

**3.4 Cambios Respecto al Entorno Anterior**

| **Aspecto** | **Antes (PostgreSQL Local)** | **Ahora (Neon Pro)** |
| --- | --- | --- |
| Ubicación | localhost:5432 (máquina del dev) | ep-*.us-east-2.aws.neon.tech:5432 |
| Disponibilidad | Depende del equipo del dev | 99.95% SLA managed |
| Acceso desde Cloud Run | Imposible (red privada) | Total (internet público + TLS) |
| SSL/TLS | No requerido (local) | Obligatorio (sslmode=require) |
| Backups | Manuales o inexistentes | Automáticos (Point-in-Time Recovery) |
| Escalado | Limitado por hardware local | Serverless (scale to zero / scale up) |
| Migrations (Alembic) | Aplicadas manualmente en local | Aplicadas via alembic upgrade head contra URL remota |
| Cost | Implícito (electricidad + hardware) | Explícito (~$19-50/mes Pro tier) |
| Aislamiento de ambientes | No existe | Branch TEST + Branch PROD separados |

**4\. Flujo de Datos**

**4.1 Flujo Principal: Request → Respuesta**

El flujo de datos completo de una solicitud de recomendación o respuesta conversacional sigue el siguiente camino a través del sistema. Neon interviene específicamente en los pasos que requieren acceso al Knowledge Base.

| **Paso** | **Componente** | **Descripción** | **Usa Neon** |
| --- | --- | --- | --- |
| 1 | Cliente → Cloud Run | HTTP GET /v1/recommendations/{id} con X-API-Key | No |
| 2 | FastAPI Router | Autenticación de API Key, extracción de parámetros | No |
| 3 | ProductCache | Búsqueda en Redis (hit ~87%). Si miss, consulta catálogo local o Shopify | No |
| 4 | TF-IDF Recommender | Cálculo de similitud coseno sobre 3.062 productos en memoria | No |
| 5 | GCP Retail API | Solicitud de predicciones colaborativas para el usuario | No |
| 6 | HybridRecommender | Combinación ponderada de TF-IDF + GCP Retail API results | No |
| 7 | KB Lookup (si intent) | SELECT content FROM kb_contents WHERE sub_intent = $1 AND language = $2 | Sí |
| 8 | Redis Cache | Almacenamiento del resultado KB para evitar re-queries a Neon en el ciclo | No |
| 9 | Claude AI | Generación de respuesta conversacional usando KB content como contexto | No |
| 10 | Cloud Run → Cliente | JSON response con recomendaciones + respuesta conversacional | No |

**4.2 Flujo de Sincronización: Shopify → Neon**

El segundo flujo crítico es la sincronización del contenido del Knowledge Base desde Shopify hacia Neon. Este flujo opera de forma asíncrona en background, independiente del flujo de requests de usuarios.

-   **Trigger:** El background job KBBackgroundSyncJob se ejecuta cada KB\_SYNC\_INTERVAL\_MINUTES minutos, o inmediatamente al recibir un webhook de Shopify (M4).
-   **Fetch:** ShopifyKBClient obtiene las páginas KB de Shopify (etiquetadas con kb, sub\_intent) vía REST API. Los metafields se obtienen en paralelo (M1: 91% mejora de velocidad).
-   **Hash comparison (L2):** Para cada página, se calcula el SHA256 del contenido Markdown. Si el hash coincide con el almacenado en kb\_contents.content\_hash, la página se omite (0 writes a DB).
-   **Upsert atómico:** Si hay cambio, se ejecuta INSERT ... ON CONFLICT DO UPDATE con distributed lock Redis (M3). El registro anterior se archiva en kb\_content\_versions antes del update.
-   **Cache invalidation:** Solo si hubo cambio real, se invalida la clave Redis correspondiente. El siguiente request obtendrá el contenido actualizado de Neon.

**4.3 Impacto en Latencia**

La migración a Neon introduce latencia de red que no existía con PostgreSQL local. Sin embargo, este impacto está mitigado por la arquitectura de caché del sistema:

| **Operación** | **Antes (local)** | **Ahora (Neon)** | **Mitigación** |
| --- | --- | --- | --- |
| Query KB simple | &lt;1ms | 15-30ms (warm) | Resultado cacheado en Redis (TTL configurable) |
| Query KB cold start | &lt;1ms | 300-500ms (cold) | Warm-up al inicio. Pool mantiene conexiones activas |
| Health check DB | &lt;1ms | 280ms promedio | Aceptable. Solo ejecutado en /api/health/kb |
| Sync KB completo | 449ms | ~980ms (13 páginas) | Background job. No afecta tiempo de respuesta al usuario |
| Alembic migration | Instantáneo | 2-5 segundos | Operación de mantenimiento. Sin impacto en runtime |

| **Observación sobre latencia en producción (Cloud Run)**   Los valores de latencia observados en smoke tests (ejecutados desde Windows local hacia Neon) son significativamente superiores a los esperados en producción. Cloud Run us-central1 y Neon us-east-2 tienen peering mejorado versus una conexión residencial con variabilidad de ~130-300ms. La latencia en producción se estima en 15-30ms para queries warm. |
| --- |

**5\. Componentes y Dependencias Principales**

**5.1 Librerías de Base de Datos**

| **Librería** | **Versión mínima** | **Rol** |
| --- | --- | --- |
| asyncpg | &gt;=0.29.0 | Driver PostgreSQL asíncrono nativo. Conexión directa a Neon sin ORM |
| alembic | &gt;=1.13.0 | Framework de migraciones de schema (M5). Modo script-only sin autogenerate |
| sqlalchemy | &gt;=2.0.35 | Solo como abstracción de conexión para Alembic. No usado en runtime |
| python-dotenv | &gt;=1.0.0 | Carga variables de entorno desde .env en desarrollo local |

**5.2 Variables de Entorno**

El sistema requiere las siguientes variables de entorno para la conexión con Neon:

| **Variable** | **Descripción** | **Ejemplo / Formato** |
| --- | --- | --- |
| DATABASE_URL | Connection string completa a Neon. Reemplaza todas las variables individuales de DB | postgresql://user:pass@ep-*.aws.neon.tech/db?sslmode=require |
| KB_DISTRIBUTED_LOCKS | Activa Redis distributed locks para multi-instancia Cloud Run | true (producción) / false (desarrollo) |
| KB_SYNC_INTERVAL_MINUTES | Intervalo del background sync KB con Shopify | 60 (producción recomendado) |
| KB_CONTENT_VERSIONING | Activa el historial de versiones L2 en kb_content_versions | true |
| KB_MAX_VERSIONS_PER_CONTENT | Máximo versiones históricas por registro KB | 10 (aumentar a 50+ para L4) |
| DB_POOL_MIN_SIZE | Mínimo de conexiones en el pool asyncpg | 5 |
| DB_POOL_MAX_SIZE | Máximo de conexiones en el pool asyncpg | 20 |

**5.3 Estructura del Schema de Base de Datos**

El estado actual del schema en Neon (versión Alembic 0002) incluye las siguientes tablas:

| **Tabla** | **Filas actuales** | **Descripción** |
| --- | --- | --- |
| kb_contents | 26 | Contenido activo del Knowledge Base. 13 sub-intents × 2 idiomas (EN, ES). 20 columnas. Índices: idx_kb_lookup, idx_kb_language, idx_kb_shopify_id, idx_kb_category, idx_kb_unique_content |
| kb_content_versions | Variable | Historial de cambios de contenido (L2). Permite trazabilidad editorial y será el dataset de entrenamiento para L4 ML Content Optimization |
| kb_contents_backup | 26 | Snapshot de backup creado durante la migración. Permite rollback de datos sin revertir schema |
| schema_migrations | 2 | Audit log de migraciones aplicadas (H2). Complementa alembic_version con metadata de negocio |
| alembic_version | 1 | Estado actual del schema gestionado por Alembic. Versión head: 0002 |

**5.4 Cambios en Infraestructura**

-   **Eliminado:** Variable de entorno localhost:5432 en .env de desarrollo y producción
-   **Añadido:** DATABASE\_URL con endpoint Neon Pro y sslmode=require
-   **Añadido:** alembic.ini y directorio alembic/versions/ para gestión de schema
-   **Añadido:** requirements.txt: alembic>=1.13.0, sqlalchemy>=2.0.35
-   **Modificado:** src/api/core/config.py: DATABASE\_URL como variable principal en lugar de DB\_HOST/PORT/NAME/USER/PASSWORD individuales
-   **Branch TEST:** Creado en Neon para validaciones pre-deploy. Permite aplicar migraciones en TEST antes de PROD

**6\. Impacto en el Sistema**

**6.1 Escalabilidad**

La migración elimina el principal cuello de botella de escalabilidad del sistema. Con PostgreSQL local, el número de instancias Cloud Run estaba artificialmente limitado a 0 (la DB no era accesible). Con Neon, no existe límite arquitectónico: cada instancia de Cloud Run puede conectarse independientemente al mismo cluster Neon.

El mecanismo de Distributed Locking (M3) garantiza que múltiples instancias paralelas no generen race conditions durante la sincronización del Knowledge Base. El pool asyncpg (min=5, max=20 conexiones por instancia) con hasta 10 instancias Cloud Run implica un máximo teórico de 200 conexiones simultáneas a Neon, bien dentro de los límites del tier Pro.

**6.2 Observabilidad**

La migración no degrada y en algunos aspectos mejora la observabilidad del sistema:

-   **Health checks:** El endpoint /api/health/kb verifica activamente la conectividad con Neon en cada llamada, reportando pool\_free, pool\_size y pool\_usage\_pct. Esto permite detectar contención de conexiones en tiempo real.
-   **Structured logging (H1):** Todos los eventos de DB emiten logs estructurados con campos estandarizados (component, duration\_ms, status). Los logs de postgres\_health\_check\_passed confirman el estado en cada health check.
-   **Prometheus metrics (M2):** Las métricas de DB queries están integradas en el sistema de métricas Prometheus. El endpoint /v1/metrics expone histogramas de latencia de queries y conteo de errores.
-   **Schema versioning (H2):** La tabla schema\_migrations actúa como audit log inmutable de todas las migraciones aplicadas, con timestamp, ejecutor y checksum. Facilita auditorías post-facto.

**6.3 Costos**

Neon Pro utiliza un modelo de facturación por cómputo activo (compute hours) y almacenamiento (GB-month). Para el volumen actual del proyecto:

| **Recurso** | **Estimación** | **Notas** |
| --- | --- | --- |
| Almacenamiento KB | &lt;1 MB | kb_contents: 26 registros de texto. Negligible en costo de storage |
| Compute hours (carga actual) | ~2-4h/día activo | Background sync cada hora + requests de usuarios. ~60-120h/mes activo |
| Costo estimado mensual | $19-40 USD | Tier Pro. Varía según tráfico y compute hours activas |
| Ahorro vs Cloud SQL (db-f1-micro) | ~50-65% | Cloud SQL factura 720h/mes (24/7) independiente del uso real |

**6.4 Mantenibilidad**

La principal mejora en mantenibilidad es la separación de responsabilidades entre la aplicación y la base de datos. Los cambios de schema ahora siguen un workflow formal y trazable:

1.  **Desarrollo:** alembic revision -m "descripcion" genera el archivo de migración en alembic/versions/
2.  **Review:** El SQL explícito en upgrade()/downgrade() es legible y revisable en pull requests
3.  **Staging:** alembic upgrade head contra el branch TEST de Neon valida la migración en aislamiento
4.  **Producción:** alembic upgrade head contra el branch PROD aplica el cambio. El downgrade está siempre disponible
5.  **Auditoría:** schema\_migrations registra timestamp, ejecutor y checksum de cada migración aplicada

**6.5 Preparación para L4 (ML Content Optimization)**

La Fase L4 requiere un dataset histórico de cambios en el contenido del Knowledge Base para entrenar modelos de optimización de contenido. La migración a Neon, combinada con L2 (Content Versioning), crea exactamente ese dataset:

-   kb\_content\_versions almacena cada versión archivada de cada registro KB con timestamp y content\_hash
-   El pipeline ML puede consultar versiones históricas y correlacionar cambios con métricas de resolución de intents
-   Neon soporta queries analíticas sobre el historial sin impactar el rendimiento de las queries transaccionales (compute layer independiente)
-   KB\_MAX\_VERSIONS\_PER\_CONTENT debe aumentarse a 50+ antes de activar L4 para garantizar suficiente historial de entrenamiento

| **Relación causal con L4**   Sin Neon (y sin L2), la fase L4 era imposible: no existía historial persistente y accessible de cambios de contenido. Neon provee la capa de persistencia que hace este dataset real y consultable. L2 provee la lógica de captura. L4 provee el modelo que aprende de ese historial. |
| --- |

**7\. Riesgos y Limitaciones Conocidas**

**7.1 Trade-offs Asumidos**

| **Trade-off** | **Descripción** | **Severidad** | **Estado** |
| --- | --- | --- | --- |
| Cold start en primera conexión | Neon suspende el cómputo tras inactividad (~5 min). La primera conexión tras el período idle puede tardar 50-500ms adicionales. | Baja | Mitigado: pool asyncpg y keepalive mantienen conexiones activas durante uso normal |
| Latencia mayor que Cloud SQL con Auth Proxy | Cloud SQL con proxy VPC ofrece ~1-5ms vs ~15-30ms de Neon en Cloud Run. Diferencia de ~20-25ms por query. | Baja | Aceptado: el impacto real es &lt;60ms/ciclo de sync con 26 registros. El bottleneck es Shopify API (~88% del tiempo de sync) |
| Dependencia de conectividad a internet | Neon usa TCP sobre internet público. Un degradamiento de red entre Cloud Run y Neon impacta todas las queries. | Media | Mitigado: caché Redis actúa como fallback para contenido KB. El sistema puede operar con datos cacheados si Neon es temporalmente inaccesible |
| Vendor lock-in parcial | El branching y algunos features de Neon son propietarios. Migrar a otro PostgreSQL requiere abandonarlos. | Baja | Aceptado: el core (asyncpg + SQL estándar) es 100% portable. Solo el branching es Neon-specific, y no es crítico para el runtime |
| Límite de conexiones concurrentes | El tier Pro de Neon tiene límites de conexiones simultáneas. 10 instancias × 20 conexiones = 200 conexiones máximas. | Media | Monitorear pool_usage_pct. Si se acerca a 80%, implementar PgBouncer o reducir pool_max_size por instancia |

**7.2 Posibles Puntos Críticos**

Se identificaron tres áreas que requieren monitoreo activo en producción:

| **Punto crítico 1: Pool de conexiones bajo carga simultánea**   Durante el smoke test v2.3, se observó pool\_free=0, pool\_size=3, pool\_usage\_pct=100.0 durante el health check /api/health/kb. Esto ocurre porque el health check ejecuta 4 queries concurrentes contra un pool de 3 conexiones. En producción real con tráfico alto, este comportamiento podría manifestarse en timeouts de adquisición de conexión del pool. Recomendación: monitorear este metric y escalar DB\_POOL\_MIN\_SIZE si se observan warnings. |
| --- |

| **Punto crítico 2: Latencia variable del cold start**   El smoke test v2.3 registró un ping inicial a Neon de 903ms (primer request tras un período de inactividad). Esta latencia es inherente al modelo serverless y no representa un fallo. Sin embargo, si Cloud Run también tiene cold start simultáneo (min-instances=0), el usuario experimenta cold start doble: Cloud Run (~2-3s) + Neon (~300-500ms). Recomendación: mantener min-instances=1 en Cloud Run para eliminar el cold start de la capa de aplicación. |
| --- |

| **Punto crítico 3: Schema migration en producción sin downtime**   Las migraciones Alembic son operaciones síncronas que bloquean la tabla durante ALTER TABLE. Para el schema actual (26 filas en kb\_contents), el bloqueo es de microsegundos. Sin embargo, a medida que el historial en kb\_content\_versions crezca (especialmente con L4 ML), las migraciones futuras sobre esa tabla requerirán estrategias zero-downtime como ADD COLUMN DEFAULT o operaciones en background. Neon Pro soporta estas operaciones de forma nativa. |
| --- |

**8\. Recomendaciones y Observaciones**

**8.1 Buenas Prácticas para Operar Neon**

-   **Nunca usar la connection string de producción en desarrollo:** Neon provee branches de DB que son copias instantáneas (copy-on-write). Usar siempre un branch dedicado para desarrollo local y otro para staging. El branch de producción solo debe ser accedido por Cloud Run.
-   **Rotar credenciales periódicamente:** La connection string de Neon incluye usuario y contraseña en texto plano (URL-encoded). Almacenarla en Cloud Run como Secret Manager secret, no como variable de entorno plana. Rotar cada 90 días.
-   **Monitorear el pool\_usage\_pct:** El endpoint /api/health/kb retorna este valor. Configurar una alerta si supera 80% de forma sostenida durante más de 5 minutos. Indica que el pool está subconfigurado para el tráfico actual.
-   **Usar alembic upgrade head --sql para dry-run:** Antes de aplicar cualquier migración en producción, ejecutar el flag --sql para obtener el SQL que se ejecutará. Revisar manualmente antes de aplicar, especialmente para migraciones con ALTER TABLE sobre tablas grandes.
-   **Mantener el branch TEST sincronizado con PROD:** Antes de cada migración, crear un nuevo branch TEST desde el branch PROD actual. Esto garantiza que la migración se prueba contra datos reales de producción, no contra una copia desactualizada.

**8.2 Consideraciones para Producción Futura**

-   **Implementar PgBouncer cuando las conexiones superen 150:** Neon ofrece PgBouncer como feature nativo. Activarlo permitirá multiplexar miles de conexiones lógicas sobre un número reducido de conexiones físicas, eliminando el límite del pool como cuello de botella.
-   **Configurar alertas de costo en el dashboard de Neon:** El modelo pay-per-use puede generar facturas inesperadas si un bug provoca queries en bucle o sync jobs descontrolados. Configurar un límite de spend mensual con alerta de email.
-   **Documentar el schema en alembic/versions/:** Cada archivo de migración debe incluir una descripción detallada en el docstring del módulo Python. Esto sirve como changelog automático del schema y facilita auditorías.
-   **Evaluar conexión privada cuando el tráfico justifique:** Si la latencia de 15-30ms resulta insuficiente en producción (tráfico alto con queries frecuentes a Neon), evaluar el acceso privado mediante peering directo entre la VPC de Cloud Run y Neon. Disponible en planes enterprise de Neon.

**8.3 Configuración de Producción Recomendada**

| **Parámetro** | **Valor recomendado** | **Justificación** |
| --- | --- | --- |
| DB_POOL_MIN_SIZE | 5 | Mantiene 5 conexiones warm en todo momento. Evita cold start de pool |
| DB_POOL_MAX_SIZE | 10 por instancia | Con max 10 instancias Cloud Run → 100 conexiones totales. Margen de seguridad |
| KB_DISTRIBUTED_LOCKS | true | Obligatorio en multi-instancia Cloud Run para prevenir race conditions en sync |
| KB_SYNC_INTERVAL_MINUTES | 60 | Balance entre frescura de datos y requests a Shopify API (rate limiting) |
| KB_CONTENT_VERSIONING | true | Activa historial L2. Dataset necesario para L4 ML Optimization |
| KB_MAX_VERSIONS_PER_CONTENT | 50 | Aumentar de 10 a 50 antes de L4 para garantizar historial suficiente |
| Cloud Run min-instances | 1 | Elimina cold start de la capa de aplicación. Costo marginal vs UX mejorado |
| sslmode en DATABASE_URL | require | Obligatorio. Sin TLS los datos de KB viajan en texto plano por internet |

**9\. Posibles Mejoras Futuras**

**9.1 Optimización de Conexiones (Corto Plazo)**

La configuración actual del pool asyncpg es funcional pero no está optimizada para producción bajo carga. Las mejoras a corto plazo incluyen:

-   **Connection pooling externo (PgBouncer):** Activar PgBouncer de Neon en modo transaction pooling. Permite que 100+ conexiones lógicas compartan un pool de 10-20 conexiones físicas. Especialmente importante al escalar Cloud Run a múltiples instancias.
-   **Health check proactivo del pool:** Implementar un background task que verifique la salud del pool asyncpg cada 30 segundos y reconecte conexiones stale. Previene errores silenciosos en períodos de baja actividad.
-   **Query timeout configurable:** Agregar statement\_timeout en la configuración asyncpg para prevenir que queries lentas bloqueen conexiones indefinidamente. Valor recomendado: 5000ms para queries transaccionales, 30000ms para migraciones.

**9.2 Estrategia Multi-Región**

A medida que el sistema expanda su cobertura geográfica (los mercados ES, MX y CL son candidatos naturales), la latencia de una DB en us-east-2 puede resultar subóptima para usuarios europeos y latinoamericanos. Neon soporta dos estrategias de multi-región:

-   **Read replicas en Neon:** Crear read replicas en eu-west-1 (para ES) y us-west-2 (para MX/CL). Las queries de lectura del KB se enrutarían a la réplica más cercana. Las writes siguen al primary. Requiere lógica de routing por market\_id en el código.
-   **Multi-primary con conflicto resolution:** Para escenarios donde cada mercado tiene su propio KB, un primary por región elimina la dependencia transatlántica. Requiere diseño de schema con market\_id en todas las tablas y estrategia de resolución de conflictos.

La Fase L3 (Multi-Region Support, actualmente pendiente) abordará esta evolución. M3 (Distributed Locking) ya provee los cimientos necesarios para multi-región seguro.

**9.3 Evolución hacia Microservicios**

El roadmap técnico contempla la extracción de servicios independientes en H2 2026. En ese contexto, la arquitectura de DB debe evolucionar también:

-   **DB-per-service pattern:** Cada microservicio (Knowledge Base Service, Recommendation Service, User Service) tendrá su propia database en Neon. El branching de Neon facilita crear estas databases sin coste adicional de infraestructura en etapa temprana.
-   **Event sourcing para sincronización:** En lugar de queries directas cross-service, los servicios publicarán eventos (e.g., KBContentUpdated) que otros servicios consumirán. Reduce el acoplamiento temporal y habilita eventual consistency.
-   **CQRS (Command Query Responsibility Segregation):** Las operaciones de lectura (recomendaciones, KB queries) se separarán de las operaciones de escritura (sync, versioning). Las lecturas pueden servirse desde réplicas optimizadas; las escrituras van al primary.

**9.4 Mejoras de Observabilidad Pendientes**

-   **Dashboard Neon en Grafana:** Neon expone métricas de query performance via pg\_stat\_statements. Integrarlas en el dashboard Grafana existente permitirá identificar queries lentas y oportunidades de indexación.
-   **Alertas de schema drift:** Un check periódico que compare alembic current contra alembic head y emita alerta si hay migraciones pendientes no aplicadas. Previene desincronización silenciosa entre código y schema.
-   **Query explain log automático:** Loguear automáticamente el EXPLAIN ANALYZE de queries que superen 100ms. Permite detectar degradación de performance antes de que impacte a usuarios.

**10\. Evidencia de Validación**

**10.1 Artefacto de Validación: Smoke Test v2.3**

La migración fue declarada completada tras la ejecución exitosa del Smoke Test v2.3, un script PowerShell de 82 checks que valida la conectividad, integridad de datos, funcionalidad de endpoints y rendimiento del sistema completo.

| **Métrica** | **Resultado** |
| --- | --- |
| Total de checks ejecutados | 82 |
| PASS | 79 (96.3%) |
| WARN | 3 (no críticos) |
| FAIL | 0 |
| Resultado general | SISTEMA PRODUCTION READY |
| Duración total del test | 3 minutos 33 segundos (22:15:30 — 22:19:03) |
| Fecha de ejecución | 04 de Marzo de 2026 |

**10.2 Checks Críticos de Neon Validados**

| **Check** | **Resultado** | **Evidencia** |
| --- | --- | --- |
| Conexión a Neon (SELECT 1) | PASS | Bloque 1: respuesta correcta de DB remota |
| Alembic version 0002 (head) | PASS | Bloque 1: schema actualizado correctamente |
| 2 migraciones registradas | PASS | Bloque 1: schema_migrations poblado |
| 20 columnas en kb_contents | PASS | Bloque 1: schema completo y correcto |
| 5 índices presentes | PASS | Bloque 1: idx_kb_lookup, idx_kb_language, idx_kb_shopify_id, idx_kb_category, idx_kb_unique_content |
| 26 registros KB (13 EN + 13 ES) | PASS | Bloque 2: datos íntegros en Neon |
| 0 NULLs en columnas críticas | PASS | Bloque 2: sub_intent, language, content, shopify_page_id |
| schema_version poblado | PASS | Bloque 2: todos los registros con versión asignada |
| DATABASE_URL apunta a Neon | PASS | Bloque 10: sin localhost en connection string |
| sslmode=require presente | PASS | Bloque 10: conexión cifrada confirmada |
| KB health check &lt;500ms | PASS | Logs: components_healthy=4, duration_ms=288ms |
| KB sync incremental activo | PASS | Logs: kb_sync_cycle_no_changes, ciclo completado en &lt;1s |

**10.3 Warnings Documentados (No Críticos)**

| **Warning** | **Descripción** | **Impacto** | **Acción Requerida** |
| --- | --- | --- | --- |
| Latencia Neon cold start (psql.exe) | ~1400ms en queries vía psql.exe externo | Ninguno en runtime real. psql.exe abre nueva conexión TCP pagando cold start. asyncpg usa pool persistente. | Ninguna. Comportamiento esperado y documentado |
| CatalogManager no disponible | Componente no instanciado en esta configuración | Solo afecta branch management de diversificación de recomendaciones. Flujo principal de recomendaciones funciona al 100%. | Ninguna. Documentado como no crítico en DCT previos |

**Historial de Cambios**

| **Versión** | **Fecha** | **Autor** | **Descripción** |
| --- | --- | --- | --- |
| 1.0 | 04 Mar 2026 | Yasmani | Versión inicial. Documento de cierre oficial de la migración a Neon Pro. |

*— FIN DEL DOCUMENTO —*

Retail Recommender System v2.1.0 · Neon Pro Migration Closure · 2026