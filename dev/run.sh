#!/bin/bash
# Run tracker keeper from this checkout, in the foreground, with its log
# streaming into the terminal — what the "(dev)" app-menu entry launches
# (dev/create_desktop_entry.sh).
#
# It REPLACES a running copy first. The app is single-instance, so launching
# beside an old process only raises the old window — which is how a fresh
# checkout ends up looking like nothing changed.
#
#   dev/run.sh                          # whichever UI this shell gets
#   TRACKERKEEPER_UI=widgets dev/run.sh # force the desktop window
#   TRACKERKEEPER_UI=quick dev/run.sh   # force the phone interface
#   TRACKERKEEPER_LOG=debug dev/run.sh  # chattier log

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY=python3

# Stop any copy running out of this checkout (the installed entry point or
# python -m), and wait for it to let go of the single-instance lock.
PATTERN="$REPO/.venv/bin/trackerkeeper\$|-m trackerkeeper\$"
if pgrep -f "$PATTERN" >/dev/null; then
    echo "stopping the running tracker keeper…"
    pkill -f "$PATTERN"
    for _ in $(seq 30); do pgrep -f "$PATTERN" >/dev/null || break; sleep 0.1; done
    pkill -9 -f "$PATTERN" 2>/dev/null
fi

# The console only gets WARNING and up (trackerkeeper/log.py); the INFO stream
# — boot, checks, results — goes to the log file. Follow it from here on.
LOG="$("$PY" - <<'PY' 2>/dev/null
from PySide6.QtCore import QCoreApplication
from trackerkeeper import identity
QCoreApplication.setOrganizationName(identity.org())
QCoreApplication.setApplicationName(identity.app())
from trackerkeeper.log import log_dir
print(log_dir() / f"{identity.app()}.log")
PY
)"
if [ -n "$LOG" ]; then
    mkdir -p "$(dirname "$LOG")" && touch "$LOG"
    tail -n 0 -F "$LOG" 2>/dev/null &
    TAIL=$!
    trap 'kill $TAIL 2>/dev/null' EXIT
fi

echo "tracker keeper (dev) — $(git -C "$REPO" log --oneline -1 2>/dev/null)"
echo "UI: ${TRACKERKEEPER_UI:-auto}   log: ${LOG:-?}"
echo
"$PY" -m trackerkeeper "$@"
code=$?
echo
echo "tracker keeper exited ($code)"
exit $code
