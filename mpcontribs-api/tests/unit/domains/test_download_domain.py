"""Contract test: every ``DownloadDomain`` maps to a real stored collection.

``domain`` is the API's contract with the out-of-repo download worker — the worker runs the ticket's
``query`` against the collection named by ``domain`` (and it is the S3 key prefix). If a member's
value ever drifts from its model's ``Settings.name`` the worker silently reads the wrong collection,
so bind the two here where a mismatch is a fast unit-test failure rather than a production surprise.
"""

from beanie import Document

from mpcontribs_api.domains.attachments.models import Attachment
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.downloads.models import DownloadDomain
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.tables.models import Table

# Each downloadable domain and the document whose collection it names.
_DOMAIN_MODEL: dict[DownloadDomain, type[Document]] = {
    DownloadDomain.contributions: Contribution,
    DownloadDomain.structures: Structure,
    DownloadDomain.tables: Table,
    DownloadDomain.attachments: Attachment,
}


def test_every_domain_has_a_model_binding():
    # If a member is added to the enum, it must be given a model here (and thus a collection).
    assert set(_DOMAIN_MODEL) == set(DownloadDomain)


def test_domain_value_equals_its_collection_name():
    for domain, model in _DOMAIN_MODEL.items():
        assert domain.value == model.Settings.name  # pyright: ignore[reportAttributeAccessIssue]
