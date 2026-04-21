# services/embedding-service/deploy.sh
#!/bin/bash
set -e
 
PROJECT=retail-recommendations-449216
REGION=us-central1
SERVICE_NAME=retail-embedding-service
IMAGE=gcr.io/$PROJECT/$SERVICE_NAME
 
echo '>>> Building Docker image (includes model download ~350MB)...'
docker build -t $IMAGE .
 
echo '>>> Pushing to Container Registry...'
docker push $IMAGE
 
echo '>>> Deploying to Cloud Run...'
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --region $REGION \
  --project $PROJECT \
  --memory 2Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 60 \
  --no-allow-unauthenticated \
  --ingress internal
 
echo '>>> Getting service URL...'
gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --project $PROJECT \
  --format='value(status.url)'
 
echo '>>> Done!'
