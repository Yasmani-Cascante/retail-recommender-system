# Instrucciones para Desplegar en Google Cloud Run

Una vez que hayas subido el código a GitHub de forma segura, puedes seguir estas instrucciones para desplegar el sistema de recomendaciones en Google Cloud Run.

## Prerequisitos

1. Asegúrate de tener instalado:
   - Google Cloud SDK: [https://cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)
   - Docker Desktop: [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
   - PowerShell 5.1 o superior

2. Configura tus credenciales de Google Cloud:
   ```powershell
   gcloud auth login
   ```

## Paso 1: Configurar Secretos

Asegúrate de tener el archivo `.env.secrets` correctamente configurado:

```powershell
# Si no lo has hecho ya:
copy .env.secrets.example .env.secrets
notepad .env.secrets
```

## Paso 2: Desplegar con Script

Usa uno de los scripts de despliegue, según la versión que desees implementar:

### Versión con Corrección para Predicciones

Esta versión incluye la corrección para el error "Unknown field for PredictionResult: product":

```powershell
.\deploy_prediction_fix.ps1
```

### Versión con Métricas Completas

Esta versión incluye el sistema de métricas completo:

```powershell
.\deploy_tfidf_full_metrics.ps1
```

### Versión Básica con Shopify

La versión con integración a Shopify:

```powershell
.\deploy_tfidf_shopify.ps1
```

## Paso 3: Verificar el Despliegue

Una vez completado el despliegue, el script mostrará la URL del servicio. Verifica que funciona correctamente:

1. Abre la URL en tu navegador con `/health` al final para comprobar el estado:
   ```
   https://tu-servicio-url.run.app/health
   ```

2. Prueba algunas recomendaciones (requiere la cabecera API Key):
   ```
   https://tu-servicio-url.run.app/v1/recommendations/user/test_user_123
   ```

## Solución de Problemas Comunes

### Error "Unknown field for PredictionResult: product"

Si encuentras este error en los logs, asegúrate de usar el script `deploy_prediction_fix.ps1` que incluye la corrección.

### Problemas con Secretos en el Despliegue

Si encuentras errores relacionados con secretos o variables de entorno:

1. Verifica que el archivo `.env.secrets` existe y está correctamente formateado.
2. Comprueba que el módulo `deploy_common.ps1` está en el directorio raíz.
3. Asegúrate de que los valores en el archivo son correctos.

### Fallo en la Construcción de la Imagen Docker

Si la construcción de la imagen Docker falla:

1. Verifica que Docker Desktop está corriendo.
2. Prueba construir la imagen manualmente:
   ```powershell
   docker build -t retail-recommender -f Dockerfile.tfidf.shopify .
   ```
3. Revisa los errores específicos en la salida.

## Recursos Adicionales

- [Documentación de Google Cloud Run](https://cloud.google.com/run/docs)
- [Documentación de Docker](https://docs.docker.com/)
- [Troubleshooting Cloud Run](https://cloud.google.com/run/docs/troubleshooting)
