"""Celery tasks for async job processing."""

import asyncio
import logging
from typing import Any, Dict

import numpy as np
from celery import Celery, Task
from celery.signals import task_failure, task_success

from app.config import settings
from app.core.model_manager import model_manager
from app.core.optimizer import optimizer

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "torchani_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


class AsyncTask(Task):
    """Base task class for async execution."""
    
    def __init__(self):
        super().__init__()
        self.loop = None
    
    def run_async(self, coro):
        """Run async coroutine in sync context."""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        return self.loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    base=AsyncTask,
    name="optimize_structure",
    max_retries=3,
)
def optimize_structure_task(
    self,
    job_id: str,
    smiles: str,
    model_name: str = None,
    max_steps: int = 1000,
    fmax: float = 1e-6,
    optimizer: str = "LBFGS",
) -> Dict[str, Any]:
    """
    Async task for structure optimization.
    
    Args:
        job_id: Unique job identifier
        smiles: SMILES string of molecule
        model_name: TorchANI model to use
        max_steps: Maximum optimization steps
        fmax: Force convergence criterion
        optimizer: Optimization algorithm
    
    Returns:
        Optimization results
    """
    try:
        logger.info(f"Starting optimization job {job_id} for SMILES: {smiles}")
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={"progress": 10.0, "status": "Converting SMILES to 3D structure"},
        )
        
        # Convert SMILES to structure
        coordinates, elements = optimizer.smiles_to_structure(smiles)
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={"progress": 30.0, "status": "Loading model"},
        )
        
        # Initialize model manager if needed
        if model_manager.redis_client is None:
            self.run_async(model_manager.initialize())
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={"progress": 50.0, "status": "Running optimization"},
        )
        
        # Run optimization
        result = self.run_async(
            optimizer.optimize_structure(
                coordinates=coordinates,
                elements=elements,
                model_name=model_name,
                max_steps=max_steps,
                fmax=fmax,
                optimizer=optimizer,
            )
        )
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={"progress": 90.0, "status": "Finalizing results"},
        )
        
        # Add job metadata
        result["job_id"] = job_id
        result["smiles"] = smiles
        
        # Convert to XYZ format
        result["xyz"] = optimizer.structure_to_xyz(
            np.array(result["coordinates"]),
            result["elements"],
            comment=f"Optimized structure for {smiles}",
        )
        
        logger.info(f"Optimization job {job_id} completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Optimization job {job_id} failed: {e}")
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@celery_app.task(
    bind=True,
    base=AsyncTask,
    name="batch_optimize",
    max_retries=3,
)
def batch_optimize_task(
    self,
    job_id: str,
    smiles_list: list,
    model_name: str = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Async task for batch structure optimization.
    
    Args:
        job_id: Unique job identifier
        smiles_list: List of SMILES strings
        model_name: TorchANI model to use
        **kwargs: Additional optimization parameters
    
    Returns:
        Batch optimization results
    """
    try:
        logger.info(f"Starting batch optimization job {job_id} for {len(smiles_list)} molecules")
        
        results = []
        total = len(smiles_list)
        
        # Initialize model manager if needed
        if model_manager.redis_client is None:
            self.run_async(model_manager.initialize())
        
        for i, smiles in enumerate(smiles_list):
            # Update progress
            progress = (i / total) * 100
            self.update_state(
                state="PROGRESS",
                meta={
                    "progress": progress,
                    "status": f"Optimizing molecule {i+1}/{total}",
                    "current_smiles": smiles,
                },
            )
            
            try:
                # Convert SMILES to structure
                coordinates, elements = optimizer.smiles_to_structure(smiles)
                
                # Run optimization
                result = self.run_async(
                    optimizer.optimize_structure(
                        coordinates=coordinates,
                        elements=elements,
                        model_name=model_name,
                        **kwargs,
                    )
                )
                
                result["smiles"] = smiles
                results.append(result)
                
            except Exception as e:
                logger.error(f"Failed to optimize {smiles}: {e}")
                results.append({
                    "smiles": smiles,
                    "success": False,
                    "error": str(e),
                })
        
        logger.info(f"Batch optimization job {job_id} completed")
        
        return {
            "job_id": job_id,
            "total": total,
            "successful": sum(1 for r in results if r.get("success", False)),
            "failed": sum(1 for r in results if not r.get("success", True)),
            "results": results,
        }
        
    except Exception as e:
        logger.error(f"Batch optimization job {job_id} failed: {e}")
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@celery_app.task(
    name="cleanup_old_jobs",
    ignore_result=True,
)
def cleanup_old_jobs():
    """
    Periodic task to cleanup old job results.
    
    This should be scheduled to run periodically (e.g., daily)
    to clean up old results from Redis.
    """
    try:
        logger.info("Starting cleanup of old job results")
        
        # Get Redis client
        import redis
        r = redis.from_url(settings.celery_result_backend)
        
        # Find and delete old results (older than 7 days)
        # This is a simplified example - implement based on your needs
        
        logger.info("Cleanup completed")
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")


# Signal handlers for monitoring
@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """Handle successful task completion."""
    logger.info(f"Task {sender.name} completed successfully")


@task_failure.connect
def task_failure_handler(sender=None, exception=None, **kwargs):
    """Handle task failure."""
    logger.error(f"Task {sender.name} failed: {exception}")


# Celery beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "cleanup-old-jobs": {
        "task": "cleanup_old_jobs",
        "schedule": 86400.0,  # Daily
    },
}