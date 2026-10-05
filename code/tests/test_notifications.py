import json
import sys
from pathlib import Path
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


@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("command,failure", [
    ("validate", None), ("validate", "extraction"),
    ("run", None), ("run", "UI preflight"),
    ("run", "extraction"), ("run", "workflow"),
])
def test_full_command_outcome_sound(monkeypatch, tmp_path, capsys, command, failure, quiet):
    from fakturama_cash import cli
    from fakturama_cash.errors import ReviewRequired
    from fakturama_cash.models import OrderInput
    from fakturama_cash.progress import TerminalProgress

    events = []
    fixture = Path(__file__).parent / "fixtures/synthetic_order.json"
    order = OrderInput.model_validate_json(fixture.read_text()).reconcile()

    def stop_at(stage):
        if failure == stage:
            raise ReviewRequired("Simulated failure", stage=stage)

    class Adapter:
        def __init__(self, *args, **kwargs):
            pass

        def preflight(self, *args, **kwargs):
            stop_at("UI preflight")

    def extract(*args, **kwargs):
        stop_at("extraction")
        return order

    class Workflow:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, order):
            stop_at("workflow")
            events.append("persisted_verified")
            return {"order": "PO-TEST", "invoice": "INV-TEST"}

    close = TerminalProgress.__exit__

    def cleanup(self, *args):
        close(self, *args)
        events.append("progress_closed")

    def sound(*, success):
        # Final result/error and context cleanup must precede notification.
        output = capsys.readouterr()
        reported = json.loads(output.out if success else output.err.splitlines()[-1])
        expected = ("complete" if command == "run" else "validated_image") if success else "review_required"
        assert reported["status"] == expected
        if not success:
            assert reported["stage"] == failure
        assert events[-1] == "progress_closed"
        events.append(("sound", success))

    monkeypatch.setattr(cli, "UIAAdapter", Adapter)
    monkeypatch.setattr(cli, "load_profile", lambda path: {})
    monkeypatch.setattr(cli, "extract", extract)
    monkeypatch.setattr(cli, "Workflow", Workflow)
    monkeypatch.setattr(cli, "capture_finished", sound)
    monkeypatch.setattr(TerminalProgress, "__exit__", cleanup)
    args = [command, str(fixture), "--runs", str(tmp_path)] + (["--quiet"] if quiet else [])
    assert main(args) == (2 if failure else 0)
    assert [event for event in events if isinstance(event, tuple)] == ([] if quiet else [("sound", failure is None)])
    assert ("persisted_verified" in events) == (command == "run" and failure is None)


@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_live_runner_sound_after_journal_closes(monkeypatch, tmp_path, capsys, quiet, fails):
    import importlib.util
    from fakturama_cash.errors import ReviewRequired

    spec = importlib.util.spec_from_file_location("run_live_smoke", Path(__file__).parents[1] / "scripts/run_live_smoke.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    events = []
    source = json.loads((Path(__file__).parent / "fixtures/synthetic_order.json").read_text())
    source["external_reference"] = "CODEX-SOUND-UNIT-TEST"
    fixture = tmp_path / "order.json"
    fixture.write_text(json.dumps(source))

    class Journal:
        def __init__(self, *args):
            self.directory = tmp_path / 'workflow-attempt'
            self.path = self.directory / 'checkpoint.json'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("journal_closed")

    class Workflow:
        def __init__(self, *args, progress=None):
            self.progress = progress

        def run(self, order):
            if self.progress:
                self.progress("working")
            if fails:
                raise ReviewRequired("Simulated UI failure", stage="workflow")
            return {"invoice": "INV-TEST"}

    monkeypatch.setattr(runner, "Journal", Journal)
    monkeypatch.setattr(runner, "Workflow", Workflow)
    monkeypatch.setattr(runner, "load_profile", lambda path: {})
    monkeypatch.setattr(runner, "UIAAdapter", lambda profile: object())
    monkeypatch.setattr(runner, "capture_finished", lambda *, success: events.append(("sound", success)))
    args = [str(fixture)] + (["--quiet"] if quiet else [])
    if fails:
        with pytest.raises(ReviewRequired):
            runner.main(args)
    else:
        runner.main(args)
    assert events == ["journal_closed"] + ([] if quiet else [("sound", not fails)])
    output = capsys.readouterr().out
    assert ("working" in output) == (not quiet)
    if not fails:
        assert json.loads(output.splitlines()[-1])["status"] == "complete"
