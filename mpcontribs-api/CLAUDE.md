# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is a complete rewrite of the MPContribs API server.
The core of the package is FastAPI, Pydantic, and Beanie.
Developer experience and process efficiency are top priorities.

## Commands

```bash
# Format, fix, and lint (preferred)
just fmt

# Run tests
uv run pytest

# Run tests by marker
uv run pytest -m base
uv run pytest -m extra

# Run tests in parallel
uv run pytest -n auto

# Type check
uv run basedpyright
```

## Environment

Copy `.env.example` to `.env`. Key variables (all prefixed `MPCONTRIBS_`):

- `MONGO__URI` — MongoDB Atlas URI
- `MONGO__DB_NAME` — database name
- `ENVIRONMENT` — `dev` or `prod` (controls log format and debug mode)

## Architecture

### Domain structure

Each resource lives in `src/mpcontribs_api/domains/<resource>/` with four files:

- `models.py` — Beanie `Document` subclass (DB model) + Pydantic output/input/patch/filter models
- `repository.py` — `MongoDb<Resource>Repository` encapsulating all database access
- `router.py` — `APIRouter` with CRUD endpoint handlers
- `dependencies.py` — `<Resource>Dep` type alias (`Annotated[MongoDb<Resource>Repository, Depends(...)]`)

Routers are registered in `src/mpcontribs_api/api/v1/router.py`.

### Authentication and authorization

Kong injects user identity via headers; `dependencies.get_user` parses them into a frozen `User` model (`authz.py`). The dependency chain is:

- `UserDep` — any caller (anonymous or authenticated)
- `AuthedDep` / `require_user` — requires an authenticated user (raises 401 otherwise)
- `require_role(role)` — factory returning a dependency that requires a specific group membership

All mutating endpoints (POST/PUT/PATCH/DELETE) depend on `require_user`, so anonymous callers get 401; read endpoints (GET) stay open and rely on scope to filter results.

All database access goes through a repository instantiated with the current `User`. The repository's `_scope` dict is injected into every MongoDB query automatically:

- **Admins** (members of `mongo.admin_group`): no filter applied
- **Authenticated users**: see public+approved data, own resources (`owner == username`), and group resources
- **Anonymous**: public + approved only

Components (structures/tables/attachments) have no access field of their own; their reads and deletes are gated by whether an in-scope contribution references them (see `ContributionService`/`ComponentService`).

**Trust boundary:** the service is only reachable through Kong, which terminates auth and sets the identity headers. There is no in-app gateway-secret check today — the deployment network is the boundary, so the identity headers are trusted. If the service is ever exposed off the Kong path, add a gateway-secret (or mTLS) check before trusting those headers.

### Repository pattern

Repositories take a `User` at construction time and expose typed async methods (`get_*`, `insert_*`, `patch_*`, `upsert_*`, `delete_*`). They never leak the scope logic to routers — routers only call repository methods.

### Sparse field selection

The `_fields` query parameter (handled in `projection.py`) lets callers request specific fields (comma-separated, dotted for nesting). `SparseFieldsModel` dynamically creates a trimmed Pydantic model via `create_model()` and converts field paths to MongoDB projection syntax. Results are cached with `@lru_cache`.

### Cursor-based pagination

`Page[T]` in `pagination.py` contains `items` and a `next_cursor` (base64-encoded last item ID). Pagination is forward-only and stateless. Default page size is 20; max is 100.

### Exception hierarchy

`exceptions.py` defines `AppError` subclasses (`NotFoundError`, `ConflictError`, `ValidationError`, `AuthenticationError`, `PermissionError`). All carry `status_code`, `error_code`, `message`, and a `context` dict. Handlers in `app.py` convert them to a uniform JSON shape; internal context is logged but not sent to clients.

### Observability

`logging.py` configures structlog with per-request context vars (request_id, method, path, consumer_id) bound by the middleware in `middleware.py`. OpenTelemetry traces are exported via OTLP/gRPC and trace/span IDs are injected into every log line.
