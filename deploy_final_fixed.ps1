# PowerShell script para desplegar la versión Final (corregida) a Cloud Run
Write-Host "Iniciando despliegue de la versión Final (corregida)..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker Final..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-final:fixed -f Dockerfile.final .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-final:fixed

Write-Host "Desplegando a Cloud Run con configuración optimizada..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-final-fixed `
    --image gcr.io/retail-recommendations-449216/retail-recommender-final:fixed `
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

Write-Host "Proceso de despliegue Final (corregido) completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión tiene corregido el problema de middleware" -ForegroundColor Yellow
Write-Host "       Puedes monitorear el proceso de carga en los logs" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"