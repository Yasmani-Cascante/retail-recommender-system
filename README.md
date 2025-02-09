# Retail Recommender System

Sistema de recomendaciones para retail que combina recomendaciones basadas en contenido con la API de Google Cloud Retail.

## Características

- API REST con FastAPI
- Sistema de recomendaciones híbrido
- Integración con Google Cloud Retail API
- Autenticación y autorización
- Logging y monitoreo
- Despliegue en Google Cloud Platform

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

## Monitoreo

- Logs: Google Cloud Logging
- Métricas: Google Cloud Monitoring
- Trazabilidad: Google Cloud Trace

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