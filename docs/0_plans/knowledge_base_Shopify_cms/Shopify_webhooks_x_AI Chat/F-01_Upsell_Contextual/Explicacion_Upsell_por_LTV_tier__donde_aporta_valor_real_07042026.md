
Explicación: Upsell por LTV tier — dónde aporta valor real
fecha: 07.04.2026
Ahora la segunda parte de tu pregunta. Con ejemplos concretos de la tienda AI-Shoppings:
El LTV tier es la clasificación del cliente según su historial de compras: new (primera vez), returning (2-5 compras), loyal (6-15), vip (16+ o gasto alto). F-04 ya inyecta este dato en mcp_context.customer_profile.
El problema actual es que aunque Claude conoce tanto el producto que ve el usuario (current_product_context) como su historial de compras (customer_profile), el prompt de upsell no los cruza explícitamente. Los sugiere por separado.
Tres casos donde el cruce aporta valor concreto:

Caso 1 — Cliente VIP viendo un vestido de €79
Sin la mejora, Claude sugiere:

"Este vestido combina muy bien con accesorios de la colección Fiesta."

Con la mejora, Claude sabe que es cliente VIP (ha gastado €1.200+) y cruza esa información:

"Como clienta habitual, quizás te interese el vestido Emma en versión largo (€129) de la misma colección — tiene el mismo corte champagne que tanto te ha gustado en pedidos anteriores."

El VIP ya conoce la marca, confía en ella, y tiene capacidad de gasto demostrada. El upsell correcto es hacia un producto de mayor valor, no el mismo rango de precio.

Caso 2 — Cliente NEW viendo un vestido de €79
Sin la mejora, Claude puede sugerir complementos de €50-80.
Con la mejora, Claude sabe que es primera compra y el objetivo es cerrar esa primera venta:

"Para completar el look puedes añadir el cinturón fino dorado (€19) — combina perfecto y el envío sale gratis al superar €80."

La estrategia es diferente: bajo riesgo percibido, incentivo concreto (envío gratis), precio pequeño de add-on. El VIP no necesita este empuje; el cliente nuevo sí.

Caso 3 — Cliente LOYAL en colección Fiesta
Sin la mejora, Claude sugiere cualquier producto de la colección.
Con la mejora, Claude sabe que el cliente tiene 8 compras previas todas de la categoría "Vestidos de Noche" y nunca ha comprado accesorios:

"Veo que has renovado tu armario de noche varias veces — ¿has probado los zapatos de la colección Fiesta? Completan el look sin buscar en otra tienda."

Es una sugerencia de cross-sell a una categoría adyacente que el cliente nunca ha explorado, usando su historial para hacer la sugerencia creíble.

En resumen: La mejora vale más cuando el ticket potencial y el riesgo de rechazo son diferentes por tier. Un VIP acepta sugerencias de gama alta; un NEW necesita reducción de fricción; un LOYAL es candidato a cross-sell en categorías nuevas. Sin el cruce, Claude da el mismo tipo de sugerencia a los tres. Con él, cada respuesta está calibrada al comportamiento real del cliente.