#!/usr/bin/env bash
set -euo pipefail

PGROOT="${POSTGRES_LOCAL_ROOT:-$HOME/.local/pgsql/postgresql-16}"
PGDATA="${POSTGRES_LOCAL_DATA:-$HOME/.local/var/postgresql16-data}"
PGLOG="${POSTGRES_LOCAL_LOG:-$HOME/.local/var/postgresql16.log}"

if [[ ! -x "$PGROOT/bin/pg_ctl" ]]; then
  echo "PostgreSQL binaries not found at $PGROOT"
  exit 1
fi

if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
  echo "PostgreSQL data directory not found at $PGDATA"
  exit 1
fi

if "$PGROOT/bin/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  echo "PostgreSQL is already running."
  exit 0
fi

"$PGROOT/bin/pg_ctl" -D "$PGDATA" -l "$PGLOG" start
"$PGROOT/bin/pg_isready" -h localhost -p 5432 -U postgres
