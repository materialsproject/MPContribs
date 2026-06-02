import base64

from pydantic import BaseModel, Field


class CursorParams(BaseModel):
    """Models parameters used in cursor-based pagination"""

    # None == First page
    cursor: str | None = None
    # Per-page limit
    limit: int = Field(default=20, ge=1, le=100)


class Page[T](BaseModel):
    """Model to be returned for a single page of cursor-based paginated results.

    Attributes:
        items (list[T]): the items returned for the given page
        next_cursor (str): the base64-encoded value of the first id on the next page. If None, then no more pages are available
    """

    items: list[T]
    # None == last page
    next_cursor: str | None = None


def encode_cursor(last_id: str) -> str:
    return base64.urlsafe_b64encode(last_id.encode()).decode()


def decode_cursor(cursor: str) -> str:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except ValueError, UnicodeDecodeError:
        raise ValueError("malformed cursor")
