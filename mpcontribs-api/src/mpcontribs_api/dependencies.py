from typing import Annotated

import aioboto3
import structlog
from fastapi import Depends, Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.authz import User
from mpcontribs_api.exceptions import AuthenticationError


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.db


DbDep = Annotated[AsyncDatabase, Depends(get_db)]


def get_boto(request: Request) -> aioboto3.Session:
    return request.app.state.boto_session


BotoDep = Annotated[aioboto3.Session, Depends(get_boto)]


def get_s3(request: Request) -> S3Client:
    return request.app.state.s3


S3Dep = Annotated[S3Client, Depends(get_s3)]


def get_mongo_client(request: Request) -> AsyncMongoClient:
    return request.app.state.mongo_client


MongoClientDep = Annotated[AsyncMongoClient, Depends(get_mongo_client)]


def _split(raw: str | None) -> set[str]:
    return {g.strip() for g in (raw or "").split(",") if g.strip()}


def get_user(request: Request) -> User:
    """Dissects request headers for user-related keys."""
    h = request.headers
    explicit_anon = h.get("x-anonymous-consumer", "").lower() == "true"
    username = h.get("x-consumer-username") or None
    if explicit_anon or username is None:
        user = User()  # anonymous = all defaults
    else:
        groups = _split(h.get("x-authenticated-groups")) | _split(h.get("x-consumer-groups"))
        user = User(
            consumer_id=h.get("x-consumer-id"),
            username=username,
            groups=frozenset(groups),
        )
    structlog.contextvars.bind_contextvars(
        consumer_id=user.consumer_id,
        is_admin=user.is_admin,
    )
    return user


UserDep = Annotated[User, Depends(get_user)]


def require_user(user: UserDep) -> User:
    if user.is_anonymous:
        raise AuthenticationError("authentication required")
    return user


# AuthedDep = Annotated[User, Depends(require_user)]


# def require_role(role: str):
#     def checker(user: AuthedDep) -> User:
#         if not user.has_role(role):
#             raise PermissionError(required_role=role)
#         return user

#     return Annotated[User, Depends(checker)]
