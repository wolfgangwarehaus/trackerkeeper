"""The Delivery walkthroughs (dough/deliver.py) — state is DETECTED, offline-
safe, and never touches secret values. Probes are faked at the module seam
(_run/_gh_json/_http_json), so no test shells out or hits the network."""

from __future__ import annotations

import pytest

from dough import deliver
from dough.deliver import Ctx


@pytest.fixture
def ctx() -> Ctx:
    return Ctx(slug="butterpdf", repo="wolfgangwarehaus/butterPDF", display_name="butterPDF")


@pytest.fixture
def offline(monkeypatch):
    """Every probe fails — no git, no gh, no network."""
    monkeypatch.setattr(deliver, "_run", lambda cmd: None)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(deliver, "_http_json", lambda url: None)


def test_board_renders_every_channel_offline(ctx, offline):
    """Total probe failure degrades to '?' — never a crash, never a false LIVE."""
    out = deliver.board(ctx)
    for key in ("github-release", "pypi", "aur", "winget", "msix", "macos"):
        assert key in out
    assert "LIVE" not in out
    assert "(none — nothing shipped yet)" in out


def test_github_release_progression(ctx, monkeypatch):
    """no tag → tag+draft → published, detected purely from git/gh."""
    monkeypatch.setattr(deliver, "_http_json", lambda url: None)

    # no tag at all
    monkeypatch.setattr(deliver, "_run", lambda cmd: "" if cmd[:2] == ["git", "tag"] else None)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    states = deliver._channels()[0].states(Ctx(slug="x", repo="o/x", display_name="x"))
    assert states[0] is False  # tag: pending
    assert "git tag v0.1.0" in deliver.walkthrough(
        Ctx(slug="x", repo="o/x", display_name="x"), "github-release")

    # tag exists, release still a draft
    monkeypatch.setattr(deliver, "_run", lambda cmd: "v0.1.0\n" if cmd[:2] == ["git", "tag"] else None)
    monkeypatch.setattr(
        deliver, "_gh_json",
        lambda args: {"isDraft": True} if args[:2] == ["release", "view"] else None,
    )
    states = deliver._channels()[0].states(Ctx(slug="x", repo="o/x", display_name="x"))
    assert states[:3] == [True, True, False]  # publish is the human step

    # published
    monkeypatch.setattr(
        deliver, "_gh_json",
        lambda args: {"isDraft": False} if args[:2] == ["release", "view"] else None,
    )
    states = deliver._channels()[0].states(Ctx(slug="x", repo="o/x", display_name="x"))
    assert states == [True, True, True]


def test_pypi_guide_prints_the_exact_pending_publisher_values(ctx, monkeypatch):
    """With the name FREE (a definitive 404) the name-step checks off and the
    next pending step surfaces the four pending-publisher values verbatim."""
    monkeypatch.setattr(deliver, "_run", lambda cmd: None)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(deliver, "_http_json", lambda url: deliver._NOT_FOUND)
    out = deliver.walkthrough(ctx, "pypi")
    assert "PyPI project name:  butterpdf" in out
    assert "Owner / repository: wolfgangwarehaus/butterPDF" in out
    assert "Workflow name:      pypi-publish.yml" in out
    assert "Environment name:   pypi" in out


def test_free_name_is_distinct_from_offline(monkeypatch):
    monkeypatch.setattr(deliver, "_run", lambda cmd: None)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(deliver, "_http_json", lambda url: deliver._NOT_FOUND)
    assert Ctx(slug="x", repo="o/x", display_name="x").pypi_state == "free"
    monkeypatch.setattr(deliver, "_http_json", lambda url: None)
    assert Ctx(slug="x", repo="o/x", display_name="x").pypi_state is None


def test_secret_names_only_never_values(ctx, monkeypatch):
    """The gh probe asks for secret NAMES; nothing in the module reads a value."""
    seen: list[list[str]] = []

    def fake_gh(args):
        seen.append(args)
        return [{"name": "AUR_SSH_PRIVATE_KEY"}] if args[:2] == ["secret", "list"] else None

    monkeypatch.setattr(deliver, "_gh_json", fake_gh)
    monkeypatch.setattr(deliver, "_run", lambda cmd: None)
    monkeypatch.setattr(deliver, "_http_json", lambda url: None)
    assert ctx.secret_set("AUR_SSH_PRIVATE_KEY") is True
    assert ctx.secret_set("WINGET_TOKEN") is False
    for call in seen:
        assert "--json" in call and "name" in call  # names, never values


def test_walkthrough_shows_one_actionable_step(ctx, offline):
    """The first non-done step carries its guide; later steps stay collapsed —
    one 30-second action at a time."""
    out = deliver.walkthrough(ctx, "aur")
    assert out.count("one-time: create") == 1
    assert "gh secret set AUR_SSH_PRIVATE_KEY" not in out  # step 2's guide: collapsed


def test_unknown_channel_lists_the_known(ctx, offline):
    out = deliver.walkthrough(ctx, "flathub")
    assert "unknown channel" in out and "github-release" in out


def test_release_lap_refuses_an_empty_changelog(ctx, monkeypatch):
    def fake_run(cmd):
        if cmd[:2] == ["git", "tag"]:
            return "v0.1.0\n"
        if cmd[:2] == ["git", "diff"]:
            return ""  # changelog untouched since the tag
        return None

    monkeypatch.setattr(deliver, "_run", fake_run)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(deliver, "_http_json", lambda url: None)
    text, rc = deliver.release_lap(ctx)
    assert rc == 1 and "has not moved" in text


def test_release_lap_suggests_the_next_patch(ctx, monkeypatch):
    def fake_run(cmd):
        if cmd[:2] == ["git", "tag"]:
            return "v0.3.2\n"
        if cmd[:2] == ["git", "diff"]:
            return " docs/CHANGELOG.md | 12 ++++\n"
        return None

    monkeypatch.setattr(deliver, "_run", fake_run)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(deliver, "_http_json", lambda url: None)
    text, rc = deliver.release_lap(ctx)
    assert rc == 0 and "git tag v0.3.3" in text


def test_next_version_first_release():
    assert deliver._next_version(None) == "v0.1.0"
    assert deliver._next_version("v1.2.9") == "v1.2.10"


def _pypi_payload(home: str) -> dict:
    return {"info": {"name": "dough", "home_page": home, "project_urls": None}}


def test_pypi_name_conflict_is_flagged_not_live(monkeypatch):
    """A squatted PyPI name must read NAME CONFLICT, never LIVE (found live:
    pypi 'dough' is a 2015-era third-party package)."""
    monkeypatch.setattr(deliver, "_run", lambda cmd: None)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(
        deliver, "_http_json",
        lambda url: _pypi_payload("https://github.com/someone/else") if "pypi.org" in url else None,
    )
    c = Ctx(slug="dough", repo="wolfgangwarehaus/dough", display_name="dough")
    assert c.pypi_state == "conflict"
    out = deliver.board(c)
    assert "NAME CONFLICT" in out and "LIVE" not in out
    walk = deliver.walkthrough(c, "pypi")
    assert "FOREIGN" in walk and "different [project].name" in walk


def test_pypi_ownership_via_project_urls(monkeypatch):
    monkeypatch.setattr(deliver, "_run", lambda cmd: None)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(
        deliver, "_http_json",
        lambda url: _pypi_payload("https://github.com/wolfgangwarehaus/butterPDF")
        if "pypi.org" in url else None,
    )
    c = Ctx(slug="butterpdf", repo="wolfgangwarehaus/butterPDF", display_name="butterPDF")
    assert c.pypi_state == "ours"


def test_pypi_probes_use_the_distribution_name(monkeypatch):
    """dough publishes as dough-base (the bare name is squatted): every PyPI
    probe and guide must carry [project].name, never the slug."""
    urls = []
    monkeypatch.setattr(deliver, "_run", lambda cmd: None)
    monkeypatch.setattr(deliver, "_gh_json", lambda args: None)
    monkeypatch.setattr(
        deliver, "_http_json", lambda url: urls.append(url) or deliver._NOT_FOUND
    )
    c = Ctx(slug="dough", repo="wolfgangwarehaus/dough", display_name="dough",
            dist="dough-base")
    assert c.pypi_state == "free"
    assert any("pypi.org/pypi/dough-base/json" in u for u in urls)
    out = deliver.walkthrough(c, "pypi")
    assert "PyPI project name:  dough-base" in out


def test_ctx_dist_defaults_to_slug():
    c = Ctx(slug="butterpdf", repo="o/r", display_name="b")
    assert c.dist == "butterpdf"
