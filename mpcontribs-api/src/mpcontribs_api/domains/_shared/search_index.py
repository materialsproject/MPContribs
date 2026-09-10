from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pymongo.operations import SearchIndexModel


@dataclass(frozen=True)
class SearchIndex:
    """A single Atlas Search index definition.

    Pymongo.SearchIndexModel does not keep parameters accessible.
    """

    name: str
    type: str
    definition: dict[str, Any]

    def to_pymongo(self) -> SearchIndexModel:
        return SearchIndexModel(name=self.name, type=self.type, definition=self.definition)


class SearchIndexed(BaseModel, ABC):
    """Mixin for Document subclasses to declare SearchIndexes.

    Suggested to use `_path` to validate that the strings in the `SearchIndex.definition`
    are on the model (this prevents drift).
    """

    @classmethod
    @abstractmethod
    def search_indexes(cls) -> tuple[SearchIndex, ...]:
        """Declare this model's search indexes."""
        ...

    @classmethod
    def _path(cls, *parts: str) -> str:
        """Validate a field path against the model at call time."""
        head, *rest = parts
        if head not in cls.model_fields:
            raise KeyError(f"{cls.__name__} has no field {head!r}")
        info = cls.model_fields[head]
        return ".".join((info.alias or head, *rest))
