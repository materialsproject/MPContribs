"""Simulation settings shared by every MXene in the project.

These settings are identical for all entries, so they are recorded once at
the project level (in the MPContribs project description / `other` metadata)
rather than repeated in each contribution. The model documents what is
recorded and validates it.

The values are supplied when the MPContribs project is set up (see
`pipelines/README.md`, "Describe the project and initialise the columns").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class CalculationSettings(BaseModel):
    """DFT settings used to relax the structures and compute properties."""

    model_config = _MODEL_CONFIG

    code: str | None = Field(None, description="Simulation code, e.g. `VASP`.")
    codeVersion: str | None = Field(
        None, description="Version of the simulation code, e.g. `5.4.4`."
    )
    functional: str | None = Field(
        None,
        description="Exchange-correlation functional, e.g. `PBE`.",
    )
    vdwCorrection: str | None = Field(
        None,
        description="Dispersion correction, e.g. `DFT-D3`, or null if none.",
    )
    pseudopotentials: list[str] | None = Field(
        None,
        description="Pseudopotential (e.g. PAW POTCAR) labels used for each element.",
    )
    energyCutoff: float | None = Field(
        None, gt=0.0, description="Plane-wave kinetic energy cutoff, in eV."
    )
    kpointMesh: list[int] | None = Field(
        None,
        min_length=3,
        max_length=3,
        description="Monkhorst-Pack or Gamma-centred k-point mesh for relaxations.",
    )
    spinPolarized: bool | None = Field(
        None, description="Whether calculations were spin-polarized."
    )
    electronicConvergence: float | None = Field(
        None, gt=0.0, description="Electronic (SCF) energy convergence, in eV."
    )
    forceConvergence: float | None = Field(
        None,
        gt=0.0,
        description="Maximum residual force on any atom after relaxation, in eV/Å.",
    )
    elasticMethod: str | None = Field(
        None,
        description="How elastic constants were obtained, e.g. `energy-strain "
        "fitting with +/-2% strain`.",
    )
