# Guía de Migración a la Arquitectura Unificada

Este documento proporciona instrucciones paso a paso para migrar código y funcionalidades desde las versiones anteriores del sistema de recomendaciones a la nueva arquitectura unificada.

## Tabla de Contenidos

1. [Migración de Configuración](#1-migración-de-configuración)
2. [Migración de Recomendadores](#2-migración-de-recomendadores)
3. [Migración de Endpoints](#3-migración-de-endpoints)
4. [Migración de Funcionalidades Personalizadas](#4-migración-de-funcionalidades-personalizadas)
5. [Pruebas y Validación](#5-pruebas-y-validación)

## 1. Migración de Configuración

### Versión Anterior

En la versión anterior, la configuración se realizaba mediante variables de entorno dispersas en el código:

```python
# Ejemplo de código anterior
project_number = os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166")
location = os.getenv("GOOGLE_LOCATION", "global")
catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
```

### Versión Unificada

En la nueva arquitectura, utiliza el sistema de configuración centralizado:

```python
# Nueva forma de obtener configuración
from src.api.core.config import get_settings

settings = get_settings()
project_number = settings.google_project_number
location = settings.google_location
catalog = settings.google_catalog
```

### Pasos para Migrar

1. Identifica todas las variables de entorno utilizadas en tu código
2. Verifica si ya están incluidas en `src/api/core/config.py`
3. Si alguna variable no está incluida, añádela a la clase `RecommenderSettings`
4. Reemplaza las llamadas a `os.getenv()` por referencias a `settings`

## 2. Migración de Recomendadores

### Versión Anterior

En la versión anterior, los recomendadores se creaban directamente:

```python
# Ejemplo de código anterior
tfidf_recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")
retail_recommender = RetailAPIRecommender(
    project_number=os.getenv("GOOGLE_PROJECT_NUMBER"),
    location=os.getenv("GOOGLE_LOCATION"),
    catalog=os.getenv("GOOGLE_CATALOG"),
    serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG")
)
```

### Versión Unificada

En la nueva arquitectura, utiliza las fábricas para crear instancias:

```python
# Nueva forma de crear recomendadores
from src.api.factories import RecommenderFactory

tfidf_recommender = RecommenderFactory.create_tfidf_recommender()
retail_recommender = RecommenderFactory.create_retail_recommender()
hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
    tfidf_recommender, retail_recommender
)
```

### Pasos para Migrar

1. Identifica todas las instancias de recomendadores en tu código
2. Reemplázalas por llamadas a los métodos de fábrica correspondientes
3. Si tienes implementaciones personalizadas, considera añadirlas como métodos a la fábrica

## 3. Migración de Endpoints

### Versión Anterior

En la versión anterior, los endpoints accedían directamente a componentes específicos:

```python
# Ejemplo de código anterior
@app.get("/v1/recommendations/{product_id}")
async def get_recommendations(product_id: str):
    recommendations = await hybrid_recommender.get_recommendations(
        user_id="anonymous",
        product_id=product_id,
        n_recommendations=5
    )
    return {"recommendations": recommendations}
```

### Versión Unificada

En la nueva arquitectura, los endpoints utilizan configuración centralizada y fábricas:

```python
# Nueva forma de implementar endpoints
@app.get("/v1/recommendations/{product_id}")
async def get_recommendations(
    product_id: str, 
    n: Optional[int] = Query(5)
):
    # Usar configuración centralizada
    settings = get_settings()
    
    # Obtener recomendaciones
    recommendations = await hybrid_recommender.get_recommendations(
        user_id="anonymous",
        product_id=product_id,
        n_recommendations=n
    )
    
    # Registrar métricas si están habilitadas
    if settings.use_metrics:
        from src.api.core.metrics import recommendation_metrics
        recommendation_metrics.record_recommendation_request(...)
        
    return {"recommendations": recommendations}
```

### Pasos para Migrar

1. Identifica los endpoints en tu código
2. Reemplaza accesos directos a configuración por el sistema centralizado
3. Añade lógica condicional basada en la configuración (por ejemplo, métricas)
4. Asegúrate de usar las fábricas para obtener instancias de componentes

## 4. Migración de Funcionalidades Personalizadas

### Versión Anterior

En la versión anterior, las funcionalidades personalizadas estaban integradas directamente en el código:

```python
# Ejemplo de código anterior con funcionalidad personalizada
# Código para métricas directamente en el archivo principal
@app.get("/v1/metrics")
async def get_metrics():
    return recommendation_metrics.get_aggregated_metrics()

# Lógica para exclusión de productos vistos integrada directamente
filtered_recommendations = [r for r in recommendations if r["id"] not in seen_products]
```

### Versión Unificada

En la nueva arquitectura, implementa las funcionalidades como extensiones:

```python
# Nueva forma de implementar funcionalidades personalizadas
# 1. Crear una clase de extensión
class MiFuncionalidadExtension:
    def __init__(self, app, settings):
        self.app = app
        self.settings = settings
        
    def setup(self):
        if not self.settings.use_mi_funcionalidad:
            return
        
        # Configurar la funcionalidad
        @self.app.get("/v1/mi-funcionalidad")
        async def mi_endpoint():
            return {"status": "success"}

# 2. Registrar la extensión en main_unified.py
if settings.use_mi_funcionalidad:
    from src.api.extensions.mi_funcionalidad_extension import MiFuncionalidadExtension
    mi_extension = MiFuncionalidadExtension(app, settings)
    mi_extension.setup()
```

### Pasos para Migrar

1. Identifica funcionalidades personalizadas en tu código
2. Crea nuevas clases de extensión en el directorio `src/api/extensions/`
3. Implementa la lógica dentro de las extensiones
4. Añade opciones de configuración en `config.py`
5. Registra las extensiones en `main_unified.py`

## 5. Pruebas y Validación

Después de migrar tu código a la nueva arquitectura, es importante validar que todo funcione correctamente:

1. **Pruebas Unitarias**:
   - Crea pruebas para tus componentes personalizados
   - Utiliza mocks para simular dependencias

2. **Pruebas de Integración**:
   - Verifica que los componentes interactúan correctamente
   - Prueba los diferentes flujos del sistema

3. **Pruebas de Configuración**:
   - Verifica que las diferentes opciones de configuración funcionan como se espera
   - Prueba activar/desactivar características

4. **Verificación de Endpoints**:
   - Prueba todos los endpoints con diferentes parámetros
   - Verifica que las respuestas son correctas

5. **Despliegue de Prueba**:
   - Utiliza `deploy_unified.ps1` para desplegar una versión de prueba
   - Verifica que el sistema funciona correctamente en el entorno de Cloud Run

## Ejemplos de Migración

### Ejemplo 1: Migrar una Estrategia de Fallback Personalizada

**Código Original:**

```python
# En main_tfidf_custom_fallback.py
async def custom_fallback_strategy(products, n=5):
    # Lógica personalizada de fallback
    return selected_products
    
@app.get("/v1/recommendations/fallback")
async def get_fallback_recommendations(n: int = 5):
    products = await custom_fallback_strategy(tfidf_recommender.product_data, n)
    return {"recommendations": products}
```

**Código Migrado:**

```python
# 1. Crear extension en src/api/extensions/custom_fallback_extension.py
class CustomFallbackExtension:
    def __init__(self, app, settings, recommender):
        self.app = app
        self.settings = settings
        self.recommender = recommender
        
    def setup(self):
        if not self.settings.use_custom_fallback:
            return
            
        @self.app.get("/v1/recommendations/fallback")
        async def get_fallback_recommendations(n: int = 5):
            products = await self._custom_fallback_strategy(
                self.recommender.product_data, n
            )
            return {"recommendations": products}
            
    async def _custom_fallback_strategy(self, products, n=5):
        # Lógica personalizada de fallback
        return selected_products

# 2. Añadir configuración en src/api/core/config.py
class RecommenderSettings(BaseSettings):
    # ... configuración existente
    use_custom_fallback: bool = Field(default=False, env="USE_CUSTOM_FALLBACK")

# 3. Registrar en main_unified.py
if settings.use_custom_fallback:
    from src.api.extensions.custom_fallback_extension import CustomFallbackExtension
    custom_fallback_extension = CustomFallbackExtension(app, settings, tfidf_recommender)
    custom_fallback_extension.setup()
```

### Ejemplo 2: Migrar un Sistema de Validación de Productos

**Código Original:**

```python
# En retail_api.py
async def import_catalog(self, products: List[Dict]):
    # Validación de productos
    validated_products = []
    for product in products:
        if self._validate_product(product):
            validated_products.append(product)
    
    # Importar productos validados
    # ...

def _validate_product(self, product: Dict) -> bool:
    # Lógica de validación
    if not product.get("id"):
        return False
    # Más validaciones...
    return True
```

**Código Migrado:**

```python
# 1. Crear un validador separado en src/api/core/product_validator.py
class ProductValidator:
    def __init__(self, settings):
        self.settings = settings
        
    def validate_products(self, products: List[Dict]) -> Tuple[List[Dict], Dict]:
        if not self.settings.validate_products:
            return products, {"validation_skipped": True}
            
        validated_products = []
        stats = {"total": len(products), "valid": 0, "invalid": 0}
        
        for product in products:
            if self._validate_product(product):
                validated_products.append(product)
                stats["valid"] += 1
            else:
                stats["invalid"] += 1
                
        return validated_products, stats
        
    def _validate_product(self, product: Dict) -> bool:
        # Lógica de validación
        if not product.get("id"):
            return False
        # Más validaciones...
        return True

# 2. Modificar retail_api.py para usar el validador
from src.api.core.product_validator import ProductValidator
from src.api.core.config import get_settings

async def import_catalog(self, products: List[Dict]):
    settings = get_settings()
    
    # Usar validador si está habilitado
    if settings.validate_products:
        validator = ProductValidator(settings)
        validated_products, stats = validator.validate_products(products)
        logger.info(f"Validación de productos: {stats}")
        products = validated_products
    
    # Importar productos
    # ...
```

### Ejemplo 3: Migrar Métricas Personalizadas

**Código Original:**

```python
# En main_tfidf_metrics.py
# Inicialización de métricas
recommendation_metrics = RecommendationMetrics()

# Endpoint para obtener métricas
@app.get("/v1/custom-metrics")
async def get_custom_metrics():
    return {
        "conversion_rate": recommendation_metrics.calculate_conversion_rate(),
        "other_metric": calculate_other_metric()
    }

def calculate_other_metric():
    # Lógica para calcular otra métrica
    return value
```

**Código Migrado:**

```python
# 1. Crear extensión en src/api/extensions/custom_metrics_extension.py
class CustomMetricsExtension:
    def __init__(self, app, settings):
        self.app = app
        self.settings = settings
        
    def setup(self):
        if not self.settings.use_custom_metrics:
            return
            
        # Importar métricas base
        from src.api.core.metrics import recommendation_metrics
        
        @self.app.get("/v1/custom-metrics")
        async def get_custom_metrics():
            return {
                "conversion_rate": self._calculate_conversion_rate(recommendation_metrics),
                "other_metric": self._calculate_other_metric()
            }
            
    def _calculate_conversion_rate(self, metrics):
        # Lógica para calcular tasa de conversión
        return value
        
    def _calculate_other_metric(self):
        # Lógica para calcular otra métrica
        return value

# 2. Añadir configuración en src/api/core/config.py
class RecommenderSettings(BaseSettings):
    # ... configuración existente
    use_custom_metrics: bool = Field(default=False, env="USE_CUSTOM_METRICS")

# 3. Registrar en main_unified.py
if settings.use_custom_metrics:
    from src.api.extensions.custom_metrics_extension import CustomMetricsExtension
    custom_metrics_extension = CustomMetricsExtension(app, settings)
    custom_metrics_extension.setup()
```

## Recomendaciones Finales

1. **Migra gradualmente**: Comienza con los componentes más sencillos y avanza hacia los más complejos.

2. **Versiona el código**: Realiza la migración en una rama separada para no afectar el código existente.

3. **Prueba exhaustivamente**: Asegúrate de que cada componente migrado funcione correctamente.

4. **Documenta los cambios**: Mantén un registro de los cambios realizados para facilitar el mantenimiento futuro.

5. **Formación del equipo**: Asegúrate de que todos los miembros del equipo comprendan la nueva arquitectura y cómo utilizarla.

6. **Monitoreo post-migración**: Implementa un sistema de monitoreo para detectar posibles problemas tras la migración.

## Preguntas Frecuentes

**P: ¿Es necesario migrar todo el código a la vez?**

R: No, puedes migrar gradualmente. La nueva arquitectura está diseñada para coexistir con el código anterior.

**P: ¿Qué hago si mi funcionalidad no encaja en el sistema de extensiones?**

R: Las extensiones son flexibles. Si tu funcionalidad no encaja bien, consulta con el equipo para diseñar una solución adecuada.

**P: ¿Cómo puedo añadir nuevas opciones de configuración?**

R: Modifica la clase `RecommenderSettings` en `src/api/core/config.py` añadiendo nuevos campos con sus valores por defecto.

**P: ¿Puedo seguir utilizando las clases/funciones originales?**

R: Sí, las clases y funciones originales siguen disponibles. Sin embargo, se recomienda utilizar las fábricas y el sistema de configuración centralizado.

**P: ¿Qué sucede si la migración causa problemas en producción?**

R: El script de despliegue `deploy_unified.ps1` despliega la nueva versión en un servicio separado, por lo que puedes volver a la versión anterior simplemente redirigiendo el tráfico.
