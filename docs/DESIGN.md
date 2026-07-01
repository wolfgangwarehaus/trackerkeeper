# dough — first-looks design

dough's promise isn't just "it runs everywhere" — it's **looks right on the very first
launch**, before the maker touches a pixel. These are the load-bearing defaults that make
that true. They were proven by building the first real app (butterPDF) WITH dough and
folding what worked back into the base ([docs/BACKPORT.md](BACKPORT.md)). Honour them; a
fork inherits a polished surface for free.

> Sibling of [PHILOSOPHY.md](PHILOSOPHY.md) (the *why* of fork-and-own). This is the *look*.

## The seven principles

1. **Single chrome.** The custom top bar **is** the titlebar — never doubled with a
   native one. On KDE Wayland the window stays *server-side-decorated* and a KWin
   `noborder` rule strips the decoration (this keeps compositor blur alive through a
   drag); Qt `FramelessWindowHint` is reserved for Windows (main window) and for
   transient **dialogs**. A doubled titlebar on a fresh launch is a *missing-noborder-rule*
   bug — fix it by installing the rule before show, **not** by going Qt-frameless on the
   main window (that loses blur mid-drag and leaves NVIDIA stale-blur trails).

2. **Even, balanced gutters.** Symmetric margins so content floats centered. A scrollbar
   lane reserved on one side is mirrored by an equal margin on the other — the lane is a
   designed gutter, not an afterthought.

3. **Truly-centered bars.** A centered element is centered over the **full bar width**
   (`ui_helpers.CenteredBar`), not merely between the left/right side groups — so it never
   drifts when the side groups differ in width, and re-balances on resize. A centered
   child sets `WA_TransparentForMouseEvents` so titlebar drag passes through it.

4. **Fit-to-content, non-resizable dialogs.** A `FrostedDialog` snugly fits its content
   (`SetFixedSize`) and opts into resize only via `resizable=True`. Fit first, center
   second — centering only reads correctly inside a snug, fixed-size box.

5. **Slim auto-hiding scrollbars, painted in the live ACCENT.** `AutoFadeScrollBar`: a 6px
   pill centered on the widget's *true* axis, min-length-clamped so it stays grabbable and
   never clips the lane ends, painted in `ACCENT` (not text ink) and repainting on
   `theme_changed` even while idle — so the accent is pervasively present and tracks live
   switches. Wire it onto a scroll area with `install_autofade_scrollbars()`.

6. **Frosted uniformity — no opaque widget breaks the glass.** Scroll surfaces, viewports
   and menus are made transparent so the compositor frost shows through:
   `ui_helpers.frost_scroll_surface(area)` for a scroll area + its viewport, and
   **`ui_helpers.opaque_menu()` instead of a raw `QMenu`** (a raw `QMenu` renders an
   unreadable opaque white box — it is banned).

7. **Accent present and live-switching from the first frame.** Keep the shipped
   subdued-violet default, but surface the accent on the *first painted frame* (accent
   scrollbars; at least one accent mark in the content) — not only on hover/click. The
   Settings swatches already cascade live via `AppBus.theme_changed`.

## Conventions cheat-sheet

| Want | Use | Not |
|------|-----|-----|
| A dropdown / context menu | `ui_helpers.opaque_menu(parent)` | raw `QMenu(parent)` |
| A truly-centered bar title | `ui_helpers.CenteredBar` + `set_centered()` | stretches between side groups |
| Frost showing through a scroll area | `ui_helpers.frost_scroll_surface(area)` | leaving the default opaque grey |
| Slim accent scrollbars | `ui_helpers.install_autofade_scrollbars(area)` | native scrollbars |
| A settings/alert dialog | `FrostedDialog` (fixed-size by default) | `QMessageBox` / native dialog |
| Frameless main window | leave `window.py` as-is (decorated + noborder on KDE Wayland) | `FramelessWindowHint` on the main window |

## Corners & the frost fallback (real symbols)

Two base primitives back the look above and are worth knowing by name:

- **Square corners** — every finite radius flows through `design_tokens.rad()`, which
  zeros it when the `ui/square_corners` setting is on (the pill/circle sentinel
  `RADIUS_PILL` passes through, so round controls stay round). It's baked into the
  `RADIUS_*` tokens at import; `set_square_corners()` flips the in-memory flag (the
  Settings setter persists it and shows a restart notice). A fork gets a global
  sharp/soft corner switch for free.
- **Faux-frost fallback** — where the compositor/OS can't supply real blur
  (GNOME/Wayland, Windows without Mica, KDE with the Blur effect off, macOS with
  Reduce Transparency on), a frosted body would otherwise be a dead near-opaque panel.
  `blur/_faux_frost.py`'s `FauxFrost` paints a self-contained frosted texture (soft
  blooms + film grain, deterministic, cached per size/colour) so the glass still reads
  as glass. `window.py` selects it automatically from `blur.status()`; nothing to wire
  per surface. macOS specifics live in [MACOS.md](MACOS.md).

## Per-app, not base

Some butterPDF tuning is app taste and deliberately stays out of dough: the 8px scrollbar
lane (dough's default is 12px), TopBar density (48px / 36×32 buttons), the per-app
top-bar content, and any document/PDF-specific geometry. A fork overrides these by
subclassing — the base ships comfortable, grabbable defaults.
