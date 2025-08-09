# Environment Status Check

## ✅ Kubernetes Cluster
- **Status**: Connected and accessible
- **Control Plane**: https://192.168.1.165:6443
- **Context**: Available

## ⚠️ GPU Node
- **Node Name**: amk-gpu-worker-01
- **Status**: Ready
- **Label**: nvidia.com/gpu=true
- **Issue**: NVIDIA drivers/toolkit not properly configured
  - NVIDIA device plugin is running but can't detect GPUs
  - Error: "libnvidia-ml.so.1: cannot open shared object file"
  - **Action Required**: Install NVIDIA drivers and container toolkit on the node

### Fix GPU Node
SSH into amk-gpu-worker-01 and run:
```bash
# Install NVIDIA drivers
sudo apt-get update
sudo apt-get install -y nvidia-driver-535

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure containerd
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd
sudo systemctl restart kubelet

# Verify
nvidia-smi
```

## ✅ ArgoCD
- **Status**: Installed and running
- **Namespace**: argocd
- **Pods**: 8 pods running
- **Ingress**: argocd.ameyanagi.com

## ✅ Storage
- **Default StorageClass**: local-path
- **Provisioner**: rancher.io/local-path
- **Type**: Local storage (good for development)

## ✅ Ingress
- **IngressClass**: nginx
- **Controller**: k8s.io/ingress-nginx
- **Domain**: *.ameyanagi.com
- **Working Examples**: 
  - argocd.ameyanagi.com
  - hub.ameyanagi.com
  - auth.ameyanagi.com

## ✅ GitHub
- **CLI Status**: Authenticated
- **Account**: Ameyanagi
- **Token**: Active

## 📝 Configuration Summary

Based on your environment, here are the values to use:

```bash
# Kubernetes
K8S_GPU_NODE_LABEL="nvidia.com/gpu"
K8S_STORAGE_CLASS="local-path"
K8S_INGRESS_CLASS="nginx"
K8S_INGRESS_DOMAIN="ameyanagi.com"

# ArgoCD
ARGOCD_SERVER="argocd.ameyanagi.com"
ARGOCD_NAMESPACE="argocd"

# GitHub
GITHUB_USERNAME="Ameyanagi"
DOCKER_REGISTRY="ghcr.io"
DOCKER_REGISTRY_USER="Ameyanagi"

# Application
APP_DOMAIN="torchani.ameyanagi.com"
```

## 🚀 Next Steps

1. **Fix GPU Node** (Critical):
   ```bash
   # SSH to amk-gpu-worker-01 and install NVIDIA drivers + container toolkit
   # See commands above
   ```

2. **Get ArgoCD Password**:
   ```bash
   kubectl -n argocd get secret argocd-initial-admin-secret \
     -o jsonpath="{.data.password}" | base64 -d
   ```

3. **Generate ArgoCD Token**:
   ```bash
   # Port forward if needed
   kubectl port-forward svc/argocd-server -n argocd 8080:443 &
   
   # Login
   argocd login argocd.ameyanagi.com
   # Or if using port-forward: argocd login localhost:8080
   
   # Generate token
   argocd account generate-token
   ```

4. **Create GitHub PAT**:
   - Go to https://github.com/settings/tokens
   - Create token with: repo, write:packages, delete:packages

5. **Set GitHub Secrets**:
   ```bash
   cd /home/ryuichi/dev/cheminfuse/torchani-service
   
   gh secret set ARGOCD_GITHUB_TOKEN --body "<your-github-pat>"
   gh secret set ARGOCD_TOKEN --body "<argocd-token>"
   gh secret set ARGOCD_SERVER --body "argocd.ameyanagi.com"
   ```

6. **Update Manifests**:
   ```bash
   # Update ingress domain
   sed -i "s/api.cheminfuse.com/torchani.ameyanagi.com/g" k8s/ingress.yaml
   
   # Update image registry
   sed -i "s|ghcr.io/yourusername|ghcr.io/Ameyanagi|g" \
     ../k8s-manifests/overlays/*/kustomization.yaml
   
   # Update ArgoCD application
   sed -i "s|yourusername|Ameyanagi|g" argocd/application.yaml
   ```

## ⚠️ Issues to Address

1. **GPU Support**: The NVIDIA device plugin can't detect GPUs. This needs to be fixed before deploying the torchani-service.

2. **Storage**: You're using local-path storage which is fine for development but consider using a network storage solution for production.

3. **SSL Certificates**: Check if cert-manager is installed:
   ```bash
   kubectl get clusterissuer
   ```

## 🎯 Ready Components
- ✅ Kubernetes cluster
- ✅ ArgoCD
- ✅ Ingress controller
- ✅ GitHub authentication
- ✅ Domain (ameyanagi.com)

## 🔧 Needs Setup
- ❌ GPU drivers on node
- ❌ ArgoCD token
- ❌ GitHub PAT
- ❌ GitHub secrets