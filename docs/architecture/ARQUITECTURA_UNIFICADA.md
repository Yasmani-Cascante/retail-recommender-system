# Arquitectura Unificada del Sistema de Recomendaciones

## Descripción General

Esta implementación consolida las múltiples versiones del sistema de recomendaciones en una arquitectura modular y configurable. La nueva arquitectura utiliza un sistema de configuración centralizado, fábricas para la creación de componentes y extensiones activables según la configuración.

## Componentes Principales

### 1. Sistema de Configuración Centralizado

El archivo `src/api/core/config.py` implementa un sistema de configuración basado en Pydantic que:

- Lee variables de entorno
- Proporciona valores por defecto cuando es necesario
- Admite activación/desactivación de características mediante flags
- Cachea la configuración para evitar lecturas repetidas

Ejemplo de uso:
```python
from src.api.core.config import get_settings

settings = get_settings()
if settings.use_metrics:
    # Configurar sistema de métricas
```

### 2. Fábricas de Componentes

El archivo `src/api/factories.py` proporciona fábricas para crear los diferentes componentes del sistema:

- `RecommenderFactory`: Crea instancias de los diferentes tipos de recomendadores
  - `create_tfidf_recommender()`: Crea un recomendador basado en TF-IDF
  - `create_retail_recommender()`: Crea un recomendador basado en Google Retail API
  - `create_hybrid_recommender()`: Crea el recomendador híbrido adecuado según la configuración

### 3. Recomendador Híbrido Unificado

El archivo `src/api/core/hybrid_recommender.py` consolida las diferentes implementaciones del recomendador híbrido:

- `HybridRecommender`: Implementación base que combina recomendaciones de diferentes fuentes
- `HybridRecommenderWithExclusion`: Extensión que excluye productos ya vistos por el usuario

### 4. Sistema de Extensiones

El directorio `src/api/extensions/` contiene extensiones modulares que pueden activarse según la configuración:

- `metrics_extension.py`: Añade endpoints y lógica para métricas y análisis de rendimiento

### 5. Archivo Principal Unificado

El archivo `src/api/main_unified.py` implementa la API REST utilizando los componentes anteriores.

## Configuración

### Variables de Entorno

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `GOOGLE_PROJECT_NUMBER` | Número de proyecto en GCP | (Requerido) |
| `GOOGLE_LOCATION` | Ubicación de los servicios en GCP | `global` |
| `GOOGLE_CATALOG` | Nombre del catálogo en Retail API | `default_catalog` |
| `GOOGLE_SERVING_CONFIG` | Configuración de serving en Retail API | `default_recommendation_config` |
| `API_KEY` | API Key para autenticación | (Requerido) |
| `SHOPIFY_SHOP_URL` | URL de la tienda Shopify | (Requerido) |
| `SHOPIFY_ACCESS_TOKEN` | Token de acceso a Shopify | (Requerido) |
| `GCS_BUCKET_NAME` | Nombre del bucket en GCS para importación | (Requerido) |
| `USE_GCS_IMPORT` | Usar GCS para importación de catálogos | `true` |
| `DEBUG` | Activar modo de depuración | `false` |
| `METRICS_ENABLED` | Activar sistema de métricas | `true` |
| `EXCLUDE_SEEN_PRODUCTS` | Excluir productos ya vistos | `true` |
| `DEFAULT_CURRENCY` | Código de moneda predeterminado | `COP` |
| `USE_REDIS_CACHE` | Activar caché con Redis | `false` |
| `REDIS_URL` | URL de conexión a Redis | (Opcional) |

## Activación/Desactivación de Características

La nueva arquitectura permite activar o desactivar características simplemente modificando las variables de entorno:

- **Métricas**: `METRICS_ENABLED=true/false`
- **Exclusión de productos vistos**: `EXCLUDE_SEEN_PRODUCTS=true/false`
- **Validación de productos**: `VALIDATE_PRODUCTS=true/false`
- **Uso de fallback**: `USE_FALLBACK=true/false`
- **Caché con Redis**: `USE_REDIS_CACHE=true/false`

## Despliegue

Para desplegar la versión unificada, utilice el script `deploy_unified.ps1`:

```powershell
.\deploy_unified.ps1
```

Este script:
1. Crea un Dockerfile específico para la versión unificada
2. Construye y despliega la imagen en Google Cloud Run
3. Realiza pruebas básicas de funcionalidad
4. Muestra instrucciones para pruebas manuales adicionales

## Ventajas sobre la Arquitectura Anterior

1. **Centralización**: Una única fuente de verdad para la configuración
2. **Modularidad**: Componentes claramente separados con responsabilidades definidas
3. **Extensibilidad**: Facilidad para añadir nuevas funcionalidades sin modificar código existente
4. **Mantenibilidad**: Menos código duplicado y más fácil de entender
5. **Flexibilidad**: Activación/desactivación de características sin cambios en el código
6. **Testabilidad**: Componentes más fáciles de probar de forma aislada

## Planificación para el Futuro

La nueva arquitectura facilita la implementación de mejoras futuras:

1. **Caché distribuida**: Implementación de caché con Redis para mejorar rendimiento
2. **Microservicios**: Evolución hacia una arquitectura de microservicios para mayor escalabilidad
3. **Pre-computación de vectores**: Implementación de pre-computación durante CI/CD
4. **Reintroducción de Transformer**: Posibilidad de reintroducir modelos transformer de manera gradual
5. **Sistema de plugins**: Extensión del sistema de extensiones para admitir plugins de terceros

## Documentación Adicional

- [Diagrama de la Arquitectura Unificada](docs/unified_architecture.md)
- [Guía de Desarrollo con la Arquitectura Unificada](docs/development_guide.md)
- [Mejores Prácticas para Extender el Sistema](docs/extension_guide.md)
