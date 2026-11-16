# DCT -- Alineacion del venv local con produccion y diagnostico de la suite (13/11/2026 - 16/11/2026)

Documento de continuidad tecnica del pendiente 4 del incidente de credenciales
(`DCT_Incidente_Credenciales_Expuestas_31102026.md`, seccion 8): alinear el venv local con
`requirements.cloudrun.txt` y explicar cada cambio de estado de la suite. El diagnostico destapo
varios hallazgos (seccion 7) y obligo a cerrar una comprobacion de seguridad nueva (seccion 6).

Convencion: [V] verificado con evidencia; [H] hipotesis; [Y] confirmado por Yasmani sin salida
adjunta. Ningun valor secreto aparece en este documento. Las evidencias en bruto estan en
`C:\Users\yasma\Desktop\diag_14112026\` (fuera del repo).

---

## 1. Resumen

- El venv local queda instalado desde el mismo fichero que produccion (`requirements.cloudrun.txt`) [V].
- Suite: 1220 tests, **171 -> 168 fallos**, 0 regresiones reales. 4 tests arreglados por `httpx2`;
  1 "fallo nuevo" que es ruido de medicion (R-5); 1 fallo enmascarado que cambia de causa y destapa
  un problema de los tests, no de produccion (R-1) [V].
- Produccion se degrada bien si Redis falla al arrancar [V]; la cascada observada solo ocurre dentro
  de pytest, por una configuracion de `structlog` propia de los tests (R-1), reproducida en aislamiento [V].
- Riesgo real antes de abrir la tienda: la base de conocimiento v2 tiene como ultima capa un respaldo
  con **contenido ficticio de plantilla** (R-2), alcanzable en produccion [V]; no servido en 30 dias,
  pero con solo 2 consultas a la base de conocimiento en ese periodo [V].
- `.env.test` estuvo en el historial publico (4 commits de 2025): sin credenciales con valor, y ningun
  valor actual de `.env` ni de `.env.test` aparece publicado salvo una clave de prueba muerta [V].
- **Mitigaciones en produccion (16/11/2026)** [V], solo configuracion y misma imagen: R-2
  (`KB_ENABLE_FALLBACK=false`, revision `00341-mr8`) y R-8 (`LFM_MCP_ENABLED` y `LFM_KB_ENABLED=false`,
  revision `00342-c6x`). Detalle en la seccion 10.

## 2. Alineacion del venv

1. Copia previa: `C:\Users\yasma\Desktop\venv_backup_13112026\freeze_antes.txt` (143 paquetes) [V].
2. Simulacion (`--dry-run`) con tabla de versiones: 38 paquetes previstos; 3 bajan
   (`google-cloud-retail` 1.25.1 -> 1.24.0, `grpcio-status` 1.75.1 -> 1.71.2, `protobuf` 6.32.1 -> 5.29.6),
   el resto suben o son nuevos (`httpx2`, `httpcore2`, `websockets`, `watchfiles`...) [V].
   El "38 frente a 39" de la instalacion real lo explica una linea (`markdownify`) perdida al pegar [V].
3. `pip install -r requirements.cloudrun.txt` -> codigo 0, 39 paquetes [V]. Versiones comprobadas desde
   Python: `anthropic` 1.7.0, `openai` 3.16.2, `redis` 8.1.0, `torch` 2.14.0+cpu, `transformers` 5.17.0,
   `protobuf` 5.29.6, `httpx2` importable [V]. Copia posterior: `freeze_despues.txt`.
4. `pip check` -> codigo 1, 5 conflictos [V]:
   - `grpcio-tools 1.75.1` pide `protobuf>=6.31.1`: herramienta de desarrollo; lo provoca la bajada de `protobuf`.
   - `locust 2.43.1` pide `requests>=2.32.2` (hay 2.32.0): ya existia.
   - `retail-recommender 0.1.0` pide `google-cloud-retail>=1.25`, `redis<5` y `scikit-learn==1.2.2`: los
     **metadatos del propio paquete estan desfasados**, una tercera fuente de verdad que ya no coincide
     con `requirements.cloudrun.txt` ni con el venv.

## 3. Suite: antes y despues

Comando (igual antes y despues, venv comprobado, `PYTHONUTF8=1`):
`pytest --ignore=tests/integration/test_hybrid_detector_with_reset.py --continue-on-collection-errors --junitxml=...`

| | tests | failed | passed | errors | skipped |
|---|---|---|---|---|---|
| Antes | 1220 | 171 | 1008 | 37 | 4 |
| Despues | 1220 | 168 | 1011 | 37 | 4 |

Cambios de estado (`compare_junit.py`) y veredicto:

| Test | Cambio | Causa | Veredicto |
|---|---|---|---|
| `test_kb_language_detection::test_conversation_default_language` | failed -> passed | antes `ModuleNotFoundError: httpx2` | Arreglado por la alineacion [V]. Ojo: solo comprueba `len(texto) > 10` |
| `test_user_journey_conversational::test_mcp_conversation_empty_query` | failed -> passed | idem | Arreglado [V] |
| `test_user_journey_conversational::test_mcp_conversation_session_persistence` | failed -> passed | idem | Arreglado [V] |
| `test_mcp_router_di_migration::TestMCPRouterPerformance::test_di_overhead_is_minimal` | failed -> passed | idem (no era el tiempo) | Arreglado [V] |
| `test_environment_setup::TestEnvironmentPerformance::test_redis_performance_baseline` | passed -> failed | relacion 4,0x frente a > 5x exigido | Ruido de medicion (R-5): pasa 6 de 6 veces suelto [V] |
| `test_kb_language_detection::test_conversation_respects_language_header` | failed -> failed (otro mensaje) | antes `httpx2`; ahora responde en espanol "No he encontrado productos" | Fallo enmascarado; causa en los tests (R-1) [V] |

## 4. Diagnostico del test de idioma

Pregunta del test: "What is your return policy?" con `Accept-Language: en-US`.

- **Produccion** responde bien: intencion `informational` (regla, confianza 1.0, salida temprana) y la
  politica en ingles desde la base de conocimiento [V].
- **Local fuera de pytest** (script con `TestClient`, solo `.env`): igual que produccion. Redis tambien
  falla (timeout), pero el arranque termina y la base de conocimiento responde desde PostgreSQL
  (`kb_buffer_hit`, `language=en`) [V].
- **Local dentro de pytest** (el fichero de test solo, `--no-cov`): falla [V]. Cadena causal, toda en el log:
  1. `tests/conftest.py` carga `.env.test` con `override=True`; con esos valores la app no alcanza su Redis.
  2. El manejador de ese error, `logger.error("[BG] %s", redis_error)` (`main_unified_redis.py` L460, 463, 472),
     lanza `TypeError: BoundLoggerBase._proxy_to_logger() takes from 2 to 3 positional arguments`.
  3. La excepcion aborta el arranque (`Enterprise startup encountered error`): la base de conocimiento v2
     no se registra en `app.state`.
  4. El handler cae a su ultimo respaldo, `get_knowledge_base()`, y lo llama con `language=` y `category=`,
     que `SimpleKnowledgeBase.get_answer()` no acepta -> `TypeError` capturado.
  5. Sin respuesta: busqueda de productos -> `HybridRecommender not available` -> 0 productos -> el redactor
     no corre -> sale el texto provisional fijo en espanol de `mcp_conversation_handler.py` L3915.
- **Por que solo en pytest** [V]: `tests/conftest.py` (L65) llama a `structlog.configure(...,
  wrapper_class=structlog.BoundLogger, logger_factory=structlog.PrintLoggerFactory())`. La app llama
  despues a `configure_structlog()`, que **no fija `wrapper_class`**; como `structlog.configure()` deja sin
  cambiar lo que no recibe, la clase de los tests sobrevive. Esa clase generica no acepta argumentos
  posicionales. Reproduccion minima con `structlog` 26.1.0: solo la configuracion de la app ->
  `BoundLoggerFilteringAtNotset`, mensaje formateado; configuracion de tests y luego la de la app ->
  `_generic.BoundLogger`, el mismo `TypeError` [V].
- **Confirmacion en produccion** [V]: `Redis BG init completed. redis_initialized=True` (L1323, con `%s`)
  aparece formateado en los logs del 16/11.

## 5. Deriva de configuracion: tres capas

Solo nombres de variables; los valores se compararon sin mostrarlos.

| Comparacion | Resultado [V] |
|---|---|
| `env-vars.yaml` (37) frente a `.env` (133) | 4 solo en produccion (`DB_SSL`, `ENVIRONMENT`, `RECS_MAX_ALTERNATIVES`, `RECS_VISUAL_FILTER_IN_SEARCH`); 100 solo en local, de ellas 11 son los secretos de `--set-secrets` y 89 flags con valor local frente al valor por defecto del codigo en produccion; 5 con valor distinto (`FORCE_GPT4O_MINI_FALLBACK`, `GCS_BUCKET_NAME`, `KB_WEBHOOKS_ENABLED`, `LFM_COLBERT_ENABLED`, `LOG_JSON_FORMAT`) |
| Flags relevantes | Solo en local y a `true`: `TEST_MODE`, `USE_SAMPLE_DATA`, `DEBUG`; en produccion `true` y en local `false`: `KB_WEBHOOKS_ENABLED`, `LFM_COLBERT_ENABLED`, `LOG_JSON_FORMAT`; el bucket GCS local es el de Cloud Build |
| `.env.test` (81) frente a `.env` | 9 solo en `.env.test` (`DB_*`, `ENABLE_MOCK_EXTERNAL_APIS`, `ENABLE_TEST_MODE`, `ENV`); 31 con valor distinto, incluidos `REDIS_*`, `MCP_*` y las claves |

Consecuencia: un test e2e que pasa o falla en local dice poco de produccion mientras estas capas no se
vigilen; es el motivo de `tools/validation/check_env_drift.py` (pendiente), que debe cubrir las tres.

## 6. Comprobacion de seguridad: `.env.test` (cerrada)

- No rastreado hoy y cubierto por `.gitignore` (L19) [V], pero **4 commits publicados** lo tocaron:
  `1d86b70` (20/04/2025), `9da1dd4` (22/04/2025), `462306b` (28/04/2025) y `bd58ca6` (18/06/2025, lo borra) [V].
- Ninguna de esas versiones tiene credenciales con valor (12 caracteres o mas); control positivo: el mismo
  filtro detecta 3 credenciales en el `.env.test` actual [V].
- Valores actuales de `.env` y `.env.test` en el historial publicado: 0 para todas las credenciales, salvo el
  `API_KEY` de `.env.test` (1 commit: `9c8df16`, `tests/e2e/conftest.py`, donde S-13 lo sustituyo por la
  lectura del entorno). Es una clave de prueba distinta de la de produccion, que solo acepta la version 3 del
  secreto `api-key`: muerta para produccion [V]. Nada que rotar.
- La busqueda del 12/11 solo cubria los valores de Secret Manager; esta la completa con los ficheros locales.

## 7. Hallazgos

| Id | Hallazgo | Gravedad | Estado / propuesta |
|---|---|---|---|
| R-1 | **Logging de los tests distinto del de la app**: `tests/conftest.py` fija `wrapper_class=structlog.BoundLogger` y la app no fija ninguna, asi que hereda la de los tests. 12 llamadas con argumentos posicionales en `main_unified_redis.py` (L423, 460, 463, 467, 472, 1323, 1359, 1367, 1374, 1539, 1612, 1647) lanzan `TypeError` solo en pytest. 0 casos en produccion en 30 dias [V] | Media (solo suite; falsea los e2e de degradacion) | Opciones: (a) `configure_structlog()` fija `wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET)`, la clase efectiva hoy en produccion [V], y deja de depender del estado global; (b) quitar `wrapper_class` del conftest; (c) pasar las 12 llamadas a pares clave-valor. Evaluar (a) en laboratorio con la suite completa (los tests H1 reconfiguran `structlog`) |
| R-2 | **Respaldo de la base de conocimiento con contenido ficticio**: `SimpleKnowledgeBase` (telefonos `+52`, envios en MXN, **cuenta bancaria y CLABE inventadas**), solo en el codigo (nunca en `kb_contents` ni en Redis). Capa 4 de `ShopifyKnowledgeBase.get_answer()` (firma correcta; `fallback_enabled=True` por el valor por defecto de `config.py`, no declarado en `env-vars.yaml` [V]). Con cobertura completa (13 temas x `es`/`en`/`fr` [V]) se alcanzaba por `GET /api/v1/kb/answer?...&category=X` **sin clave** (`category=ZAPATOS` -> 200 con la CLABE [V]) o con Supabase caido y la cache fria. El respaldo propio del handler (L541) ademas esta roto por firma | Alta (accesible sin clave) | **Mitigado** 16/11/2026 (seccion 10): `KB_ENABLE_FALLBACK=false`; el modulo y sus tests se conservan. Pendiente parte 2: mensaje honesto del handler (con R-4). 0 respuestas ficticias servidas en 30 dias, con solo 2 consultas a la base de conocimiento [V] |
| R-3 | **Apagado con variable sin asignar** (`lfm_keepalive_task`) cuando el arranque se aborta | Baja | Pendiente |
| R-4 | **Texto provisional fijo en espanol** (`mcp_conversation_handler.py` L3915): llega al usuario si no hay productos ni contrato | Media | Pendiente: texto segun el idioma de la peticion |
| R-5 | **Test de velocidad de Redis mal calibrado**: calibrado para ~150 ms por operacion; hoy 100 SET tardan 10-28 ms y el pipeline ~1 ms, asi que la relacion es ruido [V] | Baja (suite) | `perf_counter`, mas operaciones, mediana, o comprobar solo el orden |
| R-6 | **Tres modulos no se recolectan** [V]: `tests/performance/conftest.py` define `pytest_plugins` fuera de la raiz; `test_mcp_bridge_integration.py` existe con el mismo nombre en `tests/mcp/integration/` y en `tests/phase0_consolidation/`; `test_shopify_kb_client_logging` importa `assert_event_logged` de `conftest`, que resuelve a `tests/mcp/conftest.py` | Baja (suite) | Mover `pytest_plugins`, renombrar un duplicado, mover el helper a un modulo propio |
| R-7 | **`addopts` del `pytest.ini` en cada ejecucion**: `--cov-fail-under=40` hace fallar toda ejecucion parcial (codigo 1 con el test en verde) y la medicion de cobertura altera los tiempos | Baja (suite) | Cobertura solo en la ejecucion completa; tests de rendimiento aparte y sin cobertura |
| R-8 | **Modelos LFM retirados en OpenRouter**: `liquid/lfm-2-24b-a2b` (redactor de respuestas, calentamiento y keep-alive) y `liquid/lfm-2.5-1.2b-instruct:free` (reformulacion de la base de conocimiento), fijos en `claude_config.py` (L95, L116), devuelven 404 "no longer available" [V]. Errores todos los dias de la ventana de 30 dias de logs [V]; mas de 3 meses segun Yasmani [Y]. El respaldo GPT-4o-mini respondia en silencio, tras una llamada fallida (~190 ms medidos en la reformulacion) | Media (integracion muerta sin aviso; latencia y ruido) | **Mitigado** 16/11/2026 (seccion 10). Pendiente: decidir sustituto (candidatos en OpenRouter: `liquid/lfm-2.5-24b-a2b`, `liquid/lfm-3-1.7b:free` [H]) o retirar el codigo LFM; identificadores de modelo a configuracion; metrica de que camino responde |
| R-9 | **Piezas de la base de conocimiento rotas o duplicadas** [V]: `ServiceFactory.get_knowledge_base()` llama al constructor con `db=`, `redis=`, `shopify=` (los parametros son `db_pool`, `redis_service`, `shopify_client`), asi que siempre lanza `TypeError`, y fija `enable_fallback=True` ignorando el ajuste; `kb_config.py` define otra vez `KB_ENABLE_FALLBACK`; el log "System will use fallback KB (hardcoded) only" (`main_unified_redis.py` L2423) describe un respaldo que no funciona | Baja | Higiene: arreglar o retirar; una sola fuente de configuracion |

Observaciones:
- Redis local: la app no alcanza su Redis ni con `.env` (timeout); se degrada bien [V].
- Pausa constante de 2,05 s antes de conectar al Redis de Docker [H: `localhost` prueba primero IPv6] y aviso
  `MAINT_NOTIFICATIONS` (el cliente `redis` 8 usa un comando que el servidor local no conoce) [V]; sin efecto.
- `tests/conftest.py` contiene `TEST_API_KEY = "test-api-key-123"` (valor de prueba, sin uso en produccion).
- Produccion tras R-2 (logs del 16/11, 20:46-21:00 UTC) [V]: 5 consultas de la base de conocimiento (es/en)
  respondidas desde PostgreSQL o Redis; 0 eventos de capa 4; 0 `ERROR`. "Si, puedes pagar con tu cuenta PayPal"
  (reformulada por GPT-4o-mini) esta respaldada por el documento real [V]. Solo las respuestas reformuladas
  muestran "Ver politica completa"; las que son el documento entero no [H: intencionado].
- Clasificacion fragil: "aceptan devoluciones?" -> reglas `TRANSACTIONAL` 0.5 (sin palabra interrogativa); la
  rescatan el modelo ML y MiniLM con un margen de 0.07 [V].
- La primera clasificacion ML tras arrancar tarda 584 ms; las siguientes, 2 ms (carga perezosa) [V].
- Ruido de logs: ~110 WARNING `batch throttled` por arranque (limitador compartido funcionando); Google Retail
  API devuelve respuestas vacias para `anonymous` (sin eventos de usuario reales) [V].
- El log `LFM MCP personalisation disabled -- using Claude` es enganoso: con `GPT4O_MINI_FALLBACK_ENABLED=true`
  responde GPT-4o-mini [V].
- El commit `3b91ca1` (13/11, "cierre de S-13 y S-14") guardo una version anterior del DCT del incidente; la
  corrige `c1cfc51`. Lo delato un `numstat` de 98/20 frente a 9/3 previsto [V].

## 8. Pendientes, en orden

1. ~~R-2: decision y mitigacion~~: **hecho** 16/11/2026 (opcion B por configuracion, seccion 10).
2. ~~R-8: mitigacion~~: **hecho** 16/11/2026 (seccion 10).
3. R-2 parte 2 + R-4 (codigo, laboratorio primero): mensaje honesto en el idioma del cliente cuando no hay
   respuesta informativa; retirar o someter al ajuste el respaldo del handler; texto provisional segun el
   idioma; corregir los logs enganosos de R-8 y R-9.
4. R-8, decision de producto: sustituto LFM o retirada del codigo; identificadores de modelo a configuracion;
   metrica de que camino responde (LFM / GPT-4o-mini / Claude / texto fijo) con aviso.
5. R-1 (laboratorio y suite completa; si se elige (a), es un cambio de produccion con despliegue propio).
6. `tools/validation/check_env_drift.py` con las tres capas (seccion 5) y mejora de `compare_junit.py`
   (fallos que cambian de mensaje).
7. Higiene: R-3, R-5, R-6, R-7, R-9; metadatos del paquete (`pip check`); `tools/validation/README.md`.
8. Continuar con los pendientes 5 a 10 del DCT del incidente.

## 9. Lecciones

- **Un fallo temprano tapa los siguientes**: al instalar `httpx2`, un test paso de un fallo a otro distinto;
  comparar estados no basta, hay que comparar mensajes.
- **Comprobar el interprete en cada bloque**: dos sintomas que parecian fallos de codigo
  (`ModuleNotFoundError`, `--cov` desconocido) eran el Python global, no el del venv.
- **Un cociente de dos medidas de milisegundos es ruido**; los tests de rendimiento caducan en silencio
  cuando cambia el entorno para el que se calibraron.
- **Comparar local y produccion con la misma entrada** separa "codigo" de "entorno" en una sola llamada.
- **Buscar la observacion que refuta la hipotesis**: el log de una ejecucion sin pytest, ya disponible,
  desmontaba "R-1 rompe produccion"; se cruzo tarde.
- **Una configuracion global que no se fija entera hereda lo que otro dejo**: `structlog.configure()` solo
  cambia lo que recibe; la configuracion de la app debe ser completa.
- **Los caminos de error son codigo que casi nunca se ejecuta**: un test de degradacion los ejercita.
- **Un respaldo con datos de ejemplo es peor que no tener respaldo**, y hay que revisar todos sus puntos de
  uso: el mismo respaldo estaba roto en un sitio y vivo en otro.
- **Coincidencias no son sucesos**: leer el texto, contar por dimensiones y cruzar con otra senal antes de
  concluir; y "0 servidos" con 2 consultas en 30 dias no demuestra seguridad, solo falta de exposicion.
- **Comillas en Windows**: PowerShell, `cmd` (`gcloud` es un `.cmd`) y el lenguaje de filtros interpretan las
  comillas por separado; disenar filtros sin comillas internas y con control positivo.
- **Apagar no es borrar**: separar si algo debe ejecutarse (interruptor reversible), si debe existir el codigo
  y que parte del contenido vale; el interruptor ya existia (`KB_ENABLE_FALLBACK`).
- **Medir la cobertura cambia la naturaleza del riesgo**: con 13 temas x 3 idiomas, la capa 4 solo se alcanzaba
  por un parametro de la API o por una caida; un respaldo se dispara por todas las rutas que llevan a "no
  encontrado".
- **Un valor por defecto es la configuracion de produccion** de todo ajuste que nadie declara; los valores por
  defecto deben ser los seguros y `env-vars.yaml` deberia declarar todos los ajustes con efecto.
- **Mitigar primero, corregir despues**: una linea de configuracion con la misma imagen corta la exposicion en
  menos de una hora; la correccion completa sigue el ciclo normal, con su "parte 2" escrita en los pendientes.
- **Un respaldo silencioso puede ocultar una integracion muerta durante meses**: medir que camino responde y
  tratar un 404 de proveedor como fallo permanente (desactivar y avisar), no como transitorio.
- **Verificar lo que entra en el commit**, no solo lo que hay en disco: un `numstat` inesperado delato un
  commit anterior incompleto.

## 10. Mitigaciones en produccion (16/11/2026)

Ambas solo con configuracion (`env-vars.yaml`), la misma imagen (`sha256:e7b9c6fa...`) y commit antes del
despliegue. Vuelta atras: `gcloud run services update-traffic retail-recommender --to-revisions=<revision
anterior>=100`.

| Hallazgo | Cambio | Commit | Revision | Validacion [V] |
|---|---|---|---|---|
| R-2 | `KB_ENABLE_FALLBACK: "false"` (+3 lineas de comentario) | `1b7bb8f` | `00341-mr8` | Antes, sin clave: `category=ZAPATOS` -> 200 con la CLABE inventada; despues -> 404. `general` -> 200 con el contenido real, antes y despues. `fallback_enabled=False` al arrancar; 0 parejas `fallback_kb_enabled`; chat en ingles -> politica real; 0 `ERROR` |
| R-8 | `LFM_MCP_ENABLED` y `LFM_KB_ENABLED: "false"` (+3 lineas de comentario; `numstat` 6/2 por una linea en blanco al final) | `027c935` | `00342-c6x` | `lfm_warmup_skipped`; keep-alive no arranca; `gpt4o_mini_fallback_ok ... lfm_was_active=False` en las respuestas de producto; reformulacion KB por GPT-4o-mini sin llamada LFM; recomendaciones 8/8/0 antes y despues; 0 `ERROR` |

Latencia de R-8 con 3 muestras desde el cliente: 3337 / 2836 / 1376 ms antes y 3010 / 4202 / 1354 ms despues.
No es concluyente: con 3 muestras, la variacion entre peticiones (hasta ~1,4 s) es mayor que el efecto esperado
(~190 ms). La evidencia es la desaparicion de la llamada fallida previa en los logs, no el cronometro.
