# PowerShell script para desplegar la versión Final (simplificada) a Cloud Run
Write-Host "Iniciando despliegue de la versión Final (simplificada)..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker Final..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-final:simple -f Dockerfile.final .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-final:simple

Write-Host "Desplegando a Cloud Run con configuración simplificada..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-final-simple `
    --image gcr.io/retail-recommendations-449216/retail-recommender-final:simple `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --concurrency 80 `
    --min-instances 0 `
    --max-instances 10 `
    --set-env-vars "SIMPLIFIED_MODE=true" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue Final (simplificado) completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión tiene una carga simplificada sin dependencias complejas" -ForegroundColor Yellow
Write-Host "       Puedes monitorear el proceso de carga en los logs" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"