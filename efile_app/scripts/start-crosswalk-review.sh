#!/bin/sh
set -eu

review_database_path="${CROSSWALK_REVIEW_DATABASE_PATH:-/data/crosswalk-review.sqlite3}"
review_checksum_path="${CROSSWALK_REVIEW_CHECKSUM_PATH:-/data/crosswalk-review-source.sha256}"
review_source_path="efile/data/form_code_crosswalk.json"
review_database_existed=false

if [ -s "$review_database_path" ]; then
    review_database_existed=true
fi

.venv/bin/python manage.py migrate --noinput --fake-initial

review_checksum_line=$(sha256sum "$review_source_path")
review_checksum=${review_checksum_line%% *}
review_previous_checksum=""
if [ -r "$review_checksum_path" ]; then
    review_previous_checksum=$(sed -n '1p' "$review_checksum_path")
fi

if [ "$review_database_existed" != true ] || [ "$review_checksum" != "$review_previous_checksum" ]; then
    .venv/bin/python manage.py load_crosswalk
    printf '%s\n' "$review_checksum" > "$review_checksum_path"
else
    echo "Crosswalk source is unchanged; keeping the volume-backed review database."
fi

exec .venv/bin/gunicorn efile.asgi:application \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
