import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# Dev fallback; staging/prod must override via env in their settings modules.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-r1o&rohs_$%i1)u-8amhsu)o!z4ply+x^*_ht&-jav0h6rnpdo")

# SECURITY WARNING: don't run with debug turned on in production!
# Override in env-specific settings
DEBUG = True

# Override in env-specific settings
_configured_allowed_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS: list[str] = [host.strip() for host in _configured_allowed_hosts.split(",") if host.strip()]

# Override in env-specific settings
CSRF_TRUSTED_ORIGINS: list[str] = []

AUTH_USER_MODEL = "efile.UserProfile"

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "efile",
    "efile.templatetags.md_to_html",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "efile.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "efile/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "efile.context_processors.jurisdiction_context",
            ],
        },
    },
]

WSGI_APPLICATION = "efile.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "efile.authentication.SuffolkEFileBackend",  # for logging users in with Tyler
    "django.contrib.auth.backends.ModelBackend",
]

SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "efile/static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SUFFOLK_EFILE_API_KEY = os.getenv("SUFFOLK_EFILE_API_KEY", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/")

# Base URL for EFSP-compatible APIs (Suffolk LIT Lab by default)
# Override per environment with EFSP_URL env var
EFSP_URL = os.getenv("EFSP_URL", "https://efile-test.suffolklitlab.org")

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME", "")
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-1")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", None)

# File Upload Settings
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_FILE_TYPES = [".pdf", ".doc", ".docx"]

# Logging configuration
# Uses standard Python logging. Control the app logger level via DJANGO_LOG_LEVEL env var.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[%(levelname)s] %(asctime)s %(name)s: %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        }
    },
    "loggers": {
        # Django's own logs
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_DJANGO_LOG_LEVEL", "INFO"),
            "propagate": True,
        },
        # App-specific logger
        "efile": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "DEBUG"),
            "propagate": False,
        },
    },
}
