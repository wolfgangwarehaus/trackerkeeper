"""``trackerkeeper rig`` — rig up the app and probe what the platform actually saw.

The testing half of the pipeline: the unit suite proves the code, but chrome
regressions live in the compositor (a wrong app_id, a titlebar flash, a lost
blur) where only a REAL session can testify. This module productizes those
probes so any session — a maker, an AI agent, CI — can rig the app up and
read back ground truth instead of eyeballing.

    python -m trackerkeeper.rig boot            # offscreen boot smoke (any machine, CI)
    python -m trackerkeeper.rig probe           # live KDE probe: app_id / noborder / X11 class
    python -m trackerkeeper.rig shot [-o f.png] # screenshot the live window (visual review)
    python -m trackerkeeper.rig baseline        # visual-bump gate: grabs vs the goldens
    python -m trackerkeeper.rig baseline --update   # (re)write the goldens

``boot`` runs everywhere (it's the CI smoke, callable locally). ``probe`` and
``shot`` need a real KDE Plasma session and decline cleanly elsewhere (exit
2) — other desktops can grow their own probes behind the same verbs.

``baseline`` grabs the window + the settings dialog OFFSCREEN at a fixed size
under a scratch identity (so the maker's saved theme/accent can't skew them)
and compares against the goldens in ``tests/baselines/``. The diff is
AA-tolerant (exact-equal fast path, else a downscaled per-pixel compare).
It's a LOCAL gate — goldens are machine-truthful (fonts differ across
machines), so run it where they were baked; the wind-down ritual is the
natural moment. A drift means a visual bump: eyeball it, then either fix the
regression or bless it with ``--update``.

All probes launch the app as a subprocess (``python -m <package>``), observe,
then kill it — nothing here imports the app into the current process, so the
rig can't contaminate what it measures.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# The package this rig ships in — a fork's whole-word rename keeps this correct.
# (__package__, not __name__: under ``python -m <pkg>.rig`` __name__ is __main__.)
_PKG = (__package__ or "trackerkeeper").split(".")[0]

_KWIN_PROBE_JS = """\
workspace.windowList().forEach(function (w) {
    print("RIGPROBE class=" + w.resourceClass + " caption=" + w.caption
          + " noBorder=" + w.noBorder);
});
"""


def _qdbus() -> str | None:
    return shutil.which("qdbus6") or shutil.which("qdbus")


def _is_kde_session() -> bool:
    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def _launch_app(extra_env: dict | None = None) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.Popen(
        [sys.executable, "-m", _PKG],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _kwin_windows(qdbus: str) -> list[str]:
    """Load a one-shot KWin script that prints every window's class/caption/
    noBorder, run it, and read the lines back from the user journal."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(_KWIN_PROBE_JS)
        js = f.name
    name = f"{_PKG}_rig_probe"
    try:
        subprocess.run([qdbus, "org.kde.KWin", "/Scripting",
                        "org.kde.kwin.Scripting.unloadScript", name],
                       capture_output=True)
        out = subprocess.run([qdbus, "org.kde.KWin", "/Scripting",
                              "org.kde.kwin.Scripting.loadScript", js, name],
                             capture_output=True, text=True)
        sid = out.stdout.strip()
        ran = subprocess.run([qdbus, "org.kde.KWin", f"/Scripting/Script{sid}",
                              "org.kde.kwin.Script.run"], capture_output=True)
        if ran.returncode != 0:  # older KWin exposes /<id> instead
            subprocess.run([qdbus, "org.kde.KWin", f"/{sid}",
                            "org.kde.kwin.Script.run"], capture_output=True)
        time.sleep(1.0)
        subprocess.run([qdbus, "org.kde.KWin", "/Scripting",
                        "org.kde.kwin.Scripting.unloadScript", name],
                       capture_output=True)
        j = subprocess.run(
            ["journalctl", "--user", "-t", "kwin_wayland",
             "--since", "15 seconds ago", "-o", "cat"],
            capture_output=True, text=True)
        return [ln for ln in j.stdout.splitlines() if "RIGPROBE" in ln]
    finally:
        Path(js).unlink(missing_ok=True)


def cmd_boot() -> int:
    """Offscreen boot smoke — the app + its settings dialog construct, show,
    and pump events with no display. The exact smoke CI runs, callable here."""
    code = (
        "import sys\n"
        "from PySide6.QtCore import QTimer\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication(sys.argv)\n"
        f"app.setApplicationName({_PKG!r}); app.setOrganizationName({_PKG!r})\n"
        f"import {_PKG}.app as A\n"
        f"from {_PKG}.window import AppWindow\n"
        f"w = AppWindow(title={_PKG!r}); w.set_content(A._placeholder()); w.show()\n"
        "app.processEvents()\n"
        f"from {_PKG}.settings_dialog import SettingsDialog\n"
        "SettingsDialog(w).show(); app.processEvents()\n"
        "QTimer.singleShot(0, app.quit); app.exec()\n"
        "print('boot smoke OK')\n"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-c", code], env=env)
    return r.returncode


def cmd_probe() -> int:
    """Launch the app on the LIVE desktop and read back what the compositor
    saw: the Wayland app_id must equal ``identity.desktop_id()`` (the taskbar
    icon association), and the noborder state is reported. Then the X11 leg:
    ``WM_CLASS`` must carry the bare slug and ``_KDE_NET_WM_DESKTOP_FILE`` the
    desktop-id (both association paths, per docs — verified 2026-07-03)."""
    qdbus = _qdbus()
    if not (_is_kde_session() and qdbus and shutil.which("journalctl")):
        print("probe: needs a live KDE Plasma session (+qdbus/journalctl) — declining.")
        return 2

    from importlib import import_module

    ident = import_module(f"{_PKG}.identity")
    want_id = ident.desktop_id()
    slug = ident.app()
    failures: list[str] = []

    # ── Wayland leg ──────────────────────────────────────────────────────
    proc = _launch_app()
    try:
        time.sleep(4)
        lines = [ln for ln in _kwin_windows(qdbus) if f"class={want_id} " in ln
                 or f"class={slug} " in ln]
    finally:
        proc.terminate()
    if not lines:
        failures.append("wayland: the app window never appeared to KWin")
    else:
        ln = lines[-1]
        print(f"wayland: {ln.split('RIGPROBE ', 1)[-1]}")
        if f"class={want_id} " not in ln:
            failures.append(f"wayland: app_id != desktop_id() ({want_id})")

    # ── X11 (XWayland) leg ───────────────────────────────────────────────
    if shutil.which("xprop"):
        proc = _launch_app({"QT_QPA_PLATFORM": "xcb"})
        try:
            time.sleep(4)
            x = subprocess.run(
                ["xprop", "-name", ident.display_name(),
                 "WM_CLASS", "_KDE_NET_WM_DESKTOP_FILE"],
                capture_output=True, text=True)
        finally:
            proc.terminate()
        print("x11:", "; ".join(x.stdout.split("\n")[:2]).strip() or "(no window)")
        if f'"{slug}"' not in x.stdout:
            failures.append(f"x11: WM_CLASS does not carry the slug ({slug})")
        if f'"{want_id}"' not in x.stdout:
            failures.append(f"x11: _KDE_NET_WM_DESKTOP_FILE != {want_id}")
    else:
        print("x11: xprop not installed — leg skipped")

    if failures:
        for f_ in failures:
            print(f"FAIL {f_}")
        return 1
    print("probe: PASS")
    return 0


def cmd_shot(out: str | None) -> int:
    """Screenshot the live app window (KDE spectacle) so a visual bump can be
    reviewed — by eyes or by an AI reading the file. The app is launched,
    captured active, and killed."""
    if not (_is_kde_session() and shutil.which("spectacle")):
        print("shot: needs a live KDE Plasma session with spectacle — declining.")
        return 2
    dest = out or f"{_PKG}-rig-shot.png"
    proc = _launch_app()
    try:
        time.sleep(4)
        r = subprocess.run(["spectacle", "-abn", "-o", dest], capture_output=True)
    finally:
        proc.terminate()
    if r.returncode != 0 or not Path(dest).is_file():
        print("shot: capture failed")
        return 1
    print(f"shot: {dest}")
    return 0


# ── the visual-bump gate ────────────────────────────────────────────────────

_BASELINE_SHOTS = ("window", "settings")
_DRIFT_BUDGET = 0.005  # >0.5% of (downscaled) pixels changed = a visual bump


def _repo_root() -> Path:
    """The checkout root (nearest pyproject.toml above this file) — the gate's
    goldens belong to the REPO, never to whatever directory the maker happens
    to run the ritual from."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()  # installed-wheel fallback; baseline is a checkout ritual


def _grab_shots(out_dir: Path) -> int:
    """Deterministic offscreen grabs: the main window + the settings dialog at
    a fixed size, under a SCRATCH identity so the maker's persisted theme,
    accent, and font scale can't leak into the pixels — and a SCRUBBED Qt
    environment (QT_SCALE_FACTOR, QT_FONT_DPI, …) so a stray shell export
    can't double the grab size or poison a --update."""
    code = (
        "import sys\n"
        f"import {_PKG}\n"
        f"{_PKG}.configure(org={_PKG + '_rig'!r}, app={_PKG + '_rig_baseline'!r})\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication(sys.argv)\n"
        f"import {_PKG}.app as A\n"
        f"from {_PKG}.window import AppWindow\n"
        f"w = AppWindow(title={_PKG!r}); w.resize(1100, 760)\n"
        "w.set_content(A._placeholder()); w.show(); app.processEvents()\n"
        f"w.grab().save({str(out_dir)!r} + '/window.png')\n"
        f"from {_PKG}.settings_dialog import SettingsDialog\n"
        "d = SettingsDialog(w); d.show(); app.processEvents()\n"
        f"d.grab().save({str(out_dir)!r} + '/settings.png')\n"
        "print('grabbed')\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("QT_")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    return subprocess.run([sys.executable, "-c", code], env=env).returncode


def _image_drift(a_path: Path, b_path: Path, *, tol: int = 8) -> float:
    """Fraction of pixels that changed. Byte-identical → 0.0 fast. Otherwise
    both images are smooth-scaled to 200×200 and compared per pixel with a
    per-channel tolerance — antialiasing wobble doesn't count, real layout,
    colour, or chrome changes do. Size mismatch = total drift (1.0)."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QImage

    a, b = QImage(str(a_path)), QImage(str(b_path))
    if a.isNull() or b.isNull() or a.size() != b.size():
        return 1.0
    fmt = QImage.Format.Format_RGBA8888
    a, b = a.convertToFormat(fmt), b.convertToFormat(fmt)
    if bytes(a.constBits()) == bytes(b.constBits()):
        return 0.0
    small = (
        img.scaled(200, 200, _Qt.AspectRatioMode.IgnoreAspectRatio,
                   _Qt.TransformationMode.SmoothTransformation)
        for img in (a, b)
    )
    ba, bb = (bytes(i.constBits()) for i in small)
    total = len(ba) // 4
    differing = sum(
        1
        for i in range(0, len(ba), 4)
        if max(abs(ba[i + c] - bb[i + c]) for c in range(3)) > tol
    )
    return differing / total


def cmd_baseline(update: bool, base_dir: str | None) -> int:
    baselines = Path(base_dir) if base_dir else _repo_root() / "tests" / "baselines"
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        if _grab_shots(tmp) != 0:
            print("baseline: the grab boot failed")
            return 1
        if update:
            baselines.mkdir(parents=True, exist_ok=True)
            for shot in _BASELINE_SHOTS:
                (baselines / f"{shot}.png").write_bytes((tmp / f"{shot}.png").read_bytes())
            print(f"baseline: goldens written to {baselines}/")
            return 0
        failures = 0
        for shot in _BASELINE_SHOTS:
            golden = baselines / f"{shot}.png"
            if not golden.is_file():
                print(f"  ? {shot}: no golden — run `baseline --update` once to bake them")
                failures += 1
                continue
            drift = _image_drift(golden, tmp / f"{shot}.png")
            ok = drift <= _DRIFT_BUDGET
            print(f"  {'✓' if ok else '✗'} {shot}: drift {drift:.2%}"
                  + ("" if ok else "  ← a visual bump: eyeball it, fix or --update"))
            failures += 0 if ok else 1
    print("baseline: PASS" if not failures else "baseline: FAIL")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=f"{_PKG}-rig", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("boot", help="offscreen boot smoke (runs anywhere)")
    sub.add_parser("probe", help="live KDE probe: app_id / noborder / X11 class")
    shot = sub.add_parser("shot", help="screenshot the live window")
    shot.add_argument("-o", "--out", default=None, help="output PNG path")
    base = sub.add_parser("baseline", help="visual-bump gate: offscreen grabs vs the goldens")
    base.add_argument("--update", action="store_true", help="(re)write the goldens")
    base.add_argument("--dir", default=None, help="goldens dir (default: tests/baselines)")
    args = ap.parse_args(argv)
    if args.cmd == "boot":
        return cmd_boot()
    if args.cmd == "probe":
        return cmd_probe()
    if args.cmd == "baseline":
        return cmd_baseline(args.update, args.dir)
    return cmd_shot(args.out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
