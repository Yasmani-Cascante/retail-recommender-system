# DCT -- Incidente: credenciales expuestas en el repositorio publico (31/10/2026 - 03/11/2026)

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
sirven. Quedan pendientes la `API_KEY` propia, la contrasena de Neon y la limpieza del arbol.

| Credencial | Publicada desde | En uso al detectarlo | Estado |
|---|---|---|---|
| Token Admin API de Shopify (`shpat_`, 38 car.) | 08/04/2025 (`354c398`) | Si [V] | **Rotado** [V] -- token viejo -> HTTP 401 |
| Contrasena de Supabase (`DATABASE_URL`) | 20/09/2026 (`8c9fb20`) | Si [V] | **Rotada** [V] |
| `API_KEY` propia (32 car.) | 04/2025 (32 commits) | Si [V] | Pendiente (S-2) |
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
| 01/11/2026 | Rotacion de Shopify: permisos reducidos, desinstalar/reinstalar la app, version 3 del secreto |
| 02/11/2026 | Despliegue con el token nuevo: revision `00337-mf7` |
| 03/11/2026 09:57 | Arranque en frio de `00337-mf7` sin errores: valida la rotacion sin intervencion |

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

## 5. Hallazgos

| Id | Hallazgo | Gravedad | Estado |
|---|---|---|---|
| S-1 | Credenciales en el historial de un repositorio publico | Alta | Rotadas las criticas; repo publico por decision de Yasmani |
| S-2 | `API_KEY` publicada (32 commits); protege los endpoints de S-3. Su valor ES el identificador publico (API key) de la app de Shopify [V]: nunca fue secreto. Se usa en `theme.liquid` (L331, `data-api-key`) y en las cabeceras `X-API-Key` de 2 jobs de Scheduler [V] | Alta | Pendiente: valor aleatorio propio; cambiar en Secret Manager, tema y los 2 jobs en la misma ventana |
| S-3 | Endpoints con datos protegidos solo por `API_KEY`, por DUPLICADO: legacy en `main` (`GET /v1/legacy/ustomers/` -- HTTP 200, 6 clientes [V] --, `GET /v1/legacy/recommendations/user/{user_id}`, `POST /v1/legacy/events/user/{user_id}`) y sus equivalentes actuales en `routers/recommendations.py`, montado en `/v1` (`GET /v1/customers/`, `GET /v1/recommendations/user/{user_id}` con pedidos de cualquier id, `POST /v1/events/user/{user_id}`) [V]. Eliminar solo los legacy NO cierra S-3 | Alta | Analisis de consumidores en curso (seccion 6) |
| S-4 | F-04 confia en el `customerId` que envia el navegador: cualquiera puede pedir el perfil de otro cliente | Media (alta al abrir la tienda) | Rediseno antes de abrir la tienda (p. ej. App Proxy con firma HMAC de Shopify) |
| S-5 | `security_auth.py` usa `"default_key"` si falta `API_KEY`: falla abierto | Media | Pendiente |
| S-6 | Contrasena de Neon publicada; el proyecto Neon sigue existiendo 5 meses despues de la migracion | Media | Pendiente: eliminar el proyecto |
| S-7 | Ficheros del arbol con credenciales ya muertas: `.env.backup`, `scripts/deployment/gcp/*.ps1`, `revision-config.yaml`, token escrito en `tests/test_f04_customer_profile.py` | Baja (credenciales muertas) | Pendiente: commit de limpieza + `.gitignore` |
| S-8 | Secretos en claro en el `.env` local (`DATABASE_URL`, `SHOPIFY_ACCESS_TOKEN`) | Baja | Propuesta: cargador por sesion (`load_dotenv()` no sobrescribe [V]) |
| S-9 | Versiones de API `2025-01` (clientes) y `2024-01` (`products_router`); version de webhooks de la app `2025-01` | Baja | Pendiente [H: fuera de soporte] |
| S-10 | `ServiceFactory.get_db_pool()` ignora `DATABASE_URL` y apunta a `localhost`; usado por `get_knowledge_base()` y `get_kb_sync_service()`. Solo lo ejercita `/api/health/kb*` en 30 dias [V] | Baja (latente) | Pendiente |
| S-11 | Jobs de Scheduler `tfidf-daily-rebuild` (`/v1/admin/tfidf/rebuild`) y `visual-search-weekly-rebuild` (`/v1/mcp/visual-search/index`) se autentican con la `API_KEY`, sin OIDC [V]: con la clave publicada, cualquiera puede lanzar operaciones costosas | Media | Pendiente: OIDC de la cuenta de servicio y endpoints de administracion sin la clave del widget |

Observacion (no de seguridad): ping lento de Redis (~8 s) durante el arranque, visto en 2 de 2 arranques analizados.

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

Cambio preparado en laboratorio (pendiente de aplicar): 5 handlers en `main` (-246 lineas),
3 en `routers/recommendations.py` (-273), 1 linea en `observability_manager.py`.
Diff solo de eliminacion (+0); oraculo AST: resto de cada modulo identico; tabla de rutas:
exactamente las 8 eliminadas; finales de linea conservados (main LF; los otros dos CRLF).
Limpieza de 4 imports sin uso como paso B, condicionada a que ningun test los use como
objetivo de `patch`.

## 7. Pendientes, en orden

1. Completar el analisis de la seccion 6 y eliminar los endpoints legacy (cambio de codigo,
   laboratorio primero, un despliegue).
2. Rotar `API_KEY` (S-2): nueva version del secreto + despliegue + actualizar `data-api-key`
   en el tema de Shopify, en la misma ventana.
3. Limpieza del arbol + `.gitignore` (S-7).
4. Eliminar el proyecto Neon (S-6).
5. Antes de abrir la tienda: claves separadas (widget publica y limitada a `/v1/mcp/*`;
   administracion solo en servidor), rediseno de F-04 (S-4), `default_key` (S-5).
6. Mejoras: cargador de secretos por sesion (S-8), versiones de API (S-9), pool de
   `ServiceFactory` (S-10); versionar la prueba de humo de permisos en `tools/validation/`.
7. Retomar E5: recomendacion 2 (script de despliegue del monolito) y seguimiento 17.5.

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
