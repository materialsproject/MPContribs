from fastapi import APIRouter

from mpcontribs_api.domains.projects.router import router as projects_router

router = APIRouter(prefix="/api/v1")

router.include_router(projects_router, prefix="/projects")
