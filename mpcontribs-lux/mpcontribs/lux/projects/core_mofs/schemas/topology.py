"""Nested schema for v26.0.2_topology.json."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from .common import MODEL_CONFIG, Dimension, StructureId


TopologyExecutionStatus = Literal["SUCCESS", "PARTIAL", "ERROR"]
TopologyNodeStatus = Literal["SUCCESS", "ERROR"]


class TopologyMethod(BaseModel):
    """CrystalNets calculation settings recorded for the release."""

    model_config = MODEL_CONFIG

    clusterings: list[Literal["SingleNodes", "AllNodes"]] = Field(
        description="CrystalNets clustering modes in execution order."
    )
    exports_enabled: bool = Field(
        description="Whether CrystalNets auxiliary exports were enabled."
    )
    interpenetration_definition: str = Field(
        description="Definition used for the interpenetration count."
    )
    structure_type: Literal["MOF"] = Field(
        description="Structure class supplied to CrystalNets."
    )
    warnings_enabled: bool = Field(
        description="Whether CrystalNets warning output was enabled."
    )

    @model_validator(mode="after")
    def fixed_release_method(self) -> "TopologyMethod":
        if self.clusterings != ["SingleNodes", "AllNodes"]:
            raise ValueError("clusterings must preserve the release calculation order")
        return self


class TopologySoftware(BaseModel):
    """Software versions used for the topology calculation."""

    model_config = MODEL_CONFIG

    crystalnets_version: Annotated[
        str,
        Field(min_length=1, description="CrystalNets.jl version."),
    ]
    julia_version: Annotated[
        str,
        Field(min_length=1, description="Julia runtime version."),
    ]


class TopologyError(BaseModel):
    """Record-level topology calculation failure."""

    model_config = MODEL_CONFIG

    message: Annotated[
        str,
        Field(min_length=1, description="Record-level calculation error message."),
    ]
    type: Annotated[
        str,
        Field(min_length=1, description="Record-level calculation error type."),
    ]


class TopologyNodeResult(BaseModel):
    """Topology result for one clustering of one subnet."""

    model_config = MODEL_CONFIG

    dimension: Dimension | None = Field(
        description="Network dimensionality when this clustering succeeded."
    )
    status: TopologyNodeStatus = Field(
        description="Execution status for this clustering result."
    )
    topological_genome: str | None = Field(
        description="CrystalNets topological genome when generated."
    )
    topology_key: str | None = Field(
        description="Recognized or generated topology key."
    )
    topology_name: str | None = Field(
        description="Recognized topology name when available."
    )
    error_message: str | None = Field(
        default=None,
        description="Clustering-level error message when status is ERROR.",
    )

    @model_validator(mode="after")
    def status_matches_payload(self) -> "TopologyNodeResult":
        if self.status == "SUCCESS":
            if self.dimension is None or self.topology_key is None:
                raise ValueError("SUCCESS node requires dimension and topology_key")
            if self.error_message is not None:
                raise ValueError("SUCCESS node cannot contain error_message")
        else:
            if self.error_message is None:
                raise ValueError("ERROR node requires error_message")
            if self.dimension is not None or self.topology_key is not None:
                raise ValueError("ERROR node cannot contain dimension or topology_key")
            if self.topological_genome is not None or self.topology_name is not None:
                raise ValueError("ERROR node cannot contain topology results")
        return self


class TopologySubnet(BaseModel):
    """Single-node and all-node results for one interpenetrated subnet."""

    model_config = MODEL_CONFIG

    all_node: TopologyNodeResult = Field(
        description="AllNodes clustering result for this subnet."
    )
    single_all_agree: bool = Field(
        description="Whether SingleNodes and AllNodes assignments agree."
    )
    single_node: TopologyNodeResult = Field(
        description="SingleNodes clustering result for this subnet."
    )
    subnet_index: Annotated[
        int,
        Field(ge=1, description="One-based subnet index."),
    ]


class TopologyRecord(BaseModel):
    """Complete CrystalNets result for one CoRE MOF structure."""

    model_config = MODEL_CONFIG

    all_node_net: str | None = Field(
        description="Aggregate AllNodes topology key when uniquely defined."
    )
    catenation_degree: (
        Annotated[
            int,
            Field(ge=1),
        ]
        | None
    ) = Field(description="Number of interpenetrated subnetworks.")
    error: TopologyError | None = Field(
        description="Record-level failure details for an ERROR execution."
    )
    execution_status: TopologyExecutionStatus = Field(
        description="Overall CrystalNets execution status."
    )
    interpenetrated_subnet_count: (
        Annotated[
            int,
            Field(ge=1),
        ]
        | None
    ) = Field(description="Number of subnet records returned by CrystalNets.")
    method: TopologyMethod = Field(description="Calculation method and settings.")
    network_dimension: Dimension | None = Field(
        description="Aggregate network dimensionality when uniquely defined."
    )
    runtime_seconds: (
        Annotated[
            float,
            Field(ge=0),
        ]
        | None
    ) = Field(description="CrystalNets execution time in seconds.")
    single_all_agree: bool | None = Field(
        description="Aggregate agreement between SingleNodes and AllNodes results."
    )
    single_node_net: str | None = Field(
        description="Aggregate SingleNodes topology key when uniquely defined."
    )
    software: TopologySoftware = Field(
        description="Software versions used for the calculation."
    )
    structure_id: StructureId
    subnets: list[TopologySubnet] = Field(
        description="Topology results for each interpenetrated subnet."
    )
    topology_available: bool = Field(
        description="Whether a complete aggregate topology result is available."
    )

    @model_validator(mode="after")
    def execution_status_matches_payload(self) -> "TopologyRecord":
        indices = [subnet.subnet_index for subnet in self.subnets]
        if indices != list(range(1, len(self.subnets) + 1)):
            raise ValueError("subnet_index values must be contiguous and one-based")

        if self.catenation_degree is not None and self.catenation_degree != len(
            self.subnets
        ):
            raise ValueError("catenation_degree must equal the number of subnets")
        if (
            self.interpenetrated_subnet_count is not None
            and self.interpenetrated_subnet_count != len(self.subnets)
        ):
            raise ValueError(
                "interpenetrated_subnet_count must equal the number of subnets"
            )

        node_statuses = {
            node.status
            for subnet in self.subnets
            for node in (subnet.single_node, subnet.all_node)
        }
        if self.execution_status == "ERROR":
            if self.topology_available or self.error is None or self.subnets:
                raise ValueError(
                    "ERROR record requires error, no subnets, and unavailable topology"
                )
            if any(
                value is not None
                for value in (
                    self.catenation_degree,
                    self.interpenetrated_subnet_count,
                    self.network_dimension,
                    self.single_all_agree,
                    self.single_node_net,
                    self.all_node_net,
                )
            ):
                raise ValueError("ERROR record cannot contain topology result values")
        elif self.execution_status == "PARTIAL":
            if self.topology_available or self.error is not None or not self.subnets:
                raise ValueError(
                    "PARTIAL record requires subnets and unavailable topology"
                )
            if "ERROR" not in node_statuses or self.runtime_seconds is None:
                raise ValueError("PARTIAL record requires a failed node and runtime")
            if any(
                value is not None
                for value in (
                    self.network_dimension,
                    self.single_all_agree,
                    self.single_node_net,
                    self.all_node_net,
                )
            ):
                raise ValueError(
                    "PARTIAL record cannot publish aggregate topology results"
                )
        else:
            if (
                not self.topology_available
                or self.error is not None
                or not self.subnets
            ):
                raise ValueError(
                    "SUCCESS record requires available, error-free subnet results"
                )
            if node_statuses != {"SUCCESS"} or self.runtime_seconds is None:
                raise ValueError("SUCCESS record requires successful nodes and runtime")
            if (
                self.catenation_degree is None
                or self.interpenetrated_subnet_count is None
            ):
                raise ValueError("SUCCESS record requires subnet counts")
            if self.single_all_agree is None:
                raise ValueError("SUCCESS record requires single_all_agree")
        return self
