"""Schema for v26.0.2_checker_findings.csv."""

from __future__ import annotations

import json
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import MODEL_CONFIG, StructureId


CheckerName = Literal[
    "MOFClassifier",
    "MOFChecker",
    "Chen-Manz",
    "MOSAEC",
    "SETC-GAT",
]
CheckResult = Literal["PASS", "FAIL", "NOT_AVAILABLE"]


class CheckerFindingRecord(BaseModel):
    """One checker result for one structure.

    The two JSON payloads intentionally remain strings because their nested
    shapes differ by checker. The validators guarantee that both strings are
    JSON objects and that the raw operational vote agrees with check_result.
    """

    model_config = MODEL_CONFIG

    structure_id: StructureId
    checker: CheckerName = Field(description="Name of the structure-checking method.")
    check_result: CheckResult = Field(
        description="Normalized operational result published for this checker."
    )
    detail_errors: Annotated[
        str,
        Field(description="JSON object serialized by the checker adapter."),
    ]
    raw_prediction_output: Annotated[
        str,
        Field(description="Complete checker-specific output serialized as JSON."),
    ]

    _EXECUTION_STATUSES: ClassVar[dict[str, set[str | None]]] = {
        "MOFClassifier": {"SUCCESS", "ERROR"},
        "MOFChecker": {"SUCCESS", "ERROR", "PROCESS_ERROR", "TIMEOUT"},
        "Chen-Manz": {"SUCCESS", "ERROR", "PROCESS_ERROR", "TIMEOUT"},
        "MOSAEC": {"SUCCESS", "ERROR", "TIMEOUT", "NOT_APPLICABLE_NO_METAL"},
        "SETC-GAT": {
            "SUCCESS",
            "GRAPH_ERROR",
            "INPUT_ERROR",
            "NOT_APPLICABLE_NO_METAL",
            None,
        },
    }

    @field_validator("detail_errors", "raw_prediction_output")
    @classmethod
    def serialized_value_is_json_object(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("value must contain valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("value must contain a JSON object")
        return value

    @model_validator(mode="after")
    def result_matches_raw_payload(self) -> "CheckerFindingRecord":
        raw = self.parsed_raw_prediction_output()
        expected_vote = (
            None if self.check_result == "NOT_AVAILABLE" else self.check_result
        )
        if raw.get("operational_vote") != expected_vote:
            raise ValueError("raw operational_vote does not match check_result")
        execution_status = raw.get("execution_status")
        if execution_status not in self._EXECUTION_STATUSES[self.checker]:
            raise ValueError(
                f"unexpected execution_status for {self.checker}: {execution_status!r}"
            )
        return self

    def parsed_detail_errors(self) -> dict[str, object]:
        """Return detail_errors as a JSON object without changing storage type."""

        return json.loads(self.detail_errors)

    def parsed_raw_prediction_output(self) -> dict[str, object]:
        """Return raw_prediction_output as a checker-specific JSON object."""

        return json.loads(self.raw_prediction_output)
