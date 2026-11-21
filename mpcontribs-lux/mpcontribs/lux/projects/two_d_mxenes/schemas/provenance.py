"""How the structure and properties of one MXene were computed.

Most entries are computed with density functional theory (DFT); the DFT
settings are the same for the whole project and are stored once in the
project metadata. Entries computed with a machine-learning interatomic
potential (MLIP), e.g. large solid-solution cells, name the potential here so
that the two kinds of data can be told apart and filtered.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Method = Literal["DFT", "MLIP"]
"""Calculation methods: density functional theory or a machine-learning
interatomic potential."""

POTENTIAL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$"
"""Name and version of a potential, e.g. `MACE-MP-0-medium` or `CHGNet-0.3.0`."""


class Provenance(BaseModel):
    """Calculation method of one entry."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    method: Method = Field(
        "DFT",
        description="Method used to relax the structure and compute the "
        "properties: `DFT` (settings in the project metadata) or `MLIP` "
        "(machine-learning interatomic potential named in `potential`).",
    )
    potential: str | None = Field(
        None,
        max_length=64,
        pattern=POTENTIAL_PATTERN,
        description="Name and version of the machine-learning interatomic "
        "potential, e.g. `MACE-MP-0-medium`. Required for `MLIP` and null "
        "for `DFT`.",
    )

    @model_validator(mode="after")
    def _check_potential(self) -> Provenance:
        if (self.method == "MLIP") != (self.potential is not None):
            raise ValueError("potential must be given if and only if method is MLIP")
        return self
