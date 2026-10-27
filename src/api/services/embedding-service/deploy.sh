#!/bin/bash
# services/embedding-service/deploy.sh
#
# Construye, sube y despliega el embedding service en Cloud Run.
#
# USO: desde ESTA carpeta (el contexto de build es "."; el .dockerignore de
# esta carpeta solo deja entrar los ficheros que la imagen necesita):
#     cd src/api/services/embedding-service && bash deploy.sh
# Requiere finales de linea LF: bash no admite CRLF (el \r se pega a cada
# valor). En Windows, ejecutarlo con Git Bash/WSL tras asegurar LF, o usar el
# comando equivalente de PowerShell documentado en
# SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md (seccion 15).
#
# REVISADO 26/10/2026 (E5 nivel 2, cierre del paso 1). Ahora hace exactamente
# lo que se valido a mano en el despliegue de la revision 00062-kvd:
#   - despliega por DIGEST la imagen recien subida (no por la etiqueta);
#   - sonda de arranque de 240 s (antes 135 s; ver H-15 abajo);
#   - --cpu-boost explicito (ya estaba activo en el servicio);
#   - el health check se autentica (el servicio no admite peticiones anonimas);
#   - shebang en la primera linea y comentarios alineados con los flags.
set -e

PROJECT=retail-recommendations-449216
REGION=us-central1
SERVICE_NAME=retail-embedding-service
IMAGE=gcr.io/$PROJECT/$SERVICE_NAME

echo '>>> Building Docker image (ColBERT + FashionSigLIP)...'
docker build -t "$IMAGE" .

echo '>>> Pushing to Container Registry...'
docker push "$IMAGE"

# Desplegar por DIGEST (26/10/2026). Una etiqueta (":latest") es un puntero
# movil: si otra subida la mueve entre el push y el deploy, se desplegaria
# otra imagen. El digest identifica exactamente la imagen que se acaba de
# construir y subir. Se toma el RepoDigest de ESTE repositorio (una imagen
# puede tener digests de varios registros).
IMAGE_DIGEST=$(docker inspect --format='{{range .RepoDigests}}{{println .}}{{end}}' "$IMAGE" | grep "^$IMAGE@sha256:" | head -n 1 || true)
if [ -z "$IMAGE_DIGEST" ]; then
  echo "ERROR: no se encontro el digest de $IMAGE tras el push. No se despliega." >&2
  exit 1
fi
echo ">>> Imagen a desplegar: $IMAGE_DIGEST"

echo '>>> Deploying to Cloud Run...'
# CONFIGURACION (revisada 26/10/2026; antes los comentarios contradecian a los
# flags: decian cpu 2 y min-instances 1 -- hallazgo H-12):
#   --memory 4Gi        ColBERT + FashionSigLIP + indice FAISS + margen.
#   --cpu 1             con --cpu-boost: CPU extra durante el arranque y los
#                       10 s siguientes (doc. Cloud Run), solo se paga entonces.
#   --min-instances 0   el servicio se apaga sin trafico; cada arranque en frio
#                       carga los modelos (104-140 s medidos, 18-26/10/2026).
#   --max-instances 1   un unico indice FAISS en memoria.
#   --timeout 300       la indexacion de imagenes por lotes puede durar >60 s.
#   --startup-probe     failureThreshold=16 x periodSeconds=15 = 240 s, el MAXIMO
#                       que admite Cloud Run (antes 9 x 15 = 135 s). H-15: del
#                       18 al 25/10/2026 la revision en produccion fallo 56 de
#                       64 arranques en frio: todos los correctos tardaron
#                       <= 129,9 s y todos los fallidos que llegaron a terminar,
#                       >= 130,3 s. Los interrumpidos por la sonda pudieron
#                       llegar a ~175 s (ESTIMADO: fase ColBERT de hasta
#                       134,9 s + resto).
#                       NO volver a 9: el incidente reapareceria en silencio.
gcloud beta run deploy "$SERVICE_NAME" \
  --image "$IMAGE_DIGEST" \
  --region "$REGION" \
  --project "$PROJECT" \
  --memory 4Gi \
  --cpu 1 \
  --cpu-boost \
  --min-instances 0 \
  --max-instances 1 \
  --timeout 300 \
  --no-allow-unauthenticated \
  --ingress all \
  --startup-probe="httpGet.path=/health/startup-probe,httpGet.port=8080,initialDelaySeconds=10,periodSeconds=15,timeoutSeconds=3,failureThreshold=16" \
  --set-env-vars VISUAL_INDEX_BUCKET=retail-recommendations-449216-visual-index

echo '>>> Verificando que la revision nueva sirve la imagen desplegada...'
REVISION=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" --project "$PROJECT" \
  --format='value(status.latestReadyRevisionName)')
DEPLOYED=$(gcloud run revisions describe "$REVISION" \
  --region "$REGION" --project "$PROJECT" \
  --format='value(status.imageDigest)')
echo "Revision: $REVISION"
echo "Imagen:   $DEPLOYED"
if [ "$DEPLOYED" != "$IMAGE_DIGEST" ]; then
  echo "AVISO: la revision activa NO sirve la imagen recien subida." >&2
  exit 1
fi

echo '>>> Getting service URL...'
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT" \
  --format='value(status.url)')
echo "Service URL: $SERVICE_URL"

echo ''
echo '>>> Health check:'
# Con token de identidad: el servicio es --no-allow-unauthenticated y una
# peticion anonima siempre seria rechazada (antes este paso siempre "fallaba").
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" "$SERVICE_URL/health" | python3 -m json.tool || echo 'Health check failed (service may still be starting)'

echo ''
echo '>>> NEXT STEP (solo si hace falta reindexar): Trigger image indexation:'
echo "curl -X POST $SERVICE_URL/v1/embed/index-images -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" -H 'Content-Type: application/json' -d '{\"products\": [...catalog...], \"batch_size\": 16}'"
echo ''
echo '>>> Done!'
