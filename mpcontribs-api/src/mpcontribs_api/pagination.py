import base64

from pydantic import BaseModel, Field


class CursorParams(BaseModel):
    # None == First page
    cursor: str | None = None
    # Per-page limit
    limit: int = Field(default=20, ge=1, le=100)


class Page[T](BaseModel):
    items: list[T]
    # None == last page
    next_cursor: str | None = None


def encode_cursor(last_id: str) -> str:
    return base64.urlsafe_b64encode(last_id.encode()).decode()


def decode_cursor(cursor: str) -> str:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        raise ValueError("malformed cursor")
