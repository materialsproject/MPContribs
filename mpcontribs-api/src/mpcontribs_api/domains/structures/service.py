from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.structures.models import StructureFilter
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository


class StructureService(ComponentService[MongoDbStructureRepository, StructureFilter]):
    """Defines which field on a Contribtution to look in for the references."""

    ref_field = "structures"
