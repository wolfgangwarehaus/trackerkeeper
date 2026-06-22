# dough Backport Checkpoint — butterPDF first-looks learnings

## Status (2026-06-22)
- ✅ **DONE (committed `2719dd8`):** ranks 1–8 — the clean design-default backports
  (resize-filter slider-yield; AutoFadeScrollBar slim-accent-pill set + `PILL_LANE`;
  `CenteredBar`; `frost_scroll_surface`; `settings.auto_hide_scrollbars`; FrostedDialog
  frameless-gate + fit-to-content; `TopBar(CenteredBar)`). dough: 100 passed, ruff clean.
- ✅ **DONE:** rank 11 — `docs/DESIGN.md` (the seven first-looks principles).
- ⏭ **DEFERRED → the "chrome-machinery pass" (next session):** rank 9 (`drag_repaint`
  sub-package) + rank 10 (generic wmclass `keep_above`). Both are KWin assets that also
  require `dough new` to re-namespace them on fork (the effect id/dir/metadata/main.js
  matcher AND the keep_above wmclass — note the whole-word `\bdough\b` replace does NOT
  catch `dough_dragrepaint`), paired with the `setDesktopFileName` reverse-DNS Wayland
  wiring, and a real-KDE-Wayland smoke. Do them together.

## What we learned (verified against dough source)

butterPDF, the first real fork built WITH dough, surfaced a batch of first-looks polish and one architectural fork in the road. I verified every catalog claim against the live dough tree:

- `window.py:87` checks only `QAbstractButton` (no `QAbstractSlider` import) — the scrollbar-on-the-resize-edge grab bug is real.
- `window.py:177-182` is **already architecturally correct**: FramelessWindowHint only on Windows; KDE Wayland stays decorated (`_borderless` with no Qt frameless flag). This is the jellytoast architecture and must be preserved.
- `frosted_dialog.py:64` gates frameless on `is_kde_wayland()` **alone**, while `window.py:181` gates on `is_kde_wayland() and not native_window_border` — a genuine consistency bug; the dialog and main window disagree on KDE Wayland today.
- `settings.py` has `native_window_border` (67-73) but **no** `auto_hide_scrollbars`.
- `AutoFadeScrollBar` paints `TEXT`, `PILL_ALPHA=110`, hardcoded hover `180`, no `PILL_THICKNESS`/`PILL_MIN_LENGTH`, no true-center fix.
- `opaque_menu` already ships (ui_helpers.py:1358); `top_bar.py` has no `CenteredBar`; no `drag_repaint`/`keep_above` dirs; `app.py:118` passes the bare slug to `setDesktopFileName`; `docs/` has PHILOSOPHY.md but no DESIGN.md.

## The frameless decision (load-bearing)

**dough's main-window chrome = decorated-on-KDE-Wayland + KWin noborder rule + drag_repaint — NOT Qt FramelessWindowHint.** Leave `window.py`'s frameless gating exactly as-is. Do **not** backport butterPDF's `if self._borderless: setWindowFlag(FramelessWindowHint)`. That was a band-aid for "the noborder rule is absent on a fresh launch," and it causes the artifacts the correct path avoids: an undecorated (Qt-frameless) window loses KWin blur mid-drag and leaves stale-blur trails (NVIDIA-EGL / KWin bug 455526/457727); a decorated window keeps blur through a drag. The right fix for the fresh-launch gap is to **install the noborder rule before show** (keep_above), not to switch to Qt frameless.

The two missing pieces that make the decorated-frameless approach work end-to-end:
1. **drag_repaint** — a clean dough-base port (rename to `dough_dragrepaint`, env var `DOUGH_NO_DRAG_REPAINT`, package-data, `sync()` in run_app **after** `win.show()`). No dependency on setDesktopFileName (matches on title/caption). Lands independently/now.
2. **A new generic wmclass-based keep_above** — port jellytoast's module, stripped of its title-list machinery, writing a single `noborder` Force rule scoped by **wmclass only** (title-agnostic, survives a fork renaming its title). Installed in run_app **before** `win.show()`. Depends on `setDesktopFileName` being the reverse-DNS app-id, so **finish that wiring in the same pass** — the rule's wmclass and the real app_id must agree.

FramelessWindowHint stays fine for **dialogs** (transient/modal, no sustained-drag blur concern) — gate it on `native_window_border`, but don't let that spill into the main window.

## Backport plan (ranked by value × safety)

**Clean dough-base wins first (do these now, independent of the chrome work):**
1. **QAbstractSlider yield** in `_ResizeEdgeFilter` (window.py) — trivial, strict superset, can't regress.
2. **AutoFadeScrollBar slim accent pill** — PILL_THICKNESS=6, PILL_MIN_LENGTH=44 with end-clamp, true-center on widget width, PILL_ALPHA 110→190, hover 180→255, paint ACCENT not TEXT, + a `theme_changed→update()` hook to kill idle-accent lag.
3. **PILL_LANE=12 as a class constant** (NOT butterPDF's 8px) — bundle with #2.
4. **settings.auto_hide_scrollbars** toggle (key `ui/auto_hide_scrollbars`, default True).
5. **FrostedDialog frameless gate** → `not native_window_border` (fixes the dialog/main-window inconsistency).
6. **FrostedDialog fit-to-content** — `resizable=False` default + `SetFixedSize` (land after/with #5; centering only reads in a snug box).
7. **CenteredBar primitive** into ui_helpers; `TopBar(CenteredBar)`. Adopting a centered child in the stock TopBar is a separate optional call.
8. **frost_scroll_surface** generic helper (area + viewport transparent, palette roles cleared on both).

**Bigger/riskier, sequence deliberately:**
9. **drag_repaint** sub-package (rename + package-data + run_app `sync()` after show).
10. **Generic wmclass keep_above** package + run_app wiring before show — **paired with the setDesktopFileName Wayland wiring**; smoke-test on real KDE Wayland.
11. **docs/DESIGN.md** — enshrine the seven first-looks principles (write after the code primitives land so it indexes real dough symbols); record the `opaque_menu`-not-raw-`QMenu` convention here and in AGENTS.md.

## FASTER findings (act on now, don't over-engineer the rest)

- **Move `drag_repaint.sync()` off the pre-show line** — defer to after `win.show()` / a `singleShot`. Its subprocess + file-copy must not sit in front of the first paint; the effect only needs to be live for the first drag.
- **Add `theme_changed→.update()`** in `install_autofade_scrollbars` so a live accent switch repaints the idle pill.
- run_app is otherwise already lean: deferred heavy imports, pre-widget override load (no re-stamp flash), post-show blur, 120ms resize-debounced re-blur. Confirm and keep; HiDPI + QApplication construction dominate cold-open and are unavoidable.

## Leave in butterPDF (do NOT backport)

- The `FramelessWindowHint`-on-every-borderless-platform change (the shortcut).
- The TopBar PDF content (Open/Edit/Sign menu, doc-name title, gear-left, 48→40 density, 32×28 buttons).
- 8px lane width, min_width 420→300, the THEME/ACCENT/FONT example rows, blur_corner_radius=8.
- frost_scroll_surface's QtPdf bits (the `QPdfView` selector literal + bezel/margin geometry).

## Fork-rename note

Both KWin assets are per-app namespaced (effect id `dough_dragrepaint`; noborder rule `wmclass` = app slug). `dough new` must rewrite **both** on rename — the effect id/dir/metadata/main.js matcher AND the keep_above wmclass. butterPDF is the proof case: it renamed the effect to `butterpdf_dragrepaint` but never gained keep_above (it took the FramelessWindowHint shortcut instead).