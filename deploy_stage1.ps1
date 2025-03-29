# PowerShell script para desplegar la versión Stage 1 a Cloud Run
Write-Host "Iniciando despliegue de la versión Stage 1..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker Stage 1..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-stage1:latest -f Dockerfile.stage1 .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-stage1:latest

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-stage1 `
    --image gcr.io/retail-recommendations-449216/retail-recommender-stage1:latest `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "STAGE=1" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue Stage 1 completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión implementa carga de routers pero usa datos de muestra" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"