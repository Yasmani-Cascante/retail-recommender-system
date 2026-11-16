# DCT -- Incidente: credenciales expuestas en el repositorio publico (31/10/2026 - 13/11/2026)

Documento de continuidad tecnica del incidente de seguridad detectado el 30/10/2026
al revisar `env-vars.yaml` durante la recomendacion 1 de E5 nivel 2. Interrumpe el plan
de E5 (ver `RESUMEN_E5_Nivel2_Estado_30102026.md`, seccion 10), que se retoma al cerrar
los pendientes de la seccion 8.

Convencion: [V] verificado con evidencia; [H] hipotesis; [Y] confirmado por Yasmani sin
salida adjunta. Ningun valor secreto aparece en este documento.

---

## 1. Resumen

El repositorio `github.com/Yasmani-Cascante/retail-recommender-system` es **publico** [V]
y su historial contenia credenciales en uso. Se han **rotado** la contrasena de Supabase y
el token de Admin API de Shopify, con prueba de que las credenciales publicadas ya no
sirven, y se han eliminado las 8 rutas que exponian datos con la `API_KEY` (S-3, 07/11/2026).
Tambien se ha rotado la `API_KEY` (S-2, 11/11/2026). Se han retirado los endpoints de diagnostico sin autenticacion
(S-13, 13/11/2026) y una contrasena de Redis escrita en un test (S-14, credencial muerta). La busqueda por
VALOR de las 9 credenciales de Secret Manager (12/11) confirma que ninguna credencial en uso aparece en el
historial publico ni en el arbol. Quedan pendientes la contrasena de Neon y la limpieza del arbol.

| Credencial | Publicada desde | En uso al detectarlo | Estado |
|---|---|---|---|
| Token Admin API de Shopify (`shpat_`, 38 car.) | 08/04/2025 (`354c398`) | Si [V] | **Rotado** [V] -- token viejo -> HTTP 401 |
| Contrasena de Supabase (`DATABASE_URL`) | 20/09/2026 (`8c9fb20`) | Si [V] | **Rotada** [V] |
| `API_KEY` propia (32 car.) | 04/2025 (32 commits) y `GET /v1/debug/headers` (S-13) | Si [V] | **Rotada** 11/11/2026 [V] -- clave vieja -> HTTP 403 |
| Contrasena de Neon (`neondb_owner`, 16 car.) | 10/06/2026 (`7c6cd6f`) | Sin consumidores | Pendiente: eliminar proyecto (S-6) |
| Contrasena de Redis de una base de datos ya eliminada (32 car., `tests/test_f04_customer_profile.py`) | 04/2026 (`d11daf7`) | No: su host ya no existe [V] | Retirada del codigo (S-14) |
| Secreto del webhook de Shopify | -- | -- | **No expuesto** [V] (0 commits) |
| Clave de cuenta de servicio `embedding-service-key.json` | -- | -- | **Nunca publicada** [V] |
| Claves de Anthropic / OpenRouter / Perplexity | -- | -- | Solo marcadores de ejemplo [V] |

## 2. Cronologia (UTC salvo indicacion)

| Fecha | Hecho |
|---|---|
| 14/02/2025 15:36 | Se crea el token de Admin API de la app `Retails-assistant` (nunca rotado hasta este incidente) |
| 08/04/2025 | Primer commit con el token (`354c398`, `.env.secrets` y 6 scripts `.ps1`) |
| 12/04/2025 | Intento de limpieza con BFG (`49c6ac7`, `26530ac`): no reescribio el historial publicado y `replacements.txt` contiene el propio token |
| 20/09/2026 | `8c9fb20` publica `DATABASE_URL` con la contrasena de Supabase (`env-vars.yaml`, `revision-config.yaml`) |
| 30/10/2026 | Deteccion (N-1) al revisar `env-vars.yaml` |
| 31/10/2026 ~12:10 | Revision `00334-tdd` FALLA al desplegar: la cuenta de servicio no tenia acceso al secreto `database-url` (fallo seguro, el trafico siguio en `00333`) |
| 31/10/2026 ~12:36 | Despliegue A: `00335-rdg`, misma imagen, `DATABASE_URL` desde Secret Manager (commit `c8138cf`) |
| 31/10/2026 14:54 | Rotacion de Supabase: version 2 del secreto; revision `00336-h5g` |
| 01/11/2026 09:14 | Rotacion de Shopify: permisos reducidos, desinstalar/reinstalar la app, version 3 del secreto (token nuevo terminado en `8428`, segun el admin de Shopify) |
| 02/11/2026 | Despliegue con el token nuevo: revision `00337-mf7` |
| 03/11/2026 09:57 | Arranque en frio de `00337-mf7` sin errores: valida la rotacion sin intervencion |
| 07/11/2026 | S-3: commit `c2c11a8` (8 rutas eliminadas + tests); suite 1239 -> 1220 tests, 0 regresiones; revision `00338-kxr` (imagen `sha256:c1a39842...`) |
| 07/11/2026 | Commit `1033fdf`: corrige un CR suelto al final de `test_user_journey_discovery.py`, introducido por el corte (sin despliegue) |
| 11/11/2026 | Rotacion de `API_KEY`: valor aleatorio propio (v3 del secreto; v1 y v2 desactivadas), `theme.liquid`, `.env` y cabeceras de los 2 jobs; revision `00339-bws` (misma imagen) |
| 11/11/2026 19:42 | S-13 verificado en produccion: `GET /v1/debug/headers` sin clave -> 200; 0 peticiones en los 30 dias previos |
| 12/11/2026 | Busqueda por VALOR de las 9 credenciales de Secret Manager en el historial publicado y en el arbol: 0 en todas (control: la clave vieja, 32 commits y 95 ficheros) |
| 12/11/2026 | S-14: el host de Redis del test no resuelve en DNS (base de datos eliminada); el control con el host de produccion autentica |
| 13/11/2026 | S-13: commit `9c8df16` (5 endpoints de diagnostico retirados; tests y scripts leen `API_KEY` del entorno); suite 1220 -> 1220 sin cambios de estado; revision `00340-ssm` (imagen `sha256:e7b9c6fa...`) |

## 3. Alcance de la exposicion

- **Repositorio publico** [V]: API de GitHub, `visibility: public`. Ramas remotas: 17.
- **Busqueda por contenido** [V]: `git log --remotes -G` con los prefijos `shpat_`, `sk-ant-`,
  `sk-or-v1-`, `pplx-` y URLs `postgres://usuario:clave@`; 24 commits, valores enmascarados
  por su longitud. Control positivo: encontro `8c9fb20`.
- **Token de Shopify**: ~20 apariciones en 15 commits (scripts `.ps1` de 2025, `.env.secrets`,
  `.env.backup`, `replacements.txt`, `validate_e2e_fixes.py`, `tests/test_f04_customer_profile.py`,
  un `.docx`). Comparado con el valor en uso: igual [V].
- **Permisos del token expuesto**: 87, incluidos `write_discounts`, `write_gift_cards`,
  `write_custom_pixels`, `write_customers`, `write_orders` y 17 `unauthenticated_*`.
- **Revision de abuso en el admin de Shopify** [Y]: sin descuentos, tarjetas regalo, pixeles,
  paginas ni pedidos ajenos. Limite: una lectura no deja rastro.
- **Datos personales**: la tienda es de desarrollo de partner y **tiene contrasena** [V]
  (conector de Shopify). 6 clientes, todos con cuenta desactivada; 3 creados en el mismo
  segundo (datos de ejemplo) [V]; de prueba [H].
- **Trafico de 30 dias a las 8 rutas con datos** [V]: 3 peticiones, todas de Yasmani
  (IP confirmada) el 01/11 00:58-01:03 UTC: 2 `curl` (200) y 1 navegador sin clave (403).
  Limite: los logs cubren 30 dias; la `API_KEY` lleva publicada desde 04/2025.
- **`.env.test`** [V] (16/11/2026): estuvo en 4 commits publicados de 2025, sin credenciales con valor
  (control positivo con el fichero actual); ningun valor actual de `.env` ni de `.env.test` aparece publicado,
  salvo una clave de prueba muerta para produccion. Detalle en
  `DCT_Alineacion_Venv_Diagnostico_Suite_16112026.md`, seccion 6.

## 4. Contencion y rotacion

### 4.1 `DATABASE_URL` (Supabase) -- cerrada

Patron expandir -> migrar -> contraer (la primera propuesta, rotar primero, habria tirado
produccion: corregida antes de ejecutarla).

1. Secreto `database-url` (v1) con el valor en uso; igualdad comprobada por SHA-256 sin mostrarlo [V].
2. Permiso `roles/secretmanager.secretAccessor` para `178362262166-compute@developer.gserviceaccount.com`
   a nivel de secreto, como el resto de secretos del proyecto [V].
3. Despliegue A con la misma imagen (`sha256:c02f4a43...`): `00335-rdg`. Evidencia:
   `db_config_from_DATABASE_URL` + `PostgreSQL pool created and tested successfully`;
   misma imagen, 0 variables distintas, flag E5 = 1 [V].
4. Contrasena nueva generada en local (48 hex), puesta en Supabase y en la version 2 del
   secreto; revision `00336-h5g` conecta con ella [V]. Version 1 desactivada [V].
5. `.env` local actualizado leyendo el secreto (sin portapapeles): `alembic current` -> `0002 (head)` [V].

### 4.2 Token de Admin API de Shopify -- cerrada

App `Retails-assistant` (legacy custom app creada en el admin). Segun la documentacion de
Shopify, sus credenciales no se rotan: se desinstala y reinstala la app (NUNCA borrarla).

1. Comprobaciones previas: el token de produccion terminaba en `d79f`, el de la app [V];
   secreto del webhook en 0 commits con control positivo (`api-key`: 32) [V] -> metodo R
   (reinstalar la misma app; el secreto del webhook no cambia).
2. Permisos derivados del codigo que llega a la imagen (`Dockerfile.cloudrun` solo copia
   `src/`, `data/`, `static/`, `models/`; arranca solo uvicorn, sin Node): solo lecturas.
   Configuracion final [V]: 11 marcados + 3 implicitos = **14** (`read_all_orders`,
   `read_content`, `read_customers`, `read_inventory`, `read_locales`, `read_locations`,
   `read_online_store_pages`, `read_orders`, `read_products`, `read_returns`,
   `read_shipping`, `read_translations`, `unauthenticated_read_gates`,
   `unauthenticated_write_gates`). Sin ningun `write_*`. Storefront API sin permisos.
   Decision de Yasmani: `read_locations`, `read_returns`, `read_shipping` y `read_content`
   se mantienen para funcionalidades futuras; `read_customer_events` (informacion personal) retirado.
3. Puerta de paso antes de desplegar: prueba de humo 11/11 con el token nuevo [V] y
   **token viejo -> HTTP 401** [V].
4. Despliegue con la misma imagen: `00337-mf7`. Arranque del 03/11 [V]: 0 `ERROR`;
   paginas, metafields, GraphQL (200), precios por mercado, idiomas y traducciones OK;
   `shopify_webhooks_fetched` con `total_webhooks: 4` (recreados por
   `ensure_webhooks_registered()` tras la desinstalacion).
5. Versiones 1 y 2 del secreto desactivadas; version 3 activa [V]. `.env` local actualizado
   (opcion A, decision de Yasmani).

### 4.3 `API_KEY` -- cerrada

Antes era el identificador publico (API key) de la app de Shopify: se sustituye por un valor aleatorio
propio. El identificador de Shopify no se rota ni lo necesita; lo que importaba es que el sistema dejara
de aceptarlo como clave.

1. Valor aleatorio de 32 caracteres; secreto `api-key` v3, con v1 y v2 desactivadas [V]. `.env` local
   igual al secreto (comparado en memoria, sin mostrarlo) [V].
2. Cabeceras `X-API-Key` de `tfidf-daily-rebuild` y `visual-search-weekly-rebuild` actualizadas y
   comparadas en memoria [V]; `data-api-key` en `theme.liquid`.
3. Despliegue con la misma imagen (`sha256:c1a39842...`): revision `00339-bws`, arranque sin `ERROR` [V].
4. Efecto: clave vieja -> 403 (`Intento de acceso con API Key invalida`), clave nueva -> 200 [V]; job
   `tfidf-daily-rebuild` -> `POST /v1/admin/tfidf/rebuild` 200 desde `Google-Cloud-Scheduler`, 3045
   productos [V]; 2 conversaciones del widget desde la tienda -> 200, lo que confirma la clave del tema [V].
5. Orden: los jobs se actualizaron antes del despliegue. Sin consecuencias (ningun job se ejecuto en el
   intervalo), pero el orden seguro es desplegar primero y actualizar despues los consumidores.

Pendiente: `visual-search-weekly-rebuild` se confirmara en su proxima ejecucion programada. Diez ficheros
de tests y scripts (y `config/cloud/app.yaml`) tienen el valor viejo escrito: los tests que llamen a la
aplicacion con el fallaran hasta que lean la clave del entorno (seccion 8).

## 5. Hallazgos

| Id | Hallazgo | Gravedad | Estado |
|---|---|---|---|
| S-1 | Credenciales en el historial de un repositorio publico | Alta | Rotadas las criticas; repo publico por decision de Yasmani |
| S-2 | `API_KEY` publicada (32 commits); protege los endpoints de S-3. Su valor ES el identificador publico (API key) de la app de Shopify [V]: nunca fue secreto. Se usa en `theme.liquid` (L331, `data-api-key`) y en las cabeceras `X-API-Key` de 2 jobs de Scheduler [V] | Alta | **Cerrado** 11/11/2026 [V] (seccion 4.3) |
| S-3 | Endpoints con datos protegidos solo por `API_KEY`, por DUPLICADO: legacy en `main` (`GET /v1/legacy/ustomers/` -- HTTP 200, 6 clientes [V] --, `GET /v1/legacy/recommendations/user/{user_id}`, `POST /v1/legacy/events/user/{user_id}`) y sus equivalentes actuales en `routers/recommendations.py`, montado en `/v1` (`GET /v1/customers/`, `GET /v1/recommendations/user/{user_id}` con pedidos de cualquier id, `POST /v1/events/user/{user_id}`) [V]. Eliminar solo los legacy NO cierra S-3 | Alta | **Cerrado** 07/11/2026 [V] (seccion 6) |
| S-4 | F-04 confia en el `customerId` que envia el navegador: cualquiera puede pedir el perfil de otro cliente | Media (alta al abrir la tienda) | Rediseno antes de abrir la tienda (p. ej. App Proxy con firma HMAC de Shopify) |
| S-5 | `security_auth.py` usa `"default_key"` si falta `API_KEY`: falla abierto | Media | Pendiente |
| S-6 | Contrasena de Neon publicada; el proyecto Neon sigue existiendo 5 meses despues de la migracion | Media | Pendiente: eliminar el proyecto |
| S-7 | Ficheros del arbol con credenciales ya muertas: `.env.backup`, `scripts/deployment/gcp/*.ps1`, `revision-config.yaml`, token escrito en `tests/test_f04_customer_profile.py` | Baja (credenciales muertas) | Pendiente: commit de limpieza + `.gitignore` |
| S-8 | Secretos en claro en el `.env` local (`DATABASE_URL`, `SHOPIFY_ACCESS_TOKEN`) | Baja | Propuesta: cargador por sesion (`load_dotenv()` no sobrescribe [V]) |
| S-9 | Versiones de API `2025-01` (clientes) y `2024-01` (`products_router`); version de webhooks de la app `2025-01` | Baja | Pendiente [H: fuera de soporte] |
| S-10 | `ServiceFactory.get_db_pool()` ignora `DATABASE_URL` y apunta a `localhost`; usado por `get_knowledge_base()` y `get_kb_sync_service()`. Solo lo ejercita `/api/health/kb*` en 30 dias [V] | Baja (latente) | Pendiente |
| S-11 | Jobs de Scheduler `tfidf-daily-rebuild` (`/v1/admin/tfidf/rebuild`) y `visual-search-weekly-rebuild` (`/v1/mcp/visual-search/index`) se autentican con la `API_KEY`, sin OIDC [V]: con la clave publicada, cualquiera puede lanzar operaciones costosas | Media | Pendiente: OIDC de la cuenta de servicio y endpoints de administracion sin la clave del widget |
| S-12 | `/docs` y `/openapi.json` publicos en produccion: publican el mapa de la API, incluidas las rutas de administracion [V] (logs del 07/11) | Baja | Pendiente: desactivar o proteger antes de abrir la tienda |
| S-13 | `GET /v1/debug/headers` (`products_router.py`, L2109) sin autenticacion: su respuesta incluia `expected_api_key` con la `API_KEY` en uso escrita en el codigo, asi que cualquiera podia leer la clave sin pasar por GitHub. En produccion: sin clave -> 200 [V]; 0 peticiones en los 30 dias previos, con control positivo (la consulta encuentra la peticion de prueba) [V]. Encontrado buscando el VALOR literal de la clave (busqueda de Yasmani) | Alta (neutralizado por la rotacion: devuelve un valor muerto) | **Cerrado** 13/11/2026 [V] (seccion 7) |
| S-14 | Contrasena de Redis escrita en `tests/test_f04_customer_profile.py`, con host y puerto, bajo un comentario que decia "Credenciales desde .env". Se escapo a la busqueda por prefijos (una contrasena aleatoria no tiene prefijo). No es la actual (0 commits con la actual) y su host no resuelve en DNS: base de datos eliminada [V] | Baja (credencial muerta) | **Cerrado** 13/11/2026: retirada del codigo en `9c8df16` |

Observaciones (no de seguridad):
- Ping lento de Redis (~8 s) durante el arranque, visto en 2 de 2 arranques analizados.
- Higiene de la suite (07/11) [V]: `tests/integration/test_hybrid_detector_with_reset.py` es un script que
  ejecuta `sys.exit(1)` al importarse (si falta el modelo, o si falla una de sus 6 frases) y aborta toda la
  sesion de pytest. Tres paquetes no se recolectan: `tests/performance`, `tests/phase0_consolidation/
  test_mcp_bridge_integration` y `tests/test_h1_structured_logging/test_shopify_kb_client_logging`; los
  tests de `tests/performance` no se ejecutan nunca.
- Alcance de la linea base: la suite completa tiene 1239 tests, 749 de ellos en `tests/unit`; la cifra de
  749 del 30/10 parece corresponder solo a `tests/unit` [H]. Comando usado el 07/11, igual antes y despues
  y en la misma carpeta: `pytest --ignore=tests/integration/test_hybrid_detector_with_reset.py
  --continue-on-collection-errors --junitxml=...` con `PYTHONUTF8=1`.
- `tools/validation/README.md`: el procedimiento del worktree necesita tambien los artefactos no
  versionados (`models/`); hay que corregirlo.
- Finales de linea: un CR suelto hace que git no aplique `core.autocrlf` a ese fichero (lo trata como
  binario a efectos de conversion); relacionado con H-18 (falta `.gitattributes`).
- Deriva del entorno local (13/11) [V]: el venv local tiene `anthropic` 0.69.0 y no tiene `httpx2`; produccion
  fija `anthropic==1.7.0` y `httpx2==2.13.0` (`requirements.cloudrun.txt`). Todo test que llega a la
  conversacion falla en local con `ModuleNotFoundError: httpx2` (`service_factory.py:1331`); hasta S-13 lo
  ocultaba el 403 de la clave escrita (fallo enmascarado). El comentario de `service_factory.py` (L1305) cita
  versiones antiguas (1.3.0 / 2.12.0). **Resuelto** 13-16/11/2026: venv instalado desde
  `requirements.cloudrun.txt` (ver `DCT_Alineacion_Venv_Diagnostico_Suite_16112026.md`).
- `tools/validation/compare_junit.py` compara estados, no causas: no ve un fallo que cambia de mensaje
  (`test_kb_language_detection`: 403 -> `httpx2`). Mejora: una seccion "fallos que cambian de mensaje".
- Secret Manager: `perplexity-api-key` vacio o con un valor corto [H]; `db-password` no lo usa el
  despliegue (resto de la base de datos anterior [H]).
- `tests/test_f04_customer_profile.py`: 3 de sus tests dan error al prepararse, antes y despues de S-13;
  parecen funciones de script cuyos parametros pytest interpreta como fixtures [H].

## 6. Eliminacion de los endpoints legacy -- analisis

Rutas en `main_unified_redis.py` [V]: `GET /legacy/health` (L3078),
`GET /v1/legacy/recommendations/user/{user_id}` (L3249), `POST /v1/legacy/events/user/{user_id}` (L3341),
`GET /v1/legacy/ustomers/` (L3418), `GET /health/legacy` (L3857).

Consumidores comprobados:
- Widget (`static/widget/widget.umd.cjs`) [V]: usa `/v1/mcp/conversation`, `/v1/mcp/session/`,
  `/v1/mcp/visual-search`, `/v1/mcp/visual-search/outfit` y `/health`; **ninguna ruta legacy**
  (control positivo: el mismo patron encuentra las 4 rutas `/v1/mcp`).
- Referencias internas en `main` [V]: los handlers no se llaman desde otro codigo.
- Jobs de Cloud Scheduler [V]: `tfidf-daily-rebuild` -> `/v1/admin/tfidf/rebuild`,
  `visual-search-weekly-rebuild` -> `/v1/mcp/visual-search/index`,
  `embedding-service-warmup` -> `/health` del embedding service. Ninguno legacy.
  Los dos primeros envian `X-API-Key`, sin OIDC [V] (ver S-2 y S-11).

Equivalentes actuales en `routers/recommendations.py` (montado con `prefix="/v1"`, L3526
de `main`) [V]: `GET /v1/customers/` (L139), `GET /v1/recommendations/user/{user_id}` (L467),
`POST /v1/events/user/{user_id}` (L594); ademas `GET /v1/`, `GET /v1/metrics`,
`GET /v1/recommendations/{product_id}`. Los tres primeros tienen la misma exposicion que
los legacy.

Resto de consumidores [V]: el widget que sirve el tema es `embed.js` + `widget.umd(old2).js`
(identico byte a byte a `widget.umd.cjs`); Cloud Monitoring sin comprobaciones de
disponibilidad (`exit 0`, sin resultados); trafico de 30 dias solo de Yasmani;
`observability_manager.py` solo cita una ruta en una lista informativa.

**Veredicto: eliminar las 8 rutas es seguro en produccion** [V]. Afecta a tests de
integracion, e2e y rendimiento, que se adaptan en el mismo cambio.

**Cambio aplicado (07/11/2026, commit `c2c11a8`)** [V]:
- Codigo: 5 handlers en `main` y 3 en `routers/recommendations.py`, con los 4 imports que quedaban sin
  uso (0 objetivos de `patch` en los tests); 1 linea en `observability_manager.py`. Validado en
  laboratorio: oraculo AST, tabla de rutas (exactamente las 8), pyflakes diferencial sin avisos nuevos.
- Tests: 20 retirados (19 + `test_user_journey_purchase.py` entero, porque sin compra su nombre mentia);
  3 adaptados que solo pierden sentencias (oraculo de subsecuencia); el resumen de
  `test_recommendations_router.py` se reescribio para no prometer cobertura inexistente.
- Aplicacion: `apply_S3.py` (fuera del repo), con base y resultado verificados por sha256 y todo o nada.
- Suite: 1239 -> 1220 tests (-19: el test retirado de `tests/performance` nunca se ejecutaba),
  0 fallos nuevos (`compare_junit.py`); recuentos por estado cuadrados uno a uno.
- Produccion, revision `00338-kxr`: controles `/health` y `/v1/metrics` -> 200; las 6 rutas GET y las
  2 POST eliminadas -> 404 (POST con `Content-Length: 0`; control `POST /v1/mcp/conversation` -> 422);
  prueba diferencial sin clave: ruta viva -> 403, rutas eliminadas -> 404. Arranque sin `ERROR`,
  4 webhooks, conversacion del widget -> 200, `/v1/admin/tfidf/rebuild` -> 200 (3045 productos, 417 s).
- El commit incluye `src/api/main_unified_redis.backup_07112026.py`, copia de `main` previa al cambio,
  intencionada (decision de Yasmani; no importable por los puntos del nombre).
- `1033fdf` corrige un CR suelto final en `test_user_journey_discovery.py`: el corte elimino la ultima
  linea de un fichero sin salto final. Ninguna verificacion del laboratorio contaba los CR sueltos;
  lo detecto `git diff --ignore-cr-at-eol` (1/19 frente a 0/18 previsto).

## 7. Endpoints de diagnostico sin autenticacion (S-13) y contrasena de Redis en un test (S-14)

Inventario de `products_router.py`: 7 endpoints `/v1/debug/*` [V]. Antes de retirar nada se comprobo, para cada
uno, su proposito (codigo y documentacion), su uso y si existe un equivalente:

| Endpoint | Proposito (segun su codigo) | Autenticacion | Uso / equivalente | Decision |
|---|---|---|---|---|
| `headers` | "Temporal": depurar `X-API-Key` (devolvia la clave en uso) | Ninguna | Solo pruebas de Yasmani | Retirado |
| `auth-test` | Pareja de `headers` | `API_KEY` | Equivalente: cualquier GET con clave (`/v1/metrics`) | Retirado |
| `load-test` | Diagnostico de pruebas de carga | `API_KEY` | La prueba de carga no lo usa | Retirado |
| `product-cache` | Estadisticas de ProductCache (runbook de agosto de 2025) | Ninguna | Equivalente: `/v1/enterprise/cache/stats` (misma cache, con clave) | Retirado |
| `shopify` | Conexion con Shopify (una llamada real por peticion) | Ninguna | Prueba de humo de permisos y logs de arranque | Retirado, con `debug_shopify_connection()` |
| `product/{id}` | Rendimiento por producto (runbook) | `API_KEY` | Sin equivalente | Se queda (clave de administracion antes de abrir la tienda) |
| `product-comparison/{id}` | Comparar metodos de obtencion (runbook) | `API_KEY` | Sin equivalente | Se queda (idem) |

Consumidores [V]: en el repo, solo la definicion, un `print` en `fix_cache_priority.py` y las pruebas de humo de
Neon (aceptan 404); en 30 dias de logs, solo llamadas de Yasmani (control positivo: aparecen todas); ni el
widget ni Scheduler los usan.

**Cambio aplicado (13/11/2026, commit `9c8df16`)** [V]:
- Codigo: los 5 endpoints, `debug_shopify_connection()` y el import `Request` (sin uso). Tabla de rutas 20 -> 15;
  oraculo AST (resto del modulo identico); solo eliminaciones; pyflakes sin avisos nuevos.
- Tests y scripts (8): los que corren la app en el propio proceso usan `security_auth.API_KEY` (la clave con la
  que valida); los que llaman a un servidor externo leen el entorno tras `load_dotenv()`; `test_f04` deja de
  contener el token revocado y la contrasena de Redis (S-14); la prueba de carga retira 2 tareas de rutas
  eliminadas en S-3, que entonces se escapo (solo se trataron los tests de pytest), y adapta
  `complete_shopping_flow` (peso total de tareas 61 -> 49).
- Aplicacion: `apply_S13.py` (fuera del repo; tres estados por fichero; todo o nada). Diffs de revision con los
  valores sensibles enmascarados.
- Suite: 1220 -> 1220 tests, 0 cambios de estado. Prediccion fallida y util: los 2 tests de
  `test_kb_language_detection` siguen fallando, pero por otra causa (antes 403 por la clave; despues `httpx2`,
  la deriva del entorno local de la seccion 5).
- Produccion, revision `00340-ssm`: sin clave, las 5 rutas retiradas -> 404 y las 2 que se quedan -> 403;
  `/health` -> 200; las 8 peticiones aparecen en los logs del servicio. Arranque sin `ERROR`, 4 webhooks,
  3 conversaciones del widget -> 200. git: 38 inserciones / 288 eliminaciones, igual que el laboratorio
  fichero a fichero.

S-14: la contrasena del test no es la actual (0 commits con la actual) y su host no resuelve en DNS; el control
(host de produccion, contrasena actual, mismo equipo) autentica: base de datos eliminada, credencial muerta.

## 8. Pendientes, en orden

1. ~~Eliminar los endpoints con datos~~ (S-3): **hecho** el 07/11/2026.
2. ~~Rotar `API_KEY`~~ (S-2): **hecho** el 11/11/2026.
3. ~~Retirar los endpoints de diagnostico sin autenticacion (S-13) y la clave escrita en tests y scripts~~:
   **hecho** el 13/11/2026 (seccion 7).
4. ~~Alinear el venv local con produccion~~: **hecho** 13-16/11/2026
   (`DCT_Alineacion_Venv_Diagnostico_Suite_16112026.md`). Sigue pendiente `tools/validation/check_env_drift.py`,
   ahora con tres capas (`env-vars.yaml`, `.env`, `.env.test`).
5. Limpieza del arbol + `.gitignore` (S-7; unos 95 ficheros contienen aun la clave vieja, ya muerta) y
   politica de finales de linea en `.gitattributes` (H-18). `config/cloud/app.yaml` incluido.
6. Eliminar el proyecto Neon (S-6) y revisar los secretos `db-password` y `perplexity-api-key`.
7. Higiene de la suite (observaciones de la seccion 5), mejora de `compare_junit.py` (fallos que cambian de
   mensaje) y corregir `tools/validation/README.md`. Anotar en el runbook de ProductCache (agosto de 2025)
   que `/v1/debug/product-cache` se sustituye por `/v1/enterprise/cache/stats`.
8. Antes de abrir la tienda: claves separadas (widget publica limitada a `/v1/mcp/*`; administracion solo
   en servidor, incluidos `/v1/debug/product/{id}` y `/v1/debug/product-comparison/{id}`), OIDC para Scheduler
   (S-11), rediseno de F-04 (S-4), `default_key` (S-5), `/docs` (S-12) y una via segura para eventos reales
   (compras por webhook `orders/paid` firmado con HMAC; navegacion por pixel hacia un endpoint solo de escritura).
9. Mejoras: cargador de secretos por sesion (S-8), versiones de API (S-9), pool de `ServiceFactory` (S-10);
   versionar la prueba de humo de permisos en `tools/validation/`.
10. Retomar E5: recomendacion 2 (script de despliegue del monolito) y seguimiento 17.5.

## 9. Lecciones del incidente

- **Rotar invalida; esconder no.** Borrar el repo o hacerlo privado solo protege el futuro.
- **Expandir -> migrar -> contraer**: nunca invalidar una credencial con consumidores vivos.
- **Minimo privilegio**: la gravedad de una filtracion la decide lo que la credencial permite
  (87 permisos con escritura frente a 14 de lectura).
- **Verificar el objetivo antes de una accion destructiva** (ultimos 4 caracteres) y
  **demostrar el efecto** (token viejo -> 401), no solo la accion.
- **Un valor que llega al navegador es un identificador, no un secreto** (`data-api-key`).
- **Ausencias con control positivo**: varias comprobaciones devolvieron "vacio" por fallos
  de la herramienta (paginador de git, `sh` sin llaves, un 404 con JSON valido, un regex que
  no encontraba nada). Cada "0" se acompano de una busqueda que debia dar mas de 0.
- **Validar la medicion antes de usarla**: tres lineas base invalidas (`sys.exit` por un modelo ausente,
  `sys.exit` por una frase al limite, errores de recoleccion) solo se detectaron comparando el recuento con
  un valor esperado independiente.
- **Predecir antes de medir**: 1219 previstos frente a 1220 medidos revelo que `tests/performance` no se
  ejecuta; `0 18` frente a `1 19` revelo el CR suelto.
- **Que capa responde**: un 411 del frontal de Google no llega al servicio; un 404 solo prueba una
  eliminacion si un control demuestra que la peticion llega a la aplicacion.
- **Windows PowerShell 5.1 descarta los argumentos vacios** al llamar a programas externos (`--data ""`).
- **Precondiciones de tres estados** (base / ya aplicado / otro) y **casos frontera en los extremos**
  (eliminar la ultima linea de un fichero sin salto final).
- **El radio de exposicion de un secreto incluye el codigo que lo muestra**: buscar por el VALOR literal
  encontro S-13, que ninguna busqueda por nombre de variable o por prefijo habria encontrado.
- **Huecos entre descargas de logs**: las 2 conversaciones de prueba cayeron entre dos ficheros; antes de
  interpretar una ausencia, comprobar que las ventanas de los ficheros son contiguas.
- **Orden de una rotacion con consumidores**: desplegar primero y actualizar despues a los consumidores; y
  un endpoint de diagnostico nace con autenticacion de administrador y fecha de caducidad, o no nace.
- **Buscar por el valor, no solo por la forma**: una contrasena sin prefijo (S-14) se escapo a la busqueda por
  prefijos; buscar el VALOR de cada secreto de Secret Manager responde directamente si hay credenciales vivas
  publicadas.
- **Un diff contiene lo que se quita**: al retirar credenciales del codigo, rotarlas antes; los diffs de
  revision se enmascaran.
- **Fallos enmascarados**: arreglar un fallo puede destapar el siguiente sin cambiar el estado del test;
  conviene comparar tambien los mensajes.
- **Validar el entorno antes de medir**: venv activado, informe generado y recuento minimo, con `throw` si no
  se cumple; y el venv local debe instalarse desde el mismo fichero que produccion.
- **Retirar algo citado en un runbook exige actualizar el runbook** con su equivalente.
