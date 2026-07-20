# The agent test bridge

Every dough app is born **drivable by an agent**. `DOUGH_TEST_BRIDGE=1` opens
a dev-only, per-user local socket (`dough/test_bridge.py`) whose JSON commands
run on the GUI thread — so a Claude Code session (or any script) can click
real controls, read the widget tree, flip settings, take screenshots, and read
back state, deterministically, on every platform. This is the machinery behind
jellytoast's autonomous QA legs on KDE Wayland, Windows, and macOS; dough
ships it generic so a fork inherits it on day one.

Why a socket instead of synthetic OS input: on Wayland (and in offscreen CI)
synthetic pointer/key events are unreliable or impossible. The bridge instead
posts **in-process Qt events** (`QTest`) and reads the same state the UI reads
— no compositor round-trip, no flaky coordinates.

**SECURITY**: `eval`/`exec` run arbitrary Python in-process. The socket is
user-private (0600 / per-user pipe ACL) and only listens when the env var is
set. Never enable it in a shipped build.

## Launching

```bash
# Linux / macOS — TMPDIR=/tmp is load-bearing: Qt materialises the socket
# under $TMPDIR, and server + client must share it (macOS gives every context
# a PRIVATE per-user temp dir; sandboxed/systemd launches redirect it on
# Linux too). Pin both sides:
TMPDIR=/tmp DOUGH_TEST_BRIDGE=1 python -m dough &   # wait for the window

# Windows (PowerShell) — named pipes, no TMPDIR concern:
$env:DOUGH_TEST_BRIDGE=1; python -m dough
```

The socket name is `{identity.app()}-test-bridge-{user}` — it follows the
identity seam, so a renamed fork gets its own socket with zero edits.

## Driving

`dev/ctl.py` is the one-shot client: `op` then `key=value` args (values parse
as JSON where they can). `eval`/`exec` take the code as one positional arg.

```bash
TMPDIR=/tmp python dev/ctl.py ping
TMPDIR=/tmp python dev/ctl.py windows                      # top-level windows
TMPDIR=/tmp python dev/ctl.py tree depth=4                 # the widget map
TMPDIR=/tmp python dev/ctl.py click object=settingsButton  # objectName OR accessible name
TMPDIR=/tmp python dev/ctl.py set_text object=searchInput text="hello"
TMPDIR=/tmp python dev/ctl.py screenshot path=/tmp/shot.png
TMPDIR=/tmp python dev/ctl.py get_setting key=ui/theme_mode
TMPDIR=/tmp python dev/ctl.py set_setting key=ui/theme_mode value=dark
TMPDIR=/tmp python dev/ctl.py theme mode=frosted_light     # sets + re-stamps live
TMPDIR=/tmp python dev/ctl.py raise
TMPDIR=/tmp python dev/ctl.py eval "win.windowTitle()"
TMPDIR=/tmp python dev/ctl.py exec "bus.show_settings.emit()"
TMPDIR=/tmp python dev/ctl.py quit
```

Built-in ops: `ping`, `windows`, `tree`, `click`, `set_text`, `screenshot`,
`get_setting`, `set_setting`, `theme`, `raise`, `quit`, plus the `eval`/`exec`
escape hatch (namespace: `app`, `win`, `bus`, `settings`, `get_settings`,
`QApplication`, `QTest`, `Qt`, `QPoint` — extendable, see below).

`click` and `set_text` resolve widgets by `objectName` first, then
`accessibleName` — so the accessibility naming rule (docs/ACCESSIBILITY.md)
pays twice: everything named for a screen reader is addressable by an agent.

## Screenshots: grab() is blur-blind

The default `screenshot` op uses `QWidget.grab()`, which renders the widget's
**own painting** — compositor effects (KWin blur, Acrylic, vibrancy) never
appear in the shot, so a frosted surface looks like its translucent fallback.
That's fine for layout / content / theme checks (and it works offscreen in
CI), which is why it's the base default. **Never use it to judge frost** — a
lesson jellytoast's QA learned the hard way. To capture the real composited
screen, use the OS tool (`spectacle` on KDE, `screencapture` on macOS, a DXGI
grabber on Windows) — or override the op with a compositor-real backend for
your platform:

```python
test_bridge.register_command("screenshot", my_compositor_screenshot)
```

The command registry is the platform hook: re-registering a built-in name
replaces it.

## Extending with app commands

Register commands in your app code before `run_app` (module import is enough
— the registry is process-global):

```python
from dough import test_bridge

def _open_document(bridge, args):
    # bridge.app / bridge.win are the live objects; runs on the GUI thread.
    AppBus.get().files_received.emit([args["path"]])
    return args["path"]                # JSON-coerced into "result"

test_bridge.register_command("open_document", _open_document)
```

```bash
python dev/ctl.py open_document path=/tmp/report.pdf
```

A handler that raises becomes a structured `{"ok": false, "error",
"traceback"}` response — the agent sees the real stack, not a hang.

For late-bound eval/exec names (controllers built after first paint), pass a
`namespace_factory` when constructing `TestBridge` yourself, or just reach
them through `win` attributes.

## The QA-session pattern

How jellytoast runs autonomous QA legs, distilled to the reusable idioms:

- **A shared brief + a platform brief.** One doc holds how to drive and the
  platform-agnostic checklist; a small per-OS doc adds native checks and that
  platform's historical bugs. The agent reads both, drives the app, captures
  evidence, and writes triaged findings (P1 blocker / P2 should-fix / P3
  polish) — it reports; the maker decides.
- **Sweep every surface in both themes.** Script navigation over the bridge
  (`theme mode=…` + your app's nav commands), screenshot each surface, then
  actually **read the images** and assess against the checklist — don't just
  collect them.
- **Let the app settle client-side.** Never drive `app.processEvents()` or
  `QTest.qWait()` through `eval`/`exec` — spinning a nested event loop inside
  a handler can tear a socket down on a nested stack (a real SIGSEGV class;
  the bridge guards against it by refusing re-entrant handling, so a nested
  RPC would just stall anyway). Instead `time.sleep(0.4)` in the *client*
  between calls: the app's own loop keeps running and deferred builds land.
- **Restore what you flip.** `set_setting` writes the user's real config —
  save the old value first and put it back (theme mode especially).
- **Leave nothing running.** Close the app (`quit`) when the session ends.
- **Fix small drive-breakage in place.** If a nav call in your harness drifted
  from the app, fix the harness call, note it, re-run — don't skip the surface.

## Testing

`tests/test_bridge.py` boots the app offscreen as a real subprocess with the
bridge on and drives ping / tree / click / set_text / settings / theme /
screenshot / a registered custom command over the actual socket — the
production shape (in-process both-ends would deadlock: the server answers on
the same GUI thread a blocking client would starve).
