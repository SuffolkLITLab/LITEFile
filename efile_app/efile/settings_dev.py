import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Determine BASE_DIR without importing base to load .env first
_BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env at the project base directory BEFORE base import
load_dotenv(dotenv_path=_BASE_DIR / ".env", override=False)

from efile.settings_base import *  # noqa: E402,F401,F403
from efile.settings_base import DATABASES as BASE_DATABASES  # noqa: E402

# Bind DATABASES explicitly to avoid F405 and make linter aware of the symbol
DATABASES = BASE_DATABASES

DEBUG = True
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1", ".localhost", "[::1]", "testserver"]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://::1",
    "http://testserver",
]

# If a DATABASE_URL is provided locally, prefer Postgres over SQLite
_DEV_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if _DEV_DATABASE_URL:
    DATABASES["default"] = dj_database_url.config(
        default=_DEV_DATABASE_URL,
        conn_max_age=0,  # no pooling for dev; immediate close on request end
        ssl_require=False,
    )
