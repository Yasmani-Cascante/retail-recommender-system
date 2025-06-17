# PowerShell script para desplegar versión minimal a Cloud Run
Write-Host "Desplegando versión minimalista a Cloud Run para pruebas..." -ForegroundColor Green

Write-Host "Construyendo la imagen Docker minimalista..." -ForegroundColor Yellow
docker build -t gcr.io/retail-recommendations-449216/retail-minimal -f Dockerfile.minimal .

Write-Host "Autenticando con Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker

Write-Host "Subiendo imagen a Container Registry..." -ForegroundColor Yellow
docker push gcr.io/retail-recommendations-449216/retail-minimal

Write-Host "Desplegando a Cloud Run como 'retail-minimal'..." -ForegroundColor Yellow
gcloud run deploy retail-minimal `
    --image gcr.io/retail-recommendations-449216/retail-minimal `
    --platform managed `
    --region us-central1 `
    --memory 512Mi `
    --timeout 300 `
    --allow-unauthenticated

Write-Host "Proceso de despliegue completado." -ForegroundColor Green
Write-Host "Prueba la versión minimalista y luego podremos trabajar en la versión completa." -ForegroundColor Green
Read-Host "Presiona Enter para salir"