# PowerShell script para desplegar una versión simplificada a Cloud Run
Write-Host "Iniciando despliegue de la versión simple..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker simplificada..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-simple:latest -f Dockerfile.optimized .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-simple:latest

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-simple `
    --image gcr.io/retail-recommendations-449216/retail-recommender-simple:latest `
    --platform managed `
    --region us-central1 `
    --memory 512Mi `
    --cpu 1 `
    --timeout 600 `
    --set-env-vars "SIMPLE_MODE=true" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue simplificado completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión simplificada es solo para verificar que la aplicación responde correctamente" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"