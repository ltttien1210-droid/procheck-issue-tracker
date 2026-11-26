#!/usr/bin/env sh
set -eu
python -m flask --app procheck db-upgrade
python -m flask --app procheck prepare-public-demo
exec gunicorn --workers 1 --bind "0.0.0.0:${PORT:-10000}" 'procheck:create_app()'
