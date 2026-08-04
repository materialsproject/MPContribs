"""
Workflow Tasks Schema

Task execution history for each experiment (1:N relationship).
Maps to: workflow_tasks.parquet
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkflowTask(BaseModel, extra="forbid"):
    """
    Single task in the experiment workflow.

    Each experiment has multiple tasks (1:N relationship).
    Tasks include: PowderDosing, Heating, HeatingWithAtmosphere, ManualHeating,
    RecoverPowder, Diffraction, Starting, Ending.
    """

    rgNumber: str = Field(description="Reference to parent experiment")

    taskId: str = Field(description="Unique task identifier")

    taskType: str = Field(
        description="Type of task (PowderDosing, Heating, RecoverPowder, Diffraction, Ending, ...)"
    )

    status: Literal["cancelled", "completed", "error"] = Field(
        description="Task execution status"
    )

    createdAt: datetime = Field(description="When the task was created")

    startedAt: datetime | None = Field(
        default=None, description="When the task started execution"
    )

    completedAt: datetime | None = Field(
        default=None, description="When the task completed"
    )

    message: str | None = Field(
        default=None, description="Task result message or error"
    )
