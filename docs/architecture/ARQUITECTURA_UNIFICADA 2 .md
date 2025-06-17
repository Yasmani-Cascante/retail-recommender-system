# Arquitectura Unificada del Sistema de Recomendaciones para Retail

## Descripción General

Esta implementación establece una arquitectura unificada para el sistema de recomendaciones de retail, usando un enfoque modular con configuración centralizada que permite activar/desactivar funcionalidades específicas sin necesidad de mantener múltiples versiones del código.

## Cambios Principales

### 1. Uso Exclusivo de la Implementación Unificada

- Se utiliza exclusivamente la implementación del recomendador híbrido en `src/api/core/hybrid_recommender.py`
- Se elimina la dependencia de `ContentBasedRecommender` que requería `sentence_transformers`
- La versión en `src/recommenders/hybrid.py` se mantiene solo como compatibilidad

### 2. Sistema de Fábricas

Se ha ampliado el sistema de fábricas para crear todos los componentes del sistema:

```python
# Crear componentes a través de la factoría
content_recommender = RecommenderFactory.create_content_recommender()
retail_recommender = RecommenderFactory.create_retail_recommender()
product_cache = RecommenderFactory.create_product_cache()
hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
    content_recommender=content_recommender,
    retail_recommender=retail_recommender,
    product_cache=product_cache
)
```

### 3. Configuración Centralizada

La configuración está centralizada en `src/api/core/config.py` con soporte para:

- Diferentes tipos de recomendadores
- Activación/desactivación de funcionalidades
- Configuración de caché y Redis
- Soporte para diferentes versiones de Pydantic

## Configuración

Para configurar el sistema, edita el archivo `.env` con las siguientes opciones:

### Opciones Principales:

- `USE_UNIFIED_ARCHITECTURE`: Activa la arquitectura unificada (default: true)
- `USE_TRANSFORMERS`: Usa ContentBasedRecommender en lugar de TF-IDF si está disponible (default: false)
- `EXCLUDE_SEEN_PRODUCTS`: Excluye productos ya vistos por el usuario (default: true)
- `USE_REDIS_CACHE`: Activa el sistema de caché con Redis (default: false)

### Configuración del Recomendador:

- `CONTENT_WEIGHT`: Peso para las recomendaciones basadas en contenido (0-1)
- `TFIDF_MODEL_PATH`: Ruta al modelo TF-IDF

## Beneficios de la Arquitectura Unificada

1. **Código Centralizado**: Una única fuente de verdad para cada componente
2. **Configuración Flexible**: Activación/desactivación de funcionalidades sin cambiar código
3. **Extensibilidad**: Fácil incorporación de nuevos componentes
4. **Mantenibilidad**: Menos código duplicado y mayor claridad
5. **Diagnóstico Mejorado**: Errores detallados y degradación elegante

## Desarrollo Futuro

Para extender la arquitectura unificada:

1. Añadir nuevos recomendadores implementando métodos en la factoría
2. Crear nuevas extensiones para funcionalidades adicionales
3. Configurar opciones adicionales en `config.py`

## Ejemplos de Uso

### Crear un Recomendador con la Factoría

```python
from src.api.factories import RecommenderFactory

# Crear un recomendador TF-IDF
tfidf_recommender = RecommenderFactory.create_content_recommender()

# Crear un recomendador híbrido unificado
hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
    content_recommender=tfidf_recommender,
    retail_recommender=retail_recommender
)
```

### Añadir Nueva Funcionalidad

Para añadir una nueva funcionalidad:

1. Actualiza `config.py` con la nueva opción de configuración
2. Implementa la lógica en un componente específico
3. Modifica la factoría para crear el componente según la configuración
4. Usa el componente donde sea necesario

## Notas Adicionales

- La implementación unificada facilita la integración de nuevos componentes como el sistema de caché híbrido con Redis
- El enfoque modular permite la evolución del sistema sin afectar componentes existentes
- La degradación elegante garantiza la operatividad incluso ante fallos parciales
