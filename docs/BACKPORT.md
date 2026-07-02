# dough Backport Checkpoint — butterPDF first-looks learnings

## Status (2026-06-22)
- ✅ **DONE (committed `2719dd8`):** ranks 1–8 — the clean design-default backports
  (resize-filter slider-yield; AutoFadeScrollBar slim-accent-pill set + `PILL_LANE`;
  `CenteredBar`; `frost_scroll_surface`; `settings.auto_hide_scrollbars`; FrostedDialog
  frameless-gate + fit-to-content; `TopBar(CenteredBar)`). dough: 100 passed, ruff clean.
- ✅ **DONE:** rank 11 — `docs/DESIGN.md` (the seven first-looks principles).
- ✅ **DONE (2026-07-02, task A1) — the "chrome-machinery pass":** rank 9 (`drag_repaint`)
  + rank 10 (the noborder rule, shipped as `dough/noborder/`). **Two design changes made
  both self-standing, retiring the deferral's prerequisites:**
  - **`dough new` re-namespacing eliminated** — instead of hardcoding `dough_dragrepaint`
    + a `dough` wmclass and asking scaffold to rewrite them (the fragile `\bdough\b` miss),
    the effect ships as a `{{app_id}}` **template** rendered from `dough.identity.app()` at
    install (`drag_repaint/_kwin.py`), and the noborder rule matches `identity.app()` at
    runtime. A fork inherits both correctly with **zero scaffold edits** (proven: a
    simulated `butterpdf` identity renders `butterpdf_dragrepaint` + a `butterpdf` matcher).
  - **`setDesktopFileName` dependency dropped** — the noborder rule uses a **substring**
    wmclass match (`wmclassmatch=2`), so if the cross-cutting §2 later switches
    `setDesktopFileName` to the reverse-DNS `desktop_id()` (`io.github.owner.dough`, which
    still *contains* the slug), the rule keeps matching. A1 no longer has to land with §2.
  - Wired in `run_app`: noborder reconciled BEFORE `show` (install unless
    `native_window_border`), `drag_repaint.sync()` AFTER `show`. 52 tests; the install/
    uninstall machinery ran clean on a real KDE Wayland session. **Only the VISUAL smoke
    remains** (single chrome / blur-survives-drag / no NVIDIA trails — needs eyes on the
    running app).

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

---

## macOS absorption (jellytoast → dough, `de045ad` → HEAD)

A second sync, orthogonal to the first-looks backport above: pulling jellytoast's
**mature macOS platform + packaging** into the dough base, so the whole warehaus
app family inherits a native, signable, Store-eligible Mac target. The
hardware-earned gotchas are captured in [MACOS.md](MACOS.md) so they don't stay
locked in jellytoast's now-private ops repo.

### What landed
- **Real vibrancy blur backend** — `dough/blur/_macos.py` is now the live
  `NSVisualEffectView` **sibling-below** backend (was a stub reporting UNSUPPORTED).
  `probe()` → ACTIVE; pinned `Active` state; corner-radius reset for fullscreen;
  install-order rollback + once-per-widget `destroyed` hook; a live
  `install_accessibility_observer()` for runtime Reduce-Transparency toggles.
- **Native chrome** — `dough/macos_window.py` (transparent titlebar + full-size
  content view + debounced `NSWindowDidMove` position-sync) and
  `dough/macos_menubar.py` (global menu bar by QAction *role*, Services/About-Qt
  strip, Dock-click reopen, `CFBundleName` override for from-source runs).
- **Platform backends** — `dough/notifications/_macos.py` (UNUserNotificationCenter
  banner + osascript fallback), `dough/autostart/_macos.py` (SMAppService login item
  under MAS / LaunchAgent otherwise) and `dough/autostart/_msix.py` (the Windows MSIX
  peer absorbed in the same pass).
- **platform_compat probes** — `is_macos_sandboxed()` (the MAS/App-Sandbox gate,
  macOS analog of `is_msix_packaged()`).
- **Theme mac arms** — `_mac_glass_alpha()` (110 vibrancy cap) + the `IS_MACOS`
  branches in `body_color_for()` (glass cap when ACTIVE; dialog near-opaque bump under
  the faux-frost fallback).
- **faux-frost** — `dough/blur/_faux_frost.py`'s `FauxFrost` is the shared no-blur
  fallback texture (GNOME/Wayland, Windows-no-Mica, KDE-blur-off, **and** macOS
  Reduce-Transparency), painted by `window.py` instead of a dead panel.
- **square-corners + live-font** — `design_tokens.rad()` / `set_square_corners()` (the
  `ui/square_corners` QSetting baked into the `RADIUS_*` tokens at import, pill
  sentinel passes through) alongside the existing `font_scale` seam.
- **GNOME frameless refactor** — `window._resolve_chrome_mode()` now returns a
  three-way `(win_frameless, linux_frameless, borderless)`; non-KDE Linux Wayland
  (GNOME / wlroots) gets its own Qt-`FramelessWindowHint` / CSD arm
  (`startSystemMove`/`startSystemResize`), distinct from the KDE-Wayland
  decorated-noborder path.

### Deliberate decisions
- **Frameless decision PRESERVED (load-bearing).** macOS is the one platform that is
  **never Qt-frameless** — it keeps its real NSWindow (`_resolve_chrome_mode` → all
  False on Mac). KDE Wayland stays decorated + KWin noborder. The GNOME/Windows
  frameless arms are unchanged. None of the mac work touched this.
- **Flatpak RETIRED** — not carried into the mac/packaging matrix (matches the standing
  "skip Flathub" call in the status memory).
- **media_controls EXCLUDED** — jellytoast's `MPNowPlayingInfoCenter` /
  `MPRemoteCommandCenter` transport integration is music-specific and deliberately
  stays out of the base. No mpv/libmpv; no JIT `allow-unsigned-executable-memory`
  entitlement.
- **`cf_bundle_id` convention** — macOS identity single-sources through
  `dough.identity.cf_bundle_id()` / the `{{ cf_bundle_id }}` + `{{ app_slug }}`
  template vars; **no literal app-id or team-id** in any committed file (team id via
  the `APPLE_TEAM_ID` CI secret / `$(TeamIdentifierPrefix)`).
- **`DOUGH_*` env seam closed** — the macOS identity has **no** `DOUGH_*` env override;
  it flows only through `identity` + the templates. (The `DOUGH_*` family stays a
  dev-diagnostic seam — `DOUGH_MAC_GLASS_ALPHA`, `DOUGH_BLUR_FORCE`, `DOUGH_OPAQUE` —
  never an identity/packaging input.)
- **universal2** — a single fat `.dmg` (arm64 + x86_64), not two native per-arch
  builds (guardrail D7).