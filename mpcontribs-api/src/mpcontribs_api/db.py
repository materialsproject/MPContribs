from typing import Annotated

from fastapi import Depends, Request
from pymongo.asynchronous.database import AsyncDatabase


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.db


DbDep = Annotated[AsyncDatabase, Depends(get_db)]
