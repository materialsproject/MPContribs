"""
XRD Refinements Schema

DARA Rietveld refinement analysis results (1:1 relationship with experiments).
Maps to: xrd_refinements.parquet
"""

from pydantic import BaseModel, Field


class XRDRefinement(BaseModel, extra="forbid"):
    """
    XRD Rietveld refinement result from DARA analysis.
    
    One result per experiment (1:1 relationship).
    """
    
    experiment_id: str = Field(
        description="Reference to parent experiment"
    )
    
    experiment_name: str = Field(
        description="Experiment name (for convenience)"
    )
    
    success: bool = Field(
        description="Whether the refinement was successful"
    )
    
    error: str | None = Field(
        default=None,
        description="Error message if refinement failed"
    )
    
    error_type: str | None = Field(
        default=None,
        description="Classification of error type"
    )
    
    rwp: float | None = Field(
        default=None,
        description="Weighted profile R-factor (goodness of fit)"
    )
    
    rp: float | None = Field(
        default=None,
        description="Profile R-factor"
    )
    
    rexp: float | None = Field(
        default=None,
        description="Expected R-factor"
    )
    
    num_phases: int = Field(
        default=0,
        description="Number of phases identified"
    )
    
    chemical_system: str | None = Field(
        default=None,
        description="Chemical system (e.g., Na-Mg-P-O)"
    )
    
    target_formula: str | None = Field(
        default=None,
        description="Target formula"
    )
    
    analysis_timestamp: str | None = Field(
        default=None,
        description="When the analysis was performed"
    )
    
    mode: str | None = Field(
        default=None,
        description="Analysis mode"
    )
    
    wmin: int | None = Field(
        default=None,
        description="Minimum 2θ angle for refinement"
    )
    
    wmax: int | None = Field(
        default=None,
        description="Maximum 2θ angle for refinement"
    )

