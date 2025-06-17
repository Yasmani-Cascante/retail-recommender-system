@echo off
echo Desplegando versión minimalista a Cloud Run para pruebas...
echo.

echo Construyendo la imagen Docker minimalista...
docker build -t gcr.io/retail-recommendations-449216/retail-minimal -f Dockerfile.minimal .

echo Autenticando con Google Cloud...
gcloud auth configure-docker

echo Subiendo imagen a Container Registry...
docker push gcr.io/retail-recommendations-449216/retail-minimal

echo Desplegando a Cloud Run como 'retail-minimal'...
gcloud run deploy retail-minimal ^
    --image gcr.io/retail-recommendations-449216/retail-minimal ^
    --platform managed ^
    --region us-central1 ^
    --memory 512Mi ^
    --timeout 300 ^
    --allow-unauthenticated

echo.
echo Proceso de despliegue completado.
echo Prueba la versión minimalista y luego podremos trabajar en la versión completa.
pause