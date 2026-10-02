import copy
import json

from PIL import Image
import pytest

from fakturama_cash.address_crop import AddressPair, prepare_addresses, verify_addresses, verify_customer_id
from fakturama_cash.errors import ReviewRequired
from fakturama_cash.models import DebtorContact


def line(text, x, y, width=140):
    return {"text": text, "words": [{"text": text, "x": x, "y": y,
                                    "width": width, "height": 15}]}


def observation(payload, scale=1):
    lines = [line("BILLING ADDRESS", 20, 30), line("DELIVERY ADDRESS", 400, 30),
             line("PAYMENT", 20, 200)]
    for side, x in (("billing", 20), ("delivery", 400)):
        a = payload["debtor"][side]
        values = [a["name"], a["street"], a["zip"] + " " + a["city"], a["country"]]
        lines += [line(text, x, 60 + i * 25) for i, text in enumerate(values)]
    for entry in lines:
        for word in entry["words"]:
            for key in ("x", "y", "width", "height"):
                word[key] *= scale
    return {"width": 800 * scale, "height": 300 * scale, "lines": lines}


def pair(payload):
    return AddressPair.model_validate({key: payload["debtor"][key] for key in ("billing", "delivery")})


@pytest.mark.parametrize("scale", [1, 2])
def test_crop_and_agreement_follow_source_geometry(payload, tmp_path, scale):
    ocr = observation(payload, scale)
    source = tmp_path / "source.png"
    original = Image.new("RGB", (ocr["width"], ocr["height"]), "white")
    original.putpixel((100, 100), (25, 50, 75))
    original.save(source)
    crop, observed = prepare_addresses(source, tmp_path / "out", ocr)
    verify_addresses(pair(payload), observed)
    metadata = json.loads((tmp_path / "out/crop.json").read_text())
    assert metadata["crop_box"] == [0, 15 * scale, 800 * scale, 185 * scale]
    with Image.open(crop) as saved:
        assert saved.tobytes() == original.crop(tuple(metadata["crop_box"])).tobytes()


@pytest.mark.parametrize("problem", ["duplicate", "missing", "crossing", "few_lines", "unaligned"])
def test_ambiguous_address_layout_stops(payload, tmp_path, problem):
    ocr = observation(payload)
    if problem == "duplicate":
        ocr["lines"].append(copy.deepcopy(ocr["lines"][0]))
    elif problem == "missing":
        ocr["lines"].pop(0)
    elif problem == "crossing":
        ocr["lines"][3]["words"][0]["width"] = 450
    elif problem == "few_lines":
        ocr["lines"].pop()
    else:
        ocr["lines"][1]["words"][0]["y"] = 80
    with pytest.raises(ValueError):
        prepare_addresses(tmp_path / "unused.png", tmp_path / "out", ocr)


@pytest.mark.parametrize("problem", ["typo", "swapped", "swapped_fields", "omitted", "extra"])
def test_disagreement_is_not_auto_corrected(payload, tmp_path, problem):
    source = tmp_path / "source.png"
    Image.new("RGB", (800, 300)).save(source)
    _, observed = prepare_addresses(source, tmp_path / "out", observation(payload))
    result = pair(payload)
    if problem == "typo":
        result.delivery.street += "s"
    elif problem == "swapped":
        result.billing, result.delivery = result.delivery, result.billing
    elif problem == "swapped_fields":
        result.delivery.name, result.delivery.street = result.delivery.street, result.delivery.name
    elif problem == "omitted":
        observed["delivery"].append("Building B")
    else:
        result.delivery.additional_name = "Invented name"
    before = result.model_dump()
    with pytest.raises(ReviewRequired, match="address disagrees"):
        verify_addresses(result, observed)
    assert result.model_dump() == before


def contact(payload, value):
    return DebtorContact.model_validate({**{k: v for k, v in payload["debtor"].items()
                                          if k not in ("billing", "delivery")},
                                       "source_customer_id": value})


@pytest.mark.parametrize("value", [None, "wrong"])
def test_visible_customer_id_cannot_be_lost(payload, value):
    ocr = {"lines": [line("CUSTOMER ID", 400, 30), line("SOURCE-123", 400, 60)]}
    with pytest.raises(ReviewRequired, match="customer ID"):
        verify_customer_id(contact(payload, value), ocr)


def test_matching_customer_id_and_absent_label(payload):
    ocr = {"lines": [line("CUSTOMER ID", 400, 30), line("SOURCE-123", 400, 60)]}
    verify_customer_id(contact(payload, "SOURCE-123"), ocr)
    verify_customer_id(contact(payload, None), {"lines": []})
