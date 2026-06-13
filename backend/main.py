from __future__ import annotations

import ast
import base64
import contextvars
import hashlib
import html
import io
import json
import logging
import operator
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import requests
from database_adapter import DatabaseService, DatabaseSettings
from dotenv import load_dotenv
from fastapi.exceptions import RequestValidationError
from fastapi import File, Form, Header, HTTPException, Request, UploadFile
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field
from pypdf import PdfReader
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    import fitz
except Exception:
    fitz = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from ddgs import DDGS
except Exception:
    try:
        from duckduckgo_search import DDGS
    except Exception:
        DDGS = None

try:
    from ilovepdf import OfficePdfTask
except Exception:
    OfficePdfTask = None

try:
    from ilovepdf import PdfOfficeTask
except Exception:
    PdfOfficeTask = None

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("FEBGUY_DATA_DIR", BASE_DIR))
PROCESSED_DIR = DATA_DIR / "processed_files"
PROFILES_DIR = DATA_DIR / "profiles"
PROFILES_FILE = DATA_DIR / "profiles.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
LEGACY_MEMORY_FILE = DATA_DIR / "memory.json"
LEGACY_CHATS_FILE = DATA_DIR / "chats.json"
DATABASE_FILE = DATA_DIR / "febguy.db"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
RESEND_EMAIL_URL = "https://api.resend.com/emails"
try:
    POSTGRES_CONNECT_TIMEOUT = max(1, int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5") or "5"))
except ValueError:
    POSTGRES_CONNECT_TIMEOUT = 5
try:
    POSTGRES_STATEMENT_TIMEOUT_MS = max(
        1000,
        int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "5000") or "5000"),
    )
except ValueError:
    POSTGRES_STATEMENT_TIMEOUT_MS = 5000
try:
    POSTGRES_LOCK_TIMEOUT_MS = max(
        1000,
        int(os.getenv("POSTGRES_LOCK_TIMEOUT_MS", "3000") or "3000"),
    )
except ValueError:
    POSTGRES_LOCK_TIMEOUT_MS = 3000
try:
    POSTGRES_POOL_MAX_SIZE = max(
        1,
        int(os.getenv("POSTGRES_POOL_MAX_SIZE", "8") or "8"),
    )
except ValueError:
    POSTGRES_POOL_MAX_SIZE = 8
try:
    POSTGRES_POOL_TIMEOUT = max(
        1,
        int(os.getenv("POSTGRES_POOL_TIMEOUT", str(POSTGRES_CONNECT_TIMEOUT)) or str(POSTGRES_CONNECT_TIMEOUT)),
    )
except ValueError:
    POSTGRES_POOL_TIMEOUT = POSTGRES_CONNECT_TIMEOUT
DATABASE_PROVIDER = (
    os.getenv("DATABASE_PROVIDER")
    or os.getenv("FEBGUY_DATABASE_PROVIDER")
    or "sqlite"
).strip().lower() or "sqlite"

API_PUBLIC_BASE_URL = os.getenv("API_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("CHAT_MODEL", "llama-3.1-8b-instant")
CODE_MODEL = os.getenv("CODE_MODEL", "qwen/qwen3-32b")
VISION_MODEL = os.getenv("VISION_MODEL", "gemini-2.0-flash")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
STT_PROVIDER = os.getenv("STT_PROVIDER", "groq").lower()
STT_MODEL = os.getenv("STT_MODEL", "whisper-large-v3-turbo")
VOICE_CHAT_MODEL = os.getenv("VOICE_CHAT_MODEL", DEFAULT_MODEL)
FAST_MODEL = os.getenv("FAST_MODEL", DEFAULT_MODEL)
SMART_MODEL = os.getenv("SMART_MODEL", DEFAULT_MODEL)
DEEP_MODEL = os.getenv("DEEP_MODEL", SMART_MODEL or DEFAULT_MODEL)
RESPONSE_REFINER_MODEL = os.getenv("RESPONSE_REFINER_MODEL", SMART_MODEL or DEFAULT_MODEL)
ENABLE_RESPONSE_REFINER = os.getenv("ENABLE_RESPONSE_REFINER", "false").strip().lower() in {"1", "true", "yes", "on"}
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "browser")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
ILOVEPDF_PUBLIC_KEY = os.getenv("ILOVEPDF_PUBLIC_KEY")
ILOVEPDF_SECRET_KEY = os.getenv("ILOVEPDF_SECRET_KEY")
MAX_CHATS = int(os.getenv("FEBGUY_MAX_CHATS", "30"))
CONTEXT_LIMIT = int(os.getenv("FEBGUY_CONTEXT_LIMIT", "12000"))
META_PREFIX = "\n\n[[FEBGUY_META:"
META_SUFFIX = "]]"
STREAM_RESPONSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}
DEVICE_ID_HEADER = "X-FebGuy-Device-ID"
GUEST_LIMIT_MESSAGE = "You\u2019ve reached the guest limit. Sign in to continue."
GUEST_USAGE_LIMITS = {
    "chat": 10,
    "code": 4,
    "upload": 3,
}
try:
    MAX_UPLOAD_MB = max(1, int(os.getenv("FEBGUY_MAX_UPLOAD_MB", "10") or "10"))
except ValueError:
    MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_DOCUMENT_EXPANDED_BYTES = 50 * 1024 * 1024
VALID_RESPONSE_MODES = {"balanced", "deep", "creative", "teacher", "coding", "human"}
VALID_MODEL_MODES = {"fast", "smart", "deep"}
RESPONSE_MODE_INSTRUCTIONS = {
    "balanced": (
        "Use a professional, friendly, balanced answer. Answer directly first, then add only the detail "
        "needed to make the response useful."
    ),
    "deep": (
        "Give a deeper answer with reasoning, tradeoffs, examples, and practical implications. Stay grounded "
        "in the available evidence and avoid padding."
    ),
    "creative": (
        "Offer thoughtful ideas, alternatives, and original framing while staying useful, realistic, and "
        "factually careful."
    ),
    "teacher": (
        "Teach step by step. Define important terms, use simple examples, and check that the explanation "
        "builds from basics to the final answer."
    ),
    "coding": (
        "Be implementation-focused and precise. Prefer code, diagnostics, edge cases, and exact fix steps "
        "over broad theory unless the user asks for theory."
    ),
    "human": (
        "Sound natural and conversational. Keep simple replies brief, adapt to the user's wording, and avoid "
        "fake emotions or robotic phrasing."
    ),
}


def normalize_response_mode(response_mode: str | None) -> str:
    normalized = (response_mode or "balanced").strip().lower()
    if normalized in VALID_RESPONSE_MODES:
        return normalized
    return "balanced"


def normalize_model_mode(model_mode: str | None) -> str:
    normalized = (model_mode or "smart").strip().lower()
    if normalized in VALID_MODEL_MODES:
        return normalized
    return "smart"


def response_mode_instruction(response_mode: str | None = None) -> str:
    mode = normalize_response_mode(response_mode)
    return f"Response mode: {mode}\n{RESPONSE_MODE_INSTRUCTIONS[mode]}"


def select_chat_model(
    response_mode: str = "balanced",
    model_mode: str | None = None,
    intent: str = "",
    answer_mode: str = "",
    has_file_context: bool = False,
    has_search_context: bool = False,
    has_images: bool = False,
    is_voice: bool = False,
) -> str:
    """Pick a configured model tier without breaking existing default routing."""
    mode = normalize_response_mode(response_mode)
    quality_mode = normalize_model_mode(model_mode) if model_mode is not None else ""
    normalized_intent = (intent or "").strip().lower()
    normalized_answer_mode = (answer_mode or "").strip().lower()

    def configured(model_name: str | None, fallback: str = DEFAULT_MODEL) -> str:
        return (model_name or "").strip() or fallback

    if has_images:
        return configured(VISION_MODEL, DEFAULT_MODEL)
    if mode == "coding" or normalized_intent in {"coding_help", "code_help", "coding", "code"}:
        return configured(CODE_MODEL, DEFAULT_MODEL)
    if quality_mode == "fast":
        return configured(FAST_MODEL, DEFAULT_MODEL)
    if quality_mode == "smart":
        return configured(SMART_MODEL, DEFAULT_MODEL)
    if quality_mode == "deep":
        return configured(DEEP_MODEL, SMART_MODEL or DEFAULT_MODEL)
    if is_voice:
        return configured(VOICE_CHAT_MODEL, FAST_MODEL or DEFAULT_MODEL)
    if mode == "deep" or normalized_answer_mode in {"deep", "detailed"}:
        return configured(DEEP_MODEL, SMART_MODEL or DEFAULT_MODEL)
    if has_file_context or has_search_context or mode in {"teacher", "creative", "human"}:
        return configured(SMART_MODEL, DEFAULT_MODEL)
    return configured(DEFAULT_MODEL)
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".txt"}
DISALLOWED_UPLOAD_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".zip"}
CODE_CONTEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".html",
    ".css",
    ".json",
    ".md",
    ".txt",
    ".sql",
    ".yml",
    ".yaml",
    ".toml",
}
GENERATED_CODE_DOWNLOAD_EXTENSIONS = CODE_CONTEXT_EXTENSIONS | {".md"}
ALLOWED_DOWNLOAD_EXTENSIONS = ALLOWED_UPLOAD_EXTENSIONS | GENERATED_CODE_DOWNLOAD_EXTENSIONS
UPLOAD_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg", "image/jpg"},
    ".jpeg": {"image/jpeg", "image/jpg"},
    ".txt": {"text/plain"},
}
CANONICAL_UPLOAD_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
}
GENERIC_UPLOAD_MIME_TYPES = {"", "application/octet-stream"}
CODE_CONTEXT_MIME_TYPES = {
    "",
    "application/json",
    "application/octet-stream",
    "application/sql",
    "application/x-c",
    "application/x-c++",
    "application/x-javascript",
    "application/x-python",
    "application/xml",
    "text/css",
    "text/html",
    "text/javascript",
    "text/jsx",
    "text/markdown",
    "text/plain",
    "text/typescript",
    "text/tsx",
    "text/x-c",
    "text/x-c++",
    "text/x-java-source",
    "text/x-python",
    "text/xml",
    "text/yaml",
}
CODE_LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "py": ".py",
    "javascript": ".js",
    "js": ".js",
    "jsx": ".jsx",
    "typescript": ".ts",
    "ts": ".ts",
    "tsx": ".tsx",
    "c": ".c",
    "cpp": ".cpp",
    "c++": ".cpp",
    "java": ".java",
    "html": ".html",
    "css": ".css",
    "json": ".json",
    "markdown": ".md",
    "md": ".md",
    "sql": ".sql",
    "yaml": ".yaml",
    "yml": ".yml",
    "toml": ".toml",
    "text": ".txt",
    "txt": ".txt",
}
ACCOUNT_SHARED_VOICE_SETTINGS = {"voiceEnabled", "sentenceVoice"}
DEVICE_PROFILE_LIMIT = 3
DEVICE_PROFILE_NOT_FOUND = "Profile does not exist on this device."
PIN_HASH_ITERATIONS = 200_000
PIN_RESET_CODE_TTL_SECONDS = 10 * 60
PIN_RESET_CODE_LENGTH = 6
SESSION_MODES = {"guest", "account", "profile"}


def env_positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default)) or str(default)))
    except ValueError:
        return default


MAX_REQUEST_MB = max(MAX_UPLOAD_MB + 1, env_positive_int("FEBGUY_MAX_REQUEST_MB", 20))
MAX_REQUEST_BYTES = MAX_REQUEST_MB * 1024 * 1024
MAX_MESSAGE_CHARS = env_positive_int("FEBGUY_MAX_MESSAGE_CHARS", 24000)
STREAM_CHAT_CONTEXT_MESSAGES = env_positive_int("FEBGUY_STREAM_CHAT_CONTEXT_MESSAGES", 14)
STREAM_CODE_CONTEXT_MESSAGES = env_positive_int("FEBGUY_STREAM_CODE_CONTEXT_MESSAGES", 12)
MAX_CHAT_TITLE_CHARS = 160
MAX_CHAT_ID_CHARS = 128
MAX_PROFILE_NAME_CHARS = 80
MAX_PIN_CHARS = 128
MAX_MEMORY_TEXT_CHARS = 4000
MAX_AUTH_TOKEN_CHARS = 8192
MAX_CODE_CONTEXT_FILES = 12
MAX_CODE_CONTEXT_FILE_BYTES = env_positive_int("FEBGUY_MAX_CODE_FILE_KB", 256) * 1024
MAX_CODE_CONTEXT_CHARS = env_positive_int("FEBGUY_MAX_CODE_CONTEXT_CHARS", 18000)
MAX_GENERATED_CODE_FILES = 4

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    "login": (env_positive_int("FEBGUY_RATE_LOGIN_REQUESTS", 10), 300),
    "profile_pin": (env_positive_int("FEBGUY_RATE_PIN_REQUESTS", 8), 300),
    "profile_pin_reset": (env_positive_int("FEBGUY_RATE_PIN_RESET_REQUESTS", 12), 300),
    "guest_chat": (env_positive_int("FEBGUY_RATE_GUEST_CHAT_REQUESTS", 20), 60),
    "upload": (env_positive_int("FEBGUY_RATE_UPLOAD_REQUESTS", 15), 60),
    "ai": (env_positive_int("FEBGUY_RATE_AI_REQUESTS", 45), 60),
}
RATE_LIMIT_LABELS = {
    "login": "sign-in attempts",
    "profile_pin": "PIN attempts",
    "profile_pin_reset": "PIN reset attempts",
    "guest_chat": "guest messages",
    "upload": "file uploads",
    "ai": "AI requests",
}
# This process-local limiter protects a single backend instance. Use a shared
# limiter when running multiple production workers.
RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_BUCKETS: dict[tuple[str, str], deque[float]] = defaultdict(deque)

LOGGER = logging.getLogger("febguy.api")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

try:
    SLOW_ENDPOINT_LOG_MS = max(
        250,
        int(os.getenv("SLOW_ENDPOINT_LOG_MS", "2000") or "2000"),
    )
except ValueError:
    SLOW_ENDPOINT_LOG_MS = 2000
REQUEST_DB_TIME: contextvars.ContextVar[float] = contextvars.ContextVar("request_db_time", default=0.0)
REQUEST_AI_TIME: contextvars.ContextVar[float] = contextvars.ContextVar("request_ai_time", default=0.0)
REQUEST_TIMING_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_timing_id", default=None)
REQUEST_TIMING_TOTALS: dict[str, dict[str, float]] = {}
REQUEST_TIMING_LOCK = threading.Lock()
DATA_LOCK = threading.RLock()
DATABASE_INITIALIZED = False
SESSION_ACCESS_CACHE_SECONDS = 120
SESSION_ACCESS_CACHE: dict[str, dict[str, Any]] = {}
SESSION_ACCESS_LOCK = threading.Lock()
GUEST_DEVICE_SESSION_CACHE: dict[str, dict[str, Any]] = {}
GUEST_DEVICE_SESSION_LOCK = threading.Lock()
DEVICE_ROW_CACHE: set[str] = set()
DEVICE_ROW_CACHE_LOCK = threading.Lock()
GUEST_USAGE_STATUS_CACHE_SECONDS = 10
GUEST_USAGE_STATUS_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
GUEST_USAGE_STATUS_LOCK = threading.Lock()
WORKSPACE_CONTEXT_CACHE_SECONDS = 30
SETTINGS_CACHE: dict[str, dict[str, Any]] = {}
MEMORY_CACHE: dict[str, dict[str, Any]] = {}
WORKSPACE_CONTEXT_CACHE_LOCK = threading.Lock()
TABLE_COLUMN_CACHE: dict[tuple[str, str], set[str]] = {}
TABLE_COLUMN_LOCK = threading.Lock()
POSTGRES_KNOWN_TABLE_COLUMNS: dict[str, set[str]] = {
    "devices": {
        "id",
        "client_device_id",
        "device_id",
        "created_at",
        "updated_at",
        "last_seen_at",
    },
    "sessions": {
        "token",
        "token_hash",
        "profile_id",
        "user_id",
        "mode",
        "guest_id",
        "device_id",
        "created_at",
        "last_seen_at",
    },
    "usage_limits": {
        "id",
        "guest_id",
        "device_id",
        "limit_key",
        "period_start",
        "period_end",
        "used_count",
        "max_count",
        "metadata",
        "created_at",
        "updated_at",
    },
    "files": {
        "id",
        "profile_id",
        "user_id",
        "guest_id",
        "device_id",
        "file_name",
        "original_name",
        "file_type",
        "mime_type",
        "path",
        "storage_path",
        "document_id",
        "size_bytes",
        "metadata",
        "created_at",
        "updated_at",
    },
}
GUEST_BACKGROUND_SETUP_DELAY_SECONDS = 15.0
try:
    DATABASE_HEALTH_CACHE_SECONDS = max(
        1,
        int(os.getenv("DATABASE_HEALTH_CACHE_SECONDS", "15") or "15"),
    )
except ValueError:
    DATABASE_HEALTH_CACHE_SECONDS = 15
DATABASE_HEALTH_LOCK = threading.Lock()
DATABASE_HEALTH_CACHE: dict[str, Any] = {"checked_at": 0.0, "status": None}

DATABASE = DatabaseService(
    DatabaseSettings(
        sqlite_path=DATABASE_FILE,
        database_url=DATABASE_URL,
        provider=DATABASE_PROVIDER,
        connect_timeout=POSTGRES_CONNECT_TIMEOUT,
        statement_timeout_ms=POSTGRES_STATEMENT_TIMEOUT_MS,
        lock_timeout_ms=POSTGRES_LOCK_TIMEOUT_MS,
        pool_max_size=POSTGRES_POOL_MAX_SIZE,
        pool_timeout=POSTGRES_POOL_TIMEOUT,
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_ANON_KEY,
        supabase_service_role_key=SUPABASE_SERVICE_ROLE_KEY,
    )
)


def validate_device_id(device_id: str | None) -> str | None:
    raw = (device_id or "").strip()
    if not raw:
        return None

    if len(raw) > 64:
        raise HTTPException(status_code=400, detail="Invalid device ID.")

    try:
        return str(uuid.UUID(raw))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID.")


def resolve_device_id(*values: str | None) -> str | None:
    normalized = [value for value in (validate_device_id(item) for item in values) if value]
    if not normalized:
        return None
    if len(set(normalized)) > 1:
        raise HTTPException(status_code=400, detail="Conflicting device IDs.")
    return normalized[0]

WINDOWS_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
SCANNED_PDF_OCR_UNAVAILABLE_MESSAGE = (
    "This appears to be a scanned or image-only PDF. No embedded text was found, "
    "and OCR is unavailable on this server because the Tesseract executable is "
    "not installed or is not in PATH."
)
PDF_TEXT_UNAVAILABLE_MESSAGE = (
    "No readable text was found in this PDF. If it is scanned or image-only, OCR is required."
)
IMAGE_OCR_UNAVAILABLE_MESSAGE = (
    "Image OCR is unavailable because the Tesseract executable is not installed or is not in PATH."
)
CONVERSION_TIMEOUT_SECONDS = 120


def resolve_executable(*candidates: str | None) -> str | None:
    for candidate in candidates:
        command = str(candidate or "").strip()
        if not command:
            continue
        if Path(command).exists():
            return command
        found = shutil.which(command)
        if found:
            return found
    return None


TESSERACT_CMD = resolve_executable(os.getenv("TESSERACT_CMD"), "tesseract", WINDOWS_TESSERACT_CMD)
PANDOC_CMD = resolve_executable(os.getenv("PANDOC_CMD"), "pandoc")
PRINCE_CMD = resolve_executable(os.getenv("PRINCE_CMD"), "prince", "princexml")

if pytesseract is not None and TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def ocr_available() -> bool:
    return pytesseract is not None and bool(TESSERACT_CMD)


def cloud_docx_to_pdf_available() -> bool:
    return bool(OfficePdfTask is not None and ILOVEPDF_PUBLIC_KEY and ILOVEPDF_SECRET_KEY)


def cloud_pdf_to_docx_available() -> bool:
    return bool(PdfOfficeTask is not None and ILOVEPDF_PUBLIC_KEY and ILOVEPDF_SECRET_KEY)


def local_docx_to_pdf_available() -> bool:
    return bool(PANDOC_CMD and PRINCE_CMD)


def error_code_for_status(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "request_too_large",
        415: "unsupported_file_type",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_error",
        502: "upstream_error",
        503: "service_unavailable",
    }.get(status_code, "request_failed")


def public_error_message(detail: Any, fallback: str = "Request could not be completed.") -> str:
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return fallback


def structured_error_response(
    status_code: int,
    detail: Any,
    *,
    request: Request | None = None,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    message = public_error_message(detail)
    error: dict[str, str] = {
        "code": code or error_code_for_status(status_code),
        "message": message,
    }
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    if request_id:
        error["request_id"] = request_id
    # Keep detail in Phase 11 so the existing frontend renders friendly messages.
    response_headers = dict(headers or {})
    if request_id:
        response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": error, "detail": message},
        headers=response_headers,
    )


def rate_limit_identity(request: Request, profile: dict[str, Any] | None = None) -> str:
    device_id = getattr(request.state, "device_id", None)
    if profile and profile.get("is_guest"):
        return f"guest:{profile.get('guest_id') or profile.get('id')}:{device_id or 'missing-device'}"
    if profile:
        return f"profile:{profile.get('id')}"
    client_host = request.client.host if request.client else "unknown-client"
    return f"client:{device_id or client_host}"


def enforce_rate_limit(
    request: Request,
    bucket: str,
    profile: dict[str, Any] | None = None,
) -> None:
    limit, window_seconds = RATE_LIMIT_RULES[bucket]
    identity = rate_limit_identity(request, profile)
    now = time.monotonic()
    key = (bucket, identity)
    with RATE_LIMIT_LOCK:
        requests_in_window = RATE_LIMIT_BUCKETS[key]
        while requests_in_window and requests_in_window[0] <= now - window_seconds:
            requests_in_window.popleft()
        if len(requests_in_window) >= limit:
            retry_after = max(1, int(window_seconds - (now - requests_in_window[0])) + 1)
            LOGGER.warning("Rate limit exceeded: bucket=%s identity=%s", bucket, identity)
            raise HTTPException(
                status_code=429,
                detail=f"Too many {RATE_LIMIT_LABELS[bucket]}. Please wait and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        requests_in_window.append(now)


def validate_chat_id(chat_id: str) -> str:
    value = str(chat_id or "").strip()
    if not value or len(value) > MAX_CHAT_ID_CHARS:
        raise HTTPException(status_code=400, detail="Invalid chat ID.")
    return value


def validate_message_length(message: str) -> str:
    value = str(message or "")
    if len(value) > MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Message is too long. Maximum length is {MAX_MESSAGE_CHARS} characters.",
        )
    return value


app = FastAPI(title="FebGuy AI Backend")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
if "*" in ALLOWED_ORIGINS:
    LOGGER.warning("CORS_ORIGINS contains '*'. Configure explicit production origins before deployment.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials="*" not in ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", DEVICE_ID_HEADER],
)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        LOGGER.error(
            "API error request_id=%s method=%s path=%s status=%s",
            getattr(request.state, "request_id", "unknown"),
            request.method,
            request.url.path,
            exc.status_code,
        )
    return structured_error_response(
        exc.status_code,
        exc.detail,
        request=request,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    LOGGER.info(
        "Invalid request request_id=%s method=%s path=%s",
        getattr(request.state, "request_id", "unknown"),
        request.method,
        request.url.path,
    )
    return structured_error_response(
        422,
        "Request data is invalid.",
        request=request,
        code="validation_error",
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    LOGGER.exception(
        "Unhandled API error request_id=%s method=%s path=%s",
        getattr(request.state, "request_id", "unknown"),
        request.method,
        request.url.path,
    )
    return structured_error_response(
        500,
        "An unexpected server error occurred. Please try again.",
        request=request,
        code="internal_error",
    )


@app.middleware("http")
async def attach_device_context(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    REQUEST_DB_TIME.set(0.0)
    REQUEST_AI_TIME.set(0.0)
    timing_token = REQUEST_TIMING_ID.set(request.state.request_id)
    with REQUEST_TIMING_LOCK:
        REQUEST_TIMING_TOTALS[request.state.request_id] = {"db": 0.0, "ai": 0.0}
    started_at = time.perf_counter()
    try:
        content_length = request.headers.get("content-length", "").strip()
        if content_length:
            try:
                body_size = int(content_length)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid request size header.")
            if body_size > MAX_REQUEST_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request is too large. Maximum request size is {MAX_REQUEST_MB} MB.",
                )
        request.state.device_id = validate_device_id(request.headers.get(DEVICE_ID_HEADER))
        enforce_device_bound_session_access(
            request.headers.get("Authorization"),
            request.state.device_id,
        )
    except HTTPException as exc:
        return structured_error_response(
            exc.status_code,
            exc.detail,
            request=request,
            headers=exc.headers,
        )
    try:
        response = await call_next(request)
        return response
    finally:
        total_ms = (time.perf_counter() - started_at) * 1000
        with REQUEST_TIMING_LOCK:
            totals = REQUEST_TIMING_TOTALS.pop(request.state.request_id, {"db": REQUEST_DB_TIME.get(), "ai": REQUEST_AI_TIME.get()})
        REQUEST_TIMING_ID.reset(timing_token)
        db_ms = totals.get("db", 0.0) * 1000
        ai_ms = totals.get("ai", 0.0) * 1000
        if total_ms >= SLOW_ENDPOINT_LOG_MS:
            LOGGER.info(
                "slow_endpoint endpoint=%s method=%s status=%s db_ms=%.1f ai_ms=%.1f total_ms=%.1f",
                request.url.path,
                request.method,
                getattr(locals().get("response", None), "status_code", "unknown"),
                db_ms,
                ai_ms,
                total_ms,
            )
        if "response" in locals():
            response.headers["X-Request-ID"] = request.state.request_id


SYSTEM_PROMPT = """
You are FebGuy AI, a private AI workspace assistant created by Pranav Amble.

Core identity:
- FebGuy AI was created, founded, and is owned by Pranav Amble.
- Mention that only when the user asks about FebGuy AI, its owner, creator, founder, or Pranav Amble.

Personality:
- Professional, friendly, thoughtful, practical, and natural.
- Adapt to the user's tone instead of sounding robotic.
- Be concise for simple messages and structured for serious work.

Behavior:
- Understand the user's intent, tone, current chat context, and available tools before answering.
- Infer obvious typos when the meaning is clear, especially casual chat and search/news requests.
- Treat short follow-ups and references like "he", "it", "that", "pm", "same", "above",
  "previous", "this file", and "that answer" as part of the current chat when recent context exists.
- For greetings, thanks, banter, or small talk, reply in one or two natural sentences.
- For casual messages like "yo brother","yo bro","hello bro", "thanks", "good night",
  "I just want to talk", or "I do coding", respond socially instead of forcing
  a task, search, or document workflow.
- Ask a clarifying question only when the request truly cannot be answered safely or accurately.
- Do not start with filler like "It seems like", "It sounds like", or "Sure, here's" when a direct answer is possible.
- Use provided search results, document context, calculator output, weather output, and memory when relevant.
- Use memory selectively. It should help with personal preferences, ongoing projects, coding/deployment
  context, and identity details, but it should not dominate unrelated answers.
- Do not invent source links, file names, page numbers, tool results, or private data.
- If current search evidence is provided, answer from it and do not say you lack real-time access.
- If current search evidence is needed but unavailable, say what could not be verified.

Formatting:
- Do not output internal separators, templates, or decorative marker lines.
- Do not use headings, bullets, or "Next steps" for casual chat.
- Use numbered steps only for ordered procedures.
- Use bullets for unordered details and indented bullets only for sub-points.
- Keep Markdown clean; do not over-bold every line or overuse heading markers.
- Add "Next steps" only for plans, troubleshooting, research, or workflows where action matters.
- Never force a Summary, Key points, or Next steps section into simple chat, identity answers, greetings, thanks, or short factual replies.
""".strip()

CREATOR_BRIEF = (
    "Pranav Amble is the creator, founder, and owner of FebGuy AI. "
    "He built FebGuy AI as a helpful AI assistant for chat, voice, files, web search, "
    "memory, and document tools."
)


DEFAULT_SETTINGS = {
    "voiceEnabled": True,
    "sentenceVoice": True,
    "searchEnabled": True,
    "ragEnabled": True,
    "voiceName": "",
    "voiceSpeed": "normal",
    "lastSpokenResponse": "",
    "theme": "midnight",
}

BANNED_GENERIC_SUGGESTIONS = {
    "Explain this more simply",
    "Give me step-by-step help",
    "Turn this into an action plan",
}


class ChatCreateRequest(BaseModel):
    title: str = Field(default="New Chat", max_length=MAX_CHAT_TITLE_CHARS)


class ProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_PROFILE_NAME_CHARS)
    pin: str = Field(min_length=1, max_length=MAX_PIN_CHARS)


class ProfileLoginRequest(BaseModel):
    profile_id: str | None = Field(default=None, max_length=MAX_CHAT_ID_CHARS)
    profile_name: str | None = Field(default=None, max_length=MAX_PROFILE_NAME_CHARS)
    pin: str = Field(min_length=1, max_length=MAX_PIN_CHARS)


class ProfileDeleteRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=MAX_PIN_CHARS)


class ProfilePinResetStartRequest(BaseModel):
    profile_id: str = Field(min_length=1, max_length=MAX_CHAT_ID_CHARS)


class ProfilePinResetVerifyRequest(BaseModel):
    profile_id: str = Field(min_length=1, max_length=MAX_CHAT_ID_CHARS)
    code: str = Field(min_length=4, max_length=16)


class ProfilePinResetCompleteRequest(BaseModel):
    profile_id: str = Field(min_length=1, max_length=MAX_CHAT_ID_CHARS)
    code: str = Field(min_length=4, max_length=16)
    new_pin: str = Field(min_length=4, max_length=MAX_PIN_CHARS)


class AccountSessionRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=MAX_AUTH_TOKEN_CHARS)


class ChatUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_CHAT_TITLE_CHARS)
    pinned: bool | None = None


class CodeChatRequest(BaseModel):
    chat_id: str = Field(min_length=1, max_length=MAX_CHAT_ID_CHARS)
    message: str = Field(default="", max_length=MAX_MESSAGE_CHARS)


class MemoryUpdateRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    facts: list[dict[str, Any]] | None = None


class MemoryFactRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MEMORY_TEXT_CHARS)


class SettingsUpdateRequest(BaseModel):
    voiceEnabled: bool | None = None
    sentenceVoice: bool | None = None
    searchEnabled: bool | None = None
    ragEnabled: bool | None = None
    voiceName: str | None = Field(default=None, max_length=180)
    voiceSpeed: str | None = Field(default=None, max_length=20)
    lastSpokenResponse: str | None = Field(default=None, max_length=3000)
    theme: str | None = None


class RoutePreviewRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_CHARS)
    hasFileContext: bool = False
    hasSearchContext: bool = False


def model_to_update(data: BaseModel) -> dict[str, Any]:
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_none=True)
    return data.dict(exclude_none=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    init_database()


def load_json(path: Path, default: Any) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup_path = path.with_suffix(path.suffix + ".broken")
        path.replace(backup_path)
        return default


def save_json(path: Path, data: Any) -> None:
    with DATA_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_path.replace(path)


def encode_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def decode_json(raw: str | None, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def clone_json_compatible(data: Any) -> Any:
    return json.loads(json.dumps(data))


def elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def cache_get(cache: dict[str, dict[str, Any]], key: str) -> Any | None:
    with WORKSPACE_CONTEXT_CACHE_LOCK:
        cached = cache.get(key)
        if not cached:
            return None
        if time.monotonic() - float(cached.get("checked_at") or 0.0) > WORKSPACE_CONTEXT_CACHE_SECONDS:
            cache.pop(key, None)
            return None
        return clone_json_compatible(cached["value"])


def cache_set(cache: dict[str, dict[str, Any]], key: str, value: Any) -> None:
    with WORKSPACE_CONTEXT_CACHE_LOCK:
        cache[key] = {
            "checked_at": time.monotonic(),
            "value": clone_json_compatible(value),
        }


def cache_clear(cache: dict[str, dict[str, Any]], key: str) -> None:
    with WORKSPACE_CONTEXT_CACHE_LOCK:
        cache.pop(key, None)


def add_request_db_time(elapsed: float) -> None:
    REQUEST_DB_TIME.set(REQUEST_DB_TIME.get() + elapsed)
    request_id = REQUEST_TIMING_ID.get()
    if request_id:
        with REQUEST_TIMING_LOCK:
            totals = REQUEST_TIMING_TOTALS.setdefault(request_id, {"db": 0.0, "ai": 0.0})
            totals["db"] += elapsed


def add_request_ai_time(elapsed: float) -> None:
    REQUEST_AI_TIME.set(REQUEST_AI_TIME.get() + elapsed)
    request_id = REQUEST_TIMING_ID.get()
    if request_id:
        with REQUEST_TIMING_LOCK:
            totals = REQUEST_TIMING_TOTALS.setdefault(request_id, {"db": 0.0, "ai": 0.0})
            totals["ai"] += elapsed


class TimedDatabaseConnection:
    def __init__(self, conn: Any):
        self._conn = conn

    def __enter__(self):
        if hasattr(self._conn, "__enter__"):
            self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if hasattr(self._conn, "__exit__"):
            return self._conn.__exit__(exc_type, exc, traceback)
        self.close()
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return self._conn.execute(*args, **kwargs)
        finally:
            add_request_db_time(time.perf_counter() - start)

    def executemany(self, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return self._conn.executemany(*args, **kwargs)
        finally:
            add_request_db_time(time.perf_counter() - start)

    def executescript(self, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return self._conn.executescript(*args, **kwargs)
        finally:
            add_request_db_time(time.perf_counter() - start)


def db_connect() -> Any:
    return TimedDatabaseConnection(DATABASE.connect())


def data_write_lock():
    return DATA_LOCK if DATABASE.is_sqlite_active() else nullcontext()


def postgres_connect():
    return DATABASE.postgres_connect()


def supabase_config_status() -> dict[str, Any]:
    return DATABASE.supabase_status()


def postgres_health_status() -> dict[str, Any]:
    return DATABASE.postgres_health()


def database_health_status(*, force: bool = False) -> dict[str, Any]:
    checked_at = float(DATABASE_HEALTH_CACHE.get("checked_at") or 0.0)
    cached_status = DATABASE_HEALTH_CACHE.get("status")
    if (
        not force
        and isinstance(cached_status, dict)
        and time.monotonic() - checked_at < DATABASE_HEALTH_CACHE_SECONDS
    ):
        return dict(cached_status)

    if not force and DATABASE.is_postgres_active():
        status = {
            "active_provider": "postgres" if DATABASE_URL else "unavailable",
            "requested_provider": DATABASE.requested_provider,
            "database_url_required": True,
            "sqlite_available": False,
            "postgres_configured": bool(DATABASE_URL),
            "postgres_connected": bool(DATABASE_URL),
            "sqlite": {"available": False, "configured": True, "status": "inactive"},
            "postgres": {
                "configured": bool(DATABASE_URL),
                "connected": bool(DATABASE_URL),
                "status": "configured_fast_health" if DATABASE_URL else "not_configured",
            },
            "supabase": supabase_config_status(),
            "migration_mode": "postgres_active",
        }
        with DATABASE_HEALTH_LOCK:
            DATABASE_HEALTH_CACHE["checked_at"] = time.monotonic()
            DATABASE_HEALTH_CACHE["status"] = dict(status)
        return status

    status = DATABASE.safe_health()
    with DATABASE_HEALTH_LOCK:
        DATABASE_HEALTH_CACHE["checked_at"] = time.monotonic()
        DATABASE_HEALTH_CACHE["status"] = dict(status)
    return status


def database_error_hint(exc: Exception) -> str:
    raw = str(exc).replace("\n", " ").strip()
    parts = [type(exc).__name__]
    for label, pattern in (
        ("table", r'(?:relation|table) "([^"]+)"'),
        ("column", r'column "([^"]+)"'),
        ("constraint", r'constraint "([^"]+)"'),
        ("detail", r"DETAIL:\s*([^;]+)"),
    ):
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            parts.append(f"{label}={match.group(1)[:160]}")
    if len(parts) == 1 and raw:
        parts.append(raw[:240])
    return " ".join(parts)


POSTGRES_CORE_TABLES = (
    "profiles",
    "sessions",
    "guest_sessions",
    "usage_limits",
    "settings",
    "memories",
    "chats",
    "messages",
    "code_chats",
    "code_messages",
    "code_project_files",
    "documents",
    "files",
)
POSTGRES_SCHEMA_VERSION = "session-flow-2026-06-07"
POSTGRES_RUNTIME_REPAIR_SQL = """
create table if not exists public.meta (
  key text primary key,
  value text not null
);
create table if not exists public.devices (
  id uuid primary key,
  client_device_id text not null unique,
  device_id text unique,
  created_at text not null,
  updated_at text,
  last_seen_at text
);
alter table public.devices add column if not exists id text;
alter table public.devices add column if not exists client_device_id text;
alter table public.devices add column if not exists device_id text;
alter table public.devices add column if not exists created_at text;
alter table public.devices add column if not exists updated_at text;
alter table public.devices add column if not exists last_seen_at text;
alter table public.sessions add column if not exists token_hash text;
update public.devices
set client_device_id = coalesce(
  nullif(client_device_id, ''),
  nullif(device_id, ''),
  nullif(id::text, ''),
  'legacy-' || replace(replace(ctid::text, '(', ''), ')', '')
)
where client_device_id is null or client_device_id = '';
update public.devices
set device_id = client_device_id
where device_id is null or device_id = '';
update public.sessions
set token_hash = 'legacy-md5:' || md5(token)
where (token_hash is null or token_hash = '') and token is not null;
update public.sessions
set token_hash = 'missing-token'
where token_hash is null or token_hash = '';
alter table public.devices alter column client_device_id set not null;
alter table public.sessions alter column token_hash set default '';
alter table public.sessions alter column token_hash set not null;
create unique index if not exists idx_meta_key_unique
  on public.meta(key);
create unique index if not exists idx_devices_id_unique
  on public.devices(id);
create unique index if not exists idx_devices_client_device_id_unique
  on public.devices(client_device_id);
create unique index if not exists idx_devices_device_id_unique
  on public.devices(device_id)
  where device_id is not null;
create unique index if not exists idx_profiles_id_unique
  on public.profiles(id);
create unique index if not exists idx_sessions_token_unique
  on public.sessions(token);
create unique index if not exists idx_guest_sessions_guest_id_unique
  on public.guest_sessions(guest_id);
create unique index if not exists idx_guest_sessions_device_id_unique
  on public.guest_sessions(device_id);
create unique index if not exists idx_guest_sessions_profile_id_unique
  on public.guest_sessions(profile_id);
create unique index if not exists idx_settings_profile_id_unique
  on public.settings(profile_id);
create unique index if not exists idx_memories_profile_id_unique
  on public.memories(profile_id);
create unique index if not exists idx_chats_id_unique
  on public.chats(id);
create unique index if not exists idx_code_chats_id_unique
  on public.code_chats(id);
create unique index if not exists idx_files_id_unique
  on public.files(id);
create unique index if not exists idx_files_path_unique
  on public.files(path);
create unique index if not exists idx_documents_id_unique
  on public.documents(id);
create unique index if not exists idx_code_project_files_id_unique
  on public.code_project_files(id);
create unique index if not exists idx_usage_limits_guest_device_key_unique
  on public.usage_limits(guest_id, device_id, limit_key);
alter table public.usage_limits add column if not exists period_start timestamptz;
alter table public.usage_limits add column if not exists period_end timestamptz;
alter table public.usage_limits add column if not exists metadata jsonb not null default '{}'::jsonb;
"""


def postgres_core_schema_exists(conn: sqlite3.Connection) -> bool:
    table_list = ", ".join(f"'{table}'" for table in POSTGRES_CORE_TABLES)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ({table_list})
        """
    ).fetchone()
    return bool(row and int(row["table_count"]) == len(POSTGRES_CORE_TABLES))


def postgres_schema_version(conn: sqlite3.Connection) -> str | None:
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    return row["value"] if row and row["value"] else None


def mark_postgres_schema_initialized(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO meta(key, value)
        VALUES('schema_initialized_at', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (timestamp,),
    )
    conn.execute(
        """
        INSERT INTO meta(key, value)
        VALUES('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (POSTGRES_SCHEMA_VERSION,),
    )


def init_postgres_database() -> None:
    schema_path = BASE_DIR / "supabase_schema.sql"
    if not schema_path.exists():
        raise RuntimeError("Supabase/Postgres schema file is missing.")

    with db_connect() as conn:
        schema_version = postgres_schema_version(conn)
        if schema_version == POSTGRES_SCHEMA_VERSION:
            return

        if postgres_core_schema_exists(conn):
            if schema_version != POSTGRES_SCHEMA_VERSION:
                conn.executescript(POSTGRES_RUNTIME_REPAIR_SQL)
        else:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
        mark_postgres_schema_initialized(conn)


def init_database() -> None:
    global DATABASE_INITIALIZED
    if DATABASE_INITIALIZED:
        return

    with DATA_LOCK:
        if DATABASE_INITIALIZED:
            return

        if DATABASE.is_postgres_active():
            init_postgres_database()
            DATABASE_INITIALIZED = True
            return

        with db_connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pin_salt TEXT NOT NULL,
                    pin_hash TEXT NOT NULL,
                    profile_kind TEXT NOT NULL DEFAULT 'legacy',
                    user_id TEXT,
                    device_id TEXT,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'profile',
                    guest_id TEXT,
                    device_id TEXT,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    auth_user_id TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    onboarding_completed INTEGER NOT NULL DEFAULT 0,
                    workspace_profile_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT,
                    FOREIGN KEY(workspace_profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS account_sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS profile_pin_reset_codes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    code_salt TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS guest_sessions (
                    guest_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL UNIQUE,
                    profile_id TEXT NOT NULL UNIQUE,
                    session_token TEXT,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_token) REFERENCES sessions(token) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS usage_limits (
                    id TEXT PRIMARY KEY,
                    guest_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    limit_key TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
                    max_count INTEGER NOT NULL CHECK (max_count >= 0),
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (guest_id, device_id, limit_key),
                    FOREIGN KEY(guest_id) REFERENCES guest_sessions(guest_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    profile_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    voice_enabled INTEGER NOT NULL DEFAULT 1,
                    sentence_voice INTEGER NOT NULL DEFAULT 1,
                    search_enabled INTEGER NOT NULL DEFAULT 1,
                    rag_enabled INTEGER NOT NULL DEFAULT 1,
                    voice_name TEXT NOT NULL DEFAULT '',
                    voice_speed TEXT NOT NULL DEFAULT 'normal',
                    last_spoken_response TEXT NOT NULL DEFAULT '',
                    theme TEXT NOT NULL DEFAULT 'midnight',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memories (
                    profile_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_facts (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    last_uploaded_file TEXT,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    chat_id TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS code_chats (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS code_messages (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    chat_id TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(chat_id) REFERENCES code_chats(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS code_project_files (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    chat_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_type TEXT,
                    language TEXT,
                    content TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(chat_id) REFERENCES code_chats(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    chat_id TEXT,
                    file_name TEXT NOT NULL,
                    file_type TEXT,
                    path TEXT NOT NULL,
                    context TEXT,
                    raw_text TEXT,
                    chunks TEXT,
                    is_image INTEGER NOT NULL DEFAULT 0,
                    used_ocr INTEGER NOT NULL DEFAULT 0,
                    page_count INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    chat_id TEXT,
                    chunk_index INTEGER NOT NULL,
                    page_number INTEGER,
                    text TEXT NOT NULL,
                    preview TEXT,
                    terms TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS activity_events (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    event_type TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    user_id TEXT,
                    guest_id TEXT,
                    device_id TEXT,
                    file_name TEXT NOT NULL,
                    file_type TEXT,
                    path TEXT NOT NULL UNIQUE,
                    document_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chats_profile_updated
                    ON chats(profile_id, pinned, updated_at);
                CREATE INDEX IF NOT EXISTS idx_messages_chat_order
                    ON messages(chat_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_code_chats_profile_updated
                    ON code_chats(profile_id, pinned, updated_at);
                CREATE INDEX IF NOT EXISTS idx_code_messages_chat_order
                    ON code_messages(chat_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_code_project_files_profile_chat
                    ON code_project_files(profile_id, chat_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_documents_profile_chat
                    ON documents(profile_id, chat_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document
                    ON document_chunks(document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_profile_chat
                    ON document_chunks(profile_id, chat_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_activity_profile_created
                    ON activity_events(profile_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_guest_sessions_device
                    ON guest_sessions(device_id);
                CREATE INDEX IF NOT EXISTS idx_guest_sessions_profile
                    ON guest_sessions(profile_id);
                CREATE INDEX IF NOT EXISTS idx_guest_sessions_last_seen
                    ON guest_sessions(last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_users_auth_user_id
                    ON users(auth_user_id);
                CREATE INDEX IF NOT EXISTS idx_users_provider_id
                    ON users(provider, provider_id);
                CREATE INDEX IF NOT EXISTS idx_account_sessions_user
                    ON account_sessions(user_id, last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_profile_pin_reset_lookup
                    ON profile_pin_reset_codes(user_id, profile_id, device_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_usage_limits_guest_device
                    ON usage_limits(guest_id, device_id, limit_key);
                """
            )

            profile_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(profiles)").fetchall()
            }
            if "profile_kind" not in profile_columns:
                conn.execute(
                    "ALTER TABLE profiles ADD COLUMN profile_kind TEXT NOT NULL DEFAULT 'legacy'"
                )
            if "user_id" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN user_id TEXT")
            if "device_id" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN device_id TEXT")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_profiles_account_device
                ON profiles(user_id, device_id, profile_kind, created_at)
                """
            )

            session_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "mode" not in session_columns:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'profile'"
                )
            if "guest_id" not in session_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN guest_id TEXT")
            if "device_id" not in session_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN device_id TEXT")
            conn.execute(
                """
                UPDATE sessions
                SET mode = 'guest',
                    guest_id = (
                        SELECT guest_id FROM guest_sessions
                        WHERE guest_sessions.profile_id = sessions.profile_id
                    ),
                    device_id = (
                        SELECT device_id FROM guest_sessions
                        WHERE guest_sessions.profile_id = sessions.profile_id
                    )
                WHERE EXISTS (
                    SELECT 1 FROM guest_sessions
                    WHERE guest_sessions.profile_id = sessions.profile_id
                )
                """
            )
            conn.execute(
                """
                UPDATE sessions
                SET mode = 'profile', guest_id = NULL, device_id = NULL
                WHERE mode NOT IN ('guest', 'profile')
                   OR (
                       mode = 'guest'
                       AND NOT EXISTS (
                           SELECT 1 FROM guest_sessions
                           WHERE guest_sessions.profile_id = sessions.profile_id
                       )
                   )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_mode_profile
                ON sessions(mode, profile_id, last_seen_at)
                """
            )

            usage_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(usage_limits)").fetchall()
            }
            usage_column_defs = {
                "period_start": "TEXT",
                "period_end": "TEXT",
                "metadata": "TEXT NOT NULL DEFAULT '{}'",
            }
            for column, definition in usage_column_defs.items():
                if column not in usage_columns:
                    conn.execute(f"ALTER TABLE usage_limits ADD COLUMN {column} {definition}")

            owned_tables = (
                "settings",
                "memories",
                "memory_facts",
                "chats",
                "messages",
                "code_chats",
                "code_messages",
                "code_project_files",
                "documents",
                "document_chunks",
                "activity_events",
                "files",
            )
            for table in owned_tables:
                columns = {
                    row["name"]
                    for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for column in ("user_id", "guest_id", "device_id"):
                    if column not in columns:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")

            settings_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(settings)").fetchall()
            }
            settings_column_defs = {
                "voice_name": "TEXT NOT NULL DEFAULT ''",
                "voice_speed": "TEXT NOT NULL DEFAULT 'normal'",
                "last_spoken_response": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in settings_column_defs.items():
                if column not in settings_columns:
                    conn.execute(f"ALTER TABLE settings ADD COLUMN {column} {definition}")

            document_chunk_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(document_chunks)").fetchall()
            }
            if "page_number" not in document_chunk_columns:
                conn.execute("ALTER TABLE document_chunks ADD COLUMN page_number INTEGER")

            ownership_migrated = conn.execute(
                "SELECT value FROM meta WHERE key = 'ownership_v1_migrated'"
            ).fetchone()
            if not ownership_migrated:
                for table in owned_tables:
                    if table == "files":
                        continue
                    # Attach historical guest records to the device/session that
                    # created their existing hidden guest workspace.
                    conn.execute(
                        f"""
                        UPDATE {table}
                        SET guest_id = (
                                SELECT guest_id FROM guest_sessions
                                WHERE guest_sessions.profile_id = {table}.profile_id
                            ),
                            device_id = (
                                SELECT device_id FROM guest_sessions
                                WHERE guest_sessions.profile_id = {table}.profile_id
                            ),
                            user_id = NULL
                        WHERE EXISTS (
                            SELECT 1 FROM guest_sessions
                            WHERE guest_sessions.profile_id = {table}.profile_id
                        )
                        """
                    )
                    # Account/device profiles and the account-level settings
                    # workspace retain their owning signed-in account.
                    conn.execute(
                        f"""
                        UPDATE {table}
                        SET user_id = COALESCE(
                                (SELECT profiles.user_id FROM profiles
                                 WHERE profiles.id = {table}.profile_id),
                                (SELECT users.id FROM users
                                 WHERE users.workspace_profile_id = {table}.profile_id)
                            ),
                            guest_id = NULL,
                            device_id = (
                                SELECT profiles.device_id FROM profiles
                                WHERE profiles.id = {table}.profile_id
                            )
                        WHERE NOT EXISTS (
                                SELECT 1 FROM guest_sessions
                                WHERE guest_sessions.profile_id = {table}.profile_id
                            )
                          AND (
                                EXISTS (
                                    SELECT 1 FROM profiles
                                    WHERE profiles.id = {table}.profile_id
                                      AND profiles.user_id IS NOT NULL
                                )
                                OR EXISTS (
                                    SELECT 1 FROM users
                                    WHERE users.workspace_profile_id = {table}.profile_id
                                )
                            )
                        """
                    )
                conn.execute(
                    """
                    INSERT INTO meta(key, value)
                    VALUES('ownership_v1_migrated', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (now_iso(),),
                )

            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_chats_guest_owner
                    ON chats(guest_id, device_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_chats_profile_owner
                    ON chats(user_id, profile_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_messages_guest_owner
                    ON messages(guest_id, device_id, chat_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_messages_profile_owner
                    ON messages(user_id, profile_id, chat_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_code_chats_guest_owner
                    ON code_chats(guest_id, device_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_code_chats_profile_owner
                    ON code_chats(user_id, profile_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_code_messages_guest_owner
                    ON code_messages(guest_id, device_id, chat_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_code_messages_profile_owner
                    ON code_messages(user_id, profile_id, chat_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_code_project_files_guest_owner
                    ON code_project_files(guest_id, device_id, chat_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_code_project_files_profile_owner
                    ON code_project_files(user_id, profile_id, chat_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_documents_guest_owner
                    ON documents(guest_id, device_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_documents_profile_owner
                    ON documents(user_id, profile_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_guest_owner
                    ON document_chunks(guest_id, device_id, document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_profile_owner
                    ON document_chunks(user_id, profile_id, document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_files_guest_owner
                    ON files(guest_id, device_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_files_profile_owner
                    ON files(user_id, profile_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_activity_guest_owner
                    ON activity_events(guest_id, device_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_activity_profile_owner
                    ON activity_events(user_id, profile_id, created_at);
                """
            )

            migrated = conn.execute(
                "SELECT value FROM meta WHERE key = 'json_migrated'"
            ).fetchone()
            if not migrated:
                migrate_json_to_sqlite(conn)
                conn.execute(
                    """
                    INSERT INTO meta(key, value)
                    VALUES('json_migrated', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (now_iso(),),
                )
        DATABASE_INITIALIZED = True


def table_column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_name.replace("_", "").isalnum():
        return set()
    if DATABASE.is_postgres_active() and table_name in POSTGRES_KNOWN_TABLE_COLUMNS:
        return set(POSTGRES_KNOWN_TABLE_COLUMNS[table_name])
    cache_key = (DATABASE.active_provider, table_name)
    with TABLE_COLUMN_LOCK:
        cached = TABLE_COLUMN_CACHE.get(cache_key)
        if cached is not None:
            return set(cached)
    try:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            if "name" in row.keys()
        }
        with TABLE_COLUMN_LOCK:
            TABLE_COLUMN_CACHE[cache_key] = set(columns)
        return columns
    except Exception:
        return set()


def ensure_device_row(conn: sqlite3.Connection, device_id: str | None) -> None:
    normalized_device_id = validate_device_id(device_id)
    if not normalized_device_id:
        return

    with DEVICE_ROW_CACHE_LOCK:
        if normalized_device_id in DEVICE_ROW_CACHE:
            return

    columns = table_column_names(conn, "devices")
    if not columns:
        return

    key_column = (
        "id"
        if "id" in columns
        else "device_id"
        if "device_id" in columns
        else "client_device_id"
        if "client_device_id" in columns
        else ""
    )
    if not key_column:
        return

    timestamp = now_iso()
    insert_columns = [key_column]
    values: list[Any] = [normalized_device_id]

    if key_column != "device_id" and "device_id" in columns:
        insert_columns.append("device_id")
        values.append(normalized_device_id)
    if key_column != "client_device_id" and "client_device_id" in columns:
        insert_columns.append("client_device_id")
        values.append(normalized_device_id)
    if "created_at" in columns:
        insert_columns.append("created_at")
        values.append(timestamp)
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        values.append(timestamp)
    if "last_seen_at" in columns:
        insert_columns.append("last_seen_at")
        values.append(timestamp)

    update_assignments = []
    if key_column != "device_id" and "device_id" in columns:
        update_assignments.append("device_id = excluded.device_id")
    if key_column != "client_device_id" and "client_device_id" in columns:
        update_assignments.append("client_device_id = excluded.client_device_id")
    if "updated_at" in columns:
        update_assignments.append("updated_at = excluded.updated_at")
    if "last_seen_at" in columns:
        update_assignments.append("last_seen_at = excluded.last_seen_at")

    placeholders = ", ".join("?" for _ in insert_columns)
    column_sql = ", ".join(insert_columns)
    if update_assignments:
        conflict_sql = f"ON CONFLICT({key_column}) DO UPDATE SET {', '.join(update_assignments)}"
    else:
        conflict_sql = f"ON CONFLICT({key_column}) DO NOTHING"

    conn.execute(
        f"INSERT INTO devices ({column_sql}) VALUES ({placeholders}) {conflict_sql}",
        tuple(values),
    )
    with DEVICE_ROW_CACHE_LOCK:
        DEVICE_ROW_CACHE.add(normalized_device_id)


def ensure_scope_device_row(conn: sqlite3.Connection, scope: dict[str, str | None] | None) -> None:
    if scope:
        ensure_device_row(conn, scope.get("device_id"))


def session_token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def session_owner_user_id(conn: sqlite3.Connection, profile_id: str | None) -> str | None:
    if not profile_id:
        return None
    row = conn.execute(
        """
        SELECT COALESCE(profiles.user_id, users.id) AS user_id
        FROM profiles
        LEFT JOIN users ON users.workspace_profile_id = profiles.id
        WHERE profiles.id = ?
        """,
        (profile_id,),
    ).fetchone()
    return row["user_id"] if row and row["user_id"] else None


def upsert_session_row(
    conn: sqlite3.Connection,
    *,
    token: str,
    profile_id: str,
    mode: str = "profile",
    guest_id: str | None = None,
    device_id: str | None = None,
    created_at: str | None = None,
    last_seen_at: str | None = None,
) -> None:
    ensure_device_row(conn, device_id)
    columns = table_column_names(conn, "sessions")
    timestamp = now_iso()
    created = created_at or timestamp
    last_seen = last_seen_at or timestamp

    insert_values: dict[str, Any] = {
        "token": token,
        "token_hash": session_token_hash(token),
        "profile_id": profile_id,
        "user_id": session_owner_user_id(conn, profile_id),
        "mode": mode if mode in {"guest", "profile"} else "profile",
        "guest_id": guest_id,
        "device_id": device_id,
        "created_at": created,
        "last_seen_at": last_seen,
    }
    insert_columns = [column for column in insert_values if column in columns]
    placeholders = ", ".join("?" for _ in insert_columns)
    update_columns = [
        column
        for column in (
            "token_hash",
            "profile_id",
            "user_id",
            "mode",
            "guest_id",
            "device_id",
            "created_at",
            "last_seen_at",
        )
        if column in insert_columns
    ]
    update_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    conflict_sql = f"ON CONFLICT(token) DO UPDATE SET {update_sql}" if update_sql else "ON CONFLICT(token) DO NOTHING"
    conn.execute(
        f"""
        INSERT INTO sessions ({", ".join(insert_columns)})
        VALUES ({placeholders})
        {conflict_sql}
        """,
        tuple(insert_values[column] for column in insert_columns),
    )


def upsert_profile_row(conn: sqlite3.Connection, profile: dict[str, Any]) -> None:
    ensure_device_row(conn, profile.get("device_id"))
    conn.execute(
        """
        INSERT INTO profiles
            (id, name, pin_salt, pin_hash, profile_kind, user_id, device_id,
             created_at, last_login_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            pin_salt = CASE
                WHEN excluded.pin_salt != '' THEN excluded.pin_salt
                ELSE profiles.pin_salt
            END,
            pin_hash = CASE
                WHEN excluded.pin_hash != '' THEN excluded.pin_hash
                ELSE profiles.pin_hash
            END,
            profile_kind = excluded.profile_kind,
            user_id = excluded.user_id,
            device_id = excluded.device_id,
            created_at = profiles.created_at,
            last_login_at = excluded.last_login_at
        """,
        (
            profile["id"],
            profile.get("name", "User"),
            profile.get("pin_salt", ""),
            profile.get("pin_hash", ""),
            profile.get("profile_kind", "legacy"),
            profile.get("user_id"),
            profile.get("device_id"),
            profile.get("created_at") or now_iso(),
            profile.get("last_login_at") or profile.get("created_at") or now_iso(),
        ),
    )


def row_to_profile(row: sqlite3.Row) -> dict[str, Any]:
    profile = {
        "id": row["id"],
        "name": row["name"],
        "pin_salt": row["pin_salt"],
        "pin_hash": row["pin_hash"],
        "profile_kind": row["profile_kind"] if "profile_kind" in row.keys() else "legacy",
        "user_id": row["user_id"] if "user_id" in row.keys() else None,
        "device_id": row["device_id"] if "device_id" in row.keys() else None,
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }

    row_keys = set(row.keys())
    if "guest_id" in row_keys and row["guest_id"]:
        profile["is_guest"] = True
        profile["guest_id"] = row["guest_id"]

    return profile


def row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "auth_user_id": row["auth_user_id"],
        "email": row["email"],
        "provider": row["provider"],
        "provider_id": row["provider_id"],
        "onboarding_completed": bool(row["onboarding_completed"]),
        "workspace_profile_id": row["workspace_profile_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def ownership_scope_for_profile(
    profile_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, str | None]:
    close_connection = conn is None
    if conn is None:
        ensure_files()
        conn = db_connect()
    try:
        row = conn.execute(
            """
            SELECT profiles.id, profiles.user_id, profiles.device_id,
                guest_sessions.guest_id,
                guest_sessions.device_id AS guest_device_id,
                users.id AS workspace_user_id
            FROM profiles
            LEFT JOIN guest_sessions ON guest_sessions.profile_id = profiles.id
            LEFT JOIN users ON users.workspace_profile_id = profiles.id
            WHERE profiles.id = ?
            """,
            (profile_id,),
        ).fetchone()
    finally:
        if close_connection:
            conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Workspace owner no longer exists.")

    if row["guest_id"]:
        return {
            "mode": "guest",
            "profile_id": profile_id,
            "user_id": None,
            "guest_id": row["guest_id"],
            "device_id": row["guest_device_id"],
        }

    user_id = row["user_id"] or row["workspace_user_id"]
    if user_id:
        return {
            "mode": "profile",
            "profile_id": profile_id,
            "user_id": user_id,
            "guest_id": None,
            "device_id": row["device_id"],
        }

    # Existing PIN-only profiles predate account ownership; retain their
    # isolated profile workspace until the legacy flow is retired.
    return {
        "mode": "legacy",
        "profile_id": profile_id,
        "user_id": None,
        "guest_id": None,
        "device_id": None,
    }


def ownership_scope_from_profile(profile: dict[str, Any]) -> dict[str, str | None] | None:
    profile_id = profile.get("id")
    if not profile_id:
        return None

    if profile.get("is_guest") and profile.get("guest_id") and profile.get("device_id"):
        return {
            "mode": "guest",
            "profile_id": profile_id,
            "user_id": None,
            "guest_id": profile.get("guest_id"),
            "device_id": profile.get("device_id"),
        }

    if profile.get("user_id"):
        return {
            "mode": "profile",
            "profile_id": profile_id,
            "user_id": profile.get("user_id"),
            "guest_id": None,
            "device_id": profile.get("device_id"),
        }

    if profile.get("profile_kind") in {None, "", "legacy"}:
        return {
            "mode": "legacy",
            "profile_id": profile_id,
            "user_id": None,
            "guest_id": None,
            "device_id": None,
        }

    return None


def owner_values(scope: dict[str, str | None]) -> tuple[str | None, str | None, str | None]:
    return scope.get("user_id"), scope.get("guest_id"), scope.get("device_id")


def owner_where(
    scope: dict[str, str | None],
    alias: str = "",
) -> tuple[str, tuple[str, ...]]:
    column = f"{alias}." if alias else ""
    if scope["mode"] == "guest":
        return (
            f"{column}guest_id = ? AND {column}device_id = ?",
            (str(scope["guest_id"]), str(scope["device_id"])),
        )
    if scope["mode"] == "profile":
        return (
            f"{column}user_id = ? AND {column}profile_id = ?",
            (str(scope["user_id"]), str(scope["profile_id"])),
        )
    return (
        f"{column}profile_id = ? AND {column}user_id IS NULL AND {column}guest_id IS NULL",
        (str(scope["profile_id"]),),
    )


def reject_other_owner_id(
    conn: sqlite3.Connection,
    table: str,
    record_id: str,
    scope: dict[str, str | None],
    label: str,
) -> None:
    existing = conn.execute(f"SELECT id FROM {table} WHERE id = ?", (record_id,)).fetchone()
    if not existing:
        return
    owner_clause, owner_params = owner_where(scope)
    owned = conn.execute(
        f"SELECT id FROM {table} WHERE id = ? AND {owner_clause}",
        (record_id, *owner_params),
    ).fetchone()
    if not owned:
        raise HTTPException(status_code=403, detail=f"This {label} belongs to another workspace.")


def settings_to_db(settings: dict[str, Any]) -> dict[str, Any]:
    merged = DEFAULT_SETTINGS.copy()
    if isinstance(settings, dict):
        merged.update({key: settings[key] for key in merged.keys() if key in settings})
    if merged.get("voiceSpeed") not in {"slow", "normal", "fast"}:
        merged["voiceSpeed"] = "normal"
    merged["voiceName"] = str(merged.get("voiceName") or "")[:180]
    merged["lastSpokenResponse"] = str(merged.get("lastSpokenResponse") or "")[:3000]
    return merged


def upsert_settings_row(
    conn: sqlite3.Connection,
    profile_id: str,
    settings: dict[str, Any] | None = None,
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    merged = settings_to_db(settings or DEFAULT_SETTINGS)
    conn.execute(
        """
        INSERT INTO settings
            (profile_id, user_id, guest_id, device_id, voice_enabled, sentence_voice,
             search_enabled, rag_enabled, voice_name, voice_speed, last_spoken_response,
             theme, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_id) DO UPDATE SET
            user_id = excluded.user_id,
            guest_id = excluded.guest_id,
            device_id = excluded.device_id,
            voice_enabled = excluded.voice_enabled,
            sentence_voice = excluded.sentence_voice,
            search_enabled = excluded.search_enabled,
            rag_enabled = excluded.rag_enabled,
            voice_name = excluded.voice_name,
            voice_speed = excluded.voice_speed,
            last_spoken_response = excluded.last_spoken_response,
            theme = excluded.theme,
            updated_at = excluded.updated_at
        """,
        (
            profile_id,
            *owner_values(scope),
            int(bool(merged["voiceEnabled"])),
            int(bool(merged["sentenceVoice"])),
            int(bool(merged["searchEnabled"])),
            int(bool(merged["ragEnabled"])),
            str(merged["voiceName"] or ""),
            str(merged["voiceSpeed"] or "normal"),
            str(merged["lastSpokenResponse"] or ""),
            str(merged["theme"] or "midnight"),
            now_iso(),
        ),
    )


def row_to_settings(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return DEFAULT_SETTINGS.copy()
    return {
        "voiceEnabled": bool(row["voice_enabled"]),
        "sentenceVoice": bool(row["sentence_voice"]),
        "searchEnabled": bool(row["search_enabled"]),
        "ragEnabled": bool(row["rag_enabled"]),
        "voiceName": row["voice_name"] or "",
        "voiceSpeed": row["voice_speed"] or "normal",
        "lastSpokenResponse": row["last_spoken_response"] or "",
        "theme": row["theme"] or "midnight",
    }


def upsert_memory_rows(
    conn: sqlite3.Connection,
    profile_id: str,
    memory: dict[str, Any] | None = None,
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    owner_clause, owner_params = owner_where(scope)
    normalized = normalize_memory(memory or {})
    conn.execute(
        """
        INSERT INTO memories
            (profile_id, user_id, guest_id, device_id, name, role, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_id) DO UPDATE SET
            user_id = excluded.user_id,
            guest_id = excluded.guest_id,
            device_id = excluded.device_id,
            name = excluded.name,
            role = excluded.role,
            updated_at = excluded.updated_at
        """,
        (profile_id, *owner_values(scope), normalized["name"], normalized["role"], now_iso()),
    )
    conn.execute(f"DELETE FROM memory_facts WHERE {owner_clause}", owner_params)
    for fact in normalized.get("facts", []):
        fact_id = fact.get("id") or str(uuid.uuid4())
        reject_other_owner_id(conn, "memory_facts", fact_id, scope, "memory item")
        conn.execute(
            """
            INSERT INTO memory_facts
                (id, profile_id, user_id, guest_id, device_id, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id,
                profile_id,
                *owner_values(scope),
                fact.get("text", ""),
                fact.get("created_at") or now_iso(),
            ),
        )


def row_to_memory(
    conn: sqlite3.Connection,
    profile_id: str,
    scope: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    owner_clause, owner_params = owner_where(scope)
    row = conn.execute(
        f"SELECT name, role FROM memories WHERE {owner_clause}",
        owner_params,
    ).fetchone()
    facts = [
        {"id": fact["id"], "text": fact["text"], "created_at": fact["created_at"]}
        for fact in conn.execute(
            """
            SELECT id, text, created_at
            FROM memory_facts
            WHERE {owner_clause}
            ORDER BY created_at ASC
            """.format(owner_clause=owner_clause),
            owner_params,
        ).fetchall()
    ]
    return normalize_memory(
        {
            "name": row["name"] if row else "",
            "role": row["role"] if row else "",
            "facts": facts,
        }
    )


def normalize_message_role(role: Any) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == "user":
        return "user"
    if normalized == "system":
        return "system"
    if normalized in {"assistant", "ai", "bot", "febguy", "febguyai", "model"}:
        return "assistant"
    return "assistant"


def normalize_timestamp_value(value: Any, fallback: str | None = None) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")

    raw = str(value or "").strip()
    if not raw:
        return fallback or now_iso()

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat(timespec="seconds")
    except ValueError:
        return raw


def message_to_payload(message: dict[str, Any]) -> dict[str, Any]:
    payload = dict(message)
    payload["id"] = payload.get("id") or str(uuid.uuid4())
    payload["created_at"] = normalize_timestamp_value(payload.get("created_at"))
    payload["role"] = normalize_message_role(payload.get("role"))
    payload["text"] = payload.get("text") or ""
    return payload


def is_saved_backend_failure_message(message: dict[str, Any]) -> bool:
    if normalize_message_role(message.get("role")) != "assistant":
        return False
    text = str(message.get("text") or "").strip().lower()
    failure_markers = (
        "backend unavailable",
        "failed to fetch",
        "start the fastapi backend",
        "check the app url",
    )
    return any(marker in text for marker in failure_markers)


def upsert_chat_header_row(
    conn: sqlite3.Connection,
    profile_id: str,
    chat_item: dict[str, Any],
    scope: dict[str, str | None] | None = None,
    *,
    trusted_owner: bool = False,
) -> dict[str, Any]:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    chat_item = normalize_chat(chat_item)
    if not trusted_owner:
        reject_other_owner_id(conn, "chats", chat_item["id"], scope, "chat")
    conn.execute(
        """
        INSERT INTO chats
            (id, profile_id, user_id, guest_id, device_id, title, summary,
             last_uploaded_file, pinned, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            profile_id = excluded.profile_id,
            user_id = excluded.user_id,
            guest_id = excluded.guest_id,
            device_id = excluded.device_id,
            title = excluded.title,
            summary = excluded.summary,
            last_uploaded_file = excluded.last_uploaded_file,
            pinned = excluded.pinned,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at
        """,
        (
            chat_item["id"],
            profile_id,
            *owner_values(scope),
            chat_item["title"],
            chat_item["summary"],
            encode_json(chat_item.get("last_uploaded_file")),
            int(bool(chat_item.get("pinned"))),
            chat_item["created_at"],
            chat_item["updated_at"],
        ),
    )
    return chat_item


def upsert_code_chat_header_row(
    conn: sqlite3.Connection,
    profile_id: str,
    chat_item: dict[str, Any],
    scope: dict[str, str | None] | None = None,
    *,
    trusted_owner: bool = False,
) -> dict[str, Any]:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    chat_item = normalize_chat(chat_item)
    if not trusted_owner:
        reject_other_owner_id(conn, "code_chats", chat_item["id"], scope, "code chat")
    conn.execute(
        """
        INSERT INTO code_chats
            (id, profile_id, user_id, guest_id, device_id, title, summary,
             pinned, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            profile_id = excluded.profile_id,
            user_id = excluded.user_id,
            guest_id = excluded.guest_id,
            device_id = excluded.device_id,
            title = excluded.title,
            summary = excluded.summary,
            pinned = excluded.pinned,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at
        """,
        (
            chat_item["id"],
            profile_id,
            *owner_values(scope),
            chat_item["title"],
            chat_item["summary"],
            int(bool(chat_item.get("pinned"))),
            chat_item["created_at"],
            chat_item["updated_at"],
        ),
    )
    return chat_item


def append_new_message_rows(
    conn: sqlite3.Connection,
    table: str,
    profile_id: str,
    chat_id: str,
    messages: list[dict[str, Any]],
    loaded_message_ids: Iterable[str],
    scope: dict[str, str | None],
    *,
    next_sort_order: int | None = None,
    trusted_owner: bool = False,
) -> None:
    if table not in {"messages", "code_messages"}:
        raise ValueError("Unsupported message table.")

    owner_clause, owner_params = owner_where(scope)
    if next_sort_order is not None:
        next_sort_order = int(next_sort_order)
    else:
        row = conn.execute(
            f"""
            SELECT MAX(sort_order) AS max_sort_order
            FROM {table}
            WHERE {owner_clause} AND chat_id = ?
            """,
            (*owner_params, chat_id),
        ).fetchone()
        max_sort_order = row["max_sort_order"] if row else None
        next_sort_order = int(max_sort_order) + 1 if max_sort_order is not None else 0
    loaded_ids = {str(message_id) for message_id in loaded_message_ids if message_id}

    for message in messages:
        existing_id = str(message.get("id") or "")
        if existing_id and existing_id in loaded_ids:
            continue

        payload = message_to_payload(message)
        if str(payload["id"]) in loaded_ids:
            continue

        message.clear()
        message.update(payload)
        if not trusted_owner:
            reject_other_owner_id(conn, table, payload["id"], scope, "message")
        try:
            conn.execute(
                f"""
                INSERT INTO {table}
                    (id, profile_id, user_id, guest_id, device_id, chat_id,
                     sort_order, role, text, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    user_id = excluded.user_id,
                    guest_id = excluded.guest_id,
                    device_id = excluded.device_id,
                    chat_id = excluded.chat_id,
                    sort_order = excluded.sort_order,
                    role = excluded.role,
                    text = excluded.text,
                    payload = excluded.payload,
                    created_at = excluded.created_at
                """,
                (
                    payload["id"],
                    profile_id,
                    *owner_values(scope),
                    chat_id,
                    next_sort_order,
                    payload["role"],
                    payload.get("text", ""),
                    encode_json(payload),
                    payload["created_at"],
                ),
            )
        except Exception as exc:
            LOGGER.exception(
                "DB write failed table=%s chat_id=%s role=%s db_hint=%s",
                table,
                chat_id,
                payload.get("role"),
                database_error_hint(exc),
            )
            raise
        next_sort_order += 1


def upsert_chat_row(
    conn: sqlite3.Connection,
    profile_id: str,
    chat_item: dict[str, Any],
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    owner_clause, owner_params = owner_where(scope)
    chat_item = normalize_chat(chat_item)
    reject_other_owner_id(conn, "chats", chat_item["id"], scope, "chat")
    conn.execute(
        """
        INSERT INTO chats
            (id, profile_id, user_id, guest_id, device_id, title, summary,
             last_uploaded_file, pinned, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            profile_id = excluded.profile_id,
            user_id = excluded.user_id,
            guest_id = excluded.guest_id,
            device_id = excluded.device_id,
            title = excluded.title,
            summary = excluded.summary,
            last_uploaded_file = excluded.last_uploaded_file,
            pinned = excluded.pinned,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at
        """,
        (
            chat_item["id"],
            profile_id,
            *owner_values(scope),
            chat_item["title"],
            chat_item["summary"],
            encode_json(chat_item.get("last_uploaded_file")),
            int(bool(chat_item.get("pinned"))),
            chat_item["created_at"],
            chat_item["updated_at"],
        ),
    )

    conn.execute(
        f"DELETE FROM messages WHERE {owner_clause} AND chat_id = ?",
        (*owner_params, chat_item["id"]),
    )
    for index, message in enumerate(chat_item.get("messages", [])):
        payload = message_to_payload(message)
        message.clear()
        message.update(payload)
        try:
            conn.execute(
                """
                INSERT INTO messages
                    (id, profile_id, user_id, guest_id, device_id, chat_id,
                     sort_order, role, text, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    profile_id,
                    *owner_values(scope),
                    chat_item["id"],
                    index,
                    payload["role"],
                    payload.get("text", ""),
                    encode_json(payload),
                    payload["created_at"],
                ),
            )
        except Exception as exc:
            LOGGER.exception(
                "DB write failed table=messages chat_id=%s role=%s db_hint=%s",
                chat_item["id"],
                payload.get("role"),
                database_error_hint(exc),
            )
            raise


def insert_empty_chat_row(
    conn: sqlite3.Connection,
    profile_id: str,
    chat_item: dict[str, Any],
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    chat_item = normalize_chat({**chat_item, "messages": []})
    conn.execute(
        """
        INSERT INTO chats
            (id, profile_id, user_id, guest_id, device_id, title, summary,
             last_uploaded_file, pinned, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (
            chat_item["id"],
            profile_id,
            *owner_values(scope),
            chat_item["title"],
            chat_item["summary"],
            encode_json(chat_item.get("last_uploaded_file")),
            int(bool(chat_item.get("pinned"))),
            chat_item["created_at"],
            chat_item["updated_at"],
        ),
    )


def row_to_chat(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    scope: dict[str, str | None] | None = None,
    message_limit: int | None = None,
) -> dict[str, Any]:
    scope = scope or ownership_scope_for_profile(row["profile_id"], conn)
    owner_clause, owner_params = owner_where(scope)
    messages = []
    if message_limit is not None and message_limit > 0:
        message_rows = conn.execute(
            f"""
            SELECT payload, sort_order
            FROM (
                SELECT payload, sort_order
                FROM messages
                WHERE {owner_clause} AND chat_id = ?
                ORDER BY sort_order DESC
                LIMIT ?
            ) AS recent_messages
            ORDER BY sort_order ASC
            """,
            (*owner_params, row["id"], int(message_limit)),
        ).fetchall()
    else:
        message_rows = conn.execute(
            f"""
            SELECT payload, sort_order
            FROM messages
            WHERE {owner_clause} AND chat_id = ?
            ORDER BY sort_order ASC
            """,
            (*owner_params, row["id"]),
        ).fetchall()

    max_sort_order = None
    for message_row in message_rows:
        payload = decode_json(message_row["payload"], {})
        if isinstance(payload, dict):
            messages.append(payload)
        try:
            sort_order = message_row["sort_order"]
            if sort_order is not None:
                max_sort_order = max(int(sort_order), int(max_sort_order if max_sort_order is not None else sort_order))
        except Exception:
            pass

    chat_item = normalize_chat(
        {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "messages": messages,
            "last_uploaded_file": decode_json(row["last_uploaded_file"], None),
            "pinned": bool(row["pinned"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    if message_limit is not None and message_limit > 0:
        chat_item["_recent_messages_only"] = True
        chat_item["_loaded_message_ids"] = [
            message["id"] for message in chat_item["messages"] if message.get("id")
        ]
        chat_item["_next_sort_order"] = int(max_sort_order) + 1 if max_sort_order is not None else 0
    return chat_item


def row_to_chat_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return normalize_chat(
        {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "messages": [],
            "last_uploaded_file": decode_json(row["last_uploaded_file"], None),
            "pinned": bool(row["pinned"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


def upsert_code_chat_row(
    conn: sqlite3.Connection,
    profile_id: str,
    chat_item: dict[str, Any],
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    owner_clause, owner_params = owner_where(scope)
    chat_item = normalize_chat(chat_item)
    reject_other_owner_id(conn, "code_chats", chat_item["id"], scope, "code chat")
    conn.execute(
        """
        INSERT INTO code_chats
            (id, profile_id, user_id, guest_id, device_id, title, summary,
             pinned, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            profile_id = excluded.profile_id,
            user_id = excluded.user_id,
            guest_id = excluded.guest_id,
            device_id = excluded.device_id,
            title = excluded.title,
            summary = excluded.summary,
            pinned = excluded.pinned,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at
        """,
        (
            chat_item["id"],
            profile_id,
            *owner_values(scope),
            chat_item["title"],
            chat_item["summary"],
            int(bool(chat_item.get("pinned"))),
            chat_item["created_at"],
            chat_item["updated_at"],
        ),
    )

    conn.execute(
        f"DELETE FROM code_messages WHERE {owner_clause} AND chat_id = ?",
        (*owner_params, chat_item["id"]),
    )
    for index, message in enumerate(chat_item.get("messages", [])):
        payload = message_to_payload(message)
        message.clear()
        message.update(payload)
        try:
            conn.execute(
                """
                INSERT INTO code_messages
                    (id, profile_id, user_id, guest_id, device_id, chat_id,
                     sort_order, role, text, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    profile_id,
                    *owner_values(scope),
                    chat_item["id"],
                    index,
                    payload["role"],
                    payload.get("text", ""),
                    encode_json(payload),
                    payload["created_at"],
                ),
            )
        except Exception as exc:
            LOGGER.exception(
                "DB write failed table=code_messages chat_id=%s role=%s db_hint=%s",
                chat_item["id"],
                payload.get("role"),
                database_error_hint(exc),
            )
            raise


def insert_empty_code_chat_row(
    conn: sqlite3.Connection,
    profile_id: str,
    chat_item: dict[str, Any],
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    chat_item = normalize_chat({**chat_item, "messages": []})
    conn.execute(
        """
        INSERT INTO code_chats
            (id, profile_id, user_id, guest_id, device_id, title, summary,
             pinned, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (
            chat_item["id"],
            profile_id,
            *owner_values(scope),
            chat_item["title"],
            chat_item["summary"],
            int(bool(chat_item.get("pinned"))),
            chat_item["created_at"],
            chat_item["updated_at"],
        ),
    )


def row_to_code_chat(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    scope: dict[str, str | None] | None = None,
    message_limit: int | None = None,
    include_project_files: bool = True,
) -> dict[str, Any]:
    scope = scope or ownership_scope_for_profile(row["profile_id"], conn)
    owner_clause, owner_params = owner_where(scope)
    messages = []
    if message_limit is not None and message_limit > 0:
        message_rows = conn.execute(
            f"""
            SELECT payload, sort_order
            FROM (
                SELECT payload, sort_order
                FROM code_messages
                WHERE {owner_clause} AND chat_id = ?
                ORDER BY sort_order DESC
                LIMIT ?
            ) AS recent_code_messages
            ORDER BY sort_order ASC
            """,
            (*owner_params, row["id"], int(message_limit)),
        ).fetchall()
    else:
        message_rows = conn.execute(
            f"""
            SELECT payload, sort_order
            FROM code_messages
            WHERE {owner_clause} AND chat_id = ?
            ORDER BY sort_order ASC
            """,
            (*owner_params, row["id"]),
        ).fetchall()

    max_sort_order = None
    for message_row in message_rows:
        payload = decode_json(message_row["payload"], {})
        if isinstance(payload, dict):
            messages.append(payload)
        try:
            sort_order = message_row["sort_order"]
            if sort_order is not None:
                max_sort_order = max(int(sort_order), int(max_sort_order if max_sort_order is not None else sort_order))
        except Exception:
            pass

    chat_item = normalize_chat(
        {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "messages": messages,
            "pinned": bool(row["pinned"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    if message_limit is not None and message_limit > 0:
        chat_item["_recent_messages_only"] = True
        chat_item["_loaded_message_ids"] = [
            message["id"] for message in chat_item["messages"] if message.get("id")
        ]
        chat_item["_next_sort_order"] = int(max_sort_order) + 1 if max_sort_order is not None else 0
    chat_item["projectFiles"] = (
        load_code_project_files(row["profile_id"], row["id"], conn, scope)
        if include_project_files
        else []
    )
    return chat_item


def row_to_code_chat_metadata(row: sqlite3.Row) -> dict[str, Any]:
    chat_item = normalize_chat(
        {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "messages": [],
            "pinned": bool(row["pinned"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    chat_item["projectFiles"] = []
    return chat_item


def upsert_file_row(
    conn: sqlite3.Connection,
    profile_id: str,
    path: str,
    file_name: str,
    file_type: str = "",
    *,
    document_id: str | None = None,
    scope: dict[str, str | None] | None = None,
) -> None:
    raw_path = str(path or "").strip()
    if not raw_path:
        return
    clean_path = str(ensure_controlled_file_path(Path(raw_path)))
    safe_name = str(file_name or Path(clean_path).name or "file").strip() or "file"
    safe_type = str(file_type or "application/octet-stream").strip() or "application/octet-stream"
    timestamp = now_iso()
    try:
        size_bytes = ensure_controlled_file_path(Path(clean_path)).stat().st_size
    except OSError:
        size_bytes = 0
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    owner_clause, owner_params = owner_where(scope)
    existing = conn.execute(
        f"SELECT id, created_at FROM files WHERE path = ? AND {owner_clause}",
        (clean_path, *owner_params),
    ).fetchone()
    if not existing and conn.execute(
        "SELECT id FROM files WHERE path = ?",
        (clean_path,),
    ).fetchone():
        raise HTTPException(status_code=403, detail="This file belongs to another workspace.")
    file_id = existing["id"] if existing else str(uuid.uuid4())
    created_at = existing["created_at"] if existing else timestamp
    columns = table_column_names(conn, "files")
    values: dict[str, Any] = {
        "id": file_id,
        "profile_id": profile_id,
        "user_id": scope.get("user_id"),
        "guest_id": scope.get("guest_id"),
        "device_id": scope.get("device_id"),
        "file_name": safe_name,
        "original_name": safe_name,
        "file_type": safe_type,
        "mime_type": safe_type,
        "path": clean_path,
        "storage_path": clean_path,
        "document_id": document_id,
        "size_bytes": size_bytes,
        "metadata": encode_json({}),
        "created_at": created_at,
        "updated_at": timestamp,
    }
    insert_order = [
        "id",
        "profile_id",
        "user_id",
        "guest_id",
        "device_id",
        "file_name",
        "original_name",
        "file_type",
        "mime_type",
        "path",
        "storage_path",
        "document_id",
        "size_bytes",
        "metadata",
        "created_at",
        "updated_at",
    ]
    insert_columns = [column for column in insert_order if column in columns]
    if not insert_columns:
        return
    placeholders = ", ".join(
        "CAST(? AS jsonb)"
        if column == "metadata" and DATABASE.is_postgres_active()
        else "?"
        for column in insert_columns
    )
    update_columns = [
        column
        for column in insert_columns
        if column not in {"id", "created_at"}
    ]
    update_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    conflict_sql = f"ON CONFLICT(id) DO UPDATE SET {update_sql}" if update_sql else "ON CONFLICT(id) DO NOTHING"
    conn.execute(
        f"""
        INSERT INTO files ({", ".join(insert_columns)})
        VALUES ({placeholders})
        {conflict_sql}
        """,
        tuple(values[column] for column in insert_columns),
    )


def save_owned_file_record(
    profile_id: str,
    path: Path,
    file_name: str,
    file_type: str = "",
    document_id: str | None = None,
) -> None:
    with DATA_LOCK:
        with db_connect() as conn:
            upsert_file_row(
                conn,
                profile_id,
                str(path),
                file_name,
                file_type,
                document_id=document_id,
            )


def upsert_document_chunk_rows(
    conn: sqlite3.Connection,
    profile_id: str,
    chat_id: str | None,
    document_id: str,
    chunks: list[dict[str, Any]],
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    ensure_scope_device_row(conn, scope)
    owner_clause, owner_params = owner_where(scope)
    reject_other_owner_id(conn, "documents", document_id, scope, "document")
    conn.execute(
        f"DELETE FROM document_chunks WHERE {owner_clause} AND document_id = ?",
        (*owner_params, document_id),
    )
    for chunk in chunks or []:
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue
        chunk_index = int(chunk.get("index") or 0)
        conn.execute(
            """
            INSERT INTO document_chunks
                (id, document_id, profile_id, user_id, guest_id, device_id,
                 chat_id, chunk_index, page_number, text, preview, terms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{document_id}:{chunk_index or uuid.uuid4()}",
                document_id,
                profile_id,
                *owner_values(scope),
                chat_id,
                chunk_index,
                chunk.get("page_number"),
                text,
                chunk.get("preview") or clip_text(text, 180),
                terms_json(text),
                now_iso(),
            ),
        )


def save_document_record(
    profile_id: str,
    chat_id: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    document_id = metadata.get("document_id") or str(uuid.uuid4())
    metadata["document_id"] = document_id

    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile_id, conn)
            ensure_scope_device_row(conn, scope)
            reject_other_owner_id(conn, "documents", document_id, scope, "document")
            conn.execute(
                """
                INSERT INTO documents
                    (id, profile_id, user_id, guest_id, device_id, chat_id,
                     file_name, file_type, path, context, raw_text, chunks,
                     is_image, used_ocr, page_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    user_id = excluded.user_id,
                    guest_id = excluded.guest_id,
                    device_id = excluded.device_id,
                    chat_id = excluded.chat_id,
                    file_name = excluded.file_name,
                    file_type = excluded.file_type,
                    path = excluded.path,
                    context = excluded.context,
                    raw_text = excluded.raw_text,
                    chunks = excluded.chunks,
                    is_image = excluded.is_image,
                    used_ocr = excluded.used_ocr,
                    page_count = excluded.page_count,
                    created_at = excluded.created_at
                """,
                (
                    document_id,
                    profile_id,
                    *owner_values(scope),
                    chat_id,
                    metadata.get("name", ""),
                    metadata.get("type", ""),
                    metadata.get("path", ""),
                    metadata.get("context", ""),
                    metadata.get("raw_text", ""),
                    encode_json(metadata.get("chunks", [])),
                    int(bool(metadata.get("is_image"))),
                    int(bool(metadata.get("used_ocr"))),
                    metadata.get("page_count"),
                    metadata.get("created_at") or now_iso(),
                ),
            )
            upsert_document_chunk_rows(
                conn,
                profile_id,
                chat_id,
                document_id,
                metadata.get("chunks", []),
                scope,
            )
            upsert_file_row(
                conn,
                profile_id,
                metadata.get("path", ""),
                metadata.get("name", ""),
                metadata.get("type", ""),
                document_id=document_id,
                scope=scope,
            )
    return metadata


def load_document_record(profile_id: str, document_id: str | None) -> dict[str, Any] | None:
    if not document_id:
        return None

    ensure_files()
    with db_connect() as conn:
        scope = ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        row = conn.execute(
            f"SELECT * FROM documents WHERE {owner_clause} AND id = ?",
            (*owner_params, document_id),
        ).fetchone()

    if not row:
        return None

    return {
        "document_id": row["id"],
        "path": row["path"],
        "name": row["file_name"],
        "type": row["file_type"],
        "context": row["context"] or "",
        "raw_text": row["raw_text"] or "",
        "chunks": decode_json(row["chunks"], []),
        "is_image": bool(row["is_image"]),
        "used_ocr": bool(row["used_ocr"]),
        "page_count": row["page_count"],
    }


def migrate_json_to_sqlite(conn: sqlite3.Connection) -> None:
    profiles_data = load_json(PROFILES_FILE, {"profiles": []})
    profiles = profiles_data.get("profiles", []) if isinstance(profiles_data, dict) else []
    if not isinstance(profiles, list):
        profiles = []

    for index, raw_profile in enumerate(profiles):
        if not isinstance(raw_profile, dict) or not raw_profile.get("id"):
            continue

        profile = {
            "id": raw_profile["id"],
            "name": raw_profile.get("name", "User"),
            "pin_salt": raw_profile.get("pin_salt", ""),
            "pin_hash": raw_profile.get("pin_hash", ""),
            "created_at": raw_profile.get("created_at") or now_iso(),
            "last_login_at": raw_profile.get("last_login_at") or raw_profile.get("created_at") or now_iso(),
        }
        upsert_profile_row(conn, profile)

        chats_path = profile_chats_file(profile["id"])
        memory_path = profile_memory_file(profile["id"])
        settings_path = profile_settings_file(profile["id"])

        legacy_chats = load_json(LEGACY_CHATS_FILE, []) if index == 0 else []
        raw_chats = load_json(chats_path, legacy_chats)
        if isinstance(raw_chats, list):
            for raw_chat in raw_chats:
                if isinstance(raw_chat, dict):
                    upsert_chat_row(conn, profile["id"], normalize_chat(raw_chat))

        legacy_memory = load_json(LEGACY_MEMORY_FILE, {}) if index == 0 else {}
        upsert_memory_rows(conn, profile["id"], load_json(memory_path, legacy_memory))
        upsert_settings_row(conn, profile["id"], load_json(settings_path, DEFAULT_SETTINGS))

    sessions_data = load_json(SESSIONS_FILE, {"sessions": {}})
    sessions = sessions_data.get("sessions", {}) if isinstance(sessions_data, dict) else {}
    if isinstance(sessions, dict):
        for token, session in sessions.items():
            if not isinstance(session, dict) or not session.get("profile_id"):
                continue
            upsert_session_row(
                conn,
                token=token,
                profile_id=session.get("profile_id"),
                created_at=session.get("created_at") or now_iso(),
                last_seen_at=session.get("last_seen_at") or now_iso(),
            )


def profile_dir(profile_id: str) -> Path:
    return PROFILES_DIR / Path(profile_id).name


def profile_chats_file(profile_id: str) -> Path:
    return profile_dir(profile_id) / "chats.json"


def profile_memory_file(profile_id: str) -> Path:
    return profile_dir(profile_id) / "memory.json"


def profile_settings_file(profile_id: str) -> Path:
    return profile_dir(profile_id) / "settings.json"


def controlled_upload_path_for_profile(profile_id: str) -> Path:
    owner_folder = hashlib.sha256(str(profile_id).encode("utf-8")).hexdigest()[:32]
    return ensure_controlled_file_path(PROCESSED_DIR / "uploads" / owner_folder)


def remove_profile_storage(profile_id: str) -> None:
    for path in (profile_dir(profile_id), controlled_upload_path_for_profile(profile_id)):
        try:
            if path.exists():
                shutil.rmtree(path)
        except OSError as exc:
            LOGGER.warning("Could not remove profile storage for %s: %s", profile_id, type(exc).__name__)


def public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if profile.get("auth_mode") == "account":
        user = profile["account_user"]
        return {
            "id": user["id"],
            "user_id": user["id"],
            "name": user["email"],
            "email": user["email"],
            "provider": user["provider"],
            "provider_id": user["provider_id"],
            "onboarding_completed": bool(user["onboarding_completed"]),
            "created_at": user.get("created_at"),
            "last_login_at": user.get("last_login_at"),
            "mode": "account",
        }

    payload = {
        "id": profile["id"],
        "name": profile.get("name", "User"),
        "created_at": profile.get("created_at"),
        "last_login_at": profile.get("last_login_at"),
        "mode": "guest" if profile.get("is_guest") else "profile",
    }

    if profile.get("is_guest"):
        payload["guest_id"] = profile.get("guest_id")
    elif profile.get("profile_kind") == "account":
        payload["device_bound"] = True

    return payload


def load_profiles_data() -> dict[str, Any]:
    ensure_files()
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT profiles.id, profiles.name, profiles.pin_salt, profiles.pin_hash,
                profiles.profile_kind, profiles.user_id, profiles.device_id,
                profiles.created_at, profiles.last_login_at
            FROM profiles
            LEFT JOIN guest_sessions ON guest_sessions.profile_id = profiles.id
            LEFT JOIN users ON users.workspace_profile_id = profiles.id
            WHERE guest_sessions.profile_id IS NULL
                AND users.workspace_profile_id IS NULL
                AND profiles.profile_kind = 'legacy'
            ORDER BY profiles.created_at ASC
            """
        ).fetchall()
    return {"profiles": [row_to_profile(row) for row in rows]}


def save_profiles_data(data: dict[str, Any]) -> None:
    profiles = data.get("profiles", []) if isinstance(data, dict) else []
    if not isinstance(profiles, list):
        return

    with DATA_LOCK:
        with db_connect() as conn:
            for profile in profiles:
                if isinstance(profile, dict) and profile.get("id"):
                    upsert_profile_row(conn, profile)


def hash_pin(pin: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        salt.encode("utf-8"),
        PIN_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PIN_HASH_ITERATIONS}${digest}"


def verify_pin(profile: dict[str, Any], pin: str) -> bool:
    expected = profile.get("pin_hash", "")
    salt = profile.get("pin_salt", "")
    if not expected or not salt:
        return False

    if expected.startswith("pbkdf2_sha256$"):
        calculated = hash_pin(pin, salt)
    else:
        # Existing profiles used a salted SHA-256 digest. Keep them usable
        # while all newly created device-bound profiles use PBKDF2.
        calculated = hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()
    return secrets.compare_digest(expected, calculated)


def generate_pin_reset_code() -> str:
    upper_bound = 10 ** PIN_RESET_CODE_LENGTH
    return f"{secrets.randbelow(upper_bound):0{PIN_RESET_CODE_LENGTH}d}"


def hash_verification_code(code: str, salt: str) -> str:
    normalized = re.sub(r"\s+", "", str(code or ""))
    return hash_pin(normalized, salt)


def should_expose_dev_pin_reset_code() -> bool:
    env_name = (
        os.getenv("FEBGUY_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENV")
        or "development"
    ).strip().lower()
    return env_name not in {"prod", "production"}


def require_email_service_configured() -> None:
    if not RESEND_API_KEY or not EMAIL_FROM:
        raise HTTPException(status_code=503, detail="Email service is not configured.")


def send_resend_email(*, to_email: str, subject: str, text: str, html: str | None = None) -> None:
    require_email_service_configured()
    try:
        response = requests.post(
            RESEND_EMAIL_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "text": text,
                **({"html": html} if html else {}),
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        LOGGER.warning("Resend email request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Email could not be sent.") from exc

    if not 200 <= response.status_code < 300:
        LOGGER.warning("Resend email request failed with status %s", response.status_code)
        raise HTTPException(status_code=502, detail="Email could not be sent.")


def send_pin_reset_email(*, to_email: str, profile_name: str, code: str) -> None:
    safe_profile_name = (profile_name or "your profile").strip() or "your profile"
    text = (
        f"Your FebGuyAI PIN reset code for {safe_profile_name} is {code}.\n\n"
        f"This code expires in {PIN_RESET_CODE_TTL_SECONDS // 60} minutes. "
        "If you did not request this, you can ignore this email."
    )
    html_body = (
        "<p>Your FebGuyAI PIN reset code for "
        f"<strong>{html.escape(safe_profile_name)}</strong> is:</p>"
        f"<p style=\"font-size:24px;font-weight:700;letter-spacing:4px;\">{html.escape(code)}</p>"
        f"<p>This code expires in {PIN_RESET_CODE_TTL_SECONDS // 60} minutes.</p>"
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    send_resend_email(
        to_email=to_email,
        subject="Your FebGuyAI PIN reset code",
        text=text,
        html=html_body,
    )


def find_profile(profile_id: str) -> dict[str, Any] | None:
    ensure_files()
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT profiles.id, profiles.name, profiles.pin_salt, profiles.pin_hash,
                profiles.profile_kind, profiles.user_id, profiles.device_id,
                profiles.created_at, profiles.last_login_at, guest_sessions.guest_id
            FROM profiles
            LEFT JOIN guest_sessions ON guest_sessions.profile_id = profiles.id
            WHERE profiles.id = ?
            """,
            (profile_id,),
        ).fetchone()
    return row_to_profile(row) if row else None


def find_user_by_id(user_id: str) -> dict[str, Any] | None:
    ensure_files()
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT id, auth_user_id, email, provider, provider_id,
                onboarding_completed, workspace_profile_id, created_at,
                updated_at, last_login_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_user(row) if row else None


def find_legacy_profile_by_name(name: str | None) -> dict[str, Any] | None:
    normalized_name = (name or "").strip()
    if not normalized_name:
        return None

    ensure_files()
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT profiles.id, profiles.name, profiles.pin_salt, profiles.pin_hash,
                profiles.profile_kind, profiles.user_id, profiles.device_id,
                profiles.created_at, profiles.last_login_at, NULL AS guest_id
            FROM profiles
            LEFT JOIN guest_sessions ON guest_sessions.profile_id = profiles.id
            LEFT JOIN users ON users.workspace_profile_id = profiles.id
            WHERE lower(profiles.name) = lower(?)
                AND profiles.profile_kind = 'legacy'
                AND guest_sessions.profile_id IS NULL
                AND users.workspace_profile_id IS NULL
            ORDER BY profiles.created_at ASC
            LIMIT 1
            """,
            (normalized_name,),
        ).fetchone()
    return row_to_profile(row) if row else None


def account_owner_id(profile: dict[str, Any]) -> str | None:
    if profile.get("auth_mode") == "account":
        return profile["account_user"]["id"]
    if profile.get("profile_kind") == "account":
        return profile.get("user_id")
    return None


def load_device_bound_profiles(user_id: str, device_id: str) -> list[dict[str, Any]]:
    ensure_files()
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, pin_salt, pin_hash, profile_kind, user_id, device_id,
                created_at, last_login_at, NULL AS guest_id
            FROM profiles
            WHERE profile_kind = 'account'
                AND user_id = ?
                AND device_id = ?
            ORDER BY created_at ASC
            """,
            (user_id, device_id),
        ).fetchall()
    return [row_to_profile(row) for row in rows]


def get_owned_device_profile(profile_id: str, user_id: str, device_id: str) -> dict[str, Any]:
    profile = find_profile(profile_id)
    if (
        not profile
        or profile.get("profile_kind") != "account"
        or profile.get("user_id") != user_id
        or profile.get("device_id") != device_id
    ):
        raise HTTPException(status_code=404, detail=DEVICE_PROFILE_NOT_FOUND)
    return profile


def store_profile_pin_reset_code(
    *,
    user_id: str,
    profile_id: str,
    device_id: str,
    code: str,
) -> str:
    salt = secrets.token_hex(16)
    timestamp = now_iso()
    expires_at = datetime.fromtimestamp(time.time() + PIN_RESET_CODE_TTL_SECONDS).isoformat(
        timespec="seconds"
    )
    with DATA_LOCK:
        with db_connect() as conn:
            ensure_device_row(conn, device_id)
            conn.execute(
                """
                UPDATE profile_pin_reset_codes
                SET used_at = ?
                WHERE user_id = ?
                    AND profile_id = ?
                    AND device_id = ?
                    AND used_at IS NULL
                """,
                (timestamp, user_id, profile_id, device_id),
            )
            conn.execute(
                """
                INSERT INTO profile_pin_reset_codes
                    (id, user_id, profile_id, device_id, code_salt, code_hash,
                     expires_at, used_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    profile_id,
                    device_id,
                    salt,
                    hash_verification_code(code, salt),
                    expires_at,
                    timestamp,
                ),
            )
    return expires_at


def invalidate_profile_pin_reset_codes(*, user_id: str, profile_id: str, device_id: str) -> None:
    with DATA_LOCK:
        with db_connect() as conn:
            conn.execute(
                """
                UPDATE profile_pin_reset_codes
                SET used_at = ?
                WHERE user_id = ?
                    AND profile_id = ?
                    AND device_id = ?
                    AND used_at IS NULL
                """,
                (now_iso(), user_id, profile_id, device_id),
            )


def verify_profile_pin_reset_code(
    *,
    user_id: str,
    profile_id: str,
    device_id: str,
    code: str,
    mark_used: bool = False,
) -> None:
    normalized_code = re.sub(r"\s+", "", str(code or ""))
    if not normalized_code:
        raise HTTPException(status_code=400, detail="Verification code is required.")

    with DATA_LOCK:
        with db_connect() as conn:
            row = conn.execute(
                """
                SELECT id, code_salt, code_hash, expires_at, used_at
                FROM profile_pin_reset_codes
                WHERE user_id = ?
                    AND profile_id = ?
                    AND device_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, profile_id, device_id),
            ).fetchone()

            if not row or row["used_at"]:
                raise HTTPException(status_code=400, detail="Verification code is invalid or expired.")

            try:
                expired = datetime.fromisoformat(row["expires_at"]) < datetime.now()
            except ValueError:
                expired = True
            if expired:
                raise HTTPException(status_code=400, detail="Verification code is invalid or expired.")

            expected = row["code_hash"]
            calculated = hash_verification_code(normalized_code, row["code_salt"])
            if not secrets.compare_digest(expected, calculated):
                raise HTTPException(status_code=401, detail="Verification code is incorrect.")

            if mark_used:
                conn.execute(
                    "UPDATE profile_pin_reset_codes SET used_at = ? WHERE id = ?",
                    (now_iso(), row["id"]),
                )


def is_guest_profile_id(profile_id: str | None) -> bool:
    if not profile_id:
        return False

    ensure_files()
    with db_connect() as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM guest_sessions WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        )


def save_profile(profile: dict[str, Any]) -> None:
    with DATA_LOCK:
        with db_connect() as conn:
            upsert_profile_row(conn, profile)


def ensure_profile_defaults(
    conn: sqlite3.Connection,
    profile_id: str,
    import_legacy: bool = False,
    scope: dict[str, str | None] | None = None,
) -> None:
    scope = scope or ownership_scope_for_profile(profile_id, conn)
    owner_clause, owner_params = owner_where(scope)
    if not conn.execute(
        f"SELECT 1 FROM memories WHERE {owner_clause}",
        owner_params,
    ).fetchone():
        legacy_memory = load_json(LEGACY_MEMORY_FILE, {}) if import_legacy else {}
        upsert_memory_rows(conn, profile_id, legacy_memory, scope)

    if not conn.execute(
        f"SELECT 1 FROM settings WHERE {owner_clause}",
        owner_params,
    ).fetchone():
        upsert_settings_row(conn, profile_id, DEFAULT_SETTINGS, scope)


def ensure_profile_files(profile_id: str, import_legacy: bool = False) -> None:
    p_dir = profile_dir(profile_id)
    p_dir.mkdir(parents=True, exist_ok=True)
    ensure_files()

    with DATA_LOCK:
        with db_connect() as conn:
            ensure_profile_defaults(conn, profile_id, import_legacy)


def load_sessions() -> dict[str, Any]:
    ensure_files()
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT token, profile_id, mode, guest_id, device_id, created_at, last_seen_at
            FROM sessions
            """
        ).fetchall()
    return {
        "sessions": {
            row["token"]: {
                "profile_id": row["profile_id"],
                "mode": row["mode"] or "profile",
                "guest_id": row["guest_id"],
                "device_id": row["device_id"],
                "created_at": row["created_at"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in rows
        }
    }


def save_sessions(data: dict[str, Any]) -> None:
    sessions = data.get("sessions", {}) if isinstance(data, dict) else {}
    if not isinstance(sessions, dict):
        return

    with DATA_LOCK:
        with db_connect() as conn:
            conn.execute(
                """
                DELETE FROM sessions
                WHERE profile_id NOT IN (SELECT id FROM profiles)
                """
            )
            for token, session in sessions.items():
                if not isinstance(session, dict) or not session.get("profile_id"):
                    continue
                if not conn.execute(
                    "SELECT 1 FROM profiles WHERE id = ?",
                    (session.get("profile_id"),),
                ).fetchone():
                    continue
                upsert_session_row(
                    conn,
                    token=token,
                    profile_id=session.get("profile_id"),
                    mode=session.get("mode") if session.get("mode") in {"guest", "profile"} else "profile",
                    guest_id=session.get("guest_id"),
                    device_id=session.get("device_id"),
                    created_at=session.get("created_at") or now_iso(),
                    last_seen_at=session.get("last_seen_at") or now_iso(),
                )


def create_session(
    profile_id: str,
    *,
    mode: str = "profile",
    guest_id: str | None = None,
    device_id: str | None = None,
) -> str:
    if mode not in {"guest", "profile"}:
        raise ValueError("Workspace sessions must be guest or profile sessions.")

    token = secrets.token_urlsafe(32)
    with DATA_LOCK:
        with db_connect() as conn:
            upsert_session_row(
                conn,
                token=token,
                profile_id=profile_id,
                mode=mode,
                guest_id=guest_id,
                device_id=device_id,
            )
    return token


def create_account_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    timestamp = now_iso()
    with DATA_LOCK:
        with db_connect() as conn:
            conn.execute(
                """
                INSERT INTO account_sessions (token, user_id, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user_id, timestamp, timestamp),
            )
    return token


def delete_session(token: str) -> None:
    clear_session_caches(token)
    with DATA_LOCK:
        with db_connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.execute("DELETE FROM account_sessions WHERE token = ?", (token,))


def find_account_session_user(token: str) -> dict[str, Any] | None:
    ensure_files()
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT users.id, users.auth_user_id, users.email, users.provider,
                users.provider_id, users.onboarding_completed,
                users.workspace_profile_id, users.created_at, users.updated_at,
                users.last_login_at
            FROM account_sessions
            JOIN users ON users.id = account_sessions.user_id
            WHERE account_sessions.token = ?
            """,
            (token,),
        ).fetchone()
    return row_to_user(row) if row else None


def account_workspace_profile(user: dict[str, Any]) -> dict[str, Any] | None:
    profile = find_profile(user["workspace_profile_id"])
    if not profile:
        return None
    profile["auth_mode"] = "account"
    profile["account_user"] = user
    profile["user_id"] = user["id"]
    return profile


def verify_supabase_access_token(access_token: str) -> dict[str, str]:
    token = (access_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Supabase access token is required.")
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=503,
            detail="Account sign-in is not configured on the backend yet.",
        )

    try:
        response = requests.get(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=15,
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=503,
            detail="Account sign-in service is temporarily unavailable.",
        )

    if response.status_code in {401, 403}:
        raise HTTPException(status_code=401, detail="Invalid or expired account session.")
    if not response.ok:
        raise HTTPException(status_code=502, detail="Account sign-in could not be verified.")

    try:
        auth_user = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Account sign-in returned an invalid response.")

    auth_user_id = str(auth_user.get("id") or "").strip()
    email = str(auth_user.get("email") or "").strip().lower()
    if not auth_user_id or not email:
        raise HTTPException(status_code=401, detail="Signed-in account has no usable identity.")

    app_metadata = auth_user.get("app_metadata") if isinstance(auth_user.get("app_metadata"), dict) else {}
    identities = auth_user.get("identities") if isinstance(auth_user.get("identities"), list) else []
    provider = str(app_metadata.get("provider") or "email").strip().lower() or "email"
    matching_identity = next(
        (
            identity for identity in identities
            if isinstance(identity, dict) and identity.get("provider") == provider
        ),
        identities[0] if identities and isinstance(identities[0], dict) else {},
    )
    provider_id = str(
        matching_identity.get("identity_id")
        or matching_identity.get("id")
        or auth_user_id
    ).strip()
    return {
        "auth_user_id": auth_user_id,
        "email": email,
        "provider": provider,
        "provider_id": provider_id,
    }


def create_or_update_account_user(identity: dict[str, str]) -> dict[str, Any]:
    timestamp = now_iso()
    with DATA_LOCK:
        with db_connect() as conn:
            row = conn.execute(
                """
                SELECT id, auth_user_id, email, provider, provider_id,
                    onboarding_completed, workspace_profile_id, created_at,
                    updated_at, last_login_at
                FROM users
                WHERE auth_user_id = ?
                """,
                (identity["auth_user_id"],),
            ).fetchone()

            email_owner = conn.execute(
                "SELECT auth_user_id FROM users WHERE email = ?",
                (identity["email"],),
            ).fetchone()
            if email_owner and email_owner["auth_user_id"] != identity["auth_user_id"]:
                raise HTTPException(
                    status_code=409,
                    detail="This email is already connected to another account.",
                )

            if row:
                conn.execute(
                    """
                    UPDATE users
                    SET email = ?, provider = ?, provider_id = ?,
                        updated_at = ?, last_login_at = ?
                    WHERE id = ?
                    """,
                    (
                        identity["email"],
                        identity["provider"],
                        identity["provider_id"],
                        timestamp,
                        timestamp,
                        row["id"],
                    ),
                )
                user_id = row["id"]
            else:
                user_id = identity["auth_user_id"]
                workspace_profile_id = str(uuid.uuid4())
                upsert_profile_row(
                    conn,
                    {
                        "id": workspace_profile_id,
                        "name": identity["email"],
                        "pin_salt": "",
                        "pin_hash": "",
                        "created_at": timestamp,
                        "last_login_at": timestamp,
                    },
                )
                conn.execute(
                    """
                    INSERT INTO users
                        (id, auth_user_id, email, provider, provider_id,
                         onboarding_completed, workspace_profile_id,
                         created_at, updated_at, last_login_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        identity["auth_user_id"],
                        identity["email"],
                        identity["provider"],
                        identity["provider_id"],
                        workspace_profile_id,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )

            refreshed = conn.execute(
                """
                SELECT id, auth_user_id, email, provider, provider_id,
                    onboarding_completed, workspace_profile_id, created_at,
                    updated_at, last_login_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

    user = row_to_user(refreshed)
    ensure_profile_files(user["workspace_profile_id"])
    return user


def create_or_load_guest_session(device_id: str | None) -> dict[str, Any]:
    normalized_device_id = validate_device_id(device_id)
    if not normalized_device_id:
        raise HTTPException(status_code=400, detail="Guest mode requires a valid device ID.")
    cached_response = cached_guest_start_response(normalized_device_id)
    if cached_response:
        return cached_response

    ensure_files()
    session_token = ""
    timestamp = now_iso()
    profile: dict[str, Any] | None = None
    scope: dict[str, str | None] | None = None
    guest_id = ""
    profile_id = ""
    old_session_token: str | None = None
    created_profile = False
    reused_existing_session = False

    try:
        with DATA_LOCK:
            with db_connect() as conn:
                ensure_device_row(conn, normalized_device_id)
                guest_row = conn.execute(
                    """
                    SELECT guest_id, device_id, profile_id, session_token, created_at, last_seen_at
                    FROM guest_sessions
                    WHERE device_id = ?
                    """,
                    (normalized_device_id,),
                ).fetchone()

                if guest_row:
                    old_session_token = guest_row["session_token"]
                    profile_row = conn.execute(
                        """
                        SELECT profiles.id, profiles.name, profiles.pin_salt, profiles.pin_hash,
                            profiles.profile_kind, profiles.user_id, profiles.device_id,
                            profiles.created_at, profiles.last_login_at, guest_sessions.guest_id
                        FROM profiles
                        JOIN guest_sessions ON guest_sessions.profile_id = profiles.id
                        WHERE guest_sessions.guest_id = ?
                        """,
                        (guest_row["guest_id"],),
                    ).fetchone()

                    if profile_row:
                        profile = row_to_profile(profile_row)
                        guest_id = guest_row["guest_id"]
                        profile_id = guest_row["profile_id"]
                        if old_session_token and conn.execute(
                            """
                            SELECT token
                            FROM sessions
                            WHERE token = ? AND profile_id = ?
                            """,
                            (old_session_token, profile_id),
                        ).fetchone():
                            session_token = old_session_token
                            reused_existing_session = True
                    else:
                        conn.execute(
                            "DELETE FROM guest_sessions WHERE device_id = ?",
                            (normalized_device_id,),
                        )

                if profile is None:
                    created_profile = True
                    guest_id = str(uuid.uuid4())
                    profile_id = str(uuid.uuid4())
                    profile = {
                        "id": profile_id,
                        "name": "Guest",
                        "pin_salt": "",
                        "pin_hash": "",
                        "profile_kind": "guest",
                        "device_id": normalized_device_id,
                        "created_at": timestamp,
                        "last_login_at": timestamp,
                        "is_guest": True,
                        "guest_id": guest_id,
                    }
                    upsert_profile_row(conn, profile)
                    conn.execute(
                        """
                        INSERT INTO guest_sessions
                            (guest_id, device_id, profile_id, session_token, created_at, last_seen_at)
                        VALUES (?, ?, ?, NULL, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            guest_id = excluded.guest_id,
                            profile_id = excluded.profile_id,
                            session_token = NULL,
                            last_seen_at = excluded.last_seen_at
                        """,
                        (
                            guest_id,
                            normalized_device_id,
                            profile_id,
                            timestamp,
                            timestamp,
                        ),
                    )

                scope = {
                    "mode": "guest",
                    "profile_id": profile_id,
                    "user_id": None,
                    "guest_id": guest_id,
                    "device_id": normalized_device_id,
                }
                if not session_token:
                    session_token = secrets.token_urlsafe(32)
                if not reused_existing_session:
                    upsert_session_row(
                        conn,
                        token=session_token,
                        profile_id=profile_id,
                        mode="guest",
                        guest_id=guest_id,
                        device_id=normalized_device_id,
                        created_at=timestamp,
                        last_seen_at=timestamp,
                    )
                    conn.execute(
                        """
                        INSERT INTO guest_sessions
                            (guest_id, device_id, profile_id, session_token, created_at, last_seen_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            guest_id = excluded.guest_id,
                            profile_id = excluded.profile_id,
                            session_token = excluded.session_token,
                            last_seen_at = excluded.last_seen_at
                        """,
                        (
                            guest_id,
                            normalized_device_id,
                            profile_id,
                            session_token,
                            timestamp,
                            timestamp,
                        ),
                    )
                    if old_session_token and old_session_token != session_token:
                        conn.execute(
                            "DELETE FROM sessions WHERE token = ?",
                            (old_session_token,),
                        )
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception(
            "Guest session startup failed device_id=%s db_hint=%s",
            normalized_device_id,
            database_error_hint(exc),
        )
        raise

    if scope:
        if created_profile:
            cache_fresh_guest_defaults(profile_id, guest_id, normalized_device_id)
            ensure_guest_defaults_async(
                profile_id,
                scope,
                delay_seconds=GUEST_BACKGROUND_SETUP_DELAY_SECONDS,
            )
        else:
            touch_guest_session_async(
                session_token,
                profile_id,
                guest_id,
                normalized_device_id,
                delay_seconds=GUEST_BACKGROUND_SETUP_DELAY_SECONDS,
            )
    log_activity_async(
        profile_id,
        "guest_session_started",
        {"mode": "guest"},
        delay_seconds=GUEST_BACKGROUND_SETUP_DELAY_SECONDS,
    )
    def ensure_profile_dir_later() -> None:
        time.sleep(GUEST_BACKGROUND_SETUP_DELAY_SECONDS)
        profile_dir(profile_id).mkdir(parents=True, exist_ok=True)

    threading.Thread(target=ensure_profile_dir_later, daemon=True).start()
    profile["is_guest"] = True
    profile["guest_id"] = guest_id
    cache_session_access(
        session_token,
        mode="guest",
        profile_kind=profile.get("profile_kind"),
        device_id=normalized_device_id,
        profile=profile,
        guest_id=guest_id,
        user_id=profile.get("user_id"),
    )
    cache_guest_start_response(
        device_id=normalized_device_id,
        profile=profile,
        token=session_token,
        guest_id=guest_id,
    )
    return {
        "profile": public_profile(profile),
        "token": session_token,
        "session_mode": "guest",
        "guest": {"id": guest_id},
    }


def consume_guest_usage(
    profile: dict[str, Any],
    device_id: str | None,
    *limit_keys: str,
) -> None:
    if not profile.get("is_guest"):
        return

    normalized_device_id = validate_device_id(device_id)
    if not normalized_device_id:
        raise HTTPException(status_code=400, detail="Guest mode requires a valid device ID.")

    requested_keys = list(dict.fromkeys(key for key in limit_keys if key in GUEST_USAGE_LIMITS))
    if not requested_keys:
        return

    period_start_at = datetime.now()
    timestamp = period_start_at.isoformat(timespec="seconds")
    period_end = (period_start_at + timedelta(days=1)).isoformat(timespec="seconds")
    guest_id = profile.get("guest_id")
    profile_device_id = profile.get("device_id")
    if guest_id and profile_device_id:
        if profile_device_id != normalized_device_id:
            raise HTTPException(status_code=403, detail="This guest session belongs to another device.")

    cached_usage = (
        cached_guest_usage_status(str(guest_id), normalized_device_id)
        if guest_id
        else None
    )
    cached_limits = cached_usage.get("limits", {}) if cached_usage else {}
    for limit_key in requested_keys:
        cached_limit = cached_limits.get(limit_key)
        if cached_limit and int(cached_limit.get("remaining", 0)) <= 0:
            raise HTTPException(status_code=429, detail=GUEST_LIMIT_MESSAGE)

    cache_guest_id: str | None = str(guest_id) if guest_id else None
    with data_write_lock():
        with db_connect() as conn:
            if not guest_id:
                guest_row = conn.execute(
                    """
                    SELECT guest_id, device_id
                    FROM guest_sessions
                    WHERE profile_id = ?
                    """,
                    (profile["id"],),
                ).fetchone()

                if not guest_row:
                    raise HTTPException(status_code=401, detail="Guest session could not be verified.")

                if guest_row["device_id"] != normalized_device_id:
                    raise HTTPException(status_code=403, detail="This guest session belongs to another device.")
                guest_id = guest_row["guest_id"]
                cache_guest_id = guest_id

            if not DATABASE.is_postgres_active():
                for limit_key in requested_keys:
                    if cached_limits.get(limit_key):
                        continue
                    limit = GUEST_USAGE_LIMITS[limit_key]
                    usage_row = conn.execute(
                        """
                        SELECT used_count
                        FROM usage_limits
                        WHERE guest_id = ? AND device_id = ? AND limit_key = ?
                        """,
                        (guest_id, normalized_device_id, limit_key),
                    ).fetchone()
                    used_count = int(usage_row["used_count"]) if usage_row else 0
                    if used_count >= limit:
                        raise HTTPException(status_code=429, detail=GUEST_LIMIT_MESSAGE)

            columns = table_column_names(conn, "usage_limits")
            for limit_key in requested_keys:
                limit = GUEST_USAGE_LIMITS[limit_key]
                insert_values: dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    "guest_id": guest_id,
                    "device_id": normalized_device_id,
                    "limit_key": limit_key,
                    "period_start": timestamp,
                    "period_end": period_end,
                    "used_count": 1,
                    "max_count": limit,
                    "metadata": encode_json({"mode": "guest", "limit_key": limit_key}),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                insert_columns = [
                    column
                    for column in (
                        "id",
                        "guest_id",
                        "device_id",
                        "limit_key",
                        "period_start",
                        "period_end",
                        "used_count",
                        "max_count",
                        "metadata",
                        "created_at",
                        "updated_at",
                    )
                    if column in columns
                ]
                placeholders = ", ".join(
                    "CAST(? AS jsonb)"
                    if column == "metadata" and DATABASE.is_postgres_active()
                    else "?"
                    for column in insert_columns
                )
                update_assignments = [
                    "used_count = usage_limits.used_count + 1",
                    "max_count = excluded.max_count",
                    "updated_at = excluded.updated_at",
                ]
                if "period_start" in insert_columns:
                    update_assignments.append(
                        "period_start = COALESCE(usage_limits.period_start, excluded.period_start)"
                    )
                if "period_end" in insert_columns:
                    update_assignments.append("period_end = excluded.period_end")
                if "metadata" in insert_columns:
                    update_assignments.append("metadata = excluded.metadata")

                try:
                    if DATABASE.is_postgres_active():
                        row = conn.execute(
                            f"""
                            INSERT INTO usage_limits ({", ".join(insert_columns)})
                            VALUES ({placeholders})
                            ON CONFLICT(guest_id, device_id, limit_key) DO UPDATE SET
                                {", ".join(update_assignments)}
                            WHERE usage_limits.used_count < excluded.max_count
                            RETURNING used_count
                            """,
                            tuple(insert_values[column] for column in insert_columns),
                        ).fetchone()
                        if row is None:
                            raise HTTPException(status_code=429, detail=GUEST_LIMIT_MESSAGE)
                    else:
                        conn.execute(
                            f"""
                            INSERT INTO usage_limits ({", ".join(insert_columns)})
                            VALUES ({placeholders})
                            ON CONFLICT(guest_id, device_id, limit_key) DO UPDATE SET
                                {", ".join(update_assignments)}
                            """,
                            tuple(insert_values[column] for column in insert_columns),
                        )
                except Exception as exc:
                    if isinstance(exc, HTTPException):
                        raise
                    LOGGER.exception(
                        "DB write failed table=usage_limits limit_key=%s db_hint=%s",
                        limit_key,
                        database_error_hint(exc),
                    )
                    raise
    clear_guest_usage_status_cache(cache_guest_id, normalized_device_id)


def get_guest_usage_status(
    profile: dict[str, Any],
    device_id: str | None,
) -> dict[str, Any]:
    if not profile.get("is_guest"):
        return {"guest": False, "limits": {}}

    normalized_device_id = validate_device_id(device_id)
    if not normalized_device_id:
        raise HTTPException(status_code=400, detail="Guest mode requires a valid device ID.")

    guest_id = profile.get("guest_id")
    profile_device_id = profile.get("device_id")
    if guest_id and profile_device_id:
        if profile_device_id != normalized_device_id:
            raise HTTPException(status_code=403, detail="This guest session belongs to another device.")
    else:
        with DATA_LOCK:
            with db_connect() as conn:
                guest_row = conn.execute(
                    """
                    SELECT guest_id, device_id
                    FROM guest_sessions
                    WHERE profile_id = ?
                    """,
                    (profile["id"],),
                ).fetchone()

                if not guest_row:
                    raise HTTPException(status_code=401, detail="Guest session could not be verified.")

                if guest_row["device_id"] != normalized_device_id:
                    raise HTTPException(status_code=403, detail="This guest session belongs to another device.")
                guest_id = guest_row["guest_id"]

    cached = cached_guest_usage_status(str(guest_id), normalized_device_id)
    if cached:
        return cached

    with db_connect() as conn:
        usage_rows = {
            row["limit_key"]: int(row["used_count"])
            for row in conn.execute(
                """
                SELECT limit_key, used_count
                FROM usage_limits
                WHERE guest_id = ? AND device_id = ?
                """,
                (guest_id, normalized_device_id),
            ).fetchall()
        }

    limits = {}
    for limit_key, maximum in GUEST_USAGE_LIMITS.items():
        used = min(maximum, max(0, usage_rows.get(limit_key, 0)))
        limits[limit_key] = {
            "used": used,
            "limit": maximum,
            "remaining": max(0, maximum - used),
        }

    status = {"guest": True, "limits": limits}
    cache_guest_usage_status(str(guest_id), normalized_device_id, status)
    return status


def insert_activity_event(
    conn: sqlite3.Connection,
    profile_id: str | None,
    event_type: str,
    detail: dict[str, Any] | str | None = None,
    scope: dict[str, str | None] | None = None,
) -> None:
    safe_detail = detail if isinstance(detail, str) else encode_json(detail or {})
    scope = scope or (ownership_scope_for_profile(profile_id, conn) if profile_id else None)
    ensure_scope_device_row(conn, scope)
    conn.execute(
        """
        INSERT INTO activity_events
            (id, profile_id, user_id, guest_id, device_id,
             event_type, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            profile_id,
            *(owner_values(scope) if scope else (None, None, None)),
            event_type,
            clip_text(safe_detail, 1500),
            now_iso(),
        ),
    )


def log_activity(
    profile_id: str | None,
    event_type: str,
    detail: dict[str, Any] | str | None = None,
) -> None:
    try:
        with DATA_LOCK:
            with db_connect() as conn:
                insert_activity_event(conn, profile_id, event_type, detail)
    except Exception:
        pass


def log_activity_async(
    profile_id: str | None,
    event_type: str,
    detail: dict[str, Any] | str | None = None,
    delay_seconds: float = 0.0,
) -> None:
    def worker() -> None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        log_activity(profile_id, event_type, detail)

    threading.Thread(
        target=worker,
        daemon=True,
    ).start()


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing session.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing session.")
    return token


def cache_session_access(
    token: str | None,
    *,
    mode: str | None,
    profile_kind: str | None,
    device_id: str | None,
    profile: dict[str, Any] | None = None,
    guest_id: str | None = None,
    user_id: str | None = None,
) -> None:
    if not token:
        return
    cached = {
        "checked_at": time.monotonic(),
        "mode": mode,
        "profile_kind": profile_kind,
        "device_id": device_id,
        "guest_id": guest_id,
        "user_id": user_id,
    }
    if isinstance(profile, dict):
        cached["profile"] = dict(profile)
    with SESSION_ACCESS_LOCK:
        SESSION_ACCESS_CACHE[token] = cached


def cached_session_access(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with SESSION_ACCESS_LOCK:
        cached = SESSION_ACCESS_CACHE.get(token)
        if not cached:
            return None
        if time.monotonic() - float(cached.get("checked_at") or 0.0) > SESSION_ACCESS_CACHE_SECONDS:
            SESSION_ACCESS_CACHE.pop(token, None)
            return None
        return dict(cached)


def enforce_cached_device_access(cached: dict[str, Any], device_id: str | None) -> None:
    if (
        cached.get("mode") == "profile"
        and cached.get("profile_kind") == "account"
        and (not device_id or cached.get("device_id") != device_id)
    ):
        raise HTTPException(status_code=403, detail=DEVICE_PROFILE_NOT_FOUND)


def cached_session_context(token: str) -> dict[str, Any] | None:
    cached = cached_session_access(token)
    profile = cached.get("profile") if cached else None
    if not cached or not isinstance(profile, dict):
        return None
    mode = str(cached.get("mode") or "")
    if mode not in SESSION_MODES:
        return None
    return {
        "token": token,
        "mode": mode,
        "profile": dict(profile),
        "user_id": cached.get("user_id"),
        "guest_id": cached.get("guest_id"),
        "device_id": cached.get("device_id"),
    }


def cached_guest_session_context(token: str) -> dict[str, Any] | None:
    cached = cached_session_context(token)
    if cached and cached.get("mode") == "guest":
        return cached
    return None


def cached_guest_start_response(device_id: str | None) -> dict[str, Any] | None:
    if not device_id:
        return None
    with GUEST_DEVICE_SESSION_LOCK:
        cached = GUEST_DEVICE_SESSION_CACHE.get(device_id)
        if not cached:
            return None
        if time.monotonic() - float(cached.get("checked_at") or 0.0) > SESSION_ACCESS_CACHE_SECONDS:
            GUEST_DEVICE_SESSION_CACHE.pop(device_id, None)
            return None
        return {
            "profile": dict(cached["profile"]),
            "token": cached["token"],
            "session_mode": "guest",
            "guest": dict(cached["guest"]),
        }


def cache_guest_start_response(
    *,
    device_id: str,
    profile: dict[str, Any],
    token: str,
    guest_id: str,
) -> None:
    with GUEST_DEVICE_SESSION_LOCK:
        GUEST_DEVICE_SESSION_CACHE[device_id] = {
            "checked_at": time.monotonic(),
            "profile": public_profile(profile),
            "token": token,
            "guest": {"id": guest_id},
        }


def cache_fresh_guest_defaults(profile_id: str, guest_id: str, device_id: str) -> None:
    cache_set(SETTINGS_CACHE, profile_id, DEFAULT_SETTINGS.copy())
    cache_set(MEMORY_CACHE, profile_id, normalize_memory({}))
    cache_guest_usage_status(
        guest_id,
        device_id,
        {
            "guest": True,
            "limits": {
                key: {"used": 0, "limit": limit, "remaining": limit}
                for key, limit in GUEST_USAGE_LIMITS.items()
            },
        },
    )


def clear_session_caches(token: str | None) -> None:
    if not token:
        return
    with SESSION_ACCESS_LOCK:
        SESSION_ACCESS_CACHE.pop(token, None)
    with GUEST_DEVICE_SESSION_LOCK:
        for device_id, cached in list(GUEST_DEVICE_SESSION_CACHE.items()):
            if cached.get("token") == token:
                GUEST_DEVICE_SESSION_CACHE.pop(device_id, None)


def touch_session_last_seen(token: str, table: str = "sessions") -> None:
    if table not in {"sessions", "account_sessions"}:
        return
    try:
        with DATA_LOCK:
            with db_connect() as conn:
                conn.execute(
                    f"UPDATE {table} SET last_seen_at = ? WHERE token = ?",
                    (now_iso(), token),
                )
    except Exception:
        pass


def touch_session_last_seen_async(token: str, table: str = "sessions") -> None:
    threading.Thread(
        target=touch_session_last_seen,
        args=(token, table),
        daemon=True,
    ).start()


def touch_guest_session_async(
    token: str,
    profile_id: str,
    guest_id: str,
    device_id: str,
    delay_seconds: float = 0.0,
) -> None:
    def worker() -> None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        timestamp = now_iso()
        try:
            with DATA_LOCK:
                with db_connect() as conn:
                    conn.execute(
                        "UPDATE sessions SET last_seen_at = ? WHERE token = ?",
                        (timestamp, token),
                    )
                    conn.execute(
                        """
                        UPDATE guest_sessions
                        SET last_seen_at = ?
                        WHERE guest_id = ? AND device_id = ?
                        """,
                        (timestamp, guest_id, device_id),
                    )
                    conn.execute(
                        """
                        UPDATE profiles
                        SET last_login_at = ?, device_id = ?
                        WHERE id = ?
                        """,
                        (timestamp, device_id, profile_id),
                    )
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def ensure_guest_defaults_async(
    profile_id: str,
    scope: dict[str, str | None],
    delay_seconds: float = 0.0,
) -> None:
    def worker() -> None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        timestamp = now_iso()
        try:
            with DATA_LOCK:
                with db_connect() as conn:
                    normalized_memory = normalize_memory({})
                    conn.execute(
                        """
                        INSERT INTO memories
                            (profile_id, user_id, guest_id, device_id, name, role, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(profile_id) DO NOTHING
                        """,
                        (
                            profile_id,
                            *owner_values(scope),
                            normalized_memory["name"],
                            normalized_memory["role"],
                            timestamp,
                        ),
                    )
                    default_settings = settings_to_db(DEFAULT_SETTINGS)
                    conn.execute(
                        """
                        INSERT INTO settings
                            (profile_id, user_id, guest_id, device_id, voice_enabled, sentence_voice,
                             search_enabled, rag_enabled, voice_name, voice_speed, last_spoken_response,
                             theme, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(profile_id) DO NOTHING
                        """,
                        (
                            profile_id,
                            *owner_values(scope),
                            int(bool(default_settings["voiceEnabled"])),
                            int(bool(default_settings["sentenceVoice"])),
                            int(bool(default_settings["searchEnabled"])),
                            int(bool(default_settings["ragEnabled"])),
                            str(default_settings["voiceName"] or ""),
                            str(default_settings["voiceSpeed"] or "normal"),
                            str(default_settings["lastSpokenResponse"] or ""),
                            str(default_settings["theme"] or "midnight"),
                            timestamp,
                        ),
                    )
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def cached_guest_usage_status(guest_id: str, device_id: str) -> dict[str, Any] | None:
    key = (guest_id, device_id)
    with GUEST_USAGE_STATUS_LOCK:
        cached = GUEST_USAGE_STATUS_CACHE.get(key)
        if not cached:
            return None
        if time.monotonic() - float(cached.get("checked_at") or 0.0) > GUEST_USAGE_STATUS_CACHE_SECONDS:
            GUEST_USAGE_STATUS_CACHE.pop(key, None)
            return None
        return json.loads(json.dumps(cached["status"]))


def cache_guest_usage_status(guest_id: str, device_id: str, status: dict[str, Any]) -> None:
    key = (guest_id, device_id)
    with GUEST_USAGE_STATUS_LOCK:
        GUEST_USAGE_STATUS_CACHE[key] = {
            "checked_at": time.monotonic(),
            "status": json.loads(json.dumps(status)),
        }


def clear_guest_usage_status_cache(guest_id: str | None, device_id: str | None) -> None:
    if not guest_id or not device_id:
        return
    with GUEST_USAGE_STATUS_LOCK:
        GUEST_USAGE_STATUS_CACHE.pop((guest_id, device_id), None)


def enforce_device_bound_session_access(
    authorization: str | None,
    device_id: str | None,
) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return

    cached = cached_session_access(token)
    if cached:
        enforce_cached_device_access(cached, device_id)
        return

    ensure_files()
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT sessions.mode, profiles.profile_kind, profiles.device_id
            FROM sessions
            JOIN profiles ON profiles.id = sessions.profile_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()

    if row:
        cache_session_access(
            token,
            mode=row["mode"],
            profile_kind=row["profile_kind"],
            device_id=row["device_id"],
        )
        enforce_cached_device_access(cached_session_access(token) or {}, device_id)


def get_session_context(authorization: str | None) -> dict[str, Any]:
    token = parse_bearer_token(authorization)
    cached = cached_session_context(token)
    if cached:
        return cached

    ensure_files()
    with DATA_LOCK:
        with db_connect() as conn:
            session = conn.execute(
                """
                SELECT
                    sessions.token AS token,
                    sessions.profile_id AS profile_id,
                    sessions.mode AS session_mode,
                    sessions.guest_id AS session_guest_id,
                    sessions.device_id AS session_device_id,
                    profiles.id AS id,
                    profiles.name AS name,
                    profiles.pin_salt AS pin_salt,
                    profiles.pin_hash AS pin_hash,
                    profiles.profile_kind AS profile_kind,
                    profiles.user_id AS user_id,
                    profiles.device_id AS device_id,
                    profiles.created_at AS created_at,
                    profiles.last_login_at AS last_login_at,
                    guest_sessions.guest_id AS guest_id
                FROM sessions
                JOIN profiles ON profiles.id = sessions.profile_id
                LEFT JOIN guest_sessions ON guest_sessions.profile_id = profiles.id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

            if session is not None:
                profile = row_to_profile(session)
                expected_mode = "guest" if profile.get("is_guest") else "profile"
                if session["session_mode"] != expected_mode:
                    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    raise HTTPException(
                        status_code=401,
                        detail="Session mode is invalid. Please sign in again.",
                    )

                cache_session_access(
                    token,
                    mode=expected_mode,
                    profile_kind=profile.get("profile_kind"),
                    device_id=session["session_device_id"],
                    profile=profile,
                    guest_id=session["session_guest_id"] if expected_mode == "guest" else None,
                    user_id=profile.get("user_id"),
                )
                touch_session_last_seen_async(token)
                return {
                    "token": token,
                    "mode": expected_mode,
                    "profile": profile,
                    "user_id": profile.get("user_id"),
                    "guest_id": session["session_guest_id"] if expected_mode == "guest" else None,
                    "device_id": session["session_device_id"],
                }

    if session is None:
        user = find_account_session_user(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired session.")

        profile = account_workspace_profile(user)
        if not profile:
            delete_session(token)
            raise HTTPException(status_code=401, detail="Account workspace no longer exists.")

        cache_session_access(
            token,
            mode="account",
            profile_kind=profile.get("profile_kind"),
            device_id=profile.get("device_id"),
            profile=profile,
            user_id=user["id"],
        )
        touch_session_last_seen_async(token, "account_sessions")
        return {
            "token": token,
            "mode": "account",
            "profile": profile,
            "user_id": user["id"],
            "guest_id": None,
            "device_id": None,
        }


def require_session_mode(
    authorization: str | None,
    allowed_modes: set[str],
) -> dict[str, Any]:
    if not allowed_modes or not allowed_modes.issubset(SESSION_MODES):
        raise ValueError("Unsupported session mode guard.")
    context = get_session_context(authorization)
    if context["mode"] not in allowed_modes:
        if context["mode"] == "guest":
            raise HTTPException(status_code=403, detail="Sign in to access private profiles.")
        if context["mode"] == "account":
            raise HTTPException(status_code=403, detail="Unlock a profile to continue.")
        raise HTTPException(status_code=403, detail="This session cannot access that feature.")
    return context


def get_profile_from_token(authorization: str | None) -> dict[str, Any]:
    return get_session_context(authorization)["profile"]


def require_guest_session(authorization: str | None) -> dict[str, Any]:
    return require_session_mode(authorization, {"guest"})["profile"]


def require_account_or_profile_session(authorization: str | None) -> dict[str, Any]:
    return require_session_mode(authorization, {"account", "profile"})["profile"]


def require_account_session(authorization: str | None) -> dict[str, Any]:
    return require_session_mode(authorization, {"account"})["profile"]


def require_workspace_session(authorization: str | None) -> dict[str, Any]:
    return require_session_mode(authorization, {"guest", "profile"})["profile"]


def require_profile(authorization: str | None = Header(None)) -> dict[str, Any]:
    return require_session_mode(authorization, {"profile"})["profile"]


def normalize_memory(memory: dict[str, Any]) -> dict[str, Any]:
    facts = memory.get("facts", [])
    normalized_facts = []

    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, dict) and fact.get("text"):
                normalized_facts.append(
                    {
                        "id": fact.get("id") or str(uuid.uuid4()),
                        "text": str(fact.get("text", "")).strip(),
                        "created_at": fact.get("created_at") or now_iso(),
                    }
                )
            elif isinstance(fact, str) and fact.strip():
                normalized_facts.append(
                    {
                        "id": str(uuid.uuid4()),
                        "text": fact.strip(),
                        "created_at": now_iso(),
                    }
                )

    return {
        "name": str(memory.get("name", "")).strip(),
        "role": str(memory.get("role", "")).strip(),
        "facts": normalized_facts,
    }


def load_memory(
    profile_id: str,
    scope: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    cached = cache_get(MEMORY_CACHE, profile_id)
    if cached is not None:
        return cached

    ensure_files()
    with db_connect() as conn:
        scope = scope or ownership_scope_for_profile(profile_id, conn)
        memory = row_to_memory(conn, profile_id, scope)
    cache_set(MEMORY_CACHE, profile_id, memory)
    return memory


def save_memory(profile_id: str, memory: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_memory(memory)
    with DATA_LOCK:
        with db_connect() as conn:
            upsert_memory_rows(conn, profile_id, normalized)
    cache_set(MEMORY_CACHE, profile_id, normalized)
    return normalized


def load_settings(
    profile_id: str,
    scope: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    cached = cache_get(SETTINGS_CACHE, profile_id)
    if cached is not None:
        return cached

    ensure_files()
    with db_connect() as conn:
        scope = scope or ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        row = conn.execute(
            f"SELECT * FROM settings WHERE {owner_clause}",
            owner_params,
        ).fetchone()
    settings = row_to_settings(row)
    cache_set(SETTINGS_CACHE, profile_id, settings)
    return settings


def save_settings(profile_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    current = load_settings(profile_id)
    current.update({key: value for key, value in settings.items() if key in DEFAULT_SETTINGS})
    with DATA_LOCK:
        with db_connect() as conn:
            upsert_settings_row(conn, profile_id, current)
    cache_set(SETTINGS_CACHE, profile_id, current)
    return current


def account_voice_settings_profile_id(profile: dict[str, Any]) -> str | None:
    if profile.get("profile_kind") != "account" or not profile.get("user_id"):
        return None

    with db_connect() as conn:
        row = conn.execute(
            "SELECT workspace_profile_id FROM users WHERE id = ?",
            (profile["user_id"],),
        ).fetchone()
    return row["workspace_profile_id"] if row else None


def load_effective_settings(profile: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings(profile["id"], ownership_scope_from_profile(profile))
    account_settings_id = account_voice_settings_profile_id(profile)
    if not account_settings_id or account_settings_id == profile["id"]:
        return settings

    account_settings = load_settings(account_settings_id)
    for key in ACCOUNT_SHARED_VOICE_SETTINGS:
        settings[key] = account_settings[key]
    return settings


def save_effective_settings(profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    saved = save_settings(profile["id"], updates)
    account_settings_id = account_voice_settings_profile_id(profile)
    shared_updates = {
        key: updates[key]
        for key in ACCOUNT_SHARED_VOICE_SETTINGS
        if key in updates
    }
    if account_settings_id and account_settings_id != profile["id"] and shared_updates:
        save_settings(account_settings_id, shared_updates)
        for key, value in shared_updates.items():
            saved[key] = value
    return saved


def normalize_chat(chat_item: dict[str, Any]) -> dict[str, Any]:
    created_at = normalize_timestamp_value(chat_item.get("created_at"))
    updated_at = normalize_timestamp_value(chat_item.get("updated_at"), created_at)
    messages = [
        message_to_payload(item) if isinstance(item, dict) else message_to_payload({"text": str(item)})
        for item in (chat_item.get("messages") or [])
    ]
    return {
        "id": chat_item.get("id") or str(uuid.uuid4()),
        "title": chat_item.get("title") or "New Chat",
        "summary": chat_item.get("summary") or "",
        "messages": [message for message in messages if not is_saved_backend_failure_message(message)],
        "last_uploaded_file": chat_item.get("last_uploaded_file"),
        "pinned": bool(chat_item.get("pinned", False)),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def ensure_current_chat_shape(
    chat_id: str,
    chat_item: dict[str, Any] | None,
    *,
    code: bool = False,
) -> dict[str, Any]:
    source = chat_item if isinstance(chat_item, dict) else {}
    title = source.get("title") or ("New Code Chat" if code else "New Chat")
    messages = source.get("messages") if isinstance(source.get("messages"), list) else []
    normalized = normalize_chat({**source, "id": source.get("id") or chat_id, "title": title, "messages": messages})

    for key in ("_recent_messages_only", "_loaded_message_ids", "_next_sort_order"):
        if key in source:
            normalized[key] = source[key]

    if code:
        project_files = source.get("projectFiles")
        normalized["projectFiles"] = project_files if isinstance(project_files, list) else []

    return normalized


def sort_chats(chats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    newest_first = sorted(
        chats,
        key=lambda item: normalize_timestamp_value(
            item.get("updated_at") or item.get("created_at"),
            "",
        ),
        reverse=True,
    )
    pinned = [item for item in newest_first if item.get("pinned")]
    unpinned = [item for item in newest_first if not item.get("pinned")]
    return pinned + unpinned


def public_chat_payload(chat_item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in chat_item.items() if not str(key).startswith("_")}


def load_chats(profile_id: str) -> list[dict[str, Any]]:
    ensure_files()
    with db_connect() as conn:
        scope = ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        rows = conn.execute(
            f"""
            SELECT *
            FROM chats
            WHERE {owner_clause}
            ORDER BY pinned DESC, updated_at DESC
            """,
            owner_params,
        ).fetchall()
        chats = [row_to_chat(conn, row, scope) for row in rows]
    return sort_chats(chats)


def joined_chat_rows_to_chat(
    chat_id: str,
    rows: list[sqlite3.Row],
    *,
    message_limit: int | None = None,
) -> dict[str, Any]:
    first = rows[0]
    messages: list[dict[str, Any]] = []
    max_sort_order = None
    for row in rows:
        payload = decode_json(row["message_payload"], None)
        if isinstance(payload, dict):
            messages.append(payload)
        try:
            sort_order = row["message_sort_order"]
            if sort_order is not None:
                max_sort_order = max(
                    int(sort_order),
                    int(max_sort_order if max_sort_order is not None else sort_order),
                )
        except Exception:
            pass

    chat_item = normalize_chat(
        {
            "id": first["id"],
            "title": first["title"],
            "summary": first["summary"],
            "messages": messages,
            "last_uploaded_file": decode_json(first["last_uploaded_file"], None),
            "pinned": bool(first["pinned"]),
            "created_at": first["created_at"],
            "updated_at": first["updated_at"],
        }
    )
    if message_limit is not None and message_limit > 0:
        chat_item["_recent_messages_only"] = True
        chat_item["_loaded_message_ids"] = [
            message["id"] for message in chat_item["messages"] if message.get("id")
        ]
        chat_item["_next_sort_order"] = int(max_sort_order) + 1 if max_sort_order is not None else 0
    return ensure_current_chat_shape(chat_id, chat_item)


def load_chat_by_id(
    profile_id: str,
    chat_id: str,
    scope: dict[str, str | None] | None = None,
    message_limit: int | None = None,
) -> dict[str, Any]:
    ensure_files()
    with db_connect() as conn:
        scope = scope or ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        if message_limit is not None:
            rows = conn.execute(
                f"""
                WITH target_chat AS (
                    SELECT *
                    FROM chats
                    WHERE {owner_clause} AND id = ?
                ),
                recent_messages AS (
                    SELECT payload, sort_order
                    FROM (
                        SELECT payload, sort_order
                        FROM messages
                        WHERE {owner_clause} AND chat_id = ?
                        ORDER BY sort_order DESC
                        LIMIT ?
                    ) AS limited_messages
                )
                SELECT target_chat.id, target_chat.title, target_chat.summary,
                    target_chat.last_uploaded_file, target_chat.pinned,
                    target_chat.created_at, target_chat.updated_at,
                    recent_messages.payload AS message_payload,
                    recent_messages.sort_order AS message_sort_order
                FROM target_chat
                LEFT JOIN recent_messages ON 1 = 1
                ORDER BY recent_messages.sort_order ASC
                """,
                (*owner_params, chat_id, *owner_params, chat_id, int(message_limit)),
            ).fetchall()
            if rows:
                return joined_chat_rows_to_chat(chat_id, rows, message_limit=message_limit)
        else:
            row = conn.execute(
                f"""
                SELECT *
                FROM chats
                WHERE {owner_clause} AND id = ?
                """,
                (*owner_params, chat_id),
            ).fetchone()
            if row:
                return ensure_current_chat_shape(
                    chat_id,
                    row_to_chat(conn, row, scope, message_limit=message_limit),
                )
        reject_other_owner_id(conn, "chats", chat_id, scope, "chat")
    return ensure_current_chat_shape(chat_id, None)


def load_chat_metadata(
    profile_id: str,
    scope: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    ensure_files()
    with db_connect() as conn:
        scope = scope or ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        rows = conn.execute(
            f"""
            SELECT id, profile_id, title, summary, last_uploaded_file,
                pinned, created_at, updated_at
            FROM chats
            WHERE {owner_clause}
            ORDER BY pinned DESC, updated_at DESC
            """,
            owner_params,
        ).fetchall()
        chats = [row_to_chat_metadata(row) for row in rows]
    return sort_chats(chats)


def save_chats(profile_id: str, chats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_chat(item) for item in chats]
    saved = sort_chats(normalized)

    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile_id, conn)
            for chat_item in saved:
                upsert_chat_row(conn, profile_id, chat_item, scope)

    return saved


def get_current_chat(chats: list[dict[str, Any]], chat_id: str) -> dict[str, Any]:
    for chat_item in chats:
        if chat_item["id"] == chat_id:
            return chat_item

    new_chat = normalize_chat({"id": chat_id})
    chats.insert(0, new_chat)
    return new_chat


def save_current_chat(
    profile_id: str,
    chats: list[dict[str, Any]],
    current_chat: dict[str, Any],
    *,
    reload_metadata: bool = True,
) -> list[dict[str, Any]]:
    current_chat["updated_at"] = now_iso()
    recent_only = bool(current_chat.get("_recent_messages_only"))
    loaded_message_ids = current_chat.get("_loaded_message_ids") or []
    with data_write_lock():
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile_id, conn)
            if recent_only:
                saved_chat = upsert_chat_header_row(
                    conn,
                    profile_id,
                    current_chat,
                    scope,
                    trusted_owner=True,
                )
                append_new_message_rows(
                    conn,
                    "messages",
                    profile_id,
                    saved_chat["id"],
                    saved_chat["messages"],
                    loaded_message_ids,
                    scope,
                    next_sort_order=current_chat.get("_next_sort_order"),
                    trusted_owner=True,
                )
                current_chat.update(saved_chat)
                current_chat["_recent_messages_only"] = True
                current_chat["_loaded_message_ids"] = [
                    message["id"] for message in saved_chat["messages"] if message.get("id")
                ]
            else:
                upsert_chat_row(conn, profile_id, current_chat, scope)
    return load_chat_metadata(profile_id) if reload_metadata else []


def load_code_chats(profile_id: str) -> list[dict[str, Any]]:
    ensure_files()
    with db_connect() as conn:
        scope = ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        rows = conn.execute(
            f"""
            SELECT *
            FROM code_chats
            WHERE {owner_clause}
            ORDER BY pinned DESC, updated_at DESC
            """,
            owner_params,
        ).fetchall()
        chats = [row_to_code_chat(conn, row, scope) for row in rows]
    return sort_chats(chats)


def joined_code_chat_rows_to_chat(
    chat_id: str,
    rows: list[sqlite3.Row],
    *,
    message_limit: int | None = None,
    project_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    first = rows[0]
    messages: list[dict[str, Any]] = []
    max_sort_order = None
    for row in rows:
        payload = decode_json(row["message_payload"], None)
        if isinstance(payload, dict):
            messages.append(payload)
        try:
            sort_order = row["message_sort_order"]
            if sort_order is not None:
                max_sort_order = max(
                    int(sort_order),
                    int(max_sort_order if max_sort_order is not None else sort_order),
                )
        except Exception:
            pass

    chat_item = normalize_chat(
        {
            "id": first["id"],
            "title": first["title"],
            "summary": first["summary"],
            "messages": messages,
            "pinned": bool(first["pinned"]),
            "created_at": first["created_at"],
            "updated_at": first["updated_at"],
        }
    )
    if message_limit is not None and message_limit > 0:
        chat_item["_recent_messages_only"] = True
        chat_item["_loaded_message_ids"] = [
            message["id"] for message in chat_item["messages"] if message.get("id")
        ]
        chat_item["_next_sort_order"] = int(max_sort_order) + 1 if max_sort_order is not None else 0
    chat_item["projectFiles"] = project_files or []
    return ensure_current_chat_shape(chat_id, chat_item, code=True)


def load_code_chat_by_id(
    profile_id: str,
    chat_id: str,
    scope: dict[str, str | None] | None = None,
    message_limit: int | None = None,
    include_project_files: bool = True,
) -> dict[str, Any]:
    ensure_files()
    with db_connect() as conn:
        scope = scope or ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        if message_limit is not None:
            rows = conn.execute(
                f"""
                WITH target_chat AS (
                    SELECT *
                    FROM code_chats
                    WHERE {owner_clause} AND id = ?
                ),
                recent_messages AS (
                    SELECT payload, sort_order
                    FROM (
                        SELECT payload, sort_order
                        FROM code_messages
                        WHERE {owner_clause} AND chat_id = ?
                        ORDER BY sort_order DESC
                        LIMIT ?
                    ) AS limited_messages
                )
                SELECT target_chat.id, target_chat.title, target_chat.summary,
                    target_chat.pinned, target_chat.created_at, target_chat.updated_at,
                    recent_messages.payload AS message_payload,
                    recent_messages.sort_order AS message_sort_order
                FROM target_chat
                LEFT JOIN recent_messages ON 1 = 1
                ORDER BY recent_messages.sort_order ASC
                """,
                (*owner_params, chat_id, *owner_params, chat_id, int(message_limit)),
            ).fetchall()
            if rows:
                project_files = (
                    load_code_project_files(profile_id, chat_id, conn, scope)
                    if include_project_files
                    else []
                )
                return joined_code_chat_rows_to_chat(
                    chat_id,
                    rows,
                    message_limit=message_limit,
                    project_files=project_files,
                )
        else:
            row = conn.execute(
                f"""
                SELECT *
                FROM code_chats
                WHERE {owner_clause} AND id = ?
                """,
                (*owner_params, chat_id),
            ).fetchone()
            if row:
                return ensure_current_chat_shape(
                    chat_id,
                    row_to_code_chat(
                        conn,
                        row,
                        scope,
                        message_limit=message_limit,
                        include_project_files=include_project_files,
                    ),
                    code=True,
                )
        reject_other_owner_id(conn, "code_chats", chat_id, scope, "code chat")
    return ensure_current_chat_shape(chat_id, {"title": "New Code Chat"}, code=True)


def load_code_chat_metadata(
    profile_id: str,
    scope: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    ensure_files()
    with db_connect() as conn:
        scope = scope or ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        rows = conn.execute(
            f"""
            SELECT id, profile_id, title, summary, pinned, created_at, updated_at
            FROM code_chats
            WHERE {owner_clause}
            ORDER BY pinned DESC, updated_at DESC
            """,
            owner_params,
        ).fetchall()
        chats = [row_to_code_chat_metadata(row) for row in rows]
    return sort_chats(chats)


def save_code_chats(profile_id: str, chats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_chat(item) for item in chats]
    saved = sort_chats(normalized)

    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile_id, conn)
            for chat_item in saved:
                upsert_code_chat_row(conn, profile_id, chat_item, scope)

    return saved


def assert_chat_owner_or_new(profile_id: str, chat_id: str, *, code: bool = False) -> None:
    with db_connect() as conn:
        scope = ownership_scope_for_profile(profile_id, conn)
        reject_other_owner_id(
            conn,
            "code_chats" if code else "chats",
            chat_id,
            scope,
            "code chat" if code else "chat",
        )


def get_current_code_chat(chats: list[dict[str, Any]], chat_id: str) -> dict[str, Any]:
    for chat_item in chats:
        if chat_item["id"] == chat_id:
            return chat_item

    new_chat = normalize_chat({"id": chat_id, "title": "New Code Chat"})
    chats.insert(0, new_chat)
    return new_chat


def save_current_code_chat(
    profile_id: str,
    chats: list[dict[str, Any]],
    current_chat: dict[str, Any],
    *,
    reload_metadata: bool = True,
) -> list[dict[str, Any]]:
    current_chat["updated_at"] = now_iso()
    recent_only = bool(current_chat.get("_recent_messages_only"))
    loaded_message_ids = current_chat.get("_loaded_message_ids") or []
    with data_write_lock():
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile_id, conn)
            if recent_only:
                saved_chat = upsert_code_chat_header_row(
                    conn,
                    profile_id,
                    current_chat,
                    scope,
                    trusted_owner=True,
                )
                append_new_message_rows(
                    conn,
                    "code_messages",
                    profile_id,
                    saved_chat["id"],
                    saved_chat["messages"],
                    loaded_message_ids,
                    scope,
                    next_sort_order=current_chat.get("_next_sort_order"),
                    trusted_owner=True,
                )
                current_chat.update(saved_chat)
                current_chat["_recent_messages_only"] = True
                current_chat["_loaded_message_ids"] = [
                    message["id"] for message in saved_chat["messages"] if message.get("id")
                ]
                current_chat["projectFiles"] = current_chat.get("projectFiles", [])
            else:
                upsert_code_chat_row(conn, profile_id, current_chat, scope)
    return load_code_chat_metadata(profile_id) if reload_metadata else []


def safe_code_file_name(raw_name: str | None, fallback: str = "code.txt") -> str:
    name = str(raw_name or "").strip() or fallback
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00\r\n]+", "", name).strip()
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._-")
    if not name:
        name = fallback
    if len(name) > 120:
        stem = Path(name).stem[:80].strip("._-") or "code"
        suffix = Path(name).suffix.lower()[:16]
        name = f"{stem}{suffix}"
    suffix = Path(name).suffix.lower()
    if suffix not in CODE_CONTEXT_EXTENSIONS:
        raise HTTPException(status_code=415, detail="This Code Studio file type is not supported.")
    if name.lower() == ".env" or name.lower().endswith(".env"):
        raise HTTPException(status_code=415, detail="Do not upload real .env files. Use .env.example with placeholders instead.")
    return name


def code_language_from_name(file_name: str, fallback: str = "text") -> str:
    suffix = Path(file_name).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".java": "java",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".md": "markdown",
        ".sql": "sql",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".txt": "text",
    }.get(suffix, fallback)


def code_project_file_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "fileName": row["file_name"],
        "fileType": row["file_type"] or "",
        "language": row["language"] or code_language_from_name(row["file_name"]),
        "sizeBytes": int(row["size_bytes"] or 0),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def load_code_project_files(
    profile_id: str,
    chat_id: str,
    conn: sqlite3.Connection | None = None,
    scope: dict[str, str | None] | None = None,
    include_content: bool = False,
) -> list[dict[str, Any]]:
    close_connection = conn is None
    if conn is None:
        ensure_files()
        conn = db_connect()
    try:
        scope = scope or ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        rows = conn.execute(
            f"""
            SELECT *
            FROM code_project_files
            WHERE {owner_clause} AND chat_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (*owner_params, chat_id, MAX_CODE_CONTEXT_FILES),
        ).fetchall()
    finally:
        if close_connection:
            conn.close()

    files = [code_project_file_payload(row) for row in rows]
    if include_content:
        for file_item, row in zip(files, rows):
            file_item["content"] = row["content"] or ""
    return files


def save_code_project_file(
    profile_id: str,
    chat_id: str,
    file_name: str,
    content: str,
    file_type: str = "",
    language: str | None = None,
) -> dict[str, Any]:
    clean_name = safe_code_file_name(file_name)
    clean_content = content.replace("\x00", "")
    encoded_size = len(clean_content.encode("utf-8"))
    if encoded_size <= 0:
        raise HTTPException(status_code=400, detail="The code file is empty.")
    if encoded_size > MAX_CODE_CONTEXT_FILE_BYTES:
        raise HTTPException(status_code=413, detail="This code file is too large. Upload a smaller file or paste only the relevant part.")
    detected_language = language or code_language_from_name(clean_name)
    timestamp = now_iso()

    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile_id, conn)
            ensure_scope_device_row(conn, scope)
            reject_other_owner_id(conn, "code_chats", chat_id, scope, "code chat")
            owner_clause, owner_params = owner_where(scope)
            existing = conn.execute(
                f"""
                SELECT id, created_at
                FROM code_project_files
                WHERE {owner_clause} AND chat_id = ? AND lower(file_name) = lower(?)
                """,
                (*owner_params, chat_id, clean_name),
            ).fetchone()
            file_id = existing["id"] if existing else str(uuid.uuid4())
            created_at = existing["created_at"] if existing else timestamp
            conn.execute(
                """
                INSERT INTO code_project_files
                    (id, profile_id, user_id, guest_id, device_id, chat_id,
                     file_name, file_type, language, content, size_bytes,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    user_id = excluded.user_id,
                    guest_id = excluded.guest_id,
                    device_id = excluded.device_id,
                    chat_id = excluded.chat_id,
                    file_name = excluded.file_name,
                    file_type = excluded.file_type,
                    language = excluded.language,
                    content = excluded.content,
                    size_bytes = excluded.size_bytes,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    file_id,
                    profile_id,
                    *owner_values(scope),
                    chat_id,
                    clean_name,
                    file_type or "text/plain",
                    detected_language,
                    clean_content,
                    encoded_size,
                    created_at,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM code_project_files WHERE id = ?",
                (file_id,),
            ).fetchone()

    return code_project_file_payload(row)


async def validate_code_context_upload(file: UploadFile) -> tuple[str, str, str]:
    raw_name = file.filename or "code.txt"
    file_name = safe_code_file_name(raw_name)
    file_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if file_type not in CODE_CONTEXT_MIME_TYPES and not file_type.startswith("text/"):
        raise HTTPException(status_code=415, detail=f"{file_name} is not a supported text/code file.")

    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail=f"{file_name} is empty.")
    if len(content_bytes) > MAX_CODE_CONTEXT_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"{file_name} is too large for Code Studio context.")
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail=f"{file_name} must be a readable UTF-8 text/code file.")

    return file_name, file_type or "text/plain", content


def extract_pasted_code_files(message: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    pattern = re.compile(
        r"(?P<label>(?:file(?:name)?|path)\s*[:=-]\s*)?(?P<name>[A-Za-z0-9_.-]+\.(?:py|js|jsx|ts|tsx|c|cpp|h|hpp|java|html|css|json|md|txt|sql|ya?ml|toml))\s*:?\s*\n```(?P<language>[A-Za-z0-9+#._-]*)\n(?P<content>[\s\S]*?)```",
        re.IGNORECASE,
    )
    for match in pattern.finditer(message):
        try:
            name = safe_code_file_name(match.group("name"))
        except HTTPException:
            continue
        content = match.group("content").rstrip()
        if content:
            files.append(
                {
                    "file_name": name,
                    "language": match.group("language") or code_language_from_name(name),
                    "content": content,
                }
            )
    return files[:MAX_CODE_CONTEXT_FILES]


def extract_referenced_code_file_names(message: str) -> list[str]:
    extensions = "|".join(re.escape(ext.lstrip(".")) for ext in sorted(CODE_CONTEXT_EXTENSIONS, key=len, reverse=True))
    return [
        match.group(0).lower()
        for match in re.finditer(rf"[\w().-]+\.({extensions})", message, flags=re.IGNORECASE)
    ]


def build_code_project_context(profile_id: str, chat_id: str, user_message: str) -> tuple[str, list[dict[str, Any]]]:
    project_files = load_code_project_files(profile_id, chat_id, include_content=True)
    if not project_files:
        return "", []

    remaining = MAX_CODE_CONTEXT_CHARS
    sections = [
        "Code Studio project context for this chat only:",
        "- Use these files together when the user asks about the project, cross-file bugs, tests, conversions, README/setup, or diffs.",
        "- Do not assume these files exist in other chats.",
        "- Do not execute code or claim tests were run.",
    ]
    selected: list[dict[str, Any]] = []
    explicit_names = extract_referenced_code_file_names(user_message)
    normalized_message = normalize_document_name(user_message)

    def score_file(file_item: dict[str, Any]) -> int:
        file_name = str(file_item.get("fileName", ""))
        normalized_name = normalize_document_name(file_name)
        stem = normalize_document_name(Path(file_name).stem)
        score = 0
        if explicit_names and any(normalize_document_name(name) == normalized_name for name in explicit_names):
            score += 10
        if normalized_name and normalized_name in normalized_message:
            score += 8
        if stem and len(stem) >= 3 and stem in normalized_message:
            score += 4
        content = str(file_item.get("content") or "").lower()
        for word in query_terms(user_message)[:12]:
            if len(word) >= 3 and word in content:
                score += 1
        return score

    sorted_files = sorted(project_files, key=lambda item: (score_file(item), item.get("updatedAt", "")), reverse=True)
    for file_item in sorted_files:
        content = str(file_item.get("content") or "")
        if remaining <= 500:
            break
        clipped = clip_text(content, min(remaining, 5000))
        remaining -= len(clipped)
        selected.append({key: value for key, value in file_item.items() if key != "content"})
        sections.append(
            f"\nFile: {file_item.get('fileName')}\n"
            f"Language: {file_item.get('language') or code_language_from_name(file_item.get('fileName', ''))}\n"
            f"```{file_item.get('language') or 'text'}\n{clipped}\n```"
        )

    return "\n".join(sections), selected


def should_load_code_project_context(
    message: str,
    task: str,
    saved_project_files: list[dict[str, Any]],
) -> bool:
    if saved_project_files or extract_referenced_code_file_names(message):
        return True

    text = f" {message.lower()} "
    project_terms = (
        " project ",
        " codebase ",
        " repo ",
        " repository ",
        " files ",
        " file ",
        " component ",
        " app ",
        " current code ",
        " existing code ",
        " my code ",
        " this code ",
    )
    if any(term in text for term in project_terms):
        return True

    return task in {"debug", "diff", "test", "readme", "optimize", "convert"}


def infer_generated_file_name(prefix: str, language: str, index: int, user_message: str = "") -> str:
    explicit = extract_referenced_code_file_names(prefix) or extract_referenced_code_file_names(user_message)
    if explicit:
        return safe_code_file_name(explicit[0])

    normalized_language = (language or "text").strip().lower()
    if "readme" in user_message.lower() or normalized_language in {"markdown", "md"}:
        return "README.md" if "readme" in user_message.lower() else f"generated_{index}.md"

    suffix = CODE_LANGUAGE_EXTENSIONS.get(normalized_language, ".txt")
    return f"generated_{index}{suffix}"


def extract_generated_code_blocks(ai_response: str, user_message: str = "") -> list[dict[str, str]]:
    generated: list[dict[str, str]] = []
    shell_languages = {"sh", "shell", "bash", "powershell", "ps1", "cmd", "bat", "terminal"}
    pattern = re.compile(
        r"(?P<prefix>(?:^|\n)[^\n`]{0,180})?\n?```(?P<language>[A-Za-z0-9+#._-]*)\n(?P<content>[\s\S]*?)```",
        re.IGNORECASE,
    )
    for match in pattern.finditer(ai_response or ""):
        language = (match.group("language") or "text").strip().lower()
        content = match.group("content").strip()
        if not content or language in shell_languages:
            continue
        if len(content.encode("utf-8")) > MAX_CODE_CONTEXT_FILE_BYTES:
            continue
        try:
            file_name = infer_generated_file_name(match.group("prefix") or "", language, len(generated) + 1, user_message)
        except HTTPException:
            file_name = f"generated_{len(generated) + 1}.txt"
        generated.append(
            {
                "fileName": file_name,
                "language": language or code_language_from_name(file_name),
                "content": content,
            }
        )
        if len(generated) >= MAX_GENERATED_CODE_FILES:
            break
    return generated


def should_offer_generated_file_downloads(user_message: str, ai_response: str) -> bool:
    if "```" not in (ai_response or ""):
        return False
    lowered = (user_message or "").lower()
    return any(
        phrase in lowered
        for phrase in [
            "download",
            "full file",
            "complete file",
            "create readme",
            "readme",
            "write",
            "generate",
            "convert",
            "typescript",
            "react",
            "test",
            "unit test",
        ]
    )


def save_generated_code_files(
    profile_id: str,
    chat_id: str,
    user_message: str,
    ai_response: str,
) -> list[dict[str, Any]]:
    if not should_offer_generated_file_downloads(user_message, ai_response):
        return []

    generated_blocks = extract_generated_code_blocks(ai_response, user_message)
    if not generated_blocks:
        return []

    output_id = str(uuid.uuid4())
    output_folder = ensure_controlled_file_path(PROCESSED_DIR / output_id)
    output_folder.mkdir(parents=True, exist_ok=True)
    saved_files: list[dict[str, Any]] = []
    used_names: set[str] = set()

    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile_id, conn)
            reject_other_owner_id(conn, "code_chats", chat_id, scope, "code chat")
            for index, block in enumerate(generated_blocks, start=1):
                try:
                    safe_name = safe_code_file_name(block.get("fileName"), fallback=f"generated_{index}.txt")
                except HTTPException:
                    safe_name = f"generated_{index}.txt"
                suffix = Path(safe_name).suffix.lower()
                if suffix not in GENERATED_CODE_DOWNLOAD_EXTENSIONS:
                    continue
                base_name = safe_name
                duplicate_index = 2
                while safe_name.lower() in used_names:
                    safe_name = f"{Path(base_name).stem}_{duplicate_index}{suffix}"
                    duplicate_index += 1
                used_names.add(safe_name.lower())
                file_path = ensure_controlled_file_path(output_folder / safe_name)
                file_path.write_text(block["content"], encoding="utf-8")
                upsert_file_row(
                    conn,
                    profile_id,
                    str(file_path),
                    safe_name,
                    file_type=CANONICAL_UPLOAD_MIME_TYPES.get(suffix, "text/plain; charset=utf-8"),
                    scope=scope,
                )
                saved_files.append(
                    {
                        "fileName": safe_name,
                        "language": block.get("language") or code_language_from_name(safe_name),
                        "downloadUrl": f"{API_PUBLIC_BASE_URL}/download/{output_id}/{safe_name}",
                        "sizeBytes": file_path.stat().st_size,
                    }
                )

    return saved_files


def is_code_context_only_message(message: str, saved_project_files: list[dict[str, Any]]) -> bool:
    if not saved_project_files:
        return False
    normalized = re.sub(r"[^a-zA-Z0-9\s]+", " ", (message or "").lower()).strip()
    attach_words = {"add", "attach", "upload", "uploaded", "project", "context", "files", "file", "code"}
    words = normalized.split()
    return bool(words) and len(words) <= 12 and all(word in attach_words or word.isdigit() for word in words)


def clip_text(text: str, limit: int = CONTEXT_LIMIT) -> str:
    clean_text = (text or "").strip()
    if len(clean_text) <= limit:
        return clean_text
    return clean_text[:limit].rstrip() + "\n...[trimmed]"


RAG_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "answer",
    "because",
    "before",
    "could",
    "document",
    "file",
    "from",
    "have",
    "into",
    "more",
    "please",
    "show",
    "that",
    "their",
    "there",
    "these",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}


def split_long_text(text: str, limit: int) -> list[str]:
    parts = []
    remaining = text.strip()
    while len(remaining) > limit:
        split_at = max(
            remaining.rfind(". ", 0, limit),
            remaining.rfind("\n", 0, limit),
            remaining.rfind(" ", 0, limit),
        )
        if split_at < limit * 0.45:
            split_at = limit
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def chunk_text(text: str, chunk_size: int = 1400, overlap: int = 220) -> list[dict[str, Any]]:
    clean = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if not clean:
        return []

    paragraphs = [
        part.strip()
        for part in re.split(r"\n\s*\n", clean)
        if part.strip()
    ]
    if not paragraphs:
        paragraphs = [clean]

    chunks: list[dict[str, Any]] = []
    current = ""
    index = 1

    def push_chunk(chunk: str) -> None:
        nonlocal index
        chunk = chunk.strip()
        if not chunk:
            return
        chunks.append(
            {
                "id": f"chunk-{index}",
                "index": index,
                "text": chunk,
                "preview": clip_text(chunk, 180),
                "char_count": len(chunk),
            }
        )
        index += 1

    for paragraph in paragraphs:
        paragraph_parts = split_long_text(paragraph, chunk_size)
        for part in paragraph_parts:
            candidate = f"{current}\n\n{part}".strip() if current else part
            if len(candidate) <= chunk_size:
                current = candidate
                continue

            push_chunk(current)
            current = f"{current[-overlap:]}\n\n{part}".strip() if overlap and current else part

    push_chunk(current)

    return chunks


def query_terms(query: str) -> list[str]:
    terms = []
    for term in re.findall(r"[a-zA-Z0-9]{3,}", query.lower()):
        if term not in RAG_STOPWORDS and term not in terms:
            terms.append(term)
    return terms


def terms_json(text: str) -> str:
    return encode_json(query_terms(text))


def score_chunk(query: str, chunk: str) -> int:
    terms = query_terms(query)
    haystack = chunk.lower()
    score = 0

    for term in terms:
        count = haystack.count(term)
        if count:
            score += 6 + count * 4

    quoted_phrases = re.findall(r'"([^"]{4,80})"', query.lower())
    for phrase in quoted_phrases:
        if phrase in haystack:
            score += 35

    compact_query = re.sub(r"\s+", " ", query.lower()).strip()
    if compact_query and compact_query in haystack:
        score += 20

    return score


def is_summary_question(message: str) -> bool:
    msg_lower = message.lower()
    return any(
        phrase in msg_lower
        for phrase in [
            "summarize",
            "summary",
            "overview",
            "main points",
            "key points",
            "explain this file",
            "analyze this file",
            "read this file",
        ]
    )


def representative_chunks(
    chunks: list[dict[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    if len(chunks) <= limit:
        return [{**chunk, "score": 1} for chunk in chunks]

    positions = [0, len(chunks) // 4, len(chunks) // 2, (len(chunks) * 3) // 4, len(chunks) - 1]
    selected: list[dict[str, Any]] = []
    seen: set[int] = set()

    for position in positions:
        if position not in seen and 0 <= position < len(chunks):
            seen.add(position)
            selected.append({**chunks[position], "score": 1})

    for chunk in chunks:
        if len(selected) >= limit:
            break
        position = int(chunk.get("index", 0)) - 1
        if position not in seen:
            seen.add(position)
            selected.append({**chunk, "score": 1})

    return selected[:limit]


def search_document_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    if not chunks:
        return []

    if is_summary_question(query) or not query_terms(query):
        return representative_chunks(chunks, limit=limit)

    scored = []
    for chunk in chunks:
        score = score_chunk(query, str(chunk.get("text", "")))
        if score > 0:
            scored.append({**chunk, "score": score})

    if not scored:
        return representative_chunks(chunks, limit=min(limit, len(chunks)))

    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def search_document_chunks_db(
    profile_id: str,
    document_id: str | None,
    query: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    if not document_id:
        return []

    ensure_files()
    with db_connect() as conn:
        scope = ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        rows = conn.execute(
            f"""
            SELECT chunk_index, page_number, text, preview
            FROM document_chunks
            WHERE {owner_clause} AND document_id = ?
            ORDER BY chunk_index ASC
            """,
            (*owner_params, document_id),
        ).fetchall()

    chunks = [
        {
            "id": f"{document_id}:{row['chunk_index']}",
            "index": row["chunk_index"],
            "page_number": row["page_number"],
            "text": row["text"],
            "preview": row["preview"],
        }
        for row in rows
    ]
    return search_document_chunks(query, chunks, limit=limit)


def update_memory_from_message(
    profile_id: str,
    message: str,
    scope: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    memory = load_memory(profile_id, scope)
    message_clean = re.sub(r"\s+", " ", message).strip()
    message_lower = message_clean.lower()
    changed = False

    name_match = re.search(
        r"\bmy name is\s+([a-zA-Z][a-zA-Z ]{1,50})",
        message,
        re.IGNORECASE,
    )
    if name_match:
        memory["name"] = name_match.group(1).strip().title()
        changed = True

    role_match = re.search(
        r"\b(?:my role is|i work as|i am a|i'm a)\s+([a-zA-Z][a-zA-Z \-]{1,70})",
        message,
        re.IGNORECASE,
    )
    if role_match:
        memory["role"] = role_match.group(1).strip()
        changed = True

    remember_match = re.search(
        r"\b(?:remember that|remember this|please remember|remember)\s*:?\s+(.{6,220})",
        message_clean,
        re.IGNORECASE,
    )
    if remember_match:
        add_memory_fact(memory, remember_match.group(1).strip(" ."))
        changed = True

    forget_match = re.search(
        r"\b(?:forget that|forget this|forget|don't remember|do not remember)\s*:?\s+(.{3,160})",
        message_clean,
        re.IGNORECASE,
    )
    if forget_match:
        forget_memory_fact(memory, forget_match.group(1).strip(" ."))
        changed = True

    auto_patterns = [
        r"\bmy goal is\s+(.{6,160})",
        r"\bi am learning\s+(.{4,120})",
        r"\bi'm learning\s+(.{4,120})",
        r"\bi study\s+(.{4,120})",
        r"\bi prefer\s+(.{4,120})",
        r"\bi like\s+(.{4,120})",
        r"\bmy exam is\s+(.{4,120})",
    ]
    if "remember" not in message_lower and "forget" not in message_lower:
        for pattern in auto_patterns:
            match = re.search(pattern, message_clean, re.IGNORECASE)
            if match:
                add_memory_fact(memory, match.group(0).strip(" ."))
                changed = True
                break

    return save_memory(profile_id, memory) if changed else memory


def add_memory_fact(memory: dict[str, Any], text: str) -> None:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) < 4:
        return

    facts = memory.setdefault("facts", [])
    if any(fact.get("text", "").lower() == clean.lower() for fact in facts):
        return

    facts.append({"id": str(uuid.uuid4()), "text": clean, "created_at": now_iso()})
    if len(facts) > 40:
        del facts[:-40]


def forget_memory_fact(memory: dict[str, Any], query: str) -> None:
    clean_query = re.sub(r"\s+", " ", query).strip().lower()
    if not clean_query:
        return

    if "name" in clean_query:
        memory["name"] = ""
    if "role" in clean_query or "job" in clean_query:
        memory["role"] = ""

    query_set = set(query_terms(clean_query))
    if not query_set:
        return

    kept = []
    for fact in memory.get("facts", []):
        fact_text = fact.get("text", "")
        fact_terms = set(query_terms(fact_text))
        overlap = len(query_set & fact_terms)
        if clean_query in fact_text.lower() or overlap >= max(1, min(3, len(query_set))):
            continue
        kept.append(fact)
    memory["facts"] = kept


def is_memory_control_message(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in [
            "remember that",
            "remember this",
            "please remember",
            "forget that",
            "forget this",
            "don't remember",
            "do not remember",
        ]
    )


def memory_control_response(message: str) -> str | None:
    text = message.lower()
    if any(phrase in text for phrase in ["forget that", "forget this", "don't remember", "do not remember"]):
        return "Done. I updated what I should forget for this profile."
    if any(phrase in text for phrase in ["remember that", "remember this", "please remember"]):
        return "Done. I will remember that for this profile."
    return None


MEMORY_RELEVANCE_TERMS = {
    "remember",
    "memory",
    "forget",
    "prefer",
    "preference",
    "like",
    "project",
    "projects",
    "coding",
    "code",
    "website",
    "websites",
    "app",
    "apps",
    "ai",
    "tool",
    "tools",
    "deploy",
    "deployment",
    "release",
    "production",
    "codex",
    "prompt",
    "profile",
    "account",
    "privacy",
    "name",
    "owner",
    "creator",
    "founder",
}


def should_use_memory_context(
    user_message: str,
    conversation: dict[str, Any] | None = None,
) -> bool:
    text = normalize_search_intent_text(user_message)
    if not text:
        return False
    if is_memory_control_message(user_message):
        return True
    if is_acknowledgement(user_message):
        return False
    if is_casual_chat_message(user_message) and len(text.split()) <= 4:
        return False
    if any(phrase in text for phrase in ["what do you remember", "about me", "my name", "who am i"]):
        return True
    if set(query_terms(text)) & MEMORY_RELEVANCE_TERMS:
        return True
    conversation_type = str((conversation or {}).get("conversationType") or "")
    if conversation_type in {"coding", "document"} and set(query_terms(text)) & {
        "project",
        "code",
        "website",
        "document",
        "file",
        "app",
        "build",
        "debug",
    }:
        return True
    return False


def memory_relevance_boost(user_message: str, fact_text: str) -> int:
    message_terms = set(query_terms(user_message))
    fact_terms = set(query_terms(fact_text))
    boost = 0
    domains = [
        ({"code", "coding", "program", "python", "react", "website", "websites", "app", "frontend", "backend"}, 18),
        ({"deploy", "deployment", "release", "production", "hosting", "security"}, 16),
        ({"codex", "prompt", "direct", "instruction"}, 14),
        ({"profile", "privacy", "pin", "account", "login"}, 12),
        ({"project", "projects", "build", "tool", "tools", "ai"}, 10),
    ]
    for domain_terms, points in domains:
        if message_terms & domain_terms and fact_terms & domain_terms:
            boost += points
    return boost


def relevant_memory_facts(
    memory: dict[str, Any],
    user_message: str,
    limit: int = 5,
    conversation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    facts = memory.get("facts", [])
    if not facts:
        return []

    if not should_use_memory_context(user_message, conversation):
        return []

    scored = []
    for fact in facts:
        fact_text = str(fact.get("text", ""))
        score = score_chunk(user_message, fact_text) + memory_relevance_boost(user_message, fact_text)
        if score >= 10:
            scored.append((score, fact))

    if not scored:
        return []

    return [fact for _score, fact in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


def format_memory(
    memory: dict[str, Any],
    user_message: str = "",
    conversation: dict[str, Any] | None = None,
) -> str:
    lines = []
    should_use = should_use_memory_context(user_message, conversation)

    if should_use and memory.get("name"):
        lines.append(f"Name: {memory['name']}")

    if should_use and memory.get("role"):
        lines.append(f"Role: {memory['role']}")

    facts = relevant_memory_facts(memory, user_message, conversation=conversation)
    if facts:
        lines.append("Relevant remembered facts:")
        lines.extend(f"- {fact.get('text')}" for fact in facts if fact.get("text"))

    return "\n".join(lines)


def safe_calculate(expression: str) -> float | int:
    allowed_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
    }

    def eval_node(node: ast.AST) -> float | int:
        legacy_num_type = getattr(ast, "Num", ())
        if legacy_num_type and isinstance(node, legacy_num_type):
            return node.n

        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in allowed_ops:
                raise ValueError("Operator is not allowed")
            return allowed_ops[op_type](eval_node(node.left), eval_node(node.right))

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in allowed_ops:
                raise ValueError("Operator is not allowed")
            return allowed_ops[op_type](eval_node(node.operand))

        raise ValueError("Invalid calculation")

    tree = ast.parse(expression, mode="eval")
    return eval_node(tree.body)


def normalize_calculation_expression(expression: str) -> str:
    clean = str(expression or "").lower()
    replacements = {
        "multiplied by": "*",
        "multiply by": "*",
        "times": "*",
        "into": "*",
        "divided by": "/",
        "divide by": "/",
        "plus": "+",
        "minus": "-",
        "modulus": "%",
        "modulo": "%",
    }
    for phrase, symbol in replacements.items():
        clean = re.sub(rf"\b{re.escape(phrase)}\b", symbol, clean)

    clean = clean.replace("×", "*").replace("÷", "/").replace("−", "-")
    clean = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", "*", clean)
    clean = clean.replace("^", "**")
    clean = re.sub(r"[^0-9+\-*/%.() ]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def extract_calculation_expression(message: str) -> str:
    text = str(message or "").strip()
    text = re.sub(
        r"^\s*(?:please\s+)?(?:calculate|calculator|calc|evaluate|solve|find|what\s+is|what's|tell\s+me)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    normalized = normalize_calculation_expression(text)
    expression_pattern = re.compile(
        r"(?<!\w)(?:\d+(?:\.\d+)?|\([^()]+\))"
        r"(?:\s*(?:\*\*|[+\-*/%])\s*(?:\d+(?:\.\d+)?|\([^()]+\)))+"
    )
    matches = expression_pattern.findall(normalized)
    if not matches:
        return ""
    return max((match.strip() for match in matches), key=len)


def is_calculator_question(message: str) -> bool:
    msg_lower = str(message or "").lower()
    trigger = any(
        phrase in msg_lower
        for phrase in ["calculate", "calculator", "calc", "evaluate", "solve", "what is", "what's"]
    )
    return trigger and bool(extract_calculation_expression(message))


def extract_pdf_content(file_bytes: bytes) -> tuple[str, int, bool, list[str], str | None]:
    page_texts: list[str] = []
    page_count = 0
    used_ocr = False

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)

        for page in reader.pages:
            page_texts.append((page.extract_text() or "").strip())
    except Exception:
        page_texts = []

    pdf_text = "\n\n".join(text for text in page_texts if text).strip()
    if pdf_text:
        return pdf_text, page_count, used_ocr, page_texts, None

    if fitz is not None:
        pdf_document = None
        try:
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = max(page_count, len(pdf_document))
            fitz_page_texts = [
                (pdf_document[page_number].get_text("text") or "").strip()
                for page_number in range(len(pdf_document))
            ]
            fitz_text = "\n\n".join(text for text in fitz_page_texts if text).strip()
            if fitz_text:
                return fitz_text, page_count, used_ocr, fitz_page_texts, None
        except Exception:
            pass
        finally:
            if pdf_document is not None:
                pdf_document.close()

    if page_count == 0:
        return "", page_count, used_ocr, page_texts, "This PDF could not be opened for text extraction."

    if fitz is None:
        return (
            "",
            page_count,
            used_ocr,
            page_texts,
            f"{PDF_TEXT_UNAVAILABLE_MESSAGE} PDF page rendering is unavailable on this server.",
        )

    if not ocr_available():
        return "", page_count, used_ocr, page_texts, SCANNED_PDF_OCR_UNAVAILABLE_MESSAGE

    used_ocr = True
    pdf_document = None
    try:
        pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = len(pdf_document)
        page_texts = []

        for page_number in range(page_count):
            page = pdf_document[page_number]
            pix = page.get_pixmap(dpi=200)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            page_texts.append(pytesseract.image_to_string(image).strip())
    except Exception as exc:
        return (
            "",
            page_count,
            False,
            [],
            f"{SCANNED_PDF_OCR_UNAVAILABLE_MESSAGE} OCR failed with: {exc}",
        )
    finally:
        if pdf_document is not None:
            pdf_document.close()

    pdf_text = "\n\n".join(text for text in page_texts if text).strip()
    if not pdf_text:
        return (
            "",
            page_count,
            used_ocr,
            page_texts,
            "OCR ran, but no readable text was found in this scanned PDF.",
        )
    return pdf_text, page_count, used_ocr, page_texts, None


def extract_pdf_text(file_bytes: bytes) -> tuple[str, int, bool, str | None]:
    text, page_count, used_ocr, _page_texts, notice = extract_pdf_content(file_bytes)
    return text, page_count, used_ocr, notice


def chunk_pdf_pages(page_texts: list[str]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    chunk_index = 1
    for page_number, page_text in enumerate(page_texts, start=1):
        for chunk in chunk_text(page_text):
            chunks.append(
                {
                    **chunk,
                    "id": f"chunk-{chunk_index}",
                    "index": chunk_index,
                    "page_number": page_number,
                }
            )
            chunk_index += 1
    return chunks


def extract_docx_text(file_path: Path) -> str:
    try:
        with zipfile.ZipFile(file_path) as docx:
            xml_content = docx.read("word/document.xml")

        root = ET.fromstring(xml_content)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []

        for paragraph in root.findall(".//w:p", namespace):
            text_parts = [
                node.text or ""
                for node in paragraph.findall(".//w:t", namespace)
                if node.text
            ]
            if text_parts:
                paragraphs.append("".join(text_parts))

        return "\n".join(paragraphs).strip()
    except Exception as exc:
        return f"DOCX text extraction failed: {exc}"


def create_simple_docx_from_text(text: str, output_path: Path, title: str) -> None:
    clean_lines = [
        line.strip()
        for line in re.split(r"\n+", text or "")
        if line.strip()
    ]
    if not clean_lines:
        clean_lines = ["No extractable text was found in this PDF."]

    paragraphs = []
    for line in clean_lines:
        paragraphs.append(
            "<w:p><w:r><w:t xml:space=\"preserve\">"
            f"{html.escape(line, quote=False)}"
            "</w:t></w:r></w:p>"
        )

    created_at = now_iso()
    safe_title = html.escape(title or "Converted PDF", quote=False)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>{safe_title}</w:t></w:r>
    </w:p>
    {''.join(paragraphs)}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        docx.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        docx.writestr("word/document.xml", document_xml)
        docx.writestr(
            "docProps/core.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{safe_title}</dc:title>
  <dc:creator>FebGuy AI</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created_at}</dcterms:created>
</cp:coreProperties>""",
        )
        docx.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>FebGuy AI</Application>
</Properties>""",
        )


def extract_image_text(file_path: Path) -> tuple[str, bool, str | None]:
    if not ocr_available():
        return "", False, IMAGE_OCR_UNAVAILABLE_MESSAGE

    try:
        image = Image.open(file_path)
        return pytesseract.image_to_string(image).strip(), True, None
    except Exception as exc:
        return "", True, f"Image OCR failed: {exc}"


def encode_image_base64(file_path: Path) -> str | None:
    try:
        return base64.b64encode(file_path.read_bytes()).decode("utf-8")
    except Exception:
        return None


def ensure_controlled_file_path(file_path: Path) -> Path:
    resolved_root = PROCESSED_DIR.resolve()
    resolved_path = file_path.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise HTTPException(status_code=400, detail="Unsafe file storage path rejected.")
    return resolved_path


def controlled_upload_directory(profile_id: str) -> Path:
    upload_dir = controlled_upload_path_for_profile(profile_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def safe_file_name(raw_name: str | None) -> tuple[str, str]:
    original_name = str(raw_name or "").strip()
    if (
        not original_name
        or len(original_name) > 180
        or "\x00" in original_name
        or "/" in original_name
        or "\\" in original_name
        or original_name in {".", ".."}
        or Path(original_name).name != original_name
    ):
        raise HTTPException(
            status_code=400,
            detail="Unsafe filename detected. Please rename the file and upload it again.",
        )

    extension = Path(original_name).suffix.lower()
    if extension in DISALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="This file type is not allowed for safety. Upload a PDF, DOCX, PNG, JPG/JPEG, or TXT file.",
        )
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PDF, DOCX, PNG, JPG/JPEG, or TXT file.",
        )
    return original_name, extension


def validate_upload_mime(extension: str, content_type: str | None) -> str:
    submitted_type = str(content_type or "").split(";", 1)[0].strip().lower()
    expected_types = UPLOAD_MIME_TYPES[extension]
    if submitted_type not in expected_types and submitted_type not in GENERIC_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail="The file type does not match its filename. Please upload a valid file.",
        )
    return CANONICAL_UPLOAD_MIME_TYPES[extension]


def validate_upload_content(extension: str, file_bytes: bytes) -> None:
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    invalid_message = "The uploaded file content does not match its file type."
    if extension == ".pdf":
        if b"%PDF-" not in file_bytes[:1024]:
            raise HTTPException(status_code=415, detail=invalid_message)
        return

    if extension == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                names = set(archive.namelist())
                required_parts = {"[Content_Types].xml", "word/document.xml"}
                expanded_size = sum(info.file_size for info in archive.infolist())
                if not required_parts.issubset(names):
                    raise HTTPException(status_code=415, detail=invalid_message)
                if expanded_size > MAX_DOCUMENT_EXPANDED_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="This document is too large after extraction. Please upload a smaller DOCX file.",
                    )
        except HTTPException:
            raise
        except (OSError, zipfile.BadZipFile):
            raise HTTPException(status_code=415, detail=invalid_message)
        return

    if extension in {".png", ".jpg", ".jpeg"}:
        expected_format = "PNG" if extension == ".png" else "JPEG"
        try:
            with Image.open(io.BytesIO(file_bytes)) as image:
                if image.format != expected_format:
                    raise HTTPException(status_code=415, detail=invalid_message)
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise HTTPException(
                        status_code=413,
                        detail="This image has dimensions that are too large to process safely.",
                    )
                image.verify()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=415, detail=invalid_message)
        return

    if extension == ".txt":
        if b"\x00" in file_bytes:
            raise HTTPException(status_code=415, detail=invalid_message)
        try:
            file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=415,
                detail="TXT uploads must contain readable UTF-8 text.",
            )


async def validate_uploaded_file(file: UploadFile) -> tuple[str, str, bytes]:
    original_name, extension = safe_file_name(file.filename)
    canonical_type = validate_upload_mime(extension, file.content_type)
    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"This file is too large. Maximum upload size is {MAX_UPLOAD_MB} MB.",
        )
    validate_upload_content(extension, file_bytes)
    return original_name, canonical_type, file_bytes


def extract_file_context(
    file_path: Path,
    file_name: str,
    file_type: str = "",
) -> dict[str, Any]:
    suffix = file_path.suffix.lower()
    file_type_lower = (file_type or "").lower()
    metadata: dict[str, Any] = {
        "path": str(file_path),
        "name": file_name,
        "type": file_type,
        "context": "",
        "raw_text": "",
        "chunks": [],
        "is_image": False,
        "used_ocr": False,
        "page_count": None,
    }

    try:
        if suffix == ".pdf" or "pdf" in file_type_lower:
            text, page_count, used_ocr, page_texts, notice = extract_pdf_content(file_path.read_bytes())
            metadata["page_count"] = page_count
            metadata["used_ocr"] = used_ocr
            metadata["raw_text"] = text
            metadata["chunks"] = chunk_pdf_pages(page_texts) or chunk_text(text)
            notice_block = f"\n\n{notice}" if notice and not text.strip() else ""
            metadata["context"] = (
                f"Uploaded PDF: {file_name}\n"
                f"Pages: {page_count}\n"
                f"OCR used: {'yes' if used_ocr else 'no'}\n\n"
                f"{clip_text(text)}"
                f"{notice_block}"
            )

        elif suffix == ".docx":
            text = extract_docx_text(file_path)
            metadata["raw_text"] = text
            metadata["chunks"] = chunk_text(text)
            metadata["context"] = f"Uploaded DOCX: {file_name}\n\n{clip_text(text)}"

        elif suffix in {".txt", ".md", ".csv"}:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            metadata["raw_text"] = text
            metadata["chunks"] = chunk_text(text)
            metadata["context"] = f"Uploaded text file: {file_name}\n\n{clip_text(text)}"

        elif file_type_lower.startswith("image/") or suffix in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".bmp",
        }:
            text, used_ocr, notice = extract_image_text(file_path)
            metadata["is_image"] = True
            metadata["used_ocr"] = used_ocr
            metadata["raw_text"] = text
            metadata["chunks"] = chunk_text(text)
            notice_block = f"\n\n{notice}" if notice and not text.strip() else ""
            metadata["context"] = (
                f"Uploaded image: {file_name}\n"
                f"OCR text, if any:\n{clip_text(text, 4000)}"
                f"{notice_block}"
            )

        else:
            metadata["context"] = (
                f"Uploaded file: {file_name}\n"
                "No text extractor is available for this file type."
            )

    except Exception as exc:
        metadata["context"] = f"Could not extract file context for {file_name}: {exc}"

    return metadata


async def save_uploaded_file(
    file: UploadFile,
    profile_id: str,
    chat_id: str | None = None,
    validated_upload: tuple[str, str, bytes] | None = None,
) -> dict[str, Any]:
    original_name, canonical_type, file_bytes = (
        validated_upload or await validate_uploaded_file(file)
    )
    profile_upload_dir = controlled_upload_directory(profile_id)
    unique_name = f"{uuid.uuid4().hex}{Path(original_name).suffix.lower()}"
    upload_path = ensure_controlled_file_path(profile_upload_dir / unique_name)
    upload_path.write_bytes(file_bytes)

    metadata = extract_file_context(upload_path, original_name, canonical_type)
    return save_document_record(profile_id, chat_id, metadata)


def is_file_question(message: str) -> bool:
    text = message.lower()
    keywords = [
        "file",
        "document",
        "pdf",
        "docx",
        "image",
        "photo",
        "picture",
        "uploaded",
        "this",
        "summarize",
        "analyze",
        "extract",
        "read",
        "notes",
        "ocr",
        "convert",
        "according",
        "from the document",
    ]
    return any(keyword in text for keyword in keywords)


def has_document_reference(message: str) -> bool:
    text = message.lower()
    document_terms = [
        "file",
        "files",
        "document",
        "documents",
        "pdf",
        "docx",
        "image",
        "photo",
        "picture",
        "my notes",
        "these notes",
        "uploaded notes",
        "from my notes",
        "uploaded",
        "ocr",
        "from the document",
        "from the file",
        "this file",
        "this document",
    ]
    return any(term in text for term in document_terms)


DOCUMENT_NOT_IN_CHAT_PREFIX = "__DOCUMENT_NOT_IN_CHAT__"


def extract_referenced_file_names(message: str) -> list[str]:
    return [
        match.group(0).lower()
        for match in re.finditer(r"[\w().-]+\.(?:pdf|docx|txt|png|jpe?g)", message, flags=re.IGNORECASE)
    ]


def normalize_document_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def filter_documents_by_message_name(
    documents: list[dict[str, Any]],
    message: str,
) -> tuple[list[dict[str, Any]], bool]:
    text = message.lower()
    explicit_names = extract_referenced_file_names(message)
    matched: list[dict[str, Any]] = []

    for document in documents:
        file_name = str(document.get("name") or "")
        if not file_name:
            continue

        file_name_lower = file_name.lower()
        stem_lower = Path(file_name_lower).stem
        normalized_name = normalize_document_name(file_name_lower)
        normalized_stem = normalize_document_name(stem_lower)
        normalized_message = normalize_document_name(text)

        if file_name_lower in text:
            matched.append(document)
            continue
        if explicit_names and any(normalize_document_name(name) == normalized_name for name in explicit_names):
            matched.append(document)
            continue
        if normalized_stem and len(normalized_stem) >= 5 and normalized_stem in normalized_message:
            matched.append(document)

    return matched, bool(explicit_names)


def missing_current_chat_document_message(message: str) -> str:
    if ".pdf" in message.lower() or " pdf" in f" {message.lower()}":
        return "I don't see that PDF attached in this chat. Please attach it here first."
    return "I don't see that file attached in this chat. Please attach it here first."


def is_multi_document_question(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in [
            "compare these",
            "compare the",
            "compare both",
            "both documents",
            "both files",
            "two pdf",
            "two document",
            "difference between",
            "different between",
            "merge key points",
            "all uploaded",
            "uploaded files",
            "uploaded documents",
        ]
    )


def is_document_extraction_question(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in [
            "key point",
            "important date",
            "dates mentioned",
            "definition",
            "names mentioned",
            "table",
            "question",
            "exam",
            "project report",
            "notes",
            "summarize",
            "summary",
            "overview",
        ]
    )


def document_record_from_row(row: sqlite3.Row) -> dict[str, Any]:
    raw_text = row["raw_text"] or ""
    used_ocr = bool(row["used_ocr"])
    return {
        "document_id": row["id"],
        "chat_id": row["chat_id"],
        "path": row["path"],
        "name": row["file_name"],
        "type": row["file_type"],
        "context": row["context"] or "",
        "raw_text": raw_text,
        "chunks": decode_json(row["chunks"], []),
        "is_image": bool(row["is_image"]),
        "used_ocr": used_ocr,
        "ocr_uncertain": used_ocr and len(raw_text.strip()) < 120,
        "text_unavailable": not bool(raw_text.strip()),
        "page_count": row["page_count"],
    }


def load_relevant_documents(
    profile_id: str,
    chat_id: str,
    allow_workspace_fallback: bool,
    max_documents: int = 12,
) -> tuple[list[dict[str, Any]], str]:
    ensure_files()
    with db_connect() as conn:
        scope = ownership_scope_for_profile(profile_id, conn)
        owner_clause, owner_params = owner_where(scope)
        rows = conn.execute(
            f"""
            SELECT *
            FROM documents
            WHERE {owner_clause} AND chat_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*owner_params, chat_id, max_documents),
        ).fetchall()
        if rows or not allow_workspace_fallback:
            return [document_record_from_row(row) for row in rows], "current chat"

        rows = conn.execute(
            f"""
            SELECT *
            FROM documents
            WHERE {owner_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*owner_params, max_documents),
        ).fetchall()
    return [document_record_from_row(row) for row in rows], "your workspace"


def document_hit(
    document: dict[str, Any],
    chunk: dict[str, Any] | None = None,
    *,
    preview: str = "",
) -> dict[str, Any]:
    chunk = chunk or {}
    default_preview = chunk.get("preview") or clip_text(chunk.get("text", ""), 180)
    if not default_preview and document.get("text_unavailable"):
        default_preview = clip_text(document.get("context", ""), 180)
    return {
        **chunk,
        "document_id": document.get("document_id"),
        "file_name": document.get("name", "Uploaded file"),
        "file_type": document.get("type", ""),
        "page_number": chunk.get("page_number"),
        "used_ocr": bool(document.get("used_ocr")),
        "ocr_uncertain": bool(document.get("ocr_uncertain")),
        "text_unavailable": bool(document.get("text_unavailable")),
        "is_image": bool(document.get("is_image")),
        "preview": preview or default_preview,
    }


def select_document_hits(
    documents: list[dict[str, Any]],
    message: str,
    broad_task: bool,
    limit: int = 10,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    per_document_limit = 3 if broad_task else 4

    for document in documents:
        chunks = document.get("chunks") or []
        if broad_task:
            selected = representative_chunks(chunks, limit=per_document_limit)
        else:
            selected = [
                {**chunk, "score": score_chunk(message, str(chunk.get("text", "")))}
                for chunk in chunks
                if score_chunk(message, str(chunk.get("text", ""))) > 0
            ]
            selected = sorted(selected, key=lambda item: item["score"], reverse=True)[:per_document_limit]
        candidates.extend(document_hit(document, chunk) for chunk in selected)

        if document.get("is_image") and not selected:
            candidates.append(
                document_hit(
                    document,
                    preview="Image provided for visual analysis; OCR text may be limited.",
                )
            )

    if not candidates:
        candidates = [
            document_hit(
                document,
                preview="No matching readable text was retrieved for this question.",
            )
            for document in documents
        ]

    if not broad_task:
        candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    return candidates[:limit]


def build_file_context_from_chat(
    profile_id: str,
    current_chat: dict[str, Any],
    message: str,
    settings: dict[str, Any],
    force_include: bool = False,
) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    has_active_upload = isinstance(current_chat.get("last_uploaded_file"), dict)
    should_include = (
        force_include
        or has_document_reference(message)
        or is_multi_document_question(message)
        or (has_active_upload and is_file_question(message))
    )
    if not should_include:
        return "", [], []

    documents, document_scope = load_relevant_documents(
        profile_id,
        str(current_chat.get("id") or ""),
        allow_workspace_fallback=False,
    )
    if not documents:
        return (
            DOCUMENT_NOT_IN_CHAT_PREFIX + missing_current_chat_document_message(message),
            [],
            [],
        )

    named_documents, used_explicit_file_name = filter_documents_by_message_name(documents, message)
    if named_documents:
        documents = named_documents
        document_scope = "named file in current chat"
    elif used_explicit_file_name:
        return (
            DOCUMENT_NOT_IN_CHAT_PREFIX + missing_current_chat_document_message(message),
            [],
            [],
        )
    elif not is_multi_document_question(message):
        active_document_id = (
            current_chat.get("last_uploaded_file", {}).get("document_id")
            if isinstance(current_chat.get("last_uploaded_file"), dict)
            else None
        )
        if active_document_id:
            active_documents = [
                document
                for document in documents
                if document.get("document_id") == active_document_id
            ]
            if active_documents:
                documents = active_documents
                document_scope = "latest uploaded file in current chat"

    if not settings.get("ragEnabled", True) and len(documents) > 1:
        active_document_id = (
            current_chat.get("last_uploaded_file", {}).get("document_id")
            if isinstance(current_chat.get("last_uploaded_file"), dict)
            else None
        )
        documents = [
            document
            for document in documents
            if document.get("document_id") == active_document_id
        ] or documents[:1]
        document_scope = "latest uploaded file (document search is disabled)"

    broad_task = (
        force_include
        or is_multi_document_question(message)
        or is_document_extraction_question(message)
        or is_summary_question(message)
    )
    hits = select_document_hits(documents, message, broad_task=broad_task)
    images: list[dict[str, str]] = []
    selected_document_ids = {hit.get("document_id") for hit in hits}
    for document in documents:
        if not document.get("is_image") or document.get("document_id") not in selected_document_ids:
            continue
        file_path = Path(document.get("path", ""))
        if file_path.exists() and len(images) < 4:
            encoded = encode_image_base64(file_path)
            if not encoded:
                continue
            images.append(
                {
                    "data": encoded,
                    "mime_type": document.get("type") or "image/png",
                }
            )

    context = [
        f"Uploaded document evidence scope: {document_scope}.",
        "Document-grounding rules:",
        "- Begin a supported file-based answer with: Based on your uploaded documents...",
        "- Use only the file evidence below for document claims.",
        "- Name the supporting file and include a page number only when one is supplied below.",
        "- If the evidence does not contain the answer, say exactly: I could not find this in the uploaded documents.",
        "- You may add clearly labelled general knowledge only when it answers the user's broader request.",
        "- For OCR-derived evidence, acknowledge uncertainty when text is sparse or exact values matter.",
        "Selected uploaded files:",
    ]
    for document in documents:
        ocr_note = ""
        if document.get("is_image") and document.get("text_unavailable"):
            ocr_note = " (visual image supplied; OCR text is unavailable or empty)"
        elif document.get("text_unavailable"):
            ocr_note = f" ({SCANNED_PDF_OCR_UNAVAILABLE_MESSAGE})"
        elif document.get("used_ocr"):
            ocr_note = " (OCR-derived text; quality may require verification)"
        context.append(f"- {document.get('name', 'Uploaded file')}{ocr_note}")

    has_readable_evidence = any(str(hit.get("text") or "").strip() for hit in hits)
    if not has_readable_evidence and not images:
        context.append(
            "\nNo matching readable evidence was found in the uploaded files for this question."
        )
        return "\n".join(context), images, hits

    context.append("\nRelevant document evidence:")
    for hit in hits:
        page_label = f", page {hit['page_number']}" if hit.get("page_number") else ""
        evidence = clip_text(hit.get("text", "") or hit.get("preview", ""), 1700)
        context.append(
            f"\nFile: {hit.get('file_name', 'Uploaded file')}{page_label}\n"
            f"{evidence}"
        )
    return "\n".join(context), images, hits


def detect_document_intent(file_name: str, prompt: str) -> str | None:
    prompt_lower = prompt.lower()
    filename_lower = file_name.lower()

    if not any(word in prompt_lower for word in ["convert", "turn", "make", "export", "to"]):
        return None

    if filename_lower.endswith(".docx") and "pdf" in prompt_lower:
        return "docx_to_pdf"

    if filename_lower.endswith(".pdf") and any(
        word in prompt_lower for word in ["docx", "word", "document"]
    ):
        return "pdf_to_docx"

    return None


def pdf_to_docx_text_fallback(
    profile_id: str,
    file_path: Path,
    filename: str,
    output_folder: Path,
    output_id: str,
    output_name: str,
    *,
    cloud_error: Exception | None = None,
) -> dict[str, Any]:
    text, _page_count, used_ocr, notice = extract_pdf_text(file_path.read_bytes())
    if not text.strip():
        prefix = "Cloud PDF to DOCX conversion failed, and " if cloud_error else ""
        return {
            "success": False,
            "message": (
                f"{prefix}{notice or PDF_TEXT_UNAVAILABLE_MESSAGE} "
                "Text-based PDF to DOCX conversion can run without OCR, but scanned PDFs need OCR."
            ),
        }

    output_file_path = output_folder / output_name
    create_simple_docx_from_text(text, output_file_path, Path(filename).stem)
    save_owned_file_record(
        profile_id,
        output_file_path,
        output_name,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    if cloud_error:
        message = (
            "Cloud PDF to DOCX conversion failed, so a text-based DOCX fallback was created. "
            "Complex layouts may not match the original exactly."
        )
    elif used_ocr:
        message = (
            "PDF converted to a DOCX using OCR-derived text. "
            "Please verify unclear details and complex layouts."
        )
    else:
        message = (
            "PDF converted to a text-based DOCX. "
            "Complex layouts may not match the original exactly."
        )
    return {
        "success": True,
        "file_name": output_name,
        "download_url": f"{API_PUBLIC_BASE_URL}/download/{output_id}/{output_name}",
        "message": message,
    }


def docx_to_pdf_local_fallback(
    profile_id: str,
    file_path: Path,
    output_folder: Path,
    output_id: str,
    output_name: str,
    *,
    cloud_error: Exception | None = None,
) -> dict[str, Any] | None:
    if not local_docx_to_pdf_available():
        return None

    output_file_path = output_folder / output_name
    try:
        result = subprocess.run(
            [
                PANDOC_CMD,
                str(file_path),
                f"--pdf-engine={PRINCE_CMD}",
                "-o",
                str(output_file_path),
            ],
            capture_output=True,
            text=True,
            timeout=CONVERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "DOCX to PDF conversion timed out while running the local converter.",
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"DOCX to PDF conversion could not start the local converter: {exc}",
        }

    if result.returncode != 0 or not output_file_path.exists():
        detail = clip_text((result.stderr or result.stdout or "").strip(), 300)
        detail_suffix = f" {detail}" if detail else ""
        return {
            "success": False,
            "message": f"DOCX to PDF conversion failed in the local converter.{detail_suffix}",
        }

    save_owned_file_record(profile_id, output_file_path, output_name, "application/pdf")
    message = "DOCX converted to PDF."
    if cloud_error:
        message = "Cloud DOCX to PDF conversion failed, so the local Render converter created the PDF."
    return {
        "success": True,
        "file_name": output_name,
        "download_url": f"{API_PUBLIC_BASE_URL}/download/{output_id}/{output_name}",
        "message": message,
    }


def process_document_tool(
    profile_id: str,
    file_path: Path,
    filename: str,
    prompt: str,
) -> dict[str, Any] | None:
    intent = detect_document_intent(filename, prompt)

    if intent is None:
        return None

    output_id = str(uuid.uuid4())
    output_folder = ensure_controlled_file_path(PROCESSED_DIR / output_id)
    output_folder.mkdir(parents=True, exist_ok=True)
    output_name = ""

    try:
        if intent == "docx_to_pdf":
            output_name = f"{Path(filename).stem}.pdf"
            if not cloud_docx_to_pdf_available():
                local_result = docx_to_pdf_local_fallback(
                    profile_id,
                    file_path,
                    output_folder,
                    output_id,
                    output_name,
                )
                if local_result is not None:
                    return local_result
                return {
                    "success": False,
                    "message": (
                        "DOCX to PDF conversion needs either ILOVEPDF_PUBLIC_KEY and "
                        "ILOVEPDF_SECRET_KEY, or local pandoc and prince/princexml executables. "
                        "Render native Python deploys include pandoc and princexml; if those are "
                        "not available, configure iLovePDF credentials or deploy the backend with Docker."
                    ),
                }
            task = OfficePdfTask(
                public_key=ILOVEPDF_PUBLIC_KEY,
                secret_key=ILOVEPDF_SECRET_KEY,
            )

        elif intent == "pdf_to_docx":
            output_name = f"{Path(filename).stem}.docx"
            if not cloud_pdf_to_docx_available():
                return pdf_to_docx_text_fallback(
                    profile_id,
                    file_path,
                    filename,
                    output_folder,
                    output_id,
                    output_name,
                )
            task = PdfOfficeTask(
                public_key=ILOVEPDF_PUBLIC_KEY,
                secret_key=ILOVEPDF_SECRET_KEY,
            )

        else:
            return None

        task.add_file(str(file_path))
        task.set_output_filename(output_name)
        task.execute()
        task.download(str(output_folder))

        files = [item for item in output_folder.iterdir() if item.is_file()]
        if not files:
            return {
                "success": False,
                "message": "Conversion finished, but no output file was returned.",
            }

        output_file = files[0].name
        save_owned_file_record(profile_id, files[0], output_file)
        return {
            "success": True,
            "file_name": output_file,
            "download_url": f"{API_PUBLIC_BASE_URL}/download/{output_id}/{output_file}",
            "message": "File converted successfully.",
        }

    except Exception as exc:
        if intent == "pdf_to_docx" and output_name:
            return pdf_to_docx_text_fallback(
                profile_id,
                file_path,
                filename,
                output_folder,
                output_id,
                output_name,
                cloud_error=exc,
            )
        if intent == "docx_to_pdf" and output_name:
            local_result = docx_to_pdf_local_fallback(
                profile_id,
                file_path,
                output_folder,
                output_id,
                output_name,
                cloud_error=exc,
            )
            if local_result is not None:
                return local_result
        return {
            "success": False,
            "message": f"Document conversion failed: {exc}",
        }


def extract_weather_city(message: str) -> str:
    match = re.search(
        r"\b(?:weather|temperature|forecast|rain|climate)\b(?:\s+(?:in|for|at|of))?\s+([a-zA-Z ,]+)",
        message,
        re.IGNORECASE,
    )

    if match:
        city = match.group(1).strip(" ?.,")
        city = re.sub(r"^(?:of|in|for|at)\s+", "", city, flags=re.IGNORECASE).strip(" ?.,")
        city = re.sub(
            r"\b(?:today|now|currently|current|please|right now|temperature|weather|forecast)\b",
            "",
            city,
            flags=re.IGNORECASE,
        )
        city = re.sub(r"\s+", " ", city).strip(" ?.,")
        if city:
            return city

    return "Pune"


def get_weather(city: str) -> str:
    if not WEATHER_API_KEY:
        return "Weather is not configured yet. Add WEATHER_API_KEY to your .env file."

    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": WEATHER_API_KEY, "units": "metric"},
            timeout=15,
        )
        data = response.json()

        if response.status_code != 200 or data.get("cod") != 200:
            return f"Weather data was not found for {city}."

        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        condition = data["weather"][0]["description"]
        wind = data["wind"]["speed"]

        return (
            f"Current weather in {city}:\n"
            f"- Temperature: {temp} C\n"
            f"- Feels like: {feels} C\n"
            f"- Condition: {condition}\n"
            f"- Humidity: {humidity}%\n"
            f"- Wind speed: {wind} m/s"
        )

    except Exception as exc:
        return f"Weather fetch failed: {exc}"


def is_weather_question(message: str) -> bool:
    return any(
        keyword in message.lower()
        for keyword in ["weather", "temperature", "forecast", "rain", "climate"]
    )


def normalized_message_text(message: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s']+", " ", str(message or "").lower()).strip()
    return re.sub(r"\s+", " ", text)


def normalize_search_intent_text(message: str) -> str:
    text = normalized_message_text(message)
    typo_replacements = {
        "newz": "news",
        "neuz": "news",
        "nwz": "news",
        "latst": "latest",
        "latesst": "latest",
        "lates": "latest",
        "letest": "latest",
        "newestt": "newest",
        "recnt": "recent",
        "recentt": "recent",
        "updte": "update",
        "updat": "update",
        "updet": "update",
        "updats": "updates",
        "curent": "current",
        "currunt": "current",
        "currnt": "current",
        "happend": "happened",
        "hapened": "happened",
        "happning": "happening",
        "todays": "today",
        "todai": "today",
        "tdy": "today",
        "tonights": "tonight",
    }
    words = [typo_replacements.get(word, word) for word in text.split()]
    normalized = " ".join(words)
    normalized = (
        normalized.replace("today's", "today")
        .replace("what's", "whats")
        .replace("today s", "today")
        .replace("what s", "whats")
    )
    return re.sub(r"\s+", " ", normalized).strip()


def recent_assistant_texts(
    recent_messages: list[dict[str, Any]] | None,
    limit: int = 5,
) -> list[str]:
    texts: list[str] = []
    for item in reversed(recent_messages or []):
        if item.get("role") == "assistant":
            text = str(item.get("content") or item.get("text") or "").strip()
            if text:
                texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def response_fingerprint(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\s]+", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", normalized).strip()[:120]


def choose_distinct_response(
    candidates: list[str],
    recent_messages: list[dict[str, Any]] | None = None,
) -> str:
    recent = {response_fingerprint(text) for text in recent_assistant_texts(recent_messages)}
    for candidate in candidates:
        if response_fingerprint(candidate) not in recent:
            return candidate
    return candidates[-1] if candidates else ""


FOLLOW_UP_REFERENCE_WORDS = {
    "he",
    "him",
    "his",
    "she",
    "her",
    "it",
    "its",
    "they",
    "them",
    "that",
    "this",
    "these",
    "those",
    "same",
    "above",
    "previous",
    "earlier",
    "pm",
}

FOLLOW_UP_REFERENCE_PHRASES = [
    "that answer",
    "this answer",
    "previous answer",
    "above answer",
    "same thing",
    "same topic",
    "this file",
    "that file",
    "this pdf",
    "that pdf",
    "the pdf",
    "the file",
    "the document",
    "uploaded file",
    "uploaded document",
    "this image",
    "that image",
    "the image",
]

SHORT_CONTEXT_CONTINUATIONS = {
    "website",
    "websites",
    "site",
    "sites",
    "app",
    "apps",
    "ai",
    "tool",
    "tools",
    "python",
    "react",
    "frontend",
    "backend",
    "project",
    "projects",
    "coding",
    "programming",
    "yes",
    "no",
    "maybe",
}


def context_message_text(item: dict[str, Any]) -> str:
    return str(item.get("content") or item.get("text") or item.get("message") or "").strip()


def has_recent_context(recent_messages: list[dict[str, Any]] | None) -> bool:
    return any(context_message_text(item) for item in (recent_messages or [])[-8:])


def has_followup_reference(message: str) -> bool:
    text = normalize_search_intent_text(message)
    if not text:
        return False
    if any(phrase in text for phrase in FOLLOW_UP_REFERENCE_PHRASES):
        return True
    words = set(text.split())
    return bool(words & FOLLOW_UP_REFERENCE_WORDS)


def infer_recent_context_type(recent_messages: list[dict[str, Any]] | None) -> str:
    recent_text = " ".join(context_message_text(item) for item in (recent_messages or [])[-8:]).lower()
    recent_text = normalize_search_intent_text(recent_text)
    if not recent_text:
        return "none"
    if any(term in recent_text for term in ["pdf", "document", "file", "uploaded", "image", "ocr", "docx"]):
        return "document"
    if any(
        term in recent_text
        for term in [
            "code",
            "coding",
            "program",
            "python",
            "javascript",
            "react",
            "frontend",
            "backend",
            "website",
            "websites",
            "app",
            "debug",
            "error",
        ]
    ):
        return "coding"
    if any(term in recent_text for term in ["latest", "current", "news", "source", "searched", "web search"]):
        return "research"
    if any(term in recent_text for term in ["quiz", "study", "exam", "notes", "teach", "explain"]):
        return "study"
    return "general"


def is_short_context_continuation(
    message: str,
    recent_messages: list[dict[str, Any]] | None,
) -> bool:
    text = normalize_search_intent_text(message)
    words = text.split()
    if not words or len(words) > 4 or not has_recent_context(recent_messages):
        return False
    if is_casual_chat_message(message) or is_acknowledgement(message):
        return False
    if set(words) & SHORT_CONTEXT_CONTINUATIONS:
        return True
    previous_text = " ".join(context_message_text(item) for item in (recent_messages or [])[-4:]).lower()
    previous_text = normalize_search_intent_text(previous_text)
    if previous_text.endswith("?") and len(words) <= 3:
        return True
    return False


def build_followup_context(
    message: str,
    recent_messages: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    has_context = has_recent_context(recent_messages)
    reference = has_followup_reference(message)
    short_continuation = is_short_context_continuation(message, recent_messages)
    is_followup = bool(has_context and (reference or short_continuation))
    if not is_followup:
        return {
            "isFollowUp": False,
            "followUpReferences": [],
            "followUpRecentContext": "",
            "followUpInstruction": "",
            "recentContextType": infer_recent_context_type(recent_messages),
        }

    text = normalize_search_intent_text(message)
    references = [word for word in FOLLOW_UP_REFERENCE_WORDS if re.search(rf"\b{re.escape(word)}\b", text)]
    references.extend(phrase for phrase in FOLLOW_UP_REFERENCE_PHRASES if phrase in text)
    references = list(dict.fromkeys(references))
    recent_lines = []
    for item in (recent_messages or [])[-6:]:
        role = item.get("role") or "message"
        content = context_message_text(item)
        if content:
            recent_lines.append(f"{role}: {clip_text(content, 240)}")

    instruction = (
        "Resolve the user's short reference using the recent conversation before answering. "
        "Do not restart the topic or ask what they mean if the reference is clear from recent context. "
        "If the reference is still ambiguous after checking context, ask one short clarifying question."
    )
    if short_continuation:
        instruction += " The current message is a short continuation of the previous turn."

    return {
        "isFollowUp": True,
        "followUpReferences": references,
        "followUpRecentContext": "\n".join(recent_lines),
        "followUpInstruction": instruction,
        "recentContextType": infer_recent_context_type(recent_messages),
    }


def is_random_talk_message(message: str) -> bool:
    text = normalize_search_intent_text(message).replace("i'm", "i am")
    words = text.split()
    if not words or len(words) > 24:
        return False
    phrases = [
        "i just want to talk",
        "just want to talk",
        "i want to talk",
        "can we talk",
        "lets talk",
        "let us talk",
        "random thing",
        "random things",
        "random thoughts",
        "just chatting",
        "just chat",
        "i am bored",
        "feeling bored",
    ]
    return any(phrase in text for phrase in phrases)


def is_coding_smalltalk_message(message: str) -> bool:
    text = normalize_search_intent_text(message).replace("i'm", "i am")
    words = text.split()
    if not words or len(words) > 14:
        return False
    phrases = [
        "i do coding",
        "i code",
        "i am coding",
        "i like coding",
        "i love coding",
        "i do programming",
        "i am a programmer",
        "i make websites",
        "i build websites",
        "i make apps",
        "i build apps",
        "i make ai tools",
    ]
    return any(phrase in text for phrase in phrases)


def is_casual_chat_message(message: str) -> bool:
    text = normalize_search_intent_text(message)
    if not text:
        return False
    words = text.split()
    if len(words) > 16 and not (is_random_talk_message(message) or is_coding_smalltalk_message(message)):
        return False
    if has_explicit_search_request(text) or requires_current_information(text):
        return False
    if is_random_talk_message(message) or is_coding_smalltalk_message(message):
        return True
    request_words = {
        "can",
        "could",
        "would",
        "please",
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "which",
        "explain",
        "define",
        "calculate",
        "convert",
        "write",
        "create",
        "make",
        "debug",
        "search",
        "news",
        "weather",
        "tell",
        "show",
    }
    casual_phrases = {
        "hi",
        "hii",
        "hello",
        "hey",
        "yo",
        "bro",
        "brother",
        "hello bro",
        "hello brother",
        "yo bro",
        "yo brother",
        "whats up",
        "wassup",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
        "goodnight",
        "bye",
        "byee",
        "goodbye",
        "thanks",
        "thank you",
        "thanks bro",
        "nice",
        "great",
        "cool",
        "ok",
        "okay",
        "got it",
    }
    if text in casual_phrases:
        return True
    if any(
        phrase in text
        for phrase in [
            "yo bro",
            "yo brother",
            "hello bro",
            "hello brother",
            "thanks bro",
            "good night",
            "whats up",
            "what's up",
            "random thing",
            "random thoughts",
            "just chat",
            "just chatting",
        ]
    ):
        return True
    if len(words) <= 4 and any(
        word in {"bro", "brother", "hi", "hii", "hello", "hey", "yo", "thanks", "nice", "ok", "okay"}
        for word in words
    ):
        return not any(word in request_words for word in words)
    return False


EMOTIONAL_TONE_INSTRUCTIONS = {
    "neutral": "Respond naturally and professionally without adding unnecessary emotional framing.",
    "frustrated": "Stay calm and practical; acknowledge friction briefly, then focus on the fix.",
    "excited": "Match the positive energy lightly while staying grounded and useful.",
    "confused": "Be patient and clear; simplify the explanation and ask a clarifying question only if needed.",
    "urgent": "Be direct and action-focused; prioritize the next useful step and avoid filler.",
    "casual": "Keep the reply friendly and natural without forcing a formal structure.",
    "sad": "Be gentle and supportive without making mental-health assumptions.",
    "confident": "Respect the user's confidence and give precise, efficient help without overexplaining.",
}


def detect_emotional_tone(message: str) -> dict[str, str]:
    """Classify user tone deterministically for future prompt routing."""
    text = normalize_search_intent_text(message)
    words = set(text.split())

    if not text:
        tone = "neutral"
    elif has_research_phrase(
        text,
        [
            "not working",
            "does not work",
            "doesnt work",
            "error",
            "broken",
            "stuck",
            "again",
            "issue",
            "problem",
            "why is this",
            "why this",
        ],
    ):
        tone = "frustrated"
    elif has_research_phrase(text, ["urgent", "deadline", "asap", "quick", "fast", "right now", "need now"]):
        tone = "urgent"
    elif has_research_phrase(
        text,
        ["i dont understand", "i do not understand", "confused", "what mean", "what does this mean", "explain"],
    ) or (text.startswith("how ") and len(words) <= 8):
        tone = "confused"
    elif has_research_phrase(text, ["great", "nice", "awesome", "lets go", "let us go", "perfect", "love it"]):
        tone = "excited"
    elif has_research_phrase(text, ["worried", "scared", "tired", "stressed", "i failed", "feeling low"]):
        tone = "sad"
    elif has_research_phrase(text, ["i know", "i can", "i understand", "got it", "done", "clear", "i am sure"]):
        tone = "confident"
    elif is_casual_chat_message(message) or words.intersection({"bro", "brother", "yo", "bhai", "hey", "sup"}):
        tone = "casual"
    else:
        tone = "neutral"

    return {
        "tone": tone,
        "instruction": EMOTIONAL_TONE_INSTRUCTIONS[tone],
    }


def detect_user_tone(message: str) -> str:
    text = normalize_search_intent_text(message)
    if has_research_phrase(text, ["not working", "error", "broken", "failed", "issue", "problem"]):
        return "frustrated"
    if has_research_phrase(text, ["confused", "dont understand", "do not understand", "what is this"]):
        return "confused"
    if has_research_phrase(text, ["haha", "lol", "funny"]):
        return "playful"
    if is_casual_chat_message(message) or any(word in text.split() for word in ["bro", "brother", "yo"]):
        return "casual"
    if has_research_phrase(text, ["please", "requirement", "implement", "professional"]):
        return "professional"
    return "neutral"


def detect_conversation_type(
    message: str,
    has_file_context: bool = False,
    has_search_context: bool = False,
    recent_messages: list[dict[str, Any]] | None = None,
) -> str:
    text = normalize_search_intent_text(message)
    followup = build_followup_context(message, recent_messages)
    if is_creator_question(message):
        return "identity"
    if is_memory_control_message(message):
        return "tool"
    if is_weather_question(message) or is_calculator_question(message):
        return "tool"
    if has_file_context or has_document_reference(message):
        return "document"
    if has_search_context or has_explicit_search_request(message) or requires_current_information(message):
        return "research"
    if followup.get("isFollowUp"):
        recent_type = str(followup.get("recentContextType") or "")
        if recent_type in {"document", "coding", "research"}:
            return recent_type
        return "follow_up"
    if is_casual_chat_message(message):
        return "casual"
    coding_terms = ["code", "program", "python", "javascript", "react", "error", "debug", "function", "api"]
    if any(term in text for term in coding_terms):
        return "coding"
    if len(text.split()) <= 2 and not str(message).strip().endswith("?"):
        return "unclear"
    return "general"


def detect_intent(
    message: str,
    recent_messages: list[dict[str, Any]] | None = None,
) -> str:
    text = normalize_search_intent_text(message)
    if is_creator_question(message):
        return "ask_identity"
    if has_document_reference(message):
        return "request_document_analysis"
    if is_calculator_question(message):
        return "request_calculation"
    if is_weather_question(message):
        return "request_weather"
    if has_explicit_search_request(message) or requires_current_information(message):
        return "request_recent_info"
    if build_followup_context(message, recent_messages).get("isFollowUp"):
        return "follow_up"
    if is_casual_chat_message(message):
        if any(word in text.split() for word in ["thanks", "thank", "nice", "great", "cool", "ok", "okay"]):
            return "casual_acknowledgement"
        return "casual_chat"
    if has_research_phrase(text, ["explain", "define", "what is", "what are", "teach"]):
        return "request_explanation"
    return "general"


def choose_response_style(intent: str, tone: str, conversation_type: str) -> str:
    if conversation_type == "casual" or intent.startswith("casual"):
        return "natural_short"
    if conversation_type == "follow_up" or intent == "follow_up":
        return "contextual"
    if conversation_type == "research":
        return "source_aware"
    if conversation_type == "document":
        return "document_grounded"
    if conversation_type == "coding":
        return "technical_practical"
    if tone in {"frustrated", "confused"}:
        return "calm_helpful"
    return "balanced"


def classify_conversation(
    message: str,
    recent_messages: list[dict[str, Any]] | None = None,
    has_file_context: bool = False,
    has_search_context: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    followup = build_followup_context(message, recent_messages)
    conversation_type = detect_conversation_type(message, has_file_context, has_search_context, recent_messages)
    intent = detect_intent(message, recent_messages)
    emotional_tone = detect_emotional_tone(message)
    tone = detect_user_tone(message)
    tool_need = "chat"
    if conversation_type == "tool":
        tool_need = "direct"
    elif conversation_type == "document":
        tool_need = "document_rag"
    elif conversation_type == "research":
        tool_need = "web_search"
    elif conversation_type == "identity":
        tool_need = "direct"
    return {
        "conversationType": conversation_type,
        "intent": intent,
        "userTone": tone,
        "emotionalTone": emotional_tone,
        "toneInstruction": emotional_tone["instruction"],
        "responseStyle": choose_response_style(intent, tone, conversation_type),
        "toolNeed": tool_need,
        "contextNeed": "recent_chat" if followup.get("isFollowUp") else ("current_chat" if has_file_context or recent_messages else "none"),
        "isCasual": conversation_type == "casual" or intent.startswith("casual"),
        "searchNormalized": normalize_search_intent_text(message),
        "searchEnabled": bool((settings or DEFAULT_SETTINGS).get("searchEnabled", True)),
        "isFollowUp": bool(followup.get("isFollowUp")),
        "followUpReferences": followup.get("followUpReferences", []),
        "followUpRecentContext": followup.get("followUpRecentContext", ""),
        "followUpInstruction": followup.get("followUpInstruction", ""),
        "recentContextType": followup.get("recentContextType", "none"),
    }


def is_creator_question(message: str) -> bool:
    msg_lower = message.lower()
    patterns = [
        r"\bwho\s+(created|made|built|developed)\s+(you|febguy|febguy ai|febguyai)\b",
        r"\bwho\s+is\s+(your\s+)?(owner|creator|founder)\b",
        r"\bwho\s+is\s+the\s+(owner|creator|founder)\s+of\s+(febguy|febguy ai|febguyai)\b",
        r"\b(owner|creator|founder)\s+of\s+(febguy|febguy ai|febguyai)\b",
        r"\bwho\s+owns\s+(you|febguy|febguy ai|febguyai)\b",
        r"\bwho\s+is\s+pranav\s+amble\b",
        r"\btell\s+me\s+about\s+pranav\s+amble\b",
    ]
    return any(re.search(pattern, msg_lower) for pattern in patterns)


def creator_response(
    message: str,
    recent_messages: list[dict[str, Any]] | None = None,
) -> str:
    msg_lower = message.lower()

    if "who is pranav amble" in msg_lower or "tell me about pranav amble" in msg_lower:
        return choose_distinct_response(
            [
                (
                    "Pranav Amble is the founder of FebGuy AI. He also created and owns FebGuy AI, "
                    "building it as a private AI workspace for chat, voice, files, web search, memory, and document tools."
                ),
                (
                    "Pranav Amble is the creator, founder, and owner behind FebGuy AI. He built it to help users "
                    "work with conversations, documents, search, voice, and coding tools."
                ),
                (
                    "Pranav Amble founded and created FebGuy AI. He is also its owner, and FebGuy AI is built around "
                    "private workspaces, document help, search, voice, and coding support."
                ),
            ],
            recent_messages,
        )

    if "owner" in msg_lower or "owns" in msg_lower:
        return choose_distinct_response(
            [
                "My owner is Pranav Amble. He is also the creator and founder of FebGuy AI.",
                "FebGuy AI is owned by Pranav Amble, who also created and founded it.",
                "Pranav Amble is the owner, creator, and founder of FebGuy AI.",
            ],
            recent_messages,
        )

    return choose_distinct_response(
        [
            "FebGuy AI was created by Pranav Amble. He is also the founder and owner of FebGuy AI.",
            "Pranav Amble is the creator, founder, and owner of FebGuy AI.",
            "FebGuy AI comes from Pranav Amble, who created, founded, and owns it.",
        ],
        recent_messages,
    )


def short_social_response(
    message: str,
    recent_messages: list[dict[str, Any]] | None = None,
) -> str | None:
    normalized = normalize_search_intent_text(message).replace("i'm", "i am")
    words = normalized.split()

    if not words:
        return None
    if len(words) > 12 and not (is_random_talk_message(message) or is_coding_smalltalk_message(message)):
        return None

    farewell_phrases = {
        "bye",
        "byee",
        "goodbye",
        "good bye",
        "good night",
        "goodnight",
        "see you",
        "see you later",
        "talk later",
        "talk to you later",
    }
    if any(phrase in normalized for phrase in farewell_phrases):
        if "night" in normalized:
            return choose_distinct_response(
                [
                    "Good night. Rest well; I'll be here when you come back.",
                    "Good night. Take care, and we can continue whenever you're ready.",
                    "Sleep well. I'll be ready when you need help again.",
                ],
                recent_messages,
            )
        return choose_distinct_response(
            [
                "Goodbye. Take care, and I'll be here whenever you need help again.",
                "See you. Come back anytime and we'll continue from here.",
                "Bye for now. I'll be here when you need me.",
            ],
            recent_messages,
        )

    if re.search(r"\bhow\s+(are|r)\s+(you|u)(\s+(doing|going))?\b", normalized):
        return choose_distinct_response(
            [
                "I'm doing well, thanks for asking. How are you doing?",
                "I'm good and ready to help. How's your side going?",
                "Doing well. Tell me what you're working on today.",
            ],
            recent_messages,
        )

    if is_random_talk_message(message):
        return choose_distinct_response(
            [
                "Sure, I am here. Want to talk about coding, college, games, ideas, or just random thoughts?",
                "Of course. We can talk casually. What is on your mind?",
                "Yes, we can just talk. Pick a topic or start with whatever is in your head.",
            ],
            recent_messages,
        )

    if is_coding_smalltalk_message(message):
        return choose_distinct_response(
            [
                "Nice. What are you building these days: websites, AI tools, apps, or college projects?",
                "That is good. Are you mostly coding websites, apps, AI tools, or college projects right now?",
                "Nice, coding is a strong skill to build. What kind of projects do you enjoy making?",
            ],
            recent_messages,
        )

    request_words = {
        "can",
        "could",
        "would",
        "please",
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "which",
        "explain",
        "define",
        "calculate",
        "convert",
        "write",
        "create",
        "make",
        "debug",
        "search",
        "tell",
        "show",
    }
    if "?" in message or any(word in request_words for word in words):
        return None

    if normalized in {"hello bro", "hello brother"}:
        return choose_distinct_response(
            [
                "Hello bro. What are we working on today?",
                "Hey brother. What do you want to solve today?",
                "Hello brother. Tell me what you need help with.",
            ],
            recent_messages,
        )

    if normalized in {"yo bro", "yo brother"}:
        return choose_distinct_response(
            [
                "Yo brother, what is up?",
                "Yo bro. What are we doing today?",
                "Hey brother. What do you want to solve today?",
            ],
            recent_messages,
        )

    if normalized == "good morning":
        return choose_distinct_response(
            [
                "Good morning. What do you want to work on today?",
                "Morning. Ready when you are; what should we start with?",
                "Good morning. Tell me what you need help with.",
            ],
            recent_messages,
        )

    if normalized == "good afternoon":
        return choose_distinct_response(
            [
                "Good afternoon. What are we working on?",
                "Good afternoon. What do you want to solve today?",
                "Afternoon. Tell me what you need help with.",
            ],
            recent_messages,
        )

    if normalized == "good evening":
        return choose_distinct_response(
            [
                "Good evening. What are we working on tonight?",
                "Good evening. How can I help you now?",
                "Evening. Tell me what you want to do next.",
            ],
            recent_messages,
        )

    if normalized in {
        "hi",
        "hii",
        "hello",
        "hey",
        "yo",
        "bro",
        "brother",
        "hello bro",
        "hello brother",
        "yo bro",
        "yo brother",
    }:
        return choose_distinct_response(
            [
                "Hey. What are we working on?",
                "Hello. Tell me what you need help with.",
                "Yo, I'm here. What do you want to solve?",
                "Hey brother. What's on your mind?",
            ],
            recent_messages,
        )

    gratitude_words = {
        "thanks",
        "thank",
        "thankyou",
        "ty",
        "appreciate",
        "appreciated",
        "apprecciate",
        "thx",
    }
    praise_words = {
        "nice",
        "nicr",
        "good",
        "great",
        "awesome",
        "amazing",
        "perfect",
        "excellent",
        "useful",
        "helpful",
        "cool",
        "love",
        "liked",
    }
    acknowledgement_words = {
        "ok",
        "okay",
        "k",
        "got",
        "understood",
        "done",
        "fine",
        "yes",
        "yeah",
        "yep",
        "no",
        "nope",
    }

    if any(word in gratitude_words for word in words):
        return choose_distinct_response(
            [
                "You're welcome. Glad I could help.",
                "Anytime. Happy to help.",
                "No problem. We can keep going whenever you want.",
            ],
            recent_messages,
        )

    if any(word in praise_words for word in words):
        return choose_distinct_response(
            [
                "Glad it helped.",
                "Nice, happy that was useful.",
                "Great. We can build on that whenever you're ready.",
            ],
            recent_messages,
        )

    if all(word in acknowledgement_words or word == "it" for word in words):
        return choose_distinct_response(
            [
                "Got it.",
                "Okay, noted.",
                "Understood.",
            ],
            recent_messages,
        )

    return None


def direct_tool_response(
    message: str,
    current_chat: dict[str, Any] | None = None,
    conversation: dict[str, Any] | None = None,
) -> str | None:
    msg_lower = message.lower().strip()
    now = datetime.now()
    recent_messages = (current_chat or {}).get("messages", [])

    memory_response = memory_control_response(message)
    if memory_response:
        return memory_response

    if is_creator_question(message):
        return creator_response(message, recent_messages)

    social_response = short_social_response(message, recent_messages)
    if social_response:
        return social_response

    if any(
        phrase in msg_lower
        for phrase in ["today's date", "what is the date", "current date"]
    ):
        return f"Today's date is {now.strftime('%d %B %Y')}."

    if any(phrase in msg_lower for phrase in ["what time", "current time"]):
        return f"The current time is {now.strftime('%I:%M %p')}."

    if is_weather_question(message):
        return get_weather(extract_weather_city(message))

    if is_calculator_question(message):
        expression = extract_calculation_expression(message)
        if not expression:
            return "Tell me the expression you want me to calculate."

        try:
            result = safe_calculate(expression)
            return f"{expression} = {result}"
        except Exception:
            return "Calculation failed. Please use a simple arithmetic expression."

    return None


def is_direct_tool_message(message: str) -> bool:
    msg_lower = message.lower().strip()
    return (
        is_memory_control_message(message)
        or is_creator_question(message)
        or short_social_response(message) is not None
        or
        any(
            phrase in msg_lower
            for phrase in ["today's date", "what is the date", "current date"]
        )
        or any(phrase in msg_lower for phrase in ["what time", "current time"])
        or is_weather_question(message)
        or is_calculator_question(message)
    )


def classify_intent(
    message: str,
    has_file_context: bool = False,
    has_search_context: bool = False,
    conversation: dict[str, Any] | None = None,
) -> str:
    if conversation and conversation.get("intent"):
        mapped = {
            "ask_identity": "identity",
            "request_recent_info": "web_research",
            "request_document_analysis": "document_help",
            "request_calculation": "math",
            "request_weather": "daily_help",
            "casual_acknowledgement": "casual",
            "casual_chat": "casual",
            "request_explanation": "study_help",
            "follow_up": "general_help",
            "general": "general_help",
        }
        return mapped.get(str(conversation["intent"]), str(conversation["intent"]))

    msg_lower = normalize_search_intent_text(message)

    if is_creator_question(message):
        return "identity"

    if is_memory_control_message(message):
        return "memory"

    if has_file_context or has_document_reference(message):
        return "document_help"

    if has_search_context or has_explicit_search_request(message):
        return "web_research"

    if is_weather_question(message):
        return "daily_help"

    if is_calculator_question(message):
        return "math"

    if any(term in msg_lower for term in ["quiz", "practice questions", "flashcard", "flash cards", "study notes"]):
        return "study_help"

    coding_terms = [
        "code",
        "program",
        "python",
        "javascript",
        "react",
        "fastapi",
        "html",
        "css",
        "bug",
        "error",
        "debug",
        "function",
        "api",
        "database",
        "server",
        "frontend",
        "backend",
    ]
    if any(term in msg_lower for term in coding_terms):
        return "coding_help"

    study_terms = [
        "study",
        "explain",
        "learn",
        "exam",
        "homework",
        "notes",
        "chapter",
        "topic",
        "concept",
        "question paper",
        "syllabus",
        "teach",
    ]
    if any(term in msg_lower for term in study_terms):
        return "study_help"

    if any(
        phrase in msg_lower
        for phrase in ["plan", "roadmap", "schedule", "steps", "how should i"]
    ):
        return "planning"

    if is_casual_chat_message(message):
        return "casual"

    return "general_help"


def detect_answer_mode(message: str, intent: str) -> str:
    msg_lower = message.lower()
    if intent == "memory" or is_memory_control_message(message):
        return "memory"
    if any(term in msg_lower for term in ["quiz", "questions for practice", "practice questions", "mcq", "multiple choice"]):
        return "quiz"
    if any(term in msg_lower for term in ["flashcard", "flash cards"]):
        return "flashcards"
    if any(term in msg_lower for term in ["notes", "short notes", "study notes"]):
        return "notes"
    if any(term in msg_lower for term in ["simple", "simpler", "beginner", "easy language"]):
        return "simple"
    if any(term in msg_lower for term in ["step by step", "steps", "procedure"]):
        return "step_by_step"
    if any(term in msg_lower for term in ["compare", "difference between", "vs"]):
        return "compare"
    if any(term in msg_lower for term in ["detailed", "deep", "in detail"]):
        return "detailed"
    if intent == "web_research":
        return "research"
    if intent == "document_help":
        return "document"
    if intent == "coding_help":
        return "code_help"
    return "balanced"


def answer_mode_instruction(mode: str) -> str:
    instructions = {
        "quiz": (
            "Answer mode: Practice Quiz\n"
            "- Create useful quiz questions from the topic.\n"
            "- Mix easy, medium, and slightly challenging questions when possible.\n"
            "- Put the answer key after the questions.\n"
            "- Add one short revision tip at the end."
        ),
        "flashcards": (
            "Answer mode: Flashcards\n"
            "- Format as front/back flashcards.\n"
            "- Keep each card short and exam-friendly."
        ),
        "notes": (
            "Answer mode: Study Notes\n"
            "- Use headings, key points, examples, and a compact summary.\n"
            "- Avoid long paragraphs."
        ),
        "simple": (
            "Answer mode: Simple Explanation\n"
            "- Explain like the user is learning it for the first time.\n"
            "- Use one clear example."
        ),
        "step_by_step": (
            "Answer mode: Step-by-step\n"
            "- Give numbered steps.\n"
            "- Mention the expected result after key steps."
        ),
        "compare": (
            "Answer mode: Comparison\n"
            "- Use a compact table when useful.\n"
            "- Highlight the practical difference, not only definitions."
        ),
        "detailed": (
            "Answer mode: Detailed\n"
            "- Give a complete explanation with structure.\n"
            "- Keep it readable and avoid filler."
        ),
        "research": (
            "Answer mode: Research Summary\n"
            "- Start with a concise conclusion.\n"
            "- Then summarize the strongest evidence and cite uncertainty."
        ),
        "document": (
            "Answer mode: Document-grounded\n"
            "- Answer from the document chunks first.\n"
            "- Mention if the document does not include enough evidence."
        ),
        "code_help": (
            "Answer mode: Coding Help\n"
            "- Be practical and precise.\n"
            "- Ask for the exact error/code if missing."
        ),
        "memory": (
            "Answer mode: Memory Control\n"
            "- Confirm the memory action briefly."
        ),
    }
    return instructions.get(mode, "Answer mode: Balanced\n- Be clear, useful, and not overly long.")


def normalize_answer_length(value: str | None) -> str:
    normalized = str(value or "standard").strip().lower()
    return normalized if normalized in {"short", "standard", "detailed"} else "standard"


def answer_length_instruction(value: str | None) -> str:
    instructions = {
        "short": (
            "User-selected response length: Short\n"
            "- Be direct and compact.\n"
            "- Give only the key answer and essential next action."
        ),
        "detailed": (
            "User-selected response length: Detailed\n"
            "- Explain the answer thoroughly with helpful examples or steps when relevant.\n"
            "- Keep the detail structured and practical rather than repetitive."
        ),
    }
    return instructions.get(
        normalize_answer_length(value),
        "User-selected response length: Standard\n- Give a balanced answer with enough explanation to be useful.",
    )


def select_response_quality_profile(
    message: str,
    intent: str,
    answer_mode: str,
    conversation: dict[str, Any] | None,
    has_file_context: bool,
    has_search_context: bool,
) -> str:
    conversation = conversation or {}
    conversation_type = str(conversation.get("conversationType") or "")
    recent_type = str(conversation.get("recentContextType") or "")
    if conversation.get("isCasual") or intent == "casual":
        return "natural_chat"
    if is_acknowledgement(message) or intent in {"identity", "math", "daily_help"}:
        return "quick_answer"
    if has_file_context or intent == "document_help" or conversation_type == "document" or recent_type == "document":
        return "document_analyst"
    if has_search_context or intent == "web_research" or conversation_type == "research":
        return "research_analyst"
    if intent == "coding_help" or conversation_type == "coding" or recent_type == "coding":
        return "coding_expert"
    if intent == "study_help" or answer_mode in {"quiz", "flashcards", "notes", "simple"}:
        return "tutor_mode"
    if answer_mode == "step_by_step":
        return "professional_answer"
    if len(normalize_search_intent_text(message).split()) <= 6 and not message.strip().endswith("?"):
        return "quick_answer"
    return "professional_answer"


def response_quality_profile_instruction(profile: str | None) -> str:
    profile_key = str(profile or "professional_answer")
    instructions = {
        "natural_chat": (
            "Response quality profile: Natural Chat\n"
            "- Sound human, relaxed, and brief.\n"
            "- Match the user's casual tone without forcing a task workflow."
        ),
        "professional_answer": (
            "Response quality profile: Professional Answer\n"
            "- Give a direct answer first, then useful structure.\n"
            "- Stay polished, practical, and focused on the user's goal.\n"
            "- Do not add default headings or a closing action list unless the answer benefits from them."
        ),
        "coding_expert": (
            "Response quality profile: Coding Expert\n"
            "- Diagnose before explaining.\n"
            "- Give exact code, diffs, commands, or fix steps when helpful.\n"
            "- Avoid generic theory unless the user asks to learn."
        ),
        "research_analyst": (
            "Response quality profile: Research Analyst\n"
            "- Compare evidence, remove duplicate facts, and explain uncertainty.\n"
            "- Prefer official or primary sources when supplied.\n"
            "- If search evidence is present, do not claim you lack real-time access."
        ),
        "document_analyst": (
            "Response quality profile: Document Analyst\n"
            "- Ground the answer in the current chat's uploaded files.\n"
            "- Name files/pages when available and say when the document does not contain the answer."
        ),
        "tutor_mode": (
            "Response quality profile: Tutor Mode\n"
            "- Explain from basics, use examples, and check understanding when useful.\n"
            "- Keep the learning path clear and not overwhelming.\n"
            "- Use headings only when they make the lesson easier to scan."
        ),
        "quick_answer": (
            "Response quality profile: Quick Answer\n"
            "- Answer in one or two concise sentences unless the user asks for detail.\n"
            "- No headings, no next steps, and no unnecessary explanation."
        ),
    }
    return instructions.get(profile_key, instructions["professional_answer"])


def analyze_user_intent(
    message: str,
    has_file_context: bool,
    has_search_context: bool,
    settings: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    conversation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or DEFAULT_SETTINGS
    intent = classify_intent(message, has_file_context, has_search_context, conversation=conversation)
    mode = detect_answer_mode(message, intent)
    research = research or build_research_plan(message, has_file_context, settings)
    tool = str((conversation or {}).get("toolNeed") or "chat")
    if intent == "memory":
        tool = "memory"
    elif is_direct_tool_message(message):
        tool = "direct"
    elif has_file_context or intent == "document_help":
        tool = "document_rag"
    elif has_search_context or has_explicit_search_request(message):
        tool = "web_search"
    elif intent == "study_help" and mode in {"quiz", "flashcards", "notes"}:
        tool = "study_tools"

    confidence = 0.6
    if tool != "chat" or intent in {"study_help", "coding_help", "document_help", "web_research"}:
        confidence = 0.84
    if is_acknowledgement(message):
        confidence = 0.92

    response_profile = select_response_quality_profile(
        message,
        intent,
        mode,
        conversation,
        has_file_context,
        has_search_context,
    )
    if conversation is not None:
        conversation["responseProfile"] = response_profile

    return {
        "intent": intent,
        "answerMode": mode,
        "tool": tool,
        "confidence": confidence,
        "responseProfile": response_profile,
        "searchEnabled": bool(settings.get("searchEnabled", True)),
        "ragEnabled": bool(settings.get("ragEnabled", True)),
        "research": research,
        "conversation": conversation or {},
    }


def intent_instruction(intent: str) -> str:
    instructions = {
        "study_help": (
            "Study help mode:\n"
            "- Explain from basics first, then go deeper if useful.\n"
            "- Use examples, analogies, and short practice questions when helpful.\n"
            "- Avoid dumping too much theory without structure."
        ),
        "coding_help": (
            "Coding help mode:\n"
            "- Identify the likely cause, then give practical fix steps.\n"
            "- Use code blocks for code and commands.\n"
            "- Mention assumptions if the exact file or error is missing."
        ),
        "web_research": (
            "Web research mode:\n"
            "- Answer the user's question directly before giving supporting detail.\n"
            "- Use the provided search evidence as the source of current facts, preferring primary or official evidence.\n"
            "- Combine repeated information across sources instead of repeating it.\n"
            "- Compare important claims across sources and clearly mention conflicts or uncertainty.\n"
            "- Keep summaries clean and avoid raw copied snippets."
        ),
        "document_help": (
            "Document help mode:\n"
            "- Answer from the uploaded document first.\n"
            "- If the document does not contain the answer, say so clearly.\n"
            "- Quote only tiny fragments when needed; mostly summarize."
        ),
        "planning": (
            "Planning mode:\n"
            "- Turn the answer into clear phases or steps.\n"
            "- Include priorities, tradeoffs, and a practical next action."
        ),
        "daily_help": (
            "Daily help mode:\n"
            "- Be direct, useful, and practical.\n"
            "- Include exact dates/times/locations when relevant."
        ),
        "memory": (
            "Memory control mode:\n"
            "- Confirm what changed briefly.\n"
            "- Do not repeat the full memory list unless asked."
        ),
        "general_help": (
            "General problem-solving mode:\n"
            "- Start with the answer, then explain the reasoning briefly.\n"
            "- Offer one practical next action only when it is genuinely useful."
        ),
    }
    return instructions.get(intent, instructions["general_help"])


def clarification_response(
    message: str,
    intent: str,
    has_file_context: bool,
    has_history: bool,
    conversation: dict[str, Any] | None = None,
) -> str | None:
    msg_lower = re.sub(r"\s+", " ", message.lower()).strip(" ?.!") 
    words = re.findall(r"[a-zA-Z0-9]+", msg_lower)
    conversation_type = str((conversation or {}).get("conversationType") or "")
    conversation_intent = str((conversation or {}).get("intent") or "")

    if (
        not msg_lower
        or is_direct_tool_message(message)
        or has_file_context
        or has_history
        or intent in {"casual", "identity", "daily_help", "math", "web_research"}
        or conversation_type in {"casual", "identity", "research", "document", "tool", "coding"}
        or conversation_intent.startswith("casual")
    ):
        return None

    vague_messages = {
        "help",
        "help me",
        "can you help",
        "can you help me",
        "fix this",
        "solve this",
        "do this",
        "make this",
        "make it better",
        "improve this",
        "explain this",
        "what about this",
        "tell me about this",
    }

    if msg_lower in vague_messages:
        return (
            "Send the topic, question, error, code, or file you want me to work on, and I will help from there."
        )

    if len(words) <= 2 and not message.strip().endswith("?"):
        return (
            "Give me one more detail so I can answer properly: the topic, goal, file, or error."
        )

    return None


def is_acknowledgement(message: str) -> bool:
    text = re.sub(r"[^a-zA-Z0-9\s]+", " ", message.lower()).strip()
    text = re.sub(r"\s+", " ", text)
    words = text.split()
    acknowledgements = {
        "ok",
        "okay",
        "thanks",
        "thank you",
        "ok thank you",
        "okay thank you",
        "got it",
        "nice",
        "great",
        "cool",
        "yes",
        "no",
        "done",
    }
    if text in acknowledgements:
        return True

    if not words or len(words) > 12:
        return False

    request_words = {
        "can", "could", "would", "please", "what", "why", "how", "when", "where", "who", "which",
        "explain", "define", "calculate", "convert", "write", "create",
        "make", "debug", "search", "tell", "show",
    }
    if any(word in request_words for word in words):
        return False

    if text in {"hi", "hello", "hey", "yo", "good morning", "good afternoon", "good evening"}:
        return True

    social_words = {
        "thanks", "thank", "thankyou", "ty", "thx", "appreciate",
        "appreciated", "apprecciate", "nice", "nicr", "good", "great",
        "awesome", "amazing", "perfect", "excellent", "useful",
        "helpful", "cool", "love", "liked",
    }
    return any(word in social_words for word in words)


def clean_suggestions(suggestions: list[str] | None) -> list[str]:
    cleaned = []
    seen = set()

    for suggestion in suggestions or []:
        item = re.sub(r"\s+", " ", str(suggestion)).strip()
        if not item or item in BANNED_GENERIC_SUGGESTIONS or item.lower() in seen:
            continue
        seen.add(item.lower())
        cleaned.append(item)

    return cleaned[:3]


def suggestion_topic(message: str) -> str:
    topic = re.sub(r"\s+", " ", message).strip(" ?.")
    topic = re.sub(
        r"^(please\s+)?(explain|define|describe|tell me about|what is|what are|make notes on|quiz me on)\s+",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(
        r"^(create|make|generate)\s+(a\s+)?(practice\s+)?(quiz|questions|notes)\s+(from|on|about)\s+",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    return clip_text(topic.strip(" ?.") or "this topic", 58)


def build_followup_suggestions(
    intent: str,
    user_message: str,
    has_file_context: bool = False,
    search_used: bool = False,
) -> list[str]:
    topic = suggestion_topic(user_message)

    if is_acknowledgement(user_message) or is_casual_chat_message(user_message):
        return []

    if intent == "study_help":
        return clean_suggestions([
            f"Show a simple example of {topic}",
            f"Make short notes on {topic}",
            f"Create a practice quiz on {topic}",
        ])

    if intent == "coding_help":
        return clean_suggestions([
            "Give me the exact fix steps",
            "Explain why this error happens",
            "Show a cleaner code version",
        ])

    if intent == "web_research" or search_used:
        return clean_suggestions([
            "Summarize the sources in simple points",
            "Compare the most important details",
            "What should I do next based on this?",
        ])

    if intent == "document_help" or has_file_context:
        return clean_suggestions([
            "Summarize this document",
            "Find the key points in this file",
            "Create questions from this document",
        ])

    if intent == "planning":
        return clean_suggestions([
            "Turn this into a checklist",
            "Make a simple timeline",
            "What is the first step?",
        ])

    if intent == "casual":
        return []

    return []


def has_explicit_search_request(message: str) -> bool:
    normalized = normalize_search_intent_text(message)
    explicit_action = re.search(
        r"\b(look up|look (it|this) up|find online|check the web|search (the )?(web|internet|online)|"
        r"(do|perform|run|use) (a )?web search|web search (for|about|on)|"
        r"today news|latest news|current update|what happened today)\b",
        normalized,
        re.IGNORECASE,
    )
    leading_search_command = re.match(
        r"^\s*(please\s+)?(can you\s+)?(search|google|news)\b",
        normalized,
        re.IGNORECASE,
    )
    return bool(explicit_action or leading_search_command)


def has_research_phrase(message: str, phrases: list[str]) -> bool:
    text = message.lower()
    return any(
        re.search(rf"\b{re.escape(phrase.lower())}\b", text)
        for phrase in phrases
    )


def current_information_signals(message: str) -> list[str]:
    signals = []
    lowered = normalize_search_intent_text(message)
    if has_explicit_search_request(message):
        signals.append("explicit_web_request")

    freshness_terms = [
        "latest",
        "current",
        "today",
        "tonight",
        "tomorrow",
        "yesterday",
        "right now",
        "recent",
        "recently",
        "newest",
        "live",
        "as of",
        "up to date",
        "this week",
        "this month",
        "this year",
    ]
    if has_research_phrase(lowered, freshness_terms):
        signals.append("fresh_information")
    elif re.search(r"\b(now|currently)\b", lowered) and has_research_phrase(
        lowered,
        ["what", "who", "where", "happening", "status", "update", "price", "weather", "score", "ceo", "president"],
    ):
        signals.append("fresh_information")

    changing_topics = [
        "news",
        "breaking news",
        "update",
        "updates",
        "price",
        "stock",
        "score",
        "schedule",
        "standings",
        "fixture",
        "match result",
        "sports result",
        "current event",
        "release date",
        "availability",
        "in stock",
        "ceo",
        "chief executive",
        "chairman",
        "managing director",
        "cto",
        "cfo",
        "current role",
        "president",
        "prime minister",
        "election",
        "exchange rate",
        "interest rate",
        "deadline",
    ]
    if has_research_phrase(lowered, changing_topics):
        signals.append("changing_topic")

    legal_policy_terms = [
        "regulation",
        "regulations",
        "legal requirement",
        "legal requirements",
        "policy update",
        "policy change",
        "government rule",
        "government rules",
        "compliance requirement",
        "compliance requirements",
    ]
    current_legal_terms = ["current", "latest", "new", "today", "legal", "government", "india"]
    if has_research_phrase(lowered, legal_policy_terms) or (
        has_research_phrase(lowered, ["law", "laws", "rule", "rules"])
        and has_research_phrase(lowered, current_legal_terms)
    ):
        signals.append("policy_or_legal")

    sports_terms = [
        "sports",
        "match",
        "fixture",
        "standings",
        "score",
        "tournament",
        "league table",
    ]
    if (
        has_research_phrase(lowered, sports_terms)
        and has_research_phrase(
            lowered,
            ["today", "current", "latest", "live", "recent", "score", "result", "standings", "fixture"],
        )
    ):
        signals.append("sports_or_event")

    recommendation_terms = [
        "recommend",
        "recommendation",
        "best",
    ]
    buyer_choice_terms = [
        "which should i buy",
        "which one should i choose",
    ]
    recommendation_context_terms = [
        "buy",
        "price",
        "cost",
        "deal",
        "available",
        "availability",
        "phone",
        "mobile",
        "laptop",
        "gpu",
        "cpu",
        "camera",
        "model",
        "tool",
        "software",
        "app",
        "website",
        "hosting",
        "api",
        "near me",
        "restaurant",
        "hotel",
        "flight",
        "travel",
        "2025",
        "2026",
        "latest",
        "current",
    ]
    if has_research_phrase(lowered, buyer_choice_terms) or (
        has_research_phrase(lowered, recommendation_terms)
        and has_research_phrase(lowered, recommendation_context_terms)
    ):
        signals.append("recommendation")

    return list(dict.fromkeys(signals))


def requires_current_information(message: str) -> bool:
    signals = current_information_signals(message)
    return any(signal != "explicit_web_request" for signal in signals)


def should_search_message(
    message: str,
    has_file_context: bool,
    settings: dict[str, Any],
) -> bool:
    if not settings.get("searchEnabled", True):
        return False

    msg_lower = normalize_search_intent_text(message)
    original_lower = message.lower()

    if any(
        phrase in msg_lower or phrase in original_lower
        for phrase in ["don't search", "dont search", "do not search", "no web"]
    ):
        return False

    if is_weather_question(message) or is_calculator_question(message) or is_casual_chat_message(message):
        return False

    if has_file_context and is_file_question(message) and not has_explicit_search_request(message):
        return False

    if has_explicit_search_request(message):
        return True

    if requires_current_information(message):
        return True

    realtime_keywords = [
        "as of",
        "online",
        "internet",
        "latest",
        "current",
        "today",
        "news",
        "recent",
        "live",
        "this week",
        "this month",
        "2025",
        "2026",
        "price",
        "stock",
        "score",
        "schedule",
        "release date",
        "ceo",
        "chief executive",
        "chairman",
        "managing director",
        "current role",
        "president",
        "prime minister",
        "regulation",
        "regulations",
        "legal requirement",
        "policy update",
        "standings",
        "fixture",
    ]

    if has_research_phrase(msg_lower, realtime_keywords):
        return True

    if re.search(r"\b(who|what|when|where)\s+(is|are|was|were)\b", msg_lower):
        volatile_terms = ["company", "person", "movie", "game", "event", "election"]
        return has_research_phrase(msg_lower, volatile_terms)

    return False


def build_research_plan(
    message: str,
    has_file_context: bool,
    settings: dict[str, Any],
) -> dict[str, Any]:
    normalized_message = normalize_search_intent_text(message)
    signals = current_information_signals(message)
    used = should_search_message(message, has_file_context, settings)
    depth_terms = [
        "compare",
        "comparison",
        "research",
        "verify",
        "sources",
        "recommend",
        "recommendation",
        "best",
        "pros and cons",
    ]
    depth = "deep" if has_research_phrase(normalized_message, depth_terms) or len(signals) > 1 else "standard"
    return {
        "used": used,
        "requested": bool(signals),
        "requiresFreshInfo": requires_current_information(message),
        "depth": depth,
        "signals": signals,
        "query": extract_search_query(message) if used else "",
        "maxResults": 7 if depth == "deep" else 5,
        "grounded": False,
        "sourceCount": 0,
        "coverage": "not_requested" if not used else "pending",
        "searchEnabled": bool(settings.get("searchEnabled", True)),
    }


def extract_search_query(message: str) -> str:
    normalized = normalize_search_intent_text(message)
    query = re.sub(
        r"^\s*(please\s+)?(search|look up|google|find|check|news)\s+(the\s+web\s+)?(online\s+)?(for\s+)?",
        "",
        normalized or message,
        flags=re.IGNORECASE,
    )
    return rewrite_search_query(query.strip(" ?.") or normalized or message.strip())


def rewrite_search_query(query: str) -> str:
    clean = re.sub(r"\s+", " ", query).strip(" ?.")
    if not clean:
        return query

    remove_phrases = [
        "can you",
        "please",
        "tell me",
        "give me",
        "explain",
        "summarize",
    ]
    lowered = clean.lower()
    for phrase in remove_phrases:
        if lowered.startswith(phrase + " "):
            clean = clean[len(phrase) :].strip()
            lowered = clean.lower()

    return clean


def source_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


PRIMARY_SOURCE_DOMAINS = {
    "openai.com",
    "microsoft.com",
    "apple.com",
    "samsung.com",
    "google.com",
    "about.google",
    "blog.google",
    "python.org",
    "nodejs.org",
    "react.dev",
}


def source_authority_label(domain: str) -> str:
    normalized = (domain or "").lower()
    if (
        normalized.endswith(".gov")
        or ".gov." in normalized
        or normalized.startswith("docs.")
        or normalized.startswith("developer.")
        or any(normalized == item or normalized.endswith(f".{item}") for item in PRIMARY_SOURCE_DOMAINS)
    ):
        return "primary"
    return "supporting"


def research_source_focus(message: str) -> str:
    lowered = message.lower()
    known_company_terms = ["company", "microsoft", "openai", "google", "apple", "iphone", "samsung"]
    company_role_or_product_terms = ["ceo", "chief executive", "president", "chairman", "product", "release date"]
    government_terms = [
        "government",
        "minister",
        "president",
        "election",
        "regulation",
        "legal",
        "policy",
        "parliament",
        "law",
    ]
    software_terms = [
        "api",
        "library",
        "framework",
        "python",
        "javascript",
        "react",
        "software",
        "documentation",
        "release notes",
    ]
    company_terms = [
        "company",
        "ceo",
        "chief executive",
        "microsoft",
        "openai",
        "google",
        "apple",
        "iphone",
        "samsung",
        "product",
    ]
    if has_research_phrase(lowered, known_company_terms) and has_research_phrase(
        lowered, company_role_or_product_terms
    ):
        return "company"
    if has_research_phrase(lowered, government_terms):
        return "government"
    if has_research_phrase(lowered, software_terms):
        return "software"
    if has_research_phrase(lowered, company_terms):
        return "company"
    return "general"


def primary_source_query(query: str, message: str) -> str:
    focus = research_source_focus(message)
    if focus == "government":
        return f"{query} official government statement"
    if focus == "software":
        return f"{query} official documentation release notes"
    if focus == "company":
        return f"{query} official announcement official site"
    return ""


def web_search(
    query: str,
    max_results: int = 5,
    additional_queries: list[str] | None = None,
) -> list[dict[str, str]]:
    if DDGS is None:
        return []

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    errors: list[str] = []
    search_queries = list(dict.fromkeys([query, *(additional_queries or [])]))
    for query_index, search_query in enumerate(search_queries):
        for backend in ("duckduckgo", "brave", "google"):
            try:
                with DDGS() as ddgs:
                    found = ddgs.text(search_query, backend=backend, max_results=max_results * 2)
                added_for_query = 0
                for result in found:
                    href = result.get("href", "").strip()
                    title = result.get("title", "").strip()
                    body = result.get("body", "").strip()
                    fingerprint = (href or title).lower().rstrip("/")
                    if not fingerprint or fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    if title or body or href:
                        domain = source_domain(href)
                        results.append(
                            {
                                "title": title,
                                "body": body,
                                "href": href,
                                "domain": domain,
                                "sourceType": source_authority_label(domain),
                                "searchIntent": "official_priority" if query_index else "general",
                            }
                        )
                        added_for_query += 1
                    if added_for_query >= max_results:
                        break
                if added_for_query:
                    break
            except Exception as exc:
                errors.append(f"{backend}: {type(exc).__name__}")
    if not results and errors:
        LOGGER.warning("Web search failed for all backends (%s).", ", ".join(errors))
    return rank_search_results(query, results)[:max_results]


def rank_search_results(query: str, results: list[dict[str, str]]) -> list[dict[str, str]]:
    trusted_boosts = {
        "wikipedia.org": 2,
        "docs.python.org": 3,
        "developer.mozilla.org": 3,
        "microsoft.com": 2,
        "github.com": 1,
        "stackoverflow.com": 1,
    }
    terms = query_terms(query)
    ranked = []
    for index, result in enumerate(results):
        text = f"{result.get('title', '')} {result.get('body', '')}".lower()
        score = sum(4 + text.count(term) for term in terms if term in text)
        domain = result.get("domain") or source_domain(result.get("href", ""))
        score += next((boost for trusted, boost in trusted_boosts.items() if domain.endswith(trusted)), 0)
        if result.get("sourceType") == "primary":
            score += 6
        if result.get("searchIntent") == "official_priority":
            score += 2
        if domain.endswith(".gov") or ".gov." in domain:
            score += 4
        if domain.endswith(".edu") or ".edu." in domain or domain.endswith(".ac.in"):
            score += 3
        if domain.startswith("docs.") or domain.startswith("developer."):
            score += 2
        if result.get("href"):
            score += 1
        ranked.append((score, -index, result))
    return [result for _score, _index, result in sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True)]


def format_search_context(
    results: list[dict[str, str]],
    retrieved_at: str = "",
    requires_fresh_info: bool = False,
) -> str:
    if not results:
        return ""

    formatted = [
        f"Web evidence checked at: {retrieved_at}" if retrieved_at else "Web evidence retrieved for this answer.",
        f"Fresh information required: {'yes' if requires_fresh_info else 'no'}",
    ]
    for index, result in enumerate(results, start=1):
        title = result.get("title") or "Untitled"
        body = clip_text(re.sub(r"\s+", " ", result.get("body", "")).strip(), 360)
        link = result.get("href") or "No link"
        domain = result.get("domain") or source_domain(link)
        source_type = result.get("sourceType") or source_authority_label(domain)
        formatted.append(
            f"Source {index}\nTitle: {title}\nSite: {domain or 'Unknown'}\n"
            f"Source type: {source_type}\nSummary: {body}\nLink: {link}"
        )

    return "\n\n".join(formatted)


def public_citations(results: list[dict[str, str]], retrieved_at: str = "") -> list[dict[str, str]]:
    citations = []
    for index, result in enumerate(results, start=1):
        if not result.get("href"):
            continue
        citations.append(
            {
                "id": str(index),
                "title": result.get("title") or f"Source {index}",
                "url": result.get("href", ""),
                "domain": result.get("domain") or source_domain(result.get("href", "")),
                "snippet": clip_text(result.get("body", ""), 220),
                "retrievedAt": retrieved_at,
                "sourceType": result.get("sourceType") or source_authority_label(result.get("domain", "")),
            }
        )
    return citations


def prepare_web_research(
    message: str,
    has_file_context: bool,
    settings: dict[str, Any],
) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    plan = build_research_plan(message, has_file_context, settings)
    if is_direct_tool_message(message):
        plan.update({"used": False, "coverage": "built_in_tool", "query": ""})
        return "", [], plan
    if not plan["used"]:
        if plan["requested"] and not settings.get("searchEnabled", True):
            plan.update(
                {
                    "coverage": "search_disabled",
                    "failureReason": "Web search is disabled in settings.",
                }
            )
        return "", [], plan

    focused_query = primary_source_query(plan["query"], message)
    additional_queries = [focused_query] if focused_query and focused_query != plan["query"] else []
    attempted_queries = [plan["query"], *additional_queries]
    search_attempted = DDGS is not None
    results = web_search(
        plan["query"],
        max_results=plan["maxResults"],
        additional_queries=additional_queries,
    )
    retrieved_at = datetime.now().astimezone().isoformat(timespec="seconds")
    citations = public_citations(results, retrieved_at=retrieved_at)
    source_count = len(citations)
    coverage = "strong" if source_count >= 3 else "limited" if source_count else "unavailable"
    plan.update(
        {
            "retrievedAt": retrieved_at,
            "sourceCount": source_count,
            "grounded": bool(citations),
            "coverage": coverage,
            "sourceFocus": research_source_focus(message),
            "queriesTried": attempted_queries,
            "searchAttempted": search_attempted,
        }
    )
    if not citations:
        plan["failureReason"] = (
            "No usable web sources were returned for the attempted search."
            if search_attempted
            else "The web search provider is unavailable."
        )
    context = format_search_context(
        results,
        retrieved_at=retrieved_at,
        requires_fresh_info=plan["requiresFreshInfo"],
    )
    return context, citations, plan


def public_document_hits(hits: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "documentId": hit.get("document_id"),
            "fileName": Path(str(hit.get("file_name") or "Uploaded file")).name,
            "fileType": hit.get("file_type") or "",
            "index": hit.get("index"),
            "pageNumber": hit.get("page_number"),
            "score": hit.get("score", 0),
            "preview": hit.get("preview") or clip_text(hit.get("text", ""), 180),
            "ocrUsed": bool(hit.get("used_ocr")),
            "ocrUncertain": bool(hit.get("ocr_uncertain")),
            "textUnavailable": bool(hit.get("text_unavailable")),
            "isImage": bool(hit.get("is_image")),
        }
        for hit in (hits or [])
    ]


def format_history(messages: list[dict[str, Any]], limit: int = 10) -> str:
    history = []
    for item in messages[-limit:]:
        role = item.get("role", "")
        text = item.get("text", "")
        if text:
            if normalize_message_role(role) == "assistant":
                text = clean_model_output(str(text))
            history.append(f"{normalize_message_role(role)}: {clip_text(str(text), 1200)}")
    return "\n".join(history)


def conversation_instruction(conversation: dict[str, Any] | None) -> str:
    if not conversation:
        return ""
    emotional_tone = conversation.get("emotionalTone") if isinstance(conversation.get("emotionalTone"), dict) else {}
    emotional_label = emotional_tone.get("tone") or "neutral"
    tone_instruction = conversation.get("toneInstruction") or emotional_tone.get("instruction") or ""
    lines = [
        "Conversation routing context:",
        f"- Type: {conversation.get('conversationType', 'general')}",
        f"- Intent: {conversation.get('intent', 'general')}",
        f"- User tone: {conversation.get('userTone', 'neutral')}",
        f"- Emotional tone: {emotional_label}",
        f"- Response style: {conversation.get('responseStyle', 'balanced')}",
        f"- Response profile: {conversation.get('responseProfile', 'professional_answer')}",
    ]
    if tone_instruction:
        lines.append(f"- Tone guidance: {tone_instruction}")
        lines.append(
            "- Tone safety: adapt conservatively; do not claim to feel, fake emotions, or make "
            "medical/mental-health assumptions."
        )
    if conversation.get("isFollowUp"):
        references = ", ".join(conversation.get("followUpReferences") or []) or "short contextual continuation"
        lines.append(f"- Follow-up handling: resolve references ({references}) from recent chat before answering.")
        if conversation.get("followUpInstruction"):
            lines.append(f"- Follow-up instruction: {conversation['followUpInstruction']}")
        if conversation.get("followUpRecentContext"):
            lines.append("Recent context for resolving the follow-up:\n" + conversation["followUpRecentContext"])
    if conversation.get("isCasual"):
        lines.append("- Casual response: use one or two natural sentences; no headings, bullets, or next steps.")
    if conversation.get("conversationType") == "research":
        lines.append("- Research response: answer from current evidence when supplied and explain uncertainty clearly.")
    if conversation.get("conversationType") == "document":
        lines.append("- Document response: prioritize attached current-chat files and name the files used when possible.")
    if conversation.get("conversationType") == "coding":
        lines.append("- Coding response: be practical, precise, and avoid unnecessary filler.")
    return "\n".join(lines)


def build_anti_repetition_instruction(
    recent_messages: list[dict[str, Any]] | None,
    user_message: str,
    conversation: dict[str, Any] | None = None,
) -> str:
    assistant_texts = recent_assistant_texts(recent_messages, limit=4)
    lines = [
        "Response diversity rules:",
        "- Do not reuse the same opening sentence or closing phrase from recent assistant replies.",
        "- Do not always start with \"Sure\" or \"Here's\"; start with the answer when that is cleaner.",
        "- Never write the phrase \"I'm ready for the next question.\"",
        "- Avoid generic recycled lines like \"Let me know if you need anything else\" unless it genuinely fits.",
        "- Do not force \"Next steps\" for casual chat or simple acknowledgements.",
        "- Avoid robotic phrasing and repeated sentence structures.",
        "- Be specific to the user's actual request, project, files, or question.",
        "- If the user repeats a similar question, answer naturally and add one small new useful detail.",
    ]
    openings = []
    for text in assistant_texts:
        first_sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0]
        if first_sentence:
            openings.append(clip_text(first_sentence, 100))
    if openings:
        lines.append("- Avoid these recent openings: " + " | ".join(openings[:3]))
    if (conversation or {}).get("isCasual") or is_casual_chat_message(user_message):
        lines.append("- For casual chat, keep it warm and brief; do not turn it into a task plan.")
    return "\n".join(lines)


def build_prompt(
    user_message: str,
    memory: dict[str, Any],
    current_chat: dict[str, Any],
    file_context: str,
    search_context: str,
    calculator_result: str,
    intent: str = "general_help",
    answer_mode: str = "balanced",
    answer_length: str = "standard",
    response_mode: str = "balanced",
    research: dict[str, Any] | None = None,
    conversation: dict[str, Any] | None = None,
) -> str:
    now = datetime.now()
    research = research or {}
    sections = [
        SYSTEM_PROMPT,
        (
            "Current system info:\n"
            f"- Date: {now.strftime('%d %B %Y')}\n"
            f"- Time: {now.strftime('%I:%M %p')}"
        ),
    ]

    memory_text = format_memory(memory, user_message, conversation)
    if memory_text:
        sections.append(f"Relevant user memory (use only if it directly helps this answer):\n{memory_text}")

    routing_text = conversation_instruction(conversation)
    if routing_text:
        sections.append(routing_text)

    if current_chat.get("summary"):
        sections.append(f"Compressed chat memory:\n{current_chat['summary']}")

    history_text = format_history(current_chat.get("messages", []))
    if history_text:
        sections.append(f"Recent conversation:\n{history_text}")

    if file_context:
        sections.append(f"Relevant uploaded file context:\n{clip_text(file_context)}")

    if calculator_result:
        sections.append(f"Calculator result:\n{calculator_result}")

    if search_context:
        sections.append(
            "Current web search evidence:\n"
            f"{search_context}\n\n"
            "Web-grounding rules:\n"
            "- Live web evidence was retrieved for this answer. Do not say that you do not have real-time access.\n"
            "- Answer directly first, then give concise key points.\n"
            "- Use primary sources for important current claims when supplied, and confirm material claims across sources when possible.\n"
            "- Merge duplicate facts rather than repeating similar source snippets.\n"
            "- If sources conflict or a claim is not sufficiently supported, state the uncertainty clearly.\n"
            "- Cite supporting claims with [1], [2], and so on, matching the numbered sources.\n"
            "- Do not paste raw snippets. The UI shows source links separately."
        )
    elif (
        research.get("requiresFreshInfo")
        or research.get("used")
        or research.get("coverage") == "search_disabled"
    ):
        attempted_queries = research.get("queriesTried") if research.get("searchAttempted") else []
        searched_text = "; ".join(attempted_queries)
        failure_detail = research.get("failureReason") or "No grounded web evidence is available."
        verification_detail = (
            f"Search attempted: {searched_text}.\nMissing evidence: {failure_detail}"
            if searched_text
            else f"No live search was performed. {failure_detail}"
        )
        sections.append(
            "Web verification unavailable:\n"
            f"{verification_detail}\n"
            "The user's request may depend on changed information. Do not confidently claim a latest/current "
            "fact from memory. Briefly tell the user what could not be verified and why; do not claim that "
            "FebGuyAI can never access current information."
        )

    sections.append(intent_instruction(intent))
    sections.append(response_quality_profile_instruction((conversation or {}).get("responseProfile")))
    sections.append(response_mode_instruction(response_mode))
    sections.append(answer_mode_instruction(answer_mode))
    sections.append(answer_length_instruction(answer_length))
    sections.append(
        build_anti_repetition_instruction(
            current_chat.get("messages", []),
            user_message,
            conversation,
        )
    )
    sections.append(f"Current user message:\n{user_message}")
    sections.append(
        "Response quality rules:\n"
        "- Start with the direct answer.\n"
        "- Keep the tone professional, friendly, and human.\n"
        "- Use enough detail to solve the user's real problem, but avoid padding.\n"
        "- Do not expose hidden chain-of-thought; give concise reasoning or steps only when helpful.\n"
        "- If document context is relevant, use it before general knowledge.\n"
        "- If search evidence is weak or unavailable, say what is uncertain.\n"
        "- For quiz/flashcard/note requests, produce that study tool directly instead of a generic explanation.\n"
        "- Do not add a 'Next steps' section to greetings, thanks, casual chat, identity answers, or simple factual answers.\n"
        "- If the task has a practical outcome, end with a short 'Next steps' section only when it truly helps.\n"
        "- Do not force sections named Summary, Key points, or Conclusion unless the user asks for them or the format clearly helps.\n"
        "- Use clean Markdown: proper `1.`, `2.`, `3.` numbering, `-` bullets, and indented `  -` sub-points.\n"
        "- Do not use malformed numbering like `0.` and do not overuse `###` headings or `**bold**` on every item.\n"
        "- Do not output decorative separators such as `---`, `====`, or template marker lines.\n"
        "- Avoid openings like 'It seems like...' and 'It sounds like...' when you can answer directly.\n"
        "- Avoid repeated greetings and filler."
    )

    return "\n\n".join(section for section in sections if section)


CODE_SYSTEM_PROMPT = """
You are FebGuy Code Studio, a focused coding assistant created by Pranav Amble.

Your job:
- Help users write, debug, explain, convert, and improve code.
- Support Python, C, C++, JavaScript, Java, HTML/CSS, SQL, Bash, and other common languages.
- Detect the language and task from the user's prompt automatically.
- Do not execute code. You can explain how to run it only when useful or when the user asks.
- Use attached Code Studio project files together when they are provided in the current code chat.
- Keep project context scoped to the current Code Studio chat. Never assume files from another chat are available.

Style:
- Friendly but professional.
- Be practical and specific.
- Ask one short clarifying question only when the request cannot be answered safely.
- Use fenced code blocks with the right language label.
- Use clean formatting: short section labels, proper numbered steps, bullets, and indented sub-points.
- Do not overuse `###` headings or bold every line.
- For debugging, explain the likely cause first, then provide the fixed code or exact change.
- For writing code, give the clean solution first, then a short explanation.
- For requested fixes/refactors, prefer a readable diff-style section with file name, removed lines, added lines, and a short explanation when possible.
- For tests, suggest the obvious framework when clear, such as pytest for Python or Vitest/Jest for JavaScript/React, and explain how to run the tests without claiming you ran them.
- For pasted compiler/runtime errors, explain what the error means, the likely cause, exact fix steps, and the affected file if clear.
- For README/setup requests, include project overview, install steps, environment variable placeholders, run commands, folder structure, and testing instructions. Never include real secrets.
- Avoid long theory unless the user asks for learning detail.
- If the latest message is only thanks, ok, yes/no, or a greeting, answer briefly as a conversation and do not repeat code or run steps.
- Avoid canned closings like "ready for your next task"; respond naturally to the user's exact message.
""".strip()


CODE_LANGUAGE_PATTERNS = [
    ("python", ["python", ".py", "py script", "django", "flask", "fastapi"]),
    ("c", [" c ", " c program", ".c", "stdio", "scanf", "printf"]),
    ("cpp", ["c++", "cpp", ".cpp", "iostream", "std::"]),
    ("javascript", ["javascript", "js", ".js", "node", "react"]),
    ("typescript", ["typescript", "ts", ".ts"]),
    ("java", ["java", ".java", "spring boot"]),
    ("html", ["html", "website", "web page"]),
    ("css", ["css", "style", "responsive"]),
    ("sql", ["sql", "sqlite", "mysql", "postgres"]),
    ("bash", ["bash", "shell", "powershell", "command line"]),
]


def detect_code_language(message: str) -> str:
    text = f" {message.lower()} "
    for language, patterns in CODE_LANGUAGE_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return language
    return "auto"


def detect_code_task(message: str) -> str:
    text = message.lower()
    if get_code_conversation_reply(message):
        return "conversation"
    if any(word in text for word in ["readme", "setup instructions", "documentation", "install guide"]):
        return "readme"
    if any(word in text for word in ["diff", "patch", "show changes", "what changed"]):
        return "diff"
    if any(word in text for word in ["debug", "fix", "error", "traceback", "exception", "bug", "not working"]):
        return "debug"
    if any(word in text for word in ["explain", "what does", "understand", "meaning"]):
        return "explain"
    if any(word in text for word in ["convert", "translate", "rewrite in", "port this"]):
        return "convert"
    if any(word in text for word in ["optimize", "faster", "performance", "clean up", "refactor", "improve"]):
        return "optimize"
    if any(word in text for word in ["test", "unit test", "pytest", "unittest"]):
        return "test"
    return "write"


CODE_REQUEST_WORDS = {
    "write",
    "create",
    "make",
    "build",
    "debug",
    "fix",
    "error",
    "code",
    "program",
    "script",
    "function",
    "class",
    "convert",
    "optimize",
    "refactor",
    "explain",
    "test",
    "tests",
    "readme",
    "diff",
    "patch",
}


def get_code_conversation_reply(message: str) -> str | None:
    normalized = re.sub(r"[^a-zA-Z0-9\s]+", " ", message.lower()).strip()
    words = normalized.split()

    if not words or len(words) > 6:
        return None

    if any(word in CODE_REQUEST_WORDS for word in words):
        return None

    thanks_words = {"thanks", "thank", "thankyou", "ty", "appreciate"}
    ok_words = {"ok", "okay", "fine", "cool", "great", "nice", "done", "got", "understood"}
    praise_words = {"good", "awesome", "amazing", "perfect", "excellent", "useful", "helpful", "love", "liked"}
    greeting_words = {"hi", "hello", "hey", "yo"}
    yes_no_words = {"yes", "yeah", "yep", "no", "nope"}

    if any(word in thanks_words for word in words):
        return "You're welcome. Send the next code problem whenever you want."

    if any(word in praise_words for word in words):
        return "Glad it helped. What should we improve or build next?"

    if all(word in ok_words or word == "it" for word in words):
        return "Got it."

    if any(word in greeting_words for word in words):
        return "Hi. Tell me what you want to build, debug, explain, convert, or optimize."

    if all(word in yes_no_words for word in words):
        return "Got it. Share the exact coding change or question when you are ready."

    return None


def code_clarification_response(message: str, task: str, has_project_context: bool = False) -> str | None:
    text = message.strip()
    lower = text.lower()
    has_code_block = "```" in text or bool(re.search(r"\b(def|class|#include|function|const|let|var|public static|SELECT|import)\b", text))
    has_error = any(term in lower for term in ["error", "traceback", "exception", "failed", "not working"])

    if has_project_context:
        return None

    if task == "debug" and not (has_code_block or has_error):
        return (
            "Send me the code and the exact error message first. "
            "Then I can point out the cause and give you the corrected version."
        )

    if task in {"convert", "optimize", "explain"} and not has_code_block and len(text.split()) < 8:
        return "Paste the code or describe the exact file/function you want me to work on."

    return None


def build_code_prompt(
    user_message: str,
    current_chat: dict[str, Any],
    profile: dict[str, Any],
    answer_length: str = "standard",
    project_context: str = "",
) -> tuple[str, str, str]:
    language = detect_code_language(user_message)
    task = detect_code_task(user_message)
    history_text = format_history(current_chat.get("messages", []), limit=8)
    sections = [
        CODE_SYSTEM_PROMPT,
        f"User profile name: {profile.get('name', 'User')}",
        f"Detected coding task: {task}",
        f"Detected language: {language}",
    ]
    if current_chat.get("summary"):
        sections.append(f"Compressed Code Studio memory:\n{current_chat['summary']}")
    if history_text:
        sections.append(f"Recent Code Studio conversation:\n{history_text}")
    if project_context:
        sections.append(project_context)
    sections.append(answer_length_instruction(answer_length))
    sections.append(f"Current user request:\n{user_message}")
    sections.append(
        "Response rules:\n"
        "- Start with the useful answer, not a long introduction.\n"
        "- If code is needed, put it in a fenced code block with a language label.\n"
        "- Keep explanations short and practical.\n"
        "- Include run/setup steps only when the prompt asks for them or the answer cannot be used without them.\n"
        "- Do not repeat previous code, setup steps, or explanations when the user only says thanks, ok, yes/no, or a greeting.\n"
        "- If the user provides an error, identify the likely cause and the exact fix.\n"
        "- If the user asks for a fix/change and project files are available, show a clean diff when practical:\n"
        "  File: path/name.ext\n"
        "  Removed:\n"
        "  - old line or block\n"
        "  Added:\n"
        "  + new line or block\n"
        "  Explanation: one or two sentences.\n"
        "- If the user asks for tests, produce test code plus how to run it. Do not execute tests.\n"
        "- If the user asks to convert code, give converted code and mention limitations or non-equivalent behavior.\n"
        "- If the user asks for README/setup, generate safe placeholder env names, never real secrets.\n"
        "- Never show hidden reasoning, analysis notes, or <think>...</think> blocks.\n"
        "- Use clean Markdown: proper `1.`, `2.`, `3.` numbering, `-` bullets, and indented sub-points.\n"
        "- Do not use malformed numbering like `0.` and do not overuse heading markers or bold labels.\n"
        "- Do not claim that code was executed or tested locally."
    )
    return "\n\n".join(sections), task, language


def summarize_code_chat(old_summary: str, messages: list[dict[str, Any]]) -> str:
    if len(messages) < 6:
        return old_summary

    recent_text = format_history(messages, limit=12)
    prompt = f"""
Create a short memory summary for this Code Studio chat.
Keep the programming language, task, project details, errors, decisions, and unfinished TODOs.

Previous summary:
{old_summary}

Recent messages:
{recent_text}

Code Studio summary:
""".strip()

    return clip_text(call_text_model(prompt, model=CODE_MODEL), 1200)


def friendly_api_error(provider: str, exc: Exception | None = None, response: requests.Response | None = None) -> str:
    provider_name = provider.capitalize()

    if response is not None:
        message = ""
        try:
            payload = response.json()
            error_payload = payload.get("error", payload)
            if isinstance(error_payload, dict):
                message = str(error_payload.get("message") or error_payload.get("detail") or "")
            else:
                message = str(error_payload)
        except Exception:
            message = response.text[:300]

        status = response.status_code
        lowered = message.lower()
        if status == 401:
            return f"{provider_name} API authentication failed. Check the backend .env API key."
        if status == 413 or "request entity too large" in lowered or "payload too large" in lowered or "too large" in lowered:
            return (
                f"{provider_name} API request was too large. The selected file or context is too large. "
                "Please attach fewer files, use a smaller file, or ask about one document at a time."
            )
        if status == 429:
            return f"{provider_name} API rate limit reached. Please wait a moment and try again."
        if status in {400, 404} and "model" in lowered:
            return f"{provider_name} API rejected the model name. Check the model setting in backend .env."
        if message:
            return f"{provider_name} API error: {clip_text(message, 260)}"
        return f"{provider_name} API request failed with status {status}."

    if isinstance(exc, requests.Timeout):
        return f"{provider_name} API timed out. Please try again."
    if isinstance(exc, requests.ConnectionError):
        return f"Could not connect to {provider_name} API. Check internet connection and backend network access."
    if exc is not None:
        return f"{provider_name} API failed: {clip_text(str(exc), 260)}"
    return f"{provider_name} API failed."


def groq_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


MODEL_OUTPUT_RULES = (
    "Return only the final helpful answer. Do not reveal hidden reasoning, chain-of-thought, "
    "analysis notes, or <think> blocks. If you need to reason, keep it private and answer clearly. "
    "Do not include decorative separators, forced summary templates, or repeated default next-step sections. "
    "Start directly instead of using filler like 'It seems like' when the answer is clear."
)


def clean_model_output(text: str) -> str:
    cleaned = re.sub(r"<think\b[^>]*>[\s\S]*?</think>", "", str(text or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"</?think\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<analysis\b[^>]*>[\s\S]*?</analysis>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?(analysis|final)\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"[-=_*]{3,}", stripped):
            continue
        lines.append(line.rstrip())
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def without_thinking_stream(chunks: Iterable[str]) -> Iterable[str]:
    buffer = ""
    inside_thinking = False
    open_tag = "<think>"
    close_tag = "</think>"

    for chunk in chunks:
        buffer += chunk

        while buffer:
            lowered = buffer.lower()

            if inside_thinking:
                close_index = lowered.find(close_tag)
                if close_index == -1:
                    buffer = buffer[-(len(close_tag) - 1) :]
                    break
                buffer = buffer[close_index + len(close_tag) :]
                inside_thinking = False
                continue

            open_index = lowered.find(open_tag)
            if open_index == -1:
                hold = 0
                for tail_length in range(min(len(open_tag) - 1, len(buffer)), 0, -1):
                    if open_tag.startswith(buffer[-tail_length:].lower()):
                        hold = tail_length
                        break

                emit_length = len(buffer) - hold
                if emit_length > 0:
                    yield buffer[:emit_length]
                    buffer = buffer[emit_length:]
                break

            if open_index > 0:
                yield buffer[:open_index]
            buffer = buffer[open_index + len(open_tag) :]
            inside_thinking = True

    if buffer and not inside_thinking:
        cleaned = clean_model_output(buffer)
        if cleaned:
            yield cleaned


def vision_model_candidates() -> list[str]:
    candidates = [
        VISION_MODEL,
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]
    unique: list[str] = []
    for model in candidates:
        clean = str(model or "").replace("models/", "").strip()
        if clean and clean not in unique:
            unique.append(clean)
    return unique


def apply_reasoning_controls(payload: dict[str, Any], model: str) -> None:
    if "qwen3" in str(model or "").lower():
        payload["reasoning_format"] = "hidden"


def groq_chat_completion(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.65,
    timeout: tuple[int, int] = (8, 180),
) -> str:
    if not GROQ_API_KEY:
        return "Groq API key is missing. Add GROQ_API_KEY to backend .env and restart the backend."

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": MODEL_OUTPUT_RULES},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "top_p": 0.9,
        "stream": False,
    }
    apply_reasoning_controls(payload, model)

    try:
        response = requests.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=groq_headers(),
            json=payload,
            timeout=timeout,
        )
        if not response.ok:
            return friendly_api_error("groq", response=response)
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return "Groq API returned no response choices."
        return clean_model_output(choices[0].get("message", {}).get("content") or "")
    except Exception as exc:
        return friendly_api_error("groq", exc=exc)


def stream_groq_chat_completion(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.65,
) -> Iterable[str]:
    if not GROQ_API_KEY:
        yield "Groq API key is missing. Add GROQ_API_KEY to backend .env and restart the backend."
        return

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": MODEL_OUTPUT_RULES},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "top_p": 0.9,
        "stream": True,
    }
    apply_reasoning_controls(payload, model)

    try:
        with requests.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=groq_headers(),
            json=payload,
            stream=True,
            timeout=(8, 300),
        ) as response:
            if not response.ok:
                yield friendly_api_error("groq", response=response)
                return

            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                chunk = delta.get("content") or ""
                if chunk:
                    yield chunk
    except Exception as exc:
        yield friendly_api_error("groq", exc=exc)


def normalize_image_payloads(images: list[Any] | None) -> list[dict[str, str]]:
    normalized = []
    for item in images or []:
        if isinstance(item, dict):
            data = item.get("data") or item.get("base64") or ""
            mime_type = item.get("mime_type") or item.get("mimeType") or "image/png"
        else:
            data = str(item or "")
            mime_type = "image/png"
        if data:
            normalized.append({"data": data, "mime_type": mime_type})
    return normalized


def groq_vision_completion(prompt: str, image_parts: list[dict[str, str]]) -> str:
    if not GROQ_API_KEY:
        return "Vision is unavailable because Gemini quota is exhausted and GROQ_API_KEY is missing."
    if not image_parts:
        return groq_chat_completion(prompt, model=DEFAULT_MODEL)

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image in image_parts[:4]:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image['mime_type']};base64,{image['data']}",
                },
            }
        )

    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": [
            {"role": "system", "content": MODEL_OUTPUT_RULES},
            {"role": "user", "content": content},
        ],
        "temperature": 0.35,
        "top_p": 0.9,
        "stream": False,
    }

    try:
        response = requests.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=groq_headers(),
            json=payload,
            timeout=(8, 180),
        )
        if not response.ok:
            return friendly_api_error("groq", response=response)
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return "Groq vision returned no response choices."
        return clean_model_output(choices[0].get("message", {}).get("content") or "")
    except Exception as exc:
        return friendly_api_error("groq", exc=exc)


def call_gemini_vision(prompt: str, images: list[Any] | None = None) -> str:
    image_parts = normalize_image_payloads(images)
    if not image_parts:
        return groq_chat_completion(prompt, model=DEFAULT_MODEL)
    if not GEMINI_API_KEY:
        return groq_vision_completion(prompt, image_parts)

    parts: list[dict[str, Any]] = [{"text": prompt}]
    for image in image_parts:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image["mime_type"],
                    "data": image["data"],
                }
            }
        )

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.45, "topP": 0.9},
    }

    last_error = ""
    for model in vision_model_candidates():
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=(8, 180),
            )
            if not response.ok:
                last_error = friendly_api_error("gemini", response=response)
                lowered_error = last_error.lower()
                if response.status_code == 429 or "quota" in lowered_error or "rate limit" in lowered_error:
                    fallback = groq_vision_completion(prompt, image_parts)
                    if not fallback.lower().startswith("groq api"):
                        return fallback
                    return (
                        "Gemini API rate limit reached. Please wait a moment and try again. "
                        "If this was an image question, try a smaller image or fewer uploads."
                    )
                if response.status_code in {400, 404} and ("model" in lowered_error or "not found" in lowered_error):
                    continue
                return last_error

            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return "Gemini vision returned no response."
            parts = candidates[0].get("content", {}).get("parts") or []
            text = clean_model_output("".join(part.get("text", "") for part in parts))
            return text or "Gemini vision returned an empty response."
        except Exception as exc:
            last_error = friendly_api_error("gemini", exc=exc)
            return last_error

    return last_error or "Gemini vision failed. Set VISION_MODEL=gemini-2.0-flash in backend .env."


def call_text_model(
    prompt: str,
    model: str = DEFAULT_MODEL,
    images: list[Any] | None = None,
    allow_image_fallback: bool = True,
) -> str:
    started_at = time.perf_counter()
    try:
        if images:
            return call_gemini_vision(prompt, images)
        return clean_model_output(groq_chat_completion(prompt, model=model))
    finally:
        add_request_ai_time(time.perf_counter() - started_at)


def build_response_refiner_prompt(
    original_response: str,
    user_message: str,
    response_mode: str,
    emotional_tone: dict[str, Any] | None,
    intent: str,
) -> str:
    mode = normalize_response_mode(response_mode)
    tone = emotional_tone or {}
    tone_label = str(tone.get("tone") or "neutral")
    tone_instruction = str(tone.get("instruction") or "")
    return (
        "You are a conservative response polish pass for FebGuyAI.\n"
        "Improve only clarity, naturalness, structure, and repetition. Preserve meaning.\n\n"
        "Hard preservation rules:\n"
        "- Preserve every factual claim unless the original is internally contradictory.\n"
        "- Preserve all code blocks exactly, including indentation, language tags, comments, and commands.\n"
        "- Preserve citations like [1], [2], source links, file names, page references, and download/file links.\n"
        "- Preserve calculator, weather, tool, OCR, document, and search results exactly.\n"
        "- Preserve Markdown structure when it is already useful; only clean malformed or robotic wording.\n"
        "- Do not add new facts, citations, links, files, examples, or promises.\n"
        "- Do not remove safety warnings or uncertainty statements.\n"
        "- Do not expose hidden reasoning.\n\n"
        "Style guidance:\n"
        f"- Response mode: {mode}. {RESPONSE_MODE_INSTRUCTIONS[mode]}\n"
        f"- Intent: {intent or 'general'}\n"
        f"- Emotional tone: {tone_label}\n"
        f"- Tone instruction: {tone_instruction or 'Stay natural, professional, and concise.'}\n"
        "- Avoid repeated openings like 'Sure' and generic endings like 'Let me know'.\n"
        "- Do not force a Next steps section for casual or simple answers.\n"
        "- Return only the improved final answer, no commentary about the rewrite.\n\n"
        f"User message:\n{user_message}\n\n"
        f"Original FebGuyAI response:\n{original_response}"
    )


def response_refiner_error(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return bool(
        lowered.startswith("groq api")
        or lowered.startswith("gemini api")
        or "api key" in lowered
        or "rate limit" in lowered
        or "request entity too large" in lowered
    )


def refine_response_if_enabled(
    original_response: str,
    user_message: str,
    response_mode: str,
    emotional_tone: dict[str, Any] | None,
    intent: str,
) -> str:
    if not ENABLE_RESPONSE_REFINER:
        return original_response
    original = (original_response or "").strip()
    if not original or response_refiner_error(original):
        return original_response
    try:
        prompt = build_response_refiner_prompt(
            original,
            user_message,
            response_mode,
            emotional_tone,
            intent,
        )
        refined = clean_model_output(groq_chat_completion(prompt, model=RESPONSE_REFINER_MODEL)).strip()
        if not refined or response_refiner_error(refined):
            return original_response
        return refined
    except Exception:
        return original_response


def stream_text_model(
    prompt: str,
    model: str = DEFAULT_MODEL,
    images: list[Any] | None = None,
    allow_image_fallback: bool = True,
) -> Iterable[str]:
    started_at = time.perf_counter()
    try:
        if images:
            yield call_gemini_vision(prompt, images)
            return
        yield from without_thinking_stream(stream_groq_chat_completion(prompt, model=model))
    finally:
        add_request_ai_time(time.perf_counter() - started_at)


def model_status() -> dict[str, Any]:
    return {
        "provider": "online",
        "groq_ok": bool(GROQ_API_KEY),
        "gemini_ok": bool(GEMINI_API_KEY),
        "groq_vision_model": GROQ_VISION_MODEL,
        "stt_provider": STT_PROVIDER,
        "tts_provider": TTS_PROVIDER,
        "available_models": [
            DEFAULT_MODEL,
            FAST_MODEL,
            SMART_MODEL,
            DEEP_MODEL,
            CODE_MODEL,
            VISION_MODEL,
            GROQ_VISION_MODEL,
            STT_MODEL,
        ],
        "default_model_ready": bool(GROQ_API_KEY and DEFAULT_MODEL),
        "fast_model_ready": bool(GROQ_API_KEY and FAST_MODEL),
        "smart_model_ready": bool(GROQ_API_KEY and SMART_MODEL),
        "deep_model_ready": bool(GROQ_API_KEY and DEEP_MODEL),
        "code_model_ready": bool(GROQ_API_KEY and CODE_MODEL),
        "vision_model_ready": bool(GEMINI_API_KEY and VISION_MODEL),
    }


def transcribe_audio_with_groq(
    audio_bytes: bytes,
    filename: str = "voice.webm",
    content_type: str = "audio/webm",
) -> str:
    if STT_PROVIDER != "groq":
        raise HTTPException(status_code=400, detail="Unsupported STT provider. Set STT_PROVIDER=groq.")
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Groq API key is missing. Add GROQ_API_KEY to backend .env and restart the backend.",
        )
    if not audio_bytes or len(audio_bytes) < 512:
        raise HTTPException(status_code=400, detail="No audio detected. Please try speaking again.")

    try:
        response = requests.post(
            f"{GROQ_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            data={"model": STT_MODEL, "response_format": "json"},
            files={"file": (Path(filename or "voice.webm").name, io.BytesIO(audio_bytes), content_type or "audio/webm")},
            timeout=(8, 120),
        )
        if not response.ok:
            status = 429 if response.status_code == 429 else 502
            raise HTTPException(status_code=status, detail=friendly_api_error("groq", response=response))
        transcript = (response.json().get("text") or "").strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="No speech was detected in the audio.")
        return transcript
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=friendly_api_error("groq", exc=exc))


def create_database_backup(reason: str = "manual") -> dict[str, Any]:
    if not DATABASE.is_sqlite_active():
        raise HTTPException(
            status_code=400,
            detail="Database backups are only available when DATABASE_PROVIDER=sqlite.",
        )
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"febguy-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{reason}.db"
    with DATA_LOCK:
        with sqlite3.connect(DATABASE_FILE) as source:
            with sqlite3.connect(backup_path) as target:
                source.backup(target)
    return {"path": str(backup_path), "created_at": now_iso(), "reason": reason}


def summarize_chat(old_summary: str, messages: list[dict[str, Any]]) -> str:
    if len(messages) < 6:
        return old_summary

    recent_text = format_history(messages, limit=12)
    prompt = f"""
Create a short compressed memory summary for this chat.
Keep durable facts, user goals, file topics, decisions, and open tasks.
Do not include minor chatter.

Previous summary:
{old_summary}

Recent messages:
{recent_text}

Compressed summary:
""".strip()

    return clip_text(call_text_model(prompt), 1200)


def create_title_from_message(message: str) -> str:
    prompt = f"""
Create a short chat title under 5 words for this message.
Only return the title.

Message:
{message}
""".strip()
    title = call_text_model(prompt).strip().strip('"')
    return title[:40] if title else "New Chat"


def create_fast_title_from_message(message: str) -> str:
    title = re.sub(r"\s+", " ", message).strip(" ?.!")[:40]
    return title.title() if title else "New Chat"


def stream_timing_metrics() -> dict[str, Any]:
    return {
        "started_at": time.perf_counter(),
        "prepare_ms": 0.0,
        "context_ms": 0.0,
        "db_ms": 0.0,
        "ai_first_token_ms": None,
        "ai_total_ms": 0.0,
        "persist_ms": 0.0,
    }


def mark_stream_first_token(metrics: dict[str, Any]) -> None:
    if metrics.get("ai_first_token_ms") is None:
        metrics["ai_first_token_ms"] = elapsed_ms(metrics["started_at"])


def current_stream_db_ms() -> float:
    request_id = REQUEST_TIMING_ID.get()
    if request_id:
        with REQUEST_TIMING_LOCK:
            totals = REQUEST_TIMING_TOTALS.get(request_id)
            if totals is not None:
                return float(totals.get("db") or 0.0) * 1000
    return REQUEST_DB_TIME.get() * 1000


def capture_stream_db_ms(metrics: dict[str, Any]) -> None:
    metrics["db_ms"] = max(
        float(metrics.get("db_ms") or 0.0),
        current_stream_db_ms(),
    )


def finish_stream_persistence(metrics: dict[str, Any], persist_started: float) -> None:
    metrics["persist_ms"] = elapsed_ms(persist_started)
    metrics["db_ms"] = float(metrics.get("db_ms") or 0.0) + current_stream_db_ms()


def start_stream_persistence_thread(metrics: dict[str, Any], target: Callable[[], None]) -> None:
    capture_stream_db_ms(metrics)
    threading.Thread(target=target, daemon=True).start()


def log_stream_timing(endpoint: str, metrics: dict[str, Any]) -> None:
    first_token = metrics.get("ai_first_token_ms")
    db_ms = max(float(metrics.get("db_ms") or 0.0), current_stream_db_ms())
    LOGGER.info(
        (
            "stream_timing endpoint=%s prepare_ms=%.1f context_ms=%.1f "
            "db_ms=%.1f ai_first_token_ms=%s ai_total_ms=%.1f "
            "persist_ms=%.1f total_ms=%.1f"
        ),
        endpoint,
        float(metrics.get("prepare_ms") or 0.0),
        float(metrics.get("context_ms") or 0.0),
        db_ms,
        f"{float(first_token):.1f}" if first_token is not None else "n/a",
        float(metrics.get("ai_total_ms") or 0.0),
        float(metrics.get("persist_ms") or 0.0),
        elapsed_ms(metrics["started_at"]),
    )


def persist_ai_response(
    profile_id: str,
    chats: list[dict[str, Any]],
    current_chat: dict[str, Any],
    user_message: str,
    ai_response: str,
    citations: list[dict[str, str]] | None = None,
    document_hits: list[dict[str, Any]] | None = None,
    suggestions: list[str] | None = None,
    use_llm_title: bool = True,
    update_summary: bool = True,
    reload_metadata: bool = True,
) -> list[dict[str, Any]]:
    ai_response = clean_model_output(ai_response)
    current_chat["messages"].append(
        {
            "role": "assistant",
            "text": ai_response,
            "citations": citations or [],
            "documentHits": public_document_hits(document_hits),
            "suggestions": clean_suggestions(suggestions),
        }
    )

    if len(current_chat["messages"]) == 2 and current_chat["title"] == "New Chat":
        current_chat["title"] = (
            create_title_from_message(user_message)
            if use_llm_title
            else create_fast_title_from_message(user_message)
        )

    if update_summary:
        current_chat["summary"] = summarize_chat(
            current_chat.get("summary", ""),
            current_chat["messages"],
        )

    return save_current_chat(profile_id, chats, current_chat, reload_metadata=reload_metadata)


def persist_code_response(
    profile_id: str,
    chats: list[dict[str, Any]],
    current_chat: dict[str, Any],
    user_message: str,
    ai_response: str,
    task: str,
    language: str,
    project_files: list[dict[str, Any]] | None = None,
    generated_files: list[dict[str, Any]] | None = None,
    reload_metadata: bool = True,
) -> list[dict[str, Any]]:
    ai_response = clean_model_output(ai_response)
    current_chat["messages"].append(
        {
            "role": "assistant",
            "text": ai_response,
            "codeTask": task,
            "codeLanguage": language,
            "projectFiles": project_files or [],
            "generatedFiles": generated_files or [],
        }
    )

    if len(current_chat["messages"]) == 2 and current_chat["title"] in {"New Chat", "New Code Chat"}:
        current_chat["title"] = create_fast_title_from_message(user_message)

    current_chat["summary"] = summarize_code_chat(
        current_chat.get("summary", ""),
        current_chat["messages"],
    )
    return save_current_code_chat(profile_id, chats, current_chat, reload_metadata=reload_metadata)


def append_user_message(
    current_chat: dict[str, Any],
    user_message: str,
    uploaded_file: dict[str, Any] | None,
) -> None:
    current_chat["messages"].append(
        {
            "role": "user",
            "text": user_message,
            "fileName": uploaded_file.get("name") if uploaded_file else None,
            "fileType": uploaded_file.get("type") if uploaded_file else None,
        }
    )


def remove_latest_turn_for_retry(current_chat: dict[str, Any]) -> None:
    """Remove only the most recent user/assistant turn before an explicit retry."""
    messages = current_chat.get("messages", [])
    if messages and normalize_message_role(messages[-1].get("role")) == "assistant":
        messages.pop()
    if messages and messages[-1].get("role") == "user":
        messages.pop()


def save_document_response(
    profile_id: str,
    chats: list[dict[str, Any]],
    current_chat: dict[str, Any],
    user_message: str,
    uploaded_file: dict[str, Any] | None,
    document_result: dict[str, Any],
) -> dict[str, Any]:
    append_user_message(current_chat, user_message, uploaded_file)

    if document_result.get("success"):
        current_chat["messages"].append(
            {
                "role": "assistant",
                "text": document_result.get("message", "File converted successfully."),
                "fileResult": True,
                "fileName": document_result.get("file_name"),
                "downloadUrl": document_result.get("download_url"),
            }
        )
        save_current_chat(profile_id, chats, current_chat)
        return {
            "type": "file",
            "message": document_result.get("message", "File converted successfully."),
            "download_url": document_result.get("download_url"),
            "file_name": document_result.get("file_name"),
        }

    error_message = document_result.get("message", "Document tool failed.")
    current_chat["messages"].append({"role": "assistant", "text": error_message})
    save_current_chat(profile_id, chats, current_chat)
    return {"response": error_message}


def save_document_not_available_response(
    profile_id: str,
    chats: list[dict[str, Any]],
    current_chat: dict[str, Any],
    user_message: str,
    uploaded_file: dict[str, Any] | None,
    response_text: str,
) -> dict[str, Any]:
    append_user_message(current_chat, user_message, uploaded_file)
    saved_chats = persist_ai_response(
        profile_id,
        chats,
        current_chat,
        user_message,
        response_text,
        suggestions=[],
        use_llm_title=False,
        update_summary=False,
    )
    return {
        "response": response_text,
        "chat": public_chat_payload(current_chat),
        "chats": saved_chats,
        "searchUsed": False,
        "citations": [],
        "documentHits": [],
        "intent": "document_missing",
        "answerMode": "direct",
        "route": {"tool": "document", "answerMode": "direct"},
        "research": {"used": False, "coverage": "document_missing", "sourceCount": 0, "grounded": False},
        "suggestions": [],
    }


async def prepare_chat(
    profile: dict[str, Any],
    chat_id: str,
    message: str,
    file: UploadFile | None,
    validated_upload: tuple[str, str, bytes] | None = None,
    replace_last_turn: bool = False,
    metrics: dict[str, Any] | None = None,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    str,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
    str,
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, Any]],
    str,
    dict[str, Any],
]:
    profile_id = profile["id"]
    scope = ownership_scope_from_profile(profile)
    message_limit = None if replace_last_turn else STREAM_CHAT_CONTEXT_MESSAGES
    current_chat = load_chat_by_id(profile_id, chat_id, scope, message_limit=message_limit)
    chats = [current_chat]
    user_message = (message or "").strip()
    settings = load_settings(profile_id, scope)

    if replace_last_turn:
        remove_latest_turn_for_retry(current_chat)

    if not user_message and file:
        user_message = "Please analyze this file."

    if not user_message:
        user_message = "Hello"

    memory = update_memory_from_message(profile_id, user_message, scope)
    uploaded_file = None

    if file:
        uploaded_file = await save_uploaded_file(
            file,
            profile_id,
            chat_id,
            validated_upload,
        )
        current_chat["last_uploaded_file"] = uploaded_file
        log_activity_async(
            profile_id,
            "file_uploaded",
            {
                "fileName": uploaded_file.get("name"),
                "chunks": len(uploaded_file.get("chunks", [])),
                "usedOcr": bool(uploaded_file.get("used_ocr")),
            },
        )

    context_started = time.perf_counter()
    active_file = current_chat.get("last_uploaded_file")
    document_result = None

    if isinstance(active_file, dict):
        document_result = process_document_tool(
            profile_id,
            Path(active_file.get("path", "")),
            active_file.get("name", ""),
            user_message,
        )

    if document_result is not None:
        if metrics is not None:
            metrics["context_ms"] = metrics.get("context_ms", 0.0) + elapsed_ms(context_started)
        return (
            chats,
            current_chat,
            user_message,
            memory,
            settings,
            uploaded_file,
            "",
            [],
            [],
            [],
            "__DOCUMENT_TOOL__" + json.dumps(document_result),
            {"used": False, "coverage": "document_tool", "sourceCount": 0, "grounded": False},
        )

    force_file_context = uploaded_file is not None
    file_context, image_payloads, document_hits = build_file_context_from_chat(
        profile_id,
        current_chat,
        user_message,
        settings,
        force_include=force_file_context,
    )

    search_context, citations, research = prepare_web_research(
        user_message,
        has_file_context=bool(file_context),
        settings=settings,
    )
    if metrics is not None:
        metrics["context_ms"] = metrics.get("context_ms", 0.0) + elapsed_ms(context_started)

    return (
        chats,
        current_chat,
        user_message,
        memory,
        settings,
        uploaded_file,
        file_context,
        image_payloads,
        citations,
        document_hits,
        search_context,
        research,
    )


def export_chat_text(chat_item: dict[str, Any], profile_name: str) -> str:
    lines = [
        f"FebGuy AI Chat Export",
        f"Profile: {profile_name}",
        f"Title: {chat_item.get('title', 'New Chat')}",
        f"Exported: {now_iso()}",
        "",
    ]

    for message in chat_item.get("messages", []):
        role = "User" if message.get("role") == "user" else "FebGuy"
        lines.append(f"{role}: {message.get('text', '')}")

        if message.get("citations"):
            lines.append("Sources:")
            for citation in message["citations"]:
                lines.append(f"- {citation.get('title')}: {citation.get('url')}")

        if message.get("suggestions"):
            lines.append("Follow-ups:")
            for suggestion in clean_suggestions(message["suggestions"]):
                lines.append(f"- {suggestion}")
        lines.append("")

    return "\n".join(lines)


@app.get("/")
def home() -> dict[str, str]:
    return {"message": "FebGuy AI Backend Running"}


@app.get("/health")
def health() -> dict[str, Any]:
    models = model_status()
    database = database_health_status()
    safe_database = {
        "active_provider": database["active_provider"],
        "requested_provider": database["requested_provider"],
        "postgres_configured": bool(database["postgres_configured"]),
        "postgres_connected": bool(database["postgres_connected"]),
        "sqlite_available": bool(database["sqlite_available"]),
    }
    return {
        "ok": True,
        "model": DEFAULT_MODEL,
        "code_model": CODE_MODEL,
        "vision_model": VISION_MODEL,
        "groq_vision_model": GROQ_VISION_MODEL,
        "voice_chat_model": VOICE_CHAT_MODEL,
        "stt_model": STT_MODEL,
        **models,
        "search_available": DDGS is not None,
        "ocr_available": ocr_available(),
        "ocr_python_package_available": pytesseract is not None,
        "tesseract_cmd": TESSERACT_CMD,
        "docx_pdf_available": cloud_docx_to_pdf_available() or local_docx_to_pdf_available(),
        "docx_pdf_mode": "cloud" if cloud_docx_to_pdf_available() else "local-pandoc-prince" if local_docx_to_pdf_available() else "unavailable",
        "pdf_docx_available": True,
        "pdf_docx_mode": "cloud" if cloud_pdf_to_docx_available() else "text-fallback",
        "device_id_support": True,
        "guest_mode_support": True,
        "guest_limits_support": True,
        "account_auth_support": True,
        "supabase_account_session_exchange": True,
        "onboarding_status_support": True,
        "device_bound_profiles_support": True,
        "session_modes_support": True,
        "ownership_enforcement_support": True,
        "secure_file_transfer_support": True,
        "profile_management_security_support": True,
        "api_security_support": True,
        "fresh_web_research_support": True,
        "streaming_responses_support": True,
        "structured_errors_support": True,
        "rate_limiting_support": True,
        "cors_configured": bool(ALLOWED_ORIGINS),
        "max_upload_mb": MAX_UPLOAD_MB,
        "max_request_mb": MAX_REQUEST_MB,
        "storage": safe_database["active_provider"],
        "database_provider": safe_database["active_provider"],
        "requested_database_provider": safe_database["requested_provider"],
        "database": safe_database,
        "postgres": {
            "configured": safe_database["postgres_configured"],
            "connected": safe_database["postgres_connected"],
        },
    }


@app.get("/profiles")
def list_profiles(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    if not authorization:
        # Legacy PIN profiles remain usable by name, but are no longer
        # publicly enumerated on the login screen.
        return {"profiles": [], "legacy_login_enabled": True}

    current_profile = require_account_or_profile_session(authorization)

    user_id = account_owner_id(current_profile)
    if not user_id:
        return {"profiles": [], "legacy_login_enabled": True}

    device_id = getattr(request.state, "device_id", None)
    if not device_id:
        raise HTTPException(status_code=400, detail="A valid device ID is required.")

    profiles = load_device_bound_profiles(user_id, device_id)
    return {
        "profiles": [public_profile(profile) for profile in profiles],
        "legacy_login_enabled": False,
        "device_profile_limit": DEVICE_PROFILE_LIMIT,
    }


@app.post("/guest/start")
def start_guest(
    request: Request,
    x_febguy_device_id: str | None = Header(None, alias=DEVICE_ID_HEADER),
) -> dict[str, Any]:
    device_id = resolve_device_id(
        getattr(request.state, "device_id", None),
        x_febguy_device_id,
    )
    return create_or_load_guest_session(device_id)


@app.get("/guest/limits")
def guest_limits(
    request: Request,
    authorization: str | None = Header(None),
    x_febguy_device_id: str | None = Header(None, alias=DEVICE_ID_HEADER),
) -> dict[str, Any]:
    device_id = resolve_device_id(
        getattr(request.state, "device_id", None),
        x_febguy_device_id,
    )
    profile = require_guest_session(authorization)
    return get_guest_usage_status(profile, device_id)


@app.post("/profiles")
def create_profile(
    data: ProfileCreateRequest,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    name = data.name.strip()
    pin = data.pin.strip()

    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Profile name is too short.")

    if len(pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 characters.")

    current_profile = require_account_or_profile_session(authorization) if authorization else None

    user_id = account_owner_id(current_profile) if current_profile else None
    device_id = getattr(request.state, "device_id", None)
    if user_id and not device_id:
        raise HTTPException(status_code=400, detail="A valid device ID is required.")

    if user_id:
        existing_profiles = load_device_bound_profiles(user_id, device_id)
        if len(existing_profiles) >= DEVICE_PROFILE_LIMIT:
            raise HTTPException(
                status_code=403,
                detail="You can create up to 3 profiles on this device.",
            )
    else:
        existing_profiles = load_profiles_data().get("profiles", [])

    salt = secrets.token_hex(16)
    profile = {
        "id": str(uuid.uuid4()),
        "name": name,
        "pin_salt": salt,
        "pin_hash": hash_pin(pin, salt),
        "profile_kind": "account" if user_id else "legacy",
        "user_id": user_id,
        "device_id": device_id if user_id else None,
        "created_at": now_iso(),
        "last_login_at": now_iso(),
    }

    save_profile(profile)
    ensure_profile_files(
        profile["id"],
        import_legacy=not user_id and len(existing_profiles) == 0,
    )

    token = create_session(
        profile["id"],
        mode="profile",
        device_id=device_id if user_id else None,
    )
    log_activity(
        profile["id"],
        "profile_created",
        {"profile": name, "device_bound": bool(user_id)},
    )
    return {"profile": public_profile(profile), "token": token, "session_mode": "profile"}


@app.post("/profiles/login")
def login_profile(
    data: ProfileLoginRequest,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    enforce_rate_limit(request, "profile_pin")
    current_profile = require_account_or_profile_session(authorization) if authorization else None

    user_id = account_owner_id(current_profile) if current_profile else None
    device_id = getattr(request.state, "device_id", None)

    if user_id:
        if not device_id:
            raise HTTPException(status_code=400, detail="A valid device ID is required.")
        profile = find_profile(data.profile_id or "")
        if (
            not profile
            or profile.get("profile_kind") != "account"
            or profile.get("user_id") != user_id
            or profile.get("device_id") != device_id
        ):
            raise HTTPException(status_code=404, detail=DEVICE_PROFILE_NOT_FOUND)
    else:
        profile = find_legacy_profile_by_name(data.profile_name)
        if not profile and data.profile_id:
            candidate = find_profile(data.profile_id)
            if candidate and candidate.get("profile_kind") == "legacy":
                profile = candidate

    if not profile or profile.get("is_guest") or not verify_pin(profile, data.pin):
        raise HTTPException(status_code=401, detail="Wrong profile or PIN.")

    profile["last_login_at"] = now_iso()
    save_profile(profile)
    ensure_profile_files(profile["id"])
    token = create_session(
        profile["id"],
        mode="profile",
        device_id=device_id if user_id else None,
    )
    log_activity(profile["id"], "profile_login", {})
    return {"profile": public_profile(profile), "token": token, "session_mode": "profile"}


@app.delete("/profiles/current")
def delete_current_profile(
    data: ProfileDeleteRequest,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    enforce_rate_limit(request, "profile_pin")
    profile = require_profile(authorization)
    user_id = profile.get("user_id")
    device_id = getattr(request.state, "device_id", None)

    if (
        not user_id
        or not device_id
        or profile.get("profile_kind") != "account"
        or profile.get("device_id") != device_id
    ):
        raise HTTPException(status_code=403, detail="Only the current signed-in profile can be deleted.")

    if not verify_pin(profile, data.pin):
        raise HTTPException(status_code=401, detail="Wrong PIN. Profile was not deleted.")

    user = find_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Signed-in account no longer exists.")

    account_token = create_account_session(user_id)
    account_profile = account_workspace_profile(user)
    if not account_profile:
        raise HTTPException(status_code=500, detail="Account workspace could not be prepared.")

    profile_id = profile["id"]
    profile_name = profile.get("name", "Profile")
    with DATA_LOCK:
        with db_connect() as conn:
            conn.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
            conn.execute("DELETE FROM profile_pin_reset_codes WHERE profile_id = ?", (profile_id,))
            deleted = conn.execute(
                """
                DELETE FROM profiles
                WHERE id = ?
                    AND profile_kind = 'account'
                    AND user_id = ?
                    AND device_id = ?
                """,
                (profile_id, user_id, device_id),
            ).rowcount

    if not deleted:
        delete_session(account_token)
        raise HTTPException(status_code=404, detail=DEVICE_PROFILE_NOT_FOUND)

    remove_profile_storage(profile_id)
    log_activity(account_profile["id"], "profile_deleted", {"profile": profile_name})
    return {
        "ok": True,
        "profile": public_profile(account_profile),
        "token": account_token,
        "session_mode": "account",
    }


@app.post("/profiles/pin-reset/start")
def start_profile_pin_reset(
    data: ProfilePinResetStartRequest,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    enforce_rate_limit(request, "profile_pin_reset")
    current_profile = require_account_or_profile_session(authorization)
    user_id = account_owner_id(current_profile)
    device_id = getattr(request.state, "device_id", None)
    if not user_id or not device_id:
        raise HTTPException(status_code=403, detail="Sign in on this device to reset a profile PIN.")

    profile = get_owned_device_profile(data.profile_id, user_id, device_id)
    user = find_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Signed-in account no longer exists.")

    require_email_service_configured()
    code = generate_pin_reset_code()
    expires_at = store_profile_pin_reset_code(
        user_id=user_id,
        profile_id=profile["id"],
        device_id=device_id,
        code=code,
    )
    try:
        send_pin_reset_email(
            to_email=user["email"],
            profile_name=profile.get("name", "Profile"),
            code=code,
        )
    except HTTPException:
        invalidate_profile_pin_reset_codes(
            user_id=user_id,
            profile_id=profile["id"],
            device_id=device_id,
        )
        raise

    log_activity(
        user["workspace_profile_id"],
        "profile_pin_reset_started",
        {"profile_id": profile["id"]},
    )

    response: dict[str, Any] = {
        "ok": True,
        "email": user["email"],
        "expires_at": expires_at,
        "expires_in_seconds": PIN_RESET_CODE_TTL_SECONDS,
        "message": f"Verification code sent to {user['email']}.",
        "delivery": "resend",
    }
    return response


@app.post("/profiles/pin-reset/verify")
def verify_profile_pin_reset(
    data: ProfilePinResetVerifyRequest,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    enforce_rate_limit(request, "profile_pin_reset")
    current_profile = require_account_or_profile_session(authorization)
    user_id = account_owner_id(current_profile)
    device_id = getattr(request.state, "device_id", None)
    if not user_id or not device_id:
        raise HTTPException(status_code=403, detail="Sign in on this device to reset a profile PIN.")

    profile = get_owned_device_profile(data.profile_id, user_id, device_id)
    verify_profile_pin_reset_code(
        user_id=user_id,
        profile_id=profile["id"],
        device_id=device_id,
        code=data.code,
    )
    return {"ok": True, "message": "Verification code confirmed."}


@app.post("/profiles/pin-reset/complete")
def complete_profile_pin_reset(
    data: ProfilePinResetCompleteRequest,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    enforce_rate_limit(request, "profile_pin_reset")
    new_pin = data.new_pin.strip()
    if len(new_pin) < 4:
        raise HTTPException(status_code=400, detail="New PIN must be at least 4 characters.")

    current_profile = require_account_or_profile_session(authorization)
    user_id = account_owner_id(current_profile)
    device_id = getattr(request.state, "device_id", None)
    if not user_id or not device_id:
        raise HTTPException(status_code=403, detail="Sign in on this device to reset a profile PIN.")

    profile = get_owned_device_profile(data.profile_id, user_id, device_id)
    user = find_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Signed-in account no longer exists.")
    account_token = create_account_session(user_id)
    account_profile = account_workspace_profile(user)
    if not account_profile:
        delete_session(account_token)
        raise HTTPException(status_code=500, detail="Account workspace could not be prepared.")

    verify_profile_pin_reset_code(
        user_id=user_id,
        profile_id=profile["id"],
        device_id=device_id,
        code=data.code,
        mark_used=True,
    )

    salt = secrets.token_hex(16)
    with DATA_LOCK:
        with db_connect() as conn:
            conn.execute(
                """
                UPDATE profiles
                SET pin_salt = ?, pin_hash = ?
                WHERE id = ?
                    AND profile_kind = 'account'
                    AND user_id = ?
                    AND device_id = ?
                """,
                (salt, hash_pin(new_pin, salt), profile["id"], user_id, device_id),
            )
            conn.execute("DELETE FROM sessions WHERE profile_id = ?", (profile["id"],))

    log_activity(
        user["workspace_profile_id"],
        "profile_pin_reset_completed",
        {"profile_id": profile["id"]},
    )
    return {
        "ok": True,
        "message": "PIN reset successfully. Enter your new PIN to unlock this profile.",
        "profile": public_profile(account_profile),
        "token": account_token,
        "session_mode": "account",
    }


@app.post("/profiles/logout")
def logout_profile(authorization: str | None = Header(None)) -> dict[str, bool]:
    token = parse_bearer_token(authorization)
    delete_session(token)
    return {"ok": True}


@app.get("/me")
def get_me(authorization: str | None = Header(None)):
    context = get_session_context(authorization)
    return {
        "profile": public_profile(context["profile"]),
        "session_mode": context["mode"],
    }


@app.post("/auth/supabase/session")
def create_supabase_account_session(data: AccountSessionRequest, request: Request) -> dict[str, Any]:
    enforce_rate_limit(request, "login")
    identity = verify_supabase_access_token(data.access_token)
    user = create_or_update_account_user(identity)
    profile = account_workspace_profile(user)
    if not profile:
        raise HTTPException(status_code=500, detail="Account workspace could not be prepared.")

    token = create_account_session(user["id"])
    log_activity(profile["id"], "account_session_started", {"provider": user["provider"]})
    return {"profile": public_profile(profile), "token": token, "session_mode": "account"}


@app.get("/onboarding/status")
def onboarding_status(authorization: str | None = Header(None)) -> dict[str, Any]:
    current_profile = require_account_or_profile_session(authorization)
    if current_profile.get("auth_mode") != "account":
        return {
            "mode": "guest" if current_profile.get("is_guest") else "profile",
            "available": False,
            "onboarding_completed": False,
        }

    return {
        "mode": "account",
        "available": True,
        "onboarding_completed": bool(
            current_profile["account_user"]["onboarding_completed"]
        ),
    }


@app.post("/onboarding/complete")
def complete_onboarding(authorization: str | None = Header(None)) -> dict[str, Any]:
    current_profile = require_account_session(authorization)

    user_id = current_profile["account_user"]["id"]
    timestamp = now_iso()
    with DATA_LOCK:
        with db_connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET onboarding_completed = 1, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, user_id),
            )
    return {
        "mode": "account",
        "available": True,
        "onboarding_completed": True,
    }


@app.get("/admin/overview")
def admin_overview(authorization: str | None = Header(None)) -> dict[str, Any]:
    current_profile = require_profile(authorization)
    scope = ownership_scope_for_profile(current_profile["id"])
    owner_clause, owner_params = owner_where(scope)
    activity_clause, activity_params = owner_where(scope, "activity_events")
    with db_connect() as conn:
        counts = {
            "profiles": 1,
            "activeSessions": conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE profile_id = ?",
                (current_profile["id"],),
            ).fetchone()[0],
            "chats": conn.execute(f"SELECT COUNT(*) FROM chats WHERE {owner_clause}", owner_params).fetchone()[0],
            "messages": conn.execute(f"SELECT COUNT(*) FROM messages WHERE {owner_clause}", owner_params).fetchone()[0],
            "codeChats": conn.execute(f"SELECT COUNT(*) FROM code_chats WHERE {owner_clause}", owner_params).fetchone()[0],
            "codeMessages": conn.execute(f"SELECT COUNT(*) FROM code_messages WHERE {owner_clause}", owner_params).fetchone()[0],
            "documents": conn.execute(f"SELECT COUNT(*) FROM documents WHERE {owner_clause}", owner_params).fetchone()[0],
            "documentChunks": conn.execute(f"SELECT COUNT(*) FROM document_chunks WHERE {owner_clause}", owner_params).fetchone()[0],
            "memoryFacts": conn.execute(f"SELECT COUNT(*) FROM memory_facts WHERE {owner_clause}", owner_params).fetchone()[0],
        }
        recent = [
            {
                "eventType": row["event_type"],
                "profileName": row["name"] or "Unknown",
                "createdAt": row["created_at"],
                "detail": decode_json(row["detail"], row["detail"]),
            }
            for row in conn.execute(
                """
                SELECT activity_events.event_type, activity_events.detail, activity_events.created_at, profiles.name
                FROM activity_events
                LEFT JOIN profiles ON profiles.id = activity_events.profile_id
                WHERE {activity_clause}
                ORDER BY activity_events.created_at DESC
                LIMIT 20
                """.format(activity_clause=activity_clause)
                ,
                activity_params,
            ).fetchall()
        ]

    return {
        "viewer": public_profile(current_profile),
        "counts": counts,
        "modelStatus": model_status(),
        "features": {
            "smartIntentRouter": True,
            "studyTools": True,
            "documentRag": True,
            "webCitations": DDGS is not None,
            "memoryControls": True,
            "codeStudio": True,
        },
        "recentActivity": recent,
    }


@app.post("/admin/backup")
def admin_backup(authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_profile(authorization)
    backup = create_database_backup("manual")
    log_activity(profile["id"], "database_backup", {"path": backup["path"]})
    return {"ok": True, "backup": backup}


@app.get("/settings")
def get_settings(profile: dict[str, Any] = Header(None), authorization: str | None = Header(None)):
    current_profile = require_workspace_session(authorization)
    return {
        "settings": load_effective_settings(current_profile),
        "model": DEFAULT_MODEL,
        "vision_model": VISION_MODEL,
    }


@app.put("/settings")
def update_settings(
    data: SettingsUpdateRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    return {"settings": save_effective_settings(profile, model_to_update(data))}


@app.post("/intelligence/route")
def intelligence_route(
    data: RoutePreviewRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    settings = load_settings(profile["id"])
    route = analyze_user_intent(
        data.message,
        has_file_context=data.hasFileContext,
        has_search_context=data.hasSearchContext,
        settings=settings,
    )
    return {"route": route}


@app.get("/memory")
def get_memory(authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    return {"memory": load_memory(profile["id"], ownership_scope_from_profile(profile))}


@app.put("/memory")
def update_memory(
    data: MemoryUpdateRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    memory = load_memory(profile["id"])
    update = model_to_update(data)
    memory.update(update)
    return {"memory": save_memory(profile["id"], memory)}


@app.post("/memory/facts")
def remember_fact(
    data: MemoryFactRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    memory = load_memory(profile["id"])
    text = data.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="Memory text is empty.")

    memory.setdefault("facts", []).append(
        {"id": str(uuid.uuid4()), "text": text, "created_at": now_iso()}
    )
    return {"memory": save_memory(profile["id"], memory)}


@app.delete("/memory/facts/{fact_id}")
def forget_fact(fact_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    memory = load_memory(profile["id"])
    memory["facts"] = [fact for fact in memory.get("facts", []) if fact.get("id") != fact_id]
    return {"memory": save_memory(profile["id"], memory)}


@app.get("/download/{folder_id}/{filename}")
def download_file(
    folder_id: str,
    filename: str,
    authorization: str | None = Header(None),
):
    profile = require_workspace_session(authorization)
    if (
        not folder_id
        or not filename
        or folder_id != Path(folder_id).name
        or filename != Path(filename).name
        or any(separator in folder_id or separator in filename for separator in ("/", "\\"))
        or "\x00" in folder_id
        or "\x00" in filename
    ):
        raise HTTPException(status_code=400, detail="Unsafe download path rejected.")
    try:
        safe_folder_id = str(uuid.UUID(folder_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsafe download path rejected.")

    safe_filename = filename
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in ALLOWED_DOWNLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail="This download file type is not allowed.")

    folder_path = ensure_controlled_file_path(PROCESSED_DIR / safe_folder_id)
    file_path = ensure_controlled_file_path(folder_path / safe_filename)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    scope = ownership_scope_for_profile(profile["id"])
    owner_clause, owner_params = owner_where(scope)
    with DATA_LOCK:
        with db_connect() as conn:
            owned_file = conn.execute(
                f"SELECT id FROM files WHERE path = ? AND {owner_clause}",
                (str(file_path), *owner_params),
            ).fetchone()
            if not owned_file:
                for row in conn.execute(
                    f"SELECT payload FROM messages WHERE {owner_clause}",
                    owner_params,
                ).fetchall():
                    payload = decode_json(row["payload"], {})
                    download_url = payload.get("downloadUrl") if isinstance(payload, dict) else ""
                    if download_url and download_url.endswith(f"/download/{safe_folder_id}/{safe_filename}"):
                        upsert_file_row(
                            conn,
                            profile["id"],
                            str(file_path),
                            safe_filename,
                            scope=scope,
                        )
                        owned_file = True
                        break

    if not owned_file:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized download. This file does not belong to your workspace.",
        )

    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type=CANONICAL_UPLOAD_MIME_TYPES.get(
            suffix,
            "text/plain; charset=utf-8" if suffix in GENERATED_CODE_DOWNLOAD_EXTENSIONS else "application/octet-stream",
        ),
    )


@app.get("/chats")
def get_chats(authorization: str | None = Header(None)) -> dict[str, list[dict[str, Any]]]:
    profile = require_workspace_session(authorization)
    return {"chats": load_chat_metadata(profile["id"], ownership_scope_from_profile(profile))}


@app.post("/chats/new")
def create_chat(
    data: ChatCreateRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    new_chat = normalize_chat(
        {
            "id": str(uuid.uuid4()),
            "title": data.title or "New Chat",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_from_profile(profile) or ownership_scope_for_profile(profile["id"], conn)
            insert_empty_chat_row(conn, profile["id"], new_chat, scope)
    return new_chat


@app.patch("/chats/{chat_id}")
def update_chat(
    chat_id: str,
    data: ChatUpdateRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    assert_chat_owner_or_new(profile["id"], chat_id)
    chats = load_chats(profile["id"])
    chat_item = get_current_chat(chats, chat_id)

    if data.title is not None:
        chat_item["title"] = data.title.strip() or "New Chat"

    if data.pinned is not None:
        chat_item["pinned"] = data.pinned

    saved = save_current_chat(profile["id"], chats, chat_item)
    return {"chat": public_chat_payload(chat_item), "chats": saved}


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    assert_chat_owner_or_new(profile["id"], chat_id)
    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile["id"], conn)
            owner_clause, owner_params = owner_where(scope)
            conn.execute(
                f"DELETE FROM chats WHERE {owner_clause} AND id = ?",
                (*owner_params, chat_id),
            )
    return {"chats": load_chats(profile["id"])}


@app.get("/chats/{chat_id}")
def get_chat(chat_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    chat_id = validate_chat_id(chat_id)
    return {
        "chat": load_chat_by_id(
            profile["id"],
            chat_id,
            ownership_scope_from_profile(profile),
        )
    }


@app.post("/chats/{chat_id}/clear")
def clear_chat(chat_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    assert_chat_owner_or_new(profile["id"], chat_id)
    chats = load_chats(profile["id"])
    chat_item = get_current_chat(chats, chat_id)
    chat_item["messages"] = []
    chat_item["summary"] = ""
    chat_item["last_uploaded_file"] = None
    saved = save_current_chat(profile["id"], chats, chat_item)
    return {"chat": public_chat_payload(chat_item), "chats": saved}


@app.get("/chats/{chat_id}/export")
def export_chat(chat_id: str, authorization: str | None = Header(None)):
    profile = require_workspace_session(authorization)
    chats = load_chats(profile["id"])
    chat_item = next((chat for chat in chats if chat["id"] == chat_id), None)

    if not chat_item:
        raise HTTPException(status_code=404, detail="Chat not found.")

    text = export_chat_text(chat_item, profile.get("name", "User"))
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", chat_item.get("title", "chat")).strip("_")
    filename = f"{safe_title or 'chat'}-{datetime.now().strftime('%Y%m%d')}.txt"
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/code/chats")
def get_code_chats(authorization: str | None = Header(None)) -> dict[str, list[dict[str, Any]]]:
    profile = require_workspace_session(authorization)
    return {"chats": load_code_chat_metadata(profile["id"], ownership_scope_from_profile(profile))}


@app.post("/code/chats/new")
def create_code_chat(
    data: ChatCreateRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    new_chat = normalize_chat(
        {
            "id": str(uuid.uuid4()),
            "title": data.title or "New Code Chat",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_from_profile(profile) or ownership_scope_for_profile(profile["id"], conn)
            insert_empty_code_chat_row(conn, profile["id"], new_chat, scope)
    return new_chat


@app.patch("/code/chats/{chat_id}")
def update_code_chat(
    chat_id: str,
    data: ChatUpdateRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    assert_chat_owner_or_new(profile["id"], chat_id, code=True)
    chats = load_code_chats(profile["id"])
    chat_item = get_current_code_chat(chats, chat_id)

    if data.title is not None:
        chat_item["title"] = data.title.strip() or "New Code Chat"

    if data.pinned is not None:
        chat_item["pinned"] = data.pinned

    saved = save_current_code_chat(profile["id"], chats, chat_item)
    return {"chat": chat_item, "chats": saved}


@app.delete("/code/chats/{chat_id}")
def delete_code_chat(chat_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    assert_chat_owner_or_new(profile["id"], chat_id, code=True)
    with DATA_LOCK:
        with db_connect() as conn:
            scope = ownership_scope_for_profile(profile["id"], conn)
            owner_clause, owner_params = owner_where(scope)
            conn.execute(
                f"DELETE FROM code_chats WHERE {owner_clause} AND id = ?",
                (*owner_params, chat_id),
            )
    return {"chats": load_code_chats(profile["id"])}


@app.get("/code/chats/{chat_id}")
def get_code_chat(chat_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    profile = require_workspace_session(authorization)
    chat_id = validate_chat_id(chat_id)
    return {
        "chat": load_code_chat_by_id(
            profile["id"],
            chat_id,
            ownership_scope_from_profile(profile),
        )
    }


@app.get("/code/chats/{chat_id}/export")
def export_code_chat(chat_id: str, authorization: str | None = Header(None)):
    profile = require_workspace_session(authorization)
    chats = load_code_chats(profile["id"])
    chat_item = next((chat for chat in chats if chat["id"] == chat_id), None)

    if not chat_item:
        raise HTTPException(status_code=404, detail="Code chat not found.")

    text = export_chat_text(chat_item, profile.get("name", "User"))
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", chat_item.get("title", "code_chat")).strip("_")
    filename = f"{safe_title or 'code_chat'}-{datetime.now().strftime('%Y%m%d')}.txt"
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/code-chat-stream")
async def code_chat_stream(
    request: Request,
    chat_id: str = Form(...),
    message: str = Form(""),
    device_id: str | None = Form(None),
    answer_length: str = Form("standard"),
    replace_last_turn: bool = Form(False),
    file: UploadFile | None = File(None),
    code_files: list[UploadFile] | None = File(None),
    authorization: str | None = Header(None),
    x_febguy_device_id: str | None = Header(None, alias=DEVICE_ID_HEADER),
):
    metrics = stream_timing_metrics()
    _device_id = resolve_device_id(device_id, x_febguy_device_id)
    profile = require_workspace_session(authorization)
    enforce_rate_limit(request, "ai", profile)
    chat_id = validate_chat_id(chat_id)
    message = validate_message_length(message)
    answer_length = normalize_answer_length(answer_length)
    incoming_files = [item for item in (code_files or []) if item and item.filename]
    if file and file.filename:
        incoming_files.append(file)
    if incoming_files:
        enforce_rate_limit(request, "upload", profile)

    validated_code_uploads = [await validate_code_context_upload(item) for item in incoming_files]
    consume_guest_usage(profile, _device_id, "code", *(("upload",) if validated_code_uploads else ()))
    profile_id = profile["id"]
    scope = ownership_scope_from_profile(profile)
    user_message = (message or "").strip() or "Help me write code."
    message_limit = None if replace_last_turn else STREAM_CODE_CONTEXT_MESSAGES
    current_chat = load_code_chat_by_id(
        profile_id,
        chat_id,
        scope,
        message_limit=message_limit,
        include_project_files=False,
    )
    chats = [current_chat]
    if replace_last_turn:
        remove_latest_turn_for_retry(current_chat)
    pasted_code_files = extract_pasted_code_files(user_message)
    saved_project_files: list[dict[str, Any]] = []
    if validated_code_uploads or pasted_code_files:
        # Persist the code chat shell first so project file rows can safely reference it.
        save_current_code_chat(profile_id, chats, current_chat)
        for file_name, file_type, content in validated_code_uploads:
            saved_project_files.append(save_code_project_file(profile_id, chat_id, file_name, content, file_type))
        for pasted_file in pasted_code_files:
            saved_project_files.append(
                save_code_project_file(
                    profile_id,
                    chat_id,
                    pasted_file["file_name"],
                    pasted_file["content"],
                    "text/plain",
                    pasted_file.get("language"),
                )
            )
    append_user_message(current_chat, user_message, None)
    if saved_project_files:
        current_chat["messages"][-1]["codeFiles"] = saved_project_files
    metrics["prepare_ms"] = elapsed_ms(metrics["started_at"])
    if is_code_context_only_message(user_message, saved_project_files):
        quick_reply = (
            f"Added {len(saved_project_files)} code file"
            f"{'' if len(saved_project_files) == 1 else 's'} to this Code Studio chat. "
            "Ask me to find bugs, suggest a diff, generate tests, convert code, or create README/setup instructions."
        )

        def context_saved_stream():
            mark_stream_first_token(metrics)
            yield quick_reply
            meta = {
                "codeTask": "project_context",
                "codeLanguage": "auto",
                "workspace": "code",
                "projectFiles": saved_project_files,
            }
            yield f"{META_PREFIX}{json.dumps(meta)}{META_SUFFIX}"

            def persist_and_log() -> None:
                persist_started = time.perf_counter()
                try:
                    persist_code_response(
                        profile_id,
                        chats,
                        current_chat,
                        user_message,
                        quick_reply,
                        "project_context",
                        "auto",
                        saved_project_files,
                        [],
                        reload_metadata=False,
                    )
                finally:
                    finish_stream_persistence(metrics, persist_started)
                    log_stream_timing("/code-chat-stream", metrics)

            start_stream_persistence_thread(metrics, persist_and_log)

        return StreamingResponse(
            context_saved_stream(),
            media_type="text/plain; charset=utf-8",
            headers=STREAM_RESPONSE_HEADERS,
        )

    quick_reply = get_code_conversation_reply(user_message)

    if quick_reply:
        task = "conversation"
        language = "auto"

        def quick_response_stream():
            mark_stream_first_token(metrics)
            yield quick_reply
            meta = {
                "codeTask": task,
                "codeLanguage": language,
                "workspace": "code",
                "projectFiles": saved_project_files,
            }
            yield f"{META_PREFIX}{json.dumps(meta)}{META_SUFFIX}"

            def persist_and_log() -> None:
                persist_started = time.perf_counter()
                try:
                    persist_code_response(
                        profile_id,
                        chats,
                        current_chat,
                        user_message,
                        quick_reply,
                        task,
                        language,
                        saved_project_files,
                        [],
                        reload_metadata=False,
                    )
                finally:
                    finish_stream_persistence(metrics, persist_started)
                    log_stream_timing("/code-chat-stream", metrics)

            start_stream_persistence_thread(metrics, persist_and_log)

        return StreamingResponse(
            quick_response_stream(),
            media_type="text/plain; charset=utf-8",
            headers=STREAM_RESPONSE_HEADERS,
        )

    task = detect_code_task(user_message)
    language = detect_code_language(user_message)
    project_context = ""
    selected_project_files: list[dict[str, Any]] = []
    if should_load_code_project_context(user_message, task, saved_project_files):
        context_started = time.perf_counter()
        project_context, selected_project_files = build_code_project_context(profile_id, chat_id, user_message)
        metrics["context_ms"] = elapsed_ms(context_started)
    relevant_project_files = selected_project_files or saved_project_files
    code_activity_detail = {"task": task, "language": language}
    clarification = code_clarification_response(user_message, task, has_project_context=bool(relevant_project_files))

    if clarification:
        def clarification_response_stream():
            mark_stream_first_token(metrics)
            yield clarification
            meta = {
                "codeTask": task,
                "codeLanguage": language,
                "workspace": "code",
                "projectFiles": relevant_project_files,
            }
            yield f"{META_PREFIX}{json.dumps(meta)}{META_SUFFIX}"

            def persist_and_log() -> None:
                persist_started = time.perf_counter()
                try:
                    persist_code_response(
                        profile_id,
                        chats,
                        current_chat,
                        user_message,
                        clarification,
                        task,
                        language,
                        relevant_project_files,
                        [],
                        reload_metadata=False,
                    )
                finally:
                    finish_stream_persistence(metrics, persist_started)
                    log_stream_timing("/code-chat-stream", metrics)

            start_stream_persistence_thread(metrics, persist_and_log)

        return StreamingResponse(
            clarification_response_stream(),
            media_type="text/plain; charset=utf-8",
            headers=STREAM_RESPONSE_HEADERS,
        )

    metrics["prepare_ms"] = elapsed_ms(metrics["started_at"])
    prompt, task, language = build_code_prompt(user_message, current_chat, profile, answer_length, project_context)

    def response_stream():
        ai_text = ""
        ai_started = time.perf_counter()

        for chunk in stream_text_model(prompt, model=CODE_MODEL):
            ai_text += chunk
            mark_stream_first_token(metrics)
            yield chunk
        metrics["ai_total_ms"] = elapsed_ms(ai_started)

        final_text = ai_text.strip() or "I could not generate a coding response."
        meta = {
            "codeTask": task,
            "codeLanguage": language,
            "workspace": "code",
            "projectFiles": relevant_project_files,
        }
        generated_files = save_generated_code_files(profile_id, current_chat["id"], user_message, final_text)
        if generated_files:
            meta["generatedFiles"] = generated_files
        yield f"{META_PREFIX}{json.dumps(meta)}{META_SUFFIX}"

        def persist_and_log() -> None:
            persist_started = time.perf_counter()
            try:
                persist_code_response(
                    profile_id,
                    chats,
                    current_chat,
                    user_message,
                    final_text,
                    task,
                    language,
                    relevant_project_files,
                    generated_files,
                    reload_metadata=False,
                )
            finally:
                finish_stream_persistence(metrics, persist_started)
                log_stream_timing("/code-chat-stream", metrics)
                log_activity_async(
                    profile_id,
                    "code_request",
                    code_activity_detail,
                    delay_seconds=GUEST_BACKGROUND_SETUP_DELAY_SECONDS,
                )

        start_stream_persistence_thread(metrics, persist_and_log)

    return StreamingResponse(
        response_stream(),
        media_type="text/plain; charset=utf-8",
        headers=STREAM_RESPONSE_HEADERS,
    )


@app.post("/chat")
async def chat(
    request: Request,
    chat_id: str = Form(...),
    message: str = Form(""),
    device_id: str | None = Form(None),
    answer_length: str = Form("standard"),
    response_mode: str = Form("balanced"),
    model_mode: str = Form("smart"),
    replace_last_turn: bool = Form(False),
    file: UploadFile | None = File(None),
    authorization: str | None = Header(None),
    x_febguy_device_id: str | None = Header(None, alias=DEVICE_ID_HEADER),
):
    _device_id = resolve_device_id(device_id, x_febguy_device_id)
    profile = require_workspace_session(authorization)
    enforce_rate_limit(request, "ai", profile)
    if profile.get("is_guest"):
        enforce_rate_limit(request, "guest_chat", profile)
    if file:
        enforce_rate_limit(request, "upload", profile)
    chat_id = validate_chat_id(chat_id)
    message = validate_message_length(message)
    answer_length = normalize_answer_length(answer_length)
    response_mode = normalize_response_mode(response_mode)
    model_mode = normalize_model_mode(model_mode)
    validated_upload = await validate_uploaded_file(file) if file else None
    consume_guest_usage(profile, _device_id, "chat", *(("upload",) if file else ()))
    profile_id = profile["id"]
    (
        chats,
        current_chat,
        user_message,
        memory,
        settings,
        uploaded_file,
        file_context,
        image_payloads,
        citations,
        document_hits,
        search_context,
        research,
    ) = await prepare_chat(profile, chat_id, message, file, validated_upload, replace_last_turn)

    if search_context.startswith("__DOCUMENT_TOOL__"):
        document_result = json.loads(search_context.replace("__DOCUMENT_TOOL__", "", 1))
        return save_document_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            uploaded_file,
            document_result,
        )

    if file_context.startswith(DOCUMENT_NOT_IN_CHAT_PREFIX):
        return save_document_not_available_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            uploaded_file,
            file_context.replace(DOCUMENT_NOT_IN_CHAT_PREFIX, "", 1),
        )

    conversation = classify_conversation(
        user_message,
        current_chat.get("messages", []),
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        settings=settings,
    )
    intent = classify_intent(
        user_message,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        conversation=conversation,
    )
    route = analyze_user_intent(
        user_message,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        settings=settings,
        research=research,
        conversation=conversation,
    )
    answer_mode = route["answerMode"]
    log_activity_async(profile_id, "chat_request", {"intent": intent, "mode": answer_mode, "tool": route["tool"]})
    has_history = bool(current_chat.get("messages"))
    clarification = clarification_response(
        user_message,
        intent,
        has_file_context=bool(file_context),
        has_history=has_history,
        conversation=conversation,
    )
    suggestions = build_followup_suggestions(
        intent,
        user_message,
        has_file_context=bool(file_context),
        search_used=bool(search_context),
    )
    append_user_message(current_chat, user_message, uploaded_file)

    if clarification:
        saved_chats = persist_ai_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            clarification,
            suggestions=suggestions,
            use_llm_title=False,
            update_summary=False,
        )
        return {
            "response": clarification,
            "chat": public_chat_payload(current_chat),
            "chats": saved_chats,
            "intent": intent,
            "answerMode": answer_mode,
            "route": route,
            "suggestions": suggestions,
        }

    direct_response = direct_tool_response(user_message, current_chat, conversation)
    if direct_response:
        saved_chats = persist_ai_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            direct_response,
            suggestions=suggestions,
            use_llm_title=False,
            update_summary=False,
        )
        return {
            "response": direct_response,
            "chat": public_chat_payload(current_chat),
            "chats": saved_chats,
            "intent": intent,
            "answerMode": answer_mode,
            "route": route,
            "suggestions": suggestions,
        }

    prompt = build_prompt(
        user_message=user_message,
        memory=memory,
        current_chat=current_chat,
        file_context=file_context,
        search_context=search_context,
        calculator_result="",
        intent=intent,
        answer_mode=answer_mode,
        answer_length=answer_length,
        response_mode=response_mode,
        research=research,
        conversation=conversation,
    )
    model = select_chat_model(
        response_mode=response_mode,
        model_mode=model_mode,
        intent=intent,
        answer_mode=answer_mode,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        has_images=bool(image_payloads),
    )
    ai_response = call_text_model(prompt, model=model, images=image_payloads or None)
    ai_response = refine_response_if_enabled(
        ai_response,
        user_message,
        response_mode,
        (conversation or {}).get("emotionalTone"),
        intent,
    )
    saved_chats = persist_ai_response(
        profile_id,
        chats,
        current_chat,
        user_message,
        ai_response,
        citations=citations,
        document_hits=document_hits,
        suggestions=suggestions,
    )

    return {
        "response": ai_response,
        "chat": public_chat_payload(current_chat),
        "chats": saved_chats,
        "searchUsed": bool(search_context),
        "citations": citations,
        "documentHits": public_document_hits(document_hits),
        "intent": intent,
        "answerMode": answer_mode,
        "route": route,
        "research": research,
        "suggestions": suggestions,
    }


@app.post("/voice-chat")
async def voice_chat(
    request: Request,
    chat_id: str = Form(...),
    device_id: str | None = Form(None),
    answer_length: str = Form("standard"),
    response_mode: str = Form("balanced"),
    model_mode: str = Form("smart"),
    audio: UploadFile = File(...),
    authorization: str | None = Header(None),
    x_febguy_device_id: str | None = Header(None, alias=DEVICE_ID_HEADER),
):
    _device_id = resolve_device_id(device_id, x_febguy_device_id)
    profile = require_workspace_session(authorization)
    enforce_rate_limit(request, "ai", profile)
    if profile.get("is_guest"):
        enforce_rate_limit(request, "guest_chat", profile)
    chat_id = validate_chat_id(chat_id)
    answer_length = normalize_answer_length(answer_length)
    response_mode = normalize_response_mode(response_mode)
    model_mode = normalize_model_mode(model_mode)
    consume_guest_usage(profile, _device_id, "chat")
    profile_id = profile["id"]
    audio_bytes = await audio.read()
    transcript = transcribe_audio_with_groq(
        audio_bytes,
        filename=audio.filename or "voice.webm",
        content_type=audio.content_type or "audio/webm",
    )

    chats = load_chats(profile_id)
    current_chat = get_current_chat(chats, chat_id)
    settings = load_settings(profile_id)
    memory = update_memory_from_message(profile_id, transcript)
    file_context, image_payloads, document_hits = build_file_context_from_chat(
        profile_id,
        current_chat,
        transcript,
        settings,
    )

    if file_context.startswith(DOCUMENT_NOT_IN_CHAT_PREFIX):
        payload = save_document_not_available_response(
            profile_id,
            chats,
            current_chat,
            transcript,
            None,
            file_context.replace(DOCUMENT_NOT_IN_CHAT_PREFIX, "", 1),
        )
        payload["transcript"] = transcript
        return payload

    search_context, citations, research = prepare_web_research(
        transcript,
        has_file_context=bool(file_context),
        settings=settings,
    )

    conversation = classify_conversation(
        transcript,
        current_chat.get("messages", []),
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        settings=settings,
    )
    intent = classify_intent(
        transcript,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        conversation=conversation,
    )
    route = analyze_user_intent(
        transcript,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        settings=settings,
        research=research,
        conversation=conversation,
    )
    answer_mode = route["answerMode"]
    suggestions = build_followup_suggestions(
        intent,
        transcript,
        has_file_context=bool(file_context),
        search_used=bool(search_context),
    )
    has_history = bool(current_chat.get("messages"))
    clarification = clarification_response(
        transcript,
        intent,
        has_file_context=bool(file_context),
        has_history=has_history,
        conversation=conversation,
    )

    append_user_message(current_chat, transcript, None)
    log_activity(profile_id, "voice_request", {"intent": intent, "mode": answer_mode, "tool": route["tool"]})

    ai_response = clarification or direct_tool_response(transcript, current_chat, conversation)
    used_model_response = False
    if not ai_response:
        prompt = build_prompt(
            user_message=transcript,
            memory=memory,
            current_chat=current_chat,
            file_context=file_context,
            search_context=search_context,
            calculator_result="",
            intent=intent,
            answer_mode=answer_mode,
            answer_length=answer_length,
            response_mode=response_mode,
            research=research,
            conversation=conversation,
        )
        ai_response = call_text_model(
            prompt,
            model=select_chat_model(
                response_mode=response_mode,
                model_mode=model_mode,
                intent=intent,
                answer_mode=answer_mode,
                has_file_context=bool(file_context),
                has_search_context=bool(search_context),
                has_images=bool(image_payloads),
                is_voice=True,
            ),
            images=image_payloads or None,
        )
        used_model_response = True

    if used_model_response:
        ai_response = refine_response_if_enabled(
            ai_response,
            transcript,
            response_mode,
            (conversation or {}).get("emotionalTone"),
            intent,
        )

    saved_chats = persist_ai_response(
        profile_id,
        chats,
        current_chat,
        transcript,
        ai_response,
        citations=citations,
        document_hits=document_hits,
        suggestions=suggestions,
        use_llm_title=not bool(clarification),
        update_summary=not bool(clarification),
    )

    return {
        "transcript": transcript,
        "response": ai_response,
        "chat": public_chat_payload(current_chat),
        "chats": saved_chats,
        "searchUsed": bool(search_context),
        "citations": citations,
        "documentHits": public_document_hits(document_hits),
        "intent": intent,
        "answerMode": answer_mode,
        "route": route,
        "research": research,
        "suggestions": suggestions,
    }


@app.post("/chat-stream")
async def chat_stream(
    request: Request,
    chat_id: str = Form(...),
    message: str = Form(""),
    device_id: str | None = Form(None),
    answer_length: str = Form("standard"),
    response_mode: str = Form("balanced"),
    model_mode: str = Form("smart"),
    replace_last_turn: bool = Form(False),
    file: UploadFile | None = File(None),
    authorization: str | None = Header(None),
    x_febguy_device_id: str | None = Header(None, alias=DEVICE_ID_HEADER),
):
    metrics = stream_timing_metrics()
    _device_id = resolve_device_id(device_id, x_febguy_device_id)
    profile = require_workspace_session(authorization)
    enforce_rate_limit(request, "ai", profile)
    if profile.get("is_guest"):
        enforce_rate_limit(request, "guest_chat", profile)
    if file:
        enforce_rate_limit(request, "upload", profile)
    chat_id = validate_chat_id(chat_id)
    message = validate_message_length(message)
    answer_length = normalize_answer_length(answer_length)
    response_mode = normalize_response_mode(response_mode)
    model_mode = normalize_model_mode(model_mode)
    validated_upload = await validate_uploaded_file(file) if file else None
    consume_guest_usage(profile, _device_id, "chat", *(("upload",) if file else ()))
    profile_id = profile["id"]
    (
        chats,
        current_chat,
        user_message,
        memory,
        settings,
        uploaded_file,
        file_context,
        image_payloads,
        citations,
        document_hits,
        search_context,
        research,
    ) = await prepare_chat(profile, chat_id, message, file, validated_upload, replace_last_turn, metrics)
    metrics["prepare_ms"] = elapsed_ms(metrics["started_at"])

    if search_context.startswith("__DOCUMENT_TOOL__"):
        document_result = json.loads(search_context.replace("__DOCUMENT_TOOL__", "", 1))
        persist_started = time.perf_counter()
        response_payload = save_document_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            uploaded_file,
            document_result,
        )
        metrics["persist_ms"] = elapsed_ms(persist_started)
        log_stream_timing("/chat-stream", metrics)
        return JSONResponse(
            response_payload
        )

    if file_context.startswith(DOCUMENT_NOT_IN_CHAT_PREFIX):
        persist_started = time.perf_counter()
        response_payload = save_document_not_available_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            uploaded_file,
            file_context.replace(DOCUMENT_NOT_IN_CHAT_PREFIX, "", 1),
        )
        metrics["persist_ms"] = elapsed_ms(persist_started)
        log_stream_timing("/chat-stream", metrics)
        return JSONResponse(
            response_payload
        )

    conversation = classify_conversation(
        user_message,
        current_chat.get("messages", []),
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        settings=settings,
    )
    intent = classify_intent(
        user_message,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        conversation=conversation,
    )
    route = analyze_user_intent(
        user_message,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        settings=settings,
        research=research,
        conversation=conversation,
    )
    answer_mode = route["answerMode"]
    chat_activity_detail = {"intent": intent, "mode": answer_mode, "tool": route["tool"]}
    has_history = bool(current_chat.get("messages"))
    clarification = clarification_response(
        user_message,
        intent,
        has_file_context=bool(file_context),
        has_history=has_history,
        conversation=conversation,
    )
    suggestions = build_followup_suggestions(
        intent,
        user_message,
        has_file_context=bool(file_context),
        search_used=bool(search_context),
    )
    append_user_message(current_chat, user_message, uploaded_file)

    if clarification:
        persist_started = time.perf_counter()
        saved_chats = persist_ai_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            clarification,
            suggestions=suggestions,
            use_llm_title=False,
            update_summary=False,
        )
        metrics["persist_ms"] = elapsed_ms(persist_started)
        log_stream_timing("/chat-stream", metrics)
        return JSONResponse(
            {
                "response": clarification,
                "chat": public_chat_payload(current_chat),
                "chats": saved_chats,
                "intent": intent,
                "answerMode": answer_mode,
                "route": route,
                "suggestions": suggestions,
            }
        )

    direct_response = direct_tool_response(user_message, current_chat, conversation)
    if direct_response:
        persist_started = time.perf_counter()
        saved_chats = persist_ai_response(
            profile_id,
            chats,
            current_chat,
            user_message,
            direct_response,
            suggestions=suggestions,
            use_llm_title=False,
            update_summary=False,
        )
        metrics["persist_ms"] = elapsed_ms(persist_started)
        log_stream_timing("/chat-stream", metrics)
        return JSONResponse(
            {
                "response": direct_response,
                "chat": public_chat_payload(current_chat),
                "chats": saved_chats,
                "intent": intent,
                "answerMode": answer_mode,
                "route": route,
                "suggestions": suggestions,
            }
        )

    prompt = build_prompt(
        user_message=user_message,
        memory=memory,
        current_chat=current_chat,
        file_context=file_context,
        search_context=search_context,
        calculator_result="",
        intent=intent,
        answer_mode=answer_mode,
        answer_length=answer_length,
        response_mode=response_mode,
        research=research,
        conversation=conversation,
    )
    model = select_chat_model(
        response_mode=response_mode,
        model_mode=model_mode,
        intent=intent,
        answer_mode=answer_mode,
        has_file_context=bool(file_context),
        has_search_context=bool(search_context),
        has_images=bool(image_payloads),
    )

    def response_stream():
        ai_text = ""
        ai_started = time.perf_counter()

        for chunk in stream_text_model(prompt, model=model, images=image_payloads or None):
            ai_text += chunk
            mark_stream_first_token(metrics)
            yield chunk
        metrics["ai_total_ms"] = elapsed_ms(ai_started)

        final_text = ai_text.strip() or "I could not generate a response."
        meta = {
            "citations": citations,
            "documentHits": public_document_hits(document_hits),
            "intent": intent,
            "answerMode": answer_mode,
            "route": route,
            "research": research,
            "suggestions": suggestions,
        }
        yield f"{META_PREFIX}{json.dumps(meta)}{META_SUFFIX}"

        def persist_and_log() -> None:
            persist_started = time.perf_counter()
            try:
                persist_ai_response(
                    profile_id,
                    chats,
                    current_chat,
                    user_message,
                    final_text,
                    citations=citations,
                    document_hits=document_hits,
                    suggestions=suggestions,
                    reload_metadata=False,
                )
            finally:
                finish_stream_persistence(metrics, persist_started)
                log_stream_timing("/chat-stream", metrics)
                log_activity_async(
                    profile_id,
                    "chat_stream_request",
                    chat_activity_detail,
                    delay_seconds=GUEST_BACKGROUND_SETUP_DELAY_SECONDS,
                )

        start_stream_persistence_thread(metrics, persist_and_log)

    return StreamingResponse(
        response_stream(),
        media_type="text/plain; charset=utf-8",
        headers=STREAM_RESPONSE_HEADERS,
    )
