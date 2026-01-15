"""
XRD Phases Schema

Identified crystal phases from DARA analysis (1:N relationship with experiments).
Maps to: xrd_phases.parquet
"""

from pydantic import BaseModel, Field


class XRDPhase(BaseModel, extra="forbid"):
    """
    Identified crystal phase from XRD refinement.

    Each experiment can have multiple phases (1:N relationship).
    """

    experiment_id: str = Field(description="Reference to parent experiment")

    experiment_name: str = Field(description="Experiment name (for convenience)")

    phase_name: str = Field(description="Name of the identified phase")

    spacegroup: str = Field(description="Space group of the phase (e.g., Fm-3m)")

    weight_fraction: float = Field(
        description="Weight fraction of this phase (0-1)", ge=0, le=1
    )

    weight_fraction_error: float | None = Field(
        default=None, description="Error in weight fraction"
    )

    lattice_a_nm: float | None = Field(
        default=None, description="Lattice parameter a in nm"
    )

    lattice_b_nm: float | None = Field(
        default=None, description="Lattice parameter b in nm"
    )

    lattice_c_nm: float | None = Field(
        default=None, description="Lattice parameter c in nm"
    )

    r_phase: float | None = Field(default=None, description="R-factor for this phase")
