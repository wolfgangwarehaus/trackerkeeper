# dough on macOS — the hardware-earned gotchas

This is the distilled, dough-relevant record of what it takes to make a PySide6/Qt6
app feel native on macOS **and** ship it signed, notarized, and Store-eligible. The
lessons were paid for in real hardware time on the app dough was extracted from
(jellytoast, on an Intel MacBook Pro · macOS Sequoia 15) and in its now-private
release ops. Music/player specifics have been stripped; only the base-relevant
lessons remain.

> Companion to [DESIGN.md](DESIGN.md) (the *look*) and [BACKPORT.md](BACKPORT.md)
> (the sync record). If you touch the macOS chrome, blur, or packaging templates,
> read this first — most of these are non-obvious and re-learning them is expensive.

---

## 1. Chrome architecture — a real NSWindow, never Qt-frameless

**macOS is the one platform where dough does NOT go frameless.** On KDE Wayland the
window stays decorated with a KWin `noborder` rule; on Windows / GNOME / wlroots it's
Qt `FramelessWindowHint`. On macOS it keeps its **real NSWindow** — traffic lights,
native resize / zoom / fullscreen / tiling, and Stage Manager all keep working for
free. `window._resolve_chrome_mode()` resolves macOS to *all-False* (native chrome);
`AppWindow` never sets `FramelessWindowHint` on the Mac.

The custom look is achieved *without* dropping the frame:

- **`dough/macos_window.py`** — a **transparent titlebar + full-size content view**
  (`NSWindowStyleMaskFullSizeContentView`, `setTitlebarAppearsTransparent_`,
  `setTitleVisibility_(Hidden)`, `setTitlebarSeparatorStyleNone`). The frosted body
  flows up under the traffic lights to the native rounded top corners — no separate
  dark titlebar strip, no app-drawn corners. The chrome layout reserves a thin top
  inset (`TITLEBAR_INSET`, gated on `IS_MACOS`) so the top bar clears the stoplights.
  - `setMovableByWindowBackground_(True)` restores window dragging (the transparent
    titlebar no longer offers its own grab strip). **Gotcha:** AppKit then moves the
    window without Qt's `QWindow` learning about it, so Qt's geometry goes stale and
    anything positioned via `mapToGlobal` (menus, centered dialogs) lands hundreds of
    px off. `_install_position_sync()` observes `NSWindowDidMove` and syncs Qt's
    position back — **debounced** (a drag fires ~60×/s; syncing mid-drag fights the
    drag and freezes the UI, so it fires once the window has been still ~140ms).

- **`dough/macos_menubar.py`** — the **native global menu bar** (App / File / Edit /
  View / Window / Help). A Qt app with no `QMenuBar` reads as a half-finished port.
  Two subtleties: (1) Qt relocates About/Settings/Quit into the bold app menu by
  QAction **menu *role*** (`AboutRole`/`PreferencesRole`/`QuitRole`), *not* label
  text — so every other action must set an explicit `NoRole`, or Qt's text heuristic
  silently hoists anything that looks like "settings"/"about"/"quit". (2) Qt
  auto-adds a **Services** submenu + **About Qt**; both are end-user noise and are
  stripped via pyobjc (`_strip_app_menu_noise`, deferred a tick because Qt builds the
  native menu on the event loop). Also installs Dock-click reopen.

- **Faux-frost fallback** — when native vibrancy is off (Reduce Transparency on, or
  pyobjc absent), the body paints `dough/blur/_faux_frost.py`'s `FauxFrost` texture
  instead of a dead near-opaque panel. See §3.

---

## 2. Native vibrancy (NSVisualEffectView) — the sibling-below pattern

`dough/blur/_macos.py` is the macOS arm of the blur backend. It installs an
`NSVisualEffectView` (blending mode **behind window**, material
`UnderWindowBackground`, `.popover` for elevated popups) so the system frost shows
through Qt's translucent body — the mac-native equivalent of KWin's blur-behind.
`probe()` reports **ACTIVE**, so frosted surfaces ride it at full glass alpha.

**The load-bearing decision: sibling-BELOW, not a content-view swap.** The effect
view is inserted into Qt's *superview* (the private `NSThemeFrame`) ordered strictly
below `QNSView` via `addSubview:positioned:NSWindowBelow relativeTo:`. Qt keeps
ownership of the content-view slot.

- The naive approach — make the effect view the window's content view and re-parent
  Qt on top — demotes `QNSView` from the content-view slot. macOS then stops
  auto-sizing it (**blank margins on resize**), and `QCocoaWindow` keeps re-asserting
  `QNSView` as the content view on recreate / state change (**QTBUG-69302**), ripping
  the effect view back out and **blanking the window on activation**. This was the #1
  historical macOS bug; sibling-below kills it. This is Electron's vibrancy pattern,
  hoisted one level (in Qt the `QNSView` itself is the content view).
- **State must be pinned `Active`.** The default `FollowsWindowActiveState` washes the
  material out whenever the window isn't key — an activation-flicker symptom. Pin it.
- **Reset the corner radius on the way to fullscreen.** `corner_radius > 0` rounds the
  effect layer (mini/dialog); when the window goes edge-flush / fullscreen the caller
  passes `corner_radius=0` and the backend must `setCornerRadius_(0)` +
  `setMasksToBounds_(False)` — otherwise the layer keeps its 8px mask and the four
  screen corners clip where a desktop shows behind them.
- Insertion logs one benign `NSWindow warning: adding an unknown subview:
  NSVisualEffectView`. Expected (foreign subview in the theme frame), not a bug.
- Register the tracking entry **before** mutating the window, and roll back
  (`removeFromSuperview`) in the `except` — otherwise a throw mid-install orphans an
  untracked effect view and the next `apply()` stacks a second one. Connect the
  `destroyed` cleanup **once per widget** (a guard set), not on every off→on cycle.

**Body alpha:** vibrancy veils heavier than KWin's blur, so the shared ~67% glass
(172) reads too opaque on macOS. `theme._mac_glass_alpha()` caps it to **110 (~43%)**,
tuned by eye against KDE Plasma, applied as `min(theme_alpha, cap)` so it only ever
lightens. Env-tunable via `DOUGH_MAC_GLASS_ALPHA`.

---

## 3. Honor "Reduce Transparency" — including a *live* toggle

The HIG requires honoring System Settings → Accessibility → Display → **Reduce
Transparency**. dough does, and there's a sharp edge here:

- `probe()` returns **UNSUPPORTED** when Reduce Transparency is on, so the theme falls
  back to a near-opaque / faux-frost body instead of vibrancy.
- **The trap:** `blur.status()` is cached for the whole session, but `apply()` reads
  Reduce Transparency **live** and removes the vibrancy when it's on. So a user
  toggling it **at runtime** would strip the backdrop while the body keeps painting at
  its 43% glass alpha → a see-through-broken window. Fixed with
  `install_accessibility_observer()`: it observes
  `NSWorkspaceAccessibilityDisplayOptionsDidChange` on the main queue and re-probes
  (`status(force=True)`) + re-stamps the app, so the body drops to its near-opaque
  fallback (and back). The observer token is retained module-global or the
  observation dies immediately.
- The fallback texture is `FauxFrost` — soft lighter blooms over the body colour,
  melted by a cheap upscale + faint film grain, deterministic and cached per
  (size, base colour). Same fallback serves GNOME/Wayland, Windows-without-Mica, and
  KDE-with-blur-off — one no-compositor path for every OS.

---

## 4. Testing vibrancy on real hardware (the capture gotchas)

You cannot judge frost from a VM or from Qt's own grab:

- **`win.grab()` is blur-blind.** It renders only Qt's own painting, not the composited
  system vibrancy behind the window. Use it to check content/layout, never to judge
  frost.
- **`screencapture` needs Screen-Recording permission — attributed to the *terminal*,
  not python.** The process chain is `Terminal → shell → python → screencapture`, so
  macOS attributes the capture to **Terminal.app**. Without Screen Recording granted to
  the terminal, a full-screen or region capture returns **wallpaper only** (every app
  window stripped) and `screencapture -l<windowID>` fails with "could not create image
  from window". The window is genuinely on-screen (Qt `isVisible`, AppKit
  `occlusionState` visible) — it's the *capture path* that's blocked. Grant it in
  System Settings → Privacy & Security → Screen Recording, then **quit & reopen the
  terminal**. (The full-screen path then works without a restart; only the
  single-window `-l` path needs the relaunch.)
- **A remote framebuffer (VNC) misrepresents vibrancy** — judge the real pixels on a
  real display, or via a `screencapture` once permission is granted.
- The structural path (insert / refresh / remove without crashing) is exercised
  headlessly; the *visual* result and resize/activation behaviour must be seen on a
  real Mac.

---

## 5. Signing & notarization (Developer-ID .dmg)

dough's macOS release workflow is `.github/workflows/macos.yml` (a static file, not
templated); the bundle metadata lives in `packaging/templates/macos/**`.

- **Universal2, one fat binary.** dough ships a single `universal2` `.dmg` (arm64 +
  x86_64 in one Mach-O) rather than two native per-arch builds. Tradeoff: a universal2
  build is larger and requires universal2 wheels for every native dependency, but it's
  one artifact, one notarization, one download — simpler for a fork to reason about.
- **An honest `LSMinimumSystemVersion` floor.** Set it to the *real* minimum your
  dependencies support (PyObjC + the Qt6 you bundle), not an aspirationally low number
  — a too-low floor lets the app launch on an OS where a framework then crashes. Test
  on the floor you claim.
- **Sign inside-out; never `--deep`.** Codesign each nested Mach-O from the innermost
  dylibs/frameworks outward, then the app bundle last. Apple's `--deep` is deprecated
  for distribution and silently mis-signs nested code. **Detect Mach-O by content, not
  extension** — walk the bundle and check the Mach-O magic bytes; many bundled
  binaries have no extension or a misleading one (`.so`, no suffix), so an
  extension-based filter misses code that must be signed (→ notarization rejection).
- **Notarize via App Store Connect API key, with an Apple-ID fallback.** Primary auth
  for `notarytool` is an API key (issuer id + key id + `.p8`); the fallback is
  `APPLE_ID` + `APPLE_APP_SPECIFIC_PASSWORD` + `APPLE_TEAM_ID`. Staple the ticket to
  the `.dmg` after approval.
- **Identity flows through the templates — never a literal.** The bundle id is
  `{{ cf_bundle_id }}` / `dough.identity.cf_bundle_id()` and the app slug is
  `{{ app_slug }}`; a fork gets its own identity for free via `dough new`. **Never
  hardcode an app-id or team-id.** The team id comes from CI (`APPLE_TEAM_ID`) or, in
  build-variable contexts, from `$(AppIdentifierPrefix)` / `$(TeamIdentifierPrefix)` —
  not a literal string in a committed file.
- **Minimal Developer-ID entitlements.** Only `disable-library-validation` (so the
  bundle can load its own signed-with-a-different-cert Python/Qt dylibs) and
  `allow-dyld-environment-variables`. **Do NOT** add a JIT
  `allow-unsigned-executable-memory` entitlement — dough has no JIT'd media runtime, so
  it would only widen the attack surface and complicate hardened-runtime review.

---

## 6. Mac App Store (MAS) — the extra minefield

The Store build is the App-Sandbox variant (gated at runtime by
`platform_compat.is_macos_sandboxed()`, which also switches autostart to an
`SMAppService` login item and migrates data into the container). MAS rejects things
the Developer-ID build is fine with:

- **`disable-library-validation` is rejected / crashes under MAS.** The entitlement
  that the Developer-ID build relies on is disallowed in the sandbox — the MAS build
  must not carry it, and everything it loads has to be signed under the same
  Team ID. Budget for this being a different signing story than the `.dmg`.
- **Entitlements only on the *main* executable — `ITMS-91166`.** Apply the app's
  entitlements to the main app binary only; entitlements on a *nested* helper /
  dylib trip validation rejection **ITMS-91166** ("Invalid entitlements … nested").
- **`productbuild --sign` hangs headless → use `rcodesign`.** Building/signing the
  `.pkg` with Apple's `productbuild --sign` can hang indefinitely in a headless CI
  runner (it blocks on a keychain/UI prompt). Sign the product package with
  `rcodesign` (the Rust `apple-codesign`) instead, which is non-interactive.
- **A CPython dylib trips the `itms-services` auto-reject.** Some CPython builds ship a
  binary/string that the Store's automated scan flags as an `itms-services:` URL scheme
  and auto-rejects. Know it's a false positive on the interpreter, not your code, when
  it appears.
- **`CFBundleVersion` collisions block re-upload.** App Store Connect refuses a second
  upload with a `CFBundleVersion` it has already seen — even for a rejected build. Bump
  the build number on *every* upload attempt, not just on every release.

---

## Where the real symbols live

| Concern | Module / symbol |
|---|---|
| Transparent titlebar + full-size content, position-sync | `dough/macos_window.py` (`apply`, `TITLEBAR_INSET`, `_install_position_sync`) |
| Native global menu bar + Dock reopen | `dough/macos_menubar.py` (`install`, `set_app_name`, `_strip_app_menu_noise`) |
| Vibrancy backend (sibling-below, Reduce-Transparency, ax observer) | `dough/blur/_macos.py` (`apply`, `probe`, `install_accessibility_observer`) |
| No-blur fallback texture | `dough/blur/_faux_frost.py` (`FauxFrost`) |
| macOS body alpha cap | `dough/theme.py` (`_mac_glass_alpha`, `body_color_for`) |
| Never-frameless-on-Mac gate | `dough/window.py` (`_resolve_chrome_mode`) |
| Sandbox / MAS gate | `dough/platform_compat.py` (`is_macos_sandboxed`) |
| Notifications / autostart backends | `dough/notifications/_macos.py`, `dough/autostart/_macos.py` |
| Bundle metadata (templated) | `packaging/templates/macos/**`, release workflow `.github/workflows/macos.yml` |
