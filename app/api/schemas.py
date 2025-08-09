"""Pydantic schemas for API requests and responses."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    """Request schema for structure optimization."""
    
    coordinates: List[List[float]] = Field(
        ..., description="Atomic coordinates (N x 3 array)"
    )
    elements: List[int] = Field(
        ..., description="Atomic numbers for each atom"
    )
    model_name: Optional[str] = Field(
        None, description="TorchANI model to use (auto-select if not provided)"
    )
    charge: int = Field(0, description="Molecular charge")
    max_steps: int = Field(1000, description="Maximum optimization steps")
    fmax: float = Field(1e-6, description="Force convergence criterion")
    optimizer: str = Field(
        "LBFGS", description="Optimization algorithm (LBFGS, BFGS, FIRE)"
    )


class OptimizeResponse(BaseModel):
    """Response schema for structure optimization."""
    
    success: bool = Field(..., description="Whether optimization converged")
    model_used: str = Field(..., description="TorchANI model used")
    energy: float = Field(..., description="Final energy in Hartree")
    coordinates: List[List[float]] = Field(
        ..., description="Optimized coordinates"
    )
    forces: List[List[float]] = Field(..., description="Final forces")
    steps_taken: int = Field(..., description="Number of optimization steps")
    charge: int = Field(..., description="Molecular charge")
    elements: List[int] = Field(..., description="Atomic numbers")


class EnergyRequest(BaseModel):
    """Request schema for single-point energy calculation."""
    
    coordinates: List[List[float]] = Field(
        ..., description="Atomic coordinates (N x 3 array)"
    )
    elements: List[int] = Field(
        ..., description="Atomic numbers for each atom"
    )
    model_name: Optional[str] = Field(
        None, description="TorchANI model to use (auto-select if not provided)"
    )


class EnergyResponse(BaseModel):
    """Response schema for single-point energy calculation."""
    
    model_used: str = Field(..., description="TorchANI model used")
    energy: float = Field(..., description="Energy in Hartree")
    forces: List[List[float]] = Field(..., description="Forces on atoms")
    elements: List[int] = Field(..., description="Atomic numbers")


class SMILESOptimizeRequest(BaseModel):
    """Request schema for SMILES-based optimization."""
    
    smiles: str = Field(..., description="SMILES string of molecule")
    model_name: Optional[str] = Field(
        None, description="TorchANI model to use"
    )
    max_steps: int = Field(1000, description="Maximum optimization steps")
    fmax: float = Field(1e-6, description="Force convergence criterion")
    optimizer: str = Field(
        "LBFGS", description="Optimization algorithm"
    )


class ModelInfo(BaseModel):
    """Information about a TorchANI model."""
    
    available: bool = Field(..., description="Whether model is available")
    loaded: bool = Field(..., description="Whether model is in GPU memory")
    last_used: Optional[float] = Field(None, description="Last usage timestamp")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata"
    )


class ModelsResponse(BaseModel):
    """Response schema for model listing."""
    
    models: Dict[str, ModelInfo] = Field(
        ..., description="Available models and their status"
    )
    gpu_stats: Dict[str, Any] = Field(
        ..., description="GPU memory statistics"
    )


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")
    gpu_available: bool = Field(..., description="GPU availability")
    redis_connected: bool = Field(..., description="Redis connection status")


class ErrorResponse(BaseModel):
    """Error response schema."""
    
    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")


class JobSubmitResponse(BaseModel):
    """Response for async job submission."""
    
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status")
    message: str = Field(..., description="Status message")


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    
    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Current job status")
    progress: float = Field(..., description="Progress percentage (0-100)")
    result: Optional[Dict[str, Any]] = Field(
        None, description="Job result if completed"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: str = Field(..., description="Job creation timestamp")
    completed_at: Optional[str] = Field(
        None, description="Job completion timestamp"
    )