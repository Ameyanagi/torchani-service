"""API routes for TorchANI service."""

import logging
import uuid
from typing import Any, Dict

import numpy as np
from fastapi import APIRouter, HTTPException, status

from app.api.schemas import (
    EnergyRequest,
    EnergyResponse,
    ErrorResponse,
    JobStatusResponse,
    JobSubmitResponse,
    ModelsResponse,
    OptimizeRequest,
    OptimizeResponse,
    SMILESOptimizeRequest,
)
from app.core.model_manager import model_manager
from app.core.optimizer import optimizer
from app.tasks import celery_app, optimize_structure_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    responses={400: {"model": ErrorResponse}},
)
async def optimize_structure(request: OptimizeRequest) -> OptimizeResponse:
    """
    Optimize molecular structure using TorchANI.
    
    This endpoint performs synchronous optimization. For large molecules
    or batch processing, use the async job submission endpoint.
    """
    try:
        # Convert to numpy arrays
        coordinates = np.array(request.coordinates)
        elements = request.elements
        
        # Validate input
        if coordinates.shape[0] != len(elements):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Number of coordinates must match number of elements",
            )
        
        # Run optimization
        result = await optimizer.optimize_structure(
            coordinates=coordinates,
            elements=elements,
            model_name=request.model_name,
            charge=request.charge,
            max_steps=request.max_steps,
            fmax=request.fmax,
            optimizer=request.optimizer,
        )
        
        return OptimizeResponse(**result)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Optimization failed",
        )


@router.post(
    "/energy",
    response_model=EnergyResponse,
    responses={400: {"model": ErrorResponse}},
)
async def calculate_energy(request: EnergyRequest) -> EnergyResponse:
    """
    Calculate single-point energy without optimization.
    
    This is useful for evaluating the energy of a given conformation
    without modifying the structure.
    """
    try:
        # Convert to numpy arrays
        coordinates = np.array(request.coordinates)
        elements = request.elements
        
        # Validate input
        if coordinates.shape[0] != len(elements):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Number of coordinates must match number of elements",
            )
        
        # Calculate energy
        result = await optimizer.calculate_energy(
            coordinates=coordinates,
            elements=elements,
            model_name=request.model_name,
        )
        
        return EnergyResponse(**result)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Energy calculation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Energy calculation failed",
        )


@router.post(
    "/optimize/smiles",
    response_model=OptimizeResponse,
    responses={400: {"model": ErrorResponse}},
)
async def optimize_from_smiles(request: SMILESOptimizeRequest) -> OptimizeResponse:
    """
    Optimize molecular structure from SMILES string.
    
    This endpoint converts a SMILES string to 3D structure and optimizes it.
    The initial 3D structure is generated using RDKit's MMFF force field.
    """
    try:
        # Convert SMILES to structure
        coordinates, elements = optimizer.smiles_to_structure(request.smiles)
        
        # Run optimization
        result = await optimizer.optimize_structure(
            coordinates=coordinates,
            elements=elements,
            model_name=request.model_name,
            max_steps=request.max_steps,
            fmax=request.fmax,
            optimizer=request.optimizer,
        )
        
        return OptimizeResponse(**result)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"SMILES optimization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SMILES optimization failed",
        )


@router.get(
    "/models",
    response_model=ModelsResponse,
)
async def list_models() -> ModelsResponse:
    """
    List available TorchANI models and their status.
    
    Shows which models are available, loaded in GPU memory,
    and current GPU memory statistics.
    """
    try:
        models_info = await model_manager.list_models()
        
        # Separate GPU stats from model info
        gpu_stats = models_info.pop("gpu_stats", {})
        
        return ModelsResponse(
            models=models_info,
            gpu_stats=gpu_stats,
        )
        
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list models",
        )


@router.post(
    "/models/{model_name}/load",
    response_model=Dict[str, str],
)
async def load_model(model_name: str) -> Dict[str, str]:
    """
    Preload a model into GPU memory.
    
    This can be used to warm up the model cache before processing.
    """
    try:
        await model_manager.get_model(model_name)
        return {"message": f"Model {model_name} loaded successfully"}
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load model",
        )


@router.delete(
    "/models/{model_name}/unload",
    response_model=Dict[str, str],
)
async def unload_model(model_name: str) -> Dict[str, str]:
    """
    Unload a model from GPU memory.
    
    This can be used to free up GPU memory manually.
    """
    try:
        await model_manager._unload_model(model_name)
        return {"message": f"Model {model_name} unloaded successfully"}
        
    except Exception as e:
        logger.error(f"Failed to unload model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unload model",
        )


@router.post(
    "/jobs/submit",
    response_model=JobSubmitResponse,
)
async def submit_job(request: SMILESOptimizeRequest) -> JobSubmitResponse:
    """
    Submit an async optimization job.
    
    Returns a job ID that can be used to check status and retrieve results.
    """
    try:
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Submit to Celery
        task = optimize_structure_task.delay(
            job_id=job_id,
            smiles=request.smiles,
            model_name=request.model_name,
            max_steps=request.max_steps,
            fmax=request.fmax,
            optimizer=request.optimizer,
        )
        
        return JobSubmitResponse(
            job_id=job_id,
            status="submitted",
            message="Job submitted successfully",
        )
        
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit job",
        )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Get the status of an optimization job.
    
    Returns the current status, progress, and results if completed.
    """
    try:
        # Get task result from Celery
        result = celery_app.AsyncResult(job_id)
        
        # Map Celery states to our status
        status_map = {
            "PENDING": "pending",
            "STARTED": "processing",
            "SUCCESS": "completed",
            "FAILURE": "failed",
            "RETRY": "retrying",
            "REVOKED": "cancelled",
        }
        
        job_status = status_map.get(result.state, "unknown")
        
        response = JobStatusResponse(
            job_id=job_id,
            status=job_status,
            progress=0.0,
            result=None,
            error=None,
            created_at="",
            completed_at=None,
        )
        
        # Add result or error based on status
        if job_status == "completed":
            response.result = result.result
            response.progress = 100.0
        elif job_status == "failed":
            response.error = str(result.info)
        elif job_status == "processing":
            # Get progress from result metadata if available
            if hasattr(result, "info") and isinstance(result.info, dict):
                response.progress = result.info.get("progress", 50.0)
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job status",
        )


@router.delete(
    "/jobs/{job_id}",
    response_model=Dict[str, str],
)
async def cancel_job(job_id: str) -> Dict[str, str]:
    """
    Cancel a running optimization job.
    """
    try:
        # Revoke the Celery task
        celery_app.control.revoke(job_id, terminate=True)
        
        return {"message": f"Job {job_id} cancelled"}
        
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel job",
        )