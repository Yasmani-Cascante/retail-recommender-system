# Retail Recommender System

Sistema de recomendaciones para retail que combina recomendaciones basadas en contenido con la API de Google Cloud Retail.

## Características

- API REST con FastAPI
- Sistema de recomendaciones híbrido
- Integración con Google Cloud Retail API
- Sistema de caché híbrido con Redis
- Autenticación y autorización
- Logging y monitoreo
- Despliegue en Google Cloud Platform
- Arquitectura unificada y modular

## Requisitos

- Python 3.9+
- Google Cloud Platform account
- Google Cloud SDK
- Redis (opcional, para caché distribuida)

## Configuración Local

1. Clonar el repositorio:
```bash
git clone https://github.com/yourusername/retail-recommender-system.git
cd retail-recommender-system
```

2. Crear entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:
```bash
cp .env.example .env
# Editar .env con tus configuraciones
# Ejemplo de configuraciones adicionales para Redis:
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_PASSWORD=
# REDIS_SSL=false
# USE_REDIS_CACHE=true
# CACHE_TTL=86400
# CACHE_PREFIX=product:
# CACHE_ENABLE_BACKGROUND_TASKS=true
```

5. Ejecutar la aplicación:
```bash
python run.py
```

## Sistema de Caché Híbrido con Redis

El sistema implementa un mecanismo de caché híbrido que utiliza Redis para optimizar el rendimiento y resolver el problema de enriquecimiento de productos que no existen en el catálogo local:

### Características del Sistema de Caché

- **Caché centralizada con Redis**: Proporciona almacenamiento en caché rápido y distribuido
- **Múltiples niveles de fallback**: Redis -> Catálogo local -> Shopify -> Gateway -> Producto mínimo
- **Estadisticas y monitoreo**: Seguimiento de hit ratio, éxitos y fallos
- **Invalidación de caché**: Soporte para invalidar productos individuales o grupos
- **Precarga de productos**: Optimización para cargar múltiples productos en paralelo
- **Resiliencia ante fallos**: Degradación elegante cuando Redis no está disponible

### Activación del Sistema de Caché

Para activar el sistema de caché, configura las siguientes variables de entorno:

```
USE_REDIS_CACHE=true
REDIS_HOST=localhost  # O la dirección del servidor Redis
REDIS_PORT=6379
```

Para desplegar con caché en Google Cloud:

```powershell
# Crear instancia de Redis en Google Cloud Memorystore
.\create_redis.ps1

# Desplegar versión con caché
.\deploy_cached.ps1
```

### Verificación del Sistema de Caché

Para verificar que el sistema de caché está correctamente implementado y configurado:

```bash
python verify_cache_system.py
```

## Pruebas Unitarias y de Integración

### Ejecutar Pruebas Unitarias

Hemos implementado un conjunto completo de pruebas unitarias para los componentes principales del sistema:

```bash
# En Linux/Mac
./run_unit_tests.sh

# En Windows
.\run_unit_tests.ps1
```

También puedes ejecutar pruebas específicas para el sistema de caché:

```bash
# En Windows
python tests\test_redis_connection.py  # Probar conexión a Redis
python tests\test_product_cache.py     # Probar sistema de caché de productos
python tests\test_hybrid_recommender_with_cache.py  # Probar integración del recomendador híbrido con caché

# Script de verificación completa del sistema de caché
python verify_cache_system.py
```

Para más detalles sobre las pruebas, consulte [tests/unit/README.md](tests/unit/README.md).

## Gestión Segura de Secretos

El sistema utiliza variables de entorno para gestionar de forma segura las credenciales y secretos. Estos valores **NO** deben guardarse en el repositorio.

### Configuración de Variables Secretas

1. Crea un archivo `.env.secrets` en la raíz del proyecto (este archivo está en `.gitignore` y no se subirá al repositorio)
2. Añade las siguientes variables con sus valores reales:

```
# Google Cloud Project
GOOGLE_PROJECT_NUMBER=your_project_number
API_KEY=your_api_key

# Shopify
SHOPIFY_SHOP_URL=your_shop_url
SHOPIFY_ACCESS_TOKEN=your_access_token

# Google Cloud Storage
GCS_BUCKET_NAME=your_bucket_name

# Redis (if using cloud Redis)
REDIS_HOST=your_redis_host
REDIS_PORT=your_redis_port
REDIS_PASSWORD=your_redis_password
```

3. Para los scripts PowerShell, las variables se cargan automáticamente desde `.env.secrets`
4. Para los scripts Python, puedes configurar las variables de entorno en tu sistema o usar el archivo `.env.secrets`

### Importante: Protección de Secretos

- **NUNCA** incluyas valores secretos directamente en los scripts
- **NUNCA** subas el archivo `.env.secrets` al repositorio
- Si necesitas compartir la configuración con otros desarrolladores, utiliza un canal seguro o un gestor de secretos
- Considera utilizar Google Secret Manager o AWS Secrets Manager para entornos de producción

## Despliegue en Google Cloud Platform

1. Configurar Google Cloud SDK:
```bash
gcloud init
gcloud auth configure-docker
```

2. Habilitar las APIs necesarias:
```bash
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable retail.googleapis.com
gcloud services enable redis.googleapis.com  # Para Redis Memorystore
```

3. Configurar variables de entorno en GCP:
```bash
gcloud run services update retail-recommender \
  --update-env-vars "API_KEY=your-api-key,GOOGLE_PROJECT_NUMBER=your-project-number,USE_REDIS_CACHE=true,REDIS_HOST=your-redis-host,REDIS_PORT=your-redis-port"
```

4. Desplegar con Cloud Build:
```bash
gcloud builds submit --config cloudbuild.yaml
```

5. Desplegar la versión unificada o con caché:
```powershell
# Desplegar versión unificada en Windows
.\deploy_unified.ps1

# Desplegar versión con caché en Windows
.\deploy_cached.ps1
```

## Documentación API

La documentación de la API está disponible en:
- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Endpoints Principales

- `GET /v1/recommendations/{product_id}`: Obtiene recomendaciones para un producto
- `GET /v1/recommendations/user/{user_id}`: Obtiene recomendaciones personalizadas
- `POST /v1/events/user/{user_id}`: Registra eventos de usuario
- `GET /v1/products/category/{category}`: Lista productos por categoría
- `GET /v1/products/search/`: Busca productos
- `GET /v1/metrics`: Obtiene métricas del sistema de recomendaciones
- `GET /health`: Comprueba el estado del sistema, incluyendo estado de caché

## Arquitectura Unificada

El sistema utiliza una arquitectura unificada con:

- **Configuración centralizada**: Sistema basado en Pydantic
- **Fábricas de componentes**: Creación flexible de instancias
- **Sistema de extensiones**: Funcionalidades modulares activables/desactivables
- **Recomendador híbrido unificado**: Combinación de diferentes estrategias
- **Sistema de caché híbrido**: Múltiples niveles de caché con fallback automático

Para más detalles, consulte la documentación en la carpeta `docs/`.

## Monitoreo

- Logs: Google Cloud Logging
- Métricas: Google Cloud Monitoring
- Trazabilidad: Google Cloud Trace
- Sistema interno de métricas: `/v1/metrics`
- Estado de caché: `/health` incluye información detallada de caché

## Seguridad

- Autenticación API Key
- CORS configurado
- Rate limiting
- Validación de entrada

## Contribuir

1. Fork el repositorio
2. Crear una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

## Licencia

Distribuido bajo la licencia MIT. Ver `LICENSE` para más información.
