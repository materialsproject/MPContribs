from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.consumers.repository import MongoDbConsumerRepository
from mpcontribs_api.domains.consumers.service import ConsumerService


def get_consumer_service(user: UserDep) -> ConsumerService:
    return ConsumerService(consumer=MongoDbConsumerRepository(user))


ConsumerServiceDep = Annotated[ConsumerService, Depends(get_consumer_service)]
