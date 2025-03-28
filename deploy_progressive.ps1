# PowerShell script para desplegar la versión progresiva a Cloud Run
Write-Host "Iniciando despliegue de la versión progresiva..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker progresiva..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-progressive:latest -f Dockerfile.progressive .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-progressive:latest

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-progressive `
    --image gcr.io/retail-recommendations-449216/retail-recommender-progressive:latest `
    --platform managed `
    --region us-central1 `
    --memory 512Mi `
    --cpu 1 `
    --timeout 600 `
    --set-env-vars "PROGRESSIVE_MODE=true" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue progresivo completado." -ForegroundColor Green
Write-Host "NOTA: La aplicación simulará un tiempo de carga de aproximadamente 10 segundos." -ForegroundColor Yellow
Write-Host "       Puede verificar el estado accediendo a /health o / (raíz)" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"