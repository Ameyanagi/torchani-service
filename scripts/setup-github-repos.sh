#!/bin/bash

# Setup GitHub repositories and secrets for Ameyanagi

set -e

# Configuration
GITHUB_USER="Ameyanagi"
# GitHub token should be set as environment variable
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
ARGOCD_SERVER="argocd.ameyanagi.com"

if [ -z "$GITHUB_TOKEN" ]; then
    log_error "GITHUB_TOKEN environment variable is not set"
    log_info "Please export GITHUB_TOKEN=your_token before running this script"
    exit 1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "======================================"
echo "   GitHub Repository Setup"
echo "======================================"
echo ""

# Step 1: Create torchani-service repository
log_info "Creating torchani-service repository..."

cd /home/ryuichi/dev/cheminfuse/torchani-service

# Initialize git if not already
if [ ! -d .git ]; then
    git init
    git add .
    git commit -m "Initial commit: TorchANI GPU-optimized service"
fi

# Create GitHub repository
if gh repo view Ameyanagi/torchani-service &>/dev/null; then
    log_info "Repository torchani-service already exists"
else
    gh repo create torchani-service --public --description "GPU-optimized molecular structure optimization service"
fi

# Add remote if not exists
if ! git remote | grep -q origin; then
    git remote add origin https://github.com/Ameyanagi/torchani-service.git
fi

# Push to GitHub
log_info "Pushing to GitHub..."
git branch -M main
git push -u origin main || log_warn "Already pushed or push failed"

# Step 2: Set GitHub secrets
log_info "Setting GitHub secrets..."

gh secret set ARGOCD_GITHUB_TOKEN --body "$GITHUB_TOKEN"
gh secret set ARGOCD_SERVER --body "$ARGOCD_SERVER"

# Note: ARGOCD_TOKEN needs to be set manually after generating it
log_warn "Remember to set ARGOCD_TOKEN after generating it from ArgoCD"

echo ""

# Step 3: Create k8s-manifests repository
log_info "Creating k8s-manifests repository..."

cd /home/ryuichi/dev/cheminfuse

if [ ! -d k8s-manifests/.git ]; then
    cd k8s-manifests
    git init
    git add .
    git commit -m "Initial commit: Kubernetes manifests for torchani-service"
    
    # Create GitHub repository
    if gh repo view Ameyanagi/k8s-manifests &>/dev/null; then
        log_info "Repository k8s-manifests already exists"
    else
        gh repo create k8s-manifests --public --description "Kubernetes manifests for GitOps"
    fi
    
    # Add remote and push
    if ! git remote | grep -q origin; then
        git remote add origin https://github.com/Ameyanagi/k8s-manifests.git
    fi
    
    git branch -M main
    git push -u origin main || log_warn "Already pushed or push failed"
else
    log_info "k8s-manifests repository already initialized"
fi

echo ""
echo "======================================"
echo "   Next Steps"
echo "======================================"
echo ""

# Step 4: Get ArgoCD password
log_info "Getting ArgoCD initial password..."
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d 2>/dev/null || echo "")

if [ -n "$ARGOCD_PASSWORD" ]; then
    echo "ArgoCD admin password: $ARGOCD_PASSWORD"
    echo ""
    echo "Generate ArgoCD token:"
    echo "1. Login to ArgoCD:"
    echo "   argocd login $ARGOCD_SERVER --username admin --password '$ARGOCD_PASSWORD'"
    echo ""
    echo "2. Generate token:"
    echo "   argocd account generate-token"
    echo ""
    echo "3. Set the token as GitHub secret:"
    echo "   cd /home/ryuichi/dev/cheminfuse/torchani-service"
    echo "   gh secret set ARGOCD_TOKEN --body '<token>'"
else
    log_error "Could not retrieve ArgoCD password. Check if ArgoCD is installed."
fi

echo ""
echo "======================================"
echo "   GPU Node Fix Required"
echo "======================================"
echo ""
log_warn "IMPORTANT: The GPU node (amk-gpu-worker-01) needs NVIDIA drivers installed!"
echo ""
echo "SSH into the node and run:"
echo "  sudo apt-get update"
echo "  sudo apt-get install -y nvidia-driver-535"
echo "  # Install NVIDIA Container Toolkit"
echo "  # (See ENVIRONMENT_STATUS.md for full commands)"
echo ""

echo "======================================"
echo "   Repository URLs"
echo "======================================"
echo ""
echo "Main repository: https://github.com/Ameyanagi/torchani-service"
echo "Manifests repository: https://github.com/Ameyanagi/k8s-manifests"
echo ""
echo "To trigger CI/CD:"
echo "  cd /home/ryuichi/dev/cheminfuse/torchani-service"
echo "  git add ."
echo "  git commit -m 'Update configuration'"
echo "  git push"
echo ""
log_info "Setup complete! (except for GPU drivers and ArgoCD token)"