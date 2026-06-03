from fastapi import APIRouter

from src.mpcontribs_api.domains.contributions.router import router as contributions_router
from src.mpcontribs_api.domains.projects.router import router as projects_router

router = APIRouter()

router.include_router(projects_router, prefix="/projects")
router.include_router(contributions_router, prefix="/contributions")
