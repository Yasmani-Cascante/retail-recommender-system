# DCT -- Incidente: credenciales expuestas en el repositorio publico (31/10/2026 - 11/11/2026)

Documento de continuidad tecnica del incidente de seguridad detectado el 30/10/2026
al revisar `env-vars.yaml` durante la recomendacion 1 de E5 nivel 2. Interrumpe el plan
de E5 (ver `RESUMEN_E5_Nivel2_Estado_30102026.md`, seccion 10), que se retoma al cerrar
los pendientes de la seccion 7.

Convencion: [V] verificado con evidencia; [H] hipotesis; [Y] confirmado por Yasmani sin
salida adjunta. Ningun valor secreto aparece en este documento.

---

## 1. Resumen

El repositorio `github.com/Yasmani-Cascante/retail-recommender-system` es **publico** [V]
y su historial contenia credenciales en uso. Se han **rotado** la contrasena de Supabase y
el token de Admin API de Shopify, con prueba de que las credenciales publicadas ya no
sirven, y se han eliminado las 8 rutas que exponian datos con la `API_KEY` (S-3, 07/11/2026).
Tambien se ha rotado la `API_KEY` (S-2, 11/11/2026). Quedan pendientes retirar `/v1/debug/headers`
(S-13), la contrasena de Neon y la limpieza del arbol.

| Credencial | Publicada desde | En uso al detectarlo | Estado |
|---|---|---|---|
| Token Admin API de Shopify (`shpat_`, 38 car.) | 08/04/2025 (`354c398`) | Si [V] | **Rotado** [V] -- token viejo -> HTTP 401 |
| Contrasena de Supabase (`DATABASE_URL`) | 20/09/2026 (`8c9fb20`) | Si [V] | **Rotada** [V] |
| `API_KEY` propia (32 car.) | 04/2025 (32 commits) y `GET /v1/debug/headers` (S-13) | Si [V] | **Rotada** 11/11/2026 [V] -- clave vieja -> HTTP 403 |
| Contrasena de Neon (`neondb_owner`, 16 car.) | 10/06/2026 (`7c6cd6f`) | Sin consumidores | Pendiente: eliminar proyecto (S-6) |
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
aplicacion con el fallaran hasta que lean la clave del entorno (seccion 7).

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
| S-13 | `GET /v1/debug/headers` (`products_router.py`, L2109) sin autenticacion: su respuesta incluia `expected_api_key` con la `API_KEY` en uso escrita en el codigo, asi que cualquiera podia leer la clave sin pasar por GitHub. En produccion: sin clave -> 200 [V]; 0 peticiones en los 30 dias previos, con control positivo (la consulta encuentra la peticion de prueba) [V]. Encontrado buscando el VALOR literal de la clave (busqueda de Yasmani) | Alta (neutralizado por la rotacion: devuelve un valor muerto) | Pendiente: eliminar el endpoint |

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

## 7. Pendientes, en orden

1. ~~Eliminar los endpoints con datos~~ (S-3): **hecho** el 07/11/2026.
2. ~~Rotar `API_KEY`~~ (S-2): **hecho** el 11/11/2026.
3. Eliminar `GET /v1/debug/headers` (S-13) y que los tests y scripts lean `API_KEY` del entorno en lugar de
   tenerla escrita (un cambio de codigo, laboratorio primero); debe ir ANTES de la proxima linea base de la
   suite, o los fallos por la rotacion se confundiran con regresiones. `config/cloud/app.yaml` va a S-7.
4. Limpieza del arbol + `.gitignore` (S-7) y politica de finales de linea en `.gitattributes` (H-18).
5. Eliminar el proyecto Neon (S-6).
6. Higiene de la suite (observaciones de la seccion 5) y corregir `tools/validation/README.md`.
7. Antes de abrir la tienda: claves separadas (widget publica limitada a `/v1/mcp/*`; administracion solo
   en servidor), OIDC para Scheduler (S-11), rediseno de F-04 (S-4), `default_key` (S-5), `/docs` (S-12) y
   una via segura para eventos reales (compras por webhook `orders/paid` firmado con HMAC; navegacion por
   pixel hacia un endpoint solo de escritura).
8. Mejoras: cargador de secretos por sesion (S-8), versiones de API (S-9), pool de `ServiceFactory` (S-10);
   versionar la prueba de humo de permisos en `tools/validation/`.
9. Retomar E5: recomendacion 2 (script de despliegue del monolito) y seguimiento 17.5.

## 8. Lecciones del incidente

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
