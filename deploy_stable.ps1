# PowerShell script para desplegar la versión estable a Cloud Run
Write-Host "Iniciando despliegue de la versión estable..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker estable..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-stable:latest -f Dockerfile.stable .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-stable:latest

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-stable `
    --image gcr.io/retail-recommendations-449216/retail-recommender-stable:latest `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "SIMPLIFY_CONFIG=true" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue estable completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión es una implementación estable y simplificada." -ForegroundColor Yellow
Write-Host "       Incluye solo el recomendador basado en contenido." -ForegroundColor Yellow
Write-Host "       Endpoints disponibles:" -ForegroundColor Yellow
Write-Host "       - /v1/products/ (listado de productos)" -ForegroundColor Yellow
Write-Host "       - /v1/products/search/ (búsqueda de productos)" -ForegroundColor Yellow
Write-Host "       - /v1/recommendations/content/{product_id} (recomendaciones basadas en contenido)" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"