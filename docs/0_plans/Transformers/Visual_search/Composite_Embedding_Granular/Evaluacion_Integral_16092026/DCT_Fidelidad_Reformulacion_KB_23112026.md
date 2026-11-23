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
| R-18 | **Limite de tokens distinto del previsto**: el codigo calcula 250 tokens (500 para tallas), pero ese valor solo se usa en la ruta de Claude; GPT-4o-mini usa el de su configuracion, 300. Para tallas, 300 en lugar de 500: una tabla larga puede salir cortada, y el cliente no lo devuelve (`LLMResponse` no guarda `finish_reason`), asi que el corte no se ve [V, codigo `kb_contextualizer.py` y `llm_client.py`] | Media para tallas (dato incompleto), Baja para el resto | Medir: longitud de las respuestas de tallas en el banco de pruebas |
| R-19 | **El prompt de tallas no pide cenirse al documento ni decir "no lo se"**: es el tema con mas numeros (medidas) y el unico sin esas dos instrucciones [V, codigo] | Media [H: por medir] | Medir antes de cambiar |

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

## 4. Plan de la investigacion (propuesta, pendiente de decisiones [Y])

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

Decisiones pendientes [Y]:
- Via del banco de pruebas: llamar a la funcion directamente (propuesta) o pasar por el chat de produccion.
- Idiomas: es/en/fr (los publicados) como propuesta.
- Fuente de los documentos: `kb_contents` (lo que el chat sirve; propuesta) o las paginas de Shopify.

## 5. Lecciones

- **Un respaldo que pasa a principal necesita la evaluacion del principal**: GPT-4o-mini se eligio como respaldo
  "suficientemente bueno" para ~5 % del trafico; tras apagar LFM responde el 100 % y nadie midio lo que importa
  ahora (apego al documento).
- **Lo que no se registra no se puede auditar**: guardar solo la longitud de una respuesta generada impide saber
  despues que se le dijo al cliente.
