import hmac
from typing import Annotated

import structlog
from fastapi import Depends, Header, Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from mpcontribs_api.auth import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.exceptions import (
    AuthenticationError,
    GatewayError,
    PermissionError,
)

settings = get_settings()


def verify_gateway(x_gateway_secret: Annotated[str | None, Header()] = None) -> None:
    """Ensures the current access attempt is coming through Kong."""
    if x_gateway_secret is None or not hmac.compare_digest(
        x_gateway_secret, settings.kong.gateway_secret.get_secret_value()
    ):
        raise GatewayError("direct access not permitted")


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.db


DbDep = Annotated[AsyncDatabase, Depends(get_db)]


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
        username=user.username,
        consumer_id=user.consumer_id,
        is_admin=user.is_admin,
    )
    return user


UserDep = Annotated[User, Depends(get_user)]


def require_user(user: UserDep) -> User:
    if user.is_anonymous:
        raise AuthenticationError("authentication required")
    return user


AuthedDep = Annotated[User, Depends(require_user)]


def require_role(role: str):
    def checker(user: AuthedDep) -> User:
        if not user.has_role(role):
            raise PermissionError(required_role=role)
        return user

    return Annotated[User, Depends(checker)]
