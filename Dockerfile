# Multi-stage build for TorchANI service
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04 AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e .

# Production stage
FROM base AS production

# Copy application code
COPY app ./app

# Create non-root user
RUN useradd -m -u 1000 torchani && \
    chown -R torchani:torchani /app

USER torchani

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Development stage
FROM base AS development

# Install development dependencies
RUN . .venv/bin/activate && \
    uv pip install -e ".[dev]"

# Copy all code
COPY . .

# Run with reload
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Celery worker stage
FROM production AS celery

# Run Celery worker
CMD [".venv/bin/celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=2"]