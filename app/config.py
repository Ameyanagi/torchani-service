"""Configuration settings for TorchANI service."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    
    # Service settings
    service_name: str = "torchani-service"
    version: str = "0.1.0"
    debug: bool = False
    
    # API settings
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "https://cheminfuse.com"]
    
    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_model_ttl: int = 300  # 5 minutes
    redis_result_ttl: int = 3600  # 1 hour
    
    # Celery settings
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_time_limit: int = 600  # 10 minutes
    celery_task_soft_time_limit: int = 540  # 9 minutes
    
    # GPU settings
    gpu_device: str = "cuda:0"
    gpu_memory_limit: float = 0.8  # 80% of available memory
    gpu_memory_threshold: float = 0.7  # Trigger cleanup at 70%
    
    # Model settings
    model_max_loaded: int = 2
    model_preload: list[str] = []
    model_cache_dir: str = "/tmp/torchani_models"
    
    # Performance settings
    max_batch_size: int = 32
    max_atoms: int = 500
    request_timeout: int = 60
    worker_threads: int = 4
    
    # Monitoring
    prometheus_enabled: bool = True
    prometheus_port: int = 9090
    
    # Storage
    storage_backend: str = "local"  # local, s3
    storage_path: str = "/tmp/torchani_results"
    s3_bucket: Optional[str] = None
    s3_region: str = "us-east-1"
    
    @property
    def redis_url(self) -> str:
        """Get Redis connection URL."""
        password = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password}{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()