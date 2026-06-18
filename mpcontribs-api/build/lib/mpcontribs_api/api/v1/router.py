from fastapi import APIRouter

from mpcontribs_api.domains.attachments.router import router as attachments_router
from mpcontribs_api.domains.contributions.router import router as contributions_router
from mpcontribs_api.domains.projects.router import router as projects_router
from mpcontribs_api.domains.structures.router import router as structures_router
from mpcontribs_api.domains.tables.router import router as tables_router

router = APIRouter()

router.include_router(attachments_router, prefix="/attachments", tags=["attachments"])
router.include_router(contributions_router, prefix="/contributions", tags=["contributions"])
router.include_router(projects_router, prefix="/projects", tags=["projects"])
router.include_router(structures_router, prefix="/structures", tags=["structures"])
router.include_router(tables_router, prefix="/tables", tags=["tables"])
