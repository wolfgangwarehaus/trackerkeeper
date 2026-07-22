#!/usr/bin/env bash
# Smoke-test the built .deb inside a CLEAN, NEWER distro than the build runner —
# proves the Qt xcb Depends closure is COMPLETE on a machine that lacks the
# build-time libs (the in-runner boot can't: it built on the same host). GENERATED
# by `trackerkeeper bake` — edit the template, never this file.
#   for img in ubuntu:24.04 debian:stable; do
#     docker run --rm -v "$PWD:/src:ro" "$img" bash /src/packaging/deb/smoke_test_deb.sh
#   done
set -euo pipefail

apt-get update -qq
# Install the .deb (apt resolves its Depends) + what the boot probe / validators need.
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  /src/dist/trackerkeeper_*_amd64.deb \
  python3 xvfb desktop-file-utils appstream >/dev/null

# The COMPLETE Qt xcb DT_NEEDED closure must be pulled by the .deb's Depends; the
# boot probe below is authoritative, this loop just fast-fails with a clear name
# if Depends drifts out of sync with what the bundled plugin links.
for dep in \
  libx11-6 libx11-xcb1 libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-randr0 libxcb-render0 libxcb-render-util0 libxcb-shape0 \
  libxcb-shm0 libxcb-sync1 libxcb-util1 libxcb-xfixes0 libxcb-xkb1 \
  libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 libegl1 libgl1; do
  dpkg -s "$dep" >/dev/null
done
echo "OK: full Qt xcb DT_NEEDED closure present"

# The /usr/bin entrypoint symlink must resolve to a real executable.
test -x /usr/bin/trackerkeeper && test -x "$(readlink -f /usr/bin/trackerkeeper)"
echo "OK: /usr/bin/trackerkeeper resolves to the bundle"

# Metadata validators (catch build_deb.sh staging drift). appstream is advisory.
desktop-file-validate /usr/share/applications/io.github.wolfgangwarehaus.trackerkeeper.desktop
echo "OK: .desktop validates"
appstreamcli validate --no-net /usr/share/metainfo/io.github.wolfgangwarehaus.trackerkeeper.metainfo.xml || true

# Boot the installed bundle under Xvfb forcing the xcb plugin: a missing X
# DT_NEEDED aborts HERE (rc != 0/124) instead of in a user's session. rc 0 = clean
# exit, 124 = survived the timeout (Qt + xcb initialized). QT_DEBUG_PLUGINS names
# the missing .so in the log.
echo "Booting the installed bundle under Xvfb (xcb)…"
set +e
QT_DEBUG_PLUGINS=1 QT_QPA_PLATFORM=xcb xvfb-run -a timeout 15 /usr/bin/trackerkeeper >/tmp/boot-xcb.log 2>&1
rc=$?
set -e
if [ "$rc" != 124 ] && [ "$rc" != 0 ]; then
  echo "FAIL: xcb platform plugin did not load (rc=$rc) — a Qt DT_NEEDED is missing."
  grep -iE "cannot open shared object|Cannot load library|undefined symbol" /tmp/boot-xcb.log \
    || echo "(no 'cannot open shared object' line — inspect the full log + readelf -d the xcb plugin)"
  tail -30 /tmp/boot-xcb.log
  exit 1
fi
echo "OK: xcb platform plugin loads under Xvfb (rc=$rc)"
echo "deb smoke test passed"
