from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.consumers.models import ConsumerSettings
from mpcontribs_api.domains.consumers.repository import MongoDbConsumerRepository


def get_scoped_consumers(user: UserDep) -> MongoDbConsumerRepository:
    return MongoDbConsumerRepository(user)


ConsumerDep = Annotated[MongoDbConsumerRepository, Depends(get_scoped_consumers)]


async def get_effective_limits(user: UserDep) -> ConsumerSettings:
    """Resolve the settings in effect for the current caller.

    Returns the ``settings`` of the caller's stored ``Consumer`` override if one exists, otherwise a
    default ``ConsumerSettings`` (which fills from the env-backed global defaults). Callers with no
    ``consumer_id`` (anonymous or dev) skip the lookup.
    """
    if user.consumer_id is None:
        return ConsumerSettings()

    override = await MongoDbConsumerRepository(user).get_by_consumer_id(user.consumer_id)
    return override.settings if override is not None else ConsumerSettings()


ConsumerLimitsDep = Annotated[ConsumerSettings, Depends(get_effective_limits)]
