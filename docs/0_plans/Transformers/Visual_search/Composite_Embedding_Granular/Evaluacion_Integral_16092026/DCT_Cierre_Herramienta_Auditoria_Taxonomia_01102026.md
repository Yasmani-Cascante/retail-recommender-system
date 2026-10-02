# DCT — Cierre: Herramienta de Auditoría de Taxonomía de Catálogo

**Fecha de cierre:** 1 de octubre de 2026
**Alcance de este documento:** `taxonomy_centroid_audit.py` (script completo, raíz del repo) — sus tres motivos de auditoría, y en particular el chequeo de texto automático que completa el Motivo 3 (mistagging).
**Audiencia:** este documento está escrito para dos lectores distintos a la vez — quien necesite entender **qué hace la herramienta y por qué importa** sin leer código, y quien necesite **mantenerla o extenderla** con precisión técnica. Las secciones 1-5 y 10-11 priorizan lo primero; las secciones 6-9 y 12-13 priorizan lo segundo.
**Documentos relacionados:** `DCT_Cierre_Fase2_Unificacion_Taxonomia_27092026.md` (mismo directorio, secciones 7.4 a 7.8) tiene la cronología completa de cómo se construyó esto, incluyendo una saga real de depuración de autenticación en la nube que vale la pena leer si algo similar vuelve a fallar.

---

## 1. Resumen ejecutivo

El catálogo de la tienda tiene 3045 productos, cada uno con una categoría asignada a mano en Shopify (vestido, aros, cartera, etc.). Esa categoría no es solo una etiqueta administrativa — el motor de recomendaciones de IA la usa activamente para decidir qué sugerir a cada cliente. Si un producto tiene la categoría equivocada, el sistema puede recomendarlo en el contexto incorrecto, o dejar de recomendarlo donde sí correspondería.

Construimos una herramienta que revisa el catálogo completo de tres formas distintas y automáticas, y que además compara cada producto sospechoso contra sí mismo en dos dimensiones — cómo se ve, y qué dice su propio nombre — para separar los errores reales de la simple variedad visual normal. En su versión final, de 3045 productos, la herramienta señala exactamente **1** para que alguien lo revise, con el resto ya auto-confirmado como correcto. Ese único caso, verificado directamente en Shopify, resultó ser un problema real y genuino: un producto con información contradictoria entre sí.

La herramienta ya encontró y permitió corregir un error real de categorización en el catálogo de producción antes de este cierre ("Body Renata Negro", categorizado como sostén cuando en realidad es un body).

---

## 2. Objetivo

Detectar, de forma automática y periódica, tres tipos de problemas en la categorización del catálogo que antes solo se descubrían por casualidad:

1. Categorías que existen en el catálogo real pero que el sistema de recomendaciones no conoce.
2. Categorías que el sistema conoce pero que ya no existen en el catálogo (código obsoleto).
3. Productos a los que, por error humano al cargarlos en Shopify, se les asignó la categoría equivocada.

---

## 3. Qué hemos implementado y por qué

Un script independiente (`taxonomy_centroid_audit.py`) que se corre manualmente cuando se quiere auditar el catálogo — no es parte del flujo de atención a clientes, no afecta la velocidad ni el comportamiento del chat en vivo.

**Por qué como script separado y no integrado al sistema en vivo:** la auditoría no necesita correr en cada conversación — necesita correr periódicamente (cuando se sospecha un problema, o como chequeo de rutina). Meterlo en el camino de atención a clientes agregaría complejidad y riesgo a un sistema que ya funciona, sin ningún beneficio para el cliente final.

**Por qué el tercer motivo (mistagging) tardó más en construirse:** necesitaba acceso a los "embeddings" visuales de cada producto — una representación numérica de su foto, que ya calculábamos para otra función del sistema (la búsqueda por imagen) pero que nunca habíamos expuesto para que algo externo pudiera leerla. Hubo que construir esa puerta de acceso nueva, en el propio servicio que ya genera esos datos.

---

## 4. Problema que resuelve

**El problema concreto:** un producto cargado con la categoría equivocada en Shopify no se nota a simple vista en una tienda de miles de productos — pero sí afecta, de forma silenciosa, la calidad de las recomendaciones que el sistema de IA ofrece a los clientes (sugerencias de "completa tu outfit" incorrectas, búsquedas visuales que devuelven resultados extraños, filtros de categoría que no encuentran lo que deberían).

**Por qué no se detectaba antes:** nadie puede revisar 3045 productos uno por uno de forma rutinaria. El único mecanismo previo era la casualidad — alguien notando, mientras probaba otra cosa, que un producto se veía raro en un resultado.

---

## 5. Cómo funciona la solución

En términos simples, la herramienta hace tres preguntas distintas sobre el mismo catálogo:

1. **"¿Qué categorías existen de verdad?"** — cuenta, sin adivinar, todas las categorías reales y cuántos productos tiene cada una.
2. **"¿El sistema conoce todas esas categorías?"** — compara esa lista real contra las dos listas de referencia que usa el motor de recomendaciones, y señala cualquier diferencia en cualquiera de las dos direcciones.
3. **"¿Hay productos con la categoría equivocada?"** — para cada categoría, calcula "cómo se ve, en promedio, un producto típico de este tipo" a partir de sus fotos, y mide qué tan lejos está cada producto individual de ese promedio. Antes de molestar a una persona con la lista de sospechosos, la herramienta misma revisa el título y las etiquetas de cada uno — si el texto confirma la categoría, lo descarta como "simplemente una foto poco común"; si no, lo deja como pendiente de revisión real.

---

## 6. Flujo de ejecución

```
1. Cargar .env (variables de configuración, incluida la URL del servicio de IA visual)
2. Leer tfidf_model.pkl (la fotografía más reciente del catálogo de Shopify)
3. MOTIVO 1 — contar categorías reales
4. MOTIVO 2 — comparar contra las fuentes de referencia del sistema
5. MOTIVO 3:
   a. Pedir al servicio de IA visual los embeddings de todos los productos indexados
   b. Agrupar por categoría declarada
   c. Calcular el "promedio visual" (centroide) de cada categoría
   d. Medir qué tan lejos está cada producto de ese promedio
   e. Para los que se alejan demasiado: comparar su título/etiquetas contra su categoría
   f. Separar en dos listas: "revisar de verdad" vs. "probablemente solo raro visualmente"
6. Imprimir el reporte completo
```

---

## 7. Principales componentes involucrados

| Componente | Rol |
|---|---|
| `taxonomy_centroid_audit.py` (raíz del repo) | El script en sí — orquesta los tres motivos |
| `tfidf_model.pkl` | La fotografía del catálogo que el script lee (no una llamada en vivo a Shopify) |
| `src/recommenders/product_taxonomy.py` | Una de las dos fuentes de referencia que se audita en el Motivo 2 |
| `src/recommenders/improved_fallback_exclude_seen.py` | La otra fuente de referencia (Motivo 2), y la función reutilizada para el chequeo de texto del Motivo 3 |
| `src/api/services/colbert_client.py` | El cliente, dentro del monolito, que le pide los embeddings al servicio de IA visual |
| `src/api/services/embedding-service/` (`main.py`, `visual_retriever.py`) | El servicio de IA visual en sí — aquí vive el modelo que generó los embeddings y el índice donde están guardados |
| `env_loader.py` | Utilitario del repo que carga las variables de configuración cuando el script corre de forma independiente |

---

## 8. Datos de entrada y fuentes de datos

| Dato | De dónde viene | Cómo llega al script |
|---|---|---|
| Categoría declarada de cada producto (`product_type`) | Shopify | Vía `tfidf_model.pkl` — una sincronización periódica, no una llamada en vivo durante la ejecución |
| Título y etiquetas de cada producto | Shopify | Igual que arriba, mismo pickle |
| Embeddings visuales (representación numérica de la foto) | Calculados a partir de las fotos de Shopify, en un momento anterior, por el modelo de IA visual (FashionSigLIP) | Pedidos en vivo al servicio de IA visual, durante la ejecución del script |
| Listas de referencia de categorías | Código del propio repo (`product_taxonomy.py`, `improved_fallback_exclude_seen.py`) | Importadas directamente, no vienen de Shopify |

---

## 9. Integración/dependencias con Shopify

La herramienta **no llama a la API de Shopify directamente** durante su ejecución — todo lo que "viene de Shopify" llega indirectamente, a través de una fotografía (`tfidf_model.pkl`) generada por el proceso normal de sincronización del catálogo. Esto tiene una consecuencia práctica importante: **si se corrige un producto en Shopify Admin, ese cambio no se refleja en la siguiente corrida del script hasta que el pickle se regenere.** Ya ocurrió exactamente esto durante esta misma iniciativa — una corrección real en Shopify no se vio reflejada hasta regenerar el pickle, y el script, al no tener forma de saberlo, mostró el mismo resultado de antes.

Campos exactos de Shopify utilizados (vía el pickle): `id`, `product_type`, `title`, `tags`.

La verificación manual de candidatos (no parte del script, hecha como paso de control de calidad) sí consultó Shopify en vivo, usando la herramienta de Shopify conectada a esta conversación (`search_products`, `get-product`) para leer título, etiquetas, descripción y estado de cada producto sospechoso.

---

## 10. Resultados obtenidos

Evolución real, a lo largo de las corridas de esta iniciativa:

| Corrida | Umbral | Candidatos señalados | Qué pasó |
|---|---|---|---|
| 1 (29/09) | 2.0 | 130 | Revisados manualmente contra Shopify: 128 correctos, 1 mistagging real, 1 descripción duplicada |
| 2 (30/09, antes de regenerar el catálogo) | 2.5 | 54 | Mismo set que antes (el pickle aún no reflejaba la corrección hecha en Shopify) |
| 3 (30/09, con el catálogo regenerado) | 2.5 | 53 | Confirmó que la corrección sí se aplicó — el producto corregido ya no aparece |
| 4 (30/09, con el chequeo de texto ya construido) | 2.5 | **1** "requiere revisión" + 52 "confirmado por texto" | El filtro de texto redujo la lista de seguimiento de 53 a 1, sin perder el único caso genuinamente dudoso |
| 5 (01/10, corrida independiente) | 2.5 | **1** + 52 | Mismo resultado exacto que la corrida 4 — confirma estabilidad |

El único producto señalado en las corridas 4 y 5 (`Vestido Midi de Fiesta Alessia Estampado`, id 9978562183477) se verificó en Shopify Admin durante este cierre: tiene etiquetas contradictorias entre sí ("MAXI VESTIDOS" y "MIDI Y MINI VESTIDOS" a la vez) y su propia descripción se autodenomina "vestido midi" mientras está categorizado como `VESTIDOS LARGOS`. Es una inconsistencia real, aunque de bajo impacto — el producto está archivado, sin inventario, no visible a clientes.

---

## 11. Interpretación de los resultados

**Motivo 1 y 2** dieron, en la corrida más reciente, el mejor resultado posible: ambas fuentes de referencia del sistema cubren el 100% de las categorías reales del catálogo. No hay ninguna acción pendiente aquí.

**Motivo 3** pasó de "una lista larga que alguien tiene que revisar entera" a "una lista de un solo elemento, ya verificado como genuino". Esto no significa que el catálogo esté libre de errores — significa que, con los datos que tenemos hasta ahora, el mecanismo logra separar correctamente la variedad visual normal (una tela con lentejuelas, un estampado de animal print) de los errores de categorización reales.

---

## 12. Cálculo e interpretación de `similitud` y `z`

**Similitud** responde: *"¿qué tan parecida es la foto de este producto al 'look típico' de su propia categoría?"* Es un número entre 0 y 1 (en la práctica, para fotos de ropa del mismo tipo, suele estar entre 0.5 y 1.0) — más cerca de 1 significa más parecido a lo esperado.

Se calcula como **similitud coseno** entre el vector del producto y el **centroide** (promedio) de todos los vectores de su categoría declarada:

```python
# src/taxonomy_centroid_audit.py, funcion _cosine_similarity()
similitud = (vector_producto · vector_centroide) / (|vector_producto| × |vector_centroide|)
```

El centroide mismo se calcula así:

```python
# funcion _compute_centroid()
centroide = promedio, posicion por posicion, de todos los vectores de esa categoria
```

**Z (puntuación z, "desviaciones estándar")** responde una pregunta distinta: *"¿qué tan inusual es este resultado, comparado con lo que es normal dentro de su propia categoría?"* No es una medida absoluta de parecido — es una medida de qué tan extremo es, relativo a sus propios compañeros de categoría.

```python
# funcion run_mistagging_audit()
promedio = promedio de todas las similitudes de esa categoria
desviacion_estandar = que tanto varian esas similitudes entre si
z = (promedio - similitud_del_producto) / desviacion_estandar
```

**Ejemplo real, de la corrida del 1 de octubre:** la categoría `VESTIDOS LARGOS` tiene una similitud promedio de 0.866. Un producto con similitud 0.711 obtuvo z=5.0 — es decir, la desviación estándar de esa categoría es de aproximadamente 0.031, y ese producto está casi 5 veces más lejos del promedio de lo que es habitual ahí. Resultó ser, al verificarlo, un vestido legítimo cubierto de lentejuelas — una tela que se ve radicalmente distinta a una tela mate, aunque la prenda sea exactamente del tipo correcto.

**Por qué z y no solo similitud:** una categoría con mucha variedad natural (`VESTIDOS LARGOS` tiene 990 productos, de todos los estilos) tiene, de por sí, más dispersión que una categoría pequeña y homogénea. Usar un umbral fijo de similitud penalizaría injustamente a las categorías grandes. Medir en desviaciones estándar hace la comparación justa entre categorías de tamaños y variedades distintas.

---

## 13. Criterios, umbrales o reglas utilizados

| Parámetro | Valor actual | Por qué |
|---|---|---|
| `MISTAGGING_MIN_SAMPLES` | 5 productos | Por debajo de esto, no hay suficiente información para calcular una desviación estándar confiable — comparar un único producto contra sí mismo siempre da una similitud perfecta, sin aportar nada |
| `MISTAGGING_STD_THRESHOLD` | 2.5 desviaciones estándar | Empezó en 2.0 (130 candidatos); subido a 2.5 tras confirmar que el único mistagging real conocido estaba justo en el límite — es un ajuste de volumen de revisión, no una mejora de precisión comprobada con muchos casos |
| Chequeo de texto | El título+etiquetas del producto deben confirmar su categoría declarada (usando la misma lógica que ya usa el chat para entender lo que un cliente pide) | Reutiliza una fuente ya validada en producción, en vez de inventar una quinta lista de palabras clave |

---

## 14. Problemas/gaps conocidos

1. **El script lee una fotografía del catálogo, no Shopify en vivo.** Una corrección hecha en Shopify Admin no se refleja hasta que esa fotografía (`tfidf_model.pkl`) se regenera — ya ocurrió una vez durante esta iniciativa y generó confusión momentánea hasta identificar la causa.
2. **El umbral está calibrado con un solo caso real confirmado.** Es un punto de partida razonable, no una cifra validada estadísticamente.
3. **Correr el script localmente requiere autenticación de Google Cloud que no es trivial de configurar** — documentado en detalle (cinco intentos, causa real en el quinto) en `DCT_Cierre_Fase2_Unificacion_Taxonomia_27092026.md`, sección 7.5.
4. **Hay un aviso de formato ignorable** (`Python-dotenv could not parse statement starting at line 197`) en cada corrida — no afecta el resultado, pero vale la pena revisar esa línea del `.env` en algún momento sin prisa.

---

## 15. Consideraciones y limitaciones

- El chequeo de texto depende de que el título/etiquetas del producto estén bien escritos. Si un producto tiene la categoría Y el título mal puestos a la vez, el chequeo de texto no lo detectaría — seguiría pareciendo "consistente" entre sí, aunque ambos estén equivocados. Esto no pasó en los datos reales hasta ahora, pero es un límite teórico del método.
- El mecanismo de similitud visual funciona mejor donde la apariencia física correlaciona fuertemente con la categoría (moda/ropa). No necesariamente se traduce igual de bien a categorías donde dos productos visualmente parecidos pueden ser cosas completamente distintas.
- Esta herramienta es de **auditoría periódica**, no de prevención en tiempo real — no evita que un producto se cargue mal categorizado, solo ayuda a encontrarlo después.

---

## 16. Oportunidades de mejora

1. ~~Recalibrar el umbral~~ con más casos reales conforme se acumulen más corridas — hoy el ajuste descansa en un solo dato.
2. **Hacer el chequeo de texto más completo**: por ahora solo compara contra la categoría tal cual — podría también sugerir una categoría alternativa cuando detecta una mejor coincidencia textual.
3. ~~Automatizar la regeneración del pickle~~ **-- resuelto parcialmente el 01/10/2026, ver Addendum 1 abajo.**
4. **Evaluar si conviene registrar un historial** de candidatos ya revisados y descartados, para no tener que reconsiderar el mismo caso en cada corrida futura si nada cambió.

---

## Addendum 1 (01/10/2026) — Refresco automático del catálogo antes de cada corrida

**Origen:** durante esta misma iniciativa, una corrección hecha en Shopify Admin no se reflejó en una corrida del script porque la copia local de `tfidf_model.pkl` era de antes de esa corrección — nadie lo notó hasta comparar dos corridas manualmente (ver sección 10 de este documento). Yasmani identificó correctamente que esto es una versión más concreta y de menor riesgo de la oportunidad de mejora #3 de la sección 16: no automatizar la regeneración completa del catálogo (que dispararía un proceso pesado, con efectos secundarios), sino automatizar el **traer la copia más reciente que ya existe en el bucket**, eliminando el paso manual de `gsutil cp`.

**Decisión de diseño — reusar, no inventar:** el repo ya tenía exactamente este mecanismo en `check_missing_images.py` (un script hermano): si el pickle local no existe, lo descarga solo llamando a `gsutil` por subproceso. Se adoptó el mismo mecanismo aquí, en vez de introducir el cliente de Python de `google-cloud-storage` (aunque ya es una dependencia pinneada del proyecto, `google-cloud-storage==2.19.0`) — por consistencia, y para no abrir un camino de autenticación nuevo justo después de la saga de IAM documentada en la sección 7.5 del DCT de Fase 2. La autenticación de `gsutil` para leer un bucket es un caso simple y ya probado (es literalmente lo que Yasmani ya corría a mano), sin relación con la limitación específica de minteo de ID tokens que causó esa saga.

**Cambio de comportamiento, no solo de mecanismo:** el patrón existente en `check_missing_images.py` solo descarga si el archivo **falta** — si ya hay una copia local, por vieja que sea, la usa tal cual. Eso no habría resuelto el problema real que tuvimos (sí había una copia local). El nuevo comportamiento por defecto es más estricto: **sin ruta explícita, el script siempre trae la versión más reciente del bucket**, sobrescribiendo cualquier copia local.

**Diseño final:**
- Sin argumento de ruta (uso normal): `ensure_fresh_pickle()` siempre descarga antes de analizar.
- Con una ruta explícita (`python taxonomy_centroid_audit.py mi_pickle.pkl`): se respeta tal cual, sin tocar el bucket — preserva la capacidad de probar contra un pickle fijo o sintético, como se hizo durante el desarrollo de esta misma herramienta.
- Degradación con gracia: si `gsutil` no está instalado o la descarga falla, se usa la copia local existente como respaldo (con aviso explícito de que puede estar desactualizada), o se aborta limpiamente si tampoco hay copia local.
- **Defensa adicional**: el reporte ahora siempre imprime el campo `synced_at` que ya trae el propio pickle (la fecha de sincronización real con Shopify) — así, sin importar de dónde vino el archivo, la antigüedad de los datos analizados queda a la vista en cada corrida, incluso si alguien pasa a propósito una ruta a un archivo viejo.

**Validado** con tres escenarios sintéticos antes de aplicar al repo real: (A) ruta explícita — no toca el bucket; (B) sin ruta, sin `gsutil`, sin copia local — aborta limpio con instrucciones; (C) sin ruta, sin `gsutil`, con copia local — la usa como respaldo con aviso claro. Sintaxis validada en el archivo real.

**Archivo modificado:** `taxonomy_centroid_audit.py` — nueva función `ensure_fresh_pickle()`, `main()` reescrito, `load_catalog_data()` ahora también devuelve `synced_at`.

### Addendum 1.1 (01/10/2026, misma tarde) — Validación de circuito cerrado, con datos reales

Yasmani corrigió en Shopify Admin la inconsistencia de `Vestido Midi de Fiesta Alessia Estampado` (id 9978562183477), ejecutó la sincronización del catálogo, y corrió el script de nuevo -- sin pasar ninguna ruta, dejando que el refresco automático hiciera su trabajo.

**Confirmado con los propios datos de la corrida:**
- `synced_at` del pickle (16:26:19 UTC) quedó a solo 3-4 minutos de la hora de inicio del script (18:29:55 hora local de Suiza) -- el refresco automático trajo el catálogo recién sincronizado, no una copia vieja.
- El producto corregido aparece ahora en **"CONFIRMADO POR TEXTO"**, ya no en "requiere revisión manual" -- con la MISMA similitud y z-score exactos que antes (0.787 / 2.6), lo cual es internamente consistente: la foto no cambió, el texto sí.
- **Resultado final: 53 de 53 candidatos confirmados por texto, 0 requieren revisión.** Tercera confirmación real consecutiva (sin contar la validación sintética original) de que el chequeo de texto se comporta correctamente ante datos reales, incluyendo reaccionar bien a una corrección.

Esto cierra el circuito completo que motivó ambas mejoras de esta semana: detectar -> verificar -> corregir -> refrescar automáticamente -> confirmar que la corrección se sostiene. **Fase cerrada**, sin reservas pendientes sobre el mecanismo en sí.

---

## 17. Conclusión y estado final

El trabajo **"script de auditoría + chequeo de texto automático" se da por completo**, para el alcance con el que se definió: los tres motivos funcionan de punta a punta contra el catálogo real, validados en múltiples corridas independientes, y el chequeo de texto logró lo que se esperaba de él — reducir una lista de 130 (o 53) productos a revisar, a solo 1, sin perder el único caso genuinamente dudoso conocido hasta ahora.

Esto es un **primer resultado funcional maduro**, no un producto terminado para siempre — las limitaciones de la sección 15 y las oportunidades de la sección 16 son trabajo legítimo de una segunda iteración, no pendientes bloqueantes.

---

## 18. Referencias a código y documentación relacionada

**Código:**
- `taxonomy_centroid_audit.py` (raíz del repo) — el script completo
- `src/recommenders/product_taxonomy.py` — fuente de referencia auditada (Motivo 2)
- `src/recommenders/improved_fallback_exclude_seen.py` — fuente de referencia auditada (Motivo 2) y función reutilizada para el chequeo de texto (Motivo 3)
- `src/api/services/colbert_client.py` — cliente que solicita los embeddings (método `export_embeddings()`)
- `src/api/services/embedding-service/main.py` y `visual_retriever.py` — servicio que calcula y expone los embeddings
- `env_loader.py` — utilitario de carga de configuración

**Documentación relacionada:**
- `DCT_Cierre_Fase2_Unificacion_Taxonomia_27092026.md` (mismo directorio) — cronología completa del desarrollo de esta herramienta, incluida la saga de autenticación local (sección 7.5) y la verificación manual de los 130 candidatos originales (sección 7.7)
- `DCT_Fase1b_Composite_Embedding_F08B_Cierre_24072026.md` — origen de la necesidad (caso real que motivó todo esto: un producto `CARTERAS` visualmente idéntico a un vestido)
