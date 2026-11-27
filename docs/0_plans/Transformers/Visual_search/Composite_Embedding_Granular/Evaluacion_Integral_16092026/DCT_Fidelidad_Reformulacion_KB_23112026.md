# DCT -- Fidelidad de la reformulacion de la base de conocimiento (23/11/2026 - en curso)

Punto 3 del plan de `DCT_Frescura_Contenido_KB_20112026.md` (seccion 6): comprobar que el modelo que reformula
las respuestas de la base de conocimiento no afirma nada que el documento no diga. Es responsabilidad directa del
sistema, sea cual sea la tienda: el contenido lo aporta cada tienda, pero lo que el chat dice a partir de ese
contenido es nuestro.

Convencion: [V] verificado con evidencia; [H] hipotesis; [Y] confirmado o decidido por Yasmani. Ningun valor
secreto aparece en este documento.

---

## 1. Que significa "fidelidad" aqui

Una respuesta reformulada es **fiel** si todo lo que afirma esta en el documento de la base de conocimiento (o en
los bloques de contexto que el propio sistema anade al prompt: historial de tallas, inventario, datos del
producto). No se mide si el documento es verdadero (eso es el verificador de contenido por tienda, punto 4 del
plan), sino si el chat se aparta de el.

Ejemplo con la pagina de ejemplo `metodos-de-pago` de la demo, que dice: tarjetas Visa, Mastercard, American
Express y Discover; PayPal, Apple Pay, Google Pay; "Compras >$300: Hasta 6 cuotas sin interes":

| Pregunta | Respuesta fiel | Respuesta infiel (riesgo) |
|---|---|---|
| "Puedo pagar con Mastercard?" | Si, Mastercard esta entre las tarjetas aceptadas | - |
| "Puedo pagar con Mercado Pago?" | La pagina no menciona Mercado Pago; estos son los metodos que si figuran | "Si, aceptamos Mercado Pago" |
| "Puedo pagar en 6 cuotas una compra de $200?" | No: 6 cuotas a partir de $300; para $200, hasta 3 | "Si, puedes pagarla en 6 cuotas" |

## 2. Como funciona hoy la reformulacion (lectura de codigo, 23/11) [V]

```
 pregunta del cliente -> deteccion de intencion -> sub_intent (p. ej. policy_payment)
     -> base de conocimiento: documento del tema (Redis -> PostgreSQL)
     -> puerta: has_specific_entities(pregunta, sub_intent)        (kb_contextualizer.py)
          |- NO (pregunta generica): se sirve el documento TAL CUAL  (sin modelo, sin riesgo de infidelidad)
          |- SI, o tema forzado (tallas; disponibilidad o material con pagina de producto):
               generate_contextual_answer() -> modelo -> respuesta de 2-3 frases
               si el modelo falla: documento tal cual
```

- **Puerta** (`has_specific_entities`, regex por tema): solo 8 temas tienen patrones (pago, envio, devolucion,
  garantia, tallas, material, cuidado, pedidos). Se reformula cuando la pregunta nombra algo concreto: una marca de
  tarjeta, un transportista, un pais, un numero de dias, un material... Llamada desde
  `mcp_conversation_handler.py` (L607-L711).
- **Modelos, en orden**: LFM (apagado: `LFM_KB_ENABLED=false` desde R-8), **GPT-4o-mini** por OpenRouter
  (`GPT4O_MINI_FALLBACK_ENABLED=true`, timeout 8 s, temperatura 0,3) y Claude como ultimo recurso (modelo de
  `claude_config`, timeout 3 s). En produccion responde GPT-4o-mini [V, `env-vars.yaml`].
- **Prompt general** (todos los temas menos tallas): "You answer customer questions ONLY using the policy document
  provided ... If the document does not contain the specific information asked, say so clearly and briefly", 2-3
  frases, en el idioma del cliente. El mensaje del usuario lleva el documento entre comillas triples, la pregunta
  y "Answer ... based only on the document above".
- **Prompt de tallas** (`product_sizing`): pide presentar los datos de la tabla, hasta 5 frases; **no** dice que se
  cina al documento ni que diga cuando no tiene el dato.
- **Bloques de contexto** que el sistema anade antes del documento: historial de tallas del cliente (F-02), alerta
  de stock y disponibilidad por talla (F-05), datos de material del producto, y una instruccion de mencionar el
  nombre del producto. Son fuentes legitimas: una comprobacion de fidelidad debe contarlas como fuente.
- **Lo que sale**: la respuesta va directa al cliente; el JSON incluye `kb_document` (el documento completo) cuando
  hubo reformulacion, para que el frontend pueda ofrecer "ver la politica completa".
- **Lo que queda registrado**: modelo, milisegundos y numero de caracteres. **Ni la pregunta completa ni la
  respuesta.**

## 3. Hallazgos de la lectura de codigo

| Id | Hallazgo | Gravedad | Estado |
|---|---|---|---|
| R-16 | **El modelo de respaldo es hoy el principal, sin evaluacion de fidelidad**: con LFM apagado (R-8), GPT-4o-mini responde todas las reformulaciones. Las evaluaciones de junio (`DCT_Haiku_vs_GPT4oMini_09062026.md`, DCT de la migracion del 10/06) midieron calidad conversacional, latencia y coste, como respaldo para ~5 % del trafico; no midieron si se ciñe al documento [V, configuracion y documentos] | Media | Lo mide este punto del plan |
| R-17 | **Nada comprueba la respuesta antes de enviarla y nada la deja registrada**: no hay verificacion posterior (datos, truncamiento) y los logs solo guardan la longitud. Una respuesta infiel en produccion no se puede detectar ni auditar despues [V, codigo] | Media | Candidato a mejora tras medir |
| R-18 | **Limite de tokens distinto del previsto**: el codigo calcula 250 tokens (500 para tallas), pero ese valor solo se usa en la ruta de Claude; GPT-4o-mini usa el de su configuracion, 300. Para tallas, 300 en lugar de 500: una tabla larga puede salir cortada, y el cliente no lo devuelve (`LLMResponse` no guarda `finish_reason`), asi que el corte no se ve [V, codigo `kb_contextualizer.py` y `llm_client.py`] | Media para tallas (dato incompleto), Baja para el resto | **Medido el 23/11: Baja.** 0 respuestas cortadas en 428; maximo 145 tokens de salida (tallas, mediana 66) con limite 300 [V]. El riesgo vuelve si una tienda tiene tablas mas largas |
| R-19 | **El prompt de tallas no pide cenirse al documento ni decir "no lo se"**: es el tema con mas numeros (medidas) y el unico sin esas dos instrucciones [V, codigo] | Media [H: por medir] | Medir antes de cambiar |
| R-20 | **La puerta casi no reconoce preguntas en frances y falla con palabras conjugadas**: con el conjunto de preguntas, pasan la puerta 44 de 48 en es y en, pero **17 de 48 en fr** [V, laboratorio, codigo real]. Los patrones son en su mayoria en espanol e ingles, y varios son raices con `\b` al final que no aceptan la palabra completa: `centrifug` no reconoce "centrifugar", `cancelar` no reconoce "cancelarlo", `perdido` no reconoce "perdio", `hand\s*wash` no reconoce "hand washing"; en ingles faltan "installments" y "temperature". Efecto: el cliente en frances recibe casi siempre el documento completo en vez de una respuesta a su pregunta. No es un riesgo de fidelidad (el documento tal cual es fiel) sino de calidad y coherencia entre idiomas (Suiza) | Media para fr | Registrado; se decide tras medir la fidelidad |
| R-23 | **"No" contradictorio en el cuidado de la lana** (CAR-A1, "¿puedo meter un sueter de lana en la lavadora?"): en todas las ejecuciones y con todos los prompts, casi todas las respuestas empiezan "No" y a la vez dicen "a mano o en ciclo delicado"; el ciclo delicado es lavadora. El cliente recibe un "No" que el documento no dice [V, revision manual del 24/11 de run_base_v3, run_v3, run_base_v4 y run_v4]. No se etiqueto en ninguna ejecucion para no romper la comparacion entre versiones | Baja (consejo mas prudente que el documento, no mas arriesgado) | Registrado; se vuelve a mirar con el modelo del paso 3 |
| R-25 | **El cliente de OpenRouter envia el razonamiento del modelo como respuesta**: si `content` llega vacio, `llm_client.py` (L79-L87) devuelve `message.reasoning` o `reasoning_content`, es decir, el texto interno del modelo, normalmente en ingles e incompleto. Pasa con modelos que razonan cuando agotan el limite de tokens razonando. Reproducido con el codigo real y un modelo simulado: 63 de 63 respuestas eran el razonamiento [V, laboratorio 24/11] | Latente hoy (GPT-4o-mini no razona); **Alta** si se configura un modelo que razona (los dos Liquid de texto de OpenRouter lo hacen siempre) | Corregir antes de adoptar un modelo que razone: `content` vacio = fallo (respaldo), nunca el razonamiento |
| R-27 | **Claude Haiku 5.5 no cabe en el limite de tokens actual**: con 300 tokens, 24 de 189 respuestas salen vacias (el razonamiento interno, que OpenRouter no devuelve ni cuenta, agota el limite) y 30 salen cortadas a mitad de frase; se concentran en garantia (29 de 36) y tallas [V, criba 24/11]. El respaldo Claude de produccion (R-11) usa 250 tokens (500 en tallas): pasar a Haiku 5.5 sin ajustar razonamiento o limite repetiria el problema [H: la API de Anthropic usa razonamiento adaptativo con esfuerzo medio por defecto, segun su documentacion] | Media para R-11 | Medir Haiku 5.5 en modo capacidad antes de configurar R-11 |
| R-28 | **Variable `PERPLEXITY_API_KEY` declarada en produccion sin uso**: la revision 00346 la carga del secreto `perplexity-api-key` (sin valor real) [Y, consola 25/11] y `revision-config.yaml` L145-149 la declara. Ningun codigo activo la lee [V, `git grep` 25/11]: la fabrica activa (`service_factory.py` L1264) crea `OptimizedConversationAIManager` solo con `anthropic_api_key`, asi que la validacion Perplexity nunca se activa; `core/ai_factory.py` la pasaria desde `settings.perplexity_api_key`, atributo que `core/config.py` no define, y nadie importa ese modulo (codigo muerto). El resto son copias en `0_backups` y `0_legacy` | Baja (higiene: un secreto mas que gestionar, y una revision depende de un secreto que no se usa) | Quitarla de la revision en un despliegue propio; despues **deshabilitar** (no borrar) la version del secreto, para que las revisiones antiguas sigan pudiendo arrancar en un rollback |
| R-29 | **La reformulacion KB depende del cliente de Anthropic aunque responda otro modelo**: si `generate_contextual_answer` no recibe ni obtiene un cliente Anthropic, sale con `None` (documento tal cual) **antes** de probar LFM y el modelo principal (`kb_contextualizer.py` L923-935) [V, codigo]. Hoy no ocurre (hay `ANTHROPIC_API_KEY`) [H]; ocurriria si se retira la clave de Anthropic o falla su cliente. El paso 1 no lo cambia y lo hace visible (`document_as_is`) | Baja hoy; Media si se retira Claude (R-11) | Mover la comprobacion al escalon Claude, en un cambio aparte |
| R-30 | **Una consulta de producto repetida recibe la plantilla y no el texto del redactor**: "Busco un vestido para una boda" dio el 25/11 un texto redactado la primera vez (2.419 ms, "Te recomiendo el Vestido Largo Isi Burdeo...") y, al repetirla con otra sesion, `strategy_used=cached` y la respuesta "Aqui tienes algunas opciones que pueden encajar." (399-489 ms) [V, sondas de produccion]. Es la plantilla `_SOME_PRODUCTS_TEMPLATES` de `localized_messages.py`, que segun su comentario "solo llega al usuario si la personalizacion no lo sobrescribe" [V, codigo]: la ruta de cache no pasa por el redactor [H: falta leer la ruta exacta] | Media para la experiencia (un cliente que repite o reformula igual recibe una frase generica); afecta a R-8(b) y a las sondas del paso 1 (hay que usar consultas nuevas) | Registrado; se estudia con R-8(b) |
| R-31 | **Una peticion de producto clasificada como pregunta de informacion**: "Necesito una chaqueta para el invierno" (es, mercado CL, sesion nueva) recibio el 25/11 el menu de ayuda "No pudimos clasificar tu pregunta especificamente... Devoluciones y Cambios..." con 0 productos, en 303 ms [V, una sonda en `00346-f5w`]. La causa no esta estudiada [H: alguna regla de intencion informativa reconoce "invierno" o "necesito"]. Afecta a la experiencia de compra, no a la fidelidad | Media (por confirmar con mas consultas) | Registrado; reproducir con el clasificador en el laboratorio antes de decidir |
| R-32 | **Preguntas de garantia y de cancelacion que no llegan a su documento en produccion**: con las mismas 3 x 2 repeticiones antes y despues del paso 2 [V, sondas 26/11]: "Si la cremallera de un vestido se rompe a los 45 dias, ¿me lo cambian por garantia?" se clasifica `policy_return` y se responde con la politica de devoluciones ("no se menciona garantia"), aunque la tienda tiene pagina de garantia; "The sole of my shoes came off 70 days after I bought them, is it covered by the warranty?" se clasifica `unknown` (menu de ayuda); "I placed my order 5 hours ago, can I cancel it for free?" va a `account_modifications` sin entidades y recibe el documento tal cual. La bateria del laboratorio fijaba el `sub_intent` de cada pregunta, asi que no media el enrutamiento | **Alta** para garantia (el cliente oye que no hay garantia); Media para cancelacion (recibe el documento correcto, sin reformular) | Alcance medido el 26/11 (7.16): **69 de 162** preguntas de la bateria no llegan a su documento (garantia 20/24, pedidos 19/24, materiales 12/18); cinco mecanismos, M1-M5 |
| R-33 | **La carga de MiniLM borra el token de HuggingFace del disco**: `MiniLMIntentClassifier.load()` llama a `HfFolder.delete_token()` para forzar acceso anonimo; pensado para Cloud Run, pero en un equipo de desarrollo o en pruebas borra el token guardado [V, lectura 26/11] | Baja (no afecta a clientes) | Registrado; el simulador de R-32 lo neutraliza |
| R-34 | **Paginas de la base de conocimiento con contenido de plantilla que contradice a la tienda** [V, Shopify 26/11]: `cancelaciones-y-modificaciones-de-pedidos` dice "cancelacion gratis antes de 1 hora", "modificar hasta 30 minutos", cargo de $2, `pedidos@tutienda.com` y +1 (555) 123-4567, mientras `donde-esta-mi-pedido` dice "antes de 2 horas: gratis" y `orders@ai-shoppings.com`; `preguntas-frecuentes-faq` usa `info@tutienda.com` y +1 (555) 123-4567; `mensaje-de-ayuda-general` (el menu de `unknown`) da WhatsApp +52 55 1234 5678 y `ayuda@tutienda.com`; la politica de privacidad dice "En Tu Tienda". En la bateria llegan a esas paginas 16 preguntas de pedidos (cancelaciones) y 29 (menu) | **Alta**: el cliente recibe plazos contradictorios y contactos que no existen | **Cerrado el 26/11** (7.17): 6 paginas corregidas en es/en/fr y validadas en produccion (6 de 6 sondas) |
| R-35 | **Las preguntas de cancelacion nunca se reformulan: la puerta de reformulacion no tiene patrones para `account_modifications`** [V, lectura de `kb_contextualizer.py` 26/11]: `has_specific_entities` solo tiene patrones para 7 temas; sin patrones devuelve False y se sirve la pagina entera. "Hice el pedido hace 5 horas, ¿puedo cancelarlo gratis?" recibe toda la pagina de cancelaciones y el cliente debe deducir que ya no es gratis (sondas R-34). En frances se suma R-20 ("annuler" no esta en los patrones de `account_orders`) | Media (la respuesta es correcta pero no contesta a la pregunta concreta) | Registrado; activar la reformulacion aqui expone al error ya medido "5 horas esta dentro de las 2 horas": medir primero en el banco de fidelidad |
| R-26 | **El servicio de embeddings usa un modelo que Liquid marca como obsoleto**: `LiquidAI/LFM2-ColBERT-350M` (`colbert_retriever.py` L27); sucesor `LFM2.5-ColBERT-350M` [V, liquid.ai/models]. Los pesos se descargan al construir la imagen (Dockerfile L58) y en ejecucion no hay descarga: no afecta al servicio actual [V]. La proxima construccion de la imagen depende de que Hugging Face siga sirviendo los pesos obsoletos [H] | Baja | Registrado. "Retirar el codigo LFM" (R-8) no incluye esta parte: la fase C de ColBERT esta activa (`LFM_COLBERT_ENABLED=true`) |

Observaciones:
- La puerta manda al modelo justo las preguntas mas expuestas: las que nombran algo (Mercado Pago, DHL, Canada)
  que el documento puede no mencionar. Las genericas se sirven tal cual. La superficie de riesgo esta acotada, pero
  es la de mayor riesgo [V, codigo; H: riesgo].
- Temperatura: la configuracion `GPT4O_MINI_FALLBACK_CONFIG` dice 0,7, pero el cliente de la base de conocimiento
  la fija en 0,3 al crearlo [V, codigo]. Correcto para respuestas factuales; confuso al leer la configuracion.
- Respuesta en otro idioma que el documento (p. ej. cliente en frances con documento en espanol por el respaldo de
  idioma): el modelo traduce y resume a la vez. Los numeros deben sobrevivir; los nombres pueden cambiar de forma.
- El contenido de la demo es de ejemplo y tiene contradicciones entre paginas (R-14); para medir fidelidad da
  igual: el criterio es el documento que recibio el modelo, no la verdad de la tienda.
- Antecedente: el DCT anterior registra un caso comprobado (PayPal); este punto lo convierte en una medida.

## 4. Plan de la investigacion (decisiones del 23/11 [Y])

1. **Conjunto de preguntas** (laboratorio): para cada uno de los 8 temas con puerta, tres tipos de pregunta:
   - A, la respuesta esta en el documento ("Aceptan American Express?");
   - B, trampa, no esta ("Aceptan Mercado Pago?"); lo correcto es decir que no figura;
   - C, premisa que el documento contradice ("6 cuotas en una compra de $200?").
   Unas 6 preguntas por tema (2 de cada tipo), en es/en/fr: ~144 preguntas. Cada una con su respuesta esperada,
   escrita a partir del documento y ligada al hash del documento (si el documento cambia, se revisa la esperada).
2. **Banco de pruebas**: un script llama a `generate_contextual_answer()` con el mismo prompt, modelo y temperatura
   que produccion, con los documentos de `kb_contents` (solo lectura), 3 veces por pregunta para ver la
   variabilidad. Coste estimado: ~430 llamadas de ~1.300 tokens con GPT-4o-mini, del orden de 0,10-0,20 USD [H].
   Se ejecuta en el equipo de Yasmani: la clave de OpenRouter se lee de Secret Manager a una variable de entorno y
   se borra al terminar (mismo patron que `KB_CHECK_DSN`).
3. **Comprobacion automatica** de cada respuesta:
   - datos concretos (numeros con unidad o moneda, correos, telefonos, direcciones web y los nombres del registro
     de entidades: marcas, transportistas, paises, metodos de pago) deben aparecer en el documento o en los bloques
     de contexto; un dato que solo esta en la pregunta se marca como "eco de la pregunta" (revisar si lo afirma);
   - en las trampas (tipo B), la respuesta debe decir que el dato no figura (frases de abstencion en es/en/fr) y no
     afirmarlo;
   - normalizacion de formatos de numero (1.000 / 1,000 / 1 000) y de moneda.
4. **Revision manual**: todas las marcadas y una muestra al azar del resto (20 %).
5. **Medidas**: porcentaje de respuestas con algun dato sin respaldo; porcentaje de trampas respondidas con una
   afirmacion; longitud de las respuestas de tallas frente al limite (R-18). El umbral aceptable se decide con los
   datos [Y].
6. **Despues** (otro paso, laboratorio primero): correcciones segun lo que salga (prompt, limite de tokens de
   tallas, verificacion posterior y registro de la respuesta para R-17).

Decisiones (23/11) [Y], las tres propuestas:
- Via: llamar a `generate_contextual_answer()` directamente (aisla al modelo; no deja sesiones en produccion).
- Idiomas: es/en/fr.
- Documentos: `kb_contents`. Se leen con `GET /api/v1/kb/answer` (solo lectura), que es el mismo codigo
  que usa el chat (Redis -> PostgreSQL, con su respaldo de idioma): el texto es exactamente el que recibe el
  modelo y no hace falta la credencial de la base de datos.

## 5. Banco de pruebas (laboratorio, 23/11)

Paquete `KB_fidelity_harness.zip` (SHA-256 `e607882aa92f7f37fff0d4f2a1c2e93ce76be27977589593b98ed55dc55888e8`),
fuera del repo, en `C:\Users\yasma\Desktop\diag_14112026\kb_fidelity\`:

| Fichero | SHA-256 | Que es |
|---|---|---|
| `kb_fidelity_questions.json` | `135f5942...e38b5472` | 48 preguntas x es/en/fr (8 temas x 2 de cada tipo A/B/C), con lo que dice el documento y los datos esperados |
| `build_questions.py` | `e02ed669...836bdfa8` | Genera el JSON anterior (fuente legible del conjunto) |
| `run_kb_fidelity.py` | `6add5ce0...bf34c5962` | Banco de pruebas: camino de modelo leido de `env-vars.yaml`, documentos del endpoint, llamada al codigo real, captura de `finish_reason`/tokens/modelo envolviendo el cliente de OpenAI (sin tocar el repo); Claude desactivado |
| `check_kb_fidelity.py` | `f712643a...1730c25f` | Comprobador sin red: datos sin respaldo (numeros, correos, telefonos, URLs, nombres de un vocabulario), datos esperados, abstencion en trampas, cortes por limite de tokens; `report.csv`, `review.md`, `summary.md` |

Validacion en laboratorio [V], con el codigo real de `kb_contextualizer.py` y un modelo simulado (432
llamadas: respuestas fieles por defecto y 7 fallos inyectados: metodo de pago inventado, premisa aceptada, precio
inventado, correo inventado, telefono inventado, respuesta cortada y fallo del modelo):
- el comprobador marca exactamente los 7 casos inyectados, con las marcas esperadas, y ninguno mas (control
  negativo);
- 10 respuestas realistas escritas a mano (fieles e infieles, en es/en/fr) se clasifican como se esperaba tras
  dos correcciones: telefonos solo con prefijo `+` o entre parentesis (un patron laxo tomaba tablas de medidas
  por telefonos) y numeros esperados comparados como numero (`12,99` en frances = `12.99`);
- con un fallo del modelo, la ruta de Claude recibe el cliente desactivado y la llamada queda "sin respuesta".

Coste estimado de la ejecucion completa (432 llamadas a GPT-4o-mini): ~0,10 USD [H]. Duracion: ~5 min con
concurrencia 4 [H].

Limites conocidos del comprobador (por eso hay revision manual): no entiende negaciones ("no aceptamos X" da el
mismo dato que "aceptamos X"), ni numeros escritos con letras, ni afirmaciones sin datos concretos.

Prueba corta en el equipo de Yasmani (23/11, 14:26 UTC, 6 llamadas) [V]: camino de modelo leido de
`env-vars.yaml` (LFM apagado, GPT-4o-mini encendido); 24 documentos descargados (8 temas x es/en/fr; markdown de
`kb_contents`); 6 de 6 respuestas de `openai/gpt-4o-mini` con `finish_reason=stop`, temperatura 0,3 y limite 300
tokens [V: captura del banco de pruebas, confirma R-18 en ejecucion]; 6 OK; latencia mediana 1,2 s. Contra los
documentos reales descargados: todos los datos esperados de A y C estan en el documento de su idioma y ninguna
entidad de las trampas B aparece en el [V, laboratorio].

Incidencia: la prueba corta se ejecuto con el Python global (`C:\Python311`, `openai` 1.57.4) y no con el venv del
repo (`venv`, `openai` 3.16.2 como `requirements.cloudrun.txt`), porque el bloque llamaba a `python` sin ruta. El
resultado de la prueba corta es valido (el prompt, el modelo y los parametros salen del codigo del repo), pero la
ejecucion completa usa `venv\Scripts\python.exe` explicitamente. El envoltorio del cliente se probo tambien en el
laboratorio con `openai` 3.16.2: pasa [V].

## 6. Resultados de la primera medicion (run_23112026) [V]

Ejecucion 2026-11-23 15:14-15:16 UTC: 432 llamadas (48 preguntas x es/en/fr x 3 repeticiones), GPT-4o-mini por el
camino de produccion, venv del repo. Datos copiados del equipo de Yasmani al laboratorio: el comprobador da el
mismo resumen en los dos sitios y los SHA-256 de los documentos coinciden con los de cada llamada [V].

Revision manual de Claude (primera pasada) de **las 432 respuestas**, no solo de la muestra: el comprobador
automatico resulto ciego al tipo de error que aparecio (ver abajo). Juicios en
`C:\Users\yasma\Desktop\diag_14112026\kb_fidelity\revision_manual_run_23112026.md` (fuera del repo).

| Juicio | A (dato en el documento) | B (trampa) | C (premisa falsa) | Total |
|---|---|---|---|---|
| FIEL | 140 | 135 | 97 | 372 |
| INFERENCIA (deduce algo que el documento no dice) | 4 | 7 | 8 | 19 |
| ABSTENCION INDEBIDA (dice que no figura y si figura) | 0 | 0 | 8 | 8 |
| **INFIEL** (afirma algo que el documento no dice o contradice) | **0** | **2** | **27** | **29 (6,8 %)** |
| Sin respuesta (OpenRouter 402, R-21) | 0 | 0 | 4 | 4 |

Por idioma, INFIEL: es 10, en 6, fr 13. Preguntas con al menos una respuesta infiel: 7 de 48.

Lo que **no** ocurre [V]: **ningun dato inventado** (0 numeros, correos, telefonos, direcciones web o nombres sin
respaldo en 428 respuestas); **ninguna respuesta cortada**; en las trampas (B) el modelo reconoce que el dato no
figura en 135 de 144.

Lo que **si** ocurre: el modelo **razona mal cuando la pregunta trae una premisa falsa** (tipo C, 27 de 142
infieles, 19 %). Patrones:

| Patron | Ejemplo | Casos |
|---|---|---|
| Acepta la premisa del cliente | ORD-C2 "Hice el pedido hace 5 horas, puedo cancelarlo gratis?" -> "Si, ... porque hace menos de 2 horas" (en/fr); el documento: gratis solo antes de 2 h | 9 de 9 |
| Empieza con "Si" y despues se contradice | WAR-C1 "Si, te lo pueden cambiar por garantia ... Sin embargo, como han pasado 45 dias, no califica" | 5 (es/fr) |
| Atribuye mal un dato del documento | WAR-C1 fr: "60 jours pour les vetements" (60 son zapatos; ropa 30) | 1 |
| Razona mal con una tabla | SIZ-C1 cintura 70 / cadera 100 -> recomienda M; la cadera 100 esta en L (98-102) y la regla "entre dos tallas, la mayor" da L | 9 de 9 |
| Inventa una restriccion o una condicion | SHP-C2 es: "solo el envio estandar es gratis >50 $"; PAY-C1 fr: "cuotas solo >300 $"; SHP-B2 fr: "solo entregas a domicilio"; RET-B2 fr: "sin gastos" | 5 |

Otras observaciones:
- Abstencion indebida en RET-C2 ("me devuelven en efectivo?"): 8 de 9 dicen que el documento no lo indica, pero
  indica "reembolso al metodo de pago original". Ademas, en espanol "etiqueta" es ambigua (de la prenda o de
  devolucion) y el modelo la confunde.
- Frances: "D'apres le document, nous n'acceptons pas Mercado Pago/bitcoin" (6 de 6): presenta como dato del
  documento una deduccion.
- Incoherencia entre idiomas: RET-A2 responde "No" en espanol y "Si" en ingles y frances a la misma pregunta.
- Completitud (no fidelidad): PAY-A2 en ingles y en 2 de 3 en frances omite los umbrales de las cuotas.
- Variabilidad: 8 de 144 pares pregunta/idioma cambian de veredicto automatico entre repeticiones; ORD-C2 y SIZ-C1
  fallan en las 9 respuestas: el error es sistematico, no aleatorio.

**Exposicion en produccion**: de las 29 infieles, 16 pasarian la puerta y llegarian al cliente; las otras 13
(sobre todo frances y "cancelarlo") recibirian el documento completo por R-20. La puerta mala protege por
accidente: arreglar R-20 sin arreglar esto aumentaria la exposicion.

**El comprobador automatico detecto 1 de las 29** (WAR-C1 fr, por el 30 que faltaba). Comprueba datos
inventados, que no aparecieron; no comprueba conclusiones. Ademas, un dato esperado mio era incorrecto: en SIZ-C1
acepte "M" como respuesta valida y el documento da "L" [V]. Se corrige en la version 2 del conjunto.

Hallazgos nuevos:

| Id | Hallazgo | Gravedad | Estado |
|---|---|---|---|
| R-21 | **Saldo de OpenRouter bajo: 402 `in_flight_budget_exhausted`** en 4 de 432 llamadas con 4 en paralelo. OpenRouter retiene el coste estimado de las peticiones en curso y limita lo retenido a una fraccion del saldo; con saldo bajo, pocas peticiones simultaneas bastan para agotarlo [V: error de la API; documentacion de OpenRouter]. La misma clave da servicio a produccion: con varios clientes a la vez, la reformulacion fallaria y caeria a la ruta de Claude (R-11) o al documento tal cual | Media (operacion) | Comprobar el saldo en el panel de OpenRouter; decidir recarga o alerta |
| R-22 | **GPT-4o-mini acepta premisas falsas y razona mal con tablas** (seccion 6): 27 de 142 respuestas tipo C infieles; 0 datos inventados | Alta para un chat de tienda ("si, puede cancelar gratis", "si, lo cubre la garantia", talla equivocada) | Experimento en laboratorio (seccion 7) |

## 7. Comprobador v2 y experimento de prompt (decision del 23/11 [Y]: pasos 1 y 2)

1. **Comprobador v2** (laboratorio): en las preguntas tipo C la respuesta no debe empezar afirmando ("Si", "Yes",
   "Oui"); corregir el dato esperado de SIZ-C1 (L); anadir frases de abstencion que faltaban ("solo hay",
   "only provides"). Sirve para medir el antes y el despues sin repetir 432 revisiones manuales.
2. **Experimento de prompt** (laboratorio, sin tocar el repo): misma bateria y **mismos documentos**
   (`--docs-file docs_snapshot.json` de run_23112026) con un prompt que pida comprobar la premisa antes de
   contestar, no cambiar los datos del cliente y aplicar todas las medidas a la tabla. Comparar contra esta
   medicion. Si no basta, probar otro modelo con la misma bateria.
3. **R-21**: comprobar el saldo de OpenRouter (panel) antes de la siguiente ejecucion; la siguiente se lanza con
   concurrencia 2.

Paquete `KB_fidelity_harness_v2.zip` (SHA-256 `f5f6153f6ae698772fca516353466d4c3f10b396b7b8962ebf81ccdf72716cec`),
en `C:\Users\yasma\Desktop\diag_14112026\kb_fidelity\v2\` (la v1 se conserva al lado):

| Fichero | SHA-256 | Cambio |
|---|---|---|
| `kb_fidelity_questions.json` (+ `build_questions.py`) | `8158adcf...18bd37` (`8085fbe4...a8d704`) | v2: campo `premise_false` en las 16 de tipo C; SIZ-C1 espera L (v1 aceptaba M por error). Textos de las preguntas identicos a v1 [V, comparados] |
| `check_kb_fidelity.py` | `9ce80f32...0ab4f9` | Marca `afirma_premisa_falsa` si una respuesta tipo C empieza con "Si"/"Yes"/"Oui" (en espanol, "Si" sin tilde solo con coma: "Si tu pedido..." es condicional); frases de abstencion nuevas |
| `run_kb_fidelity.py` | `d1e2ab63...f0d9ac83` | `--prompt-variant` (aplica la variante en el envoltorio del cliente, justo antes de enviar; el resto del camino es el de produccion); hasta 4 reintentos del 402 transitorio (R-21); huella del prompt de sistema enviado en cada llamada |
| `compare_kb_fidelity.py` | `0f6870e0...84edb5` | Compara linea base y candidata con el comprobador v2; aborta si los documentos no son identicos |
| `prompt_v2_premisa.py` | `f81d4d25...38db0cee` | Variante: AÑADE al prompt de sistema una regla por patron de R-22 (comprobar la premisa antes de contestar y no empezar por "Si" salvo confirmacion completa; no cambiar los datos del cliente; no anadir condiciones; usar lo que el documento dice de forma indirecta; presentar las deducciones como deducciones) y, en tallas, cenirse a la guia (R-19) y comprobar cada medida aplicando la regla de "entre dos tallas". No quita nada del prompt actual |

Comprobador v2 medido contra la revision manual de run_23112026 (sin volver a llamar al modelo) [V]:

| Juicio manual | Marcadas por v1 | Marcadas por v2 |
|---|---|---|
| INFIEL (29) | 1 | **24** |
| ABSTENCION INDEBIDA (8) | 8 | 8 |
| FIEL (372) | 0 falsos positivos | **0 falsos positivos** |

Las 5 infieles que v2 no ve son condiciones o anadidos inventados con una respuesta que empieza bien ("No..."):
SHP-C2 es r3, PAY-C1 fr r2-r3, SHP-B2 fr r1, RET-B2 fr r1. Por eso la revision manual de la candidata cubre todas
las de tipo C, no solo las marcadas (`compare.md`).

Validacion en laboratorio del paquete v2 [V], con los documentos reales de run_23112026, modelo simulado y
`openai` 3.16.2 (la de produccion): la variante llega solo a la candidata y las reglas de tallas solo a tallas
(6 huellas de prompt por ejecucion: general y tallas x 3 idiomas); un 402 simulado dos veces se reintenta y
responde a la tercera; la comparacion detecta la mejora simulada (144 -> 0 premisas afirmadas). pyflakes limpio.

Linea base para la comparacion: run_23112026 (prompt de produccion), con sus mismos documentos
(`--docs-file`). No se repite la linea base: mismo dia, mismo modelo, temperatura 0,3; y con R-21 conviene
gastar lo minimo.

### 7.1 Resultado del experimento (run_v2_premisa_23112026) [V]

Ejecucion 2026-11-23 21:32-21:37 UTC, 432 llamadas, concurrencia 2, venv del repo (`openai` 3.16.2), saldo de
OpenRouter recargado por Yasmani: 0 sin respuesta y 0 reintentos. Hashes del paquete v2 verificados en el equipo
de Yasmani. Documentos identicos a la linea base (comprobado por `compare_kb_fidelity.py`); la variante se aplico
(6 huellas de prompt frente a 1). Datos copiados al laboratorio: mismo resumen [V].

Revision manual de las 432 respuestas, mismo criterio que la linea base
(`kb_fidelity\revision_manual_run_v2_premisa_23112026.md`):

| Juicio | Linea base | v2_premisa |
|---|---|---|
| FIEL | 372 | 379 |
| INFERENCIA | 19 | 38 |
| ABSTENCION INDEBIDA | 8 | 3 |
| **INFIEL** | **29** | **12** |
| Sin respuesta | 4 | 0 |
| INFIEL que llegarian al cliente (pasan la puerta) | 16 | 12 |
| Preguntas con alguna respuesta infiel | 7 de 48 | 2 de 48 |

Por tipo, INFIEL: A 0 -> **3**; B 2 -> 0; C 27 -> 9. Por idioma: es 10 -> 3, en 6 -> 4, fr 13 -> 5.

Lo que corrige la variante: aceptar la premisa (ORD-C2, 9 -> 0), empezar con "Si" y contradecirse (WAR-C1,
6 -> 0), condiciones inventadas (PAY-C1 fr, SHP-C2 es, SHP-B2 fr, RET-B2 fr: 5 -> 0) y casi todas las
abstenciones indebidas (8 -> 3). Las reglas generales funcionan.

Lo que no corrige o empeora:
- **Tallas, el punto debil**: SIZ-C1 sigue mal en las 9 (recomienda M con cadera de 100 cm, que es L), y la regla
  de tallas **introduce un error nuevo**: con 90 cm de busto (dentro de M, 88-92) el modelo ve un limite que no
  existe; 3 respuestas recomiendan L (SIZ-A1 en r2, fr r1-r2) y 5 aciertan la talla con un razonamiento falso. Con
  los dos prompts, 18 de 18 respuestas fallan SIZ-C1: no es un problema de redaccion sino de calculo [V].
- **"No" categorico**: la regla "empieza con un 'No' claro" se generaliza. Las trampas pasan de "el documento no
  menciona Mercado Pago" a "No, no aceptamos Mercado Pago" (inferencias 19 -> 38), y aparecen "No," de apertura en
  respuestas correctas de tipo A (SIZ-A2 en r1, PAY-A2 en r1).
- Comun a las dos ejecuciones (sin cambio): "el documento no menciona la viscosa" (la menciona una vez);
  "no se puede lavar la lana en lavadora" (el documento admite ciclo delicado).

Comprobador v2 sobre la candidata: detecta 9 de las 12 infieles (no ve las 3 de SIZ-A1, porque "M" aparece en la
respuesta aunque recomiende L) y da 7 falsos positivos por raices esperadas incompletas ("remplace" no coincide
con "remplacer"; "no incluye" no estaba entre las frases de abstencion) [V].

Defectos del conjunto de preguntas vistos en la revision (para la version 3): RET-C2 es ambigua ("sin etiqueta":
de la prenda o de devolucion; el modelo la lee como etiqueta de devolucion); RET-A2 mezcla procesamiento y
reembolso (el documento solo da el plazo de procesamiento).

### 7.2 Opciones para el siguiente paso (pendiente de decision [Y])

1. **Prompt v3** (laboratorio, barato): mantener las reglas generales; cambiar "empieza con 'No'" por "corrige
   primero la premisa" y "si no figura, di que no figura, no que no se ofrece"; **quitar la regla de tallas** que
   creo el error de SIZ-A1. Mide el resto sin tocar tallas.
2. **Tallas por calculo y no por el modelo** (estructural): el modelo no calcula bien tallas con varias medidas, y
   ningun prompt lo arreglo. Hoy no hay calculo de tallas a partir de la guia (el asistente de tallas F-02 usa el
   historial del cliente) [V, codigo]. Opciones: (a) un calculador que lea la tabla de la guia de tallas de
   `kb_contents` y decida la talla en codigo, y el modelo solo la redacta; (b) que el modelo devuelva las medidas y
   rangos en una salida estructurada y el codigo decida. Implica disenar el formato de tabla que se exige a cada
   tienda (encaja con el verificador de contenido del punto 4 del plan).
3. **Otro modelo** con la misma bateria (por ejemplo uno mayor de la misma familia): mide si el problema de tallas
   y el "No" categorico son del modelo o del enfoque.

Propuesta de Claude: 1 y 2 en paralelo (1 en laboratorio ya; 2 empezando por leer como llegan las tablas de tallas a
`kb_contents`), y 3 solo si 1 no basta.

**Decision (23/11) [Y]: 1 y 2 en paralelo; 3 solo si 1 no basta.**

### 7.3 Paso 1 y 2 en laboratorio (v3)

Como llega la guia de tallas a `kb_contents` [V, docs_snapshot de run_23112026]: markdown con dos tablas limpias
en los tres idiomas: ropa de mujer (`Talla | Busto | Cintura | Cadera`, rangos `80-84`; en frances `Taille |
Tour de poitrine | Tour de taille | Tour de hanches`) y zapatos (`US | EU | UK | CM`), mas la regla "si estas entre
dos tallas, elige la mayor". Los rangos comparten el limite (S 84-88, M 88-92).

**Calculador de tallas** (`size_chart_calculator.py`, prototipo, no esta en el repo):
- lee las tablas markdown de la guia y las clasifica (ropa o zapatos) por sus encabezados en es/en/fr/de/it;
  "Taille" sola es la columna de talla y "tour de taille" la cintura;
- extrae de la pregunta las medidas en cm (busto, cintura, cadera, pie) por clausulas ("70 cm de cintura y 100 cm
  de cadera"), con coma decimal ("24,5 cm");
- decide la talla con la regla de la guia: medida en el limite comun -> la mayor; medidas en tallas distintas ->
  la mayor; medida fuera de la tabla -> no hay talla (no se adivina);
- genera un bloque "SIZE CALCULATION ... RECOMMENDED CLOTHING SIZE: L" con la explicacion por medida.
- **Decision de diseno pendiente [Y]**: aplicar "la mayor" cuando las medidas caen en tallas distintas es la
  lectura habitual de una guia, pero la de la demo no lo dice literalmente.
- 40 tests [V] con las guias reales es/en/fr y una alemana inventada. Control negativo con tres mutaciones del
  codigo (elegir la menor; partir "24,5" por la coma; tomar "taille" como cintura): cada una hace fallar tests
  (6, 16 y 1) [V].

**Prompt v3** (`prompt_v3.py`): fuera de tallas, reglas de v2 sin "empieza con un 'No' claro" (ahora "corrige
primero la premisa") y con "si no figura, di que no figura; no digas que no se ofrece". En tallas: prompt de
sistema de produccion sin cambios y, delante del documento, el bloque del calculador (solo si la pregunta trae
medidas). Asi el efecto se atribuye por tema.

**Conjunto de preguntas v3**: RET-A2 -> RET-A2b (plazo de procesamiento, que si esta en el documento) y RET-C2 ->
RET-C2b ("a los 10 dias, en efectivo?", sin la ambiguedad de "etiqueta"); raices esperadas en WAR-C2; `forbid_any`
en SIZ-A1 (no recomendar L ni S). Al cambiar dos preguntas, la linea base se repite con el conjunto v3.

**Comprobador v3**: termino prohibido (`dato_prohibido`), negacion categorica en trampas (`negacion_categorica`,
informativa), frases de abstencion nuevas, sin negritas de markdown. Medido contra las dos revisiones manuales
[V]: linea base 24 de 29 infieles detectadas y 0 falsas alarmas; v2_premisa 11 de 12 (no ve "size, which is L") y
3 marcas por respuesta incompleta (ORD-C1 es no menciona la devolucion).

Validacion del paquete v3 en laboratorio [V] (modelo simulado, documentos reales, `openai` 3.16.2), mirando lo que
se enviaria al modelo: linea base sin cambios; fuera de tallas, prompt de sistema = produccion + reglas v3 y mensaje
intacto; en tallas, prompt de sistema = produccion y bloque con la talla correcta en las 12 llamadas con medidas
(SIZ-A1 M, SIZ-A2 US 8, SIZ-C1 L, SIZ-C2 XL) y en ninguna sin medidas; comparacion operativa. pyflakes limpio.

Paquete `KB_fidelity_harness_v3.zip` (SHA-256 `d5f26e36d7c222a26a7dfe63e593a4cbad9e181467cd608e7c7a07f0ea5cac50`)
en `C:\Users\yasma\Desktop\diag_14112026\kb_fidelity\v3\`. `run_kb_fidelity.py` es identico al de v2
(`d1e2ab63...`). Ejecucion prevista: linea base (prompt de produccion) y v3, ambas con el conjunto v3 y los
documentos de run_23112026.

### 7.4 Resultado de v3 (run_base_v3 y run_v3, 23/11 22:39-22:46 UTC) [V]

En el equipo de Yasmani: hash del zip correcto; 40 tests del calculador pasados con el venv del repo; las dos
ejecuciones con 432 llamadas, 0 sin respuesta, 0 reintentos; variante `v3` aplicada (sha `c59882fa...`); 36 llamadas
con bloque de talla (12 con medidas x 3), 0 en la linea base. Datos copiados al laboratorio: misma comparacion.

Revision manual de las 864 respuestas, mismo criterio (`kb_fidelity\revision_manual_runs_v3.md`):

| Juicio | run_23112026 (produccion) | run_base_v3 (produccion) | v2_premisa | **v3 + calculador** |
|---|---|---|---|---|
| FIEL | 372 | 387 | 379 | **404** |
| INFERENCIA | 19 | 16 | 38 | 22 |
| ABSTENCION INDEBIDA | 8 | 0 | 3 | 0 |
| **INFIEL** | 29 | 29 | 12 | **6** |
| INFIEL que llegarian al cliente | 16 | 18 | 12 | **3** |
| Sin respuesta | 4 | 0 | 0 | 0 |

(run_base_v3 usa RET-A2b/RET-C2b en lugar de RET-A2/RET-C2: por eso desaparecen las abstenciones indebidas.)

- **La linea base es estable**: 29 infieles en las dos ejecuciones con el prompt de produccion, con los mismos
  patrones (ORD-C2 9/9, SIZ-C1 9/9, WAR-C1 "Si... sin embargo", condiciones inventadas en frances).
- **El calculador resuelve las tallas**: SIZ-C1 9 -> 0 (L en las 9, con la explicacion por medida); SIZ-A1 sin
  errores (la regla de v2 que los creaba se quito); SIZ-C2 correcta. Queda un detalle de redaccion: 2 respuestas
  en frances dicen que 70 cm esta "a la limite de M".
- **Las reglas v3 corrigen** WAR-C1 (4 -> 0), condiciones inventadas (6 -> 0) y la negacion categorica de v2 ("No,
  no aceptamos Mercado Pago": 9 -> 0; ahora "el documento no menciona Mercado Pago").
- **Lo que queda: ORD-C2 en ingles y frances, 6 de 6** ("You can cancel... you placed it 5 hours ago, which is
  within the 2-hour window"). En espanol, bien. v2 lo resolvia con "empieza con un 'No' claro", que se quito por sus
  efectos secundarios. Es otra comparacion numerica (5 h frente a 2 h), la misma clase de fallo que las tallas.
  Exposicion real: 3 (ingles; en frances la puerta no deja pasar "annuler" + "5 heures", R-20).
- Inferencias (22): sobre todo anadidos de conocimiento general en tallas ("medir en la parte mas ancha del busto")
  y "podria danar el tejido"; ninguna afirma algo contrario al documento.

Comprobador: una regla mas amplia de apertura afirmativa en tipo C ("Si/Puedes", "Yes/You can", "Oui/Vous pouvez")
marca en las cuatro ejecuciones solo infieles (15/15, 0/0, 13/13, 6/6; 0 falsas alarmas) y detecta las 6 de v3 [V].
Se incorpora en la version 4 del comprobador.

### 7.5 Propuesta (pendiente de decision [Y])

El paso 1 queda casi suficiente: de 29 a 6 infieles, todas en un unico caso (comparar las horas del cliente con
el limite del documento). Antes de pasar al paso 3 (otro modelo), una iteracion corta:

1. **v4 = v3 + una regla de comparacion explicita**: "cuando el cliente da un numero (horas, dias, importe,
   medida) y el documento da un limite, compara los dos y escribe la comparacion antes de concluir (p. ej. '5 horas
   es mas que el limite de 2 horas')".
2. **Preguntas de control nuevas** (para no ajustar el prompt a una sola pregunta): 4 de tipo C con comparaciones
   numericas distintas de ORD-C2 (p. ej. pedido hecho hace 3 horas; zapatos rotos a los 70 dias; compra de 90 $ en
   3 cuotas; devolucion a los 31 dias). Se miden en la linea base y en v4.
3. Si ORD-C2 o las preguntas nuevas siguen fallando en ingles o frances: paso 3 (otro modelo con la misma bateria).

Despues, propuesta de implementacion en el repo, un cambio por despliegue: primero el calculador de tallas (el
cambio estructural, con sus tests) y despues las reglas del prompt.

**Decisiones (24/11) [Y]**: cuando las medidas caen en tallas distintas, el calculador aplica "elige la mayor";
seguir con la iteracion v4 de 7.5.

### 7.6 v4 en laboratorio

- `prompt_v4.py`: reglas de v3 copiadas sin cambios (comprobado: texto identico) + **una** regla nueva de
  comparacion explicita ("cuando el cliente da un numero y el documento un limite, escribe primero la comparacion,
  p. ej. '5 horas es mas que el limite de 2 horas', y despues la conclusion"). Tallas: igual que v3 (prompt de
  produccion + bloque del calculador).
- Conjunto v4 (54 preguntas): las 48 de v3 + 6 de control con comparaciones numericas que el prompt no ha "visto":
  4 de tipo C con el numero fuera del limite (ORD-C3 pedido hace 3 h; WAR-C3 zapatos a los 70 dias; PAY-C3 compra
  de 90 $ en 3 cuotas; RET-C3 devolucion a los 31 dias) y 2 de tipo A con el numero dentro (ORD-A3 30 minutos;
  WAR-A3 40 dias), para detectar el efecto contrario (responder "No" a todo, como con v2). Datos esperados
  comprobados contra los documentos reales en los tres idiomas [V].
- Comprobador v4: apertura afirmativa ampliada ("Puedes", "You can" sin "not/'t", "Vous pouvez"); detecta las 6
  infieles de v3 [V].
- Calculador: solo cambia el comentario de la decision. 40 tests pasados [V].
- Validacion en laboratorio con modelo simulado [V]: fuera de tallas, prompt = produccion + reglas v3 + regla de
  comparacion; tallas, como v3 (12 llamadas con bloque).
- Paquete `KB_fidelity_harness_v4.zip` (SHA-256 `f2b2eef2451ac9f7e156750d9e8b8dc2061d72be849442cd9143e81d527204a8`).
  Ejecucion prevista: linea base (produccion) y v4 con el conjunto v4 y los documentos de run_23112026
  (2 x 486 llamadas).

### 7.7 Resultados de v4 (ejecucion del 24/11, revision manual completa) [V]

Ejecuciones (UTC): `run_base_v4` 23:14:44-23:18 (prompt de produccion) y `run_v4` 23:18:54-23:23:31 (v4 +
calculador). 486 llamadas cada una, 0 sin respuesta, 0 reintentos, 36 bloques de talla en la candidata; hashes de
los ficheros comprobados antes de ejecutar. Revisadas a mano las 972 respuestas con el mismo criterio que v1-v3
(`manual_labels_r4.py`; detalle en `revision_manual_runs_v4.md`).

**48 preguntas comunes con v3** (432 respuestas por ejecucion):

| Ejecucion | INFIEL | llegaria al cliente | INFERENCIA | ABSTENCION INDEBIDA |
|---|---|---|---|---|
| run_base_v3 (produccion) | 29 | 18 | 16 | 0 |
| run_v3 (v3 + calculador) | 6 | 3 | 22 | 0 |
| run_base_v4 (produccion) | 24 | 15 | 11 | 0 |
| run_v4 (v4 + calculador) | **0** | **0** | 32 | 0 |

**Preguntas de control** (respuestas correctas, es decir no INFIEL, de 3 por idioma; produccion -> v4):

| Pregunta | Tipo | es | en | fr |
|---|---|---|---|---|
| ORD-C2 (5 h, cancelar gratis) | C | 0 -> 3 | 0 -> 3 | 0 -> 3 |
| ORD-C3 (3 h, cancelar gratis) | C | 0 -> 3 | 3 -> 3 | 0 -> 3 |
| WAR-C3 (zapatos, 70 dias) | C | 3 -> 3 | 0 -> 3 | 3 -> 3 |
| PAY-C3 (90 $ en 3 cuotas) | C | 3 -> 3 | 3 -> 3 | 3 -> 3 |
| RET-C3 (devolucion a los 31 dias) | C | 3 -> 3 | 3 -> 3 | 3 -> 3 |
| ORD-A3 (30 min, cancelar gratis) | A | 3 -> 3 | 3 -> 3 | 3 -> 3 |
| **WAR-A3 (zapatos, 40 dias)** | A | 3 -> 3 | **3 -> 0** | **3 -> 0** |

- **Lo que v4 arregla**: ORD-C2 9/9 ("5 horas es mas que el limite de 2 horas"), las 4 preguntas de control de
  tipo C y todo lo que quedaba en las 48 comunes. En produccion, los controles confirman el problema: ORD-C3 6 de
  9 y WAR-C3 en ingles 3 de 3 infieles ("70 dias esta dentro de los 60").
- **Lo que v4 rompe**: WAR-A3 en ingles y frances, 6 de 6: "40 days is more than the 60-day warranty coverage...
  not covered". La comparacion se escribe, pero **al reves**, y se niega una garantia que si corresponde. En
  produccion WAR-A3 sale bien 9 de 9. En espanol v4 responde bien porque no usa la plantilla ("La garantia cubre
  60 dias. Como tu problema ocurrio a los 40 dias, si esta cubierto"). Exposicion: 3 (ingles; en frances la puerta
  no deja pasar la pregunta, R-20).
- Hipotesis [H]: la regla obliga a escribir la comparacion antes de razonar, y GPT-4o-mini rellena la forma de los
  ejemplos del prompt ("X es mas que el limite de Y") sin comparar los numeros. Ordenar el texto no hace que el
  calculo sea correcto.
- **Error de diseno mio**: el ejemplo de la regla ("$90 is less than the $100 minimum") usa los mismos numeros que
  PAY-C3, asi que PAY-C3 no es un control independiente para v4. No cambia la conclusion: PAY-C3 ya salia bien 9/9
  en produccion y ninguna conclusion se apoya en ella. Leccion en la seccion 8.
- **Variacion de la linea base**: el mismo prompt de produccion dio 29 infieles el 23/11 y 24 el 24/11 en las mismas
  48 preguntas (mismos patrones: ORD-C2 9/9, SIZ-C1 9/9, WAR-C1). Diferencias de unas 5 respuestas son ruido de
  muestreo; por eso cada variante se compara con su linea base del mismo dia.
- Inferencias en las 48 comunes (32 en v4, 22 en v3): "60 C podria danar el tejido" (7), instrucciones de medida
  de conocimiento general en tallas (7), "no puedes cancelar gratis" cuando el documento dice "consultar
  disponibilidad" (6, y 6 mas en los controles), "puedes devolver el pedido danado" (4), "express no es gratis
  sobre 30 $" sin el umbral de 50 $ (3), "70 cm esta en el limite de M" (2) y 3 sueltas. Ninguna contradice el
  documento; las de cancelacion son mas prudentes que el documento.
- Coste y latencia [V, results.jsonl]: v4 envia ~420.000 tokens de entrada por ejecucion (produccion ~297.000:
  las reglas anaden ~250 tokens por llamada); mediana 1,06 s frente a 0,96 s.

### 7.8 Decision segun la regla acordada (24/11)

Regla [Y]: "si ORD-C2 y las 4 preguntas de control de tipo C salen bien sin romper las 2 de tipo A, propuesta para
el repo; si no, paso 3 (otro modelo con la misma bateria)". **WAR-A3 se rompe (6 de 9): se pasa al paso 3.** La
regla de comparacion (v4) se descarta; el calculador de tallas y las reglas de v3 siguen siendo candidatos.

Diseno del paso 3 (laboratorio):
- Banco de pruebas v5: opcion `--model` que sustituye el modelo de la llamada a OpenRouter justo antes de enviar;
  todo lo demas (prompt, documento, temperatura 0,3, limite 300, puerta) sigue siendo el de produccion. Antes de
  empezar comprueba en la lista publica de OpenRouter que el identificador existe. Validado con modelo simulado
  [V]: sin `--model` se envia `openai/gpt-4o-mini`; con `--model X` las 162 llamadas van a X y queda anotado el
  modelo que pedia el codigo; combinado con v3, 144 prompts con reglas y 12 bloques de talla; un identificador mal
  escrito aborta. Prueba de mutacion: sin la linea que sustituye el modelo, la prueba falla [V].
- Ejecuciones (conjunto v4, documentos de run_23112026, 486 llamadas cada una):
  1. GPT-4o-mini + v3 + calculador: referencia que faltaba (v3 no se midio con las preguntas de control).
  2. Por cada modelo candidato: prompt de produccion, y v3 + calculador.
- Criterio para elegir modelo (antes de ver los datos): 0 infieles que llegarian al cliente en las 48 comunes,
  ORD-C2 y los 4 controles C bien en los tres idiomas, ORD-A3 y WAR-A3 bien; despues, coste y latencia frente a
  GPT-4o-mini (el banco registra tokens y milisegundos por llamada).
- Alternativa estructural si ningun modelo cumple: comparar en codigo los umbrales del cliente con los del
  documento, como el calculador de tallas. Es mas dificil (los umbrales estan en texto libre y cambian por tienda),
  por eso va despues.
- Modelos candidatos: ver 7.9 (decision pendiente [Y]).

### 7.9 Paso 3 ampliado con R-8 y R-11 (propuesta del 24/11, pendiente de decision [Y])

Propuesta de Yasmani: aprovechar el paso 3 para cerrar R-8 (sustituto de LFM o retirada del codigo) y R-11
(respaldo Claude con modelos retirados). Hechos de partida:

- **Una sola configuracion para tres usos** [V, codigo 57de04c]: `GPT4O_MINI_FALLBACK_CONFIG` alimenta la
  reformulacion de la base de conocimiento (`kb_contextualizer.py` L1202), el redactor de respuestas de producto
  (`mcp_personalization_engine.py` L144) y el calentamiento (`main_unified_redis.py` L1593). Cambiar su modelo
  cambia los tres. La bateria de fidelidad solo mide el primero.
- **R-8 tiene tres partes**: (a) modelo de la reformulacion: la bateria lo decide; (b) modelo del redactor de
  producto: otra tarea (tono, productos citados), que la bateria no mide; ahi encaja el banco de 20 consultas
  reales previsto en R-8; (c) identificadores a configuracion y metrica de que camino responde: codigo, sea
  cual sea el modelo.
- **R-11 debe corregirse**: el 16/11 se recomendo `claude-haiku-4-5-20251001`. La documentacion de Anthropic
  (captura del 24/11) la marca como *legacy*, con retirada "no antes del 15/10/2026" (fecha ya pasada) y
  sustituta Claude Haiku 5.5. Pasar a Haiku 4.5 seria repetir R-11. Ademas, `main_unified_redis.py` L1701 tiene
  `claude-haiku-4-5-20251001` fijo en el codigo y `kb_contextualizer.py` L1236 `claude-3-haiku-20240307` como
  valor de emergencia [V].
- **El ultimo respaldo de la reformulacion ya es fiel**: si fallan los modelos, se sirve el documento tal cual.
  El escalon Claude aporta disponibilidad de la reformulacion, no seguridad; su valor real es no depender de
  OpenRouter (caida o saldo, R-21), porque hoy LFM y GPT-4o-mini van por el mismo proveedor [H: decision de
  producto].

Candidatos (capturas de OpenRouter y de Anthropic del 24/11; precios por millon de tokens):

| Modelo | Precio entrada / salida | Para la bateria | Motivo |
|---|---|---|---|
| `openai/gpt-4.1-mini` | 0,40 / 1,60 | Si | Sin razonamiento previo (mismo contrato que hoy); latencia ~0,9 s; enrutado en la UE disponible (Azure, plan Business) |
| Claude Haiku 5.5 (identificador de OpenRouter por comprobar) | "desde" 0,10 / 0,50 | Si | Sustituto vigente de Haiku 4.5; razonamiento adaptativo: vigilar latencia y que la respuesta llegue en `content` |
| `liquid/lfm-3-1.7b` (de pago) | 0,08 / 0,20 | Si, solo para cerrar R-8 | 1,7B parametros, indice de inteligencia 6,0; **razona antes de responder** (el comentario de `LFM_KB_CONFIG` ya documenta que los modelos que razonan devuelven `content=None`); latencia extremo a extremo P90 ~20 s frente al limite de 8 s; aviso "los prompts y respuestas pueden conservarse y usarse para entrenar" |
| `liquid/lfm-2.5-24b-a2b` | por comprobar | Solo si existe | Candidato de R-8 [H]; la pagina de OpenRouter tambien enlaza `lfm-2-24b-a2b`, que da 404, asi que un enlace no prueba que este disponible; el banco v5 lo comprueba |
| `liquid/lfm-3-1.7b:free` | gratis | No | Mismo modelo que el de pago; disponibilidad 96,4 % en 3 dias; uso para entrenamiento |
| `liquid/d1.2` | 0,02 / 0 | No | No redacta texto: devuelve la probabilidad de un si/no. Idea para despues (R-24): verificador "esta respuesta esta respaldada por el documento?" antes de enviar (R-17) o clasificador de la puerta (R-20). Publicado el 14/11/2026 |
| Claude Haiku 4.5 | 1 / 5 | No | *Legacy*, retirada posible en cualquier momento |

Diseno propuesto, en dos fases para que la revision manual siga siendo completa:
1. **Criba** con las preguntas de premisa y comparacion numerica (subconjunto del conjunto v4 en un fichero de
   preguntas aparte; el banco no cambia), cada candidato con v3 + calculador, mas GPT-4o-mini como referencia.
   Revision manual completa del subconjunto.
2. **Finalistas**: conjunto v4 completo con prompt de produccion y con v3 + calculador, revision manual
   completa, latencia (p50 y p95 de `llm_ms`) y coste por tokens.

Orden en el repo si un modelo gana (un cambio por despliegue): (1) configuracion por uso y no por proveedor
(modelo de la reformulacion separado del redactor), identificadores en `env-vars.yaml` y metrica de que camino
responde, sin cambiar ningun modelo; (2) calculador de tallas; (3) reglas v3; (4) cambio de modelo de la
reformulacion, solo con configuracion.

Decisiones que pide la propuesta [Y]: candidatos; si el aviso de entrenamiento de Liquid es aceptable para
preguntas de clientes (en junio, el criterio RGPD/nLPD descarto a DeepSeek); alcance de R-8 (b); y si se
mantiene un respaldo fuera de OpenRouter (R-11).

### 7.10 Decisiones del 24/11 y diseno de la criba

Decisiones [Y]:
1. Candidatos aprobados (`gpt-4.1-mini`, Claude Haiku 5.5, `lfm-3-1.7b` de pago, `lfm-2.5-24b-a2b`), con
   libertad para anadir otros modelos Liquid. **Evaluar las capacidades de Liquid antes de retirar codigo LFM.**
2. R-8 (b), redactor de producto: decision delegada a Claude tras valorar volumen y contexto (abajo).
3. R-11: se mantiene el respaldo Claude (aporta disponibilidad); pasara a un modelo vigente (Haiku 5.5) y a
   configuracion.

Catalogo de Liquid (liquid.ai/models, 24/11) [V]:
- Texto vigente: LFM3-1.7B, LFM2.5-24B-A2B (13/10/2026), LFM2.5-1.2B-Instruct, LFM2.5-1.2B-Thinking,
  LFM2.5-230M, LFM2.5-350M, LFM2.5-8B-A1B. **Obsoletos: LFM2-24B-A2B** (el del redactor) y otros LFM2: explica los
  404 de R-8. LFM2.5-1.2B-Instruct (el tipo de modelo que eligio el comentario de `LFM_KB_CONFIG`) solo figura en
  Hugging Face y la documentacion, no en OpenRouter.
- En OpenRouter, los dos de texto disponibles **razonan siempre antes de responder**: LFM2.5-24B-A2B
  ("always reasons before answering"; 24B totales, 2,45B activos; 0,05 / 0,70 $ por millon; contexto 128K;
  P50 0,17 s y 165 tok/s; sin aviso de entrenamiento en su ficha) y LFM3-1.7B (con aviso de entrenamiento).
- Decision (d1.x): clasificacion, enrutado y puntuacion con probabilidades calibradas; no redactan. No sirven
  para reformular, pero si para R-24: con las respuestas ya etiquetadas a mano (972 de v4 y las de v1-v3) se
  puede medir directamente si d1.2 distingue fieles de infieles. Experimento aparte, despues de la criba.
- Otros: modelos de extraccion, PII y ColBERT (R-26). Ninguno de RAG vigente (LFM2-1.2B-RAG esta obsoleto).

Consecuencia para la criba: con el limite actual (300 tokens, 8 s), un modelo que razona puede agotar el
limite antes de responder y, por R-25, el cliente veria el razonamiento. Eso diria que la configuracion actual
no le sirve, no que el modelo sea malo. Por eso cada Liquid se mide dos veces: en condiciones de produccion y en
**modo capacidad** (4.000 tokens, sin limite de tiempo). Si solo funciona en modo capacidad, adoptarlo exige
cambiar limite y tiempo de espera, y corregir R-25.

Banco v6 (laboratorio) [V]:
- Anota por llamada `content_empty`, `reasoning_chars`, `reasoning_tokens` y `answer_from_reasoning` (R-25).
  Prueba: modelo simulado que razona y deja `content` vacio -> 63 de 63 respuestas son el razonamiento y las 63
  quedan marcadas; modelo normal -> 0. Mutacion (anulando la marca): la prueba falla.
- Modo capacidad: `--max-tokens N` (anota el limite que pedia el codigo) y `--no-timeout` (solo dentro de
  `kb_contextualizer`). Prueba con un modelo de 9 s: sin la opcion se pierden 4 de 4 por el limite de 8 s; con
  ella llegan 4 de 4; el `asyncio` real no cambia. Mutacion: la prueba falla.
- `list_openrouter_models.py`: inventario de solo lectura, sin clave (identificador exacto, precio, contexto,
  si puede razonar, proveedores). Probado con la API simulada; mutacion de la deteccion de razonamiento: falla.
- `build_criba.py` -> `kb_fidelity_questions_criba.json`: 21 preguntas del conjunto v4 copiadas sin cambios
  (comprobado): 11 C (PAY-C1, SHP-C2, RET-C1, WAR-C1, SIZ-C1, SIZ-C2, ORD-C2, ORD-C3, WAR-C3, PAY-C3, RET-C3),
  7 A (PAY-A2, WAR-A1, SIZ-A1, CAR-A1, ORD-A1, ORD-A3, WAR-A3) y 3 B (PAY-B1, PAY-B2, ORD-B1). 189 respuestas por
  ejecucion; revision manual completa.
- Paquete `KB_fidelity_harness_v6.zip` (SHA-256
  `dc33f4c8cd6e5e1ed51c128c8e9e16ffa69253f30ce58ee50f879270705dbd1d`; `build_criba.py` escribe con saltos de
  linea `\n` para que el conjunto regenerado en Windows tenga el mismo hash).

Ejecuciones de la criba (todas con v3 + calculador): GPT-4o-mini (referencia), `gpt-4.1-mini`,
`claude-haiku-5.5`, `lfm-2.5-24b-a2b` (produccion y capacidad) y `lfm-3-1.7b` (produccion y capacidad).
Coste estimado del orden de 1 USD; peor caso ~1,5 USD si los Liquid agotan los 4.000 tokens en todas las
llamadas del modo capacidad [H].

**R-8 (b), redactor de producto: se deja para justo despues del paso 3** (decision de Claude, 24/11):
- Volumen: el prompt del redactor lo construyen ~900 lineas (`mcp_personalization_engine.py` L2617-L3507:
  perfil, estrategia, precios, venta adicional, mercado) [V]. Medirlo exige otro banco (capturar los prompts
  reales de la app en local y reproducirlos con cada modelo), otros criterios (productos solo de la lista,
  precios correctos, idioma, tono) y otra revision manual: del orden de una o dos sesiones [H].
- Contexto: nada obliga a hacerlo ahora. LFM esta apagado y el redactor funciona con GPT-4o-mini; el primer
  cambio del repo (configuracion por uso) separa los dos modelos, asi que la reformulacion puede cambiar sin
  tocar el redactor. Mezclar dos evaluaciones a la vez va contra "un cambio cada vez". Las "20 consultas
  reales" no existen en la demo (2 consultas a la base de conocimiento en 30 dias): serian sinteticas igual.
- La criba aporta a (b): un modelo que falla en fidelidad o en latencia aqui dificilmente servira de redactor.
- **El codigo generador de LFM no se retira hasta decidir (b)**: LFM2.5-24B-A2B, sucesor del modelo del
  redactor, se evalua tambien alli. La parte de ColBERT no se toca en ningun caso (R-26).

### 7.11 Resultados de la criba (24/11, 03:40-03:51 UTC) [V]

Siete ejecuciones de 189 respuestas, 0 errores de API, hashes del paquete v6 comprobados. Inventario de
OpenRouter (03:38 UTC): `anthropic/claude-haiku-5.5` (0,10 / 0,50 $, cinco proveedores), `liquid/lfm-2.5-24b-a2b`
y `liquid/lfm-3-1.7b` (solo el proveedor Liquid, ambos "pueden razonar"); Haiku 4.5 sigue listado. Revision manual
completa de las 1.323 respuestas (`manual_labels_criba.py`, `stats_criba.py`, detalle en
`revision_manual_criba.md`).

| Modelo | FIEL | INFER. | INFIEL | Razonamiento enviado | Cortada | Vacia | Fallos | Llegarian | R-23 | p50 / p95 ms | >8 s | USD / 189 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT-4o-mini (hoy) | 159 | 26 | 4 | 0 | 0 | 0 | 4 | 1 | 7 | 1203 / 1841 | 0 | 0,024 |
| **GPT-4.1-mini** | **182** | 7 | **0** | 0 | 0 | 0 | **0** | **0** | 2 | 1195 / 1725 | 0 | 0,065 |
| Claude Haiku 5.5 | 128 | 7 | 0 | 0 | 30 | 24 | 54 | 27 | 7 | 1172 / 2030 | 0 | 0,037 |
| LFM2.5-24B-A2B, produccion | 4 | 0 | 0 | **177** | 8 | 0 | 185 | 125 | - | 1025 / 1239 | 0 | 0,046 |
| LFM2.5-24B-A2B, capacidad | 179 | 9 | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 2323 / 5481 | 4 | 0,119 |
| LFM3-1.7B, produccion | 9 | 0 | 0 | **167** | 13 | 0 | 180 | 120 | - | 1053 / 1178 | 0 | 0,022 |
| LFM3-1.7B, capacidad | 161 | 25 | 2 | 0 | 0 | 0 | 2 | 2 | 1 | 1850 / 4513 | 1 | 0,040 |

(1 respuesta de ABSTENCION INDEBIDA en LFM3 capacidad. "Llegarian": fallos que pasan la puerta de produccion.
R-23: "No" a la lavadora en CAR-A1, contado aparte.)

Controles (respuestas completas y sin error, de 9): GPT-4.1-mini y LFM2.5-24B-A2B en capacidad, **9 de 9 en
los diez** (ORD-C2, ORD-C3, WAR-C3, PAY-C3, RET-C3, SIZ-C1, WAR-C1, ORD-A3, WAR-A3, WAR-A1). GPT-4o-mini: ORD-C2
5 de 9 ("Oui... il y a moins de 2 heures" con 5 horas, igual que en v3). Haiku 5.5: WAR-C3 0, WAR-C1 0, SIZ-C1 2,
WAR-A3 2 (respuestas vacias o cortadas, no incorrectas). LFM3 en capacidad: WAR-A1 7 (dice que una costura
que se descose a la semana "suele considerarse desgaste normal").

Lo que dice cada resultado:
- **R-25 confirmado con modelos reales**: en condiciones de produccion, el cliente habria recibido el
  razonamiento interno de LFM2.5-24B-A2B en 177 de 189 respuestas y el de LFM3-1.7B en 167 (en ingles, p. ej.
  "We need to answer the customer's question: ... We need to check the policy document..."). 125 y 120 pasarian
  la puerta.
- **GPT-4.1-mini cumple todos los criterios fijados antes de ver los datos**: 0 infieles, 0 fallos, todos los
  controles en los tres idiomas, misma latencia que GPT-4o-mini. Coste ~2,7 veces (0,00034 frente a 0,00013 USD
  por llamada).
- **LFM2.5-24B-A2B tiene la capacidad** (179 fieles, 1 infiel, controles 9 de 9, el unico sin R-23), pero solo
  con un presupuesto que produccion no le da: razona entre ~600 y ~3.400 tokens (maximo 3.379 de 4.000), p95 de
  5,5 s y 4 llamadas de mas de 8 s; cuesta ~5 veces GPT-4o-mini y ~1,8 veces GPT-4.1-mini. Adoptarlo exigiria
  limite de tokens >= 4.000, otro tiempo de espera y corregir R-25.
- **LFM3-1.7B queda descartado** para la reformulacion: 2 infieles (inventa equivalencias de tallas de zapato;
  niega la garantia de una costura), 25 inferencias y aviso de uso para entrenamiento.
- **Claude Haiku 5.5 no es concluyente**: sus respuestas completas son fieles (0 infieles), pero el limite de 300
  tokens produce 54 fallos (R-27). Hay que medirlo en modo capacidad, como a Liquid; el resultado sirve tambien
  para configurar R-11.
- GPT-4o-mini con v3 repite el unico fallo conocido de v3 (ORD-C2 en frances y uno en ingles).

### 7.12 Fase de finalistas (propuesta, 24/11)

Finalistas: GPT-4.1-mini y LFM2.5-24B-A2B (capacidad). Ejecuciones con el conjunto v4 completo (54 preguntas,
486 respuestas cada una), documentos de run_23112026:
1. GPT-4o-mini, prompt de produccion: linea base del mismo dia.
2. GPT-4.1-mini, prompt de produccion: si ya cumple, basta un cambio (el modelo) sin reglas nuevas.
3. GPT-4.1-mini, v3 + calculador.
4. LFM2.5-24B-A2B, v3 + calculador, modo capacidad.
5. Claude Haiku 5.5, criba en modo capacidad (189): cierra R-27 y orienta R-11.

Revision manual completa de las 2.133 respuestas; coste estimado ~0,8 USD [H]. Criterio de eleccion (fijado
antes): 0 infieles que lleguen al cliente, controles 9 de 9 en los tres idiomas; despues, numero de cambios en
el repo, latencia y coste.

### 7.13 Resultados de los finalistas y decision (24/11)

Ejecutadas por Yasmani el 24/11 (zip finalistas_24112026). Comprobacion tecnica [V]: en las cinco ejecuciones,
finish=stop 100 %, 0 respuestas vacias, 0 razonamiento como respuesta, 0 errores. Revision manual completa de
las 2.133 respuestas por Claude (lab: `manual_labels_fin.py` SHA256 `ae3d2074...1989`, `stats_fin.py`
`97bc3470...5952`, revision legible `fin/revision_manual_finalistas.md` `e09b1af8...a0`). Criterios de
etiquetado: los de la criba, mas cinco nuevos escritos en el docstring de `manual_labels_fin.py` (lana "a mano
o ciclo delicado" sin preferencia; 30 C es la regla general, no la del denim; excepcion inventada por "defecto
grave"; ancla inventada del plazo de devolucion; cancelar "desde tu cuenta").

| Ejecucion | N | FIEL | Infer. | Abst. | INFIEL | Fallos | Llegarian | R-23 | p50 / p95 ms | max ms | >8 s | USD/1.000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT-4o-mini, prompt produccion (hoy) | 486 | 435 | 17 | 0 | **34** | 34 | **18** | 9 | 1063 / 1947 | 3259 | 0 | 0,112 |
| GPT-4.1-mini, prompt produccion | 486 | 453 | 31 | 0 | 2 | 2 | **0** | 0 | 1074 / 1679 | 7192 | 0 | 0,306 |
| GPT-4.1-mini, v3 + calculador | 486 | 463 | 21 | 0 | 2 | 2 | 2 | 1 | 1078 / 1621 | 3192 | 0 | 0,384 |
| LFM2.5-24B-A2B, v3 + calc., capacidad | 486 | 456 | 26 | 3 | 1 | 1 | 1 | 1 | 2254 / 4448 | 9090 | 1 | 0,540 |
| Haiku 5.5, v3 + calc., capacidad (criba) | 189 | 174 | 11 | 4 | 0 | 0 | 0 | 4 | 1430 / 3000 | 4340 | 0 | 0,214 |

Controles (ORD-C2, ORD-C3, WAR-C3, PAY-C3, RET-C3, SIZ-C1, WAR-C1, ORD-A3, WAR-A3, WAR-A1; superado = las 3
repeticiones del idioma son FIEL o INFERENCIA): GPT-4.1-mini (los dos prompts) **10 de 10 en los tres idiomas**.
GPT-4o-mini falla 5: ORD-C2 (es, en, fr: "Si/Yes/Oui... menos de 2 horas" con 5 horas), ORD-C3 (es, fr), SIZ-C1
(los tres: recomienda M), WAR-C1 (es, fr: "Si... cubierta" a los 45 dias) y WAR-C3 (en: "Yes, covered" a los 70
dias). LFM2.5: PAY-C3 en ("the document does not confirm"). Haiku 5.5: WAR-A1 fr (duda de un caso cubierto).

Lo que dice cada resultado:
- **La linea base del dia confirma el problema**: GPT-4o-mini con el prompt de produccion da 34 infieles, 18 de
  ellos con la puerta abierta (llegarian al cliente), y falla 5 de los 10 controles.
- **GPT-4.1-mini con el prompt de produccion cumple los criterios** [V]: 0 infieles que lleguen al cliente,
  controles 10 de 10, 0 R-23, misma latencia que hoy (p50 1074 frente a 1063 ms). Recomienda L en SIZ-C1 9 de 9
  sin calculador. Sus 2 infieles (RET-C2b fr rep 2 y 3: "Oui, vous pouvez retourner..." a "me remboursez-vous en
  especes ?") tienen la puerta cerrada hoy: **llegarian si R-20 abre la puerta al frances** (ver riesgos).
  Sus 31 inferencias se concentran en "no figura -> no aceptamos" (PAY-B1/B2: 12) y "nationwide" (SHP-B2: 4).
- **El prompt v3 no se adopta con GPT-4.1-mini**: baja las inferencias (31 -> 21; elimina "no aceptamos") pero
  introduce 2 infieles con la puerta abierta: ORD-A1 es rep 1 y 2, "No, no puedes cancelar tu pedido una hora
  despues" (1 h < 2 h). Es el efecto ya visto de "empieza con un 'No'" (seccion 8). Mejor media, peor en el
  criterio que decide.
- **LFM2.5-24B-A2B no gana**: 1 infiel con la puerta abierta (SIZ-C2 en rep 1, "Yes, you should choose XL" a
  "should I choose L?"), latencia doble (p95 4,4 s, maximo 9,1 s, 1 llamada > 8 s) y coste 1,8 veces GPT-4.1-mini,
  ademas de exigir R-25 y otro limite de tokens. Su capacidad queda documentada para R-8(b); el codigo LFM no se
  retira hasta decidir R-8(b).
- **R-27 resuelto** [V]: con presupuesto de capacidad, Haiku 5.5 da 0 vacias, 0 infieles, mediana de 141 tokens
  de salida y maximo de 852. Los 54 fallos de la criba eran el limite de 300 tokens, no el modelo.

**Decision propuesta (pendiente de "aplicalo")**: GPT-4.1-mini (`openai/gpt-4.1-mini`) como modelo de la
reformulacion KB, **con el prompt de produccion actual**, sin reglas v3 y sin calculador de tallas (el codigo de
ambos queda en el lab). Coste: ~0,0003 USD por respuesta (~2,7 veces hoy; en valor absoluto, despreciable al
volumen de la tienda de demostracion).

**R-11 (respaldo Claude)** [H, a validar en el lab]: pasar a `claude-haiku-5-5` desde configuracion, con
max_tokens >= 1.024 (maximo observado 852) y el mismo tiempo de espera de 8 s (maximo observado 4,3 s).
Precision (24/11, lectura del codigo) [V]: el escalon Claude de la reformulacion (`kb_contextualizer.py`
L1229-1236) y el del redactor (`mcp_personalization_engine.py` L1626-1634) toman el modelo del secreto
`CLAUDE_MODEL_TIER` (HAIKU -> `claude-3-haiku-20240307`, SONNET -> `claude-sonnet-4-20250514`, OPUS ->
`claude-3-opus-20240229`; sin secreto en produccion: SONNET); `claude-3-haiku-20240307` en L1236 es solo el valor
de emergencia si falla esa lectura. Valor del secreto: **HAIKU** [Y, consola 25/11; ya registrado en R-11 el 16/11
con el log `Resolved CLAUDE_MODEL_TIER 'HAIKU' to claude-3-haiku-20240307`, en `jsonPayload.event`], es decir, un
modelo retirado: hoy el escalon Claude fallaria en los dos usos. Ademas, el secreto **`CLAUDE_MAX_TOKENS` = 200**
[Y] sobrescribe el limite del codigo en el redactor (`get_model_config()` aplica `_apply_environment_overrides`);
la reformulacion KB solo toma el nombre del modelo y usa su propio limite (250, 500 en tallas). Con Haiku 5.5,
200 tokens repetirian R-27 en el redactor: **R-11 exige cambiar tambien (o retirar) `CLAUDE_MAX_TOKENS`**. `claude-haiku-4-5-20251001` en `main_unified_redis.py` aparece en el warm-up de Claude (L1468) y en el
keep-alive (L1701), los dos **comentados / no arrancados** (L1455-1480 y L1734-1746): codigo muerto hoy, a
corregir o quitar al tocar R-11, no un camino activo. R-11 pasa por cambiar `ClaudeModelTier` (o el secreto) a
un modelo vigente, no por cambiar L1701.

**Riesgos y seguimiento**:
- R-20 (puerta en frances) y el cambio de modelo interactuan: antes de abrir la puerta al frances hay que medir
  de nuevo RET-C2b y las preguntas fr con el modelo elegido.
- Una sola ejecucion de 3 repeticiones por modelo; la linea base vario entre dias (29 frente a 24). La validacion
  en produccion se hace con linea base del mismo dia.
- "No figura -> no aceptamos" (12 respuestas) queda como inferencia conocida; si se quiere corregir, una regla
  unica y medida en todas las preguntas (experimento aparte).

**Orden de implantacion en el repo** (un cambio por despliegue, lab primero, "aplicalo" obligatorio):
1. Configuracion por uso: separar el modelo de la reformulacion KB del redactor de producto y del warm-up (hoy
   comparten `GPT4O_MINI_FALLBACK_CONFIG`), identificadores en `env-vars.yaml` y metrica de que ruta respondio.
   Sin cambio de comportamiento (sigue GPT-4o-mini).
2. Cambio del modelo KB a `openai/gpt-4.1-mini` por configuracion; validacion con linea base del mismo dia.
3. R-11: respaldo Claude a Haiku 5.5 por configuracion (R-27).
4. Despues: R-8(b), redactor de producto (captura y reproduccion).

### 7.14 Paso 1: configuracion por uso y metrica de caminos (laboratorio, 25/11)

Decision de seguir el plan: Yasmani, 25/11 [Y]. Codigo leido del repo (`feature/visual_search`, HEAD `84a61b4`,
ficheros de `src` sin cambios locales) [V].

**Correccion: eran cuatro usos, no tres** [V, `git grep` 25/11]. `GPT4O_MINI_FALLBACK_CONFIG` tambien alimenta el
mensaje de la busqueda visual (`visual_search_router.py` L161-169: max_tokens 120 fijado alli, temperatura 0.7,
espera de 8 s, con su propio calentamiento `warmup_vs_gpt4o_singleton`), activo en produccion
(`VISUAL_SEARCH_ENABLED=true`). La respuesta del 24/11 a Yasmani ("tres usos") era incompleta.

| Uso | Escalones (en orden) | Ultimo recurso sin LLM | Peticion al modelo principal (hoy) |
|---|---|---|---|
| Reformulacion KB | LFM (apagado) -> principal -> Claude | documento tal cual | gpt-4o-mini, 300 tokens, 0.3, 8 s |
| Redactor de producto | LFM (apagado) -> principal -> Claude | mensaje generico | gpt-4o-mini, 300 tokens, 0.7, 8 s |
| Mensaje de busqueda visual | LFM (apagado) -> principal | plantilla del frontend | gpt-4o-mini, 120 tokens, 0.7, 8 s |
| Calentamiento de arranque | - | - | gpt-4o-mini, 1 token, 0.7, 14 s |

**Cambio** (lab, sin aplicar; paquete `paso1_patch.zip`):
- `claude_config.py`: se retira `GPT4O_MINI_FALLBACK_CONFIG`; una funcion por uso, nombrada por quien la usa
  (`get_kb_reformulation_llm_config`, `get_product_redactor_llm_config`, `get_visual_search_message_llm_config`)
  con su variable de modelo (`KB_REFORMULATION_LLM_MODEL`, `PRODUCT_REDACTOR_LLM_MODEL`,
  `VISUAL_SEARCH_MESSAGE_LLM_MODEL`). max_tokens y temperatura quedan en el codigo con los valores de hoy; solo el
  modelo pasa a configuracion (es lo unico que cambia el paso 2). Variable ausente o vacia -> `openai/gpt-4o-mini`
  con `model_source=default` en el log. Se lee el entorno en cada llamada y se devuelve un dict nuevo.
  `get_openrouter_warmup_models()`: modelos de KB y redactor sin repetir.
- `env-vars.yaml`: las tres variables con `openai/gpt-4o-mini` (38 -> 41 variables planas).
- `llm_routes.py` (nuevo) + `prometheus_metrics.py`: contador `recommender_llm_route_total{use, route}` con 12
  combinaciones validas (KB: lfm, main_model, claude, template, document_as_is; redactor: lfm, main_model, claude,
  generic_message; busqueda visual: lfm, main_model, no_message), pre-inicializadas a 0. Prefijo `recommender_`:
  lo exporta `gcp_metrics_exporter.py` sin cambios. `record_llm_route()` nunca lanza y rechaza combinaciones
  desconocidas (cardinalidad).
- `kb_contextualizer.py`, `mcp_personalization_engine.py`, `visual_search_router.py`: usan su configuracion y
  cuentan el camino en cada salida. En el redactor, una marca distingue "Claude respondio" de "se quedo el
  mensaje generico" (antes indistinguibles en el codigo).
- `main_unified_redis.py`: el calentamiento usa `get_openrouter_warmup_models()`, en paralelo; hoy una llamada
  identica a la anterior.
- Se conservan nombres de singletons, el interruptor `GPT4O_MINI_FALLBACK_ENABLED` y los textos de log existentes
  (solo se anaden campos), para no romper busquedas de logs. Renombrarlos es un cambio aparte.
- `tests/unit/test_llm_use_config_and_routes.py` (nuevo): 37 pruebas.

**Evidencia de laboratorio** [V] (Python 3.13, dependencias de produccion sin las de ML):
- Diferencial con dobles del cliente LLM: la peticion de cada uso (proveedor, modelo, max_tokens, temperatura) es
  **identica** con el codigo original y con el nuevo; el calentamiento hace la misma llamada (1 token, 0.7).
- 37/37 pruebas nuevas; fallan con el codigo original (control negativo). 19/19 mutantes detectados.
- `tests/unit` completo: 544 -> 581 aprobadas (+37), y **los mismos** 39 fallos y 12 errores de recoleccion
  que la linea base (dependencias que faltan en el laboratorio, no en el venv del repo).
- pyflakes: ningun aviso nuevo.
- Ejecutor de la bateria v7: lee `KB_REFORMULATION_LLM_MODEL` de `env-vars.yaml` si existe (para el paso 2).

**Limites** [H]: el calentamiento se comprobo extrayendo la funcion del fichero real (esta anidada en `lifespan`);
las pruebas del venv de Windows son las que cuentan. Si el manejador externo cancela al redactor por tiempo, esa
peticion no se cuenta. La metrica crea un descriptor nuevo en Cloud Monitoring (mismo patron que los contadores
existentes, incluidas las muestras `_created`).

**Hallazgo R-29** (anadido a la tabla de la seccion 3).

**Validacion en produccion prevista** (despues de "aplicalo", commit y despliegue; linea base del mismo dia):
1. Logs (`jsonPayload.event`): cada cliente se registra al crearse con `model=openai/gpt-4o-mini
   model_source=env` (redactor y busqueda visual al arrancar; reformulacion KB en su primera pregunta); una sola
   llamada `gpt4o_mini_warmup_complete`.
2. `/metrics` expone las 12 series de `recommender_llm_route_total`; tras una pregunta KB, sube
   `use="kb_reformulation",route="main_model"`; tras un chat de producto, `product_redactor/main_model`.
3. Respuestas KB es/en/fr, chat de producto y busqueda visual como antes; `ERROR` tras el despliegue: 0.
4. Vuelta atras: trafico a `00346-f5w`.

**Aplicacion y despliegue (25/11)** [V]:
- Ensayo del parche: 9 ficheros en BASE; aplicado con verificacion de hash. Suite completa en el venv de Windows
  (`compare_junit.py`): 1.364 -> 1.401 tests, las 37 nuevas en verde, **0 fallos nuevos** (167 fallos y 37 errores
  previos, identicos).
- Commit `fceb1aa` (16:23); los 9 ficheros del commit tienen el hash del laboratorio (`prometheus_metrics.py`
  comparado sin CR: git lo guarda con LF).
- Imagen `:fceb1aa`, `sha256:9842b3c7...19e9c5`, construida en 12 min; desplegada con `gcloud run services update
  --image <digest> --env-vars-file env-vars.yaml`: revision **`00347-lgs`**, 100 % del trafico (16:53 hora local).

Incidencias del camino (sin efecto en produccion): un primer intento de validacion se hizo sin commit ni Docker en
marcha y valido la revision antigua; se detecto por los logs (formato antiguo de `gpt4o_mini_warmup_started`, sin
`model=`) y por 49 variables. La guardia del bloque 4 impidio construir una imagen con codigo sin commit.

**Validacion en produccion (25/11, 17:16 hora local)** [V]:

| Comprobacion | Antes (`00346-f5w`) | Despues (`00347-lgs`) |
|---|---|---|
| Variables (secretas) | 49 (11) | 52 (11); las tres `*_LLM_MODEL` = `openai/gpt-4o-mini` |
| Digest desplegado == construido | - | si |
| `/kb/answer` policy_return es/en/fr | 200: 487 / 430 / 500 caracteres | 200: 487 / 430 / 500 |
| Pregunta KB "Aceptan pagos con Mercado Pago?" | 987-1.234 ms, contextualizada, "el documento no menciona..." | 1.392 ms (primera peticion de la instancia), misma respuesta |
| Chat de producto con consulta nueva | 2.419 ms, texto redactado | 3.001 ms (primera de la instancia), texto redactado |
| Configuracion en logs | - | redactor, busqueda visual y KB con `model_source=env`; una sola llamada de calentamiento con `model=openai/gpt-4o-mini` |
| `recommender_llm_route_total` | no existe (control: 25 series de `recommender_requests_total`) | 12 series; `kb_reformulation/main_model` = 1 y `product_redactor/main_model` = 1 tras las dos sondas; resto 0 |
| `ERROR` | 0 (ultima hora) | 0 (revision nueva) |
| Avisos | - | 68: lotes de la sincronizacion KB limitados (57), Redis lento en el arranque (2), sesiones nuevas de las sondas (4) y otros ya conocidos; ninguno de `llm_route` |

El registro de la reformulacion KB (`KB GPT-4o-mini singleton created ... model_source=env`, 16:16:47 UTC) no
salio en la consulta del bloque 5, lanzada segundos despues; si esta en los logs descargados (retraso de ingesta).
La frase de la busqueda visual no se ejercito (necesita subir una imagen) [H: misma configuracion y mismo
patron que los otros dos usos; su cliente se registro con `model_source=env`].

**Paso 1 cerrado.** Siguiente: paso 2 (modelo de la reformulacion KB a `openai/gpt-4.1-mini` por configuracion).
El paso 2 tiene que cambiar tambien la prueba `test_env_vars_yaml_declares_todays_model_for_every_use`, que hoy
exige `openai/gpt-4o-mini` en los tres usos.

Cierre documental: commit `f5b0b83`; `fceb1aa` y `f5b0b83` subidos a `origin/feature/visual_search` el 26/11 [Y].

### 7.15 Paso 2: reformulacion KB con GPT-4.1-mini (laboratorio, 26/11)

Decision de seguir: Yasmani, 26/11 [Y]. `openai/gpt-4.1-mini` sigue disponible en OpenRouter, sin aviso de
retirada, a 0,40 / 1,60 USD por millon de tokens de entrada / salida [V, pagina del modelo, 26/11].

**Cambio** (2 ficheros; sin codigo y sin imagen nueva):
- `env-vars.yaml`: `KB_REFORMULATION_LLM_MODEL: "openai/gpt-4.1-mini"`; las otras dos variables siguen en
  `openai/gpt-4o-mini` (el redactor y la busqueda visual no tienen bateria de fidelidad: R-8(b)).
- `test_llm_use_config_and_routes.py`: la prueba de `env-vars.yaml` pasa a exigir el modelo decidido por uso. El
  valor por defecto del codigo no cambia (`openai/gpt-4o-mini`, con `model_source=default` en el log).

**Evidencia de laboratorio** [V]: 37/37 pruebas; con el `env-vars.yaml` anterior la prueba nueva falla (control
negativo). Diferencial con las variables del fichero: la reformulacion KB pide `openai/gpt-4.1-mini` con 300 tokens
y temperatura 0.3 (las condiciones medidas en la fase de finalistas, ejecucion "41Mp"); redactor y busqueda visual,
identicos a hoy. El calentamiento pasa a dos modelos en paralelo (`gpt-4.1-mini`, `gpt-4o-mini`).

**Despliegue previsto**: solo configuracion. `gcloud run services update --env-vars-file env-vars.yaml` sobre la
imagen del paso 1 (`sha256:9842b3c7...`); guardias: commit hecho, HEAD con el modelo decidido e imagen actual igual a
la del paso 1. Vuelta atras: trafico a `00347-lgs`.

**Validacion prevista en produccion** (el efecto del modelo en el servicio real, no solo en el laboratorio): 9
preguntas x 3 repeticiones contra `/v1/mcp/conversation`, antes (`00347-lgs`) y despues, guardando respuesta
completa, intencion detectada, reformulacion y tiempo. Seis son controles que pasan la puerta y que GPT-4o-mini
fallaba 3 de 3 en el laboratorio (ORD-C2 en, WAR-C1 es, WAR-C3 en, SIZ-C1 es/en/fr); tres son preguntas que ambos
modelos respondian bien (RET-C2b es, PAY-C1 es, PAY-B1 es). Revision manual con los criterios de la seccion 7.13.
Ademas: logs con `model=openai/gpt-4.1-mini` en las respuestas KB, dos llamadas de calentamiento, `ERROR` = 0.

**Aplicacion y despliegue (26/11)** [V]:
- Yasmani habia cambiado a mano el valor en `env-vars.yaml` antes de ejecutar [Y]; el script de aplicacion lo
  clasifico como OTRO y no aplico nada (correcto). En consecuencia el commit **`09d68da`** lleva solo la linea del
  modelo (sin el comentario) y **no** la prueba actualizada: en `HEAD` la prueba de `env-vars.yaml` falla (1 de
  37), como mostro `paso2_1_pruebas.ps1`. El valor desplegado es el correcto (difiere del laboratorio solo en 4
  lineas de comentario). Se corrige con un commit de seguimiento (prueba + comentario), sin despliegue.
- Despliegue de configuracion sobre la imagen del paso 1: revision **`00348-lhc`**, 100 % del trafico, misma imagen
  (`sha256:9842b3c7...`), 52 variables (11 secretas).

**Validacion en produccion (26/11, 09:56-10:08 hora local)** [V]:

| Comprobacion | Antes (`00347-lgs`, gpt-4o-mini) | Despues (`00348-lhc`, gpt-4.1-mini) |
|---|---|---|
| `KB_REFORMULATION_LLM_MODEL` | `openai/gpt-4o-mini` | `openai/gpt-4.1-mini`; redactor y busqueda visual sin cambio |
| Modelo que respondio (logs de la reformulacion KB) | - | `openai/gpt-4.1-mini` en 21 de 21 |
| Calentamiento | 1 modelo | 2 en paralelo (`gpt-4.1-mini` devolvio 10 tokens con `max_tokens=1` [V, log]; coste despreciable) |
| Sondas reformuladas (de 27) | 21 | 21 |
| Tiempo de las reformuladas, mediana (max) | 1.789 ms (3.055) | 1.447 ms (2.408) |
| `kb_reformulation/main_model` en `/metrics` | 21 | 21 |
| Errores en sondas / `ERROR` en logs | 0 / - | 0 / 0 |

Revision manual de las 54 respuestas (criterios de 7.13):

| Pregunta | Antes (gpt-4o-mini) | Despues (gpt-4.1-mini) |
|---|---|---|
| SIZ-C1 es/en/fr (cintura 70, cadera 100, "talla S?") | **INFIEL 9/9**: "elige la M" (la cadera 100 no cabe en M, 94-98) | **Recomienda L 9/9**. es y fr FIEL (6); en INFERENCIA (3): "your measurements fall into the size L range" y "waist 70 between M and L" (la cintura 70 es M), conclusion correcta |
| PAY-B1 es (Mercado Pago) | FIEL 3/3 ("el documento no menciona") | INFERENCIA 3/3: "no aceptamos Mercado Pago" (patron ya medido en el laboratorio, 12 de 31) |
| PAY-C1 es (6 cuotas con $200) | FIEL 3/3 | FIEL 3/3 |
| RET-C2b es (reembolso en efectivo) | FIEL 3/3 | FIEL 3/3 |
| WAR-C1 es (cremallera a los 45 dias) | Mal enrutada a `policy_return` (R-32). INFERENCIA 1 ("no se puede cambiar"), FIEL 2 respecto al documento de devoluciones | Igual enrutamiento; FIEL 3/3 respecto al documento de devoluciones |
| WAR-C3 en, ORD-C2 en | No llegan a la reformulacion (R-32): menu de ayuda / documento tal cual | Igual |

Resultado: **respuestas infieles que llegan al cliente: 9 -> 0**; inferencias: 1 -> 6, del tipo ya conocido. Es el
perfil medido en el laboratorio. La primera peticion de la fase "antes" tardo **112 s** (arranque en frio de una
instancia de `00347-lgs`) [V]; no es efecto del cambio, pero es lo que veria un cliente tras un periodo sin
trafico (ver `CloudRun_MinInstances_Architecture_Analysis`).

**Paso 2 desplegado y validado** (pendiente el commit de seguimiento de la prueba).

### 7.16 R-32: enrutamiento de garantia y pedidos (laboratorio, 26/11)

**Pregunta**: por que tres preguntas de las sondas no llegan a su documento (WAR-C1 es a devoluciones, WAR-C3 en a
`unknown`, ORD-C2 en a `account_modifications`) y cuantas preguntas mas de la bateria estan en el mismo caso.

**Como se mide**: un simulador de enrutado (`r32_enrutado.py`) ejecuta el detector hibrido de produccion (mismo
codigo, mismos `.pkl`, mismas variables: `ML_CONFIDENCE_THRESHOLD=0.8`, `INTENT_CONFIDENCE_THRESHOLD=0.7`,
`MINILM_BACKEND=torch`) sobre las 54 preguntas x es/en/fr y aplica la misma decision de umbral que
`mcp_conversation_handler.py`. Guarda lo que dijo cada capa aunque no se use (puntuacion de cada sub_intent en la
capa 1, intent y confianza de la capa 2, las 3 etiquetas MiniLM mas cercanas). Sin produccion ni LLM. Los 5
ficheros del detector y los 2 `.pkl` del laboratorio tienen el mismo hash que el repo en `cf9882e` [V].
El laboratorio no puede descargar MiniLM (HuggingFace bloqueado), asi que aqui corren las capas 1 y 2; la
ejecucion completa se hace en el `venv` local (mismas versiones que `requirements.cloudrun.txt` [V]).

**Recordatorio del flujo** (lectura de `intent_detection.py` y `hybrid_detector.py`) [V]:
1. Capa 1 (reglas): cada sub_intent suma 0,4 por palabra clave, +0,3 si hay palabra de pregunta, +0,2 por
   contexto negativo. Gana la puntuacion **estrictamente** mayor: en un empate gana el sub_intent declarado
   antes (`policy_return` esta antes que `policy_warranty`). Solo es informacional con 0,7 o mas.
2. Si la confianza de la capa 1 es **menor** que 0,8, capa 2 (sklearn, solo informacional/transaccional). Con 0,8
   exactos la capa 1 decide sola.
3. GUARD: si la capa 1 dijo transaccional con un patron real (p. ej. "comprar", "take", "get") y la capa 2 dice
   informacional, se mantiene transaccional. Solo hay excepcion para necesito/quiero/need/want.
4. Si la capa 2 cambia a informacional, el sub_intent pasa a `unknown` y se consulta MiniLM; su etiqueta se usa
   si el coseno es 0,50 o mas.

**Resultado de las capas 1 y 2** [V, laboratorio]: 68 de las 162 consultas no pasan por MiniLM (su ruta es
definitiva); 57 aciertan y **11 fallan**. Las otras 94 (51 fr, 24 es, 19 en) dependen de MiniLM: pendiente de la
ejecucion local.

| Consulta | Va a | Mecanismo |
|---|---|---|
| WAR-C1 es "...se rompe a los 45 dias, ¿me lo cambian por garantia?" | devoluciones | M1: `garantia` es palabra clave de `policy_return` y `dias` tambien: 0,8 frente a 0,4 de garantia. 0,8 = umbral, decide la capa 1 |
| WAR-C3 es y WAR-A3 es "...se despego a los 70/40 dias..., ¿lo cubre la garantia?" | devoluciones | M1 (igual) |
| WAR-A2 en "How long is the warranty on shoes...?" | devoluciones | M1 + empate 0,7 / 0,7: gana el declarado antes |
| WAR-A1 es "Se me descosio una costura a la semana de comprar..., ¿lo cubre la garantia?" | **productos** | M2: empate 0,4/0,4 (no informacional); "comprar" activa transaccional y el GUARD ignora a la capa 2 (informacional 0,76) |
| RET-A2b en "Does processing a return take 5-7 business days?" | **productos** | M2: "take" |
| ORD-B2 en "Do I get a discount coupon if my order was lost?" | **productos** | M2: "get" |
| ORD-B1 es/en "Mi pedido llego danado, ¿me mandan uno nuevo gratis?" | envios | M3: `pedido`/`order` son palabras clave de envios y de pedidos; "mandan"/"send" suman a envios |
| CAR-A2 en "At what temperature should I wash cotton clothes?" | materiales | M3: "cotton" + "what" (0,7) frente a "wash" sin palabra de pregunta (0,4) |
| CAR-C1 fr "Puis-je laver mon jean a 60°C...?" | productos | Sin reglas en frances; la capa 2 dice transaccional (0,63) |

Mecanismos:
- **M1 - palabras clave de garantia dentro de devoluciones**: `policy_return` incluye `garantia|warranty` y
  `dias|plazo|tiempo`. Cualquier pregunta de garantia que mencione un plazo puntua mas en devoluciones.
- **M2 - verbos de compra comunes que bloquean a la capa 2**: "comprar", "take", "get" aparecen en preguntas de
  politica ("a la semana de comprar", "take 5-7 days", "do I get a coupon") y el GUARD impide que la capa 2 las
  corrija. El resultado es peor que un documento equivocado: el cliente recibe productos.
- **M3 - palabras compartidas entre sub_intents** (pedido/order, cotton+what): el sub_intent con mas
  coincidencias gana aunque la pregunta sea de otro.

**Ejecucion completa en el equipo local (26/11, 16:33)** [V]: mismas versiones que produccion, los 7 hashes
coinciden, capa 3 cargada en 8,4 s. **Control: 9 de 9 consultas de las sondas de produccion coinciden** (sub_intent y
metodo), incluidas 3 resueltas por MiniLM (ORD-C2 en, SIZ-C1 fr, RET-C2b es). Las capas 1 y 2 dan exactamente lo mismo
en el laboratorio que en el equipo local (162 de 162).

Que recibe el cliente en las 162 consultas (la ruta se traduce en contenido leyendo las paginas de Shopify, 26/11):

| Resultado | Consultas | es | en | fr |
|---|---|---|---|---|
| Documento correcto | **93** | 33 | 32 | 28 |
| Menu de ayuda (`unknown`, pagina `mensaje-de-ayuda-general`) | 29 | 5 | 9 | 15 |
| Pagina `cancelaciones-y-modificaciones-de-pedidos` (contradice a la correcta, ver R-34) | 16 | 6 | 5 | 5 |
| Otro documento de la tienda | 19 | 9 | 5 | 5 |
| Productos (busqueda de catalogo) | 5 | 1 | 3 | 1 |

Por tema: pagos 21/21 y tallas 18/18 correctos; envios 10/18; devoluciones 16/21; cuidados 13/18;
**materiales 6/18; pedidos 5/24; garantia 4/24**.

Por capa que decidio:

| Metodo | Correcto | Fallo | Fallos |
|---|---|---|---|
| Capa 1 (reglas) | 37 | 8 | M1, M2, M3 (tabla anterior): 5 a otro documento, 3 a productos |
| Capa 2 (sklearn) | 20 | 33 | **29 al menu de ayuda**: la capa 2 dice "informacional" sin tema y MiniLM no llega a 0,50 (coseno 0,26-0,48); 2 a otro documento; 2 a productos |
| Capa 3 (MiniLM) | 36 | 28 | 16 a la pagina de cancelaciones, 12 a otro documento |

**M4 - MiniLM por debajo de su umbral**: en las 29 consultas del menu, la etiqueta mas cercana de MiniLM es la
correcta en 15 y equivocada en 14 (p. ej. MAT-B2 a pagos). Bajar `MINILM_MIN_CONFIDENCE` cambiaria la mitad de los menus
por un documento equivocado. Ademas no bastaria con la variable: el handler exige 0,5 a `miniml_semantic`, asi que una
etiqueta con 0,45 iria a productos (umbral en codigo).

**M5 - la pagina de cancelaciones**: 16 preguntas de pedidos van a `account_modifications`. Para las de cancelar o
modificar es el tema correcto segun el enum, pero la pagina contradice a la de pedidos (R-34). El fallo es de contenido,
no de enrutado.

**Arnes de laboratorio con MiniLM grabado** (`simular_con_minilm_inyectado.py`): la prediccion de MiniLM solo depende
del texto, asi que se sustituye el modelo por las predicciones grabadas en el equipo local (con la misma regla previa
`_WARRANTY_DEFECTO_RE`). Con el codigo de produccion reproduce el resultado local **162 de 162** [V]. Permite medir
cambios en reglas, en la capa 2 y en umbrales sin otra ejecucion local; no sirve para cambios en MiniLM.

**Primer experimento (E1, laboratorio)**: quitar `garantia|warranty` de las palabras clave de devoluciones. 93 -> 96:
WAR-A2 en, WAR-C3 es y WAR-A3 es llegan a garantia; sin regresiones. WAR-C1 es pasa de devoluciones al menu de ayuda:
garantia solo reconoce "garantia/defecto/reparar" y no "se rompe", "cubre", "me lo cambian". Seguir anadiendo palabras
de la bateria seria ajustarse a las preguntas de control; antes hace falta un conjunto de preguntas de garantia y pedidos
que no esten en la bateria.

**Observacion lateral (R-33)**: `MiniLMIntentClassifier.load()` llama a `HfFolder.delete_token()` para forzar el
acceso anonimo en Cloud Run. Fuera de Cloud Run (equipo de desarrollo, pruebas) borra el token de HuggingFace
guardado en disco. El simulador lo neutraliza antes de cargar.

### 7.17 R-34: contenido de la tienda corregido en Shopify (26/11)

Decision de Yasmani [Y]: los textos son de prueba (se sustituiran por los de cada cliente), asi que se aplican sin
revision previa, con las herramientas de Shopify. Sin despliegue: produccion relee Shopify cada 5 minutos.

**Regla de redaccion**: solo datos que ya estan en las paginas de referencia, coherentes entre si
(`donde-esta-mi-pedido`, `como-devolver-un-producto`, `como-funcionan-los-envios`, `metodos-de-pago`,
`garantia-y-defectos`, `guia-de-tallas`). Unico dato nuevo: `support@ai-shoppings.com` (contacto general) y
`privacy@ai-shoppings.com`, en el dominio de la tienda. Un script comprobo que cada cifra de las paginas reescritas
aparece en alguna pagina de referencia (0 cifras nuevas) [V].

| Pagina (tema KB) | Cambio |
|---|---|
| `cancelaciones-y-modificaciones-de-pedidos` (`account_modifications`) | Reescrita: antes de 2 h gratis; despues, consultar disponibilidad; enviado: devolucion. Fuera "1 hora", "30 minutos", cargo de $2, `pedidos@tutienda.com`, +1 (555) 123-4567 |
| `preguntas-frecuentes-faq` (`general_faq`) | Reescrita como resumen fiel. Corrige envio gratis ($75 -> $50), cuotas ($50 -> $100), reembolso (7-10 -> 5-7 dias), paises; fuera VIP Club, tarjetas regalo, descuento de newsletter y contactos de plantilla |
| `mensaje-de-ayuda-general` (`unknown`, sin publicar) | Mismo menu de temas, con Pedidos y Garantia; fuera WhatsApp +52 55 1234 5678 y `ayuda@tutienda.com` |
| `politica-de-privacidad-y-proteccion-de-datos` | "Tu Tienda" -> AI-Shoppings; `privacy@ai-shoppings.com`; telefono de la tienda; fuera la direccion ficticia |
| `guia-de-cuidado-de-productos`, `guia-de-materiales-y-tejidos` | Solo `info@tutienda.com` -> `support@ai-shoppings.com` |

**Traducciones**: las paginas tienen traduccion en y fr en Shopify, y la sincronizacion las usa (la respuesta inglesa
de produccion salia de la traduccion) [V, `shopify_kb_client.get_page_translations`]. Cambiar solo el espanol habria
dejado el ingles y el frances con el contenido viejo. Orden aplicado por pagina, para que la sincronizacion por
`updated_at` no capture una mezcla: (1) registrar en/fr nuevas, (2) actualizar el espanol (cambia `updated_at`),
(3) volver a registrar en/fr con el nuevo identificador del espanol (`outdated=false`).

**Verificacion en Shopify** [V, 26/11 16:24 UTC]: las 6 paginas coinciden con los ficheros del laboratorio en los 3
idiomas (Shopify solo anade saltos de linea entre etiquetas); 0 traducciones cambiadas desfasadas; 0 restos de
plantilla en las 15 paginas. La guia de tallas en ingles ya estaba marcada como desfasada desde el 27/02; tiene las
mismas cifras que el espanol, no se toca.

Copia de seguridad previa (cuerpo y traducciones de las 15 paginas) en el laboratorio:
`pages_backup_26112026.json` (sha256 `70dcbe60...`) y `translations_backup_26112026.json` (`128abbeb...`).

**Sincronizacion en produccion** [V, logs del 26/11 aportados por Yasmani]: una instancia nueva de `00348-lhc` hizo
la sincronizacion completa a las 16:48:42 UTC: 13 de 13 paginas, cada una en es/en/fr (`page_sync_completed`,
`languages_synced`), 0 fallos, 10,4 s; el ciclo incremental de las 16:53 no encontro mas cambios. La sincronizacion
invalida la cache Redis de cada pagina cuyo hash cambio (`_invalidate_cache`, log a nivel DEBUG, no visible).

**Validado en produccion** [V, `r34_sondas_180426.jsonl`, 26/11 17:04 UTC, revision `00348-lhc`]: 6 de 6 PASA
(0 restos de plantilla; las 4 de pedidos dicen "2 horas"). ORD-C2 es/en y ORD-C3 es reciben la pagina de cancelaciones
nueva; ORD-C2 fr recibe "donde esta mi pedido" en frances, que da la misma regla; WAR-C3 en/fr reciben el menu nuevo con
`support@ai-shoppings.com`. Ninguna se reformula (`kb_contextualised=false`): se sirve el documento tal cual, ahora
coherente. Los "??" de la consola son solo la representacion de los emojis en PowerShell 5.1; el JSONL los guarda bien.
La primera version del script fallo en la consulta de logs (ver leccion); la segunda encontro 4 ciclos de sincronizacion.

Lo que R-34 no cambia: el enrutado (R-32). WAR-C3 sigue recibiendo el menu en vez de la pagina de garantia, y las
preguntas de pedidos siguen sin reformularse.

### 7.18 R-32: conjunto de preguntas nuevas, congelado antes de los experimentos (26/11)

Para no ajustar las reglas a la bateria (54 preguntas que ya conocemos), 31 preguntas nuevas x es/en/fr (93 consultas):
8 de garantia, 8 de pedidos, 6 de materiales y 9 de control (devoluciones, envios, pagos, cuidados, tallas), con los
temas aceptables de cada una (p. ej. cancelar: `account_modifications` o `account_orders`, que desde R-34 dan la misma
regla). `r32_holdout_questions.json`, **sha256 `9cf70b6c3c83b93a96d7a87a60f612f1ee225e249e8f991cfb0b8382c3cda4bc`**,
congelado el 26/11 antes de cualquier cambio de reglas. Parecido maximo con una pregunta de la bateria: 0,76 (dos
consultas demasiado parecidas se sustituyeron antes de congelar). Limitacion: las escribio quien escribira la
correccion; se mitiga congelandolas antes y midiendo tambien los controles.

Primera foto con capas 1 y 2 (laboratorio) [V]: de las 31 consultas que no dependen de MiniLM fallan 15, con los mismos
mecanismos: M1 ("How long is the warranty on jewelry?" -> devoluciones), M2 ("I want to cancel the purchase...", "If my
purchase is 60 dollars...", "Do I have to pay shipping to return something?" -> productos), M3 ("¿Como se en que estado
esta mi pedido?" -> envios) y uno nuevo: "¿Que datos necesito para hacer un reclamo de garantia?" -> privacidad ("datos").
Pendiente: grabar las 93 consultas con MiniLM en el equipo local.

**Opcion estudiada para M4 (Yasmani pregunta si un modelo puede enlazar las consultas con su documento)**: un
clasificador con LLM como capa de rescate (solo cuando las capas actuales acaban en `unknown` o MiniLM queda bajo su
umbral) es la candidata para M4. No sustituye la correccion de reglas: en M1 la regla decide sola con 0,8 y el modelo no
llegaria a consultarse. El laboratorio no alcanza OpenRouter; el experimento se haria en el equipo local.

### 7.19 R-32: correccion de la capa de reglas (laboratorio, 27/11)

Grabacion local de las 93 preguntas nuevas (27/11 02:07, mismas versiones, 7 hashes OK); el arnes la reproduce 93/93
[V]. **Linea base de las preguntas nuevas: 41/93** (garantia 6/24, pedidos 9/24, materiales 7/18, controles 19/27).

Protocolo: las correcciones se disenan a partir de los mecanismos vistos en la bateria (M1-M3); las preguntas nuevas
solo miden. Cada variante se mide con el arnes en los dos conjuntos y, ademas, en 14 peticiones de compra formuladas
como pregunta (`compras_control.py`), que no estan en ninguno de los dos conjuntos y deben seguir yendo a productos.

| Variante | Bateria (162) | Nuevas (93) | Compras que siguen en productos (base 8/14) |
|---|---|---|---|
| Linea base (produccion) | 93 | 41 | 8 |
| C1: quitar `garantia/warranty` de devoluciones | 96 (+3 -0) | 43 (+2 -0) | - |
| C1+C3: ademas quitar `pedido/order` de envios | 97 (+4 -0) | 49 (+8 -0) | - |
| + C2a: verbo de compra en pregunta con tema informacional -> "sin patron" | 98 (+5 -0) | 51 (+10 -0) | **6 (rompe 2)** |
| + C2b: igual, devolviendo el tema de la capa 1 | 100 (+7 -0) | 52 (+11 -0) | **6 (rompe 2)** |
| **+ C2c: C2b solo para temas de politica o cuenta** | **100 (+7 -0)** | **52 (+11 -0)** | **8 (igual)** |

C2a y C2b rompian "Do you have cotton t-shirts I can buy?" y "Where can I buy leather boots?": las palabras de material
tambien describen productos. C2c excluye material, cuidado y talla de la regla (criterio de diseno, no ajustado a las
preguntas nuevas). Las 8/14 compras de la linea base confirman R-31: el codigo actual ya manda 6 de 14 compras a un
documento; C2c no lo empeora ni lo arregla.

**Cambio propuesto** (`src/api/core/intent_detection.py`, 46 lineas de diff, LF):
- M1: eliminar `r"\b(garantía|warranty|garantia)\b"` de las palabras clave de POLICY_RETURN.
- M3: eliminar `pedido|order` de las palabras clave de POLICY_SHIPPING (queda `paquete|package`).
- M2: en `detect()`, si la consulta es pregunta, la capa 1 encontro un tema de politica o cuenta y lo unico
  transaccional es PURCHASE_INTENT, se devuelve el tema informacional con su confianza (< 0,7); el hibrido consulta la
  capa 2 y ya no hay patron que el GUARD proteja. `info_result` se inicializa a `None` antes del paso 2.

**Pruebas** [V]: `tests/unit/test_r32_routing_rules.py` (nuevo, 13 pruebas): 13/13 con el codigo nuevo y 8 fallan con
el antiguo (cada prueba detecta el cambio). Suite de deteccion (`test_handler_kb_unavailable`,
`test_hybrid_detector_layer3`, `test_intent_detection_availability` + las nuevas): 56 pasan y 1 falla igual que con el
codigo de produccion: `test_layer3_not_triggered_when_ml_confident` esta desactualizada (MiniLM v2 consulta la capa 3
cuando la capa 2 dice informacional sin tema); no se toca en este cambio.

**Lo que queda** (con el cambio): bateria 62 fallos = 30 menu (`unknown`) + 28 MiniLM a otro documento + 4 de la capa 2;
nuevas 41 fallos = 26 menu + 11 MiniLM + 4 restantes (2 de reglas). La capa de reglas queda casi resuelta; el resto es
M4, candidato a la capa de rescate con LLM.

**Observacion lateral**: el comentario del GUARD en `hybrid_detector.py` dice que la excepcion de verbos genericos exige
confianza de la capa 2 >= 0,75, pero el codigo no la comprueba.

## 8. Lecciones

- **Un respaldo que pasa a principal necesita la evaluacion del principal**: GPT-4o-mini se eligio como respaldo
  "suficientemente bueno" para ~5 % del trafico; tras apagar LFM responde el 100 % y nadie midio lo que importa
  ahora (apego al documento).
- **Lo que no se registra no se puede auditar**: guardar solo la longitud de una respuesta generada impide saber
  despues que se le dijo al cliente.
- **Un comprobador automatico mide lo que se le ocurrio a quien lo escribio**: este buscaba datos inventados y
  el modelo no invento ninguno; fallaba en otra cosa (conclusiones). Por eso la primera medicion se reviso entera
  a mano: la muestra del 20 % habria dado una imagen falsa de "todo bien".
- **Revisar tambien las respuestas esperadas**: un dato esperado mal escrito (SIZ-C1) habria validado una
  respuesta incorrecta. El conjunto de preguntas es codigo y necesita su propia revision.
- **Un defecto puede esconder otro**: la puerta que no reconoce el frances (R-20) reduce la exposicion a las
  respuestas infieles (R-22). El orden de las correcciones importa.
- **Una instruccion de prompt se generaliza mas alla de su objetivo**: "empieza con un 'No' claro" corrigio las
  premisas aceptadas pero convirtio "no figura" en "no lo ofrecemos"; "si estas en el limite, elige la mayor"
  hizo ver limites donde no los hay. Cada regla nueva se mide en todas las preguntas, no solo en las que motivaron
  la regla.
- **Cuando un prompt distinto no mueve un error (18 de 18), el problema no es la redaccion**: el calculo de tallas
  con varias medidas no es una tarea para el modelo; la solucion es estructural.
- **Repetir la linea base vale lo que cuesta**: 29 infieles en las dos ejecuciones con el prompt de produccion dan
  confianza en que las mejoras de v3 no son ruido de muestreo.
- **Quitar una regla puede devolver un error que ella tapaba**: "empieza con un 'No'" tenia efectos secundarios,
  pero tambien era lo que evitaba "5 horas esta dentro de las 2 horas". Cada cambio se compara con todas las
  versiones anteriores, no solo con la ultima.
- **Pedir que se escriba la comparacion no hace que la comparacion sea correcta**: v4 dejo 0 infieles en las 48
  preguntas y a la vez escribio "40 dias es mas que 60". Sin las preguntas de control de tipo A, v4 habria parecido
  perfecta. Toda regla que empuja hacia "No" necesita preguntas donde lo correcto es "Si".
- **Los ejemplos del prompt no pueden coincidir con las preguntas de control**: un control que comparte numeros con
  el ejemplo mide la copia, no la regla (PAY-C3 con "$90 frente a $100").
- **La linea base tambien varia**: 29 y 24 infieles con el mismo prompt en dias distintos. Solo se comparan
  ejecuciones del mismo dia y no se sacan conclusiones de diferencias de pocas respuestas.
- **Medir un modelo en condiciones de produccion y en condiciones de capacidad separa "no sabe" de "no le
  dejamos"**: LFM2.5-24B-A2B fallo 185 de 189 con 300 tokens y 1 de 189 con 4.000. Sin la segunda medida se
  habria retirado el codigo LFM por una conclusion falsa; sin la primera se habria adoptado con una
  configuracion que envia su razonamiento al cliente.
- **Un limite de tokens pensado para un modelo es una suposicion sobre ese modelo**: los 300 tokens que bastan a
  GPT-4o-mini (mediana 39) cortan o vacian las respuestas de los modelos que razonan (R-25, R-27). Al cambiar de
  modelo hay que revisar limite, tiempo de espera y extraccion de la respuesta, no solo el identificador.
- **PowerShell 5.1: `Start-Transcript` no guarda la salida de los programas nativos** (python.exe). Para guardar la
  salida completa: `& $venvPython script.py ... 2>&1 | Tee-Object -FilePath salida.txt`.
- **Mejor media no es mejor decision**: v3 bajo las inferencias de GPT-4.1-mini de 31 a 21 y a la vez creo los
  unicos 2 infieles que llegarian al cliente. Se decide por el criterio fijado antes (lo que llega al cliente), no
  por el total.
- **"Llegaria al cliente" depende de la puerta**: los 2 infieles de GPT-4.1-mini no llegan hoy solo porque la
  puerta no reconoce el frances. Corregir un componente cambia la exposicion de otro; por eso R-20 lleva una
  medicion previa.
- **Etiquetar con criterios escritos**: cada criterio nuevo se anoto antes de aplicarlo y se reviso contra las
  etiquetas de la criba (p. ej. "ya no aplica" FIEL frente a "no puedes cancelar gratis" INFERENCIA), para que el
  mismo texto reciba la misma etiqueta en todos los modelos.
- **Buscar todos los consumidores antes de afirmar cuantos hay**: el 24/11 se dijo "tres usos" leyendo los
  ficheros ya conocidos; `git grep` del 25/11 encontro un cuarto (busqueda visual). Un recuento se hace con una
  busqueda exhaustiva, no con memoria del codigo.
- **Una comprobacion debe distinguir "no hay nada" de "no pude mirar"**: el 25/11 el recuento de `ERROR` imprimio 0
  porque la consulta habia fallado (PowerShell 5.1 parte los filtros con comillas dobles escapadas). Se comprueba
  `$LASTEXITCODE` y, en `/metrics`, una serie de control que sabemos que existe.
- **Pegar bloques largos en la consola pierde lineas de salida**: dos lineas de las sondas del bloque 3 no se
  vieron en la consola pero si estaban en el fichero de evidencia. Los bloques de despliegue se ejecutan como
  ficheros `.ps1` con `2>&1 | Tee-Object`, y en ASCII (PowerShell 5.1 lee un `.ps1` sin BOM como ANSI).
- **Una sonda repetida puede no recorrer el camino que se quiere medir**: la segunda consulta de producto vino de
  la cache y no paso por el redactor (R-30). Antes y despues se usan consultas nuevas.
- **La bateria de laboratorio mide un tramo; las sondas de produccion miden el camino entero**: el laboratorio daba el
  `sub_intent` de cada pregunta y asi no podia ver que la garantia se enruta a devoluciones o a `unknown` (R-32).
- **Un paso que se para debe parar la cadena**: el 26/11 el script de aplicacion se nego a escribir (fichero
  editado a mano) y la prueba fallo, pero los pasos siguientes se ejecutaron igual y el commit salio sin la prueba.
  Los proximos despliegues iran en un solo script que se detiene en el primer fallo y exige pruebas en verde antes
  del commit.
- **Reutilizar la consulta que ya funciono**: la consulta de logs del 24/11 encontro las lineas pero imprimio solo
  la hora, porque los logs estructurados guardan el texto en `jsonPayload.event`, no en `textPayload` ni
  `jsonPayload.message`. El 16/11 (R-11) ya se habia resuelto asi. Antes de escribir una consulta nueva, buscar
  en los DCT la que ya dio resultado.
- **En un sistema RAG, el enrutado y el contenido se evaluan juntos**: por sub_intent, las 16 preguntas que iban a
  cancelaciones parecian casi bien y el menu de ayuda parecia un fallo inofensivo; leyendo el contenido, las dos rutas
  entregaban plazos o contactos falsos (R-34).
- **Cambiar una pagina multilingue es cambiar todas sus traducciones**: Shopify guarda cada idioma aparte; corregir
  solo el idioma principal deja al cliente en ingles y en frances con el texto viejo.
- **PowerShell 5.1 y filtros de gcloud: "sin espacios, sin comillas" no basta**: un valor con `:` (una hora,
  `timestamp>=2026-11-26T16:17:00Z`) rompe el filtro ("syntax error ... token ':'"). Para limitar por hora se usa
  `--freshness` y se filtra en PowerShell. Y `ConvertFrom-Json` difiere entre 5.1 y 7 (enumeracion del array y
  conversion de fechas): con un bucle explicito el mismo codigo funciona en las dos.
