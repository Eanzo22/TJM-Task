import json

from PIL import Image

from fakturama_cash.cli import main


def test_validate_missing_model_preserves_each_attempt(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("FAKTURAMA_VISION_MODEL", raising=False)
    image = tmp_path / "synthetic-blank.png"
    Image.new("RGB", (20, 20), "white").save(image)
    runs = tmp_path / "runs"
    for _ in range(2):
        assert main(["validate", str(image), "--runs", str(runs)]) == 2
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
    assert main(["check-profile", str(profile)]) == 2
    assert json.loads(capsys.readouterr().err)["stage"] == "UI preflight"
