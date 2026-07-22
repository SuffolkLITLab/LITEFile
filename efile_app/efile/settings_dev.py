import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Determine BASE_DIR without importing base to load .env first
_BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env at the project base directory BEFORE base import
load_dotenv(dotenv_path=_BASE_DIR / ".env", override=False)

from efile.settings_base import *  # noqa: E402,F401,F403
from efile.settings_base import ALLOWED_HOSTS as BASE_ALLOWED_HOSTS  # noqa: E402
from efile.settings_base import DATABASES as BASE_DATABASES  # noqa: E402

# Bind DATABASES explicitly to avoid F405 and make linter aware of the symbol
DATABASES = BASE_DATABASES

DEBUG = True
ALLOWED_HOSTS = BASE_ALLOWED_HOSTS or ["localhost", "127.0.0.1", ".localhost", "[::1]", "testserver"]

# Opt-in: send this URL to the EFSP proxy as every document's `data_url` instead
# of the real S3 URL.
#
# The proxy downloads each `data_url` itself -- for a fee quote as well as for a
# filing -- and only accepts http(s), so a LocalStack URL is unreachable to it.
# Setting this to any publicly readable PDF lets fee quotes and submissions run
# end-to-end from a laptop with no ingress, tunnel, or public bucket.
#
# Uploads still go to S3/LocalStack for real and drafts still store the real keys
# and URLs; only the URL handed to the proxy changes. Defined here rather than in
# settings_base so no environment variable can enable it outside development.
EFSP_TEST_DOCUMENT_URL = os.getenv("EFSP_TEST_DOCUMENT_URL", "").strip()
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
