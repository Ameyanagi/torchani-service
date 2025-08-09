# Kubernetes Deployment for TorchANI Service

This directory contains Kubernetes manifests for deploying the TorchANI service to your existing cluster with GPU support.

## Prerequisites

- Kubernetes cluster with GPU node already configured
- NVIDIA GPU operator or device plugin installed
- kubectl configured to access your cluster
- Docker registry accessible from cluster (or local images)

## Quick Deployment

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create ConfigMap and Secrets
kubectl apply -f configmap.yaml

# Deploy Redis
kubectl apply -f redis.yaml

# Create services
kubectl apply -f service.yaml

# Deploy applications
kubectl apply -f deployment.yaml

# Set up ingress (optional)
kubectl apply -f ingress.yaml

# Configure autoscaling (optional)
kubectl apply -f hpa.yaml
```

Or deploy all at once:
```bash
kubectl apply -f .
```

## Verify GPU Node

Check if your GPU node is ready:
```bash
# List nodes with GPU
kubectl get nodes -L nvidia.com/gpu

# Check GPU allocatable resources
kubectl describe nodes | grep -A 5 "nvidia.com/gpu"

# Verify NVIDIA device plugin
kubectl get pods -n kube-system | grep nvidia
```

## Building and Pushing Images

```bash
# Build the Docker image
cd ../
docker build -t torchani-service:latest .
docker build -t torchani-service:celery --target celery .

# Tag for your registry
docker tag torchani-service:latest your-registry/torchani-service:latest
docker tag torchani-service:celery your-registry/torchani-service:celery

# Push to registry
docker push your-registry/torchani-service:latest
docker push your-registry/torchani-service:celery

# Update deployment with your registry
kubectl set image deployment/torchani-api api=your-registry/torchani-service:latest -n torchani
kubectl set image deployment/celery-worker worker=your-registry/torchani-service:celery -n torchani
```

## Storage Configuration

The deployment uses `emptyDir` volumes by default. For production, you should use PersistentVolumeClaims:

```bash
# Create PVCs (uncomment in pvc.yaml and adjust storage class)
kubectl apply -f pvc.yaml

# Update deployment to use PVCs instead of emptyDir
# Edit deployment.yaml and change volumes section
```

## Monitoring

Check deployment status:
```bash
# Check all resources
kubectl get all -n torchani

# Check GPU usage
kubectl exec -n torchani deployment/torchani-api -- nvidia-smi

# View logs
kubectl logs -n torchani deployment/torchani-api
kubectl logs -n torchani deployment/celery-worker

# Check Redis
kubectl exec -n torchani statefulset/redis -- redis-cli ping
```

## Scaling

The HPA will automatically scale based on GPU/CPU usage:
```bash
# Check HPA status
kubectl get hpa -n torchani

# Manual scaling (if needed)
kubectl scale deployment/torchani-api --replicas=2 -n torchani
```

Note: Scaling is limited by available GPU resources. Each pod requests 1 GPU.

## Troubleshooting

### GPU Not Available
```bash
# Check if pod is scheduled on GPU node
kubectl get pod -n torchani -o wide

# Check pod events
kubectl describe pod -n torchani <pod-name>

# Verify GPU in container
kubectl exec -n torchani deployment/torchani-api -- python -c "import torch; print(torch.cuda.is_available())"
```

### Redis Connection Issues
```bash
# Check Redis pod
kubectl get pod -n torchani -l app=redis

# Test Redis connection
kubectl run redis-test --rm -it --image=redis:alpine -- redis-cli -h redis.torchani.svc.cluster.local ping
```

### Memory Issues
```bash
# Check resource usage
kubectl top pods -n torchani

# Check GPU memory
kubectl exec -n torchani deployment/torchani-api -- nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

## Configuration

Edit `configmap.yaml` to adjust:
- GPU memory limits and thresholds
- Model TTL settings
- Redis configuration
- Performance parameters

## Security Notes

1. Create secrets for sensitive data:
```bash
kubectl create secret generic torchani-secrets \
  --from-literal=redis-password=your-password \
  -n torchani
```

2. Use NetworkPolicies to restrict traffic (optional)
3. Configure RBAC for service accounts
4. Use sealed-secrets or external secrets operator for production

## Cleanup

To remove all resources:
```bash
kubectl delete namespace torchani
```