# RESUMEN -- E5 nivel 2: estado, resultados y proximos pasos

**Fecha:** 30/10/2026
**Tipo:** resumen de situacion (punto de entrada para retomar el trabajo).
**Detalle completo:** `SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md` (misma carpeta),
secciones 1-12 (diseno) y 13-17 (cierre de cada paso con su evidencia).
**Contexto previo:** `DCT_Cierre_Sesion_01102026.md` (A.11 = origen del gap E5;
A.16 = estado valido al empezar), `../BACKLOG_Busqueda_por_Atributos_Color_24072026.md`
(el color, segundo consumidor previsto).

Convencion: **[V]** verificado con codigo, logs o mediciones; **[H]** hipotesis.

---

## 0. ¿Hemos implementado la "busqueda vectorial sobre un subconjunto que define el catalogo"?

**Si, en su nucleo. Con tres matices.**

La frase viene de la decision del 17/10: disenar la opcion 1 NO como "un filtro
de categoria para F-08", sino como una primitiva general,
`buscar(fuente_de_consulta, filtro)`, donde **el catalogo decide el
subconjunto** y el buscador vectorial solo **ordena** dentro de el. El color iba
a ser el segundo uso de la misma primitiva.

| Parte de la primitiva | Estado |
|---|---|
| El servicio busca SOLO dentro de un conjunto de ids que le envian | **[V] En produccion** desde el 26/10 (`/v1/embed/search-filtered`) |
| El servicio NO sabe que es una categoria (recibe ids, nunca tipos) | **[V]** En la validacion en produccion (C3) el filtro fue un subconjunto ARBITRARIO de 64 ids, no una categoria, y el resultado fue exacto |
| El monolito define el subconjunto con su catalogo | **[V]** `build_visual_filter`, con el criterio de tipo |
| La usa un consumidor real | **[V] Activa** desde el 29/10 en F-08C y Fase A |

**Matices:**
1. **Un solo consumidor** (el tipo de producto en F-08). La generalidad esta
   disenada y probada con ids arbitrarios, pero no demostrada con un segundo uso
   real. Ese segundo uso es el color, pendiente.
2. **Faltan dos fuentes de consulta.** Hoy: "parecidos a este producto" (con o
   sin texto de refuerzo). No: solo texto (lo necesitara el color fase 2) ni
   imagen.
3. **El monolito solo construye filtros de tipo.** El contenedor (`include` /
   `exclude`) es general; el color necesitara un segundo criterio.

---

## 1. Que hemos implementado

| Fecha | Paso | Que | Donde |
|---|---|---|---|
| 19/10 | 2 | Extraer el calculo del pool duplicado (`build_pool_request`) | Monolito, `00329-mlt` |
| 19/10 | 2b | Higiene de tests: fuga del `.env` y escrituras reales en Retail API | Tests |
| 25/10 | -- | **Incidente H-15 corregido:** el embedding service fallaba 56 de 64 arranques | Servicio, `00061-f88` |
| 26/10 | 1 | Endpoint `/search-filtered` + imagen reproducible | Servicio, `00062-kvd` |
| 29/10 | 3 | Filtro en el monolito, APAGADO (comportamiento identico) | Monolito, `00330-vwb` |
| 29/10 | 4 | **Filtro activado** | Monolito, `00332-d87` |
| 30/10 | H-20 | Imagen del monolito sin artefactos (3,0 GB -> 559 MB) | Monolito, `00333-h5z` |
| 30/10 | Rec. 1 | Herramientas de validacion versionadas en `tools/validation/` | Repo, commit `6599c18` |

---

## 2. Objetivo

Que cuando el usuario pida "productos parecidos", el sistema **busque los mas
parecidos entre los que de verdad puede mostrarle**, en vez de buscar en todo el
catalogo y descartar despues.

---

## 3. El problema y como se resuelve

**Analogia.** Le pides a un dependiente "traeme 100 bolsos parecidos a este".
El metodo antiguo trae los 100 objetos mas parecidos de TODA la tienda y luego
tira lo que no sirve (vestidos, aros, lo que ya te enseno). Si hay pocos bolsos,
o ya viste muchos, puede volver con casi nada aunque haya bolsos en el almacen.
El metodo nuevo le dice desde el principio: "traeme los 100 mas parecidos, pero
SOLO de estas estanterias y sin lo que ya me ensenaste".

**El caso real que lo motivo** (DCT A.11, gap E5): el 05/10, con 80 productos
ya vistos, el pool de 50 vecinos devolvio **0 CARTERAS** aunque el catalogo si
tenia.

**Ejemplo medido en produccion** (`palazzo-silvia-negro`, turnos 5 y 7 del guion):

| | Filtro despues (antes) | Filtro dentro (ahora) |
|---|---|---|
| Candidatos utiles en el pool | 7 | **57-68** |
| Productos mostrados | 7 de 8 (faltaban alternativas) | **8 de 8** |
| PANTALONES mostrados | 5 | 5 (el catalogo no tiene mas: el filtro no inventa productos) |

**Por que es seguro (propiedades P1-P3, spec seccion 3).** El filtro decide
producto a producto, sin mirar la similitud. Por eso aplicarlo ANTES da
exactamente lo mismo que aplicarlo DESPUES a un pool infinito. Consecuencia: el
nivel 2 **nunca quita nada** de lo que antes se mostraba; **solo anade** lo que
se perdia por el recorte. [V] Demostrado en 20.000 casos y confirmado en
produccion: los productos de la categoria pedida no bajaron en ningun turno.

---

## 4. Componentes y flujo

```
 Usuario: "muestrame productos similares"   (ancla: palazzo-silvia-negro)
                         |
 +------------- MONOLITO (retail-recommender) ---------------------------+
 | 1. build_pool_request      ¿que admite el pool?                       |
 |    -> familia del ancla + alternativas declaradas                     |
 |       (PANTALONES, FALDAS, LEGGINGS...)                               |
 | 2. build_visual_filter     traduce a ids con el catalogo propio       |
 |    -> include = {ids de esos tipos}   exclude = {vistos + ancla}      |
 | 3. colbert_client.search_filtered   -------------> POST /search-filtered
 +---------------------------------------------------------|-------------+
                                                           v
 +------------- EMBEDDING SERVICE -------------------------------------+
 | 4. FAISS + IDSelector: busca SOLO entre los ids admitidos           |
 |    -> los top_k mas parecidos + anchor_found + eligible_count       |
 +---------------------------------------------------------|-----------+
                                                           v
 +------------- MONOLITO ----------------------------------------------+
 | 5. ¿anchor_found y lista vacia? -> "nada elegible": contrato honesto |
 |    ¿anchor_found falso?         -> ancla no indexada: fallback       |
 | 6. Filtro posterior (DEFENSA): no deberia quitar nada; si lo hace,   |
 |    avisa con "E5 divergencia"                                        |
 | 7. Contrato principal / alternativas -> widget                       |
 +---------------------------------------------------------------------+
```

| Componente | Fichero | Papel |
|---|---|---|
| `build_pool_request` | `src/recommenders/f08_similarity_resolution.py` | Que tipos admite el pool (una sola fuente de verdad) |
| `VisualFilter`, `build_visual_filter` | idem | El subconjunto expresado como ids |
| `RECS_VISUAL_FILTER_IN_SEARCH` | idem (y `env-vars.yaml`) | Interruptor; se lee en cada peticion |
| `search_filtered` | `src/api/services/colbert_client.py` | Cliente; EXIGE los campos del contrato |
| `/v1/embed/search-filtered` | `src/api/services/embedding-service/main.py` | Endpoint |
| `search_filtered`, `_positions` | `src/api/services/embedding-service/visual_retriever.py` | Busqueda con `IDSelector` y cache id -> posicion |

---

## 5. Decisiones de arquitectura y su impacto

| Decision | Por que | Impacto |
|---|---|---|
| **El catalogo decide el subconjunto; el servicio solo ordena** | El servicio no debe conocer la taxonomia (Fase 1b); una sola fuente de verdad | Reetiquetar un producto en Shopify no obliga a reindexar |
| **Una sola busqueda** (familia + alternativas) | Conserva la semantica actual (P2) | Presupuestos separados para principal y alternativas: mejora posterior, si las metricas la justifican |
| **Equivalencia primero** (P1-P3) | Cambio verificable: misma logica, aplicada antes | Sin sorpresas: solo aparece lo que antes se perdia |
| **`anchor_found` en la respuesta** | Una lista vacia tenia dos significados opuestos (F7) | Resuelto en tres decisiones del handler; la ruta por imagen solo se usa cuando hace falta |
| **Flag leido en cada peticion, apagado por defecto** | Activar y desactivar sin reconstruir | Vuelta atras en minutos. **Orden obligatorio: primero el flag y despues el servicio** (el circuit breaker visual es compartido) |
| **Defensa con su propia senal** | El filtro posterior ocultaria un filtro mal construido | El aviso `E5 divergencia` es la unica senal: **0 en produccion** [V] |
| **Builds reproducibles** | Una reconstruccion cambiaba 15 paquetes sin querer (H-16) | `constraints.txt`, `.dockerignore` en lista blanca, despliegue por digest |
| **Rutas descartadas** | Pedir el indice entero, guardar el tipo en el servicio, subindices por categoria | Documentadas en la spec, seccion 1 |

**Coste:** 0,5-3,4 ms por busqueda filtrada en produccion [V]; unos 8,6 KB por
peticion con el catalogo actual [V, spec seccion 2]. **Limite conocido:** por
encima de unos 20.000-30.000 productos habria que llevar los atributos junto a
los vectores (camino natural: pgvector), sin cambiar la interfaz del monolito.

---

## 6. Resultados

| Area | Resultado |
|---|---|
| Exactitud | P1-P3 en 20.000 casos; prueba diferencial del handler en 400 escenarios; 5/5 mutantes en cada oraculo [V] |
| Flag apagado | 8/8 turnos identicos caracter a caracter con la revision anterior [V] |
| Flag activado | 9/9 turnos con filtro; P3 confirmado; T5 y T7 de 7 a 8 productos; caso B.2 intacto [V] |
| Imagen ligera (30/10) | 9/9 turnos identicos a la revision anterior, ocho horas despues [V] |
| Estabilidad | 0 errores; 0 avisos de divergencia; ningun tipo de aviso nuevo [V] |
| **Beneficios indirectos** | **Un incidente de produccion descubierto y resuelto** (H-15: 87 % de arranques fallidos del embedding service); imagenes -32 % (servicio) y -81 % (monolito); builds reproducibles; margen de arranque del monolito corregido (H-23) |

---

## 7. Gaps y pendientes

**De E5 nivel 2:**

| Pendiente | Estado |
|---|---|
| **Seguimiento con trafico real** (spec 17.5): principal completo, `exhausted`, productos por turno, divergencias | Necesita unos dias de trafico desde el 29/10 ~16:10 UTC |
| **Repetir el caso que lo motivo** (anclas del 05/10 y 07/10, CARTERAS con muchos vistos) | NO reproducido todavia |
| **Rama "nada elegible" en produccion** (lista vacia con el ancla indexada) | Solo probada en la prueba diferencial (D3); el guion no la provoco |
| Fallback por imagen de Fase A sin filtro | Limitacion documentada (ruta poco frecuente) |
| Rutas Estandar y outfit (F-08B) sin la primitiva | Fuera de alcance |

**Para que la primitiva sea "general" de verdad:**
- El **segundo consumidor: color fase 1.** Empieza por el **censo de `COLOR`**
  (spec seccion 10), de solo lectura.
- La fuente **"solo texto"**, para el color fase 2.

**Contrato implicito ACCESSORIES/JOYAS** (DCT A.16.5 decia "el nivel 2 lo
retiraria"): [V] ya NO decide que entra en el pool de F-08. Para la intencion de
similitud, `pool_cats` = familia del ancla (`SIMILARITY_FAMILIES`) + alternativas
declaradas (`ALTERNATIVE_FAMILIES`); las categorias por grupo padre (que dependen
del orden del diccionario) no se usan ahi. Pero no lo retiro el nivel 2, sino el
mapa explicito de familias y alternativas (A.15/A.16); el nivel 2 aplica ese
criterio dentro de FAISS. Fuera de F-08 NO esta verificado.

**"Nivel 3" de E5:** mencionado en el DCT (A.15.7, A.16.5) pero sin definir en
ningun documento ni en el registro de sesiones.

**Hallazgos abiertos** (detalle en la spec): H-6 (LFM2 retirado: el 100 % cae a
GPT-4o-mini), H-13 (carrera en FAISS), H-17 (revision de los modelos sin fijar),
H-19 (`venv_fase0` en git), H-18 (`.gitattributes`), H-22 (ruido en la prueba
diferencial), H-10 (Retail API sin uso), H-11 (credenciales locales).

---

## 8. Recomendaciones

| # | Recomendacion | Por que |
|---|---|---|
| 1 | ~~**Versionar las herramientas de validacion**~~ **HECHA 30/10** (commit `6599c18`, `tools/validation/README.md`). [V] Logica identica a la copia (AST sin docstrings, pyflakes diferencial); `c1` 3/3 el 30/10: la linea base del 23/10 sigue valida | Motivo original: [V] `validate_search_filtered.py`, `compare_junit.py` y `check_retail_test_events.py` solo existen en `backup_E5_18102026`, fuera del repo: si esa carpeta se pierde, se pierde la forma de validar cada paso (ya paso con los oraculos de `/tmp`) |
| 2 | **Script de despliegue del monolito**, como el `deploy.sh` del servicio | El comando se escribe a mano: la sonda de 240 s, el digest y `env-vars.yaml` dependen de la memoria. Ya hubo una desincronizacion (flag activado desde la consola) |
| 3 | **Seguimiento 17.5** con consultas preparadas, y repetir el caso de CARTERAS | Mide el efecto real, no solo el mecanismo |
| 4 | **H-19 + H-18** (higiene de git) | Coste bajo; evita meter binarios en un commit |
| 5 | **Color fase 1**, empezando por el censo | Siguiente paso del plan y prueba de que la primitiva es general |
| 6 | **H-6**: decidir el modelo principal | Afecta a todas las peticiones |
| 7 | **H-13** y **H-17** | Riesgos latentes del servicio |

**Oportunidades:** retirar `visual_rank` (se envia, pero ningun componente lo
lee [V]); presupuestos separados para principal y alternativas, solo si las
metricas lo justifican; *contract tests* entre el monolito y el servicio.

---

## 9. ¿Vamos en orden y en la direccion correcta?

**Si.** El plan del 17/10 era:

```
 E5 nivel 2 (primitiva general)  ->  Color fase 1 (filtro duro)  ->  Color fase 2 (texto contra imagen)
     hecho, falta seguimiento            siguiente                       despues de un POC
```

Los desvios (H-15, H-20, H-23, la higiene de tests) aparecieron al validar cada
paso, y uno era un incidente real de produccion que nadie habia dewedrewetectado. Lo
unico que se ha quedado atras es el seguimiento con trafico real.

---

## 10. Como retomar

Orden propuesto para la proxima sesion:

1. ~~Recomendacion 1~~ (hecha el 30/10, `tools/validation/`) y **recomendacion 2**
   (script de despliegue del monolito): cierran riesgos de proceso antes de seguir.
2. **Seguimiento 17.5**: preparar las consultas de Cloud Logging, misma ventana
   antes y despues del 29/10 ~16:10 UTC, y repetir el caso de CARTERAS con
   muchos productos vistos.
3. Con las metricas en la mano, **cerrar E5 nivel 2** en la spec.
4. **Color fase 1**: empezar por el censo de `COLOR` (solo lectura), antes de
   cualquier codigo.

Recordatorios operativos:
- **Vuelta atras del filtro:** `RECS_VISUAL_FILTER_IN_SEARCH=0`, sin
  reconstruir. Si ademas hubiera que volver a una revision del embedding
  service sin `/search-filtered`: **primero el flag, despues el servicio**.
- **`env-vars.yaml` es la fuente de verdad del flag** (`"1"`): no cambiarlo
  desde la consola sin reflejarlo en el repo.
- **Comando de despliegue del monolito:** por digest, con
  `failureThreshold=24` x `periodSeconds=10` (240 s) en la sonda de arranque
  (spec 17.3, H-23).
- **Guion de validacion de 9 turnos:** fijar el ancla del turno 4
  (`aros-isadora-flor-metal-plateado`) abriendo su pagina directamente (H-21).
