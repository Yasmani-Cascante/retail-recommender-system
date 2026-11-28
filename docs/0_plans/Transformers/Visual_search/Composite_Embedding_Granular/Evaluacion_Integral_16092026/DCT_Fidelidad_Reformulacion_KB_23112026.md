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
| R-32 | **Preguntas de garantia y de cancelacion que no llegan a su documento en produccion**: con las mismas 3 x 2 repeticiones antes y despues del paso 2 [V, sondas 26/11]: "Si la cremallera de un vestido se rompe a los 45 dias, ¿me lo cambian por garantia?" se clasifica `policy_return` y se responde con la politica de devoluciones ("no se menciona garantia"), aunque la tienda tiene pagina de garantia; "The sole of my shoes came off 70 days after I bought them, is it covered by the warranty?" se clasifica `unknown` (menu de ayuda); "I placed my order 5 hours ago, can I cancel it for free?" va a `account_modifications` sin entidades y recibe el documento tal cual. La bateria del laboratorio fijaba el `sub_intent` de cada pregunta, asi que no media el enrutamiento | **Alta** para garantia (el cliente oye que no hay garantia); Media para cancelacion (recibe el documento correcto, sin reformular) | Alcance medido el 26/11 (7.16): 69 de 162 no llegan a su documento. **M1-M3 corregidos y validados en produccion el 27/11** (7.20: 9 -> 27 de 28 sondas, 0 empeoran); M5 resuelto por R-34; **M4 desplegado y validado el 28/11** en `00350-d66` (T1 con prompt v3, gpt-4.1-mini, corte automatico; 7.21-7.31) |
| R-33 | **La carga de MiniLM borra el token de HuggingFace del disco**: `MiniLMIntentClassifier.load()` llama a `HfFolder.delete_token()` para forzar acceso anonimo; pensado para Cloud Run, pero en un equipo de desarrollo o en pruebas borra el token guardado [V, lectura 26/11] | Baja (no afecta a clientes) | Registrado; el simulador de R-32 lo neutraliza |
| R-34 | **Paginas de la base de conocimiento con contenido de plantilla que contradice a la tienda** [V, Shopify 26/11]: `cancelaciones-y-modificaciones-de-pedidos` dice "cancelacion gratis antes de 1 hora", "modificar hasta 30 minutos", cargo de $2, `pedidos@tutienda.com` y +1 (555) 123-4567, mientras `donde-esta-mi-pedido` dice "antes de 2 horas: gratis" y `orders@ai-shoppings.com`; `preguntas-frecuentes-faq` usa `info@tutienda.com` y +1 (555) 123-4567; `mensaje-de-ayuda-general` (el menu de `unknown`) da WhatsApp +52 55 1234 5678 y `ayuda@tutienda.com`; la politica de privacidad dice "En Tu Tienda". En la bateria llegan a esas paginas 16 preguntas de pedidos (cancelaciones) y 29 (menu) | **Alta**: el cliente recibe plazos contradictorios y contactos que no existen | **Cerrado el 26/11** (7.17): 6 paginas corregidas en es/en/fr y validadas en produccion (6 de 6 sondas) |
| R-35 | **Las preguntas de cancelacion nunca se reformulan: la puerta de reformulacion no tiene patrones para `account_modifications`** [V, lectura de `kb_contextualizer.py` 26/11]: `has_specific_entities` solo tiene patrones para 7 temas; sin patrones devuelve False y se sirve la pagina entera. "Hice el pedido hace 5 horas, ¿puedo cancelarlo gratis?" recibe toda la pagina de cancelaciones y el cliente debe deducir que ya no es gratis (sondas R-34). En frances se suma R-20 ("annuler" no esta en los patrones de `account_orders`) | Media (la respuesta es correcta pero no contesta a la pregunta concreta) | Registrado; activar la reformulacion aqui expone al error ya medido "5 horas esta dentro de las 2 horas": medir primero en el banco de fidelidad |
| R-36 | **Un mensaje que empieza con un saludo recibe solo el saludo y su pregunta se ignora** [V, laboratorio 27/11, capa de reglas identica a 00349-88s; pendiente sonda de produccion]: `_detect_greeting` se ejecuta antes que todo lo demas y sus patrones aceptan "hola/hey/hi/hello/buenas/buenos dias..." al PRINCIPIO del mensaje aunque siga una pregunta (el comentario del codigo lo declara: "the greeting wins"). "Hola, ¿cuanto cuesta el envio a Madrid?", "Buenas tardes, quiero unos zapatos negros talla 40" y "Hi, can I return a dress I bought last week?" -> GREETING 0,95 -> plantilla de bienvenida, sin respuesta ni productos. Aparecio en los mensajes "de cliente" de M4 ("hola!! a las zapas q compre se les despego la suela...") | **Alta** (empezar con un saludo es habitual en un chat; afecta a preguntas y a compras) | Registrado; la capa de rescate (T1) no lo cubre (la ruta es "saludo", no el menu) |
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

### 7.20 R-32: correccion de reglas validada en produccion (27/11)

Commits `e03e439` (codigo y pruebas) y `36d4653` (DCT). Imagen
`gcr.io/retail-recommendations-449216/retail-recommender@sha256:c733cbbe406d078fa7619a6a59a7f333ee1bfbb0e43ab1c6e0539abc3a2ac224`,
revision **`retail-recommender-00349-88s`** (100 % del trafico; vuelta atras: 00348-lhc). Pruebas antes del commit:
56 en verde y 1 excluida por nombre (`test_layer3_not_triggered_when_ml_confident`, desactualizada desde cf9882e).

Validacion [V, `r32_despliegue_27112026`]:

| Comprobacion | Resultado |
|---|---|
| Digest desplegado = construido | Si |
| Variables de entorno | 52 (11 secretas), sin cambios |
| KB `policy_warranty` es/en/fr | HTTP 200 |
| ERROR en la revision nueva | 0 |
| Sondas "antes" (00348-lhc) como predijo el laboratorio | **28 de 28** (el laboratorio reproduce produccion) |
| Sondas "despues" (00349-88s) como predijo el laboratorio | **28 de 28** |
| Ruta correcta | **9 -> 27 de 28** |
| Sondas que empeoran | **0** (5 controles y 4 compras siguen igual) |

Ejemplos: "Se me descosio una costura a la semana de comprar..., ¿lo cubre la garantia?" pasa de productos a garantia;
"How long is the warranty on jewelry?" de devoluciones a garantia; "¿Como se en que estado esta mi pedido?" de envios a
pedidos; "Do I have to pay shipping to return something?" de productos a devoluciones. La que sigue mal es la prevista:
WAR-C1 es (cremallera a los 45 dias) pasa de devoluciones al menu de ayuda; necesita la capa de rescate (M4).

Latencia: la primera sonda "antes" tardo 104 s (arranque en frio de la revision anterior); las demas, 0,2-3 s en las dos
revisiones.

**Estado de R-32**: M1, M2 y M3 corregidos y validados. M5 resuelto por R-34. **Pendiente M4** (consultas que acaban en el
menu o que MiniLM manda al documento equivocado: 26 + 11 de las 93 preguntas nuevas), candidato a la capa de rescate con
LLM, que se probara en el equipo local.

### 7.21 R-32 M4: experimento de clasificacion del tema con LLM (diseno, 27/11)

Decision de Yasmani [Y]: comparar gpt-4.1-mini y gpt-4o-mini. `r32_m4_llm.py` (equipo local, OpenRouter): cada consulta de
la bateria y de las preguntas nuevas (255) se clasifica con los dos modelos, 2 repeticiones, temperatura 0, `max_tokens`
12. El prompt (sha256 `691a4aab...`) lista los 11 temas con pagina propia (una linea que resume el CONTENIDO de cada
pagina, no las preguntas), `product_search` (quiere comprar) y `none`. `general_faq` queda fuera: resume todos los temas
y atraeria cualquier pregunta dudosa. Respuestas que no son una etiqueta, o que nombran dos, cuentan como `invalid`.

Analisis (`analisis_m4.py`, laboratorio): simula la capa de rescate sobre el enrutado de 00349-88s (grabado con el arnes,
validado 28/28 en produccion), con cuatro disparadores: T1 solo lo que acaba en el menu; T2 T1 + lo que MiniLM manda a un
documento; T3 todo lo que va a un documento y no decidio la capa de reglas; T4 siempre (techo). T1-T3 nunca tocan una
consulta que hoy va a productos: las 14 compras de control no estan en el experimento y no se podria medir si se rompen.
Por cada modelo y disparador: aciertos, ganancias y perdidas frente a hoy, llamadas al LLM (latencia que se anade), coste y
estabilidad entre repeticiones.

**Resultados** [V, `r32_m4_llm.jsonl`, 1.020 llamadas el 27/11 14:08-14:10, 0 errores, 0 respuestas invalidas]. Bateria con el
criterio de R-34 para las 5 preguntas de cancelar (ORD-A1, A3, C1, C2, C3: se acepta tambien la pagina de cancelaciones,
igual que en las preguntas nuevas); sin ese criterio, 15 de los 19 "fallos" de gpt-4.1-mini eran justo eso.

| | gpt-4.1-mini | gpt-4o-mini |
|---|---|---|
| Latencia p50 / p95 | 852 / 1.239 ms | 684 / 875 ms |
| Coste por 1.000 llamadas | 0,18 USD | 0,07 USD |
| Misma etiqueta en las 2 repeticiones | 254/255 | 254/255 |
| LLM solo, bateria (hoy 113/162) | **158** | 148 |
| LLM solo, preguntas nuevas (hoy 52/93) | **93** | 91 |
| T1 bateria / nuevas (llamadas 19 % / 28 %) | **142 (+29 -0) / 78 (+26 -0)** | 139 (+26 -0) / 77 (+25 -0) |
| T2 bateria / nuevas (llamadas 60 % / 69 %) | 155 (+44 -2) / 89 (+37 -0) | 147 (+37 -3) / 88 (+36 -0) |
| T3 bateria / nuevas (llamadas 77 % / 88 %) | 156 (+45 -2) / 90 (+38 -0) | 148 (+38 -3) / 89 (+37 -0) |

Las 2 perdidas de gpt-4.1-mini (T2/T3) son ORD-B1 en/fr, "Mi pedido llego danado, ¿me mandan uno nuevo gratis?", enviada
a garantia. La pagina de garantia responde mejor que la de pedidos ("te enviamos una etiqueta de devolucion GRATIS...
enviamos el reemplazo"; la de pedidos solo dice "contacta a orders@"): caso ambiguo, no se cambia la bateria.

**Limitacion**: las dos baterias las escribio un LLM (lenguaje claro y bien formado); el 93/93 es optimista para mensajes
reales de clientes (erratas, jerga, varias preguntas en una). Antes de producir conviene un conjunto escrito por Yasmani.

**Lectura**: T1 con gpt-4.1-mini rescata las consultas que hoy reciben el menu (+29 / +26) sin perder ninguna y solo anade
latencia (p50 0,85 s) al 19-28 % de las consultas; coste despreciable (~0,05 USD por 1.000 consultas). T2 gana +15 / +11
mas pero hace pagar la latencia al 60-70 % y empieza a cambiar decisiones defendibles.

### 7.22 R-32 M4: mensajes "de cliente" y disparador T5 (27/11)

Decision de Yasmani [Y]: gpt-4.1-mini + T1; los mensajes "de cliente" los escribe Claude. 9 mensajes x es/en/fr
(`r32_mensajes_cliente.json`, sha256 `bd608540...`, congelado antes de clasificar): erratas, sin tildes, abreviaturas,
jerga, temas sin su palabra clave y una busqueda de productos. Enrutado grabado con el detector completo y el codigo de
`2f312e9` (= 00349-88s) y clasificacion con gpt-4.1-mini (2 repeticiones, 0 errores, 27/27 estables, 0,01 USD) [V].

| | Hoy | T1 | LLM solo |
|---|---|---|---|
| Mensajes "de cliente" (27) | 14 | 18 (+4 -0) | **27** |

En estos mensajes el sistema actual falla casi siempre **con seguridad**, no en el menu: "dress is too small, can I send it
back?" -> productos; "spilled red wine on my white shirt..." -> productos (capa de reglas); "mi pedio no llega y ya pasaron
como 10 dias" -> envios; "me quedo chico el vestido, lo puedo mandar de vuelta?" -> tallas; y los dos que empiezan con
saludo -> saludo (R-36). T1 solo actua sobre el menu y no ve ninguno de esos.

**T5** (simulado): se mantiene lo que la capa de reglas decide con confianza >= 0,8 (salvo saludo); el LLM decide el resto,
incluido lo que hoy va a productos o a saludo:

| Conjunto | Hoy | T1 | T5 | Llamadas LLM con T5 |
|---|---|---|---|---|
| Bateria (162, criterio de cancelar) | 113 | 142 (+29 -0) | 158 (+47 -2) | 78 % |
| Preguntas nuevas (93) | 52 | 78 (+26 -0) | 93 (+41 -0) | 91 % |
| Mensajes "de cliente" (27) | 14 | 18 (+4 -0) | 27 (+13 -0) | 93 % |

Las 2 perdidas de T5 son ORD-B1 en/fr (pedido danado -> garantia, caso ambiguo, 7.21). T5 resolveria tambien R-36 en
estos mensajes. Pero T5 manda al LLM consultas que hoy van a productos, y la seguridad con **peticiones de compra** no esta
medida (solo X-07 en 3 idiomas, correcto): falta un conjunto de compras y saludos antes de poder elegir T5. Coste de T5:
~0,85 s mas (p50) en la mayoria de las consultas.

### 7.23 R-32 M4: compras y saludos; T1 frente a T5 en los cuatro conjuntos (27/11)

Decision [Y]: "medir T5 primero". Conjunto de compras y saludos escrito por Claude y congelado antes de clasificar
(`r32_compras_saludos.json`, sha256 `d8c27ae6...`): 10 compras (P-01..P-10; P-10 "¿cuando vuelven las tallas S?" acepta
tambien `product_availability`), 2 saludos puros (G-01, G-02 -> saludo), saludo + compra (G-03 -> productos) y saludo +
pregunta (G-04 -> envios), x es/en/fr = 42. Enrutado grabado en Windows con el codigo de `2f312e9` (7 hashes OK) y
gpt-4.1-mini con el prompt `691a4aab...` (84 llamadas, 0 errores, p50 891 ms, p95 1175 ms, 0,015 USD; 41/42 estables:
P-09 es rep 2 dijo `product_sizing`) [V].

| Conjunto | Hoy | T1 | T5 | T5p | Llamadas LLM T1 / T5 |
|---|---|---|---|---|---|
| Bateria (162) | 113 | 142 | 158 | 156 | 30 / 126 |
| Preguntas nuevas (93) | 52 | 78 | 93 | 90 | 26 / 85 |
| Mensajes "de cliente" (27) | 14 | 18 | 27 | 23 | 4 / 25 |
| Compras y saludos (42) | 25 | 32 | 34 | 36 | 10 / 42 |
| **Total (324)** | **204 (63 %)** | **270 (83 %)** | **312 (96 %)** | **305 (94 %)** | **22 % / 86 %** |

T5p = T5 sin tocar lo que hoy va a productos. Repeticion 2: T5 311, el resto igual [V] (`t5/analisis_t5.py`).

Lo que mide el conjunto de compras [V]:
- Saludos puros: el LLM dice `none` y se quedan en saludo (6/6). El saludo no se rompe con T5.
- R-36 (el saludo se traga la pregunta): T5 corrige G-03 y G-04 en es/en; T1 no los ve (hoy van a saludo, no al menu).
- Compras que hoy acaban en el menu (P-06 "busco un vestido para una boda en la playa", P-08 "algo abrigado para
  la nieve", en los 3 idiomas, y P-04 en): T1 y T5 las mandan a productos.
- **Lo que el LLM confunde**: "¿tienen X en talla Y?" lo manda a `product_availability` (P-02 "tienen jeans skinny talle
  28??" y P-05 "¿Tienen chaquetas de cuero en talla M?", en los 3 idiomas), y una compra con condicion de envio
  ("tenis blancos con envio rapido", es/fr) a `policy_shipping`. La pagina de disponibilidad explica reposiciones y
  alertas; no dice si hay chaquetas de cuero en M: el cliente queria ver productos.
- Perdidas de T5 frente a hoy: P-02 es (productos -> disponibilidad) y P-04 fr (productos -> envios), mas ORD-B1 en/fr
  de la bateria (caso ambiguo, 7.21). T1 no pierde nada en ningun conjunto.

Lectura [H]: T5 acierta 42 consultas mas que T1 en total, pero pasa por el LLM el 86 % de los mensajes, incluidas casi
todas las compras, que son la mayor parte del trafico real y aqui solo hay 10 (30 consultas). Con 2 compras perdidas de
30, una tasa parecida en trafico real seria visible. Las dos confusiones son de **definicion de etiquetas** del prompt
(que es "disponibilidad" y que es "buscar productos"), no de idioma ni de erratas, y se pueden corregir en el prompt y
volver a medir. Coste de T5: ~0,9 s mas (p50) en el 86 % de los mensajes; 0,18 USD por 1000 mensajes.

Opciones para decidir [Y]:
- **A. Prompt v2 + nueva medicion** (recomendada): redefinir `product_availability` (reposiciones y alertas de stock,
  no "¿tienen X en talla Y?") y `product_search` (incluye "¿tienen X...?" y compras con condiciones de talla, color,
  precio o envio); ampliar el conjunto de compras a ~25 (mas peticiones "¿tienen...?" y con condiciones); medir
  v1 y v2 en los cuatro conjuntos (~700 llamadas, ~0,15 USD). Si v2 no pierde compras, T5 con v2.
- **B. T1 ahora** (sin riesgo para compras, 83 %) y R-36 como cambio aparte en la capa de reglas.
- **C. T5p**: 94 %, protege lo que hoy va a productos, pero renuncia a corregir las preguntas de ayuda que hoy caen en
  productos (ej. "dress is too small, can I send it back?").

### 7.24 R-32 M4: prompt v2 (diseno, 27/11)

Decision [Y]: opcion A (prompt v2 y medir). v2 (`r32_m4_llm.py --prompt v2`, sha256 del prompt `4b8f3508...`) mantiene
las mismas etiquetas, el mismo orden y la misma plantilla; solo cambian dos definiciones [V]:
- `product_availability`: "Stock policy: when sold-out items or sizes are restocked, back-in-stock alerts, how stock is
  updated. Not for asking whether the store has a kind of product in some size or color (that is product_search)."
- `product_search`: "...including 'do you have X (in size/color Y)?' and product requests with conditions such as size,
  color, price, occasion or fast delivery. Not a question about a store policy."
El prompt v1 sigue dando `691a4aab...` (comprobado), asi que los resultados anteriores siguen valiendo.

Conjunto nuevo congelado antes de clasificar (`r32_compras2.json`, sha256 `19830dbe...`, 15 x es/en/fr = 45):
P-11..P-20 compras "¿tienen X...?" y con condiciones (entrega rapida, material, lavado, precio); A-01..A-03 preguntas
reales de disponibilidad (reposiciones, alertas, "esta agotado, ¿vuelve?"), para comprobar que v2 no las manda a
productos (la bateria no tiene ninguna); G-05 saludo + "¿tienen...?" y G-06 saludo + garantia (R-36).
Medicion: v2 en los cinco conjuntos y v1 en el conjunto nuevo (gpt-4.1-mini, 2 repeticiones, 828 llamadas, ~0,15 USD).
Criterio fijado antes de ver resultados: T5 con v2 solo si no pierde compras ni preguntas de disponibilidad frente a hoy
y supera a T1; si no, opcion B (T1 + R-36 aparte).

### 7.25 R-32 M4: resultados del prompt v2 (27/11)

Ejecucion en Windows [V]: enrutado de hoy de `r32_compras2.json` (7 hashes OK, 45 lineas) y gpt-4.1-mini: v2 en los cinco
conjuntos (738 llamadas, 0 errores, 1 invalida, p50 861 ms, p95 1121 ms, 0,149 USD) y v1 en el conjunto nuevo (90
llamadas, 0 errores). Analisis: `v2/analisis_v2.py`.

| Conjunto | Hoy | T1/v1 | T5/v1 | T1/v2 | T5/v2 |
|---|---|---|---|---|---|
| Bateria (162) | 113 | 142 | 158 | 141 | 157 |
| Preguntas nuevas (93) | 52 | 78 | 93 | 78 | 93 |
| Mensajes "de cliente" (27) | 14 | 18 | 27 | 18 | 27 |
| Compras 1 (42) | 25 | 32 | 34 | 34 | 39 |
| Compras 2 (45) | 18 | 24 | 29 | 27 | 43 |
| **Total (369), rep 1 / rep 2** | 222 (60 %) | 294 / 294 | 341 / 339 | 298 / 300 | **359 / 361 (97 %)** |

Lo que corrige v2 [V]: todas las peticiones "¿tienen X en talla Y?" (P-02, P-05, P-12, P-14, G-05) y "con envio rapido"
(P-04, P-13) van a productos; las 9 preguntas reales de disponibilidad (A-01..A-03) siguen en disponibilidad en las dos
repeticiones (hoy acierta 2 de 9). La bateria apenas cambia: WAR-B2 fr rep 1 respondio `product_warranty` (etiqueta que
no existe; se queda la ruta de hoy) y SHP-B2 (en) fue inestable entre envios y pedidos.

Lo que rompe v2 [V]: **P-09 "¿que me pongo con una falda negra?"** (consejo de conjunto) pasa de productos a
`product_material` en es/fr (rep 1) y en es (rep 2); en en, `none`. Y P-06 es ("algo para regalarle a mi novia, unos 50
dolares") alterna `none`/`product_search`. Son compras que hoy aciertan (P-09) y que v1 acertaba.

**Criterio fijado en 7.24**: T5/v2 pierde P-09 es/fr frente a hoy, asi que **no lo cumple** -> opcion B (T1 + R-36 aparte),
salvo nueva decision [Y].

Variante calculada despues de ver los datos [H, a posteriori]: **T5g** = T5/v2 pero lo que hoy va a productos solo puede
cambiarlo el LLM hacia politicas o cuenta, nunca hacia un tema de producto (material, cuidado, tallas, disponibilidad).
353/369 y 354/369 (96 %), sin perder nada frente a hoy salvo ORD-B1 (ambiguo); renuncia a A-03 ("esta agotado, ¿vuelve?",
que hoy va a productos). Como se diseno mirando estos mismos datos, necesitaria un conjunto nuevo congelado para
validarse.

### 7.26 R-32 M4: prompt v3, proteccion T5g y conjunto de validacion (diseno, 27/11)

Decision [Y]: una ronda mas, validada con un conjunto nuevo. Orden seguido para que la validacion sea limpia [V]:
1. Primero se escribio y congelo `r32_compras3.json` (sha256 `e55ebeda...`, 17 x es/en/fr = 51), antes de escribir v3:
   10 compras (consejos de conjunto, regalos, "¿tienen...?", compras con palabras de material, cuidado, talla o envio),
   5 preguntas reales de producto que NO deben ir a productos (disponibilidad, material x2, cuidado, tallas) y 2 saludos
   seguidos de compra o pregunta.
2. Despues, v3 (`8691b753...`) = v2 + "outfit or styling advice ('what goes with X?', 'what should I wear to...?'), gift
   ideas" en `product_search`. v1 y v2 siguen dando `691a4aab...` y `4b8f3508...` (comprobado).
3. Medicion: v3 en los seis conjuntos y v2 en el de validacion (936 llamadas, ~0,19 USD).

Disparadores a comparar: T1, T5 y **T5g** (T5, pero lo que hoy va a productos solo lo puede cambiar el LLM hacia una
politica o la cuenta; nunca hacia material, cuidado, tallas o disponibilidad).

Criterio fijado antes de medir: se elige la opcion mas simple que (a) no pierda nada frente a hoy en el conjunto de
validacion, (b) no pierda nada frente a hoy en los otros cinco salvo ORD-B1 (ambiguo, 7.21), en las dos repeticiones, y
(c) supere a T1. Orden de preferencia: T5/v3, despues T5g/v3, despues T5g/v2. Si ninguna cumple: T1 con el prompt que no
pierda nada, y R-36 como cambio aparte.

### 7.27 R-32 M4: resultados de v3 y decision por el criterio (27/11)

Ejecucion en Windows [V]: enrutado de hoy del conjunto de validacion (7 hashes OK, 51 lineas); gpt-4.1-mini v3 en los
seis conjuntos (840 llamadas, 0 errores, 0 invalidas, p50 862 ms, p95 1225 ms, 0,176 USD; 418/420 estables) y v2 en el
de validacion (102 llamadas, 0 errores). Analisis: `v3/analisis_v3.py` (aplica el criterio de 7.26 tal cual).

| Conjunto (rep 1 / rep 2) | Hoy | T1/v2 | T1/v3 | T5/v3 | T5g/v3 | T5g/v2 |
|---|---|---|---|---|---|---|
| Bateria (162) | 113 | 141/142 | 141 | 156 | 155 | 156 |
| Preguntas nuevas (93) | 52 | 78 | 78 | 92 | 90 | 91 |
| Mensajes "de cliente" (27) | 14 | 18 | 18 | 27 | 25 | 25 |
| Compras 1 (42) | 25 | 34/35 | 35 | 42 | 42 | 41/42 |
| Compras 2 (45) | 18 | 27 | 27 | 43 | 40 | 40 |
| **Validacion (51)** | 28 | 43/42 | **46** | 47 | 49 | 46/45 |
| **Total (840, dos rep.)** | 60 % | 81,3 % | **82,1 %** | 96,9 % | 95,5 % | 95,0 % |

Criterio [V]:
- **T5/v3** no cumple (a): en validacion pierde "looking for a wool coat that isn't itchy" y "i want shirts that don't
  need ironing" (en; productos -> materiales) y "un bikini que me llegue antes del sabado" (es; productos -> envios).
- **T5g/v3** y **T5g/v2** no cumplen (a): la proteccion evita las dos de materiales, pero no el bikini (envios es una
  politica, la proteccion no lo para), en las dos repeticiones.
- **T1/v2 y T1/v3** no pierden nada en ningun conjunto. T1/v3 es la mejor: 690/840 frente a 683/840.

**Decision por el criterio fijado antes de medir: T1 con el prompt v3**, y R-36 como cambio aparte en la capa de reglas.
Ganancia sobre hoy en estos conjuntos: de 60 % a 82 %, sin perdidas. En el conjunto de validacion (nunca usado para
ajustar): de 28/51 a 46/51.

Lo que T1 deja sin resolver (para despues, con datos reales): consultas que hoy van con seguridad al sitio equivocado
(p. ej. "dress is too small, can I send it back?" -> productos), y los saludos seguidos de una pregunta (R-36). Patron que
queda abierto para T5: compras con una condicion de entrega ("que me llegue antes del sabado") que el LLM lee como
pregunta de envios. Tres rondas sinteticas (v1, v2, v3) muestran que cada ajuste del prompt corrige lo que mira y
descubre un caso nuevo; la siguiente evidencia util es trafico real (modo sombra, ver 7.28 cuando se disene).

### 7.28 R-32 M4: implementacion de T1 con el prompt v3 (laboratorio, 27/11)

Decision [Y]: "vamos con el siguiente paso" (implementar T1/v3, 7.27). Hecho en el laboratorio sobre el codigo de
`2f312e9` (extraido con `git archive` del repo; el `intent_detection.py` coincide con el desplegado, `24c2a38a...`).

**Donde va la capa** [V, lectura de codigo]: en `mcp_conversation_handler.py`, justo despues de calcular el umbral
efectivo (`_effective_threshold`) y antes de `if intent_result.confidence >= _effective_threshold:`. Ahi la condicion
"este mensaje acabaria en el menu de ayuda" es exactamente la del laboratorio (INFORMATIONAL + `unknown` + confianza
>= umbral, con el umbral de 0,5 o 0,7 que decide el handler). Ponerla en `hybrid_detector.py` habria obligado a
duplicar la logica del umbral. El menu sale de `knowledge_base_v2.get_answer(InformationalSubIntent.UNKNOWN)`.

**Ficheros** (lab: `m4impl/new`):

| Fichero | Cambio |
|---|---|
| `src/api/core/llm_intent_router.py` (nuevo) | Prompt v3 literal (13 etiquetas), `parse_router_label` (igual que el laboratorio), `should_rescue` (disparador T1), `apply_router_decision`, `classify_unknown_route` (llamada con limite de tiempo, nunca lanza), `rescue_if_unknown` (punto de entrada) |
| `src/api/core/mcp_conversation_handler.py` | 1 llamada: `intent_result = await rescue_if_unknown(intent_result, conversation_query, _effective_threshold)` |
| `src/api/core/claude_config.py` | `get_intent_router_llm_config()`: uso `intent_router`, variable `INTENT_ROUTER_LLM_MODEL`, 12 tokens, temperatura 0 |
| `src/api/core/llm_routes.py` | Uso `intent_router` y 4 caminos: `topic`, `product_search`, `no_label`, `failed` |
| `src/api/core/prometheus_metrics.py` | Solo el comentario (16 series en vez de 12) |
| `env-vars.yaml` | `INTENT_ROUTER_ENABLED: "true"`, `INTENT_ROUTER_LLM_MODEL: "openai/gpt-4.1-mini"`, `INTENT_ROUTER_TIMEOUT_S: "3"` (41 -> 44 variables planas) |
| `tests/unit/test_r32_llm_intent_router.py` (nuevo) | 44 pruebas (57 con el corte automatico, 7.30) (prompt = hash medido, lectura de etiquetas, disparador, decisiones, tiempo agotado, errores, metrica, log sin texto del cliente, handler con la capa encendida/apagada/fallando y rama de compra, detenida al entrar para no ejecutar el flujo de productos) |
| `tests/unit/test_llm_use_config_and_routes.py` | El cuarto uso en las pruebas de configuracion por uso y de `env-vars.yaml` |

Garantias de diseno: con "none", una etiqueta no valida, tiempo agotado (3 s; p95 medido 1,2 s), error o la capa
apagada, el resultado es el mismo objeto de antes (el menu). `product_search` -> TRANSACTIONAL / `product_search`, la
misma convencion que usa el detector hibrido cuando el ML cambia la intencion a compra. El texto del cliente no va al
log (solo su longitud); token fijo `intent_llm_router` para contar decisiones y metrica
`recommender_llm_route_total{use="intent_router"}`. Interruptor `INTENT_ROUTER_ENABLED` (apagado por defecto en el
codigo) para desactivarla sin reconstruir la imagen.

Verificacion en el laboratorio [V]:
- Pruebas: las 44 nuevas + las de configuracion por uso + `test_handler_kb_unavailable.py` + `test_r32_routing_rules.py`:
  99 en verde. `tests/unit` completo: 880 -> 925 en verde, y **los mismos 47 fallos/errores que el codigo de partida**
  (entorno del laboratorio sin Redis ni mercados, y la prueba desactualizada de la capa 3; lista identica, `diff` vacio).
  Las pruebas nuevas no cargan con el codigo anterior (el modulo no existe).
- **Equivalencia con la medicion** (`m4impl/equiv/equivalencia_t1.py`): las 420 consultas de los seis conjuntos con su
  resultado de intencion grabado y la etiqueta v3 grabada, pasadas por las funciones del codigo nuevo: 690/840 aciertos,
  196 llamadas al LLM, **0 rutas distintas de la simulacion T1/v3**. La reconstruccion del resultado grabado reproduce la
  ruta de hoy en 420/420.

Paquete de despliegue (`r32m4_paquete.zip`): `r32m4_0_sondas.ps1` (antes/despues), `r32m4_1_aplicar_probar_commit.ps1`
(comprueba HEAD `2f312e9` y el hash de cada fichero antes de copiar; pruebas; commit A codigo y B DCT; el DCT ya esta en el
repo), `r32m4_2_construir_desplegar.ps1`, `r32m4_3_validar.ps1` (55/11 variables, decisiones `intent_llm_router` en los
logs por camino y con su tiempo, controles sin la capa, tiempos antes/despues) y `r32m4_vuelta_atras.ps1` (a `00349-88s`;
alternativa: `INTENT_ROUTER_ENABLED: "false"` sin reconstruir).

Sondas de produccion (`sondas_r32_m4.json`, 25): 16 de rescate (hoy `kb:unknown`; etiqueta v3 estable en las dos
repeticiones; 15 deben acabar bien y 1, "¿Cuanto cobran por reparar un zapato?", se predice en cuidado, que no es la
pagina aceptada) y 9 de control que no deben cambiar (4 paginas por reglas, 4 compras, 1 saludo).
Despliegue: un cambio (codigo + las 3 variables), imagen nueva, base y validacion el mismo dia; vuelta atras a
`00349-88s`.

### 7.29 R-32 M4: revision antes de desplegar (28/11)

Peticion [Y]: valorar si T1/v3 es optima y solida (rendimiento y mantenimiento) antes de ejecutar el paquete.

Rendimiento [V]: latencia de gpt-4.1-mini en todas las llamadas medidas (2418, desde Windows): p50 860 ms, p95 1190 ms,
p99 1671 ms, maximo 6956 ms; 5 de 2418 (0,2 %) por encima del limite de 3 s, que en produccion acabarian en el menu.
Solo pasa por el LLM el ~23 % de los mensajes (los que hoy reciben el menu). Coste ~0,05 USD por 1000 mensajes.

Valoracion [H]: solida como paso incremental (no puede empeorar nada: solo actua donde hoy se entrega el menu, y
cualquier fallo vuelve al menu), pero no optima en absoluto: deja sin tocar los mensajes que hoy van con seguridad al
sitio equivocado y los saludos con pregunta (R-36). Riesgos de mantenimiento identificados:
- **El prompt describe el contenido de las paginas de prueba** ("30 dias", "etiqueta prepagada", "PayPal"...). Cuando
  las paginas se sustituyan por las del cliente real, esas descripciones pueden dejar de ser ciertas: hay que revisarlas
  y volver a medir en ese momento. Igual si se anade una pagina (un sub_intent nuevo).
- **Dependencia externa en el camino de la respuesta**: si OpenRouter cae, cada mensaje rescatado espera 3 s antes del
  menu. No hay corte automatico tras fallos seguidos (circuit breaker) ni alerta sobre `route=failed`.
  -> Corte automatico incluido antes de desplegar (decision [Y] del 28/11, 7.30). La alerta queda pendiente.
- **Cuatro capas de deteccion**: reglas, sklearn, MiniLM y LLM. Con trafico real en modo sombra se podra decidir si
  alguna sobra, o entrenar un clasificador local con las etiquetas del LLM (sin red en el camino de la respuesta).
- La evaluacion es con conjuntos sinteticos escritos en el laboratorio (tienda de demostracion sin trafico real).

Modelos de Marqo en Hugging Face (organizacion `Marqo`, 38 modelos): el sistema YA usa `Marqo/marqo-fashionSigLIP`
desde abril (busqueda visual, F-08, outfit). Su ficha anuncia "Marqo Fashion SigLIP 2" (+78 % de MRR y recall segun
Marqo), pero no aparece entre los modelos publicados de la organizacion: sin confirmar que haya pesos abiertos [H].
`marqo-ecommerce-embeddings-L` (652M, 1024 dimensiones, F32) no cabe en el embedding-service de 2 GiB;
`-B` es generalista y su ficha no se compara con FashionSigLIP. Los modelos de texto (stella_en, gcl-e5, chimera) son
en ingles y no resuelven el enrutado; `multilingual-e5-small` es una copia del de Microsoft. La torre de texto de
FashionSigLIP esta marcada como ingles: las consultas en es/fr no deben ir directas a `encode_text`.

### 7.30 R-32 M4: corte automatico (circuit breaker) antes de desplegar (28/11)

Decision [Y]: "vamos a incluir el corte automatico ahora" (riesgo de 7.29: con OpenRouter caido cada mensaje
rescatado esperaria 3 s). Mismo cambio y mismo despliegue que 7.28; solo crece `llm_intent_router.py`.

Diseno (patron clasico de tres estados, por instancia, en memoria) [V, codigo y pruebas]:
- **Cerrado**: se llama al LLM; se cuentan los fallos SEGUIDOS. Solo cuentan tiempo agotado y errores; "none" o una
  etiqueta no valida son respuestas del LLM y reinician el contador.
- **Abierto**: al llegar a `INTENT_ROUTER_BREAKER_FAILURES` fallos seguidos (3), no se llama al LLM durante
  `INTENT_ROUTER_BREAKER_COOLDOWN_S` (60 s): el mensaje recibe el menu al instante. Camino nuevo de la metrica
  `breaker_open` y aviso `intent_llm_router_breaker state=open` (WARNING, para poder contarlo y alertar).
- **Semiabierto**: pasado el tiempo de espera, UNA llamada de prueba; los mensajes que llegan mientras esta en curso
  reciben el menu (sin avalancha de esperas). Si responde -> cerrado (`state=closed`); si falla -> abierto otros 60 s.
- Sin Redis ni locks: todo ocurre en el bucle de asyncio de un proceso; cada instancia de Cloud Run descubre la caida
  por su cuenta con como mucho 3 esperas.

Coste de una caida de OpenRouter por instancia: 3 mensajes con 3 s de espera, despues menu al instante, y una espera
de 3 s como mucho por minuto (la llamada de prueba). Sin el corte: 3 s en cada mensaje rescatado.

Ficheros que cambian respecto a 7.28: `llm_intent_router.py` (corte), `llm_routes.py` (camino `breaker_open`),
`prometheus_metrics.py` (comentario: 17 series), `env-vars.yaml` (+2 variables: 41 -> 46 planas; 57 en total con 11
secretas), `test_r32_llm_intent_router.py` (+13 pruebas: 57). Verificacion [V]: 112 pruebas del area en verde;
`tests/unit` 938 en verde con los mismos 47 fallos/errores previos del entorno del laboratorio (`diff` vacio);
equivalencia con la simulacion intacta (690/840, 0 rutas distintas). El paquete `r32m4_paquete.zip` se rehace
(hashes nuevos; la validacion espera 57/11 variables y 0 aperturas del corte).

### 7.31 R-32 M4: despliegue y validacion en produccion (28/11)

Ejecutado por Yasmani con `r32m4_paquete_v2.zip` [V, salida de su terminal y JSONL de las sondas]:
- Linea base en `00349-88s` (01:59): 24 de 25 sondas como predijo el laboratorio.
- `r32m4_1`: HEAD `2f312e9`, los 8 ficheros con el hash esperado antes y despues de copiar; **151 pruebas en verde**
  (1 desactualizada excluida a la vista); commits `8402efd` (codigo) y `53b06b2` (DCT).
- `r32m4_2`: imagen `53b06b2`, digest `sha256:9202aab6...`, revision **`retail-recommender-00350-d66`** con el 100 %
  del trafico. Digest desplegado == construido. 57 variables (11 secretas), las 5 `INTENT_ROUTER_*` con su valor.
- Sondas despues (02:23) y `r32m4_3`:

| | Antes (00349-88s) | Despues (00350-d66) |
|---|---|---|
| Ruta correcta (25 sondas) | 9 | **24** |
| Como predijo el laboratorio | 25 | **25** |
| Sondas que empeoran | - | **0** |
| ERROR en la revision nueva | - | 0 |
| Decisiones de la capa en los logs | - | 16 (12 `topic`, 4 `product_search`), una por sonda de rescate |
| Corte automatico abierto | - | 0 |
| Controles con la capa actuando | - | 0 |

- Las 16 sondas de rescate acabaron donde predijo el laboratorio: 15 en su pagina o en productos y la prevista como
  error ("¿Cuanto cobran por reparar un zapato?" -> cuidado, en vez de garantia).
- El script mostro 24/25 y "DISTINTO" en G-01 ("hola"), pero es un **fallo del script de sondas, no del sistema**: la
  respuesta fue `primary_intent=greeting` (plantilla de saludo, 254/266 ms) antes y despues; el script solo distinguia
  `kb:<tema>` y "productos" y clasifico el saludo como productos. Corregido el recuento: 25/25 como se predijo, 9 -> 24
  rutas correctas.
- Tiempos: el LLM tardo en produccion mediana 511 ms (437-769) frente a 860 ms medidos desde Windows. Las sondas de
  rescate pasan de mediana 370 ms (el menu, inmediato e inutil) a 1957 ms: la llamada al LLM mas la respuesta real
  (pagina de ayuda o busqueda de productos, ~2,8 s). Controles sin cambio (1378 -> 999 ms, ruido).
- Observacion aparte [H]: la primera sonda de la linea base tardo 111,9 s en `00349-88s` (arranque en frio a las 2 de
  la madrugada); despues del despliegue la primera tardo 3,8 s. No tiene que ver con M4.

Pendiente: `git push` (lo ejecuta Yasmani); alerta sobre `route=failed` / `state=open`; R-36 (saludo que se traga la
pregunta); modo sombra para medir T5 con trafico real; revisar las descripciones del prompt cuando lleguen las paginas
del cliente real (7.29).

### 7.32 R-36: el saludo ya no se traga la pregunta (laboratorio, 28/11)

Problema [V, 7.22-7.27]: el paso 0 de las reglas devuelve GREETING (0,95, sin pasar por ninguna otra capa) para
cualquier mensaje que EMPIECE por un saludo en es/en. En los seis conjuntos de R-32, 16 de los 20 mensajes que empiezan
por saludo traen una pregunta o una compra y reciben solo la plantilla ("hola! busco un bolso negro de cuero",
"buenas, cuanto tarda el envio a mexico?"). La capa LLM (T1) no los ve: no acaban en el menu.

Diseno: el saludo solo gana si el mensaje es SOLO un saludo (`is_greeting_only`: palabras de saludo y cortesia en
es/en/fr, signos y emojis, hasta 80 caracteres; "hola", "buenas tardes!", "hola, que tal?", "hey 👋", "hi there").
Si trae algo mas, el mensaje sigue la deteccion normal. Dos variantes:
- **A**: deteccion normal sobre el mensaje COMPLETO (solo cambia `_detect_greeting`).
- **B**: ademas se QUITA el saludo del principio antes de las tres capas (`strip_greeting_prefix`, en el detector de
  reglas y en el hibrido), porque el saludo no aporta tema y confunde a las capas estadisticas.

Medicion con el arnes (MiniLM grabado) en los seis conjuntos y T1/v3 encima con las etiquetas v3 grabadas
(`/home/claude/lab/r36/medir_r36.py`; la base es el codigo desplegado en `00350-d66`) [V]:
- Control del arnes con el codigo desplegado: 419/420 rutas iguales a las grabadas en Windows (la diferencia, P-11 en
  "do you have long dresses in green?", no tiene saludo: sklearn da 0,848 en Windows y menos de 0,6 en el laboratorio,
  con las mismas versiones; sin explicar). Por eso las variantes se comparan con la base pasada por el MISMO arnes.
- **Variante A: 345 -> 356 de 420 (+11, 0 perdidas)** en las dos repeticiones. Ganan G-03, G-04, G-05, G-06, G-07 (es/en)
  y X-01 en. Siguen mal: X-01 es ("hola!! a las zapas q compre se les despego la suela...": las reglas ya no lo tratan
  como saludo, pero MiniLM lo lleva al prototipo de saludo, coseno 0,53, por el "hola!!") y G-08 es/en ("como saco
  una mancha de grasa...": tallas y productos con seguridad, no es un problema del saludo).
- **Variante B**: pendiente de medir. Necesita la prediccion de MiniLM de los 14 textos sin saludo, que el laboratorio
  no puede calcular: `r36_restos_paquete.zip` (`r36_restos.json`, sha256 `20552b4b...`) la graba en el equipo de
  Yasmani con el codigo del repo sin cambios.

Pendiente de decidir [Y] con la medicion de B: A (cambio minimo) o B (si gana algo mas sin perder nada).

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
- **Predecir las sondas antes de desplegar convierte la validacion en una prueba**: el laboratorio predijo la ruta de las
  28 sondas antes y despues (28 de 28 en ambas). Una sonda que no coincidiera habria senalado una diferencia entre el
  laboratorio y produccion antes de dar el cambio por bueno, en vez de descubrirla despues.
- **Fijar el criterio antes de medir y respetarlo cuando no favorece**: T5 con v3 acertaba el 97 % y T1 el 82 %, pero el
  criterio escrito antes de medir exigia cero perdidas en un conjunto nunca visto, y T5 perdia 3 compras. Si se cambia el
  criterio despues de ver el resultado, la validacion deja de ser una prueba.
- **Un script de sondas debe saber traducir TODAS las respuestas posibles**: el de M4 heredo del de R-32 (reglas) una
  traduccion con solo dos rutas (pagina o productos) y marco como fallo un saludo correcto. Al anadir un tipo de sonda
  nuevo (aqui, el saludo) hay que comprobar que el script sabe reconocer su respuesta.
- **Los avisos "LF will be replaced by CRLF" de git en Windows**: el repo guarda LF, pero la copia de trabajo puede
  pasar a CRLF la proxima vez que git toque el fichero, y entonces su sha256 cambia aunque el contenido no. Las guardias
  por hash de los scripts deberian comparar el contenido normalizado (`git hash-object`) o aceptar los dos finales.
