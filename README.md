# TorchANI Service

GPU-optimized molecular structure optimization service using TorchANI neural network potentials with intelligent memory management.

## Features

- **GPU Memory Management**: Automatic model loading/unloading with Redis-backed TTL
- **Multiple Models**: Support for ANI-1ccx, ANI-1x, and ANI-2x models
- **Async Processing**: FastAPI with Celery for non-blocking job processing
- **Auto Model Selection**: Automatically selects the best model based on molecular elements
- **Caching**: Redis caching for models and results
- **Monitoring**: Prometheus metrics and health checks
- **Scalable**: Kubernetes-ready with horizontal pod autoscaling

## Supported Elements

- **ANI-1ccx/ANI-1x**: H, C, N, O
- **ANI-2x**: H, C, N, O, F, S, Cl

## Quick Start

### Prerequisites

- Python 3.11+
- CUDA-capable GPU (optional, CPU fallback available)
- Redis server
- uv package manager

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/torchani-service.git
cd torchani-service

# Create virtual environment with uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e .

# Install development dependencies
uv pip install -e ".[dev]"
```

### Configuration

Create a `.env` file in the project root:

```env
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# GPU Configuration
GPU_DEVICE=cuda:0
GPU_MEMORY_LIMIT=0.8
GPU_MEMORY_THRESHOLD=0.7

# Model Configuration
MODEL_MAX_LOADED=2
MODEL_TTL=300  # 5 minutes

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### Running the Service

#### Development Mode

```bash
# Start Redis (if not running)
redis-server

# Start Celery worker (in separate terminal)
celery -A app.tasks worker --loglevel=info

# Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Production Mode

```bash
# Using Docker
docker-compose up

# Using Kubernetes
kubectl apply -f k8s/
```

## API Documentation

Once the service is running, visit:
- API Documentation: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc
- Health check: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

### Core Endpoints

#### 1. Optimize Structure
```bash
POST /api/v1/optimize

curl -X POST "http://localhost:8000/api/v1/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "coordinates": [[0, 0, 0], [1, 0, 0]],
    "elements": [1, 1],
    "model_name": "ANI-1ccx"
  }'
```

#### 2. Calculate Energy
```bash
POST /api/v1/energy

curl -X POST "http://localhost:8000/api/v1/energy" \
  -H "Content-Type: application/json" \
  -d '{
    "coordinates": [[0, 0, 0], [1, 0, 0]],
    "elements": [1, 1]
  }'
```

#### 3. Optimize from SMILES
```bash
POST /api/v1/optimize/smiles

curl -X POST "http://localhost:8000/api/v1/optimize/smiles" \
  -H "Content-Type: application/json" \
  -d '{
    "smiles": "CCO"
  }'
```

#### 4. List Models
```bash
GET /api/v1/models

curl "http://localhost:8000/api/v1/models"
```

#### 5. Submit Async Job
```bash
POST /api/v1/jobs/submit

curl -X POST "http://localhost:8000/api/v1/jobs/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "smiles": "c1ccccc1",
    "job_type": "optimization"
  }'
```

#### 6. Check Job Status
```bash
GET /api/v1/jobs/{job_id}

curl "http://localhost:8000/api/v1/jobs/abc123"
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI     │────▶│   Redis     │
└─────────────┘     └──────────────┘     └─────────────┘
                            │                     │
                            ▼                     │
                    ┌──────────────┐             │
                    │Model Manager │◀────────────┘
                    └──────────────┘
                            │
                            ▼
                    ┌──────────────┐     ┌─────────────┐
                    │  TorchANI    │────▶│    GPU      │
                    └──────────────┘     └─────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   Celery     │
                    └──────────────┘
```

## Memory Management

The service implements intelligent GPU memory management:

1. **Lazy Loading**: Models are loaded only when needed
2. **TTL-based Caching**: Models are cached in Redis with configurable TTL (default: 5 minutes)
3. **Auto-eviction**: Least recently used models are evicted when memory threshold is reached
4. **Memory Monitoring**: Continuous monitoring of GPU memory usage
5. **Graceful Degradation**: Falls back to CPU if GPU is unavailable

## Testing

```bash
# Run unit tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run integration tests
pytest tests/integration/

# Run performance tests
pytest tests/performance/ -v
```

## Deployment

### Docker

```bash
# Build image
docker build -t torchani-service:latest .

# Run container
docker run -d \
  --gpus all \
  -p 8000:8000 \
  -e REDIS_HOST=redis \
  torchani-service:latest
```

### Kubernetes

```bash
# Create namespace
kubectl create namespace torchani

# Deploy
kubectl apply -f k8s/

# Check status
kubectl get pods -n torchani

# View logs
kubectl logs -n torchani deployment/torchani-service
```

### Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Monitoring

The service exposes Prometheus metrics at `/metrics`:

- `torchani_gpu_memory_usage`: Current GPU memory usage
- `torchani_models_loaded`: Number of models in memory
- `torchani_optimization_duration`: Optimization time histogram
- `torchani_requests_total`: Total API requests
- `torchani_errors_total`: Total errors by type

## Performance Tuning

### GPU Memory
```env
GPU_MEMORY_LIMIT=0.8      # Use up to 80% of GPU memory
GPU_MEMORY_THRESHOLD=0.7  # Start evicting at 70% usage
MODEL_MAX_LOADED=2        # Maximum models in memory
```

### Redis Caching
```env
REDIS_MODEL_TTL=300       # Model cache TTL (5 minutes)
REDIS_RESULT_TTL=3600     # Result cache TTL (1 hour)
```

### Celery Workers
```env
CELERY_WORKER_CONCURRENCY=4
CELERY_TASK_TIME_LIMIT=600
```

## Troubleshooting

### GPU Not Detected
```bash
# Check CUDA installation
nvidia-smi

# Check PyTorch GPU support
python -c "import torch; print(torch.cuda.is_available())"
```

### Redis Connection Issues
```bash
# Test Redis connection
redis-cli ping

# Check Redis server
systemctl status redis
```

### Memory Issues
```bash
# Monitor GPU memory
watch -n 1 nvidia-smi

# Clear GPU cache
python -c "import torch; torch.cuda.empty_cache()"
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [TorchANI](https://github.com/aiqm/torchani) for neural network potentials
- [RDKit](https://www.rdkit.org/) for molecular structure handling
- [ASE](https://wiki.fysik.dtu.dk/ase/) for atomic simulation environment