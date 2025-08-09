"""Molecular structure optimization using TorchANI."""

import logging
from typing import Any, Dict, List, Optional, Tuple

import ase
import ase.optimize
import numpy as np
import torch
from rdkit import Chem
from rdkit.Chem import AllChem

from app.core.model_manager import model_manager

logger = logging.getLogger(__name__)


class MolecularOptimizer:
    """Handles molecular structure optimization with TorchANI."""
    
    async def optimize_structure(
        self,
        coordinates: np.ndarray,
        elements: List[int],
        model_name: Optional[str] = None,
        charge: int = 0,
        max_steps: int = 1000,
        fmax: float = 1e-6,
        optimizer: str = "LBFGS",
    ) -> Dict[str, Any]:
        """
        Optimize molecular structure using TorchANI.
        
        Args:
            coordinates: Initial atomic coordinates (N, 3)
            elements: Atomic numbers for each atom
            model_name: TorchANI model to use (auto-select if None)
            charge: Molecular charge
            max_steps: Maximum optimization steps
            fmax: Force convergence criterion
            optimizer: Optimization algorithm (LBFGS, BFGS, FIRE)
        
        Returns:
            Dictionary with optimized structure and energy
        """
        try:
            # Auto-select model if not specified
            if model_name is None:
                element_set = set(elements)
                model_name = model_manager.select_best_model(element_set)
                if model_name is None:
                    raise ValueError(f"No model supports elements: {element_set}")
            
            # Get model from manager
            async with model_manager.get_model_context(model_name) as model:
                # Create ASE Atoms object
                molecule = ase.Atoms(numbers=elements, positions=coordinates)
                
                # Set calculator
                molecule.set_calculator(model.ase())
                
                # Choose optimizer
                if optimizer == "LBFGS":
                    opt = ase.optimize.LBFGS(molecule, memory=1000)
                elif optimizer == "BFGS":
                    opt = ase.optimize.BFGS(molecule)
                elif optimizer == "FIRE":
                    opt = ase.optimize.FIRE(molecule)
                else:
                    raise ValueError(f"Unknown optimizer: {optimizer}")
                
                # Run optimization
                converged = opt.run(fmax=fmax, steps=max_steps)
                
                # Get results
                optimized_coords = molecule.get_positions()
                energy = molecule.get_potential_energy()
                forces = molecule.get_forces()
                
                result = {
                    "success": converged,
                    "model_used": model_name,
                    "energy": float(energy),
                    "coordinates": optimized_coords.tolist(),
                    "forces": forces.tolist(),
                    "steps_taken": opt.nsteps,
                    "charge": charge,
                    "elements": elements,
                }
                
                return result
                
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            raise
    
    async def calculate_energy(
        self,
        coordinates: np.ndarray,
        elements: List[int],
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate single-point energy without optimization.
        
        Args:
            coordinates: Atomic coordinates (N, 3)
            elements: Atomic numbers for each atom
            model_name: TorchANI model to use (auto-select if None)
        
        Returns:
            Dictionary with energy and forces
        """
        try:
            # Auto-select model if not specified
            if model_name is None:
                element_set = set(elements)
                model_name = model_manager.select_best_model(element_set)
                if model_name is None:
                    raise ValueError(f"No model supports elements: {element_set}")
            
            # Get model from manager
            async with model_manager.get_model_context(model_name) as model:
                # Create ASE Atoms object
                molecule = ase.Atoms(numbers=elements, positions=coordinates)
                molecule.set_calculator(model.ase())
                
                # Calculate energy and forces
                energy = molecule.get_potential_energy()
                forces = molecule.get_forces()
                
                result = {
                    "model_used": model_name,
                    "energy": float(energy),
                    "forces": forces.tolist(),
                    "elements": elements,
                }
                
                return result
                
        except Exception as e:
            logger.error(f"Energy calculation failed: {e}")
            raise
    
    async def batch_optimize(
        self,
        structures: List[Tuple[np.ndarray, List[int]]],
        model_name: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Optimize multiple structures in batch.
        
        Args:
            structures: List of (coordinates, elements) tuples
            model_name: TorchANI model to use
            **kwargs: Additional optimization parameters
        
        Returns:
            List of optimization results
        """
        results = []
        
        for coords, elements in structures:
            try:
                result = await self.optimize_structure(
                    coords, elements, model_name, **kwargs
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to optimize structure: {e}")
                results.append({
                    "success": False,
                    "error": str(e),
                    "elements": elements,
                })
        
        return results
    
    def smiles_to_structure(self, smiles: str) -> Tuple[np.ndarray, List[int]]:
        """
        Convert SMILES string to 3D structure.
        
        Args:
            smiles: SMILES string
        
        Returns:
            Tuple of (coordinates, atomic_numbers)
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")
        
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, randomSeed=42)
        AllChem.MMFFOptimizeMolecule(mol)
        
        conf = mol.GetConformer()
        coords = conf.GetPositions()
        elements = [atom.GetAtomicNum() for atom in mol.GetAtoms()]
        
        return coords, elements
    
    def structure_to_xyz(
        self,
        coordinates: np.ndarray,
        elements: List[int],
        comment: str = "",
    ) -> str:
        """
        Convert structure to XYZ format.
        
        Args:
            coordinates: Atomic coordinates
            elements: Atomic numbers
            comment: Comment line for XYZ file
        
        Returns:
            XYZ format string
        """
        # Element symbols
        symbols = {
            1: "H", 6: "C", 7: "N", 8: "O",
            9: "F", 16: "S", 17: "Cl"
        }
        
        lines = [str(len(elements)), comment]
        
        for i, (elem, coord) in enumerate(zip(elements, coordinates)):
            symbol = symbols.get(elem, f"X{elem}")
            x, y, z = coord
            lines.append(f"{symbol:2s} {x:12.6f} {y:12.6f} {z:12.6f}")
        
        return "\n".join(lines)


# Global optimizer instance
optimizer = MolecularOptimizer()