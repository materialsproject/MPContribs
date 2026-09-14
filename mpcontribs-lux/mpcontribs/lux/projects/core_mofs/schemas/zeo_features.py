"""Schema for v26.0.2_zeo_features.csv."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, Field, model_validator

from .common import (
    MODEL_CONFIG,
    Dimension,
    NonNegativeFloat,
    NonNegativeInt,
    StructureId,
)


Fraction = Annotated[float, Field(ge=0, le=1)]


class ZeoFeaturesRecord(BaseModel):
    """Zeo++ pore metrics, periodicity, and open-metal-site features."""

    model_config = MODEL_CONFIG

    structure_id: StructureId
    n2_he_available: bool = Field(
        description="Whether the N2/He pore-property calculation is available."
    )
    density_g_cm3: NonNegativeFloat | None = Field(
        description="Crystal density in grams per cubic centimeter."
    )
    largest_cavity_diameter_A: NonNegativeFloat | None = Field(
        description="Largest cavity diameter in angstroms."
    )
    pore_limiting_diameter_A: NonNegativeFloat | None = Field(
        description="Pore-limiting diameter in angstroms."
    )
    # Four v26.0.2 source values are slightly negative, so only finiteness is
    # enforced for this derived quantity.
    largest_free_path_diameter_A: float | None = Field(
        description="Largest free-path diameter in angstroms."
    )
    n2_channel_dimension: Dimension | None = Field(
        description="Dimensionality of the N2-accessible channel network."
    )
    n2_accessible_surface_area_A2: NonNegativeFloat | None = Field(
        description="N2-accessible surface area per unit cell in square angstroms."
    )
    n2_accessible_surface_area_m2_cm3: NonNegativeFloat | None = Field(
        description=(
            "Volumetric N2-accessible surface area in square meters per cubic "
            "centimeter."
        )
    )
    n2_accessible_surface_area_m2_g: NonNegativeFloat | None = Field(
        description="Gravimetric N2-accessible surface area in square meters per gram."
    )
    n2_nonaccessible_surface_area_A2: NonNegativeFloat | None = Field(
        description="N2-nonaccessible surface area per unit cell in square angstroms."
    )
    n2_nonaccessible_surface_area_m2_cm3: NonNegativeFloat | None = Field(
        description=(
            "Volumetric N2-nonaccessible surface area in square meters per cubic "
            "centimeter."
        )
    )
    n2_nonaccessible_surface_area_m2_g: NonNegativeFloat | None = Field(
        description=(
            "Gravimetric N2-nonaccessible surface area in square meters per gram."
        )
    )
    n2_accessible_volume_A3: NonNegativeFloat | None = Field(
        description="N2-accessible volume per unit cell in cubic angstroms."
    )
    n2_accessible_volume_cm3_g: NonNegativeFloat | None = Field(
        description="Gravimetric N2-accessible volume in cubic centimeters per gram."
    )
    n2_accessible_volume_fraction: Fraction | None = Field(
        description="Fraction of the unit-cell volume accessible to N2."
    )
    n2_nonaccessible_volume_A3: NonNegativeFloat | None = Field(
        description="N2-nonaccessible volume per unit cell in cubic angstroms."
    )
    n2_nonaccessible_volume_cm3_g: NonNegativeFloat | None = Field(
        description="Gravimetric N2-nonaccessible volume in cubic centimeters per gram."
    )
    n2_nonaccessible_volume_fraction: Fraction | None = Field(
        description="Fraction of the unit-cell volume not accessible to N2."
    )
    he_void_fraction: Fraction | None = Field(
        description="Helium-accessible void fraction."
    )
    periodicity_available: bool = Field(
        description="Whether framework periodicity analysis is available."
    )
    structure_periodic_dimension: Dimension | None = Field(
        description="Overall periodic dimensionality of the structure."
    )
    framework_1d_count: NonNegativeInt | None = Field(
        description="Number of identified one-dimensional framework components."
    )
    framework_2d_count: NonNegativeInt | None = Field(
        description="Number of identified two-dimensional framework components."
    )
    framework_3d_count: NonNegativeInt | None = Field(
        description="Number of identified three-dimensional framework components."
    )
    oms_available: bool = Field(
        description="Whether open-metal-site analysis is available."
    )
    has_open_metal_sites: bool | None = Field(
        description="Whether at least one open metal site was identified."
    )
    open_metal_site_count: NonNegativeInt | None = Field(
        description="Number of identified open metal sites."
    )

    _N2_FIELDS: ClassVar[tuple[str, ...]] = (
        "density_g_cm3",
        "largest_cavity_diameter_A",
        "pore_limiting_diameter_A",
        "largest_free_path_diameter_A",
        "n2_channel_dimension",
        "n2_accessible_surface_area_A2",
        "n2_accessible_surface_area_m2_cm3",
        "n2_accessible_surface_area_m2_g",
        "n2_nonaccessible_surface_area_A2",
        "n2_nonaccessible_surface_area_m2_cm3",
        "n2_nonaccessible_surface_area_m2_g",
        "n2_accessible_volume_A3",
        "n2_accessible_volume_cm3_g",
        "n2_accessible_volume_fraction",
        "n2_nonaccessible_volume_A3",
        "n2_nonaccessible_volume_cm3_g",
        "n2_nonaccessible_volume_fraction",
        "he_void_fraction",
    )
    _PERIODICITY_FIELDS: ClassVar[tuple[str, ...]] = (
        "structure_periodic_dimension",
        "framework_1d_count",
        "framework_2d_count",
        "framework_3d_count",
    )
    _OMS_FIELDS: ClassVar[tuple[str, ...]] = (
        "has_open_metal_sites",
        "open_metal_site_count",
    )

    @model_validator(mode="after")
    def availability_flags_match_values(self) -> "ZeoFeaturesRecord":
        self._validate_availability("n2_he_available", self._N2_FIELDS)
        self._validate_availability("periodicity_available", self._PERIODICITY_FIELDS)
        self._validate_availability("oms_available", self._OMS_FIELDS)
        if self.oms_available:
            assert self.has_open_metal_sites is not None
            assert self.open_metal_site_count is not None
            if self.has_open_metal_sites != (self.open_metal_site_count > 0):
                raise ValueError(
                    "has_open_metal_sites must equal open_metal_site_count > 0"
                )
        return self

    def _validate_availability(self, flag_name: str, fields: tuple[str, ...]) -> None:
        available = getattr(self, flag_name)
        missing = [name for name in fields if getattr(self, name) is None]
        if available and missing:
            raise ValueError(f"{flag_name}=true requires values for: {missing}")
        if not available and len(missing) != len(fields):
            raise ValueError(
                f"{flag_name}=false requires all dependent values to be null"
            )
