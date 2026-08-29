#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-efile.settings_dev}"
bind_address="${CROSSWALK_REVIEW_BIND:-0.0.0.0:8001}"

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py load_crosswalk
exec .venv/bin/python manage.py runserver "$bind_address"
