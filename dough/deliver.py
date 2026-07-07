"""``dough deliver`` — the Delivery-phase walkthroughs (docs/DELIVERY.md).

The channel machinery exists (the matrix, ``release.yml``, the dormant
per-channel workflows); this is the guided activation. State is DETECTED from
reality — git tags, the gh CLI, the channel endpoints — never recorded, so
every run is idempotent and can't drift. Steps a human must own (accounts,
secrets, the publish click) are printed as exact 30-second actions, never
performed.

    python -m dough.deliver              # the board: every channel, its state
    python -m dough.deliver pypi         # walk ONE channel's next steps
    python -m dough.deliver --release    # the update lap (the Improvements loop)

Output is plain text designed to be read by the maker's AI agent as much as by
the maker: each pending step names its kind (local / account / secret /
publish) and carries the exact command or URL. Probes are best-effort — no
network, no ``gh`` auth, no git remote all degrade to ``?`` (unknown), never a
crash. Secret VALUES are never read or printed, only secret NAMES.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from functools import cached_property
from typing import Callable

# The package this tool ships in — a fork's whole-word rename keeps it correct.
_PKG = (__package__ or "dough").split(".")[0]

_HTTP_TIMEOUT = 6


# ── probes (module-level so tests fake them wholesale) ─────────────────────


def _run(cmd: list[str]) -> str | None:
    """stdout of a command, or None on any failure (missing binary included)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def _git(*args: str) -> str | None:
    """git against THIS checkout (the repo the board reports on) — never the
    caller's CWD, which may be a different repo with its own tags."""
    from dough import metadata

    root = metadata._find_pyproject().parent
    return _run(["git", "-C", str(root), *args])


def _gh_json(args: list[str]):
    """Parsed JSON from a ``gh`` call, or None (gh missing / unauthed / 404)."""
    out = _run(["gh", *args])
    if out is None:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


# Sentinel: the endpoint answered and the name does NOT exist (HTTP 404) —
# crucially different from "couldn't reach it" (None): 404 means the name is
# FREE, None means we can't say anything.
_NOT_FOUND = object()


def _http_json(url: str):
    """Parsed JSON from a GET; _NOT_FOUND on a definitive 404; None on any
    other failure (offline-safe)."""
    try:
        with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return _NOT_FOUND if e.code == 404 else None
    except Exception:
        return None


# ── the detected world ──────────────────────────────────────────────────────


@dataclass
class Ctx:
    """Everything the steps detect against, probed lazily and cached — one
    probe per fact per run, however many steps consult it."""

    slug: str
    repo: str  # owner/name
    display_name: str
    # The PyPI DISTRIBUTION name ([project].name) — distinct from the slug when
    # the bare name is squatted (dough publishes as dough-base; the import and
    # every other channel keep the slug).
    dist: str = ""

    def __post_init__(self) -> None:
        self.dist = self.dist or self.slug

    @cached_property
    def tag(self) -> str | None:
        out = _git("tag", "--list", "v*", "--sort=-v:refname")
        return out.splitlines()[0].strip() if out and out.strip() else None

    @cached_property
    def gh_ok(self) -> bool:
        """Can gh answer at all (installed + authed)? Steps that would read a
        gh None as a real absence must consult this first — unauthed/offline is
        UNKNOWN (?), not 'doesn't exist'."""
        return _run(["gh", "auth", "status"]) is not None

    @cached_property
    def release(self) -> dict | None:
        """The GitHub release for the latest tag (draft or published)."""
        if not self.tag:
            return None
        return _gh_json(["release", "view", self.tag, "--repo", self.repo,
                         "--json", "isDraft,publishedAt,tagName"])

    @cached_property
    def secrets(self) -> set[str] | None:
        """Actions secret NAMES (never values), or None if gh can't say."""
        data = _gh_json(["secret", "list", "--repo", self.repo, "--json", "name"])
        if data is None:
            return None
        return {s["name"] for s in data}

    @cached_property
    def pypi_state(self) -> str | None:
        """'ours' | 'conflict' (name taken by a FOREIGN project — publishing
        under it is impossible) | 'free' (definitive 404 — becomes ours on
        first publish) | None (can't reach PyPI). Ownership = any of the
        project's URLs points at our repo; without that check a squatted name
        reads as LIVE (found live: PyPI 'dough' is a 2015-era third-party
        package)."""
        data = _http_json(f"https://pypi.org/pypi/{self.dist}/json")
        if data is _NOT_FOUND:
            return "free"
        if data is None:
            return None
        info = data.get("info", {})
        urls = [info.get("home_page") or ""] + list((info.get("project_urls") or {}).values())
        return "ours" if any(self.repo.lower() in u.lower() for u in urls if u) else "conflict"

    @cached_property
    def aur_state(self) -> str | None:
        """Same ownership discipline as pypi_state, on the AUR package's URL.
        The AUR RPC answers 200 with zero results for a missing name → 'free'."""
        data = _http_json(f"https://aur.archlinux.org/rpc/v5/info/{self.slug}")
        if data is None or data is _NOT_FOUND:
            return "free" if data is _NOT_FOUND else None
        results = data.get("results") or []
        if not results:
            return "free"
        url = (results[0].get("URL") or "").lower()
        return "ours" if self.repo.lower() in url else "conflict"

    def secret_set(self, name: str) -> bool | None:
        return None if self.secrets is None else (name in self.secrets)


# ── steps + channels ────────────────────────────────────────────────────────

# A detect returns True (done), False (pending), or None (can't tell — shown
# as '?', the walkthrough still prints the guide).
Detect = Callable[[Ctx], "bool | None"]
Guide = Callable[[Ctx], str]


@dataclass
class Step:
    title: str
    kind: str  # local | account | secret | publish
    detect: Detect
    guide: Guide


@dataclass
class Channel:
    key: str
    title: str
    steps: list[Step]
    stub: bool = False  # authored but not activatable from this host yet
    note: str = ""
    # optional red-flag probe — a non-None string REPLACES the board status
    # (e.g. "NAME CONFLICT" when the channel's namespace is squatted).
    alert: Callable[[Ctx], str | None] = lambda c: None

    def states(self, ctx: Ctx) -> list[bool | None]:
        return [s.detect(ctx) for s in self.steps]


def _next_version(tag: str | None) -> str:
    if not tag:
        return "v0.1.0"
    try:
        major, minor, patch = tag.lstrip("v").split(".")[:3]
        return f"v{major}.{minor}.{int(patch) + 1}"
    except Exception:
        return "v0.1.0"


def _channels() -> list[Channel]:
    tagcmd = lambda c: (  # noqa: E731 — tiny local guide helper
        f"pick the version (the tag IS the version), then:\n"
        f"    git tag {_next_version(c.tag)} && git push origin {_next_version(c.tag)}\n"
        f"release.yml builds the wheel/.deb/AppImage/Windows artifacts and drafts the release."
    )
    return [
        Channel(
            "github-release",
            "GitHub release (carries the .deb / AppImage / wheel / .exe)",
            [
                Step("a v* tag exists", "local",
                     lambda c: c.tag is not None, tagcmd),
                Step("release.yml drafted the release", "local",
                     # release None means ABSENT only when gh could answer;
                     # unauthed/offline stays ? rather than asserting "not drafted".
                     lambda c: None if c.tag is None
                     else (True if c.release is not None else (False if c.gh_ok else None)),
                     lambda c: f"watch it: gh run list --repo {c.repo} --workflow release.yml"),
                Step("the draft is PUBLISHED (human click)", "publish",
                     lambda c: None if c.release is None else (not c.release.get("isDraft", True)),
                     lambda c: f"review + publish: gh release view {c.tag or '<tag>'} "
                               f"--repo {c.repo} --web"),
            ],
        ),
        Channel(
            "pypi",
            "PyPI (OIDC trusted publishing — no token)",
            alert=lambda c: "NAME CONFLICT" if c.pypi_state == "conflict" else None,
            steps=[
                Step("the PyPI name is ours (or free)", "account",
                     lambda c: {None: None, "free": True, "ours": True,
                                "conflict": False}[c.pypi_state],
                     lambda c: f"⚠ NAME CONFLICT: pypi.org/project/{c.dist} is a FOREIGN "
                               "project — publishing under this name is impossible.\n"
                               "Pick a different [project].name (the import package can "
                               "keep its slug), or skip PyPI for this app."
                     if c.pypi_state == "conflict"
                     else f"the name is unclaimed — it becomes yours on first publish "
                          f"(https://pypi.org/project/{c.dist}/ is free)"),
                Step("pending publisher configured on pypi.org", "account",
                     # Only provable after the first publish succeeds.
                     lambda c: True if c.pypi_state == "ours" else None,
                     lambda c: "one-time, at https://pypi.org/manage/account/publishing/ "
                               "(see docs/RELEASING.md):\n"
                               f"    PyPI project name:  {c.dist}\n"
                               f"    Owner / repository: {c.repo}\n"
                               "    Workflow name:      pypi-publish.yml\n"
                               "    Environment name:   pypi"),
                Step("a published GitHub release (the trigger)", "publish",
                     lambda c: None if c.release is None else (not c.release.get("isDraft", True)),
                     lambda c: "publish the github-release channel first — "
                               "pypi-publish.yml fires on release:published"),
                Step("package live on pypi.org", "local",
                     lambda c: None if c.pypi_state is None else c.pypi_state == "ours",
                     lambda c: f"verify: https://pypi.org/project/{c.dist}/"),
            ],
        ),
        Channel(
            "aur",
            "AUR (Arch User Repository)",
            alert=lambda c: "NAME CONFLICT" if c.aur_state == "conflict" else None,
            steps=[
                Step("AUR account + SSH key exist", "account",
                     lambda c: c.secret_set("AUR_SSH_PRIVATE_KEY"),
                     lambda c: "one-time: create https://aur.archlinux.org account, then\n"
                               "    ssh-keygen -t ed25519 -f aur_key -N '' -C aur\n"
                               "and add aur_key.pub to the AUR account's SSH keys"),
                Step("AUR_SSH_PRIVATE_KEY repo secret set", "secret",
                     lambda c: c.secret_set("AUR_SSH_PRIVATE_KEY"),
                     lambda c: f"gh secret set AUR_SSH_PRIVATE_KEY --repo {c.repo} < aur_key\n"
                               "(aur.yml is dormant until this exists)"),
                Step("package live on the AUR", "local",
                     lambda c: {None: None, "free": False, "ours": True,
                                "conflict": False}[c.aur_state],
                     lambda c: f"⚠ NAME CONFLICT: aur.archlinux.org/packages/{c.slug} is a "
                               "FOREIGN package — pick a different AUR pkgname."
                     if c.aur_state == "conflict"
                     else f"after the next published release: "
                          f"https://aur.archlinux.org/packages/{c.slug}"),
            ],
        ),
        Channel(
            "winget", "Windows Package Manager",
            [Step("WINGET_TOKEN repo secret set", "secret",
                  lambda c: c.secret_set("WINGET_TOKEN"),
                  lambda c: "a GitHub PAT with public_repo; winget-releaser opens the "
                            "manifest PR from the published .exe (docs/RELEASING.md)")],
            stub=True, note="activates off the published release; needs no Windows host",
        ),
        Channel(
            "msix", "Microsoft Store (MSIX)",
            [Step("Partner Center registration + WACK run", "account",
                  lambda c: None,
                  lambda c: "manual-first: packaging/msix/STORE-SUBMISSION.md is the runbook")],
            stub=True, note="needs a Windows host + Partner Center account",
        ),
        Channel(
            "macos", "macOS (.dmg + Homebrew cask)",
            [Step("Apple Developer secrets set", "secret",
                  lambda c: c.secret_set("APPLE_TEAM_ID"),
                  lambda c: "needs the $99/yr Apple Developer membership; the secret list "
                            "is documented at the top of .github/workflows/macos.yml")],
            stub=True, note="macos.yml is dormant until the Apple secrets exist",
        ),
    ]


# ── rendering ───────────────────────────────────────────────────────────────

_MARK = {True: "✓", False: "▶", None: "?"}


def _channel_line(ch: Channel, states: list[bool | None], ctx: Ctx) -> str:
    done = sum(1 for s in states if s is True)
    alert = ch.alert(ctx)
    if alert:
        status = f"⚠ {alert}"
    elif all(s is True for s in states):
        status = "LIVE"
    elif any(s is True for s in states):
        status = f"{done}/{len(states)}"
    elif all(s is None for s in states):
        status = "?"
    else:
        status = "not started"
    stub = "  [stub]" if ch.stub else ""
    return f"  {ch.key:<16} {status:<14} {ch.title}{stub}"


def board(ctx: Ctx) -> str:
    lines = [f"delivery board — {ctx.display_name} ({ctx.repo})",
             f"  latest tag: {ctx.tag or '(none — nothing shipped yet)'}", ""]
    for ch in _channels():
        lines.append(_channel_line(ch, ch.states(ctx), ctx))
    lines += ["", f"walk a channel:  python -m {_PKG}.deliver <channel>",
              f"the update lap:  python -m {_PKG}.deliver --release"]
    return "\n".join(lines)


def walkthrough(ctx: Ctx, key: str) -> str:
    ch = next((c for c in _channels() if c.key == key), None)
    if ch is None:
        known = ", ".join(c.key for c in _channels())
        return f"unknown channel {key!r} — one of: {known}"
    lines = [f"{ch.key} — {ch.title}"]
    if ch.note:
        lines.append(f"  note: {ch.note}")
    shown_guide = False
    for step, state in zip(ch.steps, ch.states(ctx), strict=True):
        lines.append(f"  {_MARK[state]} [{step.kind}] {step.title}")
        if state is not True and not shown_guide:
            guide = step.guide(ctx)
            lines.extend(f"      {ln}" for ln in guide.splitlines())
            shown_guide = True  # one actionable step at a time
    if not shown_guide:
        lines.append("  channel is LIVE — nothing to do")
    return "\n".join(lines)


def release_lap(ctx: Ctx) -> tuple[str, int]:
    """The Improvements-loop lap: changelog → tag → watch → publish → verify.
    Refuses an empty lap (no changelog movement since the last tag)."""
    lines = [f"update lap — {ctx.display_name} ({ctx.repo})"]
    nxt = _next_version(ctx.tag)
    if ctx.tag:
        moved = _git("diff", "--stat", f"{ctx.tag}..HEAD", "--", "docs/CHANGELOG.md")
        if moved is not None and not moved.strip():
            lines += [f"  ✗ docs/CHANGELOG.md has not moved since {ctx.tag} — write the",
                      "    release notes first; an empty lap ships nothing describable."]
            return "\n".join(lines), 1
        lines.append(f"  ✓ changelog moved since {ctx.tag}")
    else:
        lines.append("  (first release — no prior tag; make sure CHANGELOG.md has an entry)")
    lines += [
        "  1. tag it (the tag IS the version):",
        f"       git tag {nxt} && git push origin {nxt}",
        f"  2. watch the build:  gh run list --repo {ctx.repo} --workflow release.yml",
        f"  3. publish the draft: gh release view {nxt} --repo {ctx.repo} --web",
        "  4. the fan-out fires on publish (pypi / aur / winget per their secrets);",
        f"     re-run `python -m {_PKG}.deliver` to verify every channel went LIVE.",
    ]
    return "\n".join(lines), 0


def _ctx() -> Ctx:
    import tomllib

    from dough import metadata

    meta = metadata.load()
    project = tomllib.loads(
        metadata._find_pyproject().read_text(encoding="utf-8")
    ).get("project", {})
    return Ctx(
        slug=meta["app_slug"],
        repo=f"{meta['github_owner']}/{meta['repo_name']}",
        display_name=meta["display_name"],
        dist=str(project.get("name") or meta["app_slug"]),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog=f"{_PKG}-deliver",
        description="Delivery-phase walkthroughs: the board, one channel, or the update lap.",
    )
    ap.add_argument("channel", nargs="?", help="channel key to walk (omit for the board)")
    ap.add_argument("--release", action="store_true", help="the update lap (tag → publish → verify)")
    args = ap.parse_args(argv)

    ctx = _ctx()
    if args.release:
        text, rc = release_lap(ctx)
        print(text)
        return rc
    print(walkthrough(ctx, args.channel) if args.channel else board(ctx))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
