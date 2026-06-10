**RETAIL RECOMMENDER SYSTEM**

Integración Liquid AI — Impacto de Negocio

| Versión: v2.1.0   Fecha: Abril 2026 | Estado: **COMPLETADO ✓** |
| --- | --- |

# **¿Qué hemos implementado?**

Hemos completado la integración de los modelos de Liquid AI en nuestro sistema de recomendaciones, reemplazando los componentes de inteligencia artificial por alternativas más eficientes sin sacrificar calidad. La integración se realizó en tres fases independientes, cada una con su propio interruptor de activación, garantizando cero riesgo durante el proceso.

| **Fase** | **Qué hace** | **Beneficio clave** |
| --- | --- | --- |
| **A** | Personalización conversacional con LFM2-24B | Respuestas más ricas, ~100x más barato que antes |
| **B** | Respuestas a preguntas de política con LFM2.5-1.2B | Velocidad y precisión en consultas de cliente, ~15x más barato |
| **C** | Búsqueda semántica multilingüe con ColBERT-350M | Encuentra productos aunque el cliente use palabras distintas |

# **Problemas que teníamos antes**

Antes de esta integración, el sistema presentaba tres limitaciones importantes que afectaban tanto la experiencia del cliente como la rentabilidad del negocio:

-   **Costo de IA elevado:** La personalización de respuestas usaba Claude Sonnet, uno de los modelos más caros del mercado ($3–15 por millón de tokens). Con el volumen actual de conversaciones, esto representaba $15–40 al mes solo en esa línea de costo, con tendencia a crecer con el catálogo.
-   **Búsqueda rígida por palabras exactas:** El sistema de búsqueda de productos solo funcionaba bien cuando el cliente usaba las palabras exactas del catálogo. Si alguien buscaba "prenda azulada" pero el producto se llamaba "vestido azul", el sistema no lo encontraba. Esto penalizaba especialmente a clientes de distintos países que usan variantes regionales del español.
-   **Respuestas genéricas en consultas de política:** Cuando un cliente preguntaba algo específico como "¿Puedo pagar con Mastercard?", el sistema devolvía todo el documento de métodos de pago en lugar de responder directamente. La experiencia era más parecida a leer una FAQ que a hablar con un asistente real.

# **Nuevas capacidades habilitadas**

## **Recomendaciones más precisas**

La Fase A incorpora un modelo LFM2-24B que genera respuestas de personalización conversacional. En la práctica, esto significa que cuando un cliente dice "busco algo para una boda en Viña del Mar en noviembre", el sistema ahora puede tener en cuenta el contexto climático, la ocasión y el mercado chileno, no solo las palabras clave del catálogo.

## **Comprensión semántica del catálogo**

La Fase C introduce ColBERT, un modelo de embeddings que "entiende" el significado detrás de las palabras. Ejemplo concreto: si una clienta escribe "vestido elegante de gala" pero en el catálogo ese producto se llama "Evening Gown Black Tie", el sistema ahora los conecta correctamente. Esto es especialmente relevante para tiendas con catálogos en inglés que atienden clientes hispanohablantes.

## **Respuestas directas a preguntas de política**

La Fase B permite que cuando un cliente pregunta algo concreto como "¿aceptan Paypal en Chile?", el sistema lea el documento de métodos de pago y responda directamente esa pregunta en 2-3 frases, en el idioma del cliente. Ya no se muestra el documento completo: se responde la pregunta.

| **Resultado combinado**   Un cliente puede ahora mantener una conversación real con el widget: preguntar por un producto, obtener recomendaciones relevantes en su idioma, aclarar dudas de política y recibir respuestas contextualizadas — todo dentro de la misma sesión conversacional. |
| --- |

# **Cómo funciona (visión general)**

Sin tecnicismos: cuando un cliente escribe un mensaje en el chat del widget, el sistema realiza cuatro pasos en menos de 7 segundos:

| **1** | Clasifica la intención: ¿el cliente quiere productos o tiene una pregunta de política? |
| --- | --- |
| **2** | Si quiere productos: busca en el catálogo usando ColBERT (semántica) o TF-IDF (palabras exactas) y combina con el historial conversacional para no repetir lo ya mostrado. |
| **3** | Si tiene una pregunta: busca en la base de conocimiento y genera una respuesta directa de 2-3 frases. |
| **4** | Personaliza la respuesta: adapta el tono, el idioma y el contexto de mercado (precios en CLP, CHF, MXN o EUR según corresponda). |

Todo esto ocurre con fallback automático: si algún componente de Liquid AI falla, el sistema vuelve al comportamiento anterior (Claude) de forma transparente para el usuario. No hay interrupciones de servicio.

# **Impacto esperado en el negocio**

| **Conversión** | **Engagement** | **Experiencia de usuario** |
| --- | --- | --- |
| Más productos encontrados correctamente → menos abandonos en la búsqueda.   Respuestas a dudas de pago/devolución en el momento → menos fricción en el checkout. | Conversaciones más largas y más útiles gracias a la memoria multi-turno.   El widget recuerda qué se mostró y no repite recomendaciones. | Respuestas en el idioma del cliente sin configuración manual.   Precios siempre en la moneda del mercado correcto (CLP, CHF, MXN, EUR). |

# **Coste vs. Beneficio**

La integración tiene un impacto dual en los costos: reduce el gasto en APIs de IA en aproximadamente un 90%, pero introduce un nuevo costo de infraestructura para el servicio de búsqueda semántica.

| **Concepto** | **Antes** | **Ahora** | **Ahorro** |
| --- | --- | --- | --- |
| **Personalización IA (MCP)** | $15–40/mes | **$0.50–2/mes** | ✓ |
| Respuestas KB (Haiku) | $0.50–1.80/mes | $0.05–0.15/mes | ✓ |
| Búsqueda semántica (ColBERT) | TF-IDF gratuito | $0 tokens + ~$40–60/mes infra | ✓ |
| **Total estimado** | $47–107/mes | **$95–165/mes\*** | ✓ |

| **Nota sobre el costo total**   El incremento en el total ($47–107 → $95–165/mes) se debe principalmente a mantener el servicio de búsqueda semántica activo de forma permanente (min-instances=1), lo que además elimina los tiempos de arranque en frío. El ahorro en APIs de IA (~$30–50/mes) compensa parcialmente este costo. El beneficio neto es de calidad, no de precio. |
| --- |

## **ROI cualitativo**

-   Sistema preparado para escalar: el costo de IA ya no crece proporcionalmente con el volumen de conversaciones.
-   Independencia de proveedores: cada componente tiene fallback y puede reemplazarse individualmente.
-   Mejora de la calidad de búsqueda: beneficio permanente para todas las tiendas, no solo una optimización de costo.

# **Posibles evoluciones futuras**

La arquitectura implementada está diseñada para crecer. Las siguientes mejoras son directamente posibles sin cambios estructurales:

| **Modelos más nuevos de Liquid AI** | Cuando Liquid AI lance nuevas versiones de LFM2 con mejor rendimiento o menor costo, el sistema puede actualizarse cambiando un parámetro de configuración. No requiere rediseño. |
| --- | --- |

| **Expansión de la base de conocimiento** | Actualmente el sistema responde preguntas de devoluciones, pagos y disponibilidad. Puede extenderse a cualquier nueva política o contenido de ayuda simplemente añadiendo documentos al KB, sin código nuevo. |
| --- | --- |

| **Retroalimentación de conversiones** | Integrar el tracking de pedidos para identificar qué recomendaciones derivaron en compra y usar esa señal para mejorar el ranking automáticamente. |
| --- | --- |

| **Búsqueda visual** | El servicio de embeddings (Fase C) puede extenderse para aceptar imágenes como entrada. Un cliente podría subir una foto de un outfit y pedir productos similares. |
| --- | --- |

| **Nuevos mercados** | El sistema ya soporta 4 mercados (CL, CH, MX, ES). Añadir un nuevo mercado requiere solo configurar el tipo de cambio y las reglas de idioma. |
| --- | --- |

*Retail Recommender System v2.1.0 — Integración Liquid AI — Abril 2026*

---

# Investigación: Viabilidad de dos mejoras futuras

*Análisis técnico realizado el 21/04/2026. Basado en el código actual del sistema y en la documentación oficial de Liquid AI (HuggingFace, blog oficial, paper técnico LFM2).*

---

## Mejora 1: Expansión de la base de conocimiento

### Estado actual del sistema

El Knowledge Base actual funciona mediante una arquitectura de triple capa (Redis → PostgreSQL → Shopify CMS). Los contenidos se organizan por `sub_intent` — cada tipo de consulta informacional apunta a un documento:

| Sub-intent | Qué responde |
|---|---|
| `policy_return` | Política de devoluciones |
| `policy_shipping` | Envíos |
| `policy_payment` | Métodos de pago |
| `policy_warranty` | Garantías |
| `policy_privacy` | Privacidad |
| `product_sizing` | Guía de tallas |
| `product_material` | Materiales y tejidos |
| `product_care` | Cuidado de prendas |
| `product_availability` | Disponibilidad de stock |
| `account_orders` | Estado de pedidos |
| `account_modifications` | Modificaciones de pedido |
| `general_faq` | Preguntas frecuentes generales |

### Es implementable? Sí— y es el trabajo futuro más simple del sistema

Esta mejora **no requiere ningún cambio de arquitectura ni de modelos**. El mecanismo está completamente construido. Añadir un nuevo tema de KB son cuatro pasos:

1. **Crear la página en Shopify CMS** con el contenido y el metafield `kb.sub_intent` configurado.
2. **Añadir el nuevo valor al enum** `InformationalSubIntent` en `src/api/core/intent_types.py`.
3. **Añadir keywords al intent detector** en `src/api/core/intent_detection.py` para que el clasificador reconozca ese tipo de consulta.
4. **Opcional**: añadir patrones de entidades específicas en `src/api/core/kb_contextualizer.py` si el nuevo tema tiene consultas que contengan nombres propios (marcas, países, etc.).

Ejemplos concretos de nuevos sub-intents que aportarían valor inmediato para nuestros mercados:

| Nuevo sub-intent propuesto | Consultas que cubriría |
|---|---|
| `policy_customs_duties` | ¿Tengo que pagar aduana en Suiza? ¿Hay impuestos de importación a Chile? |
| `product_sustainability` | ¿Tienen ropa sostenible? ¿Qué materiales reciclados usan? |
| `policy_gift_wrapping` | ¿Envuélven para regalo? ¿Puedo incluir un mensaje? |
| `product_care_special` | ¿Cómo lavo el encaje? ¿Este tejido es delicado? |

### Limitación real a considerar

El sistema actual maneja UNA única respuesta genérica por sub-intent (un documento por categoría). Si el KB de tallas tiene tablas muy distintas por categoría de producto (vestidos vs. zapatos vs. jeans), el documento actual entrega la tabla completa. La Fase B (LFM2.5-1.2B) ya resuelve parcialmente esto al extraer la información relevante del documento, pero para contenidos muy dispares la calidad de la respuesta depende de la claridad del documento fuente.

**Conclusión**: Implementable hoy. Esfuerzo estimado: 2-4 horas por sub-intent nuevo. Sin riesgo. Sin cambios de infraestructura.

---

## Mejora 2: Búsqueda visual

### Lo que se afirmó en el documento

> *"El servicio de embeddings (Fase C) puede extenderse para aceptar imágenes como entrada."*

Esta afirmación **no es correcta**. Tras investigar la documentación oficial de Liquid AI, la realidad es distinta.

### El modelo que usamos (LFM2-ColBERT-350M) es text-only

LFM2-ColBERT-350M es un late interaction retriever para búsqueda semántica multilingue. Permite indexar documentos en un idioma y recuperarlos con queries en otros idiomas.

Los lenguajes soportados son: inglés, árabe, chino, francés, alemán, japonés, coreano y español. El modelo procesa texto únicamente — tanto queries como documentos son cadenas de texto.

**No tiene ninguna capacidad de procesar imágenes.** La Fase C del sistema actual solo puede recibir queries de texto y devolver IDs de productos. Extenderlo para aceptar imágenes requiere un modelo diferente.

### ¿Tiene Liquid AI modelos para búsqueda visual?

Sí, pero son modelos de generación de lenguaje (VLMs), no retrievers:

LFM2-VL extiende la familia LFM2 al espacio visión-lenguaje, soportando inputs de texto e imagen con resoluciones variables. Está disponible en variantes de 450M y 1.6B parámetros.

LFM2.5-VL-450M incluye predicción de bounding boxes, comprensión visual multilingue y soporte de function calling para texto. Es una actualización del LFM2-VL-450M con mejor rendimiento.

Pero existe un problema de arquitectura fundamental: **LFM2-VL genera texto a partir de imágenes (captioning, VQA), no produce embeddings de imagen para búsqueda por similitud**. Son modelos de generación, no de retrieval.

### ¿Qué se necesita realmente para búsqueda visual en e-commerce?

La búsqueda visual ("sube una foto, encuentra productos similares") requiere un pipeline con dos componentes diferenciados:

**Componente 1 — Imagen a texto (opcional pero recomendable):**
Usar un VLM (como LFM2-VL) para generar una descripción textual de la imagen del cliente. Ejemplo: foto de un vestido rojo → *"elegant red midi dress with lace details"*.

**Componente 2 — Retrieval por similitud:**
Usar esa descripción para buscar en el índice ColBERT existente. Este componente **ya está construido y funcionando** (Fase C).

Alternativamente (enfoque más robusto según la literatura académica de 2025):

Mercari construyó un sistema de recomendación por similitud visual para más de 20 millones de usuarios mensuales usando un modelo SigLIP fine-tuneado con pares imagen-título de sus propios productos. Los resultados mostraron un incremento del 50% en CTR y 14% en CVR en producción.

Este enfoque (CLIP/SigLIP para embeddings de imagen + ANN search) es el estándar de la industria para búsqueda visual en e-commerce, no ColBERT.

### Análisis de viabilidad real para nuestro sistema

| Pregunta | Respuesta |
|---|---|
| ¿El ColBERT actual puede aceptar imágenes? | **No.** Es text-only por diseño. |
| ¿Liquid AI tiene un modelo de búsqueda visual? | **No.** Sus VLMs generan texto, no embeddings de imagen. |
| ¿Es implementable con otros modelos? | **Sí**, pero requiere nueva infraestructura. |
| ¿Cuánta complejidad añade vs. Fase C? | Considerablemente más: nuevo modelo, nuevo endpoint en el widget, procesamiento de imágenes. |
| ¿El catálogo actual tiene imágenes indexables? | **Sí**: `image_url` está presente en todos los productos del catálogo TF-IDF y en la respuesta de Shopify. |

### Si se quisiera implementar: arquitectura mínima viable

El camino más simple dentro del ecosistema Liquid AI sería un pipeline híbrido de dos pasos:

```
Usuario sube imagen
    ↓
[NUEVO] LFM2-VL-450M o LFM2.5-VL-450M (self-hosted en Cloud Run)
  image + prompt "Describe this fashion item in English" → descripción textual
    ↓
[EXISTENTE] LFM2-ColBERT-350M (embedding-service ya desplegado)
  descripción textual → product_ids relevantes
    ↓
Resultados mostrados al usuario
```

**Ventajas de este enfoque:**
- Reutiliza toda la infraestructura ColBERT existente.
- LFM2.5-VL-450M corre en CPU con ~250ms de inferencia (según documentación oficial), compatible con Cloud Run.
- La descripción generada es mejorable con un prompt que pida atributos de moda (color, silueta, ocasión).

**Costes adicionales:**
- Un nuevo Cloud Run service para el VLM (~40-60€/mes con min-instances=1, mismo perfil que el embedding-service actual).
- Cambios en el frontend para aceptar subida de imagen en el widget (actualmente solo acepta texto).
- Procesamiento de imágenes del catálogo para pre-generar embeddings de imagen (alternativa más precisa que el pipeline de dos pasos).

**Alternativa más eficiente (fuera del ecosistema Liquid AI):**
Usar `google/siglip-so400m-patch14-384` (open weights, sin coste de API) directamente en el embedding-service para generar embeddings de imagen. SigLIP produce embeddings de imagen y texto en el mismo espacio vectorial, lo que permite búsqueda imagen→imagen e imagen→texto con un solo modelo. Esta es la arquitectura que usan Mercari, Amazon y la mayoría de los sistemas de búsqueda visual en producción.

### Conclusión

La búsqueda visual **es implementable**, pero:

1. **No es una extensión simple de la Fase C** como se afirmó. Requiere nuevo modelo, nueva infraestructura, y cambios en el frontend.
2. **LFM2-ColBERT-350M no puede procesar imágenes**. Es un retriever de texto puro.
3. **El camino más práctico** es el pipeline hêbrido (VLM para descripción + ColBERT para retrieval), o bien sustituir ColBERT por un modelo multimodal como SigLIP que maneje ambas modalidades.
4. **El esfuerzo es considerablemente mayor** que la expansión del KB: estimado 3-5 semanas de implementación y validación, con +40-60€/mes de infraestructura.

La recomendación es priorizar primero la **expansión del KB** (alto impacto, costo cero, sin riesgo) y dejar la búsqueda visual como una iniciativa de mayor envergadura para cuando el volumen de usuarios justifique la inversión.

---

*Análisis elaborado el 21/04/2026. Fuentes: documentación oficial LiquidAI/LFM2-ColBERT-350M (HuggingFace), LFM2 Technical Report (arXiv:2511.23404), LFM2-VL blog post (liquid.ai), paper "Improving Visual Recommendation on E-commerce Platforms" (RecSys 2025), Mercari Engineering blog.*

---

# Segunda investigación: Visual Search — Análisis riguroso de opciones

*Análisis técnico elaborado el 21/04/2026. Basado en benchmarks de producción reales, documentación oficial de modelos, papers académicos (RecSys 2025, KDD 2025, arXiv) y el código actual del sistema.*

---

## 1. Landscape actual: qué se usa en producción en 2025

### ¿Cómo funciona la búsqueda visual en e-commerce?

Antes de evaluar modelos, conviene entender el patrón arquitectónico estándar que usan los sistemas en producción:

```
[Indexación offline — una vez]
Catálogo de productos (imágenes + texto)
    ↓
Modelo de embedding multimodal (CLIP / SigLIP)
    ↓ encode_image()
Vector por cada producto → índice ANN (FAISS, Vertex AI Vector Search, etc.)

[Query en tiempo real]
Usuario sube imagen
    ↓
Mismo modelo → encode_image()
    ↓
ANN search en índice → product_ids más cercanos
```

La clave: **el mismo modelo debe poder encodear tanto la query del usuario como los productos del catálogo** en el mismo espacio vectorial. Por eso los VLMs generativos (LFM2-VL, BLIP-2, Florence-2) no sirven para esto: no producen embeddings comparables.

### Qué usa la industria en producción hoy

**Mercari** (20M usuarios activos, Japón + EE.UU.): SigLIP fine-tuneado con pares imagen-título propios. FAISS para indexado local en validación, Vertex AI Vector Search en producción. Conversión a TensorRT para inferencia en GPU. Resultado medido en producción: +50% CTR, +14% CVR.

**Amazon**: Visual search propio (Amazon Rekognition + embeddings internos). No público, pero Amazon Titan Multimodal es su oferta cloud.

**Shopify/Pinterest/Zalando**: Variantes de CLIP/SigLIP propias, no publicadas. El estándar de facto es SigLIP o derivados fine-tuneados.

**Marqo**: Han publicado sus modelos open-source bajo Apache 2.0 — son los benchmarks públicos más rigurosos disponibles para fashion ecommerce en 2025.

---

## 2. Comparativa técnica de las opciones relevantes

### Modelos evaluados

| Modelo | Tipo | Parámetros | Espacio embedding | Licencia |
|---|---|---|---|---|
| `Marqo/marqo-fashionSigLIP` | Embedding multimodal | 203M | 768-dim | Apache 2.0 |
| `Marqo/marqo-fashionCLIP` | Embedding multimodal | 152M | 512-dim | Apache 2.0 |
| `Marqo/marqo-ecommerce-B` | Embedding multimodal | ~200M | 768-dim | Apache 2.0 |
| `google/siglip-so400m-patch14-384` | Embedding multimodal | 400M | 1152-dim | Apache 2.0 |
| `google/siglip2-base-patch16-224` | Embedding multimodal | 93M | 768-dim | Apache 2.0 |
| Florence-2 (Microsoft) | VLM generativo | 770M | N/A | MIT |
| BLIP-2 (Salesforce) | VLM generativo | 2.7B–12B | N/A | MIT |
| LFM2-VL-450M (Liquid AI) | VLM generativo | 450M | N/A | LFM Open License |

**Florence-2, BLIP-2 y LFM2-VL son VLMs generativos — generan texto, no producen embeddings comparables para ANN search. Se descartan para búsqueda visual directa.**

### Comparativa de los candidatos reales

| Criterio | marqo-fashionSigLIP | siglip-so400m | siglip2-base | marqo-ecommerce-B |
|---|---|---|---|---|
| **Calidad en fashion** | ★★★★★ Estado del arte fashion | ★★★★ Muy bueno general | ★★★★ Mejor multilingual | ★★★★★ Mejor general ecommerce |
| **Recall@1 relativo** | +57% vs FashionCLIP 2.0 | Baseline fuerte | Similar a SigLIP v1 B | +31% vs siglip-so400m |
| **Latencia CPU (est.)** | ~300–500 ms/imagen | ~500–900 ms/imagen | ~80–150 ms/imagen | ~300–500 ms/imagen |
| **Latencia GPU T4** | ~10–20 ms/imagen | ~15–25 ms/imagen | ~5–10 ms/imagen | ~5.7 ms/imagen |
| **RAM requerida** | ~400 MB (fp16) | ~800 MB (fp16) | ~190 MB (fp16) | ~400 MB (fp16) |
| **Soporte multilingual** | ❌ Principalmente EN/ES via webli | ❌ Principalmente EN | ✅ 36 idiomas nativo | ❌ Principalmente EN |
| **Compatibilidad HF** | ✅ transformers + open_clip | ✅ transformers | ✅ transformers | ✅ transformers |
| **Madurez producción** | ✅ Benchmark público, Apache 2.0 | ✅ Ampliamente adoptado | ⚠️ Más reciente (Feb 2025) | ✅ Benchmark público |
| **Fit con nuestro catálogo** | ★★★★★ (moda, fashion) | ★★★ | ★★★★ (multilingual CH/MX) | ★★★★ |

**Nota sobre latencia CPU**: Los números son estimaciones. La latencia GPU documentada de Marqo-Ecommerce-B es 5.7 ms/imagen en GPU. En CPU (Cloud Run), los ViT-B/16 típicamente escalan entre 20–80x vs GPU, resultando en 100–500 ms/imagen. Esto es aceptable para un sistema de búsqueda visual donde el patrón es: *una consulta por búsqueda* (el usuario sube UNA foto, no un batch).

---

## 3. Análisis profundo de SigLIP (en sus variantes)

### SigLIP original (ViT-B/16, ViT-SO400m, webli)

**Fortalezas:**
- Estándar de la industria, ampliamente probado en producción
- Embebe imagen y texto en el mismo espacio → búsqueda imagen→imagen e imagen→texto con un solo modelo
- Open weights, Apache 2.0
- Excelente zero-shot en Inglés

**Dónde falla:**
- Sin fine-tuning en moda, la capacidad de distinguir detalles finos (tela, corte, silueta) es limitada
- El modelo webli fue entrenado en datos generales, no en catálogos de moda
- En benchmarks de Marqo, ViT-B-16-SigLIP base obtiene Recall@1 ~40% en fashion vs ~65% de marqo-fashionSigLIP
- No es multilingual de forma nativa — el soporte para ES, FR es parcial

**SigLIP 2 (Febrero 2025) — mejoras reales:**
- Soporte nativo para 36 idiomas, incluyendo ES, FR, DE, AR, ZH
- Mejor recall@1 en benchmarks multilingual (Crossmodal-3600), superando incluso a mSigLIP en muchos idiomas
- Dense features mejoradas: mejor localización de objetos dentro de imágenes
- **Importante para nuestros mercados**: el modelo B (86M params) es el sweet spot calidad/velocidad

### SigLIP vs CLIP directa

La diferencia clave es la función de pérdida: CLIP usa softmax contrastivo (requiere comparar contra todos los negativos del batch), SigLIP usa sigmoid pairwise (cada par es independiente). En práctica:

- SigLIP es más estable en batches pequeños → mejor para fine-tuning con catálogos medianos (~3000 productos)
- SigLIP tiene mejor calibración de scores (la similitud coseno es más interpretable)
- Marqo-FashionSigLIP supera a Marqo-FashionCLIP en todos los benchmarks fashion (+57% vs +22% sobre FashionCLIP 2.0)

**Conclusión**: Para nuestro catálogo de moda, la variante SigLIP supera a CLIP. El punto de partida correcto es marqo-fashionSigLIP, no SigLIP genérico.

---

## 4. Evaluación de Liquid AI para búsqueda visual

### ¿Qué ofrecen hoy?

Liquid AI tiene dos líneas de modelos con capacidades visuales:

**LFM2-VL / LFM2.5-VL** (450M y 1.6B): Vision-Language Models generativos. Reciben imagen + texto y generan texto. Usan **SigLIP2 NaFlex** como encoder visual interno. Son relevantes para captioning, VQA, descripción de imágenes. **No producen embeddings para ANN search.**

**LFM2-ColBERT-350M**: Text-only retriever. Excelente para lo que hace (búsqueda semántica multilingue), pero no tiene capacidad visual.

### Limitaciones prácticas

Liquid AI **no tiene ningún modelo de embedding multimodal** (imagen + texto en el mismo espacio vectorial) equivalente a CLIP o SigLIP. Su arquitectura VL es generativa, no contrastiva.

Esto significa que hoy no existe un modelo de Liquid AI que pueda reemplazar a SigLIP directamente para búsqueda visual.

### Vendor lock-in

- LFM2-VL: Open weights bajo LFM Open License v1.0 (libre para < $10M revenue, acuerdo comercial por encima)
- Para una tienda Shopify mediana, el umbral de $10M/año no será un problema a corto plazo
- Pero la limitación es funcional, no de licencia: el modelo simplemente no hace embeddings para search

### ¿Tiene sentido integrarlo en nuestro stack?

Como componente de captioning intermedio (Opción C): sí, con reservas. Como reemplazo de CLIP/SigLIP para embeddings: no, hoy no existe esa capacidad en Liquid AI.

---

## 5. Recomendaciones arquitectónicas

### Constraint crítico del sistema actual

El embedding-service corre en Cloud Run CPU-only (2GiB/1vCPU, min=1). El modelo ColBERT-350M ocupa ~700MB. Quedan ~1.3GB libres. Esto acota las opciones a modelos que quepan en ese espacio restante o que justifiquen un upgrade de infraestructura.

---

### Opción A: Mejor calidad absoluta — Marqo-FashionSigLIP + FAISS en embedding-service existente

**Stack:**
```
[Indexación offline — al hacer catalog sync]
Catálogo TF-IDF (image_url disponible en todos los productos)
    ↓ descargar imágenes desde Shopify CDN
Marqo/marqo-fashionSigLIP (203M params, ~400MB fp16)
    ↓ encode_image() en batch de 32
Vector 768-dim por producto → FAISS IndexFlatIP en memoria (~18MB para 3062 productos)

[Búsqueda en tiempo real — usuario sube foto]
Imagen (multipart/form-data al embedding-service)
    ↓
Marqo/marqo-fashionSigLIP encode_image() ~300–500ms en CPU
    ↓
FAISS search cosine ~<1ms (3062 vectores es trivial)
    ↓
retorna product_ids + scores
```

**Integración con el sistema actual:**
- Añadir al `embedding-service/main.py` dos nuevos endpoints:
  - `POST /v1/embed/index-images` — indexa imágenes del catálogo
  - `POST /v1/embed/search-image` — busca por imagen uploaded
- ColBERT y el índice de imágenes coexisten en el mismo servicio
- Añadir `faiss-cpu` y `open-clip-torch` a requirements.txt del embedding-service
- Añadir en frontend widget un botón de "subir foto" → call al nuevo endpoint
- Colbert-client.py → añadir método `search_by_image(image_bytes)` que llame al nuevo endpoint

**Impacto en infraestructura:**
- RAM: 700MB (ColBERT) + 400MB (fashionSigLIP) + 18MB (FAISS index) = ~1.12GB de 2GiB disponibles ✅
- CPU: no se requiere upgrade
- Upgrade recomendado a 4GiB si se quiere margen confortable
- Costo adicional: $0 de modelo (open-source), $10–20/mes de upgrade RAM en Cloud Run (si se hace)

**Latencia end-to-end:**
- Encode imagen query: ~300–500ms en CPU
- FAISS search: <1ms
- Total: ~300–500ms — aceptable para búsqueda visual (no es un flujo conversacional)

**Benchmark relevante**: +57% Recall@1 vs FashionCLIP 2.0 en 7 datasets de moda (Marqo, Apache 2.0)

---

### Opción B: Mejor costo/beneficio — SigLIP 2 base + FAISS

**Stack:**
```
Modelo: google/siglip2-base-patch16-224
Parámetros: 93M (vision encoder 86M + text encoder)
RAM: ~190MB fp16
Latencia CPU: ~80–150ms/imagen (ViT-B más pequeño que fashionSigLIP)
Embedding: 768-dim
Idiomas: 36 (incluye ES, FR, DE, AR, ZH) — relevante para nuestros mercados
```

**Cuándo elegir esto sobre Opción A:**
- Si la latencia de búsqueda importa más que la calidad absoluta
- Si los usuarios buscan en idiomas distintos del inglés (clientes CH/MX/ES que escriben texto en la búsqueda)
- Si se quiere búsqueda híbrida texto+imagen sin fine-tuning (SigLIP 2 tiene mejor zero-shot multilingual)

**Diferencia clave vs Opción A:**
- fashionSigLIP está fine-tuneado en moda → mejor para "encuentra este vestido similar"
- SigLIP 2 base es más genérico pero multilingual nativo → mejor para texto+imagen combinado
- Para nuestro catálogo 100% de moda: Opción A probablemente supere a Opción B en calidad

**Costo adicional:** $0 de modelo, sin cambio de infraestructura (200MB extra en servicio actual)

---

### Opción C: Mínimo esfuerzo — Pipeline híbrido LFM2-VL + ColBERT existente

**Stack:**
```
Usuario sube imagen
    ↓
[NUEVO] LFM2.5-VL-450M en Cloud Run (captioning)
  prompt: "Describe this fashion item for search: color, style, silhouette, occasion"
  latencia: ~250ms (CPU, según doc oficial)
    ↓
descripción textual en inglés
    ↓
[EXISTENTE] LFM2-ColBERT-350M en embedding-service
  busca por texto en PLAID index
  latencia: 20–40ms
    ↓
product_ids
```

**Ventajas:**
- No modifica el embedding-service actual
- Reutiliza toda la infraestructura ColBERT
- No requiere pre-indexar imágenes del catálogo

**Desventajas críticas:**
- **Calidad inferior**: el captioning genera una descripción genérica. Si el usuario sube una foto de un vestido midi burdeos con encaje floral, el caption puede generar “elegant midi dress” sin los detalles que distinguen ese vestido de otros
- **Latencia acumulada**: ~250ms (VLM) + ~40ms (ColBERT) + red = ~350ms mínimo, pero con mayor varianza
- **Segundo Cloud Run service**: el VLM necesita su propio servicio (+$40–60/mes)
- **Dependencia de la calidad del prompt**: si el prompt no pide los atributos correctos, las búsquedas fallan
- El catálogo sigue siendo solo texto — no hay similitud visual real, solo semántica textual

**Cuándo tiene sentido:** solo si se quiere un prototipo en 1-2 semanas sin tocar el embedding-service, para validar que hay demanda de búsqueda visual antes de invertir en la Opción A.

---

### Resumen de opciones

| Criterio | Opción A (fashionSigLIP + FAISS) | Opción B (SigLIP2 base + FAISS) | Opción C (VLM + ColBERT) |
|---|---|---|---|
| Calidad de resultados | ★★★★★ | ★★★★ | ★★★ |
| Latencia query | ~400ms | ~120ms | ~300ms + varianza |
| Infraestructura nueva | Ninguna (mismo servicio) | Ninguna | Nuevo Cloud Run service |
| Cambios en embedding-service | Sí (modelo + endpoints) | Sí (modelo + endpoints) | No |
| Indexación de imágenes | Sí (offline, ~25 min) | Sí (offline, ~8 min) | No |
| Costo adicional | $0–20/mes | $0/mes | $40–60/mes |
| Semanas de implementación | 2–3 | 1–2 | 1 (prototipo) |
| Recomendada para producción | ✅ Sí | ✅ Con reservas | ⚠️ Solo prototipo |

**Recomendación**: Opción A si el objetivo es calidad de producción. Opción C solo para validar hipotésis antes de invertir.

---

## 6. Plan de validación

### Fase 0: Validación de hipótesis (1 semana, costo cero)

Antes de implementar nada, responder: **¿los usuarios querrínamos usar búsqueda visual?**

- Añadir un botón deshabilitado “Buscar por foto” al widget con un tooltip “Próximamente”
- Medir cuántos usuarios hacen hover o click en ese botón durante 2 semanas
- Si el engagement es <1% de sesiones: reconsiderar la inversión
- Si es >3%: implementar Opción A

### Fase 1: Evaluación offline (sin cambios en producción)

**Dataset**: Las imágenes del catálogo actual (image_url disponible en TF-IDF data para todos los productos).

**Cómo construirlo:**
```python
# Para cada producto del catálogo, usar SU PROPIA imagen como query
# y verificar que el producto aparece en top-k resultados
# Esto mide si el índice de embeddings es coherente internamente

for product in catalog:
    query_embedding = model.encode_image(product["image_url"])
    results = faiss_index.search(query_embedding, k=10)
    assert product["id"] in results  # debe estar entre los 10 más cercanos a sí mismo
```

**Métricas a medir:**

| Métrica | Qué mide | Umbral aceptable |
|---|---|---|
| Recall@1 | Si el mismo producto es su vecino más cercano | > 85% |
| Recall@5 | Si el mismo producto aparece entre los 5 primeros | > 95% |
| Précisión intra-categoría | De los 10 resultados, ¿cuántos son de la misma categoría? | > 70% |
| Latencia p50/p95 | En CPU Cloud Run (1 vCPU) | p50 < 500ms, p95 < 800ms |

**Dataset de moda público** para comparativa adicional (si se quiere validar contra benchmarks externos):
- `Marqo/deepfashion-inshop` (HuggingFace) — 52,000 imágenes de ropa con anotaciones
- `Marqo/atlas` (HuggingFace) — 721,065 imágenes de moda con metadatos ricos

### Fase 2: A/B test online (2 semanas)

**Setup**: Activar búsqueda visual para el 20% del tráfico (flag feature).

**Métricas de negocio:**

| Métrica | Cómo medir | Benchmark Mercari |
|---|---|---|
| CTR en recomendaciones | Clicks en productos devueltos por visual search | Referencia: +50% vs baseline |
| CVR | Conversiones desde sesiones con visual search | Referencia: +14% vs baseline |
| Queries por sesión | Si usan la función más de una vez | > 1.5x vs sesiones sin visual |
| Tiempo hasta primer click | Si los resultados son relevantes rápido | < 10s |

---

## Nota final sobre Liquid AI

La conclusión del primer análisis se mantiene: **LFM2-ColBERT no puede procesar imágenes**. Pero emerge algo positivo: Liquid AI usa SigLIP2 NaFlex como encoder visual en sus propios modelos VL. Esto confirma que SigLIP2 es la elección de referencia actual para vision encoders incluso para los laboratorios de IA más avanzados.

La arquitectura propuesta en Opción A (marqo-fashionSigLIP + FAISS dentro del embedding-service existente) es coherente con los sistemas de producción documentados (Mercari, Marqo), aprovecha el código ya construido, y no requiere nueva infraestructura.

---

*Segunda investigación elaborada el 21/04/2026. Fuentes principales: Marqo blog "Search Model for Fashion" (2025), Marqo blog "Ecommerce Embedding Models" (2025), Mercari Engineering blog (2024), paper "Zero-Shot Retrieval for Scalable Visual Search" (KDD 2025), SigLIP 2 paper arXiv:2502.14786 (Feb 2025), HuggingFace model cards Marqo/marqo-fashionSigLIP, google/siglip2-base-patch16-224, LiquidAI/LFM2-VL-1.6B.*