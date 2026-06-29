"""Schemas for the transparent_conductors project ETL migration."""

from __future__ import annotations

import math
from typing import Any

from pydantic import Field

from mpcontribs.lux.schemas import NON_DATA_FIELDS, ContributionRecord

PROJECT_NAME = "transparent_conductors"
GOOGLE_SHEET_ID = "1bgQAdSfyrPEDI4iljwWlkyUPt_mo84jWr4N_1DKQDUI"
GOOGLE_SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=xlsx"
)
SHEETS = ("n-type TCs", "p-type TCs")

RAW_TO_FIELD = {
    "doping": "doping",
    "number of studies": "studies",
    "quality.good or ok": "quality",
    "structure and composition.common dopants": "dopants",
    "structure and composition.space group symbol": "spacegroup",
    "branch point energy.bpe min ratio": "bpe_ratio_min",
    "branch point energy.bpe max ratio": "bpe_ratio_max",
    "branch point energy.bpe ratio": "bpe_ratio_mean",
    "branch point energy.has degenerate bands": "bpe_degenerate",
    "computed gap.hse06 band gap": "computed_gap_hse06_band",
    "computed gap.hse06 direct gap": "computed_gap_hse06_direct",
    "computed gap.pbe band gap": "computed_gap_pbe_band",
    "computed gap.pbe direct gap": "computed_gap_pbe_direct",
    "computed m*.conditions": "computed_mstar_conditions",
    "computed m*.m* avg": "computed_mstar_average",
    "computed m*.m* planar": "computed_mstar_planar",
    "computed stability.e_above_hull": "computed_stability_e_hull",
    "computed stability.e_above_pourbaix_hull": "computed_stability_e_pourbaix_hull",
    "experimental doping type": "experimental_doping",
    "experimental gap.max experimental gap": "experimental_gap_range_max",
    "experimental gap.max gap reference": "experimental_gap_reference_max",
    "experimental gap.min experimental gap": "experimental_gap_range_min",
    "experimental gap.min gap reference": "experimental_gap_reference_min",
    "max experimental conductivity.associated carrier concentration": "experimental_conductivity_concentration",
    "max experimental conductivity.dopant": "experimental_conductivity_dopant",
    "max experimental conductivity.max conductivity": "experimental_conductivity_max",
    "max experimental conductivity.reference link": "experimental_conductivity_reference",
    "max experimental conductivity.synthesis method": "experimental_conductivity_method",
    "max experimental mobility.dopant": "experimental_mobility_dopant",
    "max experimental mobility.max mobility": "experimental_mobility_max",
    "max experimental mobility.reference link": "experimental_mobility_reference",
    "max experimental mobility.synthesis method": "experimental_mobility_method",
}

ALIASES = {
    "studies": "studies",
    "quality": "quality",
    "dopants": "dopants",
    "spacegroup": "spacegroup",
    "bpe_ratio_min": "BPE.ratio.min",
    "bpe_ratio_max": "BPE.ratio.max",
    "bpe_ratio_mean": "BPE.ratio.mean",
    "bpe_degenerate": "BPE.degenerate",
    "computed_gap_hse06_band": "computed.gap.HSE06.band",
    "computed_gap_hse06_direct": "computed.gap.HSE06.direct",
    "computed_gap_pbe_band": "computed.gap.PBE.band",
    "computed_gap_pbe_direct": "computed.gap.PBE.direct",
    "computed_mstar_conditions": "computed.m*.conditions",
    "computed_mstar_average": "computed.m*.average",
    "computed_mstar_planar": "computed.m*.planar",
    "computed_stability_e_hull": "computed.stability.Eₕ",
    "computed_stability_e_pourbaix_hull": "computed.stability.Eₚₕ",
    "experimental_doping": "experimental.doping",
    "experimental_gap_range_max": "experimental.gap.range.max",
    "experimental_gap_reference_max": "experimental.gap.references.max",
    "experimental_gap_range_min": "experimental.gap.range.min",
    "experimental_gap_reference_min": "experimental.gap.references.min",
    "experimental_conductivity_concentration": "experimental.conductivity.concentration",
    "experimental_conductivity_dopant": "experimental.conductivity.dopant",
    "experimental_conductivity_max": "experimental.conductivity.max",
    "experimental_conductivity_reference": "experimental.conductivity.reference",
    "experimental_conductivity_method": "experimental.conductivity.method",
    "experimental_mobility_dopant": "experimental.mobility.dopant",
    "experimental_mobility_max": "experimental.mobility.max",
    "experimental_mobility_reference": "experimental.mobility.reference",
    "experimental_mobility_method": "experimental.mobility.method",
}

UNITS = {
    "studies": "",
    "bpe_ratio_min": "",
    "bpe_ratio_max": "",
    "bpe_ratio_mean": "",
    "computed_gap_hse06_band": "eV",
    "computed_gap_hse06_direct": "eV",
    "computed_gap_pbe_band": "eV",
    "computed_gap_pbe_direct": "eV",
    "computed_mstar_average": "",
    "computed_mstar_planar": "",
    "computed_stability_e_hull": "eV",
    "computed_stability_e_pourbaix_hull": "eV",
    "experimental_gap_range_max": "eV",
    "experimental_gap_range_min": "eV",
    "experimental_conductivity_concentration": "cm⁻³",
    "experimental_conductivity_max": "S/cm",
    "experimental_mobility_max": "cm²/V/s",
}


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


class TransparentConductorRecord(ContributionRecord):
    """Typed entry for one transparent conductor contribution."""

    aliases: dict[str, str] = ALIASES
    units: dict[str, str] = UNITS

    doping: str = Field(
        description="Doping class from source sheet (n-type or p-type)."
    )
    studies: int | float | None = Field(None, description="Number of studies.")
    quality: str | None = Field(None, description="Quality label (good or ok).")
    dopants: str | None = Field(None, description="Common dopants.")
    spacegroup: str | None = Field(None, description="Space group symbol.")

    bpe_ratio_min: float | int | str | None = Field(
        None, description="Minimum BPE ratio."
    )
    bpe_ratio_max: float | int | str | None = Field(
        None, description="Maximum BPE ratio."
    )
    bpe_ratio_mean: float | int | str | None = Field(
        None, description="Mean BPE ratio."
    )
    bpe_degenerate: str | bool | None = Field(
        None, description="Whether degenerate bands exist."
    )

    computed_gap_hse06_band: float | int | str | None = Field(
        None, description="Computed HSE06 band gap."
    )
    computed_gap_hse06_direct: float | int | str | None = Field(
        None, description="Computed HSE06 direct gap."
    )
    computed_gap_pbe_band: float | int | str | None = Field(
        None, description="Computed PBE band gap."
    )
    computed_gap_pbe_direct: float | int | str | None = Field(
        None, description="Computed PBE direct gap."
    )
    computed_mstar_conditions: str | None = Field(
        None, description="Effective mass conditions."
    )
    computed_mstar_average: float | int | str | None = Field(
        None, description="Average effective mass."
    )
    computed_mstar_planar: float | int | str | None = Field(
        None, description="Planar effective mass."
    )
    computed_stability_e_hull: float | int | str | None = Field(
        None, description="Energy above hull."
    )
    computed_stability_e_pourbaix_hull: float | int | str | None = Field(
        None, description="Energy above Pourbaix hull."
    )

    experimental_doping: str | None = Field(
        None, description="Experimental doping type."
    )
    experimental_gap_range_max: float | int | str | None = Field(
        None, description="Maximum experimental gap."
    )
    experimental_gap_reference_max: str | None = Field(
        None, description="Reference for max experimental gap."
    )
    experimental_gap_range_min: float | int | str | None = Field(
        None, description="Minimum experimental gap."
    )
    experimental_gap_reference_min: str | None = Field(
        None, description="Reference for min experimental gap."
    )

    experimental_conductivity_concentration: float | int | str | None = Field(
        None, description="Carrier concentration at max conductivity."
    )
    experimental_conductivity_dopant: str | None = Field(
        None, description="Dopant for max conductivity."
    )
    experimental_conductivity_max: float | int | str | None = Field(
        None, description="Maximum experimental conductivity."
    )
    experimental_conductivity_reference: str | None = Field(
        None, description="Reference for conductivity data."
    )
    experimental_conductivity_method: str | None = Field(
        None, description="Synthesis method for conductivity."
    )

    experimental_mobility_dopant: str | None = Field(
        None, description="Dopant for max mobility."
    )
    experimental_mobility_max: float | int | str | None = Field(
        None, description="Maximum experimental mobility."
    )
    experimental_mobility_reference: str | None = Field(
        None, description="Reference for mobility data."
    )
    experimental_mobility_method: str | None = Field(
        None, description="Synthesis method for mobility."
    )

    @classmethod
    def _clean_header_key(cls, keys: tuple[str, ...]) -> str:
        key = ".".join(
            [k.replace("TC", "").strip() for k in keys if not k.startswith("Unnamed:")]
        )
        if key.endswith("experimental doping type"):
            key = key.replace("Transport.", "")
        key_split = key.split(".")
        if len(key_split) > 2:
            key = ".".join(key_split[1:])
        if key.endswith("google scholar"):
            key = key.replace(".google scholar", "")
        return key

    @staticmethod
    def _normalize_unit(unit: str) -> str:
        unit = unit.replace("^-3", "⁻³").replace("^20", "²⁰")
        unit = unit.replace("V2/cms", "cm²/V/s").replace("cm^2/Vs", "cm²/V/s")
        return unit

    @classmethod
    def from_sheet_row(
        cls, row: dict[tuple[str, ...], Any], doping: str
    ) -> TransparentConductorRecord | None:
        """Convert one spreadsheet row to a validated transparent conductor record."""
        identifier: str | None = None
        extracted: dict[str, Any] = {"doping": doping}

        for keys, value in row.items():
            key = cls._clean_header_key(keys)
            if key.endswith("MP link") or key.endswith("range"):
                continue

            if key == "Material.mpid":
                if identifier is None:
                    if _is_nan(value):
                        return None
                    identifier = str(value).strip()
                continue

            if key == "Material.p pretty formula":
                key = "formula"

            if isinstance(value, str):
                normalized: Any = value.strip()
            else:
                if _is_nan(value):
                    continue
                if key.endswith(")"):
                    key, unit = key.rsplit(" (", 1)
                    unit = cls._normalize_unit(unit[:-1])
                    if "," in unit:
                        extra_key = key.rsplit(".", 1)[0].lower() + ".conditions"
                        extracted[extra_key] = unit
                normalized = value

            if normalized in ("", None):
                continue

            clean_key = key.replace(" for VB:CB = 4:2", "").replace("?", "").lower()
            extracted[clean_key] = normalized

        if not identifier:
            return None

        fields = {"identifier": identifier, "formula": extracted.get("formula")}
        for raw_key, field_name in RAW_TO_FIELD.items():
            if raw_key in extracted:
                fields[field_name] = extracted[raw_key]

        return cls(**fields)
