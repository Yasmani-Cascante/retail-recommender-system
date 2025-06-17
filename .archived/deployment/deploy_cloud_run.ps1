# PowerShell script para desplegar a Cloud Run
Write-Host "Intentando despliegue directo a Cloud Run..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker localmente..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-recommender .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-recommender

Write-Host "Desplegando a Cloud Run..." -ForegroundColor Yellow
gcloud run deploy retail-recommender-system `
    --image gcr.io/retail-recommendations-449216/retail-recommender `
    --platform managed `
    --region us-central1 `
    --memory 1Gi `
    --timeout 300 `
    --set-env-vars "GOOGLE_PROJECT_NUMBER=178362262166,GOOGLE_LOCATION=global,GOOGLE_CATALOG=default_catalog,GOOGLE_SERVING_CONFIG=default_recommendation_config,API_KEY=2fed9999056fab6dac5654238f0cae1c" `
    --allow-unauthenticated

Write-Host "Proceso de despliegue completado." -ForegroundColor Green
Read-Host "Presiona Enter para salir"