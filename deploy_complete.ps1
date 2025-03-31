# PowerShell script para desplegar la versión completa a Cloud Run
Write-Host "Iniciando despliegue de la versión completa..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-complete:latest -f Dockerfile.complete .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-complete:latest

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-complete `
    --image gcr.io/retail-recommendations-449216/retail-recommender-complete:latest `
    --platform managed `
    --region us-central1 `
    --memory 2Gi `
    --cpu 1 `
    --timeout 600 `
    --concurrency 80 `
    --min-instances 0 `
    --max-instances 10 `
    --set-env-vars "GOOGLE_PROJECT_NUMBER=178362262166,GOOGLE_LOCATION=global,GOOGLE_CATALOG=default_catalog,GOOGLE_SERVING_CONFIG=default_recommendation_config,API_KEY=2fed9999056fab6dac5654238f0cae1c,GCS_BUCKET_NAME=retail-recommendations-449216_cloudbuild,USE_GCS_IMPORT=true" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue completo terminado." -ForegroundColor Green
Write-Host "NOTA: Esta versión implementa el sistema de recomendaciones híbrido completo." -ForegroundColor Yellow
Write-Host "       Incluye integración con Google Cloud Retail API y recomendador híbrido." -ForegroundColor Yellow
Write-Host "       Endpoints disponibles:" -ForegroundColor Yellow
Write-Host "       - /v1/products/ (listado de productos)" -ForegroundColor Yellow
Write-Host "       - /v1/recommendations/content/{product_id} (recomendaciones basadas en contenido)" -ForegroundColor Yellow
Write-Host "       - /v1/recommendations/product/{product_id} (recomendaciones híbridas)" -ForegroundColor Yellow
Write-Host "       - /v1/recommendations/user/{user_id} (recomendaciones personalizadas)" -ForegroundColor Yellow
Write-Host "       - /v1/events/user/{user_id} (registro de eventos de usuario)" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"