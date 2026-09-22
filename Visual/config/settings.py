

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ─────────────────────────────────────────────────────────────────
# NEVER expose this in production — use environment variables
SECRET_KEY = "django-insecure-dataflow-dev-key-change-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]   # In production: ["yourdomain.com"]

# ── Applications ──────────────────────────────────────────────────────────────
# Django is modular — each "app" is a self-contained component.
# Our "core" app holds all DataFlow logic.
INSTALLED_APPS = [
    "django.contrib.staticfiles",   # serves CSS/JS files
    "django.contrib.messages",      # flash messages (success/error)
    "django.contrib.sessions",      # user sessions (remembers who you are)
    "core",                         # OUR app
]

# ── Middleware ─────────────────────────────────────────────────────────────────
# Middleware is code that runs on EVERY request/response cycle.
# Think of it as airport security — every passenger (request) passes through it.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",    # prevents form forgery attacks
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"

# ── Templates ──────────────────────────────────────────────────────────────────
# Django's template engine finds HTML files and renders them with context data.
# Think of templates as "mail merge" — the same letter with different names filled in.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Static files ───────────────────────────────────────────────────────────────
# Static files = CSS, JS, images that don't change per user
STATIC_URL  = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# ── Sessions ───────────────────────────────────────────────────────────────────
# We use file-based sessions (simplest) — stores session data on disk.
# In production, use Redis or database sessions.
SESSION_ENGINE = "django.contrib.sessions.backends.file"

# ── FastAPI Microservice URL ───────────────────────────────────────────────────
# This is the address where our FastAPI processing service lives.
# Django calls this URL whenever it needs to process data.
FASTAPI_BASE_URL = 'FASTAPI_BASE_URL = "https://dataflow-ggj6.onrender.com"'
FASTAPI_BASE_URL = os.environ.get(
    "FASTAPI_BASE_URL",
    "http://127.0.0.1:8001",
)

# ── File uploads ───────────────────────────────────────────────────────────────
# Limit upload size to 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
WSGI_APPLICATION = "config.wsgi.application"

# ── Message storage ────────────────────────────────────────────────────────────
# Store flash messages in cookies (no database needed)
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"