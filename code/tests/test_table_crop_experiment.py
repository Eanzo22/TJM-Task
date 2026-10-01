"""Guard the shared production/experiment crop without Windows OCR or a model."""

import pytest


from fakturama_cash import table_crop as experiment


def observation(scale=1):
    labels = [("ITEMS", 100), ("SKU", 140), ("Description", 140),
              ("Qty", 140), ("Unit", 140), ("Unit net", 135),
              ("Disc.", 140), ("VAT", 140), ("Line net", 135),
              ("NET TOTAL", 400)]
    return {"width": 1000 * scale, "height": 600 * scale,
            "lines": [{"text": label, "words": [{"y": y * scale, "height": 10 * scale}]}
                      for label, y in labels]}


def test_bounds_follow_ocr_scale_not_fixed_coordinates():
    assert experiment.table_bounds(observation()) == (0, 90, 1000, 390)
    assert experiment.table_bounds(observation(2)) == (0, 180, 2000, 780)


def test_missing_header_stops():
    data = observation()
    data["lines"] = [line for line in data["lines"] if line["text"] != "Unit net"]
    with pytest.raises(ValueError, match="Missing or ambiguous"):
        experiment.table_bounds(data)


def test_duplicate_anchor_stops():
    data = observation()
    data["lines"].append(data["lines"][0])
    with pytest.raises(ValueError, match="ambiguous"):
        experiment.table_bounds(data)


def test_displaced_header_stops():
    data = observation()
    data["lines"][1]["words"][0]["y"] = 250
    with pytest.raises(ValueError, match="single header band"):
        experiment.table_bounds(data)


def test_wrong_anchor_order_stops():
    data = observation()
    data["lines"][-1]["words"][0]["y"] = 110
    with pytest.raises(ValueError, match="vertical order"):
        experiment.table_bounds(data)


def test_crop_preserves_source_pixels_and_records_bounds(tmp_path, monkeypatch):
    import json
    from PIL import Image

    source = tmp_path / "source.png"
    original = Image.new("RGB", (1000, 600), "white")
    original.putpixel((100, 150), (1, 2, 3))
    original.save(source)
    monkeypatch.setattr(experiment, "capture_ocr", lambda *args: observation())
    cropped = experiment.prepare_table(source, tmp_path / "out")
    with Image.open(cropped) as image:
        assert image.size == (1000, 300)
        assert image.tobytes() == original.crop((0, 90, 1000, 390)).tobytes()
    metadata = json.loads((tmp_path / "out/crop.json").read_text())
    assert metadata["resized"] is False
    assert metadata["crop_box"] == [0, 90, 1000, 390]


def test_ocr_dimension_mismatch_stops_before_saving_crop(tmp_path, monkeypatch):
    from PIL import Image

    source = tmp_path / "source.png"
    Image.new("RGB", (50, 50)).save(source)
    monkeypatch.setattr(experiment, "capture_ocr", lambda *args: observation())
    with pytest.raises(ValueError, match="coordinates do not match"):
        experiment.prepare_table(source, tmp_path / "out")
    assert not (tmp_path / "out/table.png").exists()
