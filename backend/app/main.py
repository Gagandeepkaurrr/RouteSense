"""RouteSense FastAPI application entry point and API-wide middleware."""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database.connection import engine
from app.routes.auth import router as auth_router
from app.routes.intake import router as intake_router
from app.routes.itineraries import router as itineraries_router


logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("routesense")

app = FastAPI(
    title="RouteSense API",
    description=(
        "Backend-only, Delhi-specific itinerary generation API. "
        "The frontend is maintained separately."
    ),
    version="1.0.0",
    contact={"name": "RouteSense Backend"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details=None,
    headers=None,
):
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({
            "status": "error",
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": getattr(request.state, "request_id", None),
            },
        }),
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code") or f"HTTP_{exc.status_code}"
        message = detail.get("message") or "The request could not be completed."
        details = {
            key: value
            for key, value in detail.items()
            if key not in {"code", "message"}
        } or None
    else:
        code = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            503: "SERVICE_UNAVAILABLE",
        }.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = str(detail)
        details = None
    return _error_response(
        request, exc.status_code, code, message, details, exc.headers
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    details = [
        {
            "location": error.get("loc", []),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        422,
        "REQUEST_VALIDATION_ERROR",
        "The request did not match the expected schema.",
        details,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "unhandled_exception request_id=%s path=%s",
        request_id,
        request.url.path,
    )
    return _error_response(
        request,
        500,
        "INTERNAL_ERROR",
        "An unexpected server error occurred.",
    )


app.include_router(auth_router)
app.include_router(intake_router)
app.include_router(itineraries_router)


@app.get("/", tags=["Health"])
def root():
    return {"message": "RouteSense API is running", "version": app.version}


@app.get("/health", tags=["Health"])
def health():
    """Liveness check: confirms that the API process is responding."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    """Readiness check: verifies that the configured database is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Database readiness check failed")
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "The database is not currently reachable.",
            },
        ) from exc
    return {"status": "ready", "dependencies": {"database": "ok"}}
