"""
Base utilities for A-Lab Pydantic schemas.

Provides common types, validators, and field utilities.
"""

from typing import Any
from pydantic import Field


def ExcludeFromUpload(
    default: Any = None,
    description: str = "",
    **kwargs
) -> Any:
    """
    Field that should NOT be uploaded to MPContribs.
    
    Use this for sensitive data that must remain private until publication.
    Examples: weight_collected, mass measurements that are embargoed.
    
    Usage:
        weight_collected: float | None = ExcludeFromUpload(
            description="Weight of powder collected (embargoed)"
        )
    """
    return Field(
        default=default,
        description=description,
        json_schema_extra={"exclude_from_upload": True},
        **kwargs
    )


def get_uploadable_fields(model_class) -> list[str]:
    """
    Get list of fields that should be uploaded to MPContribs.
    
    Args:
        model_class: Pydantic model class
    
    Returns:
        List of field names that are NOT marked with exclude_from_upload
    """
    uploadable = []
    for field_name, field_info in model_class.model_fields.items():
        extra = field_info.json_schema_extra or {}
        if not extra.get("exclude_from_upload", False):
            uploadable.append(field_name)
    return uploadable


def get_excluded_fields(model_class) -> list[str]:
    """
    Get list of fields that should NOT be uploaded to MPContribs.
    
    Args:
        model_class: Pydantic model class
    
    Returns:
        List of field names that ARE marked with exclude_from_upload
    """
    excluded = []
    for field_name, field_info in model_class.model_fields.items():
        extra = field_info.json_schema_extra or {}
        if extra.get("exclude_from_upload", False):
            excluded.append(field_name)
    return excluded

