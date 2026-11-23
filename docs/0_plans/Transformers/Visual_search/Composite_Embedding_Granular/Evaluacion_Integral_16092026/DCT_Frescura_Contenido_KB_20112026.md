# DCT -- Frescura y fidelidad del contenido de la base de conocimiento (20/11/2026 - en curso)

Continuacion de `DCT_Alineacion_Venv_Diagnostico_Suite_16112026.md` (secciones 7, 8, 11 y 12). Aquel documento
cerro el modo degradado (R-2 parte 2, respuesta honesta cuando la base de conocimiento no responde; R-4, textos de
los modos degradados en el idioma del cliente). Este sigue el camino normal: el contenido que el chat sirve a
todos los clientes.

Convencion: [V] verificado con evidencia; [H] hipotesis; [Y] confirmado o decidido por Yasmani. Ningun valor
secreto aparece en este documento. Evidencias en bruto en `C:\Users\yasma\Desktop\diag_14112026\` (fuera del repo).

---

## 1. Por que este documento

Pregunta de Yasmani (20/11/2026): "Nos estamos asegurando de no mostrar informacion desactualizada?". Respuesta:
**no del todo** (seccion 3). Hasta ahora el foco estuvo en el camino degradado (mensaje honesto), que era lo
urgente mientras habia contenido ficticio accesible (R-2). El camino normal sirve contenido a todos los clientes
todos los dias, asi que sus defectos pesan mas. Criterio de prioridad acordado [Y]: **clientes afectados x
consecuencia**.

La tienda esta hoy protegida con contrasena ("Store access is restricted", captura del 20/11) [V]: ningun cliente
esta expuesto todavia. **Aclaracion 20/11 [Y]**: `ai-shoppings` es una tienda de demostracion sin clientes reales;
sus paginas y politicas contienen datos de ejemplo a proposito. El sistema es el producto; el contenido lo aporta
cada tienda cliente. Este documento sigue la calidad del camino normal del sistema y lo que el producto debe
exigir o comprobar en cada tienda.

## 2. Como llega el contenido al cliente (glosario)

```
 Shopify: paginas + traducciones (Translate & Adapt)    <- FUENTE DE VERDAD (la edita la tienda)
     |  sincronizacion por instancia de Cloud Run:
     |    - completa al arrancar (todas las traducciones publicadas)
     |    - incremental cada 5 min mientras la instancia vive (solo paginas cambiadas; idiomas publicados desde R-13b)
     |    - Shopify NO envia webhooks de paginas: no hay sincronizacion inmediata al editar
     v
 kb_contents en PostgreSQL (Supabase)                     <- COPIA de trabajo (39 filas generales: 13 temas x es/en/fr)
     v
 Redis (cache de respuestas, 24 h)                         <- COPIA de la copia; se invalida al cambiar una pagina
     v
 ShopifyKnowledgeBase (knowledge_base_v2.py)               <- CODIGO que busca la respuesta: Redis -> PostgreSQL
     v
 Chat: el documento tal cual, o reformulado por GPT-4o-mini
```

- **"Base de conocimiento"** = el conjunto: el codigo que responde con las copias de las paginas de Shopify. Las
  paginas de Shopify son la fuente; `kb_contents` y Redis son copias.
- **Tabla fija de enlaces** (`localized_messages.py`, en produccion desde el 18/11): solo direcciones y titulos
  de enlace para el mensaje honesto; ningun dato de la tienda (lo protege un test). Lo peor que puede pasar es un
  enlace roto; un enlace que funciona lleva a la pagina en vivo, siempre al dia. **Un enlace es mas seguro que una
  copia.**
- **Mapa de la opcion C** (pospuesta, seccion 6): direcciones aprendidas de `kb_contents`; tampoco es contenido.
- `SimpleKnowledgeBase` (datos ficticios): el chat ya no la usa (R-2 parte 2) y la capa 4 esta apagada
  (`KB_ENABLE_FALLBACK=false`).

Evidencia de la sincronizacion [V, lectura de codigo y configuracion]: `KBBackgroundSyncJob` se arranca en cada
instancia (`main_unified_redis.py` L2133) con `KB_ENABLE_BACKGROUND_SYNC=true` e intervalo de 5 min (valores por
defecto de `config.py`); primer ciclo `sync_all_pages()` (completa), siguientes `sync_single_page()` por pagina
cambiada (`shopify_kb_sync.py` L1953-2081). `KB_WEBHOOKS_ENABLED=true` y hay 4 webhooks registrados, pero al
editar una pagina el 20/11 no llego ninguno y el propio job lo declara (`note=shopify_pages_webhooks_not_supported`)
[V]: las paginas solo se sincronizan por sondeo y al arrancar una instancia. Arranques de `00344-2f2` con
sincronizacion completa: 18/11 15:25, 19/11 07:02, 20/11 07:02, 16:08 y 18:07 UTC [V]. Una pagina sin cambios
solo actualiza `last_synced` (L1398). La sincronizacion completa invalida Redis por idioma (L768, L841); la
incremental (`sync_single_page`) **no lo invalidaba** (R-15) [V, codigo, 22/11]; corregido con R-13b el 23/11
(seccion 8). Redis es compartido entre instancias.

## 3. Mecanismos y huecos de frescura (estado 20/11/2026, actualizado 23/11)

| Mecanismo o hueco | Estado |
|---|---|
| Sincronizacion cada 5 min por instancia | Funciona [V] |
| Invalidacion de Redis al cambiar una pagina | **Corregido el 23/11** (R-15, incluido en R-13b, revision `00346-f5w`): la incremental invalida la clave de cada idioma que escribe [V, codigo y tests]; prueba de punta a punta en la seccion 8. Hasta entonces solo invalidaba la completa y el chat podia servir la version anterior hasta 24 h (correccion del 22/11: antes figuraba como "funciona") |
| R-13: el frances no se actualiza al editar una pagina | **Cerrado**: R-13a el 20/11 (seccion 7) y R-13b el 23/11, que usa los idiomas publicados en Shopify sin lista manual [V] (seccion 8) |
| R-12: si falta una traduccion, se guarda el texto en espanol | **Cerrado con R-13b** el 23/11: la fila no se escribe y se registra `kb_translation_missing` [V, tests] |
| Primeros minutos tras arrancar una instancia | Posible copia vieja hasta que acaba la sincronizacion completa [H] |
| Limite de antiguedad de la copia (`KB_BUFFER_MAX_AGE_HOURS=48`) | Al superarlo registra `kb_buffer_stale`; si la base de conocimiento tiene cliente de Shopify configurado sirve la copia igualmente (la capa de Shopify no esta implementada) y si no, no hay respuesta [V, codigo `knowledge_base_v2.py`, 22/11]. Cual de los dos casos se da en produccion: log de arranque `shopify_client_configured` [H] |
| Aviso si la sincronizacion falla repetidamente | Solo un log `kb_sync_cycle_failed` (ERROR); no se ha visto una alerta [H] |
| Reformulacion por GPT-4o-mini | Riesgo de afirmar algo que el documento no dice; solo un caso comprobado (PayPal) |
| R-10: politicas legales de Shopify con contenido de plantilla | Contenido de ejemplo en la demo [Y]; en una tienda real lo aporta la tienda. Ver inventario |
| R-14: las paginas de la base de conocimiento tienen contenido ficticio de plantilla | Contenido de ejemplo a proposito en la demo [Y]; el chat lo sirve tal cual [V]. Para tiendas reales: verificador de contenido por tienda (seccion 6). Inventario en `Inventario_Contenido_Plantilla_R10_R14_20112026.md` |

No es asesoria legal: la responsabilidad del contenido es de la tienda; lo que esta en nuestra mano es que el
sistema no se aparte de la fuente y que se pueda rastrear de donde sale cada respuesta.

## 4. Hallazgos nuevos

| Id | Hallazgo | Gravedad | Estado |
|---|---|---|---|
| R-13 | **El frances no se actualiza al editar una pagina**: la sincronizacion incremental (`sync_single_page`, L602) solo recorre los idiomas de `KB_SYNC_LANGUAGES`, que no esta en `env-vars.yaml`, asi que vale el valor por defecto `"es,en"` (L202). La sincronizacion completa, en cambio, escribe todas las traducciones publicadas, pero solo corre al arrancar una instancia. Una edicion llega al frances solo con el siguiente arranque [V]. Evidencia indirecta: las 3 filas de `unknown` (es/en/fr) tienen `last_synced` 20/11 07:02, la hora de una sincronizacion completa [V] [H: arranque de instancia] | Media (contenido desactualizado para clientes en frances) | Cerrado: R-13a (configuracion) el 20/11; R-13b (codigo) el 23/11 |
| R-14 | **Las paginas de la base de conocimiento tienen contenido ficticio de plantilla** (las que el chat sirve): correos de `tutienda.com`, telefonos `+1 (555) 123-4567`, `+1 (800) 555-0123` y `+52 55 1234 5678`, "Calle Principal 123", envios a EE. UU./Espana/Mexico (la tienda no envia a Mexico ni a America Latina), monedas USD/EUR/MXN (la tienda usa CLP, CHF, MXN), Apple Pay y Google Pay (no disponibles), RFC, "VIP Club", tarjetas regalo; y contradicciones entre paginas. Las traducciones copian lo mismo [V, Admin API 20/11]. Misma clase de riesgo que R-2, pero en la fuente de verdad | Baja en la demo (datos de ejemplo a proposito [Y]); requisito de producto para tiendas reales | Inventario en `Inventario_Contenido_Plantilla_R10_R14_20112026.md`; verificador de contenido por tienda (plan, punto 4) |
| R-15 | **La sincronizacion incremental no invalida Redis**: `sync_single_page()` escribe en `kb_contents` pero no llama a `_invalidate_cache()`, y el sondeo (`KBBackgroundSyncJob._run`, L2053) tampoco; solo lo hace la sincronizacion completa (`sync_page`, L768 y L841). El chat lee primero Redis (`knowledge_base_v2.py`, TTL 24 h), asi que una edicion detectada por el sondeo puede no llegar al cliente hasta 24 h o hasta el siguiente arranque [V, codigo]. El manejador de webhooks si invalida (SCAN+DELETE), pero Shopify no envia webhooks de paginas. La validacion de R-13a comprobo la escritura en `kb_contents`, no lo que sirve el chat. **Confirmado en produccion el 22/11** [V]: con la cache llena, se anadio "PRUEBA-R15" a la pagina oculta `mensaje-de-ayuda-general`; el sondeo la sincronizo (13:59:30 UTC, `00345-xd5`, 3 idiomas) y `/kb/answer?sub_intent=unknown&language=es` siguio sin "PRUEBA-R15"; edicion deshecha a las 14:06:29 UTC (Admin API). Que `kb_contents` tuviera el texto nuevo se deduce del codigo (el hash del contenido cambio) [H] | Media (contenido desactualizado tras editar) | Corregido con R-13b [Y, 22/11]; en produccion el 23/11 (seccion 8) |
| R-12 | Ampliado: con idiomas no publicados en `KB_SYNC_LANGUAGES`, `get_page_translations()` no los pide (`_get_shop_locales` solo devuelve los publicados) y `sync_single_page` (L613) escribiria el texto en espanol etiquetado como esos idiomas, solo para las paginas editadas [V, codigo] | Baja hoy; Media si se anaden idiomas a la variable | Cerrado con R-13b (23/11) |

Observaciones:
- Idiomas de la tienda (Admin API, 20/11) [V]: `es` (principal), `en` y `fr`, los tres publicados. `de`, `it` y
  `pt` no estan anadidos.
- `handle_page_webhook()` (L1553) llama a `self.sync_page(page_id)`, pero `sync_page` espera la pagina y sus
  metafields: lanzaria `TypeError` [V]. Los docstrings indican que los webhooks entran por `sync_single_page`, asi
  que seria codigo muerto [H]. Higiene, familia de R-9 (piezas de la base de conocimiento rotas o duplicadas).
- Cambiar solo una traduccion en Translate & Adapt quiza no cambia el `updated_at` de la pagina; el sondeo no la
  detectaria hasta el siguiente arranque [H]. Comprobar con R-13b.
- Un cambio solo de titulo no se guarda: la deteccion de cambios compara el hash del contenido Markdown, no el
  titulo (`_execute_upsert`, L1393-1414; solo actualiza `last_synced`) [V, codigo, 22/11]. Impacto bajo hoy (el
  chat responde con el contenido); relevante si la opcion C usa los titulos de `kb_contents`.
- El comentario de `_execute_upsert` (L1414) dice que una pagina sin cambios "sale ANTES de `_invalidate_cache` en
  `sync_page()`", pero `_upsert_kb_content` no devuelve nada y `sync_page()` invalida despues sin condicion (L768,
  L841) [V, codigo, 23/11]: cada sincronizacion completa vacia la cache de todas las paginas, cambien o no. Efecto:
  tras cada arranque, la primera consulta de cada tema va a PostgreSQL (milisegundos). Inocuo; corregir el
  comentario en un cambio de higiene.
- 23/11, logs del control positivo [V]: el arranque en frio de una instancia tardo ~110 s (la primera peticion,
  12:58:08 UTC, espero hasta `service_initialized` a las 12:59:44); con la tienda abierta, el primer cliente tras un
  periodo sin trafico esperaria ese tiempo. Tema ya estudiado en `CloudRun_MinInstances_Architecture_Analysis`;
  revisar antes de abrir la tienda. Fuera del alcance de este documento.
- 23/11, mismo arranque [V]: el log de configuracion de Redis muestra `SSL: False` con un host de Redis Cloud
  (`redislabs.com`): la conexion con la cache, contrasena incluida, no va cifrada [H: depende del plan de Redis
  Cloud y de la red]. Seguridad, fuera del alcance de este documento; anotado para la lista de pendientes.
- Respaldo de idioma de la base de conocimiento [V, codigo, 22/11]: si falta la fila pedida, `en` prueba `es`, y
  cualquier otro idioma prueba `es` y despues `en` (`knowledge_base_v2.py`, `get_answer`). Por eso R-13b puede no
  escribir una traduccion inexistente sin dejar al cliente sin respuesta.
- `Invoke-RestMethod` de Windows PowerShell 5.1 muestra mal los acentos de `/kb/answer` (lee la respuesta como
  Latin-1 si la cabecera no trae `charset`) [H]; un navegador la lee como UTF-8.
- 20/11 20:20: el disco del equipo de Yasmani se lleno (`ENOSPC` al escribir este documento) [V]. Yasmani libero
  12 GB (918,4 GB usados). El disco virtual de Docker Desktop (`docker_data.vhdx`) ocupa **647,6 GB** [V]: las
  imagenes construidas en local se acumulan y el disco virtual no se reduce solo. Limpiar y compactar antes del
  siguiente `docker build` (R-13b); R-13a no construye imagen.
- 21-22/11, limpieza de Docker [V]: dentro de Docker, de ~256 GB (33 imagenes, 74 contenedores, 134 GB de cache de
  construccion) a ~65 GB (6 imagenes); se conservan la imagen de produccion `:ef4b99c` y la de vuelta atras. La
  compactacion del `.vhdx` con diskpart (Docker cerrado, `wsl --shutdown`, consola de administrador) lo redujo de
  647,6 a **68,5 GB**; espacio libre en C: de 11 a **590,8 GB**. Un primer intento no compacto nada (Docker seguia en
  marcha) [H].

## 5. Decisiones

| Fecha | Decision | Evidencia |
|---|---|---|
| 19/11 | Tema `unknown` en el mensaje honesto -> `preguntas-frecuentes-faq`, como excepcion declarada [Y] | `kb_contents` tiene `mensaje-de-ayuda-general`, cuyo texto esta escrito para el chat [V] |
| 20/11 | Ocultar `mensaje-de-ayuda-general` en la tienda [Y] | Hecho a las 00:44 UTC: `isPublished=false` [V]. La sincronizacion no exige publicacion (`/pages.json` sin filtro; `published_status` vale `any` por defecto segun la documentacion de Shopify) [V]; tras ocultarla, `last_synced` 20/11 07:02 en es/en/fr y `/kb/answer?sub_intent=unknown` sigue sirviendo el texto en es/en [V] |
| 20/11 | R-13a: `KB_SYNC_LANGUAGES: "es,en,fr"` [Y] | Coincide con los idiomas publicados [V] |
| 20/11 | Propuesta `"es,en,fr,de,it,pt"` descartada por ahora [Y] | `de`/`it`/`pt` no existen en Shopify: se guardaria texto en espanol con esas etiquetas (R-12) [V]. Camino correcto para Suiza: anadir y traducir `de`/`it` en Translate & Adapt, publicarlos y que R-13b los recoja solo |
| 20/11 | `pt` fuera de alcance por ahora (criterio delegado en Claude) [Y] | Ni Chile ni Suiza lo necesitan; no esta en Shopify; exigiria textos aprobados (`SUPPORTED_LANGUAGES` es es/en/fr/de/it). Reconsiderar si aparecen clientes en portugues |
| 20/11 | Nuevo orden de prioridades (seccion 6) [Y] | Clientes afectados x consecuencia |
| 22/11 | Orden del plan revisado confirmado [Y] | - |
| 22/11 | R-13b: idiomas = publicados en Shopify y se retira `KB_SYNC_LANGUAGES`; si falta una traduccion publicada, no se escribe la fila y se registra un aviso; si una traduccion desaparece, no se borra la fila (solo aviso); la alerta de sincronizacion fallida va aparte [Y] | `get_page_translations()` devuelve `{}` tanto si no hay traduccion como si falla la llamada: borrar seria peligroso [V, codigo] |
| 20/11 | El contenido de la demo (paginas y politicas) es de ejemplo a proposito; no se corrige ahora [Y] | Cada tienda cliente aporta el suyo; el inventario queda como caso de prueba y lista de incorporacion |
| 20/11 | Opcion C: el enlace de respaldo no debe prometer que la respuesta esta en preguntas frecuentes (observacion de Yasmani) | Propuesta pendiente de decidir: "Puedes revisar nuestras paginas de ayuda en el [Centro de ayuda](...) o [contactarnos](...)". Centro de ayuda: pagina nueva mantenida en Shopify, o el buscador de la tienda limitado a paginas [H: verificar que Shopify lo admite]. Handle de "Contact" por verificar [H] |

## 6. Plan, en orden

1. ~~**R-13a**~~ (el frances no se actualiza al editar una pagina; configuracion): **hecho** 20/11/2026, revision
   `00345-xd5`. Seccion 7.
Orden de los puntos 2 a 4 revisado el 20/11 tras la aclaracion sobre la demo (propuesta de Claude, pendiente de
confirmar [Y]):

2. ~~**R-13b + R-15**~~ (la sincronizacion incremental usa los idiomas publicados en Shopify y vacia la cache de
   Redis al escribir; codigo): **desplegado y validado** el 23/11/2026, revision `00346-f5w`, commit `8ebc527`
   (en GitHub). Seccion 8.
   La alerta de sincronizacion fallida va aparte (decision 22/11).
3. **Fidelidad de la reformulacion**: conjunto de preguntas con respuesta conocida; comprobar que GPT-4o-mini no
   afirma nada que el documento no diga. Es responsabilidad directa del sistema, sea cual sea la tienda.
   **En curso** desde el 23/11: `DCT_Fidelidad_Reformulacion_KB_23112026.md` (hallazgos R-16 a R-19 y plan).
4. **Verificador de contenido por tienda y lista de incorporacion** (producto; R-10 y R-14 como caso de prueba):
   detectar contenido de plantilla e incoherencias con la configuracion de la tienda antes de activar el chat.
5. **Opcion C** (enlaces del mensaje honesto desde `kb_contents`; diseno en el DCT anterior, seccion 12, ajustado
   el 20/11: refresco al final de cada ciclo de sincronizacion con cambios, ultimo valor bueno en memoria, y al
   caer a la pagina de respaldo cambian a la vez direccion y titulo). Texto del respaldo pendiente (seccion 5).
6. **R-8 y R-11** (modelos LFM retirados; respaldo Claude con modelos retirados): identificadores de modelo a
   configuracion y decision de producto.

## 7. R-13a: procedimiento y validacion

Cambio: 5 lineas al final de `env-vars.yaml` (4 de comentario y `KB_SYNC_LANGUAGES: "es,en,fr"`). Misma imagen
(`sha256:5fe2ccbb...`, etiqueta `:ef4b99c`); despliegue solo de configuracion con
`gcloud run services update --env-vars-file`.

Linea base (mismo dia) y criterios:

| Comprobacion | Antes (esperado) | Despues (esperado) |
|---|---|---|
| Variables de entorno de la revision | 49 (38 planas + 11 secretas) | 50 (39 + 11) |
| Imagen | `5fe2ccbb...` | la misma |
| `service_initialized` de `ShopifyKBSyncService`, campo `configured_languages` | `[es, en]` | `[es, en, fr]` en la revision nueva |
| `sync_single_page_language_synced` al editar una pagina | solo `es` y `en` | `es`, `en` y `fr` |
| `/kb/answer?sub_intent=policy_return` en es/en/fr | 200 | 200 |
| `ERROR` tras el despliegue | 0 | 0 |

Prueba funcional: editar el titulo de la pagina oculta `mensaje-de-ayuda-general` (anadir " (prueba)"), comprobar
los logs de sincronizacion y deshacer la edicion. Pagina oculta: sin efecto para clientes.

Vuelta atras: `gcloud run services update-traffic retail-recommender --region us-central1
--to-revisions=retail-recommender-00344-2f2=100`, y despues `--to-latest` cuando se corrija (`--no-traffic` y
`--to-revisions` dejan el trafico fijado; leccion del 18/11).

Resultados (20/11/2026) [V]. Commits `fd6f458` (documentacion) y `441692e` (`env-vars.yaml`):

| Comprobacion | Antes | Despues |
|---|---|---|
| Revision | `00344-2f2` | `00345-xd5`, 100 %, sigue a la ultima |
| Imagen | `5fe2ccbb...` | la misma |
| Variables (secretas) | 49 (11) | 50 (11); `KB_SYNC_LANGUAGES=es,en,fr` |
| `configured_languages` en `service_initialized` | `['es', 'en']` en los 5 arranques del 18 al 20/11 | `['es', 'en', 'fr']` (20:41:42 UTC) |
| `sync_single_page_language_synced` en 7 dias | ninguno (sin ediciones con una instancia viva) | prueba funcional: `es`, `en` y `fr` |
| `/kb/answer?sub_intent=policy_return` | - | es/en/fr -> 200 (487 / 430 / 500 bytes) |
| `ERROR` | - | 0 en 30 min (y 0 en los 617 eventos descargados, 20:40-20:52 UTC) |

Prueba funcional (logs descargados) [V]: titulo de `mensaje-de-ayuda-general` cambiado a " (prueba)"; el ciclo
incremental 3 (20:51:54 UTC) detecto 1 pagina cambiada (`158935941429`) y la sincronizo en `es`, `en` y `fr`
(`status=synced`, 0 errores). Ciclo 2 (20:46:54) sin cambios. El titulo se restauro a las 20:52:07 UTC (Admin
API) [V] y la restauracion se sincronizo en el ciclo siguiente (20:56:58 UTC, 3 idiomas) [V]. La consulta del
terminal salio vacia porque se ejecuto antes del ciclo 3 [H: por la hora].

Incidencias:
- `numstat` de `env-vars.yaml` 5/1 en vez de 5/0: la linea borrada es la linea en blanco final [V: `git show
  441692e` muestra una sola linea `-` vacia; las 39 claves y `KB_ENABLE_FALLBACK: "false"` siguen].
- Push del 20/11: `72062e3..d46f16e` (commits `fd6f458`, `441692e` y `d46f16e`) [V].
- La linea de vuelta atras se ejecuto sin que hiciera falta y fallo antes de llamar a la API: `$r` (respuesta de
  `Invoke-WebRequest`) piso `$R` (region) porque en PowerShell las variables no distinguen mayusculas. Error de
  diseno del bloque (Claude) [V]. Produccion no cambio: `00345-xd5` 100 %, sigue a la ultima [V].
- El nombre `00345` se repite (`00345-wub` de la prueba del 18/11 y `00345-xd5`) [V]: el numero no es una
  secuencia unica; identificar revisiones por nombre completo y fecha.
- El comentario de R-13a en `env-vars.yaml` dice "cada 5 min y webhooks": los webhooks de paginas no existen.
  Se corrige al retirar la variable en R-13b.

## 8. R-13b + R-15: procedimiento y validacion

Cambio, commit `8ebc527` (4 ficheros, +385/-34) [V]:
- `shopify_kb_sync.py`, `sync_single_page()`: sincroniza el idioma base y los idiomas **publicados** en Shopify
  (se retira `KB_SYNC_LANGUAGES`). Si falta una traduccion publicada, no escribe la fila y registra
  `kb_translation_missing`; una fila anterior de ese idioma se conserva. Si Shopify no responde al pedir los
  idiomas, sincroniza solo el idioma base y avisa (`sync_single_page_locales_fetch_failed`). Tras cada escritura
  invalida la clave de Redis de ese idioma (R-15); un fallo de Redis solo avisa
  (`sync_single_page_cache_invalidation_failed`) y no anula la escritura. El resultado y el log anaden
  `languages_skipped`; el log de arranque cambia `configured_languages` por `language_source`.
- `shopify_kb_client.py`: metodo publico `get_translation_locales()` (misma fuente y cache de 1 h que la
  sincronizacion completa; no se traga los errores).
- `env-vars.yaml`: retirada `KB_SYNC_LANGUAGES` (38 variables planas + 11 secretas = 49).
- `tests/unit/test_sync_single_page_languages.py`: 16 tests nuevos, con control negativo (fallan con el codigo
  anterior).

Laboratorio y aplicacion: paquete `R13b_patch.zip` (SHA-256 `D6B5B80D...02E52CCB`) que clasifica cada fichero
como BASE / YA APLICADO / OTRO y verifica los hashes antes y despues de escribir; 136 tests pasados en el venv de
Yasmani [V]. Imagen construida en local (24 min; un primer intento fallo por red al pedir el token de Docker Hub)
y desplegada con `gcloud run services update --image <digest> --env-vars-file env-vars.yaml`, que conserva los
11 secretos.

Resultados (23/11/2026) [V]:

| Comprobacion | Antes | Despues |
|---|---|---|
| Revision | `00345-xd5` | `00346-f5w`, 100 %, sigue a la ultima |
| Imagen | `:ef4b99c` (`sha256:5fe2ccbb...`) | `:8ebc527` (`sha256:b4362574...f42df3e242`) |
| Variables (secretas) | 50 (11) | 49 (11); `KB_SYNC_LANGUAGES` ausente |
| Log de arranque de `ShopifyKBSyncService` | `configured_languages=['es','en','fr']` | `language_source=shopify_published_locales` |
| `/kb/answer?sub_intent=policy_return` es/en/fr | 200 | 200 |
| `ERROR` tras el despliegue | 0 | 0 |
| Edicion de prueba (sincronizacion incremental) | - | es/en/fr, `languages_skipped=[]`, 0 errores |

Prueba de punta a punta de R-15 (prueba D), con la pagina oculta `mensaje-de-ayuda-general` (tema `unknown`) y
logs de peticion (`kb_answer_request`, `kb_cache_hit`, `kb_buffer_hit`) [V]. Instancias A (`...bd55f9`) y B
(`...bdc123`), ambas de `00346-f5w`:

| Hora UTC | Instancia | Paso |
|---|---|---|
| 00:57:50 | A | Arranque y sincronizacion completa |
| 01:03:09 | A | D1: consulta `unknown`/es -> `kb_buffer_hit` (PostgreSQL), que la guarda en Redis |
| entre D1 y 01:08 | - | D2: se anade "PRUEBA-R15" a la pagina |
| 01:08:01 | A | Ciclo incremental 3: sincroniza la pagina en es/en/fr, `languages_skipped=[]` |
| 01:21:52 | **B, nueva** | Arranque; sincronizacion completa de 01:21:54 a 01:22:03 |
| 01:22:01 | B | D3: consulta -> `kb_buffer_hit`; respuesta con "PRUEBA-R15" |
| 01:23:27 | - | D4: edicion deshecha (`updatedAt` de la Admin API) |
| 01:27:05 | B | Ciclo incremental 2: sincroniza la reversion en 3 idiomas |
| 01:31:41 | B | D5: consulta -> `kb_buffer_hit`; respuesta sin "PRUEBA-R15" |

Ninguna consulta encontro la clave en Redis: en las tres falto el `kb_cache_hit`. Antes de R-15 (22/11,
`00345-xd5`) la misma prueba sirvio la version vieja [V].

Atribucion. La instancia B arranco en mitad de la prueba [H: la desperto D3, 15 min despues de la ultima
peticion a A], y su sincronizacion completa tambien vacia la cache, asi que el resultado no basta por si solo. D3
cayo dentro de esa sincronizacion. El dato que decide es cuando invalido la completa la clave
`kb:unknown:es:general` (log `page_default_language_synced` con `sub_intent=unknown`, emitido justo despues de
invalidar, L768-777):
- **Antes de D3**: D3 guardo en Redis la version con "PRUEBA-R15" y nada mas que el ciclo incremental de 01:27:05
  pudo borrarla antes de D5. Prueba R-15 el tramo de la reversion.
- **Despues de D3**: en D3 la clave ya faltaba sin que la completa la hubiera tocado; solo el ciclo incremental de
  01:08:01 pudo borrar la que guardo D1 (TTL 24 h). Prueba R-15 el tramo de la edicion.
- Solo quedaria sin probar si la invalidacion cayo en los ~100 ms entre la peticion D3 y su lectura.

Ademas hace falta un control positivo: que la cache funcione en `00346-f5w` (una segunda consulta identica debe
dar `kb_cache_hit`). Sin el, faltar el acierto de cache no prueba nada.

Resultado de la primera consulta (23/11) [V]: la sincronizacion completa de B registro
`page_default_language_synced` de la pagina `158935941429` (`unknown`, es) a las **01:21:58.32**, 3,5 s **antes**
de D3. Entre D3 (01:22:01.88, que guardo en Redis la version con "PRUEBA-R15") y D5 (01:31:41) no arranco
ninguna instancia y la pagina no tiene webhooks: lo unico que borro la clave es el ciclo incremental de las
01:27:05. **El tramo de la reversion prueba R-15**, a falta del control positivo de la cache. Descartado sin
prueba directa: desalojo de la clave por memoria de Redis [H: improbable con una clave de <1 KB].

Control positivo de la cache (23/11, revision `00346-f5w`, instancia `...cb16c7`) [V]: dos consultas identicas a
`/api/v1/kb/answer?sub_intent=policy_return&language=es`; la primera (13:09:41 UTC) `kb_buffer_hit`, 440 ms; la
segunda (13:10:05 UTC) **`kb_cache_hit`**, 11 ms. Redis guarda y sirve respuestas en esta revision. Un primer
intento devolvio 404 porque la ruta del comando estaba mal (`/kb/answer` en lugar de `/api/v1/kb/answer`; error de
Claude) [V: la peticion D5 del Logs Explorer muestra la ruta completa].

**Atribucion cerrada (23/11) [V]: R-15 funciona en produccion.** La sincronizacion incremental de las 01:27:05
borro la clave que D3 habia guardado, y D5 sirvio el contenido revertido. Con esto se da por validado R-13b + R-15.
El `git push` del 23/11 respondio `Everything up-to-date`: `8ebc527` ya estaba en GitHub (subido antes del cierre
de esta validacion) [V: `origin/feature/visual_search` = `8ebc527`].

Vuelta atras: `gcloud run services update-traffic retail-recommender --project retail-recommendations-449216
--region us-central1 --to-revisions=retail-recommender-00345-xd5=100` (esa revision conserva
`KB_SYNC_LANGUAGES=es,en,fr`), y `--to-latest` cuando se corrija.

## 9. Lecciones

- **La lista escrita a mano es un patron que se repite**: tabla de handles (opcion C), `KB_SYNC_LANGUAGES`
  (R-13) y modelos fijos en `claude_config.py` (R-8, R-11). Preguntarse: este valor lo decido yo (configuracion)
  o lo copio de otro sistema (leerlo de ese sistema, con respaldo y aviso de desfase)?
- **Un enlace es mas seguro que una copia**: la copia puede quedarse vieja; el enlace lleva a la fuente.
- **Priorizar por clientes afectados x consecuencia**: el camino normal pesa mas que el degradado una vez
  retirado el contenido ficticio.
- **Separar quien lee un dato y por que camino**: el sistema lee las paginas por la API de administracion y el
  publico por la tienda; la visibilidad de una pagina se puede cambiar sin afectar a la sincronizacion.
- **Bloques de comandos autosuficientes**: un bloque que usa variables de otra sesion falla con errores enganosos
  (`C:\check_kb_links.py`); cada bloque define lo que usa.
- **En PowerShell `$r` y `$R` son la misma variable**: usar nombres largos y distintos (`$region`, `$resp`) y no
  reutilizar nombres cortos en bucles.
- **La vuelta atras no va en el bloque lineal**: los comandos condicionales se dan aparte o protegidos por una
  condicion (`if (...) { ... }`), para que copiar el bloque entero no los ejecute.
- **Un resultado vacio puede ser un problema de tiempo**: la prueba funcional dependia de un ciclo de 5 minutos;
  la consulta debe esperar al ciclo (o buscar el evento del ciclo) antes de concluir.
- **Confirmar el contexto antes de clasificar la gravedad**: el contenido de plantilla se trato como un riesgo
  legal de la tienda hasta que Yasmani aclaro que es una demo con datos de ejemplo. El mismo hallazgo pasa de
  "corregir antes de abrir" a "requisito de producto" (verificador de contenido por tienda).
- **Verificar el efecto, no solo el mecanismo**: la validacion de R-13a comprobo la escritura en `kb_contents`, no
  lo que sirve el chat; por eso R-15 paso inadvertido dos dias. La prueba de cierre debe mirar lo que ve el cliente.
- **En un servicio con escalado automatico, la instancia es una variable del experimento**: cada arranque ejecuta
  su propio codigo de inicio (aqui, una sincronizacion completa que vacia la cache). Registrar `labels.instanceId`
  en cada paso y, si la prueba es larga, mantener la instancia despierta con una peticion ligera cada pocos minutos.
- **Una prueba con ida y vuelta da dos oportunidades**: si un evento externo contamina un tramo (edicion), el otro
  (reversion) puede aislar el efecto.
- **Un control positivo antes de interpretar una ausencia**: "no hubo acierto de cache" solo prueba algo si la
  cache funciona.
- **Los comentarios tambien pueden estar equivocados**: el de L1414 describe un comportamiento que el codigo no
  tiene. Verificar el flujo real antes de apoyarse en un comentario.
- **Dar las horas con su zona y comprobar la de la herramienta**: el Logs Explorer muestra la hora local (CET,
  UTC+1); las horas de este documento son UTC. Buscar "01:22" en la vista CET lleva a las 00:22 UTC, donde no
  hubo actividad. Poner el selector de zona del Logs Explorer en UTC al contrastar con documentos.
- **Copiar las rutas de la evidencia, no de la abreviatura del documento**: el documento escribia `/kb/answer`
  como abreviatura y el comando la tomo como ruta real (404). La ruta exacta estaba en los logs de peticion.
