# CI/CD Setup Checklist & Information Gathering

This document lists all the information you need to collect before setting up CI/CD.

## 1. GitHub Setup

### What You Need
- [ ] GitHub account
- [ ] GitHub Personal Access Token (PAT)
- [ ] Repository names

### How to Get It

#### Create GitHub Personal Access Token
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a name like "ArgoCD CI/CD"
4. Select scopes:
   - `repo` (Full control of private repositories)
   - `write:packages` (Upload packages to GitHub Package Registry)
   - `delete:packages` (Delete packages from GitHub Package Registry)
5. Click "Generate token"
6. **SAVE THIS TOKEN** - you won't see it again!

```bash
# Save it temporarily
echo "GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxxxxx" >> ~/.env.cicd
```

#### Create Repositories
```bash
# If you have GitHub CLI installed
gh repo create torchani-service --public
gh repo create k8s-manifests --public

# Or create them manually on GitHub.com
```

## 2. Kubernetes Cluster Information

### What You Need
- [ ] Kubernetes cluster access
- [ ] GPU node name/label
- [ ] Ingress domain
- [ ] Storage class name

### How to Get It

```bash
# Check cluster access
kubectl cluster-info
# Save the output

# List all nodes and check for GPU
kubectl get nodes --show-labels | grep -i gpu
# Note which nodes have GPU

# Check for NVIDIA GPU operator
kubectl get pods -n gpu-operator 2>/dev/null || \
kubectl get pods -n kube-system | grep nvidia

# Get storage classes
kubectl get storageclass
# Note the default or preferred storage class

# Check for ingress controller
kubectl get ingressclass
# Note the ingress class name (usually 'nginx')

# Check existing namespaces
kubectl get namespaces
```

Save this information:
```bash
cat >> ~/.env.cicd <<EOF
# Kubernetes Info
K8S_GPU_NODE_LABEL=nvidia.com/gpu
K8S_STORAGE_CLASS=standard
K8S_INGRESS_CLASS=nginx
K8S_INGRESS_DOMAIN=your-domain.com
EOF
```

## 3. ArgoCD Information

### What You Need
- [ ] ArgoCD installation status
- [ ] ArgoCD server URL
- [ ] ArgoCD admin password
- [ ] ArgoCD API token

### How to Get It

#### Check if ArgoCD is installed
```bash
kubectl get namespace argocd
kubectl get pods -n argocd
```

#### If ArgoCD is NOT installed
```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for it to be ready
kubectl wait --for=condition=available --timeout=600s \
  deployment/argocd-server -n argocd
```

#### Get ArgoCD Password
```bash
# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# Save it
echo "ARGOCD_INITIAL_PASSWORD=<password>" >> ~/.env.cicd
```

#### Access ArgoCD UI
```bash
# Port forward to access UI
kubectl port-forward svc/argocd-server -n argocd 8080:443 &

# Access at https://localhost:8080
# Username: admin
# Password: (from above)
```

#### Create ArgoCD API Token
```bash
# Install ArgoCD CLI if not installed
curl -sSL -o /usr/local/bin/argocd \
  https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x /usr/local/bin/argocd

# Login
argocd login localhost:8080 \
  --username admin \
  --password <initial-password> \
  --insecure

# Generate token
ARGOCD_TOKEN=$(argocd account generate-token)
echo "ARGOCD_TOKEN=$ARGOCD_TOKEN" >> ~/.env.cicd
```

#### Get ArgoCD Server URL
```bash
# If using port-forward
echo "ARGOCD_SERVER=localhost:8080" >> ~/.env.cicd

# If exposed via ingress
kubectl get ingress -n argocd
# Use the hostname from ingress
```

## 4. Docker Registry Information

### What You Need
- [ ] Registry choice (GitHub Container Registry recommended)
- [ ] Registry credentials

### How to Get It

#### Option A: GitHub Container Registry (Recommended)
```bash
# No additional setup needed if using GitHub Actions
# Images will be at: ghcr.io/<your-github-username>/<repo-name>
echo "DOCKER_REGISTRY=ghcr.io" >> ~/.env.cicd
echo "DOCKER_REGISTRY_USER=$GITHUB_USERNAME" >> ~/.env.cicd
```

#### Option B: Docker Hub
```bash
# Create account at hub.docker.com
# Create access token: Account Settings → Security → Access Tokens
echo "DOCKER_REGISTRY=docker.io" >> ~/.env.cicd
echo "DOCKER_REGISTRY_USER=<dockerhub-username>" >> ~/.env.cicd
echo "DOCKER_REGISTRY_PASSWORD=<access-token>" >> ~/.env.cicd
```

#### Option C: Private Registry
```bash
# Get from your admin
echo "DOCKER_REGISTRY=registry.example.com" >> ~/.env.cicd
echo "DOCKER_REGISTRY_USER=<username>" >> ~/.env.cicd
echo "DOCKER_REGISTRY_PASSWORD=<password>" >> ~/.env.cicd
```

## 5. Application Configuration

### What You Need
- [ ] Redis password (or generate one)
- [ ] Application domain
- [ ] SSL certificate method

### How to Get It

```bash
# Generate Redis password
REDIS_PASSWORD=$(openssl rand -base64 32)
echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> ~/.env.cicd

# Application domain (for ingress)
echo "APP_DOMAIN=torchani.your-domain.com" >> ~/.env.cicd

# SSL certificate (cert-manager or manual)
kubectl get clusterissuer
# If cert-manager is installed, note the issuer name
echo "CERT_ISSUER=letsencrypt-prod" >> ~/.env.cicd
```

## 6. Collect Everything

### Create Summary Script
```bash
cat > check-setup.sh <<'EOF'
#!/bin/bash

echo "=== CI/CD Setup Information Check ==="
echo ""

# Load environment
if [ -f ~/.env.cicd ]; then
    source ~/.env.cicd
fi

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check function
check_var() {
    if [ -z "${!1}" ]; then
        echo -e "${RED}✗${NC} $1 is not set"
        return 1
    else
        echo -e "${GREEN}✓${NC} $1 = ${!1}"
        return 0
    fi
}

echo "GitHub Configuration:"
check_var GITHUB_PAT
check_var GITHUB_USERNAME
echo ""

echo "Kubernetes Configuration:"
check_var K8S_GPU_NODE_LABEL
check_var K8S_STORAGE_CLASS
check_var K8S_INGRESS_CLASS
check_var K8S_INGRESS_DOMAIN
echo ""

echo "ArgoCD Configuration:"
check_var ARGOCD_SERVER
check_var ARGOCD_TOKEN
echo ""

echo "Docker Registry:"
check_var DOCKER_REGISTRY
check_var DOCKER_REGISTRY_USER
echo ""

echo "Application Configuration:"
check_var REDIS_PASSWORD
check_var APP_DOMAIN
check_var CERT_ISSUER
echo ""

echo "=== Kubernetes Cluster Check ==="
kubectl cluster-info &>/dev/null && echo -e "${GREEN}✓${NC} Kubernetes cluster accessible" || echo -e "${RED}✗${NC} Cannot access Kubernetes cluster"
kubectl get nodes -l "$K8S_GPU_NODE_LABEL" &>/dev/null && echo -e "${GREEN}✓${NC} GPU nodes found" || echo -e "${YELLOW}⚠${NC} No GPU nodes with label $K8S_GPU_NODE_LABEL"
kubectl get namespace argocd &>/dev/null && echo -e "${GREEN}✓${NC} ArgoCD namespace exists" || echo -e "${YELLOW}⚠${NC} ArgoCD not installed"
EOF

chmod +x check-setup.sh
./check-setup.sh
```

## 7. Configure GitHub Secrets

Once you have all the information, add it to your GitHub repository:

```bash
# Using GitHub CLI
cd torchani-service

# Add secrets
gh secret set ARGOCD_GITHUB_TOKEN --body "$GITHUB_PAT"
gh secret set ARGOCD_TOKEN --body "$ARGOCD_TOKEN"
gh secret set ARGOCD_SERVER --body "$ARGOCD_SERVER"

# If using Docker Hub or private registry
gh secret set DOCKER_REGISTRY_USER --body "$DOCKER_REGISTRY_USER"
gh secret set DOCKER_REGISTRY_PASSWORD --body "$DOCKER_REGISTRY_PASSWORD"
```

Or manually in GitHub:
1. Go to your repository
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Add each secret

## 8. Update Configuration Files

### Update manifests with your values:
```bash
# Update ingress domain
sed -i "s/api.cheminfuse.com/$APP_DOMAIN/g" torchani-service/k8s/ingress.yaml

# Update image registry
sed -i "s|ghcr.io/yourusername|$DOCKER_REGISTRY/$DOCKER_REGISTRY_USER|g" \
  k8s-manifests/overlays/*/kustomization.yaml

# Update ArgoCD application
sed -i "s|yourusername|$GITHUB_USERNAME|g" \
  torchani-service/argocd/application.yaml
```

## Summary Checklist

Before running the setup:

- [ ] GitHub PAT created with correct permissions
- [ ] Kubernetes cluster accessible via kubectl
- [ ] GPU nodes identified and labeled
- [ ] ArgoCD installed and accessible
- [ ] ArgoCD token generated
- [ ] Docker registry chosen and credentials ready
- [ ] Redis password generated
- [ ] Application domain decided
- [ ] All values saved in ~/.env.cicd

Once everything is checked, run:
```bash
cd torchani-service
./scripts/setup-cicd.sh
```