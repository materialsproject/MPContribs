from pydantic import BaseModel, Field


class Timing(BaseModel):
    """Timestamps, hours since this experiment's sample creation

    Negative offsets (event logged before registration) are nulled rather than kept negative
    """

    taskCreated: float | None = Field(
        default=None,
        description="PowderDosing task creation, hours since sample creation",
    )

    taskStarted: float | None = Field(
        default=None, description="PowderDosing task start, hours since sample creation"
    )

    taskCompleted: float | None = Field(
        default=None,
        description="PowderDosing task completion, hours since sample creation",
    )
