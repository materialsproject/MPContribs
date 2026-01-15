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
    Tasks include: PowderDosing, Heating, RecoverPowder, Diffraction, Ending, etc.
    """

    experiment_id: str = Field(description="Reference to parent experiment")

    task_id: str = Field(description="Unique task identifier")

    task_type: str = Field(
        description="Type of task (PowderDosing, Heating, RecoverPowder, Diffraction, Ending)"
    )

    status: Literal["completed", "error", "pending", "running"] = Field(
        description="Task execution status"
    )

    created_at: datetime = Field(description="When the task was created")

    started_at: datetime | None = Field(
        default=None, description="When the task started execution"
    )

    completed_at: datetime | None = Field(
        default=None, description="When the task completed"
    )

    message: str | None = Field(
        default=None, description="Task result message or error"
    )
