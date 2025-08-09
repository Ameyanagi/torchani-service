#!/bin/bash
set -e

# Deployment script for TorchANI service to Kubernetes

NAMESPACE="torchani"
REGISTRY="${DOCKER_REGISTRY:-localhost:5000}"
VERSION="${VERSION:-latest}"

echo "🚀 Deploying TorchANI Service to Kubernetes"
echo "Registry: $REGISTRY"
echo "Version: $VERSION"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Check cluster connection
echo "📡 Checking cluster connection..."
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

# Check for GPU nodes
echo "🖥️ Checking for GPU nodes..."
GPU_NODES=$(kubectl get nodes -o json | jq -r '.items[] | select(.status.allocatable."nvidia.com/gpu" != null) | .metadata.name')
if [ -z "$GPU_NODES" ]; then
    echo "⚠️ Warning: No GPU nodes found in cluster. Deployment may fail."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ GPU nodes found: $GPU_NODES"
fi

# Build Docker images
echo "🔨 Building Docker images..."
docker build -t torchani-service:$VERSION .
docker build -t torchani-service:celery-$VERSION --target celery .

# Tag for registry
echo "🏷️ Tagging images..."
docker tag torchani-service:$VERSION $REGISTRY/torchani-service:$VERSION
docker tag torchani-service:celery-$VERSION $REGISTRY/torchani-service:celery-$VERSION

# Push to registry (skip if using local registry)
if [ "$REGISTRY" != "localhost:5000" ]; then
    echo "📤 Pushing images to registry..."
    docker push $REGISTRY/torchani-service:$VERSION
    docker push $REGISTRY/torchani-service:celery-$VERSION
fi

# Update image references in manifests
echo "📝 Updating manifest images..."
sed -i "s|image: torchani-service:latest|image: $REGISTRY/torchani-service:$VERSION|g" k8s/deployment.yaml
sed -i "s|image: torchani-service:celery|image: $REGISTRY/torchani-service:celery-$VERSION|g" k8s/deployment.yaml

# Create namespace if it doesn't exist
echo "📁 Creating namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Deploy to Kubernetes
echo "🚢 Deploying to Kubernetes..."
kubectl apply -f k8s/configmap.yaml -n $NAMESPACE
kubectl apply -f k8s/redis.yaml -n $NAMESPACE

# Wait for Redis to be ready
echo "⏳ Waiting for Redis to be ready..."
kubectl wait --for=condition=ready pod -l app=redis -n $NAMESPACE --timeout=120s

kubectl apply -f k8s/service.yaml -n $NAMESPACE
kubectl apply -f k8s/deployment.yaml -n $NAMESPACE

# Optional: Deploy ingress
read -p "Deploy ingress? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl apply -f k8s/ingress.yaml -n $NAMESPACE
fi

# Optional: Deploy HPA
read -p "Deploy Horizontal Pod Autoscaler? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl apply -f k8s/hpa.yaml -n $NAMESPACE
fi

# Wait for deployments to be ready
echo "⏳ Waiting for deployments to be ready..."
kubectl wait --for=condition=available deployment/torchani-api -n $NAMESPACE --timeout=300s

# Check deployment status
echo "📊 Deployment Status:"
kubectl get all -n $NAMESPACE

# Check GPU allocation
echo "🖥️ GPU Allocation:"
kubectl describe nodes | grep -A 5 "nvidia.com/gpu" || echo "No GPU information available"

# Test the service
echo "🧪 Testing service..."
POD=$(kubectl get pod -n $NAMESPACE -l app=torchani-api -o jsonpath='{.items[0].metadata.name}')
if [ ! -z "$POD" ]; then
    echo "Testing GPU availability in pod $POD..."
    kubectl exec -n $NAMESPACE $POD -- python -c "import torch; print('GPU Available:', torch.cuda.is_available())" || true
    
    echo "Testing health endpoint..."
    kubectl exec -n $NAMESPACE $POD -- curl -s http://localhost:8000/health || true
fi

echo "✅ Deployment complete!"
echo ""
echo "Access the service:"
echo "  kubectl port-forward -n $NAMESPACE service/torchani-api 8000:8000"
echo ""
echo "View logs:"
echo "  kubectl logs -n $NAMESPACE deployment/torchani-api"
echo "  kubectl logs -n $NAMESPACE deployment/celery-worker"
echo ""
echo "Monitor GPU usage:"
echo "  kubectl exec -n $NAMESPACE deployment/torchani-api -- nvidia-smi"