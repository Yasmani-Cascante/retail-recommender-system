| **Retail Recommender System v2.1.0**   **Shopify x AI Chat**   Estrategia de Producto con Impacto en Ingresos   Analisis de capacidades, casos de uso con ROI directo y roadmap de implementacionDocumento Version Fecha Clasificacion PM-2026-002 1.0 Marzo 2026 Interno |
| --- |

# **1\. Resumen Ejecutivo**

El sistema tiene desplegadas las piezas tecnicas mas costosas de construir: integracion Shopify activa (API GraphQL + Webhooks), pipeline MCP con Claude AI, widget conversacional funcional y Knowledge Base sincronizada. Lo que falta no es infraestructura — es activar los datos correctos en el momento correcto para generar ventas.

Este documento define 7 funcionalidades concretas que transforman el chat de una herramienta de soporte en una maquina de conversion. Cada una esta anclada en capacidades reales de la Shopify API, estimaciones de ROI documentadas por la industria, y una ruta de implementacion especifica sobre el stack existente.

| **Metrica clave** | **Benchmark industria** | **Objetivo ano 1** | **Mecanismo principal** |
| --- | --- | --- | --- |
| Tasa de conversion (chat-asistida) | 2-4x superior al promedio | +1.5 pp sobre linea base | F-01 + F-02 |
| Ticket medio (AOV) | Chat aumenta AOV 15-25% | +10-18 EUR por pedido | F-01 + F-04 |
| Recuperacion de carrito | Email 5-8% / Chat 10-20% | +8-12% de carritos | F-03 |
| Reduccion de devoluciones | 20-35% con guia de tallas correcta | \-15% en productos asistidos | F-02 |
| Retecnion y recompra | +20% con soporte post-compra | +2 visitas recurrentes/ano | F-04 + F-06 |

# **2\. Capacidades Reales con Shopify**

El sistema ya tiene autenticacion con la Shopify GraphQL API y manejo de webhooks implementado. La tabla siguiente mapea los recursos disponibles contra lo que podemos consumir sin desarrollo adicional de autenticacion.

## **2.1 Recursos API disponibles**

| **Recurso API** | **Datos clave disponibles** | **Estado actual** |
| --- | --- | --- |
| Products | precio, variantes, stock, imagenes, metafields, colecciones | Parcialmente activo (KB sync) |
| Customers | historial pedidos, LTV, tags segmento, email | NO integrado |
| Orders | lineas pedido, estado, valor, fecha, fulfillment | NO integrado |
| Cart (Storefront API) | productos en carrito, valor, abandono | NO integrado |
| Collections | agrupaciones de productos, reglas | NO integrado |
| Product Metafields | tabla de medidas, materiales, cuidado | Activo (KB sync) |
| Pages / KB | contenido de politicas y FAQ | Activo (Knowledge Base) |

## **2.2 Webhooks disponibles**

| **Webhook topic** | **Cuando se dispara** | **Dato util para el chat** | **Estado** |
| --- | --- | --- | --- |
| translations/update | Al editar traduccion | Re-sync KB multilingue | ACTIVO |
| pages/create-update-delete | Al modificar pagina | Re-sync KB | PARCIAL (polling) |
| carts/create + carts/update | Al crear o modificar carrito | Carrito actual + abandono | NO registrado |
| orders/create + orders/paid | Al completar compra | Perfil post-compra, cross-sell | NO registrado |
| orders/fulfilled | Al enviar pedido | Tracking + upsell accesorios | NO registrado |
| customers/create + update | Al registrar cliente | Enriquecer perfil MCP | NO registrado |
| products/update | Al cambiar precio o stock | Urgencia stock bajo | NO registrado |

| **Insight clave**   Los 5 webhooks no registrados son los que habilitan las funcionalidades de mayor ROI. Registrarlos en Shopify y anadir sus handlers es trabajo de 1-2 dias de backend. El patron ya esta implementado en ShopifyWebhookHandler — es replicacion, no diseno. |
| --- |

# **3\. Funcionalidades con ROI Directo**

Las siguientes 7 funcionalidades estan ordenadas por ROI estimado ajustado por esfuerzo. Cada una esta anclada en datos reales de la Shopify API y aprovecha infraestructura ya existente.

| **F-01. Upsell y Cross-sell Contextual por Pagina de Producto**   _El chat conoce que producto mira el usuario. Usa eso para vender mas._ |
| --- |

| **Prioridad**   **P0 — Inmediata** | **Esfuerzo**   1 sprint (5-7 dias) | **ROI estimado**   **+E300-900/dia** |
| --- | --- | --- |

**Como funciona :** widget\_context.product\_id ya llega al backend en cada request. El chat llama a la Shopify Collections API para obtener productos de la misma coleccion y al HybridRecommender para calcular similitud. Claude genera un pitch conversacional: 'Este vestido queda muy bien con el cinturon de cuero marron que tenemos en oferta.'

**Datos :** product\_id (ya en widget\_context), Shopify Collections API, HybridRecommender score TF-IDF, Inventory API para confirmar stock.

**ROI :** Upsell conversion: 10-30% de visitantes de pagina de producto. Con 500 visitas/dia y ticket E60: +E300-900/dia de revenue incremental. AOV sube 15-25% en conversaciones con cross-sell activo.

**Implementacion :** 1 sprint. Anadir endpoint GET /v1/shopify/product/{id}/context. Inyectar en prompt de MCPPersonalisationEngine. product\_id ya esta en widget\_context — sin cambios en frontend.

| **F-02. Asistente de Talla Inteligente con Historial de Cliente**   _El asistente que reduce devoluciones y sabe que tallas ya compro el usuario._ |
| --- |

| **Prioridad**   **P0 — Inmediata** | **Esfuerzo**   1 sprint (5-7 dias) | **ROI estimado**   **\-E1.500-2.800/mes devoluciones** |
| --- | --- | --- |

**Como funciona :** El sub\_intent product\_sizing ya existe en KB. Se enriquece con: (1) Metafields del producto actual: tabla de medidas especifica. (2) Si hay customer\_id: historial de tallas compradas via Shopify Customers API. Respuesta: 'Segun tu historial compraste M en esta marca. Esta chaqueta corre una talla, te recomendamos L.'

**Datos :** KB existente (guia general), product metafields (tabla especifica), Shopify Customers API: orders -> lineItems -> variant.selectedOptions, customer\_id via Shopify Liquid {{ customer.id }}.

**ROI :** Reduccion de devoluciones por talla incorrecta: 20-35% (benchmarks Zalando/ASOS). Con 100 ordenes/mes y ticket E65: ahorro E1.500-2.800/mes en logistica inversa.

**Implementacion :** 1 sprint. Enriquecer handler de product\_sizing con fetch de metafields + consulta lazy a Customers API si hay customer\_id. Anadir customer\_id en widget\_context desde Shopify Liquid.

| **F-03. Recuperacion Proactiva de Carrito Abandonado**   _El chat que llega antes que el email. Con el contexto real del carrito._ |
| --- |

| **Prioridad**   **P1 — Sprint 1-2** | **Esfuerzo**   2 sprints (12-16 dias) | **ROI estimado**   **+E400-800/dia recuperado** |
| --- | --- | --- |

**Como funciona :** Webhook carts/update detecta carrito con productos + 25 min sin actividad. Si la sesion del widget esta activa, envia mensaje proactivo: 'Vi que dejaste el vestido floral en tu carrito — hay algo en lo que pueda ayudarte para decidirte?' Si el usuario se fue, encola el mensaje para la proxima visita.

**Datos :** Webhook carts/update: cart.token, cart.line\_items, customer.email. Redis TTL 25 min con cart\_token como key. Shopify Products API: datos actualizados. MCPConversationContext: historial si existe.

**ROI :** Tasa de recuperacion via chat proactivo: 10-20% (vs email: 3-5%). Con 80 carritos abandonados/dia y ticket E50: +E400-800/dia de revenue recuperado. La tasa de abandono en fashion es 70-85%.

**Implementacion :** 2 sprints. Registrar webhook carts/update. CartWebhookHandler (mismo patron ShopifyWebhookHandler). Canal push al widget (SSE/WebSocket). Cola de mensajes para proxima visita.

| **F-04. Personalizacion por Historial de Cliente**   _El chat que te conoce. No por cookies — por tus compras reales._ |
| --- |

| **Prioridad**   **P1 — Sprint 1-2** | **Esfuerzo**   2 sprints (12-16 dias) | **ROI estimado**   **+20-30% conversion identificados** |
| --- | --- | --- |

**Como funciona :** Al inicio de sesion en Shopify, widget\_context recibe customer\_id. El backend hace fetch lazy a Customers API en la primera interaccion: ultimas 5 compras, categorias preferidas, LTV, tags. Este perfil se inyecta en MCPConversationContext. Claude adapta tono segun si el usuario es nuevo, recurrente o VIP (LTV > E500).

**Datos :** customer.orders (ultimas 5), customer.total\_spent (LTV), customer.tags (segmentos Shopify), customer.default\_address (mercado/idioma).

**ROI :** Personalizacion aumenta conversion 20-30% vs anonimo (McKinsey). Clientes recurrentes tienen AOV 67% mayor. Identificar VIP aumenta retencion 15-20%. Revenue incremental: E150-300/mes por cada 100 clientes identificados.

**Implementacion :** 2 sprints. Anadir CustomerProfileService con fetch lazy. Enriquecer MCPConversationContext con CustomerProfile. Inyectar customer\_id desde Shopify Liquid en widget\_context.

| **F-05. Alertas de Stock Bajo y Urgencia Contextual**   _FOMO legitimo: el chat dice la verdad sobre las ultimas unidades._ |
| --- |

| **Prioridad**   **P1 — Sprint 1-2** | **Esfuerzo**   1 sprint (5-7 dias) | **ROI estimado**   **+E300-500/dia conversion** |
| --- | --- | --- |

**Como funciona :** Webhook products/update detecta cuando el stock de una variante baja de 5 unidades. Se cachea en Redis con TTL 1h. Cuando el usuario interactua con ese producto (product\_id en widget\_context coincide), el chat incluye el stock real: 'Solo quedan 3 unidades de la talla M — suele agotarse esta temporada.'

**Datos :** Webhook products/update: variant.inventory\_quantity. Redis cache: stock\_alert:{variant\_id} TTL 3600s. widget\_context.product\_id para matching. Shopify Inventory API para verificacion en tiempo real.

**ROI :** FOMO aumenta conversion 15-25% en productos en alerta (Baymard Institute). Con 50 usuarios/dia en productos con stock bajo y conversion +20%: +E300-500/dia de revenue incremental capturado.

**Implementacion :** 1 sprint. Registrar webhook products/update. Handler en ShopifyWebhookHandler (patron ya implementado). Inyeccion de stock\_alert en contexto cuando product\_id coincide.

| **F-06. Soporte Post-Compra Automatizado y Cross-sell Temporal**   _El chat que aparece despues de la venta. Cuando el cliente esta mas receptivo._ |
| --- |

| **Prioridad**   **P2 — Sprint 3-4** | **Esfuerzo**   2 sprints (12-16 dias) | **ROI estimado**   **+E2.400-4.800/mes combinado** |
| --- | --- | --- |

**Como funciona :** Webhook orders/create: Claude genera mensaje personalizado con productos comprados, fecha estimada de entrega y cross-sell de complementarios. Webhook orders/fulfilled: notificacion con tracking + upsell de accesorios. Reduce tickets WISMO y captura revenue en el momento de maxima satisfaccion del cliente.

**Datos :** orders/create: order.line\_items, order.total\_price. orders/fulfilled: fulfillment.tracking\_url, fulfillment.estimated\_delivery. HybridRecommender: productos complementarios a lo comprado.

**ROI :** Reduccion tickets de soporte WISMO: 40-60%. Con 50 ordenes/dia y coste E8/ticket: ahorro E160-320/dia. Cross-sell post-compra: 8-12% conversion. +E2.400-4.800/mes combinado.

**Implementacion :** 2 sprints. Registrar webhooks orders/create y orders/fulfilled. OrderWebhookHandler. Mecanismo push al widget si sesion activa o cola para proxima visita.

| **F-07. Memoria Conversacional Multi-Turno**   _El chat que recuerda lo que dijiste hace 3 mensajes. Y lo usa._ |
| --- |

| **Prioridad**   **P0 — Inmediata** | **Esfuerzo**   3-5 dias | **ROI estimado**   **CSAT +15 pts, retencion +10%** |
| --- | --- | --- |

**Como funciona :** Actualmente la sesion Redis persiste el historial de turns pero el prompt de Claude NO incluye el historial previo. Incluir los ultimos 3-5 turns permite: comprender referencias cruzadas ('el segundo que me mostraste'), recordar preferencias ('no me gustan los sinteticos'), construir sobre la conversacion sin repetir contexto.

**Datos :** MCPConversationContext.turns (ya almacenados en Redis). recommendation\_ids de turns anteriores (ya implementado). user\_query de turns anteriores. Ninguna nueva llamada a Shopify — infraestructura 100% existente.

**ROI :** CSAT +15 puntos. Reduccion de abandono mid-conversation por frustracion de repetir contexto. Sesiones mas largas = mas oportunidades de recomendacion. Costo extra: E0.0005 por conversacion con Haiku.

**Implementacion :** 1 sprint (3-5 dias). SOLO incluir los ultimos N turns en el prompt de generate\_personalized\_response(). La infraestructura ya existe. Es el prerequisito tecnico para todas las funcionalidades avanzadas.

# **4\. Integracion de Webhooks — Diseno Tecnico**

El sistema tiene un patron maduro: idempotencia via Redis SET NX, ejecucion asincrona en BackgroundTask, manejo de errores con metricas Prometheus, distributed locking. Extender este patron a los nuevos webhooks es trabajo de replicacion.

## **4.1 Flujo webhook → accion en chat**

| **Evento Shopify** | **Handler a crear** | **Accion en Redis** | **Efecto en chat** |
| --- | --- | --- | --- |
| carts/update (inact. 25 min) | CartWebhookHandler | SET cart\_pending:{token} TTL=3600s | Mensaje proactivo o cola proxima visita |
| orders/create | OrderWebhookHandler | SET order\_context:{customer\_id} | Bienvenida personalizada + cross-sell |
| orders/fulfilled | OrderWebhookHandler | SET tracking:{order\_id} | Notificacion envio + upsell accesorios |
| products/update (stock < 5) | ProductWebhookHandler | SET stock\_alert:{variant\_id} TTL=3600s | Urgencia contextual en pagina de producto |
| customers/update | CustomerWebhookHandler | INVALIDATE customer\_profile:{id} | Re-fetch perfil en proxima sesion |

## **4.2 Timing inteligente — cuando activar el chat**

| **Situacion** | **Timing optimo** | **Por que** | **Senal tecnica** |
| --- | --- | --- | --- |
| Carrito abandonado — usuario en tienda | Inmediato (< 2 min tras inactividad) | Usuario en estado de decision activa | Sesion WebSocket activa + carrito sin checkout |
| Carrito abandonado — usuario se fue | Primera visita siguiente | Evitar competir con email automation | Nuevo pageview con cart\_token en Redis |
| Post-compra | En pagina de confirmacion | Pico de satisfaccion, maxima receptividad | orders/create + usuario en /checkout/thank\_you |
| Stock bajo en producto visto | Solo si el usuario pregunta por ese producto | FOMO legitimo, no intrusivo | product\_id en widget\_context + stock\_alert en Redis |
| Fulfillment enviado | 24h despues del envio | Anticipar pregunta WISMO | orders/fulfilled + delay via Redis sorted set |

## **4.3 Cambios en frontend (widget)**

| **Cambio** | **Archivo** | **Complejidad** | **Para que funcionalidad** |
| --- | --- | --- | --- |
| Anadir customer\_id en widget\_context | api.ts + Shopify theme.liquid | Baja — 10 lineas | F-02, F-04, F-06 |
| Anadir cart\_token en widget\_context | api.ts + Shopify theme.liquid | Baja — 10 lineas | F-03 |
| Canal de notificaciones push (SSE) | api.ts + nuevo endpoint backend | Media — 2 dias | F-03, F-06 (mensajes proactivos) |
| Mostrar kb\_document como expand | MessageList.tsx | Baja — 1 dia | Mejora UX Knowledge Base (ya disponible) |

# **5\. Priorizacion — Matriz de Decision**

La matriz evalua: impacto en ROI (revenue directo + coste evitado), esfuerzo de implementacion sobre el stack existente, y alineacion con la arquitectura actual.

| **ID** | **Funcionalidad** | **ROI (1-5)** | **Esfuerzo (inv.)** | **Alineacion (1-5)** | **Score** | **Prioridad** |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | Upsell/Cross-sell contextual | 5 | 5 | 5 | 5.0 | P0 — Inmediata |
| F-02 | Asistente de talla inteligente | 4 | 5 | 5 | 4.7 | P0 — Inmediata |
| F-07 | Memoria conversacional multi-turno | 3 | 5 | 5 | 4.3 | P0 — Inmediata |
| F-05 | Alertas de stock bajo | 4 | 4 | 4 | 4.0 | P1 — Sprint 1-2 |
| F-04 | Personalizacion por historial | 5 | 3 | 4 | 4.0 | P1 — Sprint 1-2 |
| F-03 | Recuperacion de carrito abandonado | 5 | 2 | 3 | 3.3 | P1/P2 |
| F-06 | Soporte post-compra + cross-sell | 4 | 2 | 3 | 3.0 | P2 — Sprint 3-4 |

*Esfuerzo (inv.) = score inverso: 5 = muy facil, 1 = muy complejo. Score = (ROI x 0.4) + (Esfuerzo x 0.35) + (Alineacion x 0.25).*

# **6\. Top 3 Prioridades Recomendadas**

| **Prioridad #1 — F-01: Upsell Contextual**   product\_id ya llega al backend. La Shopify Collections API ya esta autenticada. El HybridRecommender ya calcula similitud. Solo falta conectar los puntos: 1 endpoint nuevo, inyeccion en el prompt de Claude. Tiempo estimado: 5 dias. ROI inmediato y medible desde el primer dia de activacion. |
| --- |

| **Prioridad #2 — F-02: Asistente de Talla + Historial**   El sub\_intent product\_sizing ya existe y funciona. Enriquecerlo con metafields del producto especifico y tallas compradas anteriormente tiene impacto doble: aumenta conversion y reduce devoluciones (E1.500-2.800/mes de coste evitado). Mayor ratio impacto/esfuerzo del catalogo. |
| --- |

| **Prioridad #3 — F-07: Memoria Conversacional Multi-Turno**   Cero infraestructura nueva. Los turns ya estan en Redis y se cargan en MCPConversationContext. Solo hay que incluirlos en el prompt de generate\_personalized\_response(). Costo extra: E0.0005/conversacion. El chat deja de parecer un chatbot sin memoria y pasa a ser un asistente real. Prerequisito tecnico para las funcionalidades avanzadas. |
| --- |

# **7\. Roadmap de Implementacion**

| **Sprint** | **Duracion** | **Funcionalidades** | **Hito medible** |
| --- | --- | --- | --- |
| Sprint 0 | 3 dias | Preparacion: anadir customer\_id y cart\_token en widget\_context. Registrar 5 webhooks en Shopify Admin. Tests de idempotencia. | widget\_context enriquecido en produccion. Webhooks confirmados en dashboard Shopify. |
| Sprint 1A | 7 dias | F-01: Upsell Contextual. Endpoint GET /v1/shopify/product/{id}/context. Inyeccion en prompt Claude. | Primera recomendacion cross-sell en produccion. Medir CTR en ProductCard. |
| Sprint 1B | 7 dias | F-02: Asistente de Talla (5 dias). F-07: Memoria multi-turno (3 dias, en paralelo). | Respuestas de talla incluyen medidas especificas. Sesion de 3 turns con coherencia verificada. |
| Sprint 2A | 7 dias | F-05: Alertas de stock bajo. Webhook products/update + Redis cache + inyeccion contextual. | Mensaje de urgencia cuando stock < 5. Medir conversion diferencial con/sin alerta. |
| Sprint 2B | 10 dias | F-04: Personalizacion por historial. CustomerProfileService + MCPConversationContext enriquecido. | Respuestas personalizadas para clientes identificados. A/B test anonimo vs identificado. |
| Sprint 3A | 12 dias | F-03: Recuperacion de carrito abandonado. CartWebhookHandler + canal push (SSE). | Primer carrito recuperado via chat proactivo. Tasa de recuperacion vs email. |
| Sprint 3B | 12 dias | F-06: Post-compra automatizado. OrderWebhookHandler + prompts Claude para contexto post-compra. | Mensaje de confirmacion personalizado. Tickets WISMO antes/despues. |
| Sprint 4+ | Ongoing | Dashboard de metricas de conversion asistida. A/B testing por segmento. Optimizacion de prompts por resultado. | ROI cuantificado por funcionalidad. Decisiones de siguiente iteracion basadas en datos. |

# **8\. Resumen de ROI Potencial**

Estimaciones para tienda de moda mediana: 500 visitas/dia a paginas de producto, ticket medio E60, 80 carritos abandonados/dia. Rangos conservador (limite inferior) a optimista (limite superior).

| **Funcionalidad** | **Tipo de impacto** | **Rango mensual estimado** | **Tiempo al primer valor** |
| --- | --- | --- | --- |
| F-01 Upsell contextual | Revenue incremental | +E9.000-27.000/mes | Dia 1 post-deploy |
| F-02 Asistente de talla | Coste evitado (devoluciones) | E1.500-2.800/mes ahorrado | Dia 1 post-deploy |
| F-03 Recuperacion carrito | Revenue recuperado | +E12.000-24.000/mes | 2-3 sprints |
| F-04 Perfil de cliente | Incremento conversion | +E4.500-9.000/mes | 2 sprints |
| F-05 Alertas de stock | Revenue capturado (FOMO) | +E9.000-15.000/mes | 1-2 sprints |
| F-06 Post-compra | Revenue incremental + ahorro soporte | +E2.400-4.800/mes | 3 sprints |
| F-07 Memoria multi-turno | Mejora retencion/CSAT (indirecto) | No directamente cuantificable | 3-5 dias |
| **TOTAL (conservador — optimista)** | **Combinado** | **E38.400-82.600/mes** | **Full roadmap: ~3 meses** |

*Los rangos incluyen solo impacto directo. CSAT, reduccion de CAC por boca-a-boca y LTV incremental no estan incluidos pero son impactos reales de segundo orden.*

# **9\. Conclusion — El Sistema Ya Esta Listo**

El trabajo de infraestructura esta hecho. TF-IDF Recommender, MCPPersonalisationEngine, Claude Haiku, Redis, PostgreSQL, Shopify GraphQL, Intent Detection, Knowledge Base, widget conversacional — todo en produccion y funcionando. Lo que falta es activar los datos de negocio de Shopify que ya estan disponibles pero que aun no fluyen hacia el chat.

El catalogo de 7 funcionalidades no es una lista de deseos — es una lista de conexiones pendientes entre sistemas que ya existen. La mas facil (F-01) requiere 5 dias y genera valor desde el primer dia. La mas compleja (F-03) requiere 2 sprints pero tiene el mayor ROI mensual.

| **Proximo paso recomendado**   Sprint 0 (3 dias): anadir customer\_id y cart\_token en widget\_context (frontend + Shopify Liquid) y registrar los 5 webhooks en Shopify Admin. Sin estos dos cambios, el 80% de las funcionalidades de este documento no pueden activarse. Es el desbloqueador de todo el roadmap y tiene costo tecnico minimo. |
| --- |

| **Estado actual** | **Estado objetivo (3 meses)** |
| --- | --- |
| **Chat que responde preguntas** | **Chat que genera ventas** |
| Recomendaciones basadas en texto | Recomendaciones basadas en historial real de compras |
| KB estatica por sub-intent | KB contextualizada con datos de producto y cliente |
| Conversacion sin memoria cross-turn | Asistente con memoria de sesion completa |
| Sin webhooks de transacciones | Reaccion automatica a carrito, pedido, envio y stock |
| Widget reactivo (espera al usuario) | Widget proactivo (llega en el momento correcto) |