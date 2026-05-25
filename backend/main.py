"""
FastAPI application entry-point for Aletheia-Aegis.

Registers middleware:
  - CORSMiddleware      : outermost, handles preflight (Req 1.6)
  - CorrelationId       : attaches X-Request-ID to every response
  - AuthMiddleware      : JWT validation for /api/v1/admin/* routes (Req 5.2)
  - TimeoutMiddleware   : per-route timeouts (Req 9.5)
  - RateLimitMiddleware : 30 requests/minute per IP

Loads environment from backend/.env automatically.

Requirements: 5.2, 1.6, 9.5
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

# Load .env file from backend directory before anything else
_ENV_PATH = Path(__file__).resolve().parent / ".env"
if _ENV_PATH.exists():
    from dotenv import load_dotenv  # type: ignore[import]
    load_dotenv(_ENV_PATH)

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from backend.db.repository import InMemoryHistoryRepository
from backend.ml.language_router import LanguageRouter
from backend.ml.prediction_service import PredictionService
from backend.services.fact_check_client import FactCheckClient
from backend.services.trust_rater import TrustRater

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "fake_news_detector")

URL_FETCH_TIMEOUT: float = 30.0
FACT_CHECK_TIMEOUT: float = 10.0

# ---------------------------------------------------------------------------
# Middleware: Correlation ID
# ---------------------------------------------------------------------------


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Middleware: JWT Authentication for admin routes
# ---------------------------------------------------------------------------


class AuthMiddleware(BaseHTTPMiddleware):
    ADMIN_PREFIX = "/api/v1/admin"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not request.url.path.startswith(self.ADMIN_PREFIX):
            return await call_next(request)

        # Pass OPTIONS preflight through — CORS handles it
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "UNAUTHORIZED", "message": "Missing or malformed Authorization header."},
                headers={"X-Request-ID": getattr(request.state, "request_id", str(uuid.uuid4()))},
            )

        token = auth_header[len("Bearer "):]
        try:
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError as exc:
            logger.warning("JWT validation failed for %s: %s", request.url.path, exc)
            return JSONResponse(
                status_code=401,
                content={"error": "UNAUTHORIZED", "message": "Invalid or expired token."},
                headers={"X-Request-ID": getattr(request.state, "request_id", str(uuid.uuid4()))},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Middleware: Request Timeout
# ---------------------------------------------------------------------------


class TimeoutMiddleware(BaseHTTPMiddleware):
    def _timeout_for(self, path: str) -> float | None:
        if "/submissions" in path:
            return URL_FETCH_TIMEOUT
        if "/fact-check" in path:
            return FACT_CHECK_TIMEOUT
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        timeout = self._timeout_for(request.url.path)
        if timeout is None:
            return await call_next(request)
        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
            return JSONResponse(
                status_code=504,
                content={"error": "GATEWAY_TIMEOUT", "message": f"Request exceeded the {timeout:.0f}-second time limit."},
                headers={"X-Request-ID": request_id},
            )


# ---------------------------------------------------------------------------
# Repository factory — MongoDB if URI set, else in-memory
# ---------------------------------------------------------------------------


def _build_repository():
    """Return MongoHistoryRepository if MONGODB_URI is configured and reachable, else in-memory."""
    if MONGODB_URI:
        try:
            from backend.db.mongo_repository import MongoHistoryRepository  # noqa: PLC0415
            import pymongo  # noqa: PLC0415
            # Probe the connection synchronously with a short timeout before
            # committing to the async Motor client.
            probe = pymongo.MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=4000,
                tlsAllowInvalidCertificates=True,
            )
            probe.admin.command("ping")
            probe.close()
            # Probe succeeded — use the real MongoDB repository
            repo = MongoHistoryRepository(
                mongo_uri=MONGODB_URI,
                db_name=MONGODB_DB_NAME,
            )
            logger.info("Using MongoDB repository (db=%s)", MONGODB_DB_NAME)
            return repo
        except Exception as exc:
            logger.warning(
                "MongoDB unreachable (%s) — using in-memory repository. "
                "To fix: whitelist your IP in MongoDB Atlas Network Access.",
                type(exc).__name__,
            )
    else:
        logger.warning("MONGODB_URI not set — using in-memory repository (history will not persist)")
    return InMemoryHistoryRepository()
# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    language_router: "LanguageRouter | None" = None,
    trust_rater: "TrustRater | None" = None,
    fact_check_client: "FactCheckClient | None" = None,
    repository=None,
) -> FastAPI:
    application = FastAPI(
        title="Aletheia-Aegis — Fake News Detection API",
        version="1.0.0",
        description=(
            "AI-Powered Fake News Detection Platform. "
            "Detects misinformation in English, Telugu, and Hindi articles."
        ),
    )

    # Attach rate limiter
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ---------------------------------------------------------------------------
    # App-level singletons
    # ---------------------------------------------------------------------------
    if language_router is None:
        try:
            pipelines: dict = {}

            # English pipeline (always required)
            english_service = PredictionService(language="en")
            pipelines["en"] = english_service
            logger.info("Loaded English PredictionService.")

            # Hindi native pipeline
            try:
                hindi_service = PredictionService(language="hi")
                pipelines["hi"] = hindi_service
                logger.info("Loaded Hindi PredictionService.")
            except Exception as exc:
                logger.warning("Hindi model artifacts not found — Hindi unsupported: %s", exc)

            # Telugu native pipeline
            try:
                telugu_service = PredictionService(language="te")
                pipelines["te"] = telugu_service
                logger.info("Loaded Telugu PredictionService.")
            except Exception as exc:
                logger.warning("Telugu model artifacts not found — Telugu unsupported: %s", exc)

            language_router = LanguageRouter(pipelines)
            logger.info(
                "LanguageRouter ready with %d pipeline(s): %s",
                len(pipelines), list(pipelines.keys()),
            )
        except Exception as exc:
            logger.error("Failed to load PredictionService artifacts: %s", exc)
            language_router = LanguageRouter({})

    application.state.language_router = language_router
    application.state.trust_rater = trust_rater or TrustRater()
    application.state.fact_check_client = fact_check_client or FactCheckClient()
    application.state.repository = repository or _build_repository()

    # ---------------------------------------------------------------------------
    # Middleware (LIFO — last added = outermost)
    # Order outermost→innermost: CORS → CorrelationId → Auth → Timeout
    # ---------------------------------------------------------------------------
    # NOTE: TimeoutMiddleware is intentionally NOT added here — the per-route
    # timeouts (URL fetch, fact-check) are handled inside the route handlers
    # themselves via asyncio.wait_for. A blanket middleware timeout was causing
    # 504s on large Indic model predictions.
    application.add_middleware(AuthMiddleware)
    application.add_middleware(CorrelationIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------------------
    # Routers
    # ---------------------------------------------------------------------------
    from backend.routers.submissions import router as submissions_router  # noqa: PLC0415
    from backend.routers.history import router as history_router  # noqa: PLC0415
    from backend.routers.admin import router as admin_router  # noqa: PLC0415

    application.include_router(submissions_router)
    application.include_router(history_router)
    application.include_router(admin_router)

    # ---------------------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------------------

    @application.post("/api/v1/login", response_model=LoginResponse, tags=["Auth"])
    async def login(credentials: LoginRequest) -> LoginResponse:
        """Authenticate admin and return a JWT token."""
        if credentials.username != ADMIN_USERNAME or credentials.password != ADMIN_PASSWORD:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        expiration = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        token = jwt.encode(
            {"sub": credentials.username, "exp": expiration, "iat": datetime.utcnow()},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        return LoginResponse(access_token=token, token_type="bearer")

    @application.get("/api/v1/health", tags=["Health"])
    async def health() -> dict:
        """Liveness probe."""
        return {"status": "ok", "service": "Aletheia-Aegis"}

    return application


# ---------------------------------------------------------------------------
# Module-level app instance
# ---------------------------------------------------------------------------

app = create_app()
