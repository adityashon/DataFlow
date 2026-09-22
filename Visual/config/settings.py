

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY = "django-insecure-dataflow-dev-key-change-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]   # In production: ["yourdomain.com"]

# ── Applications ──────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.staticfiles",   # serves CSS/JS files
    "django.contrib.messages",      # flash messages (success/error)
    "django.contrib.sessions",      # user sessions (remembers who you are)
    "core",                         # OUR app
]

# ── Middleware ─────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.security.SecurityMiddleware"
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",    # prevents form forgery attacks
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"

# ── Templates ──────────────────────────────────────────────────────────────────

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
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ── Sessions ───────────────────────────────────────────────────────────────────

SESSION_ENGINE = "django.contrib.sessions.backends.file"

# ── FastAPI Microservice URL ───────────────────────────────────────────────────

FASTAPI_BASE_URL = "https://dataflow-s5of.onrender.com"
FASTAPI_BASE_URL = os.environ.get(
    FASTAPI_BASE_URL,
    "http://127.0.0.1:8001",
)

# ── File uploads ───────────────────────────────────────────────────────────────
# Limit upload size to 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
WSGI_APPLICATION = "config.wsgi.application"

# ── Message storage ────────────────────────────────────────────────────────────

MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"