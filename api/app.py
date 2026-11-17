"""FastAPI application: the routes of docs/API.md and their error format.

Routes are thin: they validate the request body and call ``api.service``.
Run it with ``python -m api``.
"""

from __future__ import annotations

import base64
import binascii
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config import Config, load_config
from api.corestatus import core_status
from api.service import ApiError, ImageUpload, Service
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


class ImageIn(_Body):
    name: str = "image"
    mime: str = ""  # informative: the server recognises the type from the bytes
    data: str  # base64, without the "data:...;base64," prefix


class MessageCreate(_Body):
    content: str = ""
    branch_id: int | None = None
    images: list[ImageIn] = []


def _decode_images(images: list[ImageIn]) -> list[ImageUpload]:
    decoded = []
    for image in images:
        try:
            data = base64.b64decode(image.data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ApiError(422, "validation", f"The image {image.name!r} is not valid base64.") from error
        decoded.append(ImageUpload(name=image.name, mime=image.mime, data=data))
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


class MergeRequest(_Body):
    branch_ids: list[int]


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
            conversation_id, body.content, body.branch_id, _decode_images(body.images)
        )

    @app.post("/api/conversations/{conversation_id}/generate")
    def generate(conversation_id: int, body: GenerateRequest | None = None) -> dict:
        return service.generate(conversation_id, body.branch_id if body else None)

    @app.get("/api/attachments/{attachment_id}")
    def attachment(attachment_id: int) -> Response:
        mime, data = service.attachment(attachment_id)
        return Response(
            data,
            media_type=mime,  # always one of the sniffed image types, never HTML or SVG
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",  # an attachment never changes
                "X-Content-Type-Options": "nosniff",
            },
        )

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
        return service.update_point(point_id, included=body.included, text_final=body.text_final)

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
