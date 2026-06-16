#!/usr/bin/env bash
# Launch dough from the checkout with a sane locale (LC_NUMERIC=C keeps Qt's
# number parsing predictable across locales) and any extra args passed through.
set -e
cd "$(dirname "$0")/.."
export LC_NUMERIC=C
exec python3 -m dough "$@"
