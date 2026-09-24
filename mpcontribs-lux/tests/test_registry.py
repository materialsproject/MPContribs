"""Tests for the LuxRegistry schema/validator registry.

These model the flow the MPContribs API server uses: given a project name plus a
submitted contribution and its attached tables, resolve the registered schemas
and validate the whole submission through ``LuxRegistry.validate``.
"""

import copy

import pytest
from pydantic import BaseModel, ValidationError

import mpcontribs_lux  # noqa: F401  -- import populates the registry
from mpcontribs_lux import LuxRegistry, SchemaType, ValidatedTables


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

    # cluster_materials declares a cross-object validator; A_Lab does not.
    assert LuxRegistry.get_validators("cluster_materials")
    assert LuxRegistry.get_validators("A_Lab") == []


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
# register_validator / get_validators
# --------------------------------------------------------------------------- #
def test_register_validator_allows_multiple_and_is_idempotent(isolated_registry):
    """Several validators may be attached to one contribution; dupes collapse."""
    project = "zz_validator_project"
    ctx = type("Ctx", (BaseModel,), {})
    isolated_registry.register_schema(project, SchemaType.contribution)(ctx)

    def validator_a(contribution, tables, structures):
        return True

    def validator_b(contribution, tables, structures):
        return True

    isolated_registry.register_validator(project, contribution="Ctx")(validator_a)
    isolated_registry.register_validator(project, contribution="Ctx")(validator_b)
    # Both are kept -- multiple validators per contribution are allowed.
    funcs = isolated_registry.get_validators(project)
    assert validator_a in funcs and validator_b in funcs
    # Re-registering the same function with the same gates is a no-op.
    isolated_registry.register_validator(project, contribution="Ctx")(validator_a)
    assert isolated_registry.get_validators(project).count(validator_a) == 1


def test_register_validator_validates_declared_scope(isolated_registry):
    """Gates must name registered schemas, and at least one gate is required."""
    project = "zz_scope"
    ctx = type("Ctx", (BaseModel,), {})
    tbl = type("Tbl", (BaseModel,), {})
    isolated_registry.register_schema(project, SchemaType.contribution)(ctx)
    isolated_registry.register_schema(project, SchemaType.table)(tbl)

    def validator(contribution, tables, structures):
        return True

    # Must declare contribution= and/or tables=.
    with pytest.raises(ValueError, match="contribution.*tables"):
        isolated_registry.register_validator(project)(validator)
    # Unknown contribution / table names fail fast.
    with pytest.raises(ValueError, match="no such contribution"):
        isolated_registry.register_validator(project, contribution="Missing")(validator)
    with pytest.raises(ValueError, match="no such table"):
        isolated_registry.register_validator(project, tables=("Missing",))(validator)
    # A valid table gate registers.
    isolated_registry.register_validator(project, tables="Tbl")(validator)
    assert validator in isolated_registry.get_validators(project)


# --------------------------------------------------------------------------- #
# validate()
# --------------------------------------------------------------------------- #
def test_validate_runs_only_matching_contribution_scoped_validators(isolated_registry):
    """A contribution-scoped validator runs only for its own contribution type."""
    project = "zz_multi_contrib"

    ctx_a = type("CtxA", (BaseModel,), {"__annotations__": {"x": int}})
    ctx_b = type("CtxB", (BaseModel,), {"__annotations__": {"x": int}})
    isolated_registry.register_schema(project, SchemaType.contribution)(ctx_a)
    isolated_registry.register_schema(project, SchemaType.contribution)(ctx_b)

    @isolated_registry.register_validator(project, contribution="CtxA")
    def _validate_a(contribution, tables, structures):
        raise ValueError("CtxA validator ran")

    @isolated_registry.register_validator(project, contribution="CtxB")
    def _validate_b(contribution, tables, structures):
        return True

    # Ambiguous without a contribution_name (two contribution schemas).
    with pytest.raises(ValueError):
        isolated_registry.validate(project, {"x": 1})

    # Only the resolved contribution's validator runs.
    with pytest.raises(ValueError, match="CtxA validator ran"):
        isolated_registry.validate(project, {"x": 1}, contribution_name="CtxA")
    assert (
        isolated_registry.validate(project, {"x": 1}, contribution_name="CtxB") is True
    )


def test_validate_runs_table_scoped_validator_only_when_tables_present(isolated_registry):
    """A table-scoped validator fires on table presence and gets validated rows."""
    project = "zz_table_scoped"
    ctx = type("Ctx", (BaseModel,), {"__annotations__": {"x": int}})
    row = type("Row", (BaseModel,), {"__annotations__": {"v": int}})
    isolated_registry.register_schema(project, SchemaType.contribution)(ctx)
    isolated_registry.register_schema(project, SchemaType.table)(row)

    seen: list[type] = []

    # Gate declared with the schema class; rows read back with the same class.
    @isolated_registry.register_validator(project, tables=row)
    def _cross(contribution, tables, structures):
        # Rows arrive already parsed into their table model, not as raw dicts.
        seen.extend(type(r) for r in tables.rows(row))
        return True

    # Absent table -> validator does not run.
    assert isolated_registry.validate(project, {"x": 1}) is True
    assert seen == []

    # Present table -> validator runs on validated row models.
    assert (
        isolated_registry.validate(project, {"x": 1}, tables={"Row": [{"v": 1}]}) is True
    )
    assert seen == [row]


def test_validated_tables_typed_access_and_missing():
    """rows(Schema) returns the validated instances; a missing table raises."""
    row = type("Row", (BaseModel,), {"__annotations__": {"v": int}})
    other = type("Other", (BaseModel,), {"__annotations__": {"w": int}})

    tables = ValidatedTables({"Row": [row(v=1), row(v=2)]})

    fetched = tables.rows(row)
    assert [r.v for r in fetched] == [1, 2]  # typed access, no cast at call site
    assert all(isinstance(r, row) for r in fetched)

    # Presence introspection by class or name.
    assert row in tables and "Row" in tables
    assert other not in tables
    assert tables.names() == frozenset({"Row"})

    # get() is the optional-access form; rows() raises for an absent table.
    assert tables.get(other) is None
    with pytest.raises(KeyError):
        tables.rows(other)


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


def test_validate_per_row_for_project_without_validator():
    """A_Lab declares no validator; per-row schema validation still runs."""
    assert (
        LuxRegistry.validate(
            "A_Lab",
            valid_experiment(),
            tables={"Characterization": valid_characterization_rows()},
        )
        is True
    )


def test_validate_rejects_bad_row():
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
