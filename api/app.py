"""FastAPI application: the routes of docs/API.md and their error format.

Routes are thin: they validate the request body and call ``api.service``.
Run it with ``python -m api``.
"""

from __future__ import annotations

import base64
import binascii
import logging
import traceback
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config import Config, load_config
from api.corestatus import core_status
from api.service import ApiError, Service, Upload
from core.tree import InvariantError

log = logging.getLogger("graftchat.api")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsUpdate(_Body):
    api_key: str | None = None
    spend_cap_usd: float | None = None
    chat_model: str | None = None
    takeaway_model: str | None = None


class ConversationCreate(_Body):
    title: str | None = None


class ConversationRename(_Body):
    title: str


class FileIn(_Body):
    name: str = "file"
    mime: str = ""  # informative: the server recognises the kind from the bytes
    data: str  # base64, without the "data:...;base64," prefix


class MessageCreate(_Body):
    content: str = ""
    branch_id: int | None = None
    files: list[FileIn] = []
    images: list[FileIn] = []  # older name of `files`, still accepted


def _decode_files(files: list[FileIn]) -> list[Upload]:
    decoded = []
    for file in files:
        try:
            data = base64.b64decode(file.data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ApiError(422, "validation", f"{file.name!r} is not valid base64.") from error
        decoded.append(Upload(name=file.name, mime=file.mime, data=data))
    return decoded


class GenerateRequest(_Body):
    branch_id: int | None = None


class BranchCreate(_Body):
    anchor_message_id: int
    start: int
    end: int
    quote: str


class TakeawayRequest(_Body):
    regenerate: bool = False


class PointUpdate(_Body):
    included: bool | None = None
    text_final: str | None = None
    title: str | None = None


class PointCreate(_Body):
    text: str
    title: str | None = None


class MergeRequest(_Body):
    branch_ids: list[int]


# The only names this server answers to. It listens on 127.0.0.1, but a web page in the
# same browser can still reach it: through a domain that resolves to 127.0.0.1 (DNS
# rebinding, which would let that page read the conversations) or with a cross-site form
# POST (which could spend the user's credit). The Host and Origin checks below stop both.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _hostname(value: str) -> str | None:
    """``host[:port]`` or a URL → its host name, lower case; None if unreadable."""
    try:
        return urlsplit(value if "//" in value else "//" + value).hostname
    except ValueError:
        return None


def _local_only_problem(method: str, headers) -> str | None:
    """Why a request does not come from this computer's own pages, or None if it does."""
    if _hostname(headers.get("host", "")) not in LOCAL_HOSTS:
        return "GraftChat only answers at http://127.0.0.1 or http://localhost."
    if method in _SAFE_METHODS:
        return None
    origin = headers.get("origin")
    if origin is not None and _hostname(origin) not in LOCAL_HOSTS:
        return "Requests from other websites are refused."
    if headers.get("sec-fetch-site") == "cross-site":
        return "Requests from other websites are refused."
    return None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _stub_name(error: NotImplementedError) -> str:
    """``module.function`` of the stub that raised, read from the traceback."""
    name = "a core function"
    for frame, _ in traceback.walk_tb(error.__traceback__):  # the last frame is the stub
        module = frame.f_globals.get("__name__", "")
        name = f"{module}.{frame.f_code.co_name}" if module else frame.f_code.co_name
    return name


def create_app(service: Service | None = None, config: Config | None = None) -> FastAPI:
    config = config or (service.config if service else load_config())
    service = service or Service(config)
    app = FastAPI(title="GraftChat", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    @app.middleware("http")
    async def _local_only(request: Request, call_next):
        problem = _local_only_problem(request.method, request.headers)
        if problem:
            return _error(403, "not_local", problem)
        return await call_next(request)

    # --- errors, all in the {"error": {"code", "message"}} shape -------------------

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, error: ApiError) -> JSONResponse:
        return _error(error.status, error.code, error.message)

    @app.exception_handler(InvariantError)
    async def _invariant(request: Request, error: InvariantError) -> JSONResponse:
        return _error(409, "invariant", str(error))

    @app.exception_handler(NotImplementedError)
    async def _stub(request: Request, error: NotImplementedError) -> JSONResponse:
        name = _stub_name(error)
        return _error(501, "core_not_implemented", f"{name} is not implemented yet.")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, error: RequestValidationError) -> JSONResponse:
        parts = []
        for item in error.errors():
            where = ".".join(str(p) for p in item.get("loc", ()) if p != "body")
            parts.append(f"{where}: {item.get('msg')}" if where else str(item.get("msg")))
        return _error(422, "validation", "; ".join(parts) or "Invalid request.")

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if error.status_code == 404 else "http_error"
        return _error(error.status_code, code, str(error.detail))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, error: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error(500, "internal", f"Unexpected server error: {type(error).__name__}.")

    # --- health and settings -------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "core": core_status()}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return service.settings_view()

    @app.put("/api/settings")
    def put_settings(body: SettingsUpdate) -> dict:
        # Only the fields the client actually sent (null is a value: it clears a model).
        return service.update_settings({name: getattr(body, name) for name in body.model_fields_set})

    @app.delete("/api/settings/api-key")
    def delete_api_key() -> dict:
        return service.delete_api_key()

    @app.post("/api/oauth/start")
    def oauth_start(request: Request) -> dict:
        # The browser comes back to this same server (in development, through the Vite proxy).
        return service.oauth_start(str(request.url_for("oauth_callback")))

    @app.get("/api/oauth/callback", name="oauth_callback")
    def oauth_callback(code: str = "", state: str = "") -> RedirectResponse:
        # A page the browser lands on, so errors come back as a query string, not JSON.
        try:
            if not code:
                raise ApiError(422, "validation", "OpenRouter did not send a code back.")
            service.oauth_finish(code, state)
        except ApiError as error:
            return RedirectResponse(f"/?openrouter=error&message={quote(error.message)}", status_code=303)
        return RedirectResponse("/?openrouter=connected", status_code=303)

    @app.get("/api/models")
    def models() -> dict:
        return service.models()

    # --- conversations -------------------------------------------------------------

    @app.get("/api/conversations")
    def list_conversations() -> dict:
        return service.list_conversations()

    @app.post("/api/conversations", status_code=201)
    def create_conversation(body: ConversationCreate | None = None) -> dict:
        return service.create_conversation(body.title if body else None)

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: int) -> dict:
        return service.get_conversation(conversation_id)

    @app.patch("/api/conversations/{conversation_id}")
    def rename_conversation(conversation_id: int, body: ConversationRename) -> dict:
        return service.rename_conversation(conversation_id, body.title)

    # --- chat ----------------------------------------------------------------------

    @app.post("/api/conversations/{conversation_id}/messages")
    def send_message(conversation_id: int, body: MessageCreate) -> dict:
        return service.send_message(
            conversation_id, body.content, body.branch_id, _decode_files(body.files + body.images)
        )

    @app.post("/api/conversations/{conversation_id}/generate")
    def generate(conversation_id: int, body: GenerateRequest | None = None) -> dict:
        return service.generate(conversation_id, body.branch_id if body else None)

    @app.get("/api/attachments/{attachment_id}")
    def attachment(attachment_id: int) -> Response:
        found, data = service.attachment(attachment_id)
        headers = {
            "Cache-Control": "private, max-age=31536000, immutable",  # an attachment never changes
            "X-Content-Type-Options": "nosniff",
        }
        if found.kind == "image":
            # always one of the sniffed image types, never HTML or SVG: safe to show inline
            return Response(data, media_type=found.mime, headers=headers)
        # A document is only ever downloaded, never rendered by the browser (an .html file
        # served inline would run in the app's origin).
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(found.name)}"
        return Response(data, media_type="application/octet-stream", headers=headers)

    @app.delete("/api/messages/{message_id}")
    def delete_message(message_id: int) -> dict:
        return service.delete_message(message_id)

    # --- branches ------------------------------------------------------------------

    @app.post("/api/conversations/{conversation_id}/branches", status_code=201)
    def open_branch(conversation_id: int, body: BranchCreate) -> dict:
        return service.open_branch(
            conversation_id, body.anchor_message_id, body.start, body.end, body.quote
        )

    @app.post("/api/branches/{branch_id}/discard")
    def discard_branch(branch_id: int) -> dict:
        return service.discard_branch(branch_id)

    @app.post("/api/branches/{branch_id}/takeaway")
    def generate_takeaway(branch_id: int, body: TakeawayRequest | None = None) -> dict:
        return service.generate_takeaway(branch_id, body.regenerate if body else False)

    @app.patch("/api/points/{point_id}")
    def update_point(point_id: int, body: PointUpdate) -> dict:
        return service.update_point(
            point_id, included=body.included, text_final=body.text_final, title=body.title
        )

    @app.post("/api/branches/{branch_id}/points", status_code=201)
    def add_point(branch_id: int, body: PointCreate) -> dict:
        return service.add_point(branch_id, body.text, body.title)

    @app.delete("/api/points/{point_id}")
    def delete_point(point_id: int) -> dict:
        return service.delete_point(point_id)

    @app.post("/api/conversations/{conversation_id}/merge")
    def merge(conversation_id: int, body: MergeRequest) -> dict:
        return service.merge(conversation_id, body.branch_ids)

    # --- everything else -----------------------------------------------------------

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown(path: str) -> JSONResponse:
        return _error(404, "not_found", f"No such endpoint: /api/{path}")

    if (config.web_dist / "index.html").is_file():
        # The built frontend (npm run build), so one process serves everything.
        app.mount("/", StaticFiles(directory=config.web_dist, html=True), name="web")
    else:

        @app.get("/", response_class=HTMLResponse)
        def frontend_missing() -> str:
            return FRONTEND_MISSING_PAGE

    return app


# Shown at "/" when web/ has not been built yet, instead of a bare 404.
FRONTEND_MISSING_PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>GraftChat</title>
<body style="font: 16px/1.5 system-ui, sans-serif; max-width: 40rem; margin: 4rem auto; padding: 0 1rem">
<h1 style="font-size: 1.25rem">The backend is running, but the frontend has not been built yet.</h1>
<p>Build it once, then restart <code>python -m api</code>:</p>
<pre style="background: #eee; padding: 1rem">cd web
npm install
npm run build</pre>
<p>While working on the frontend, run <code>npm run dev</code> in <code>web/</code> instead and open
<a href="http://127.0.0.1:5173">http://127.0.0.1:5173</a>.</p>
</body>
</html>
"""
