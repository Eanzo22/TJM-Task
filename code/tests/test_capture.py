"""Screenshot safety tests use simulated windows; they never move the real UI."""
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from fakturama_cash import ui
from fakturama_cash.errors import ReviewRequired


class Rectangle:
    left, top, right, bottom = 10, 20, 110, 80

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class Window:
    handle = 123
    element_info = SimpleNamespace(name="Fakturama - test workspace", control_type="Window", automation_id="")

    def __init__(self):
        self.bounds = Rectangle()
        self.focus = False
        self.minimized = False
        self.maximized = False
        self.captures = 0
        self.enumerate_hook = lambda: None
        self.capture_hook = lambda: None
        self.image = Image.new("RGB", (100, 60), "blue")

    def rectangle(self):
        return self.bounds

    def is_visible(self):
        return True

    def is_minimized(self):
        return self.minimized

    def is_maximized(self):
        return self.maximized

    def maximize(self):
        self.maximized = True

    def descendants(self):
        self.enumerate_hook()
        return []

    def parent(self):
        return None

    def window_text(self):
        return self.element_info.name

    def capture_as_image(self):
        self.captures += 1
        self.capture_hook()
        return self.image


@pytest.fixture
def setup(monkeypatch):
    window = Window()
    clock = [0.0]
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ui.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    def activate(root):
        root.minimized = False
        root.focus = True
    monkeypatch.setattr(ui, "_activate_capture_window", activate)
    monkeypatch.setattr(ui, "_foreground_handle", lambda: window.handle if window.focus else 999)
    adapter = ui.UIAAdapter({"timeout_seconds": 1}, desktop=object())
    monkeypatch.setattr(adapter, "root", lambda: window)
    return adapter, window, clock


@pytest.mark.parametrize("minimized", [False, True])
def test_capture_activates_waits_and_records_target(setup, tmp_path, minimized):
    adapter, window, clock = setup
    window.minimized = minimized
    result = adapter.capture(tmp_path, "test")
    assert window.focus and not window.minimized
    assert window.maximized
    assert clock[0] >= 0.3
    assert window.captures == 1
    assert result["kind"] == "live_capture"
    metadata = json.loads((tmp_path / "test-capture.json").read_text())
    assert metadata["window_handle"] == window.handle
    assert metadata["foreground_verified_before_and_after"] is True
    assert metadata["capture_method"] == "foreground_screen_region"
    with Image.open(tmp_path / "test.png") as saved:
        assert saved.getpixel((0, 0)) == (0, 0, 255)


def test_foreground_denied_never_takes_or_saves_screenshot(setup, tmp_path, monkeypatch):
    adapter, window, _ = setup
    monkeypatch.setattr(ui, "_activate_capture_window", lambda root: None)
    with pytest.raises(ReviewRequired, match="foreground"):
        adapter.capture(tmp_path, "test")
    assert window.captures == 0
    assert not list(tmp_path.iterdir())


def test_activation_error_is_actionable(setup, tmp_path, monkeypatch):
    adapter, window, _ = setup
    def denied(root):
        raise OSError("activation denied")
    monkeypatch.setattr(ui, "_activate_capture_window", denied)
    with pytest.raises(ReviewRequired, match="activate Fakturama") as error:
        adapter.capture(tmp_path, "test")
    assert error.value.details["stage"] == "capture"
    assert window.captures == 0


def test_maximize_failure_stops_before_capture(setup, tmp_path, monkeypatch):
    adapter, window, _ = setup
    monkeypatch.setattr(window, "maximize", lambda: None)
    with pytest.raises(ReviewRequired, match="did not maximize"):
        adapter.capture(tmp_path, "test")
    assert window.captures == 0


def test_focus_lost_during_uia_enumeration_stops_before_capture(setup, tmp_path):
    adapter, window, _ = setup
    window.enumerate_hook = lambda: setattr(window, "focus", False)
    with pytest.raises(ReviewRequired, match="before capture"):
        adapter.capture(tmp_path, "test")
    assert window.captures == 0


@pytest.mark.parametrize("change", ["focus", "bounds", "target"])
def test_mid_capture_change_discards_image_preserves_previous_evidence(setup, tmp_path, monkeypatch, change):
    adapter, window, _ = setup
    previous = tmp_path / "test.png"
    previous.write_bytes(b"previous evidence")
    def disrupt():
        if change == "focus":
            window.focus = False
        elif change == "bounds":
            window.bounds.right += 10
        else:
            monkeypatch.setattr(adapter, "root", lambda: SimpleNamespace(handle=456))
    window.capture_hook = disrupt
    with pytest.raises(ReviewRequired, match="during capture"):
        adapter.capture(tmp_path, "test")
    assert previous.read_bytes() == b"previous evidence"
    assert not (tmp_path / "test-uia.json").exists()


@pytest.mark.parametrize("image", [None, Image.new("RGB", (1, 1))])
def test_missing_or_wrong_size_image_is_not_saved(setup, tmp_path, image):
    adapter, window, _ = setup
    window.image = image
    with pytest.raises(ReviewRequired, match="dimensions"):
        adapter.capture(tmp_path, "test")
    assert not list(tmp_path.iterdir())
