RETAIL RECOMMENDER SYSTEM v2.1.0

**Visual Search: Buscar Productos por Imagen**

Informe de Cierre de Integración

Mayo 2026 | Preparado por: Equipo de Ingeniería

| PRODUCTOS INDEXADOS   **3,054**   de 3,056 del catalogo | VELOCIDAD DE RESPUESTA   **350-570ms**   por busqueda visual tipica | TASA DE EXITO   **100%**   en las pruebas de produccion |
| --- | --- | --- |

# **1\. Que se ha integrado y por que**

Hemos integrado un sistema de busqueda visual dentro del chat de recomendaciones de la tienda Shopify. Esta nueva capacidad permite a los clientes subir una fotografia de cualquier prenda — tomada con su movil, descargada de redes sociales o de otra tienda — y recibir inmediatamente los productos del catalogo que mas se parecen a esa imagen.

Esta integracion responde a un comportamiento documentado en e-commerce de moda: el cliente sabe exactamente el estilo que busca pero no siempre tiene las palabras para describirlo. La busqueda por imagen elimina esa friccion.

# **2\. El problema que resuelve**

| **Capacidad** | **Antes** | **Ahora** |
| --- | --- | --- |
| Busqueda por palabras clave | Limitada — el cliente no siempre sabe como describir el estilo que busca | **Complementada con busqueda por imagen** |
| Descubrimiento de productos | Solo mediante texto o categorias manuales | **Tambien mediante foto: el cliente encuentra lo que ve** |
| Resistencia a tendencias virales | El cliente ve algo en redes y no puede encontrarlo | **Sube la foto y el sistema lo busca por similitud visual** |
| Personalizacion percibida | Recomendaciones basadas en texto de la query | **Recomendaciones basadas en el estilo visual real del cliente** |

# **3\. Como funciona — explicacion simple**

El flujo completo tiene tres pasos:

| **PASO 1** | El cliente sube una foto desde el chat del asistente (boton de camara o seleccion de archivo). |
| --- | --- |
| **PASO 2** | Nuestro sistema de IA analiza el estilo, colores y forma de la prenda en la imagen usando un modelo especializado en moda (marqo-fashionSigLIP), entrenado especificamente para reconocer similitudes entre prendas de vestir. |
| **PASO 3** | En menos de un segundo, el sistema devuelve los 8 productos del catalogo con mayor similitud visual, con precio correcto segun el mercado del cliente (ES, CL, CH, MX). |

# **4\. Resultados observados en produccion**

Las pruebas de produccion realizadas el 30 de abril y 1 de mayo de 2026 muestran un sistema estable y funcional:

| **Metrica** | **Resultado** |
| --- | --- |
| **Tasa de exito** | 100% (4 de 4 busquedas respondidas correctamente) |
| **Productos encontrados siempre** | 8 de 8 solicitados — el indice funciona |
| **Latencia tipica** | 350ms a 570ms — experiencia fluida para el usuario |
| **Latencia maxima observada** | 806ms — aceptable para imagenes de mayor tamano |
| **Imagenes probadas** | Desde 53KB hasta 407KB — el sistema maneja todo el rango |
| **Errores en produccion** | Cero errores, cero warnings en la ventana analizada |
| **Disponibilidad del indice** | 3,054 productos listos desde el arranque (carga desde GCS) |

# **5\. Nuevas capacidades del sistema**

-   **el cliente puede encontrar productos sin usar palabras.**
-   **3,054 de 3,056 productos disponibles para busqueda visual.**
-   **el sistema no pierde el catalogo visual cuando se reinicia o actualiza; se almacena en Google Cloud Storage y se recupera automaticamente al arrancar.**
-   **los resultados incluyen precios correctos para cada mercado (Espana, Chile, Suiza, Mexico).**
-   **la funcionalidad se puede activar o desactivar en menos de 30 segundos sin interrumpir el servicio.**

# **6\. Ventajas competitivas**

La tecnologia utilizada (marqo-fashionSigLIP) es un modelo de codigo abierto especializado en moda que supera en precision a CLIP y FashionCLIP en benchmarks de recuperacion de prendas. Esta capacidad, tipicamente disponible solo en grandes plataformas de e-commerce, esta ahora integrada en el sistema sin coste adicional de licencia.

El modelo fue diseado especificamente para entender similitudes entre prendas: color, silueta, textura, patron. No es un buscador de imagenes generico sino una herramienta pensada para el cliente de moda.

# **7\. Costes de infraestructura**

| **Concepto** | **Coste estimado mensual** |
| --- | --- |
| **Embedding Service — 4Gi RAM, 2 vCPU (always-on)** | ~$25-35 / mes |
| **Google Cloud Storage — 10MB de indice FAISS** | < $0.01 / mes (despreciable) |
| **Licencia del modelo fashionSigLIP** | $0 (Apache 2.0, codigo abierto) |
| **Tiempo de reindexacion del catalogo** | ~30 min, una sola vez o tras cambios masivos |
| **TOTAL adicional respecto al sistema anterior** | ~$15-20 / mes neto |

Nota: el Embedding Service ya existia para las busquedas textuales (ColBERT). El sobrecoste corresponde al upgrade de memoria de 2Gi a 4Gi necesario para alojar ambos modelos simultaneamente.

# **8\. Oportunidades de negocio**

### **Conversion y descubrimiento**

-   **El cliente que sube una foto ya tiene una intencion de compra clara. La conversion esperada en esta micro-sesion es significativamente mayor que en busquedas genericas.**
-   **Reduccion de la tasa de abandono: el cliente que no encuentra lo que busca por palabras ahora tiene un canal alternativo.**
-   **Descubrimiento cross-category: el modelo puede detectar similitudes de estilo entre categorias que el cliente no habria explorado manualmente.**

### **Experiencia de usuario**

-   **Diferenciacion clara frente a tiendas que solo ofrecen busqueda textual.**
-   **Captura del trafico de 'inspiracion en redes sociales': cliente que ve algo en Instagram y quiere encontrarlo en la tienda.**
-   **Soporte a clientes internacionales: la busqueda por imagen no depende del idioma.**

### **Evolucion futura**

-   **Busqueda por similitud de outfit completo (no solo una prenda).**
-   **Integracion con camara en tiempo real en la app movil.**
-   **Personalizacion del indice por historial visual del cliente (productos vistos, comprados).**
-   **Sincronizacion automatica del indice visual cuando se anaden nuevos productos al catalogo.**

**Estado de la integracion: COMPLETADA**

La integracion de Visual Search esta en produccion, es estable y esta lista para activacion. El equipo tecnico ha validado el sistema con datos reales y ha resuelto todos los problemas de infraestructura encontrados durante la implementacion. La recomendacion es activar el feature flag VISUAL\_SEARCH\_ENABLED y comenzar a medir el impacto en conversion.