#!/bin/bash
# ─────────────────────────────────────────────────────────────
# ScoutIQ — Google Cloud Run Deployment Script
# Run: chmod +x scripts/deploy-gcp.sh && ./scripts/deploy-gcp.sh
# ─────────────────────────────────────────────────────────────

set -e

# ── Config — edit these ──────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="scoutiq-backend"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
MONGODB_URI="${MONGODB_URI:-}"          # Set your Atlas URI here
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

# ── Validation ───────────────────────────────────────────────
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "❌ ANTHROPIC_API_KEY is not set. Export it first:"
  echo "   export ANTHROPIC_API_KEY=your_key_here"
  exit 1
fi

if [ -z "$MONGODB_URI" ]; then
  echo "❌ MONGODB_URI is not set. For Cloud Run, use a MongoDB Atlas connection string:"
  echo "   export MONGODB_URI='mongodb+srv://user:pass@cluster.mongodb.net/scoutiq'"
  exit 1
fi

echo "🚀 Deploying ScoutIQ to Google Cloud Run"
echo "   Project:  $PROJECT_ID"
echo "   Region:   $REGION"
echo "   Service:  $SERVICE_NAME"
echo ""

# ── Step 1: Authenticate ─────────────────────────────────────
echo "🔐 Authenticating with Google Cloud..."
gcloud config set project "$PROJECT_ID"

# ── Step 2: Enable APIs ──────────────────────────────────────
echo "⚡ Enabling required APIs..."
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com \
  --quiet

# ── Step 3: Copy data into backend for build ─────────────────
echo "📦 Preparing build context..."
cp -r data backend/data 2>/dev/null || true

# ── Step 4: Build and push Docker image ─────────────────────
echo "🔨 Building Docker image..."
cd backend
gcloud builds submit \
  --tag "$IMAGE_NAME" \
  --timeout=10m \
  .
cd ..

# ── Step 5: Deploy to Cloud Run ──────────────────────────────
echo "☁️  Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_NAME" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 10 \
  --timeout 300 \
  --set-env-vars "MONGODB_URI=${MONGODB_URI},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},PORT=8080" \
  --port 8080 \
  --quiet

# ── Step 6: Get service URL ───────────────────────────────────
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --format "value(status.url)")

echo ""
echo "✅ Backend deployed successfully!"
echo "   URL: ${SERVICE_URL}"
echo ""
echo "📝 Next step: Update frontend/index.html"
echo "   Change the API const to your Cloud Run URL:"
echo "   const API = '${SERVICE_URL}';"
echo ""
echo "🌐 Then deploy frontend to Firebase Hosting or Cloud Storage:"
echo "   firebase deploy --only hosting"
echo "   (or just open frontend/index.html locally pointing to this URL)"
