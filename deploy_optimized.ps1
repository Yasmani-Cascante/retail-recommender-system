# PowerShell script para desplegar la versión optimizada a Cloud Run
Write-Host "Iniciando despliegue de la versión optimizada..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker optimizada..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-optimized:latest -f Dockerfile.optimized .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-optimized:latest

Write-Host "Desplegando a Cloud Run con configuración optimizada..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-optimized `
    --image gcr.io/retail-recommendations-449216/retail-recommender-optimized:latest `
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

Write-Host "Proceso de despliegue optimizado completado." -ForegroundColor Green
Write-Host "NOTA: La aplicación puede tardar hasta 10 minutos en inicializarse completamente." -ForegroundColor Yellow
Write-Host "       Puede verificar el estado de inicialización accediendo a /health o /" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"