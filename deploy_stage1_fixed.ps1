# PowerShell script para desplegar la versión Stage 1 (corregida) a Cloud Run
Write-Host "Iniciando despliegue de la versión Stage 1 (corregida)..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker Stage 1..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-stage1:fixed -f Dockerfile.stage1 .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-stage1:fixed

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-stage1-fixed `
    --image gcr.io/retail-recommendations-449216/retail-recommender-stage1:fixed `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "STAGE=1" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue Stage 1 (corregido) completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión tiene corregido el problema de middleware" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"