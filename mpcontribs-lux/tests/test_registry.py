"""Tests for the LuxRegistry schema/validator registry.

These model the flow the MPContribs API server uses: given a project name plus a
submitted contribution and its attached tables, resolve the registered schemas
and validate the whole submission through ``LuxRegistry.validate``.
"""

import copy

import pytest
from pydantic import BaseModel, ValidationError

import mpcontribs_lux  # noqa: F401  -- import populates the registry
from mpcontribs_lux import LuxRegistry, SchemaType


@pytest.fixture
def isolated_registry():
    """Snapshot and restore the registry class-vars around mutating tests.

    ``LuxRegistry`` is a process-wide singleton, so any test that registers
    throwaway schemas/validators must leave it as it found it.
    """
    projects_backup = copy.deepcopy(LuxRegistry.projects)
    validators_backup = dict(LuxRegistry.validators)
    try:
        yield LuxRegistry
    finally:
        LuxRegistry.projects = projects_backup
        LuxRegistry.validators = validators_backup


# --------------------------------------------------------------------------- #
# Inline record builders (no on-disk cluster/A_Lab fixtures exist)
# --------------------------------------------------------------------------- #
def valid_cluster_material() -> dict:
    return {
        "compoundSystem": "Fe-O",
        "numberOfClusters": 2,
        "clusterLatticeSpaceGroup": "Fm-3m",
        "predictedDimensionality": "3D",
        "minimumAverageDistance": 2.5,
        "isPolar": False,
        "isPiezoelectric": False,
        "isEnantiomorphic": False,
        "hasBatteryData": False,
    }


def valid_clusters() -> list[dict]:
    return [
        {
            "materialId": "mp-149",
            "size": 2,
            "averageDistance": 2.5,
            "elements": "Fe,O",
            "isExtended": False,
            "isShared": False,
        },
        {
            "materialId": "mp-149",
            "size": 3,
            "averageDistance": 3.1,
            "elements": "Fe,Fe,O",
            "isExtended": True,
            "isShared": False,
        },
    ]


def valid_cluster_point_groups() -> list[dict]:
    return [{"materialId": "mp-149", "label": "X1", "symbol": "Oh"}]


def valid_experiment() -> dict:
    return {
        "rgNumber": "RG-0000001-A",
        "globalFormula": "Fe2O3",
        "experimentElements": "Fe,O",
        "workflowTasks": ["Starting", "Heating", "Ending"],
        "precursorPowders": "Fe2O3,Li2CO3",
        "heating": {"method": "standard", "atmosphere": "Air"},
        "powderRecovery": {"totalDosedMass": 1.5},
        "referenceDois": [],
    }


def valid_characterization_rows() -> list[dict]:
    return [
        {
            "rgNumber": "RG-0000001-A",
            "xrdPointIndex": 0,
            "xrdTwoTheta": 10.0,
            "xrdCounts": 123.0,
            "xrdFileName": "RG-0000001-A.xrdml",
            "xrdSource": "aeris",
        }
    ]


# --------------------------------------------------------------------------- #
# Registration wiring
# --------------------------------------------------------------------------- #
def test_import_populates_registry():
    """Importing mpcontribs_lux registers the expected projects and schemas."""
    assert {"cluster_materials", "A_Lab"} <= set(LuxRegistry.projects)

    cluster_tables = LuxRegistry.get_schemas("cluster_materials", SchemaType.table)
    assert {"Cluster", "ClusterPointGroup"} <= set(cluster_tables)
    assert set(
        LuxRegistry.get_schemas("cluster_materials", SchemaType.contribution)
    ) == {"ClusterMaterial"}

    alab_tables = LuxRegistry.get_schemas("A_Lab", SchemaType.table)
    # subset (not equality): PowderRecovery registration lands with the upstream fix.
    assert {"Characterization", "Heating", "SamplePreparation"} <= set(alab_tables)
    assert set(LuxRegistry.get_schemas("A_Lab", SchemaType.contribution)) == {
        "Experiment"
    }

    # cluster_materials declares a cross-table validator; A_Lab does not.
    assert LuxRegistry.get_validator("cluster_materials", "ClusterMaterial") is not None
    assert LuxRegistry.get_validator("A_Lab", "Experiment") is None


def test_register_schema_idempotent_and_rejects_name_clash(isolated_registry):
    project = "zz_dup_project"
    dup_a = type("Dup", (BaseModel,), {})
    dup_b = type("Dup", (BaseModel,), {})

    isolated_registry.register_schema(project, SchemaType.table)(dup_a)
    # Re-registering the same class is a no-op, not an error.
    isolated_registry.register_schema(project, SchemaType.table)(dup_a)

    with pytest.raises(ValueError) as excinfo:
        isolated_registry.register_schema(project, SchemaType.table)(dup_b)

    message = str(excinfo.value)
    # Regression guards for the previously-broken error string.
    assert "<class 'str'>" not in message
    assert "name=" not in message
    assert "Dup" in message


# --------------------------------------------------------------------------- #
# get_schema / get_schemas
# --------------------------------------------------------------------------- #
def test_get_schema_single_and_by_name():
    contribution = LuxRegistry.get_schema("cluster_materials", SchemaType.contribution)
    assert contribution.__name__ == "ClusterMaterial"

    cluster = LuxRegistry.get_schema(
        "cluster_materials", SchemaType.table, name="Cluster"
    )
    assert cluster.__name__ == "Cluster"


def test_get_schema_unknown_project_raises_keyerror():
    with pytest.raises(KeyError):
        LuxRegistry.get_schema("no_such_project", SchemaType.table)


def test_get_schema_unknown_name_lists_available():
    with pytest.raises(KeyError) as excinfo:
        LuxRegistry.get_schema("cluster_materials", SchemaType.table, name="Nope")
    assert "Cluster" in str(excinfo.value)


def test_get_schema_ambiguous_requires_name():
    with pytest.raises(ValueError):
        # cluster_materials has multiple table schemas.
        LuxRegistry.get_schema("cluster_materials", SchemaType.table)


def test_get_schemas_returns_a_copy():
    schemas = LuxRegistry.get_schemas("cluster_materials", SchemaType.table)
    schemas.clear()
    # The registry's own mapping is untouched.
    assert LuxRegistry.get_schemas("cluster_materials", SchemaType.table)


def test_get_schemas_empty_for_unknown():
    assert LuxRegistry.get_schemas("no_such_project", SchemaType.table) == {}


# --------------------------------------------------------------------------- #
# register_validator / get_validator
# --------------------------------------------------------------------------- #
def test_register_validator_stores_and_rejects_conflict(isolated_registry):
    project = "zz_validator_project"

    def validator_a(contribution, tables, structures):
        return True

    def validator_b(contribution, tables, structures):
        return True

    isolated_registry.register_validator(project, "Ctx")(validator_a)
    assert isolated_registry.get_validator(project, "Ctx") is validator_a
    # Same callable again is fine.
    isolated_registry.register_validator(project, "Ctx")(validator_a)

    with pytest.raises(ValueError):
        isolated_registry.register_validator(project, "Ctx")(validator_b)

    assert isolated_registry.get_validator(project, "absent") is None


# --------------------------------------------------------------------------- #
# validate()
# --------------------------------------------------------------------------- #
def test_validate_dispatches_by_contribution_type(isolated_registry):
    """A project with several contribution types routes to the matching validator."""
    project = "zz_multi_contrib"

    ctx_a = type("CtxA", (BaseModel,), {"__annotations__": {"x": int}})
    ctx_b = type("CtxB", (BaseModel,), {"__annotations__": {"x": int}})
    isolated_registry.register_schema(project, SchemaType.contribution)(ctx_a)
    isolated_registry.register_schema(project, SchemaType.contribution)(ctx_b)

    @isolated_registry.register_validator(project, "CtxA")
    def _validate_a(contribution, tables, structures):
        raise ValueError("CtxA validator ran")

    @isolated_registry.register_validator(project, "CtxB")
    def _validate_b(contribution, tables, structures):
        return True

    # Ambiguous without a contribution_name (two contribution schemas).
    with pytest.raises(ValueError):
        isolated_registry.validate(project, {"x": 1})

    # Each contribution_name routes to its own validator.
    with pytest.raises(ValueError, match="CtxA validator ran"):
        isolated_registry.validate(project, {"x": 1}, contribution_name="CtxA")
    assert (
        isolated_registry.validate(project, {"x": 1}, contribution_name="CtxB") is True
    )


def test_validate_runs_declared_cross_table_validator():
    """The cluster_materials validator is always run and cannot be bypassed."""
    assert (
        LuxRegistry.validate(
            "cluster_materials",
            valid_cluster_material(),
            tables={
                "Cluster": valid_clusters(),
                "ClusterPointGroup": valid_cluster_point_groups(),
            },
        )
        is True
    )


def test_validate_rejects_cross_table_inconsistency():
    """Per-row-valid data that violates a spanning invariant still fails."""
    contribution = valid_cluster_material()
    contribution["numberOfClusters"] = 5  # tables only have 2 rows

    with pytest.raises(ValueError, match="numberOfClusters"):
        LuxRegistry.validate(
            "cluster_materials",
            contribution,
            tables={
                "Cluster": valid_clusters(),
                "ClusterPointGroup": valid_cluster_point_groups(),
            },
        )


def test_validate_rejects_mismatched_material_ids():
    clusters = valid_clusters()
    groups = valid_cluster_point_groups()
    groups[0]["materialId"] = "mp-999"  # does not match clusters' materialId

    with pytest.raises(ValueError, match="materialId"):
        LuxRegistry.validate(
            "cluster_materials",
            valid_cluster_material(),
            tables={"Cluster": clusters, "ClusterPointGroup": groups},
        )


def test_validate_fallback_per_row_for_project_without_validator():
    """A_Lab declares no validator, so validate falls back to per-row checks."""
    assert (
        LuxRegistry.validate(
            "A_Lab",
            valid_experiment(),
            tables={"Characterization": valid_characterization_rows()},
        )
        is True
    )


def test_validate_fallback_rejects_bad_row():
    bad_rows = valid_characterization_rows()
    bad_rows[0]["xrdSource"] = "bogus"  # not in {"mongo", "aeris"}

    with pytest.raises(ValidationError):
        LuxRegistry.validate(
            "A_Lab",
            valid_experiment(),
            tables={"Characterization": bad_rows},
        )


def test_validate_bad_contribution_record_rejected():
    contribution = valid_cluster_material()
    contribution["predictedDimensionality"] = "4D"  # outside the allowed literal

    with pytest.raises(ValidationError):
        LuxRegistry.validate(
            "cluster_materials",
            contribution,
            tables={
                "Cluster": valid_clusters(),
                "ClusterPointGroup": valid_cluster_point_groups(),
            },
        )
