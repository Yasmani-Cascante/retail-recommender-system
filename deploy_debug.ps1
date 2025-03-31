# PowerShell script para desplegar la versión de depuración a Cloud Run
Write-Host "Iniciando despliegue de la versión de depuración..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker de depuración..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-debug:latest -f Dockerfile.debug .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-debug:latest

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-debug `
    --image gcr.io/retail-recommendations-449216/retail-recommender-debug:latest `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "DEBUG_MODE=true" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue de depuración completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión incluye información detallada de depuración" -ForegroundColor Yellow
Write-Host "       Visita /health o / para ver la información de diagnóstico" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"