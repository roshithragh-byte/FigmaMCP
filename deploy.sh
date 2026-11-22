#!/usr/bin/env bash
set -euo pipefail

# Idempotent deployment script for figma-mcp-server on Google Cloud Run.
# Required environment variables:
#   PROJECT_ID         - Target Google Cloud project ID (falls back to gcloud config)
#   FIGMA_ACCESS_TOKEN - Figma Personal Access Token (required when creating/updating secret)

REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-figma-mcp-server}"
ARTIFACT_REPO="${ARTIFACT_REPO:-remote-mcp-servers}"
SECRET_NAME="${SECRET_NAME:-figma-access-token}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "ERROR: PROJECT_ID is not set and no default gcloud project is configured." >&2
  echo "Export PROJECT_ID=<your-gcp-project-id> and re-run." >&2
  exit 1
fi

echo "==> Using PROJECT_ID=${PROJECT_ID}, REGION=${REGION}, SERVICE_NAME=${SERVICE_NAME}"

# 1. Enable required Google Cloud APIs (idempotent)
echo "==> Enabling required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project="${PROJECT_ID}"

# 2. Store FIGMA_ACCESS_TOKEN in Secret Manager and grant runtime SA access
if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  if [[ -z "${FIGMA_ACCESS_TOKEN:-}" ]]; then
    echo "ERROR: Secret '${SECRET_NAME}' does not exist and FIGMA_ACCESS_TOKEN is not set." >&2
    exit 1
  fi
  echo "==> Creating Secret Manager secret '${SECRET_NAME}'..."
  gcloud secrets create "${SECRET_NAME}" \
    --replication-policy="automatic" \
    --project="${PROJECT_ID}"
fi

if [[ -n "${FIGMA_ACCESS_TOKEN:-}" ]]; then
  echo "==> Adding new secret version to '${SECRET_NAME}'..."
  printf '%s' "${FIGMA_ACCESS_TOKEN}" | gcloud secrets versions add "${SECRET_NAME}" \
    --data-file=- \
    --project="${PROJECT_ID}" >/dev/null
fi

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${RUNTIME_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"

echo "==> Granting roles/secretmanager.secretAccessor on '${SECRET_NAME}' to ${RUNTIME_SA}..."
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="${PROJECT_ID}" >/dev/null

# 3. Create Artifact Registry Docker repository if absent (idempotent)
if ! gcloud artifacts repositories describe "${ARTIFACT_REPO}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "==> Creating Artifact Registry repository '${ARTIFACT_REPO}' in ${REGION}..."
  gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format="docker" \
    --location="${REGION}" \
    --description="Docker repository for remote MCP servers" \
    --project="${PROJECT_ID}"
else
  echo "==> Artifact Registry repository '${ARTIFACT_REPO}' already exists."
fi

# 4. Build and push container image via Cloud Build
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE_NAME}:${IMAGE_TAG}"
echo "==> Building and pushing image ${IMAGE_URI}..."
gcloud builds submit \
  --region="${REGION}" \
  --tag="${IMAGE_URI}" \
  --project="${PROJECT_ID}" \
  .

# 5. Deploy to Cloud Run with IAM auth enforced, max-instances=1 for cache coherence, and secret mounted
echo "==> Deploying '${SERVICE_NAME}' to Cloud Run..."
READ_ONLY_FLAG="${FIGMA_READ_ONLY:-true}"
ALLOWED_KEYS="${FIGMA_ALLOWED_FILE_KEYS:-}"

ENV_VARS="^@^FIGMA_READ_ONLY=${READ_ONLY_FLAG}"
if [[ -n "${ALLOWED_KEYS}" ]]; then
  ENV_VARS="${ENV_VARS}@FIGMA_ALLOWED_FILE_KEYS=${ALLOWED_KEYS}"
fi

gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --service-account="${RUNTIME_SA}" \
  --max-instances=1 \
  --no-allow-unauthenticated \
  --set-env-vars="${ENV_VARS}" \
  --set-secrets="FIGMA_ACCESS_TOKEN=${SECRET_NAME}:latest"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format='value(status.url)')"

cat <<EOF

Deployment complete!
  Service URL: ${SERVICE_URL}
  MCP Endpoint (via proxy): http://localhost:8080/mcp

To connect local MCP clients securely via IAM:
  1. Ensure your identity has roles/run.invoker on ${SERVICE_NAME}:
     gcloud run services add-iam-policy-binding ${SERVICE_NAME} \\
       --region=${REGION} \\
       --project=${PROJECT_ID} \\
       --member="user:\$(gcloud config get-value account)" \\
       --role="roles/run.invoker"

  2. Start the authenticated local proxy:
     gcloud run services proxy ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID} --port=8080

  3. Point your MCP client (Streamable HTTP) to:
     http://localhost:8080/mcp
EOF
