#!/bin/bash

# Script to check all prerequisites and gather information for CI/CD setup

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Environment file
ENV_FILE="$HOME/.env.cicd"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

prompt_value() {
    local var_name=$1
    local prompt_text=$2
    local default_value=$3
    local current_value=${!var_name}
    
    if [ -n "$current_value" ]; then
        echo -e "${GREEN}✓${NC} $var_name already set to: $current_value"
        read -p "Keep this value? (Y/n): " keep
        if [[ $keep =~ ^[Nn]$ ]]; then
            current_value=""
        else
            return 0
        fi
    fi
    
    if [ -z "$current_value" ]; then
        if [ -n "$default_value" ]; then
            read -p "$prompt_text [$default_value]: " input_value
            input_value=${input_value:-$default_value}
        else
            read -p "$prompt_text: " input_value
        fi
        export $var_name="$input_value"
        echo "$var_name=\"$input_value\"" >> "$ENV_FILE"
    fi
}

# Load existing environment
if [ -f "$ENV_FILE" ]; then
    log_info "Loading existing configuration from $ENV_FILE"
    source "$ENV_FILE"
fi

echo ""
echo "======================================"
echo "   CI/CD Prerequisites Check"
echo "======================================"
echo ""

# 1. Check Kubernetes
echo "1. Kubernetes Cluster"
echo "---------------------"
if kubectl cluster-info &>/dev/null; then
    log_success "Kubernetes cluster is accessible"
    
    # Get cluster info
    CLUSTER_NAME=$(kubectl config current-context)
    log_info "Current context: $CLUSTER_NAME"
    
    # Check for GPU nodes
    GPU_NODES=$(kubectl get nodes -o json | jq -r '.items[] | select(.status.allocatable."nvidia.com/gpu" != null) | .metadata.name' 2>/dev/null || true)
    if [ -n "$GPU_NODES" ]; then
        log_success "GPU nodes found:"
        echo "$GPU_NODES" | while read node; do
            echo "  - $node"
        done
        
        # Get GPU label
        GPU_LABEL=$(kubectl get nodes -o json | jq -r '.items[0].metadata.labels | to_entries[] | select(.value == "true") | select(.key | contains("gpu")) | .key' | head -1)
        prompt_value K8S_GPU_NODE_LABEL "GPU node label" "${GPU_LABEL:-nvidia.com/gpu}"
    else
        log_warn "No GPU nodes found in cluster"
        log_info "Make sure NVIDIA device plugin is installed"
    fi
    
    # Get storage class
    DEFAULT_SC=$(kubectl get storageclass -o json | jq -r '.items[] | select(.metadata.annotations."storageclass.kubernetes.io/is-default-class" == "true") | .metadata.name')
    prompt_value K8S_STORAGE_CLASS "Storage class" "$DEFAULT_SC"
    
    # Get ingress class
    INGRESS_CLASS=$(kubectl get ingressclass -o json | jq -r '.items[0].metadata.name' 2>/dev/null || echo "nginx")
    prompt_value K8S_INGRESS_CLASS "Ingress class" "$INGRESS_CLASS"
    
else
    log_error "Cannot access Kubernetes cluster"
    log_info "Please ensure kubectl is configured correctly"
    exit 1
fi

echo ""

# 2. Check ArgoCD
echo "2. ArgoCD"
echo "---------"
if kubectl get namespace argocd &>/dev/null; then
    log_success "ArgoCD namespace exists"
    
    # Check if ArgoCD is running
    if kubectl get deployment argocd-server -n argocd &>/dev/null; then
        log_success "ArgoCD server is deployed"
        
        # Get initial password if available
        if kubectl get secret argocd-initial-admin-secret -n argocd &>/dev/null; then
            ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
            log_info "ArgoCD initial admin password retrieved"
            echo "ARGOCD_INITIAL_PASSWORD=\"$ARGOCD_PASSWORD\"" >> "$ENV_FILE"
        fi
        
        prompt_value ARGOCD_SERVER "ArgoCD server URL" "localhost:8080"
        
        if [ -z "$ARGOCD_TOKEN" ]; then
            log_warn "ArgoCD token not set. You'll need to generate one."
            echo "Run: argocd account generate-token"
        fi
    else
        log_warn "ArgoCD server not running"
    fi
else
    log_warn "ArgoCD not installed"
    read -p "Would you like to install ArgoCD now? (y/N): " install_argo
    if [[ $install_argo =~ ^[Yy]$ ]]; then
        kubectl create namespace argocd
        kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
        log_info "ArgoCD installation started. Please wait for pods to be ready."
    fi
fi

echo ""

# 3. Check GitHub
echo "3. GitHub Configuration"
echo "----------------------"
if command -v gh &>/dev/null; then
    if gh auth status &>/dev/null; then
        log_success "GitHub CLI is authenticated"
        GITHUB_USERNAME=$(gh api user --jq .login)
        export GITHUB_USERNAME
        echo "GITHUB_USERNAME=\"$GITHUB_USERNAME\"" >> "$ENV_FILE"
        log_info "GitHub username: $GITHUB_USERNAME"
    else
        log_warn "GitHub CLI not authenticated"
        log_info "Run: gh auth login"
    fi
else
    log_warn "GitHub CLI not installed"
    prompt_value GITHUB_USERNAME "GitHub username"
fi

if [ -z "$GITHUB_PAT" ]; then
    log_warn "GitHub Personal Access Token not set"
    echo ""
    echo "To create a GitHub PAT:"
    echo "1. Go to https://github.com/settings/tokens"
    echo "2. Click 'Generate new token (classic)'"
    echo "3. Select scopes: repo, write:packages, delete:packages"
    echo ""
    prompt_value GITHUB_PAT "GitHub Personal Access Token"
fi

echo ""

# 4. Docker Registry
echo "4. Docker Registry"
echo "-----------------"
echo "Choose registry:"
echo "1) GitHub Container Registry (ghcr.io) - Recommended"
echo "2) Docker Hub"
echo "3) Private Registry"
read -p "Enter choice [1-3]: " registry_choice

case $registry_choice in
    1)
        export DOCKER_REGISTRY="ghcr.io"
        export DOCKER_REGISTRY_USER="$GITHUB_USERNAME"
        echo "DOCKER_REGISTRY=\"ghcr.io\"" >> "$ENV_FILE"
        echo "DOCKER_REGISTRY_USER=\"$GITHUB_USERNAME\"" >> "$ENV_FILE"
        log_success "Using GitHub Container Registry"
        ;;
    2)
        prompt_value DOCKER_REGISTRY "Docker registry" "docker.io"
        prompt_value DOCKER_REGISTRY_USER "Docker Hub username"
        prompt_value DOCKER_REGISTRY_PASSWORD "Docker Hub access token"
        ;;
    3)
        prompt_value DOCKER_REGISTRY "Registry URL"
        prompt_value DOCKER_REGISTRY_USER "Registry username"
        prompt_value DOCKER_REGISTRY_PASSWORD "Registry password"
        ;;
esac

echo ""

# 5. Application Configuration
echo "5. Application Configuration"
echo "---------------------------"

# Generate Redis password if not set
if [ -z "$REDIS_PASSWORD" ]; then
    REDIS_PASSWORD=$(openssl rand -base64 32)
    export REDIS_PASSWORD
    echo "REDIS_PASSWORD=\"$REDIS_PASSWORD\"" >> "$ENV_FILE"
    log_success "Generated Redis password"
fi

prompt_value APP_DOMAIN "Application domain" "torchani.local"
prompt_value K8S_INGRESS_DOMAIN "Kubernetes ingress domain" "$APP_DOMAIN"

# Check for cert-manager
if kubectl get clusterissuer &>/dev/null; then
    CERT_ISSUERS=$(kubectl get clusterissuer -o json | jq -r '.items[].metadata.name')
    if [ -n "$CERT_ISSUERS" ]; then
        log_success "cert-manager is installed"
        echo "Available issuers:"
        echo "$CERT_ISSUERS" | while read issuer; do
            echo "  - $issuer"
        done
        prompt_value CERT_ISSUER "Certificate issuer" "letsencrypt-prod"
    fi
else
    log_info "cert-manager not found. Manual SSL certificate management required."
fi

echo ""

# 6. Summary
echo "======================================"
echo "   Configuration Summary"
echo "======================================"
echo ""

echo "GitHub:"
echo "  Username: ${GITHUB_USERNAME:-NOT SET}"
echo "  PAT: ${GITHUB_PAT:+SET}"
echo ""

echo "Kubernetes:"
echo "  Context: $CLUSTER_NAME"
echo "  GPU Label: ${K8S_GPU_NODE_LABEL:-NOT SET}"
echo "  Storage Class: ${K8S_STORAGE_CLASS:-NOT SET}"
echo "  Ingress Class: ${K8S_INGRESS_CLASS:-NOT SET}"
echo ""

echo "ArgoCD:"
echo "  Server: ${ARGOCD_SERVER:-NOT SET}"
echo "  Token: ${ARGOCD_TOKEN:+SET}"
echo ""

echo "Docker Registry:"
echo "  Registry: ${DOCKER_REGISTRY:-NOT SET}"
echo "  User: ${DOCKER_REGISTRY_USER:-NOT SET}"
echo ""

echo "Application:"
echo "  Domain: ${APP_DOMAIN:-NOT SET}"
echo "  Redis Password: ${REDIS_PASSWORD:+SET}"
echo ""

echo "Configuration saved to: $ENV_FILE"
echo ""

# Check if all required variables are set
missing=0
for var in GITHUB_USERNAME GITHUB_PAT K8S_STORAGE_CLASS DOCKER_REGISTRY DOCKER_REGISTRY_USER APP_DOMAIN REDIS_PASSWORD; do
    if [ -z "${!var}" ]; then
        log_error "$var is not set"
        missing=$((missing + 1))
    fi
done

if [ $missing -eq 0 ]; then
    log_success "All required configuration is set!"
    echo ""
    echo "Next steps:"
    echo "1. Generate ArgoCD token (if not done):"
    echo "   argocd login $ARGOCD_SERVER"
    echo "   argocd account generate-token"
    echo ""
    echo "2. Add GitHub secrets:"
    echo "   cd torchani-service"
    echo "   gh secret set ARGOCD_GITHUB_TOKEN --body \"$GITHUB_PAT\""
    echo "   gh secret set ARGOCD_TOKEN --body \"<argocd-token>\""
    echo "   gh secret set ARGOCD_SERVER --body \"$ARGOCD_SERVER\""
    echo ""
    echo "3. Run the setup script:"
    echo "   ./scripts/setup-cicd.sh"
else
    log_warn "Some configuration is missing. Please set the missing values."
fi