"""End-to-end reachability gating for component reads.

Components (structures/tables/attachments) carry no access field of their own. Visibility is
gated by whether a contribution the caller can see references the component. These tests drive the
real ComponentService against MongoDB to confirm reads only surface reachable components.
"""

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.pagination import CursorParams

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

ANON = User()


def _service(user: User) -> ComponentService:
    return ComponentService(
        MongoDbAttachmentRepository(user),
        MongoDbContributionRepository(user),
        ref_field="attachments",
    )


async def _attachment(md5: str) -> Attachment:
    doc = Attachment(_id=PydanticObjectId(), name="d.csv", md5=md5, mime="application/gzip", content=1)
    await doc.insert()
    return doc


async def _contribution(*, is_public: bool, attachments: list[Attachment]) -> Contribution:
    doc = Contribution(
        _id=PydanticObjectId(),
        project="reach-proj",
        identifier=f"mp-{md5[:6]}" if (md5 := attachments[0].md5) else "mp-x",
        formula="Fe2O3",
        data={"x": 1},
        is_public=is_public,
        attachments=attachments,
    )
    await doc.insert()
    return doc


class TestComponentReadReachability:
    async def test_get_by_id_returns_reachable_component(self, db):
        att = await _attachment("a" * 32)
        await _contribution(is_public=True, attachments=[att])
        result = await _service(ANON).get_by_id(str(att.id), fields=None)
        assert result is not None
        assert result.id == att.id

    async def test_get_by_id_hides_unreachable_component(self, db):
        att = await _attachment("b" * 32)
        # Referenced only by a private contribution -> anonymous cannot reach it.
        await _contribution(is_public=False, attachments=[att])
        result = await _service(ANON).get_by_id(str(att.id), fields=None)
        assert result is None

    async def test_get_by_id_hides_orphan_component(self, db):
        # No contribution references this attachment at all.
        att = await _attachment("c" * 32)
        result = await _service(ANON).get_by_id(str(att.id), fields=None)
        assert result is None

    async def test_get_many_only_lists_reachable(self, db):
        pub = await _attachment("d" * 32)
        priv = await _attachment("e" * 32)
        orphan = await _attachment("f" * 32)
        await _contribution(is_public=True, attachments=[pub])
        await _contribution(is_public=False, attachments=[priv])

        page = await _service(ANON).get_many(filter=AttachmentFilter(), pagination=CursorParams(), fields=None)
        ids = {item.id for item in page.items}

        assert pub.id in ids
        assert priv.id not in ids
        assert orphan.id not in ids
