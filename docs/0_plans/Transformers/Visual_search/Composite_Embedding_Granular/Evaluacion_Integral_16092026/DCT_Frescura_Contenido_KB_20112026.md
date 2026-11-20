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
esta expuesto todavia. Este documento es la lista de lo que hay que cerrar antes de abrir.

## 2. Como llega el contenido al cliente (glosario)

```
 Shopify: paginas + traducciones (Translate & Adapt)    <- FUENTE DE VERDAD (la edita la tienda)
     |  sincronizacion por instancia de Cloud Run:
     |    - completa al arrancar (todas las traducciones publicadas)
     |    - incremental cada 5 min y por webhook (solo paginas cambiadas, idiomas de KB_SYNC_LANGUAGES)
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
cambiada (`shopify_kb_sync.py` L1953-2081). `KB_WEBHOOKS_ENABLED=true` en `env-vars.yaml`; segun los docstrings,
el webhook tambien entra por `sync_single_page()` [H]. Una pagina sin cambios solo actualiza `last_synced`
(L1398) y una con cambios invalida Redis, que es compartido entre instancias.

## 3. Mecanismos y huecos de frescura (estado 20/11/2026)

| Mecanismo o hueco | Estado |
|---|---|
| Sincronizacion cada 5 min por instancia | Funciona [V] |
| Invalidacion de Redis al cambiar una pagina | Funciona [V, codigo]; Redis compartido |
| R-13: el frances no se actualiza al editar una pagina | **Hueco** [V]; R-13a lo cierra para es/en/fr (seccion 7) |
| R-12: si falta una traduccion, se guarda el texto en espanol | Idioma equivocado, no informacion vieja [V]; lo cierra R-13b |
| Primeros minutos tras arrancar una instancia | Posible copia vieja hasta que acaba la sincronizacion completa [H] |
| Limite de antiguedad de la copia (`KB_BUFFER_MAX_AGE_HOURS=48`) | Configurado; comportamiento al superarlo no verificado [H] |
| Aviso si la sincronizacion falla repetidamente | Solo un log `kb_sync_cycle_failed` (ERROR); no se ha visto una alerta [H] |
| Reformulacion por GPT-4o-mini | Riesgo de afirmar algo que el documento no dice; solo un caso comprobado (PayPal) |
| R-10: politicas legales de Shopify con contenido de plantilla | **Mayor riesgo legal hoy**, fuera del codigo: reembolso 10 dias (Shopify) frente a 5-7 (base de conocimiento) |

No es asesoria legal: la responsabilidad del contenido es de la tienda; lo que esta en nuestra mano es que el
sistema no se aparte de la fuente y que se pueda rastrear de donde sale cada respuesta.

## 4. Hallazgos nuevos

| Id | Hallazgo | Gravedad | Estado |
|---|---|---|---|
| R-13 | **El frances no se actualiza al editar una pagina**: la sincronizacion incremental (`sync_single_page`, L602) solo recorre los idiomas de `KB_SYNC_LANGUAGES`, que no esta en `env-vars.yaml`, asi que vale el valor por defecto `"es,en"` (L202). La sincronizacion completa, en cambio, escribe todas las traducciones publicadas, pero solo corre al arrancar una instancia. Una edicion llega al frances solo con el siguiente arranque [V]. Evidencia indirecta: las 3 filas de `unknown` (es/en/fr) tienen `last_synced` 20/11 07:02, la hora de una sincronizacion completa [V] [H: arranque de instancia] | Media (contenido desactualizado para clientes en frances) | R-13a (configuracion) en curso; R-13b (codigo) planificado |
| R-12 | Ampliado: con idiomas no publicados en `KB_SYNC_LANGUAGES`, `get_page_translations()` no los pide (`_get_shop_locales` solo devuelve los publicados) y `sync_single_page` (L613) escribiria el texto en espanol etiquetado como esos idiomas, solo para las paginas editadas [V, codigo] | Baja hoy; Media si se anaden idiomas a la variable | Lo cierra R-13b |

Observaciones:
- Idiomas de la tienda (Admin API, 20/11) [V]: `es` (principal), `en` y `fr`, los tres publicados. `de`, `it` y
  `pt` no estan anadidos.
- `handle_page_webhook()` (L1553) llama a `self.sync_page(page_id)`, pero `sync_page` espera la pagina y sus
  metafields: lanzaria `TypeError` [V]. Los docstrings indican que los webhooks entran por `sync_single_page`, asi
  que seria codigo muerto [H]. Higiene, familia de R-9 (piezas de la base de conocimiento rotas o duplicadas).
- Cambiar solo una traduccion en Translate & Adapt quiza no cambia el `updated_at` de la pagina; el sondeo no la
  detectaria hasta el siguiente arranque [H]. Comprobar con R-13b.
- `Invoke-RestMethod` de Windows PowerShell 5.1 muestra mal los acentos de `/kb/answer` (lee la respuesta como
  Latin-1 si la cabecera no trae `charset`) [H]; un navegador la lee como UTF-8.
- 20/11 20:20: el disco del equipo de Yasmani se lleno (`ENOSPC` al escribir este documento) [V]. Yasmani libero
  12 GB (918,4 GB usados). El disco virtual de Docker Desktop (`docker_data.vhdx`) ocupa **647,6 GB** [V]: las
  imagenes construidas en local se acumulan y el disco virtual no se reduce solo. Limpiar y compactar antes del
  siguiente `docker build` (R-13b); R-13a no construye imagen.

## 5. Decisiones

| Fecha | Decision | Evidencia |
|---|---|---|
| 19/11 | Tema `unknown` en el mensaje honesto -> `preguntas-frecuentes-faq`, como excepcion declarada [Y] | `kb_contents` tiene `mensaje-de-ayuda-general`, cuyo texto esta escrito para el chat [V] |
| 20/11 | Ocultar `mensaje-de-ayuda-general` en la tienda [Y] | Hecho a las 00:44 UTC: `isPublished=false` [V]. La sincronizacion no exige publicacion (`/pages.json` sin filtro; `published_status` vale `any` por defecto segun la documentacion de Shopify) [V]; tras ocultarla, `last_synced` 20/11 07:02 en es/en/fr y `/kb/answer?sub_intent=unknown` sigue sirviendo el texto en es/en [V] |
| 20/11 | R-13a: `KB_SYNC_LANGUAGES: "es,en,fr"` [Y] | Coincide con los idiomas publicados [V] |
| 20/11 | Propuesta `"es,en,fr,de,it,pt"` descartada por ahora [Y] | `de`/`it`/`pt` no existen en Shopify: se guardaria texto en espanol con esas etiquetas (R-12) [V]. Camino correcto para Suiza: anadir y traducir `de`/`it` en Translate & Adapt, publicarlos y que R-13b los recoja solo |
| 20/11 | `pt` fuera de alcance por ahora (criterio delegado en Claude) [Y] | Ni Chile ni Suiza lo necesitan; no esta en Shopify; exigiria textos aprobados (`SUPPORTED_LANGUAGES` es es/en/fr/de/it). Reconsiderar si aparecen clientes en portugues |
| 20/11 | Nuevo orden de prioridades (seccion 6) [Y] | Clientes afectados x consecuencia |
| 20/11 | Opcion C: el enlace de respaldo no debe prometer que la respuesta esta en preguntas frecuentes (observacion de Yasmani) | Propuesta pendiente de decidir: "Puedes revisar nuestras paginas de ayuda en el [Centro de ayuda](...) o [contactarnos](...)". Centro de ayuda: pagina nueva mantenida en Shopify, o el buscador de la tienda limitado a paginas [H: verificar que Shopify lo admite]. Handle de "Contact" por verificar [H] |

## 6. Plan, en orden

1. **R-13a** (el frances no se actualiza al editar una pagina; configuracion): `KB_SYNC_LANGUAGES: "es,en,fr"`. Seccion 7.
2. **R-10** (politicas legales de Shopify con contenido de plantilla): alinear las politicas con la base de
   conocimiento. Yasmani, en Shopify, sin codigo.
3. **R-13b** (codigo, laboratorio primero): la sincronizacion incremental usa los idiomas publicados en Shopify,
   como la completa, y solo escribe las traducciones que existen (cierra tambien R-12); se retira
   `KB_SYNC_LANGUAGES`. Anadir aqui una alerta si la sincronizacion falla repetidamente.
4. **Fidelidad de la reformulacion**: conjunto de preguntas con respuesta conocida; comprobar que GPT-4o-mini no
   afirma nada que el documento no diga.
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

Resultados: **pendiente**.

## 8. Lecciones

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
