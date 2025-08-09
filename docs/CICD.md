# CI/CD Documentation

This project uses GitHub Actions for CI/CD and ArgoCD for GitOps-based deployments to Kubernetes.

## Architecture Overview

```
GitHub Repository (torchani-service)
    ├── Push/PR triggers GitHub Actions
    ├── Run tests and build Docker images
    ├── Push images to GitHub Container Registry (ghcr.io)
    └── Update manifests in k8s-manifests repo
           │
           ▼
GitHub Repository (k8s-manifests)
    ├── Contains Kustomized Kubernetes manifests
    ├── Organized by environment (staging/production)
    └── Monitored by ArgoCD
           │
           ▼
ArgoCD
    ├── Watches k8s-manifests repository
    ├── Auto-syncs changes to Kubernetes
    └── Manages rollouts and rollbacks
           │
           ▼
Kubernetes Cluster
    └── Runs the application
```

## Setup Instructions

### 1. GitHub Repository Setup

#### Create Repositories
1. Fork/create `torchani-service` repository for application code
2. Create `k8s-manifests` repository for Kubernetes manifests

#### Configure Secrets
Add these secrets to the `torchani-service` repository:

```bash
# GitHub Settings → Secrets and variables → Actions

ARGOCD_GITHUB_TOKEN    # Personal access token with repo access to k8s-manifests
ARGOCD_TOKEN           # ArgoCD API token for triggering syncs
ARGOCD_SERVER          # ArgoCD server URL (e.g., argocd.example.com)
```

#### Enable GitHub Packages
1. Go to Settings → Pages
2. Enable GitHub Container Registry
3. Configure visibility (public/private)

### 2. ArgoCD Setup

#### Install ArgoCD
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Expose ArgoCD server
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

#### Configure ArgoCD
```bash
# Login to ArgoCD
argocd login localhost:8080

# Change admin password
argocd account update-password

# Create project
kubectl apply -f argocd/appproject.yaml

# Create applications
kubectl apply -f argocd/application.yaml
```

#### Generate ArgoCD Token
```bash
# Create API token
argocd account generate-token --account admin

# Save this token as ARGOCD_TOKEN in GitHub secrets
```

### 3. Configure Manifests Repository

Structure your `k8s-manifests` repository:

```
k8s-manifests/
├── base/
│   └── torchani-service/
│       ├── kustomization.yaml
│       ├── namespace.yaml
│       ├── configmap.yaml
│       ├── deployment.yaml
│       ├── service.yaml
│       └── hpa.yaml
├── overlays/
│   ├── staging/
│   │   ├── kustomization.yaml
│   │   └── deployment-patch.yaml
│   └── production/
│       ├── kustomization.yaml
│       ├── deployment-patch.yaml
│       └── hpa-patch.yaml
└── README.md
```

## Workflow

### Development Workflow

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make Changes and Push**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin feature/my-feature
   ```

3. **Create Pull Request**
   - GitHub Actions runs tests
   - Docker images built with PR tag
   - Review and approve PR

4. **Merge to Main**
   - Tests run again
   - Images built with `main` tag
   - Manifests updated in k8s-manifests repo
   - ArgoCD syncs to staging environment

### Release Workflow

1. **Create Release Tag**
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **Automated Release Process**
   - GitHub Actions creates release
   - Builds production images
   - Updates production manifests
   - ArgoCD deploys to production

### Rollback Process

#### Via ArgoCD UI
1. Open ArgoCD UI
2. Navigate to application
3. Click "History and Rollback"
4. Select previous version
5. Click "Rollback"

#### Via CLI
```bash
# List revisions
argocd app history torchani-service

# Rollback to specific revision
argocd app rollback torchani-service <revision>
```

#### Via Git
```bash
# Revert manifest changes
cd k8s-manifests
git revert HEAD
git push

# ArgoCD will sync the revert
```

## Monitoring

### GitHub Actions
- Check workflow runs: `https://github.com/<owner>/torchani-service/actions`
- View build logs and test results
- Monitor image push status

### ArgoCD Dashboard
```bash
# Port forward ArgoCD UI
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Access at https://localhost:8080
```

### Application Logs
```bash
# View application logs
kubectl logs -n torchani deployment/torchani-api

# View ArgoCD sync logs
argocd app logs torchani-service
```

## Environment Management

### Staging Environment
- **Trigger**: Push to `main` branch
- **Namespace**: `torchani-staging`
- **Auto-sync**: Enabled
- **Image tag**: `main-<sha>`

### Production Environment
- **Trigger**: Create release tag `v*`
- **Namespace**: `torchani`
- **Auto-sync**: Enabled with manual approval
- **Image tag**: Semantic version

### Environment Variables
Managed via Kustomize configMapGenerator:

```yaml
# staging/kustomization.yaml
configMapGenerator:
  - name: torchani-config
    literals:
      - ENVIRONMENT=staging
      - DEBUG=true

# production/kustomization.yaml
configMapGenerator:
  - name: torchani-config
    literals:
      - ENVIRONMENT=production
      - DEBUG=false
```

## Security Considerations

### Secrets Management
Use Sealed Secrets or External Secrets Operator:

```bash
# Install Sealed Secrets
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml

# Create sealed secret
echo -n mypassword | kubectl create secret generic torchani-secrets \
  --dry-run=client \
  --from-file=redis-password=/dev/stdin \
  -o yaml | kubeseal -o yaml > sealed-secret.yaml
```

### Image Scanning
Add image scanning to CI/CD:

```yaml
# In .github/workflows/ci.yml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ steps.meta.outputs.tags }}
    format: 'sarif'
    output: 'trivy-results.sarif'
```

### RBAC
Configure proper RBAC for ArgoCD:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: argocd-torchani
  namespace: torchani
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["*"]
```

## Troubleshooting

### Build Failures
```bash
# Check GitHub Actions logs
gh run list --limit 5
gh run view <run-id>

# Rebuild locally
docker build -t test .
```

### Sync Issues
```bash
# Check sync status
argocd app get torchani-service

# Force sync
argocd app sync torchani-service --force

# Check events
kubectl get events -n torchani --sort-by='.lastTimestamp'
```

### Image Pull Errors
```bash
# Check image availability
docker pull ghcr.io/<owner>/torchani-service:latest

# Check pull secrets
kubectl get secrets -n torchani
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token>
```

## Best Practices

1. **Semantic Versioning**: Use semantic versioning for releases
2. **Environment Parity**: Keep staging close to production
3. **Automated Testing**: Comprehensive test coverage before deployment
4. **Progressive Rollouts**: Use canary or blue-green deployments
5. **Monitoring**: Set up alerts for deployment failures
6. **Documentation**: Keep manifests and configs well-documented
7. **Backup**: Regular backups of persistent data

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [Kustomize Documentation](https://kustomize.io/)
- [GitHub Container Registry](https://docs.github.com/en/packages)