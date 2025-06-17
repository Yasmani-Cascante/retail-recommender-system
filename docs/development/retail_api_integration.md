# Integración con Google Cloud Retail API

## Descripción General

Este documento describe la integración del Sistema de Recomendaciones para Retail con Google Cloud Retail API, incluyendo la configuración, los flujos de datos y el procesamiento de respuestas.

## Versión

**Última actualización:** 12 de abril de 2025  
**Versión de la API:** 0.5.0  
**Versión de Google Cloud Retail API:** v2

## Componentes Principales

### RetailAPIRecommender

Clase que implementa la interfaz con Google Cloud Retail API, proporcionando funcionalidades para:

- Importación de catálogos de productos
- Registro de eventos de usuario
- Obtención de recomendaciones personalizadas

La clase está implementada en `src/recommenders/retail_api.py` y utiliza los clientes oficiales de Google Cloud para interactuar con los servicios.

## Configuración

### Variables de Entorno

```
GOOGLE_PROJECT_NUMBER=178362262166
GOOGLE_LOCATION=global
GOOGLE_CATALOG=default_catalog
GOOGLE_SERVING_CONFIG=default_recommendation_config
GCS_BUCKET_NAME=retail-recommendations-449216_cloudbuild
USE_GCS_IMPORT=true
```

### Inicialización

```python
retail_recommender = RetailAPIRecommender(
    project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
    location=os.getenv("GOOGLE_LOCATION", "global"),
    catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
    serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
)
```

## Principales Funcionalidades

### 1. Importación de Catálogos

#### Métodos de Importación

- **Importación Directa**: Para catálogos pequeños (<50 productos)
- **Importación vía Google Cloud Storage**: Para catálogos grandes (≥50 productos)

#### Control de Importación

```python
use_gcs = os.getenv("USE_GCS_IMPORT", "False").lower() == "true"
```

### 2. Registro de Eventos de Usuario

#### Tipos de Eventos Soportados

- `detail-page-view`: Vista de página de detalle de producto
- `add-to-cart`: Adición de producto al carrito
- `purchase-complete`: Finalización de compra (requiere `purchaseTransaction`)
- `category-page-view`: Vista de página de categoría
- `home-page-view`: Vista de página de inicio
- `search`: Búsqueda realizada por el usuario

#### Ejemplo de Registro de Eventos

```python
await retail_recommender.record_user_event(
    user_id="user123",
    event_type="purchase-complete",
    product_id="product456",
    purchase_amount=99.99  # Importante para eventos de compra
)
```

#### Eventos de Compra

Para eventos de tipo `purchase-complete`, es **obligatorio** proporcionar información de transacción:

```python
if event_type == "purchase-complete":
    transaction_id = f"transaction_{int(time.time())}_{user_id[-5:]}"
    revenue = purchase_amount if purchase_amount is not None else 1.0
    
    user_event.purchase_transaction = retail_v2.PurchaseTransaction(
        id=transaction_id,
        revenue=revenue
    )
```

### 3. Obtención de Recomendaciones

#### Recomendaciones para Usuarios

```python
recommendations = await retail_recommender.get_recommendations(
    user_id="user123",
    n_recommendations=5
)
```

#### Recomendaciones para Productos

```python
recommendations = await retail_recommender.get_recommendations(
    user_id="anonymous",  # Se requiere un user_id aunque sea anónimo
    product_id="product456",
    n_recommendations=5
)
```

## Procesamiento de Respuestas

### Estructura de Respuesta

La respuesta de Google Cloud Retail API puede tener diferentes estructuras dependiendo del contexto y la versión de la API. El sistema está diseñado para manejar estas variaciones.

#### Método de Procesamiento

```python
def _process_predictions(self, response) -> List[Dict]:
    # Método flexible para extraer información de la respuesta
    # Soporta múltiples estructuras de datos
    # ...
```

### Formato de Recomendaciones

Cada recomendación procesada tiene el siguiente formato:

```json
{
  "id": "product123",
  "title": "Nombre del Producto",
  "description": "Descripción del producto",
  "price": 99.99,
  "category": "Categoría del Producto",
  "score": 0.85,
  "source": "retail_api"
}
```

## Estrategias de Fallback

Cuando no es posible obtener recomendaciones de Google Cloud Retail API, el sistema implementa estrategias de fallback:

1. **Recomendador TF-IDF**: Utiliza similitud de contenido para encontrar productos similares
2. **Productos Populares**: Selecciona productos populares generales
3. **Productos Diversos**: Selecciona productos de diferentes categorías

## Manejo de Errores

El sistema implementa un manejo robusto de errores para garantizar la continuidad del servicio:

1. **Logging Detallado**: Registro de información de diagnóstico para facilitar la solución de problemas
2. **Degradación Elegante**: Si una fuente de recomendaciones falla, el sistema intenta alternativas
3. **Validación de Parámetros**: Verificación de la validez de los parámetros antes de enviar solicitudes a la API

## Consideraciones de Rendimiento

1. **Caché**: Es recomendable implementar caché para resultados frecuentes
2. **Batch Processing**: Para catálogos grandes, utilizar procesamiento por lotes
3. **Monitoreo**: Monitorizar tiempos de respuesta y tasas de error para optimizar el rendimiento

## Solución de Problemas Comunes

### Error: Unknown field for PredictionResult

Este error puede ocurrir cuando la estructura de respuesta de la API no coincide con lo esperado. El sistema ahora implementa un enfoque más flexible para extraer datos de diferentes estructuras de respuesta.

### Error: Invalid value for product.availability

Asegúrate de que todos los productos tengan un valor válido para `availability`. Los valores permitidos son:
- `IN_STOCK`
- `OUT_OF_STOCK`
- `PREORDER`
- `BACKORDER`

### Error: Failed to register user event

Verifica que:
1. El tipo de evento sea válido
2. Para eventos `purchase-complete`, se incluya el campo `purchase_amount`
3. Los IDs de producto existan en el catálogo

## Ejemplos de Uso

### Importación de Catálogo y Obtención de Recomendaciones

```python
# Importar catálogo
import_result = await retail_recommender.import_catalog(products)

# Obtener recomendaciones para usuario
recommendations = await retail_recommender.get_recommendations(
    user_id="user123",
    n_recommendations=5
)

# Registrar evento de compra
await retail_recommender.record_user_event(
    user_id="user123",
    event_type="purchase-complete",
    product_id="product456",
    purchase_amount=99.99
)
```

## Recursos Adicionales

- [Documentación oficial de Google Cloud Retail API](https://cloud.google.com/retail/docs)
- [Guía de Recomendaciones de Productos](https://cloud.google.com/retail/docs/recommendations-overview)
- [Guía de Eventos de Usuario](https://cloud.google.com/retail/docs/user-events)
