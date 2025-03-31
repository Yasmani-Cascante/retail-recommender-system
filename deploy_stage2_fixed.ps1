# PowerShell script para desplegar la versión Stage 2 (Corregida) a Cloud Run
Write-Host "Iniciando despliegue de la versión Stage 2 Corregida (Recomendador Basado en Contenido)..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker Stage 2 Corregida..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-stage2:fixed -f Dockerfile.stage2_fixed .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-stage2:fixed

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-stage2-fixed `
    --image gcr.io/retail-recommendations-449216/retail-recommender-stage2:fixed `
    --platform managed `
    --region us-central1 `
    --memory 2Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "STAGE=2_FIXED" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue Stage 2 Corregido completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión tiene correcciones para asegurar que sentence_transformers se instale correctamente" -ForegroundColor Yellow
Write-Host "       Puedes acceder a /v1/recommendations/content/{product_id} para probar las recomendaciones" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"