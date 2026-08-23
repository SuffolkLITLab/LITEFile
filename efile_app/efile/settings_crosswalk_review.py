"""Production settings for the standalone crosswalk review deployment."""

import os

from efile.settings_base import *  # noqa: F401,F403
from efile.settings_base import BASE_DIR as BASE_SETTINGS_DIR
from efile.settings_base import MIDDLEWARE as BASE_MIDDLEWARE

DEBUG = False

APP_HOSTNAME = os.getenv("CROSSWALK_REVIEW_HOSTNAME", "litefile-crosswalk-review.fly.dev").strip()
ALLOWED_HOSTS = [APP_HOSTNAME]
CSRF_TRUSTED_ORIGINS = [f"https://{APP_HOSTNAME}"]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError("DJANGO_SECRET_KEY must be set to a strong value for the crosswalk review app")

# Serve the review app at the root and do not expose the rest of LITEFile's
# filing workflow from this deployment.
ROOT_URLCONF = "crosswalk_review.project_urls"

# Store the SQLite database on the Fly volume. A single Machine and worker are
# used by the Fly config, which avoids multi-writer SQLite and volume conflicts.
CROSSWALK_REVIEW_DATABASE_PATH = os.getenv(
    "CROSSWALK_REVIEW_DATABASE_PATH",
    "/data/crosswalk-review.sqlite3",
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": CROSSWALK_REVIEW_DATABASE_PATH,
        "OPTIONS": {"timeout": 20},
    }
}

# WhiteNoise serves the static bundle collected into the Docker image.
STATIC_ROOT = BASE_SETTINGS_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MIDDLEWARE = list(BASE_MIDDLEWARE)
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

SECURE_SSL_REDIRECT = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 86400
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
