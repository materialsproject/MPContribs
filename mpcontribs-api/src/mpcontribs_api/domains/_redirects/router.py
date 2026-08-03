"""Compatibility shims for the legacy (Flask/flask-mongorest) MPContribs API.

The old API was served from the root path (e.g. ``/contributions/``,
``/projects/<pk>/``). The rewrite serves everything under ``/api/v1`` with
slightly different paths and verbs. This router is mounted at the root and:

- 308-redirects every legacy endpoint that has a direct counterpart to its new
  location (preserving method, body, and query string), and
- returns ``410 Gone`` with a machine-readable "deprecated" body for legacy
  endpoints that have no equivalent in the new API (notebooks, the formula/term
  search helpers, project-application approval links, and project creation).

Redirects are permanent (308) so well-behaved clients update their bookmarks
while keeping the original HTTP method and request body intact.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.status import HTTP_308_PERMANENT_REDIRECT, HTTP_410_GONE

router = APIRouter(include_in_schema=False)

# Base path of the new API. The legacy API lived at the service root.
API_V1 = "/api/v1"


def _redirect(request: Request, new_path: str) -> RedirectResponse:
    """308-redirect to ``new_path`` under the v1 API, preserving the query string.

    308 (rather than 301/302) keeps the original method and body, so a legacy
    ``POST``/``PUT``/``DELETE`` is replayed against the new endpoint instead of
    being silently downgraded to a ``GET``.
    """
    target = f"{API_V1}{new_path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target, status_code=HTTP_308_PERMANENT_REDIRECT)


def _deprecated(message: str, *, replacement: str | None = None) -> JSONResponse:
    """Return a ``410 Gone`` in the app's uniform error shape.

    Used for legacy endpoints that have no counterpart in the new API.
    """
    detail: dict[str, str] = {}
    if replacement is not None:
        detail["replacement"] = replacement
    body: dict = {"error": {"code": "endpoint_deprecated", "message": message}}
    if detail:
        body["error"]["detail"] = detail
    return JSONResponse(
        status_code=HTTP_410_GONE,
        content=body,
        headers={"Deprecation": "true"},
    )


# ---------------------------------------------------------------------------
# contributions
# ---------------------------------------------------------------------------
@router.get("/contributions/search")
def redirect_contributions_search() -> JSONResponse:
    # Formula autocomplete (Atlas $search) was not ported to the new API.
    return _deprecated("The contributions formula search endpoint has been removed.")


@router.get("/contributions/download/{short_mime}/")
def redirect_download_contributions(request: Request, short_mime: str) -> RedirectResponse:
    return _redirect(request, f"/contributions/download/{short_mime}")


@router.api_route("/contributions/", methods=["GET", "POST", "PUT", "DELETE"])
def redirect_contributions_collection(request: Request) -> RedirectResponse:
    # GET=list, POST=bulk insert, PUT=bulk upsert, DELETE=delete-by-filter.
    return _redirect(request, "/contributions")


@router.api_route("/contributions/{pk}/", methods=["GET", "PUT", "DELETE"])
def redirect_contribution_item(request: Request, pk: str) -> RedirectResponse:
    # GET=fetch, PUT=update/upsert, DELETE=delete (all keyed by id).
    return _redirect(request, f"/contributions/{pk}")


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------
@router.get("/projects/search")
def redirect_projects_search() -> JSONResponse:
    return _deprecated("The projects search endpoint has been removed.")


@router.get("/projects/applications/{token}")
@router.get("/projects/applications/{token}/{action}")
def redirect_projects_applications(token: str, action: str | None = None) -> JSONResponse:
    # Email-driven project approval/denial links; not part of the new API.
    return _deprecated("Project application approval links have been removed.")


@router.api_route("/projects/", methods=["GET", "POST"], response_model=None)
def redirect_projects_collection(request: Request) -> RedirectResponse | JSONResponse:
    if request.method == "POST":
        # No project-creation endpoint exists in the new API.
        return _deprecated(
            "Creating projects via POST is no longer supported. Create a project with PUT /api/v1/projects/{id}.",
            replacement=f"{API_V1}/projects/{{id}}",
        )
    return _redirect(request, "/projects")


@router.api_route("/projects/{pk}/", methods=["GET", "PUT", "DELETE"])
def redirect_project_item(request: Request, pk: str) -> RedirectResponse:
    # GET=fetch, PUT=update/upsert, DELETE=delete.
    return _redirect(request, f"/projects/{pk}")


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
def _register_component_redirects(component: str) -> None:
    @router.get(f"/{component}/download/{{short_mime}}/", name=f"redirect_download_{component}")
    def redirect_download(request: Request, short_mime: str) -> RedirectResponse:
        return _redirect(request, f"/{component}/download/{short_mime}")

    @router.get(f"/{component}/", name=f"redirect_{component}_collection")
    def redirect_collection(request: Request) -> RedirectResponse:
        return _redirect(request, f"/{component}")

    @router.get(f"/{component}/{{pk}}/", name=f"redirect_{component}_item")
    def redirect_item(request: Request, pk: str) -> RedirectResponse:
        return _redirect(request, f"/{component}/{pk}")


for _component in ("structures", "tables", "attachments"):
    _register_component_redirects(_component)


# ---------------------------------------------------------------------------
# notebooks
# ---------------------------------------------------------------------------
_NOTEBOOKS_GONE = "The notebooks API has been removed."


@router.get("/notebooks/build")
def redirect_notebooks_build() -> JSONResponse:
    return _deprecated(_NOTEBOOKS_GONE)


@router.get("/notebooks/result")
@router.get("/notebooks/result/{job_id}")
def redirect_notebooks_result(job_id: str | None = None) -> JSONResponse:
    return _deprecated(_NOTEBOOKS_GONE)


@router.get("/notebooks/")
def redirect_notebooks_collection() -> JSONResponse:
    return _deprecated(_NOTEBOOKS_GONE)


@router.get("/notebooks/{pk}/")
def redirect_notebooks_item(pk: str) -> JSONResponse:
    return _deprecated(_NOTEBOOKS_GONE)
