# Retail Recommender System

Sistema de recomendaciones para retail que combina recomendaciones basadas en contenido con la API de Google Cloud Retail.

## Características

- API REST con FastAPI
- Sistema de recomendaciones híbrido
- Integración con Google Cloud Retail API
- Autenticación y autorización
- Logging y monitoreo
- Despliegue en Google Cloud Platform
- Arquitectura unificada y modular

## Requisitos

- Python 3.9+
- Google Cloud Platform account
- Google Cloud SDK

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
```

5. Ejecutar la aplicación:
```bash
python run.py
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

También puedes ejecutar pruebas específicas:

```bash
pytest tests/unit/test_config.py -v          # Probar solo el sistema de configuración
pytest tests/unit/test_factories.py -v       # Probar solo las fábricas
pytest tests/unit/test_hybrid_recommender.py -v  # Probar solo el recomendador híbrido
pytest tests/unit/test_extensions.py -v      # Probar solo el sistema de extensiones
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
```

3. Configurar variables de entorno en GCP:
```bash
gcloud run services update retail-recommender \
  --update-env-vars "API_KEY=your-api-key,GOOGLE_PROJECT_NUMBER=your-project-number"
```

4. Desplegar con Cloud Build:
```bash
gcloud builds submit --config cloudbuild.yaml
```

5. Desplegar la versión unificada:
```powershell
# En Windows
.\deploy_unified.ps1
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

## Arquitectura Unificada

El sistema utiliza una arquitectura unificada con:

- **Configuración centralizada**: Sistema basado en Pydantic
- **Fábricas de componentes**: Creación flexible de instancias
- **Sistema de extensiones**: Funcionalidades modulares activables/desactivables
- **Recomendador híbrido unificado**: Combinación de diferentes estrategias

Para más detalles, consulte la documentación en la carpeta `docs/`.

## Monitoreo

- Logs: Google Cloud Logging
- Métricas: Google Cloud Monitoring
- Trazabilidad: Google Cloud Trace
- Sistema interno de métricas: `/v1/metrics`

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