#!/bin/sh
set -e
if [ "$INIT_DB" = "true" ]; then
  python app.py init-db
  unset INIT_DB
fi
exec "$@"
