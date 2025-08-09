#!/bin/bash

# Setup script for CI/CD with GitHub Actions and ArgoCD

set -e

echo "🚀 TorchANI Service CI/CD Setup"
echo "================================"

# Configuration
GITHUB_ORG=${GITHUB_ORG:-"yourusername"}
GITHUB_REPO="torchani-service"
MANIFESTS_REPO="k8s-manifests"
ARGOCD_NAMESPACE="argocd"
APP_NAMESPACE="torchani"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl first."
        exit 1
    fi
    
    # Check argocd CLI
    if ! command -v argocd &> /dev/null; then
        log_warn "argocd CLI not found. Installing..."
        curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
        chmod +x /usr/local/bin/argocd
    fi
    
    # Check gh CLI
    if ! command -v gh &> /dev/null; then
        log_warn "GitHub CLI not found. Some features will be skipped."
    fi
    
    log_info "Prerequisites check complete."
}

# Install ArgoCD
install_argocd() {
    log_info "Installing ArgoCD..."
    
    # Create namespace
    kubectl create namespace $ARGOCD_NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    # Install ArgoCD
    kubectl apply -n $ARGOCD_NAMESPACE -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
    
    # Wait for ArgoCD to be ready
    log_info "Waiting for ArgoCD to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n $ARGOCD_NAMESPACE
    
    log_info "ArgoCD installed successfully."
}

# Configure ArgoCD
configure_argocd() {
    log_info "Configuring ArgoCD..."
    
    # Get initial admin password
    ARGOCD_PASSWORD=$(kubectl -n $ARGOCD_NAMESPACE get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
    
    log_info "ArgoCD admin password: $ARGOCD_PASSWORD"
    log_warn "Please save this password and change it after login."
    
    # Port forward ArgoCD server
    log_info "Starting port forward to ArgoCD server..."
    kubectl port-forward svc/argocd-server -n $ARGOCD_NAMESPACE 8080:443 &
    ARGOCD_PF_PID=$!
    sleep 5
    
    # Login to ArgoCD
    argocd login localhost:8080 --username admin --password "$ARGOCD_PASSWORD" --insecure
    
    # Create project
    log_info "Creating ArgoCD project..."
    kubectl apply -f argocd/appproject.yaml
    
    # Add repository
    log_info "Adding Git repository..."
    argocd repo add "https://github.com/$GITHUB_ORG/$MANIFESTS_REPO" --type git
    
    # Create applications
    log_info "Creating ArgoCD applications..."
    kubectl apply -f argocd/application.yaml
    
    # Generate API token
    log_info "Generating ArgoCD API token..."
    ARGOCD_TOKEN=$(argocd account generate-token)
    echo "ARGOCD_TOKEN=$ARGOCD_TOKEN" > .env.argocd
    log_info "ArgoCD token saved to .env.argocd"
    
    # Kill port forward
    kill $ARGOCD_PF_PID
    
    log_info "ArgoCD configuration complete."
}

# Setup GitHub repository
setup_github() {
    log_info "Setting up GitHub repository..."
    
    if ! command -v gh &> /dev/null; then
        log_warn "GitHub CLI not found. Please manually configure the following secrets:"
        echo "  - ARGOCD_GITHUB_TOKEN: Personal access token with repo access"
        echo "  - ARGOCD_TOKEN: ArgoCD API token (see .env.argocd)"
        echo "  - ARGOCD_SERVER: Your ArgoCD server URL"
        return
    fi
    
    # Check if logged in
    if ! gh auth status &> /dev/null; then
        log_info "Please login to GitHub:"
        gh auth login
    fi
    
    # Create secrets
    log_info "Creating GitHub secrets..."
    
    # Read ArgoCD token
    if [ -f .env.argocd ]; then
        source .env.argocd
        gh secret set ARGOCD_TOKEN --body "$ARGOCD_TOKEN"
    fi
    
    # Prompt for GitHub PAT
    read -p "Enter GitHub Personal Access Token with repo access: " GITHUB_PAT
    gh secret set ARGOCD_GITHUB_TOKEN --body "$GITHUB_PAT"
    
    # Prompt for ArgoCD server
    read -p "Enter ArgoCD server URL (e.g., argocd.example.com): " ARGOCD_SERVER
    gh secret set ARGOCD_SERVER --body "$ARGOCD_SERVER"
    
    log_info "GitHub secrets configured."
}

# Create manifests repository structure
create_manifests_repo() {
    log_info "Creating k8s-manifests repository structure..."
    
    # Create directory if it doesn't exist
    if [ ! -d "../$MANIFESTS_REPO" ]; then
        mkdir -p "../$MANIFESTS_REPO"
        cd "../$MANIFESTS_REPO"
        git init
        
        # Copy manifests structure
        cp -r "../$GITHUB_REPO/k8s-manifests/" .
        
        # Create README
        cat > README.md <<EOF
# Kubernetes Manifests

This repository contains Kubernetes manifests for the TorchANI service.

## Structure

- \`base/\`: Base Kubernetes resources
- \`overlays/staging/\`: Staging environment customizations
- \`overlays/production/\`: Production environment customizations

## Usage

This repository is monitored by ArgoCD for GitOps deployments.

Any changes pushed to this repository will be automatically synced to the cluster.
EOF
        
        git add .
        git commit -m "Initial manifests setup"
        
        log_info "Please create the $MANIFESTS_REPO repository on GitHub and push this code:"
        echo "  cd ../$MANIFESTS_REPO"
        echo "  gh repo create $MANIFESTS_REPO --public"
        echo "  git remote add origin https://github.com/$GITHUB_ORG/$MANIFESTS_REPO.git"
        echo "  git push -u origin main"
        
        cd "../$GITHUB_REPO"
    else
        log_info "Manifests repository already exists."
    fi
}

# Setup GPU node
setup_gpu_node() {
    log_info "Checking GPU node configuration..."
    
    # Check for GPU nodes
    GPU_NODES=$(kubectl get nodes -o json | jq -r '.items[] | select(.status.allocatable."nvidia.com/gpu" != null) | .metadata.name')
    
    if [ -z "$GPU_NODES" ]; then
        log_warn "No GPU nodes found. Please ensure NVIDIA device plugin is installed:"
        echo "kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml"
    else
        log_info "GPU nodes found: $GPU_NODES"
    fi
}

# Main setup flow
main() {
    echo ""
    log_info "Starting CI/CD setup..."
    echo ""
    
    check_prerequisites
    
    # Ask what to setup
    echo "What would you like to setup?"
    echo "1) ArgoCD installation"
    echo "2) ArgoCD configuration"
    echo "3) GitHub repository"
    echo "4) Manifests repository"
    echo "5) GPU node check"
    echo "6) Everything"
    read -p "Enter choice [1-6]: " choice
    
    case $choice in
        1)
            install_argocd
            ;;
        2)
            configure_argocd
            ;;
        3)
            setup_github
            ;;
        4)
            create_manifests_repo
            ;;
        5)
            setup_gpu_node
            ;;
        6)
            install_argocd
            configure_argocd
            setup_github
            create_manifests_repo
            setup_gpu_node
            ;;
        *)
            log_error "Invalid choice"
            exit 1
            ;;
    esac
    
    echo ""
    log_info "Setup complete!"
    echo ""
    echo "Next steps:"
    echo "1. Update image registry in manifests if not using ghcr.io"
    echo "2. Configure production domain in ingress"
    echo "3. Setup monitoring and alerts"
    echo "4. Configure backup strategy"
    echo ""
    echo "To deploy the application:"
    echo "  git push origin main  # Triggers CI/CD pipeline"
    echo ""
    echo "To access ArgoCD UI:"
    echo "  kubectl port-forward svc/argocd-server -n argocd 8080:443"
    echo "  Open https://localhost:8080"
}

# Run main function
main