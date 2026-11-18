"""Reference schema for the raw per-atom dump columns.

Documents the ``dump.<step>.cracked`` attachments
(``id type x y z c_6 c_7[1] c_7[2] c_7[3]``). Not uploaded as a table: each
frame has hundreds of thousands of atoms, and the frames table already
holds the aggregates.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class CrackAtomRecord(BaseModel):
    """One atom in one dump frame. Stresses are stress*volume (bar*Angstrom^3)."""

    model_config = _MODEL_CONFIG

    atomId: int = Field(ge=1, description="LAMMPS atom id, stable across frames.")
    atomType: int = Field(ge=1, description="LAMMPS atom type.")
    x: float = Field(description="Position x (Angstrom).")
    y: float = Field(description="Position y (Angstrom).")
    z: float = Field(description="Position z (Angstrom).")
    potentialEnergy: float = Field(description="Per-atom energy (eV, unbounded).")
    stressXx: float = Field(description="Per-atom xx stress*volume (bar*Angstrom^3).")
    stressYy: float = Field(description="Per-atom yy stress*volume (bar*Angstrom^3).")
    stressZz: float = Field(description="Per-atom zz stress*volume (bar*Angstrom^3).")
