.PHONY: help install dev test lint format clean build deploy run-local run-docker

# Variables
PYTHON := python3
UV := uv
DOCKER := docker
KUBECTL := kubectl
NAMESPACE := torchani
REGISTRY := localhost:5000
VERSION := latest

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	$(UV) venv
	$(UV) pip install -e .

dev: ## Install development dependencies
	$(UV) venv
	$(UV) pip install -e ".[dev]"

test: ## Run tests
	$(UV) run pytest tests/ -v

test-cov: ## Run tests with coverage
	$(UV) run pytest tests/ --cov=app --cov-report=html --cov-report=term

lint: ## Run linting
	$(UV) run ruff check app/
	$(UV) run mypy app/

format: ## Format code
	$(UV) run black app/
	$(UV) run isort app/
	$(UV) run ruff check --fix app/

clean: ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

build: ## Build Docker images
	$(DOCKER) build -t torchani-service:$(VERSION) .
	$(DOCKER) build -t torchani-service:celery-$(VERSION) --target celery .

build-push: build ## Build and push Docker images
	$(DOCKER) tag torchani-service:$(VERSION) $(REGISTRY)/torchani-service:$(VERSION)
	$(DOCKER) tag torchani-service:celery-$(VERSION) $(REGISTRY)/torchani-service:celery-$(VERSION)
	$(DOCKER) push $(REGISTRY)/torchani-service:$(VERSION)
	$(DOCKER) push $(REGISTRY)/torchani-service:celery-$(VERSION)

run-local: ## Run service locally
	$(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-worker: ## Run Celery worker locally
	$(UV) run celery -A app.tasks worker --loglevel=info

run-docker: ## Run with docker-compose
	docker-compose up

run-docker-build: ## Build and run with docker-compose
	docker-compose up --build

deploy: ## Deploy to Kubernetes
	./deploy.sh

deploy-dev: ## Deploy to dev namespace
	NAMESPACE=torchani-dev ./deploy.sh

k8s-apply: ## Apply Kubernetes manifests
	$(KUBECTL) apply -f k8s/

k8s-delete: ## Delete Kubernetes resources
	$(KUBECTL) delete namespace $(NAMESPACE) --ignore-not-found

k8s-logs: ## View logs
	$(KUBECTL) logs -n $(NAMESPACE) deployment/torchani-api --tail=100 -f

k8s-logs-worker: ## View worker logs
	$(KUBECTL) logs -n $(NAMESPACE) deployment/celery-worker --tail=100 -f

k8s-port-forward: ## Port forward to local
	$(KUBECTL) port-forward -n $(NAMESPACE) service/torchani-api 8000:8000

k8s-gpu-status: ## Check GPU status
	$(KUBECTL) exec -n $(NAMESPACE) deployment/torchani-api -- nvidia-smi

redis-cli: ## Connect to Redis CLI
	$(KUBECTL) exec -it -n $(NAMESPACE) statefulset/redis -- redis-cli

check-gpu: ## Check GPU availability in cluster
	@echo "Checking GPU nodes..."
	@$(KUBECTL) get nodes -L nvidia.com/gpu
	@echo "\nGPU allocatable resources:"
	@$(KUBECTL) describe nodes | grep -A 5 "nvidia.com/gpu"

health-check: ## Check service health
	@echo "Checking service health..."
	@$(KUBECTL) exec -n $(NAMESPACE) deployment/torchani-api -- curl -s http://localhost:8000/health | jq

setup-secrets: ## Create Kubernetes secrets
	$(KUBECTL) create secret generic torchani-secrets \
		--from-literal=redis-password=$${REDIS_PASSWORD:-changeme} \
		-n $(NAMESPACE) \
		--dry-run=client -o yaml | $(KUBECTL) apply -f -

monitoring: ## Open monitoring dashboards
	@echo "Opening Grafana dashboard..."
	@echo "URL: http://localhost:3000"
	$(KUBECTL) port-forward -n monitoring service/grafana 3000:3000