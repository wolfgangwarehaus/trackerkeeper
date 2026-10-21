#!/bin/bash
# Add a "tracker keeper (dev)" entry to the app menu / phone launcher — DEV
# helper. It opens a terminal running dev/run.sh: this checkout, replacing any
# running copy, with the log streaming live. Production installs use the
# rendered packaging/*.desktop; this is only for running out of a checkout.
#
# Long-press (or right-click) the entry for "Phone interface" / "Desktop
# interface", which force TRACKERKEEPER_UI either way.
#
# Terminal: ghostty, else konsole. --wait-after-command / --hold keep the
# window open after the app quits so a final traceback stays readable.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY=python3
# The app id comes from the identity seam, never a literal (AGENTS.md).
APP_ID="$("$PY" -c 'from trackerkeeper import identity; print(identity.desktop_id())')" || exit 1
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.dev.desktop"
ICON="$REPO/trackerkeeper/assets/trackerkeeper.svg"

if command -v ghostty >/dev/null; then
    TERM_CMD="ghostty --wait-after-command=true \"--title=tracker keeper (dev)\" -e"
elif command -v konsole >/dev/null; then
    TERM_CMD="konsole --hold -e"
else
    echo "no ghostty or konsole found — install one, or edit TERM_CMD" >&2
    exit 1
fi
RUN="$TERM_CMD bash $REPO/dev/run.sh"

mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<ENTRY
[Desktop Entry]
Type=Application
Name=tracker keeper (dev)
Comment=Run this checkout with a live log
Exec=$RUN
Path=$REPO
Icon=$ICON
Terminal=false
Categories=Development;
StartupNotify=true
Actions=phone;desktop;

[Desktop Action phone]
Name=Phone interface
Exec=env TRACKERKEEPER_UI=quick $RUN

[Desktop Action desktop]
Name=Desktop interface
Exec=env TRACKERKEEPER_UI=widgets $RUN
ENTRY

command -v desktop-file-validate >/dev/null && desktop-file-validate "$DESKTOP_FILE"
command -v update-desktop-database >/dev/null && update-desktop-database -q "$(dirname "$DESKTOP_FILE")"
echo "installed $DESKTOP_FILE"
