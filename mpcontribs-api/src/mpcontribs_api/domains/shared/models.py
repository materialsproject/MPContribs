from typing import Annotated

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    skip: Annotated[int, Field(description="number of items to skip")]
    limit: Annotated[int, Field(description="maximum number of items to return")] = 100
    page: Annotated[
        int,
        Field(
            description="page number to return (in batches of 'per_page'/'_limit'; alternative to _skip"
        ),
    ]
    per_page: Annotated[
        int,
        Field(
            description="maximum number of items to return per page (same as '_limit')"
        ),
    ]
