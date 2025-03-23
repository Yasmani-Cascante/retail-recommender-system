@echo off
echo Intentando despliegue directo a Cloud Run...
echo.

echo Construyendo la imagen Docker localmente...
docker build -t gcr.io/retail-recommendations-449216/retail-recommender .

echo Autenticando con Google Cloud...
gcloud auth configure-docker

echo Subiendo imagen a Container Registry...
docker push gcr.io/retail-recommendations-449216/retail-recommender

echo Desplegando a Cloud Run...
gcloud run deploy retail-recommender-system ^
    --image gcr.io/retail-recommendations-449216/retail-recommender ^
    --platform managed ^
    --region us-central1 ^
    --memory 1Gi ^
    --timeout 300 ^
    --set-env-vars "GOOGLE_PROJECT_NUMBER=178362262166,GOOGLE_LOCATION=us-central1,GOOGLE_CATALOG=default_catalog,GOOGLE_SERVING_CONFIG=default_config,API_KEY=2fed9999056fab6dac5654238f0cae1c" ^
    --allow-unauthenticated

echo.
echo Proceso de despliegue completado.
pause