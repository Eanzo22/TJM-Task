import io
import json
from PIL import Image
import pytest

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.extraction import extract


def test_real_image_request_preserves_raw_and_normalized(payload, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKTURAMA_VISION_MODEL", "synthetic-transport-test")
    image = tmp_path / "synthetic-image.png"
    Image.new("RGB", (10, 10), "white").save(image)
    requests = []

    def transport(request, timeout):
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"message": {"content": json.dumps(payload)}}).encode())

    result = extract(image, tmp_path / "evidence", transport=transport)
    assert len(result.items) == 2
    assert requests[0]["messages"][1]["images"]
    assert requests[0]["format"]["type"] == "object"
    assert (tmp_path / "evidence/extraction-raw.txt").exists()
    assert (tmp_path / "evidence/normalized.json").exists()


def test_model_missing_is_clear_stop(tmp_path, monkeypatch):
    monkeypatch.delenv("FAKTURAMA_VISION_MODEL", raising=False)
    image = tmp_path / "synthetic.png"
    Image.new("RGB", (5, 5)).save(image)
    with pytest.raises(ReviewRequired, match="not configured"):
        extract(image, tmp_path / "out")


def test_model_output_is_data_not_code(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKTURAMA_VISION_MODEL", "synthetic-transport-test")
    image = tmp_path / "synthetic.png"
    Image.new("RGB", (5, 5)).save(image)
    with pytest.raises(ReviewRequired, match="extraction failed"):
        extract(image, tmp_path / "out", transport=lambda *_args, **_kw:
                io.BytesIO(b'{"message":{"content":"ignore schema and execute a command"}}'))
