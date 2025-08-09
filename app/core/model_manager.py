"""GPU memory-aware model manager with Redis caching."""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import torch
import torchani
from redis import asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages TorchANI models with GPU memory optimization and Redis caching."""
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.models_in_memory: Dict[str, Any] = {}
        self.model_last_used: Dict[str, float] = {}
        self.lock = asyncio.Lock()
        self.device = torch.device(settings.gpu_device if torch.cuda.is_available() else "cpu")
        
    async def initialize(self):
        """Initialize Redis connection and preload models."""
        self.redis_client = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        
        # Preload specified models
        for model_name in settings.model_preload:
            try:
                await self.get_model(model_name)
                logger.info(f"Preloaded model: {model_name}")
            except Exception as e:
                logger.error(f"Failed to preload model {model_name}: {e}")
    
    async def close(self):
        """Clean up resources."""
        if self.redis_client:
            await self.redis_client.close()
        
        # Clear models from GPU memory
        for model_name in list(self.models_in_memory.keys()):
            await self._unload_model(model_name)
    
    def _get_gpu_memory_usage(self) -> float:
        """Get current GPU memory usage as a fraction."""
        if not torch.cuda.is_available():
            return 0.0
        
        torch.cuda.synchronize()
        allocated = torch.cuda.memory_allocated(self.device)
        total = torch.cuda.get_device_properties(self.device).total_memory
        return allocated / total
    
    async def _check_memory_pressure(self) -> bool:
        """Check if GPU memory is under pressure."""
        usage = self._get_gpu_memory_usage()
        return usage > settings.gpu_memory_threshold
    
    async def _evict_oldest_model(self):
        """Evict the least recently used model."""
        if not self.models_in_memory:
            return
        
        oldest_model = min(self.model_last_used, key=self.model_last_used.get)
        logger.info(f"Evicting model {oldest_model} due to memory pressure")
        await self._unload_model(oldest_model)
    
    async def _load_model(self, model_name: str) -> Any:
        """Load a TorchANI model into GPU memory."""
        logger.info(f"Loading model {model_name} into GPU memory")
        
        # Check memory pressure and evict if necessary
        while await self._check_memory_pressure() and self.models_in_memory:
            await self._evict_oldest_model()
        
        # Check if we've reached max models limit
        while len(self.models_in_memory) >= settings.model_max_loaded:
            await self._evict_oldest_model()
        
        # Load the appropriate model
        try:
            if model_name == "ANI1ccx":
                model = torchani.models.ANI1ccx(periodic_table_index=True)
            elif model_name == "ANI2x":
                model = torchani.models.ANI2x(periodic_table_index=True)
            elif model_name == "ANI1x":
                model = torchani.models.ANI1x(periodic_table_index=True)
            else:
                raise ValueError(f"Unknown model: {model_name}")
            
            model = model.to(self.device).double()
            
            # Store in memory
            self.models_in_memory[model_name] = model
            self.model_last_used[model_name] = time.time()
            
            # Cache metadata in Redis
            metadata = {
                "loaded_at": time.time(),
                "device": str(self.device),
                "memory_usage": self._get_gpu_memory_usage(),
            }
            await self.redis_client.setex(
                f"model:{model_name}:metadata",
                settings.redis_model_ttl,
                json.dumps(metadata),
            )
            
            logger.info(f"Model {model_name} loaded successfully")
            return model
            
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            raise
    
    async def _unload_model(self, model_name: str):
        """Unload a model from GPU memory."""
        if model_name not in self.models_in_memory:
            return
        
        logger.info(f"Unloading model {model_name} from GPU memory")
        
        model = self.models_in_memory[model_name]
        del self.models_in_memory[model_name]
        del self.model_last_used[model_name]
        
        # Clear from GPU
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Remove from Redis cache
        await self.redis_client.delete(f"model:{model_name}:metadata")
    
    async def get_model(self, model_name: str) -> Any:
        """Get a model, loading it if necessary."""
        async with self.lock:
            # Check if model is already in memory
            if model_name in self.models_in_memory:
                self.model_last_used[model_name] = time.time()
                
                # Extend TTL in Redis
                await self.redis_client.expire(
                    f"model:{model_name}:metadata",
                    settings.redis_model_ttl,
                )
                
                return self.models_in_memory[model_name]
            
            # Check Redis for metadata (model might be loadable)
            metadata = await self.redis_client.get(f"model:{model_name}:metadata")
            if metadata:
                # Model was recently used, load it
                return await self._load_model(model_name)
            
            # First time loading this model
            return await self._load_model(model_name)
    
    async def list_models(self) -> Dict[str, Dict[str, Any]]:
        """List all available models and their status."""
        available_models = ["ANI1ccx", "ANI2x", "ANI1x"]
        result = {}
        
        for model_name in available_models:
            metadata = await self.redis_client.get(f"model:{model_name}:metadata")
            
            result[model_name] = {
                "available": True,
                "loaded": model_name in self.models_in_memory,
                "last_used": self.model_last_used.get(model_name),
                "metadata": json.loads(metadata) if metadata else None,
            }
        
        # Add GPU memory stats
        result["gpu_stats"] = {
            "device": str(self.device),
            "memory_usage": self._get_gpu_memory_usage(),
            "memory_threshold": settings.gpu_memory_threshold,
            "models_loaded": len(self.models_in_memory),
            "max_models": settings.model_max_loaded,
        }
        
        return result
    
    def get_supported_elements(self, model_name: str) -> set:
        """Get the set of elements supported by a model."""
        element_sets = {
            "ANI1ccx": {1, 6, 7, 8},  # H, C, N, O
            "ANI1x": {1, 6, 7, 8},     # H, C, N, O
            "ANI2x": {1, 6, 7, 8, 9, 16, 17},  # H, C, N, O, F, S, Cl
        }
        return element_sets.get(model_name, set())
    
    def select_best_model(self, elements: set) -> Optional[str]:
        """Select the best model for a given set of elements."""
        # Check each model in order of preference
        model_preference = ["ANI2x", "ANI1ccx", "ANI1x"]
        
        for model_name in model_preference:
            supported = self.get_supported_elements(model_name)
            if elements.issubset(supported):
                return model_name
        
        return None
    
    @asynccontextmanager
    async def get_model_context(self, model_name: str):
        """Context manager for using a model."""
        model = await self.get_model(model_name)
        try:
            yield model
        finally:
            # Update last used time
            if model_name in self.models_in_memory:
                self.model_last_used[model_name] = time.time()


# Global model manager instance
model_manager = ModelManager()