"""The phone interface (trackerkeeper/quick): which front end a shell gets,
the fleet model QML binds to, and the real QML loaded offscreen over a fake
fleet. No network — check results are injected."""

from __future__ import annotations

import pytest

from trackerkeeper import catalog, fleet
from trackerkeeper.sources import CheckResult

quick = pytest.importorskip("trackerkeeper.quick")
if not quick.available():
    pytest.skip("this PySide6 has no QtQuick", allow_module_level=True)


@pytest.fixture(autouse=True)
def _tmp_catalog(tmp_path):
    catalog.set_catalog_path(tmp_path / "catalog.json")
    yield
    catalog.set_catalog_path(None)


def _fleet_items():
    item = catalog.Item
    return [
        item("Ghostty", "Terminal", "PC", "github", "ghostty-org/ghostty", "1.0",
          latest="1.1", latest_date="2026-07-01"),
        item("KDE Plasma", "Linux", "PC", "arch", "plasma-desktop", "6.8",
          latest="6.8", latest_date="2026-06-01"),
        item("Slay the Spire 2", "Steam", "Gaming", "steam", "2868840", "0.1",
          latest="0.2", latest_date="2026-07-20"),
        item("Loose thing", "", "", "manual", "", "3"),
    ]


# ── which front end ──

@pytest.fixture
def _shell(monkeypatch, tmp_path):
    for var in ("PLASMA_PLATFORM", "QT_QUICK_CONTROLS_MOBILE", "XDG_CURRENT_DESKTOP",
                quick.ENV_UI):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("sys.platform", "linux")
    return monkeypatch


def test_desktop_gets_the_widgets_window(_shell):
    _shell.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert not quick.is_phone_shell()
    assert not quick.wanted()


@pytest.mark.parametrize("var,value", [
    ("PLASMA_PLATFORM", "phone:handset"),
    ("QT_QUICK_CONTROLS_MOBILE", "true"),
    ("XDG_CURRENT_DESKTOP", "Phosh:GNOME"),
])
def test_phone_shells_get_the_phone_interface(_shell, var, value):
    _shell.setenv(var, value)
    assert quick.is_phone_shell()
    assert quick.wanted()


def test_a_docked_phone_is_a_desktop(_shell, tmp_path):
    _shell.setenv("PLASMA_PLATFORM", "phone:handset")
    (tmp_path / "plasmamobilerc").write_text("[General]\nconvergenceModeEnabled=true\n")
    assert quick.is_docked()
    assert not quick.wanted()


def test_the_env_var_forces_either_way(_shell):
    _shell.setenv(quick.ENV_UI, "quick")
    assert quick.wanted()
    _shell.setenv("PLASMA_PLATFORM", "phone:handset")
    _shell.setenv(quick.ENV_UI, "widgets")
    assert not quick.wanted()


# ── the shared fleet logic ──

def test_apply_results_reports_only_newly_new():
    items = _fleet_items()
    newly = fleet.apply_results(items, {
        "Ghostty": CheckResult(latest="1.1", date="2026-07-01"),       # already surfaced
        "KDE Plasma": CheckResult(latest="6.9", date="2026-07-25"),    # new news
    }, {"Slay the Spire 2": "not_found"})
    assert [i.name for i in newly] == ["KDE Plasma"]
    spire = next(i for i in items if i.name == "Slay the Spire 2")
    assert spire.error == "not_found" and spire.latest == "0.2"   # last-known kept
    assert next(i for i in items if i.kind == "manual").error == ""


def test_order_groups_a_to_z_other_last_newest_first():
    from trackerkeeper.quick.fleet_model import order

    names = [i.name for i in order(_fleet_items())]
    assert names == ["Slay the Spire 2", "Ghostty", "KDE Plasma", "Loose thing"]


# ── the model QML binds to ──

@pytest.fixture
def fleet_obj(qapp):
    from trackerkeeper.quick.fleet_model import Fleet

    catalog.save(_fleet_items())
    return Fleet(start=False)


def _names(f):
    m = f.model
    role = next(k for k, v in m.roleNames().items() if bytes(v) == b"name")
    return [m.data(m.index(r), role) for r in range(m.rowCount())]


def test_filters(fleet_obj):
    assert fleet_obj.property("updateCount") == 2
    assert fleet_obj.property("groups") == ["Gaming", "PC", "Other"]
    fleet_obj.setProperty("filter", "new")
    assert _names(fleet_obj) == ["Slay the Spire 2", "Ghostty"]
    fleet_obj.setProperty("filter", "PC")
    assert _names(fleet_obj) == ["Ghostty", "KDE Plasma"]
    fleet_obj.setProperty("filter", "Other")
    assert _names(fleet_obj) == ["Loose thing"]
    assert fleet_obj.sectionNews("PC") == 1


def test_mark_updated_persists(fleet_obj):
    fleet_obj.markUpdated("Ghostty")
    assert fleet_obj.property("updateCount") == 1
    saved = next(i for i in catalog.load() if i.name == "Ghostty")
    assert saved.installed == "1.1"


def test_save_validates_like_the_desktop_dialog(fleet_obj):
    assert fleet_obj.save("", {"name": ""}) == "A name is required."
    assert "already tracking" in fleet_obj.save("", {"name": "ghostty"})
    assert "owner/repo" in fleet_obj.save("", {"name": "New", "kind": "github", "ref": "nope"})
    assert fleet_obj.save("", {"name": "New", "kind": "github", "ref": "a/b",
                               "group": "PC"}) == ""
    assert fleet_obj.save("Ghostty", {"name": "Ghostty", "kind": "github",
                                      "ref": "ghostty-org/ghostty", "group": "Terminals"}) == ""
    by_name = {i.name: i for i in catalog.load()}
    assert by_name["New"].ref == "a/b" and by_name["Ghostty"].group == "Terminals"


def test_remove(fleet_obj):
    fleet_obj.remove("Loose thing")
    assert "Loose thing" not in {i.name for i in catalog.load()}
    assert "Other" not in fleet_obj.property("groups")


def test_results_land_and_notify(fleet_obj):
    from trackerkeeper.bus import AppBus

    got = []
    AppBus.get().notify.connect(lambda t, b: got.append((t, b)))
    fleet_obj._on_results({"KDE Plasma": CheckResult(latest="6.9", date="2026-07-25")})
    assert fleet_obj.property("updateCount") == 3
    assert not fleet_obj.property("checking")
    assert fleet_obj.property("status").startswith("checked 1/3")
    assert got and got[-1][1] == "KDE Plasma"


def test_seen_banks_the_news(fleet_obj):
    assert fleet_obj.property("newCount") == 2
    fleet_obj.markSeen()
    assert fleet_obj.property("newCount") == 0
    assert all(not i.is_new() for i in catalog.load())


# ── the real QML ──

def _pump(ms):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _find(root, name):
    """Walk the VISUAL tree — list delegates are visual children of the view,
    not QObject children, so findChildren() never sees them."""
    stack = [root]
    while stack:
        it = stack.pop()
        if it.objectName() == name:
            return it
        stack.extend(it.childItems())
    return None


@pytest.fixture
def ui(qapp):
    catalog.save(_fleet_items())
    engine = quick.build_engine(qapp, start=False)
    roots = engine.rootObjects()
    assert roots, "Main.qml failed to load"
    win = roots[0]
    win.resize(402, 820)
    _pump(150)
    yield engine, win
    win.close()
    win.deleteLater()
    engine.deleteLater()
    _pump(20)


def test_qml_loads_with_a_row_per_item(ui):
    _engine, win = ui
    for item in _fleet_items():
        assert _find(win.contentItem(), "row_" + item.name) is not None, item.name
    assert _find(win.contentItem(), "chip_Gaming") is not None


def test_detail_and_edit_open(ui):
    from PySide6.QtCore import Q_ARG, QMetaObject

    engine, win = ui
    QMetaObject.invokeMethod(win, "showDetail", Q_ARG("QVariant", "Ghostty"))
    _pump(400)
    sheet = next(o for o in win.findChildren(object) if o.objectName() == "detailSheet")
    assert sheet.property("opened")
    QMetaObject.invokeMethod(win, "back")
    _pump(400)
    assert not sheet.property("opened")
    QMetaObject.invokeMethod(win, "openEdit", Q_ARG("QVariant", "Ghostty"))
    _pump(500)
    stack = _find(win.contentItem(), "stack")
    assert stack.property("depth") == 2
    assert stack.property("currentItem").property("original") == "Ghostty"


def test_a_phone_shell_has_no_tray(_shell, qapp):
    """Plasma Mobile registers a tray host but draws no tray items, so "start in
    the tray" there would launch with no icon AND no window."""
    from trackerkeeper import tray

    _shell.setenv("PLASMA_PLATFORM", "phone:handset")
    assert tray.will_have_tray() is False
