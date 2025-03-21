@echo off
echo Preparando el despliegue manual sin cambios en el código...
cd C:\Users\yasma\Desktop\retail-recommender-system

echo Esta opción desplegará directamente desde tu entorno local, sin hacer commit de los cambios.
echo La ventaja es que puedes probar distintas configuraciones sin modificar el repositorio.

echo.
echo ¿Quieres probar un despliegue usando directamente Google Cloud Run (sin App Engine)?
echo 1. Sí, probar Cloud Run directamente
echo 2. No, mejor usar la configuración actual con App Engine
echo.

set /p choice="Elige una opción (1 o 2): "

if "%choice%"=="1" (
    echo.
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
) else (
    echo.
    echo Usando la configuración actual con App Engine...
    echo.
    
    echo Desplegando a App Engine...
    gcloud app deploy app.yaml
)

echo.
echo Proceso de despliegue completado.
pause