"""
Experiment Elements Schema

Elements present in each experiment (1:N relationship).
Maps to: experiment_elements.parquet
"""

from pydantic import BaseModel, Field


class ExperimentElement(BaseModel, extra="forbid"):
    """
    Element present in an experiment.

    Each experiment can have multiple elements (1:N relationship).
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    elementSymbol: str = Field(description="Element symbol (e.g., Na, Mg, O)")

    targetAtomicPercent: float | None = Field(
        default=None, description="Target atomic percentage of this element"
    )
