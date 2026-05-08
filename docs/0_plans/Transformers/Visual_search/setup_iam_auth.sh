#!/bin/bash
# setup_iam_auth.sh — Activa autenticación IAM entre monolito y embedding-service.
#
# Ejecutar desde la raíz del proyecto DESPUÉS de que el monolito ya esté
# desplegado con el nuevo colbert_client.py (que incluye _auth_headers()).
#
# PREREQUISITO: desplegar primero el monolito:
#   gcloud run deploy retail-recommender --source . --region us-central1 ...
#
# Qué hace este script:
#   1. Dar al monolito (SA compute) permiso roles/run.invoker sobre embedding-service
#   2. Redeploy del embedding-service con --no-allow-unauthenticated
#   (El monolito NO necesita redeploy aquí — ya tiene el código de auth)
#
# Rollback:
#   gcloud run services update retail-embedding-service \\
#     --region us-central1 --allow-unauthenticated
#   gcloud run services update retail-recommender \\
#     --set-env-vars EMBEDDING_AUTH_DISABLED=true

set -euo pipefail

PROJECT="retail-recommendations-449216"
REGION="us-central1"
EMBEDDING_SERVICE="retail-embedding-service"
MONOLITH_SERVICE="retail-recommender"
MONOLITH_SA="178362262166-compute@developer.gserviceaccount.com"

echo "============================================================"
echo "SETUP IAM AUTH — embedding-service service-to-service"
echo "============================================================"
echo ""

# ── Paso 1: Permiso IAM para que el monolito pueda invocar el embedding-service
echo "Paso 1/2 — Añadiendo roles/run.invoker a la SA del monolito..."
gcloud run services add-iam-policy-binding "$EMBEDDING_SERVICE" \
  --region "$REGION" \
  --project "$PROJECT" \
  --member "serviceAccount:${MONOLITH_SA}" \
  --role "roles/run.invoker"
echo "✅ Permiso IAM configurado"
echo ""

# Eliminar el binding de allUsers si existe (de deploys anteriores con --allow-unauthenticated)
echo "Eliminando acceso público (allUsers) si existe..."
gcloud run services remove-iam-policy-binding "$EMBEDDING_SERVICE" \
  --region "$REGION" \
  --project "$PROJECT" \
  --member "allUsers" \
  --role "roles/run.invoker" 2>/dev/null \
  && echo "✅ Acceso público eliminado" \
  || echo "ℹ️  allUsers no tenía binding (ya estaba limpio)"
echo ""

# ── Paso 2: Redeploy del embedding-service sin allow-unauthenticated
echo "Paso 2/2 — Redeploy del embedding-service (--no-allow-unauthenticated)..."
echo "          Construyendo desde source... (~3-4 min)"
cd src/api/services/embedding-service
gcloud run deploy "$EMBEDDING_SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT" \
  --memory 4Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 1 \
  --timeout 300 \
  --no-allow-unauthenticated \
  --ingress all \
  --no-cpu-throttling \
  --set-env-vars VISUAL_INDEX_BUCKET=retail-recommendations-449216-visual-index
cd ../../../..
echo "✅ Embedding-service redesplegado con autenticación IAM activada"
echo ""

echo "============================================================"
echo "VERIFICACIÓN"
echo "============================================================"
echo ""
echo "1. El embedding-service debe rechazar requests directas sin auth:"
echo "   curl -X GET https://retail-embedding-service-178362262166.us-central1.run.app/health"
echo "   → Esperado: 403 Forbidden"
echo ""
echo "2. El monolito sigue funcionando (añade auth automáticamente):"
echo "   curl --ssl-no-revoke https://retail-recommender-178362262166.us-central1.run.app/health"
echo "   → Esperado: {\"status\":\"healthy\",...}"
echo ""
echo "3. La búsqueda visual funciona a través del monolito:"
echo "   curl -X POST \\"
echo "     'https://retail-recommender-178362262166.us-central1.run.app/v1/mcp/visual-search' \\"
echo "     -H 'X-API-Key: 2fed9999056fab6dac5654238f0cae1c' \\"
echo "     -F 'file=@/tmp/test.jpg;type=image/jpeg' \\"
echo "     -F 'market_id=ES' -F 'top_k=8' --ssl-no-revoke"
echo "   → Esperado: {\"recommendations\":[...], \"total_found\":8}"
echo ""
echo "============================================================"
echo "ROLLBACK si algo falla"
echo "============================================================"
echo ""
echo "  gcloud run services update $EMBEDDING_SERVICE \\"
echo "    --region $REGION --allow-unauthenticated"
echo ""
echo "  gcloud run services update $MONOLITH_SERVICE \\"
echo "    --region $REGION --set-env-vars EMBEDDING_AUTH_DISABLED=true"
