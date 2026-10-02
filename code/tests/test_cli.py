import json
from pathlib import Path

import pytest

from PIL import Image

from fakturama_cash.cli import main


def test_validate_missing_model_preserves_each_attempt(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("FAKTURAMA_VISION_MODEL", raising=False)
    image = tmp_path / "synthetic-blank.png"
    Image.new("RGB", (20, 20), "white").save(image)
    runs = tmp_path / "runs"
    for _ in range(2):
        assert main(["validate", str(image), "--runs", str(runs), "--quiet"]) == 2
        result = json.loads(capsys.readouterr().err)
        assert result["stage"] == "extraction"
        assert result["status"] == "review_required"
    assert len(list(runs.glob("*/extractions/*/review-required.json"))) == 2
    assert not list(runs.glob("*/checkpoint.json"))


def test_ocr_command_is_explicitly_raw_only(tmp_path, monkeypatch, capsys):
    from fakturama_cash import windows_ocr
    calls = []
    monkeypatch.setattr(windows_ocr, "capture_ocr", lambda image, out: calls.append((image, out)))
    assert main(["ocr", "synthetic.png", "--out", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "raw_ocr_only"
    assert len(calls) == 1


def test_incomplete_profile_reports_review_without_desktop(tmp_path, capsys):
    profile = tmp_path / "partial.json"
    profile.write_text('{"calibrated":false}', encoding="utf-8")
    assert main(["check-profile", str(profile), "--quiet"]) == 2
    assert json.loads(capsys.readouterr().err)["stage"] == "UI preflight"


def test_default_progress_keeps_success_json_on_stdout(capsys):
    fixture = Path(__file__).parent / "fixtures/synthetic_order.json"
    assert main(["validate-json", str(fixture)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "validated_json_only"
    assert "Starting validate-json" in output.err
    assert "JSON validation complete" in output.err
    assert "Synthetic Office" not in output.err


@pytest.mark.parametrize("before", [True, False])
def test_quiet_option_before_or_after_command(before, capsys):
    fixture = Path(__file__).parent / "fixtures/synthetic_order.json"
    args = ["validate-json", str(fixture)]
    args = ["--quiet", *args] if before else [*args, "--quiet"]
    assert main(args) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "validated_json_only"
    assert output.err == ""


def test_default_error_has_stop_message_and_final_json(tmp_path, capsys):
    profile = tmp_path / "partial.json"
    profile.write_text('{"calibrated":false}', encoding="utf-8")
    assert main(["check-profile", str(profile)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "STOPPED at UI preflight" in output.err
    assert json.loads(output.err.splitlines()[-1])["status"] == "review_required"
    assert "completeness check passed" not in output.err


def test_run_checks_profile_before_image_or_model(tmp_path, monkeypatch, capsys):
    profile = tmp_path / "partial.json"
    profile.write_text('{"calibrated": false}', encoding="utf-8")
    def forbidden(*args, **kwargs):
        pytest.fail("An incomplete profile must stop before extraction")
    monkeypatch.setattr("fakturama_cash.cli.extract", forbidden)
    assert main(["run", "does-not-exist.png", "--profile", str(profile),
                 "--runs", str(tmp_path / "runs"), "--quiet"]) == 2
    assert json.loads(capsys.readouterr().err)["stage"] == "UI preflight"
    assert not (tmp_path / "runs").exists()
