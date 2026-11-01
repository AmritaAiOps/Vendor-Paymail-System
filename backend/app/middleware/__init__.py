"""Structured logging and the global error handler. Owner: Person A.
install(app) wires both onto the app; the production server loads it through app.middleware.asgi."""
import json
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import config

log = logging.getLogger("app.errors")


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so the log collector can filter on level, logger and request_id."""

    def format(self, record: logging.LogRecord) -> str:
        out = {"time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
               "logger": record.name, "message": record.getMessage()}
        if request_id := getattr(record, "request_id", None):
            out["request_id"] = request_id
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def install(app: FastAPI) -> FastAPI:
    """JSON logs on stderr for the app and uvicorn; any unhandled error becomes a JSON 500 with a reference id
    (Nginx's X-Request-ID, so it matches the access log). The traceback goes to the log, never to the client."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=config.LOG_LEVEL, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if logger.handlers:  # uvicorn --no-access-log leaves uvicorn.access with none: keep it off
            logger.handlers.clear()
            logger.propagate = True

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc,
                  extra={"request_id": request_id})  # path only: query strings may carry vendor names
        return JSONResponse({"detail": f"Internal server error (ref {request_id})"}, status_code=500)

    return app
