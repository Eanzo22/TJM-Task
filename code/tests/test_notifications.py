import json
import sys
from types import SimpleNamespace

import pytest

from fakturama_cash.cli import main
from fakturama_cash.notifications import capture_finished


@pytest.mark.parametrize("success,expected", [(True, [(880, 150), (1175, 200)]), (False, [(440, 450)])])
def test_distinct_short_tones(monkeypatch, success, expected):
    calls = []
    monkeypatch.setitem(sys.modules, "winsound", SimpleNamespace(Beep=lambda *args: calls.append(args)))
    capture_finished(success=success)
    assert calls == expected


def test_audio_failure_is_harmless(monkeypatch):
    def broken(*args):
        raise RuntimeError("No audio device")
    monkeypatch.setitem(sys.modules, "winsound", SimpleNamespace(Beep=broken))
    capture_finished(success=True)


def test_missing_audio_module_is_harmless(monkeypatch):
    monkeypatch.setitem(sys.modules, "winsound", None)
    capture_finished(success=True)


@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_diagnostic_notifies_after_capture_finishes(monkeypatch, tmp_path, capsys, quiet, fails):
    from fakturama_cash import cli
    from fakturama_cash.errors import ReviewRequired
    events = []
    class Adapter:
        def __init__(self, profile):
            pass
        def capture(self, *args):
            if fails:
                events.append("capture_failed")
                raise ReviewRequired("Simulated capture failure", stage="capture")
            events.append("capture_saved")
            return {"kind": "live_capture"}
    monkeypatch.setattr(cli, "UIAAdapter", Adapter)
    monkeypatch.setattr(cli, "load_profile", lambda path: {})
    monkeypatch.setattr(cli, "capture_finished", lambda *, success: events.append(("sound", success)))
    args = ["diagnose", "--out", str(tmp_path)] + (["--quiet"] if quiet else [])
    assert main(args) == (2 if fails else 0)
    assert events[0] == ("capture_failed" if fails else "capture_saved")
    assert events[1:] == ([] if quiet else [("sound", not fails)])
    output = capsys.readouterr()
    if fails:
        assert json.loads(output.err.splitlines()[-1])["status"] == "review_required"
    else:
        assert json.loads(output.out)["kind"] == "live_capture"


def test_other_commands_do_not_make_sound(monkeypatch):
    from fakturama_cash import cli
    from pathlib import Path
    monkeypatch.setattr(cli, "capture_finished", lambda **kw: pytest.fail("Unexpected sound"))
    fixture = Path(__file__).parent / "fixtures/synthetic_order.json"
    assert main(["validate-json", str(fixture), "--quiet"]) == 0
