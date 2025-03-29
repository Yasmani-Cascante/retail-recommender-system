# PowerShell script para desplegar la versión Stage 1 (simplificada) a Cloud Run
Write-Host "Iniciando despliegue de la versión Stage 1 (simplificada)..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker Stage 1..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-stage1:simple -f Dockerfile.stage1 .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-stage1:simple

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-stage1-simple `
    --image gcr.io/retail-recommendations-449216/retail-recommender-stage1:simple `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "STAGE=1_SIMPLE" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue Stage 1 (simplificado) completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión tiene endpoints simplificados sin dependencias ML" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"