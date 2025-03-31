# PowerShell script para desplegar la versión con recomendador simplificado a Cloud Run
Write-Host "Iniciando despliegue de la versión con recomendador simplificado..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender-simple:latest -f Dockerfile.simple_recommender .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender-simple:latest

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-simple `
    --image gcr.io/retail-recommendations-449216/retail-recommender-simple:latest `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "SIMPLE_RECOMMENDER=true" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue completado." -ForegroundColor Green
Write-Host "NOTA: Esta versión usa un recomendador simplificado que no depende de modelos externos" -ForegroundColor Yellow
Write-Host "       Puedes acceder a /v1/recommendations/content/{product_id} para probar las recomendaciones" -ForegroundColor Yellow
Read-Host "Presiona Enter para salir"