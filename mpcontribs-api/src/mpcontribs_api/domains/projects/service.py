from bson import DBRef

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository
from mpcontribs_api.domains.projects.models import Project, ProjectPatch
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError


class ProjectService:
    """Coordinates assigning a project to its canonical initiative across the two collections."""

    def __init__(
        self,
        projects: MongoDbProjectRepository,
        initiatives: InitiativeRepository,
    ) -> None:
        self._projects = projects
        self._initiatives = initiatives
        self._limits = get_settings().domain.initiatives

    async def patch(self, id: str, update: ProjectPatch) -> Project:
        """Apply a project patch, routing an ``initiative`` change through the assignment checks.

        ``initiative`` carries the target initiative's ``slug`` (or ``null`` to unassign). It is
        split out of the patch so it never reaches the raw ``$set`` as a bare string; any remaining
        fields are applied first, then the initiative link is set.
        """
        if "initiative" not in update.model_fields_set:
            return await self._projects.patch_project_by_id(id=id, update=update)

        data = update.model_dump(exclude_unset=True)
        slug = data.pop("initiative", None)

        # Resolve the target link (and run the both-rights + limit checks) before touching anything.
        ref = await self._resolve_initiative_assignment(project_id=id, slug=slug)

        # Apply any co-submitted plain fields first, so a single request can rename and assign.
        if data:
            await self._projects.patch_project_by_id(id=id, update=ProjectPatch(**data))
        return await self._projects.set_initiative(id=id, ref=ref)

    async def _resolve_initiative_assignment(self, project_id: str, slug: str | None) -> DBRef | None:
        """Validate an initiative assignment and return the link to store (or None to unassign).

        Unassigning needs only project-write access (already enforced downstream). Assigning
        additionally requires that the caller can manage the target initiative and that an
        unapproved target has room under its member cap.
        """
        if slug is None:
            return None

        initiative = await self._initiatives.resolve_visible(slug)
        if initiative is None:
            raise NotFoundError("Initiative not found or not visible", slug=slug)

        if not self._initiatives._user.can_manage(id=initiative.slug, resource="initiative"):
            raise PermissionError(
                message="user does not have adequate acceess to this resource",
                required_role="initiative-owner-collaborator-or-admin",
                resource_id=initiative.slug,
            )

        if not initiative.is_approved:
            members = await self._projects.count_initiative_members(
                initiative_id=initiative.id,
                exclude_project_id=project_id,
            )
            if members >= self._limits.max_projects_per_unapproved:
                raise ConflictError(
                    message="unapproved initiative already has the maximum number of assigned projects",
                    slug=slug,
                    limit=self._limits.max_projects_per_unapproved,
                )

        return DBRef("initiatives", initiative.id)
