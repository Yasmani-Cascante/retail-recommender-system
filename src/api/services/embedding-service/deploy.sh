# services/embedding-service/deploy.sh
#!/bin/bash
set -e

PROJECT=retail-recommendations-449216
REGION=us-central1
SERVICE_NAME=retail-embedding-service
IMAGE=gcr.io/$PROJECT/$SERVICE_NAME

echo '>>> Building Docker image (ColBERT + FashionSigLIP, ~1.7GB)...'
docker build -t $IMAGE .

echo '>>> Pushing to Container Registry...'
docker push $IMAGE

echo '>>> Deploying to Cloud Run...'
# CAMBIOS (22/04/2026 — Opción A Visual Search):
#   --memory 4Gi    (era 2Gi)  — ColBERT ~700MB + fashionSigLIP ~400MB + margen operativo
#   --cpu 2         (era 1)    — indexación paralela de imágenes, encode más rápido
#   --min-instances 1          — sin cambio, ya estaba en 1 para ColBERT
#   --timeout 300   (era 60)   — la indexación de imagen por batch puede durar >60s
gcloud beta run deploy $SERVICE_NAME \
  --image $IMAGE \
  --region $REGION \
  --project $PROJECT \
  --memory 4Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 1 \
  --timeout 300 \
  --no-allow-unauthenticated \
  --ingress all \
  --startup-probe="httpGet.path=/health/startup-probe,httpGet.port=8080,initialDelaySeconds=10,periodSeconds=15,timeoutSeconds=3,failureThreshold=9" \
  --set-env-vars VISUAL_INDEX_BUCKET=retail-recommendations-449216-visual-index


echo '>>> Getting service URL...'
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --project $PROJECT \
  --format='value(status.url)')
echo "Service URL: $SERVICE_URL"

echo ''
echo '>>> Health check:'
curl -s "$SERVICE_URL/health" | python3 -m json.tool || echo 'Health check failed (service may still be starting)'

echo ''
echo '>>> NEXT STEP: Trigger image indexation:'
echo "curl -X POST $SERVICE_URL/v1/embed/index-images -H 'Content-Type: application/json' -d '{\"products\": [...catalog...], \"batch_size\": 16}'"
echo ''
echo '>>> Done!'
