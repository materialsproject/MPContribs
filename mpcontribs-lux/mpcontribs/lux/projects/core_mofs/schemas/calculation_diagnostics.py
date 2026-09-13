"""Schema for v26.0.2_calculation_diagnostics.csv."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from .common import MODEL_CONFIG, StructureId


CalculationName = Literal[
    "CRYSTALNETS_TOPOLOGY",
    "RAC5",
    "ZEO_N2_HE",
    "ZEO_STRUCTURE_PERIODICITY",
    "ZEO_ZERO_PROBE",
]
DiagnosticExecutionStatus = Literal["ERROR", "PARTIAL"]
DiagnosticCode = Literal[
    "CANDIDATE_RAC5_ERROR",
    "CRYSTAL_NETS_INVALID_SBU",
    "EXECUTION_ERROR",
    "INDEX_ERROR",
    "INPUT_FORMAT_ERROR",
    "KEY_ERROR",
    "NONFINITE_OUTPUT",
    "PARTIAL_RESULT",
    "TIMEOUT",
    "TOOL_ABORT",
]
DiagnosticCategory = Literal[
    "EXECUTION_ERROR",
    "INPUT_FORMAT",
    "OUTPUT_PARSE",
    "PARTIAL_RESULT",
    "RESOURCE_TIMEOUT",
    "TOOL_ABORT",
]
RetryAction = Literal["DIAGNOSTIC_ONLY", "EXTENDED_TIMEOUT"]


class CalculationDiagnosticRecord(BaseModel):
    """One failed or partial calculation associated with one structure."""

    model_config = MODEL_CONFIG

    structure_id: StructureId
    calculation: CalculationName = Field(
        description="Calculation stage that produced the diagnostic."
    )
    execution_status: DiagnosticExecutionStatus = Field(
        description="Whether the calculation failed or returned a partial result."
    )
    diagnostic_code: DiagnosticCode = Field(
        description="Specific normalized diagnostic code."
    )
    diagnostic_category: DiagnosticCategory = Field(
        description="Broader category associated with diagnostic_code."
    )
    diagnostic_message: str | None = Field(
        description="Sanitized tool message when the diagnostic provides one."
    )
    retry_action: RetryAction = Field(
        description="Recommended processing action recorded for this diagnostic."
    )

    _CATEGORY_FOR_CODE: ClassVar[dict[str, str]] = {
        "CANDIDATE_RAC5_ERROR": "EXECUTION_ERROR",
        "CRYSTAL_NETS_INVALID_SBU": "EXECUTION_ERROR",
        "EXECUTION_ERROR": "EXECUTION_ERROR",
        "INDEX_ERROR": "EXECUTION_ERROR",
        "INPUT_FORMAT_ERROR": "INPUT_FORMAT",
        "KEY_ERROR": "EXECUTION_ERROR",
        "NONFINITE_OUTPUT": "OUTPUT_PARSE",
        "PARTIAL_RESULT": "PARTIAL_RESULT",
        "TIMEOUT": "RESOURCE_TIMEOUT",
        "TOOL_ABORT": "TOOL_ABORT",
    }
    _CODES_FOR_CALCULATION: ClassVar[dict[str, set[str]]] = {
        "CRYSTALNETS_TOPOLOGY": {
            "CRYSTAL_NETS_INVALID_SBU",
            "INPUT_FORMAT_ERROR",
            "PARTIAL_RESULT",
            "TIMEOUT",
        },
        "RAC5": {
            "CANDIDATE_RAC5_ERROR",
            "INDEX_ERROR",
            "KEY_ERROR",
            "NONFINITE_OUTPUT",
        },
        "ZEO_N2_HE": {"TIMEOUT", "TOOL_ABORT"},
        "ZEO_STRUCTURE_PERIODICITY": {"TIMEOUT", "TOOL_ABORT"},
        "ZEO_ZERO_PROBE": {
            "EXECUTION_ERROR",
            "INPUT_FORMAT_ERROR",
            "TIMEOUT",
            "TOOL_ABORT",
        },
    }

    @model_validator(mode="after")
    def diagnostic_fields_agree(self) -> "CalculationDiagnosticRecord":
        if self.diagnostic_category != self._CATEGORY_FOR_CODE[self.diagnostic_code]:
            raise ValueError("diagnostic_category does not match diagnostic_code")
        if self.diagnostic_code not in self._CODES_FOR_CALCULATION[self.calculation]:
            raise ValueError("diagnostic_code is not valid for this calculation")

        expected_status = (
            "PARTIAL" if self.diagnostic_code == "PARTIAL_RESULT" else "ERROR"
        )
        if self.execution_status != expected_status:
            raise ValueError("execution_status does not match diagnostic_code")

        expected_action = (
            "EXTENDED_TIMEOUT"
            if self.diagnostic_code == "TIMEOUT"
            else "DIAGNOSTIC_ONLY"
        )
        if self.retry_action != expected_action:
            raise ValueError("retry_action does not match diagnostic_code")

        message_is_optional = self.diagnostic_code in {
            "EXECUTION_ERROR",
            "PARTIAL_RESULT",
        }
        if message_is_optional and self.diagnostic_message is not None:
            raise ValueError("this diagnostic_code requires a null diagnostic_message")
        if not message_is_optional and self.diagnostic_message is None:
            raise ValueError("this diagnostic_code requires diagnostic_message")
        return self
