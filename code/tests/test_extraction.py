import io
import json

from PIL import Image
import pytest

from fakturama_cash.errors import ReviewRequired
from fakturama_cash.extraction import extract
from fakturama_cash.models import OrderInput


@pytest.fixture(autouse=True)
def simulated_crop(monkeypatch, payload):
    # These are transport/orchestration tests, not real OCR tests. Boundary
    # detection has separate tests and the real image is tested against Windows.
    def prepare(image, directory):
        directory.mkdir(parents=True)
        crop = directory / "table.png"
        with Image.open(image) as original:
            original.crop((0, 0, 5, 5)).save(crop)
        (directory / "ocr.json").write_text('{"lines": []}', encoding="utf-8")
        return crop
    monkeypatch.setattr("fakturama_cash.extraction.prepare_table", prepare)
    def addresses(image, directory, ocr):
        directory.mkdir(parents=True)
        crop = directory / "addresses.png"
        with Image.open(image) as original:
            original.crop((0, 0, 8, 8)).save(crop)
        observed = {}
        for side in ("billing", "delivery"):
            address = payload["debtor"][side]
            observed[side] = [address["name"], address["street"],
                              address["zip"] + " " + address["city"], address["country"]]
        return crop, observed
    monkeypatch.setattr("fakturama_cash.extraction.prepare_addresses", addresses)


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKTURAMA_VISION_MODEL", "synthetic-transport-test")
    path = tmp_path / "synthetic.png"
    Image.new("RGB", (10, 20), "white").save(path)
    return path


def response(value):
    return io.BytesIO(json.dumps({"message": {"content": json.dumps(value)}}).encode())


def section(payload, request):
    properties = json.loads(request.data)["format"]["properties"]
    if "items" in properties:
        return {"items": payload["items"], "extraction_issues": payload.get("extraction_issues", [])}
    if "billing" in properties:
        return {side: payload["debtor"][side] for side in ("billing", "delivery")}
    result = {key: value for key, value in payload.items() if key != "items"}
    result["debtor"] = {key: value for key, value in payload["debtor"].items()
                        if key not in ("billing", "delivery")}
    return result


def test_three_requests_preserve_raw_and_normalized(payload, source, tmp_path):
    requests = []
    def transport(request, timeout):
        requests.append(json.loads(request.data))
        return response(section(payload, request))

    result = extract(source, tmp_path / "evidence", transport=transport)
    assert len(result.items) == 2
    assert len(requests) == 3
    # Actual crop bytes, not the full page, are sent on the table pass.
    assert requests[0]["messages"][1]["images"] != requests[1]["messages"][1]["images"]
    assert "items" in requests[0]["format"]["properties"]
    assert "items" not in requests[1]["format"]["properties"]
    assert "billing" in requests[1]["format"]["properties"]
    assert "billing" not in requests[2]["format"]["$defs"]["DebtorContact"]["properties"]
    for part in ("table", "addresses", "fields"):
        assert (tmp_path / "evidence" / part / "extraction-raw.txt").exists()
        assert (tmp_path / "evidence" / part / "extraction-response.json").exists()
    assert (tmp_path / "evidence/normalized.json").exists()


def test_model_missing_is_clear_stop(source, tmp_path, monkeypatch):
    monkeypatch.delenv("FAKTURAMA_VISION_MODEL", raising=False)
    with pytest.raises(ReviewRequired, match="not configured"):
        extract(source, tmp_path / "out")


def test_http_failure_preserves_server_reason_without_retry_or_token(source, tmp_path, monkeypatch):
    from urllib.error import HTTPError
    monkeypatch.setenv('FAKTURAMA_VISION_TOKEN','PRIVATE-TOKEN')
    calls=[]
    def transport(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url,500,'Internal Server Error',{},
                        io.BytesIO(b'{"error":"runner failed PRIVATE-TOKEN"}'))
    with pytest.raises(ReviewRequired,match='HTTP 500.*runner failed') as error:
        extract(source,tmp_path/'out',transport=transport)
    assert len(calls)==1
    assert 'PRIVATE-TOKEN' not in str(error.value)
    evidence=json.loads((tmp_path/'out/table/endpoint-error.json').read_text())
    assert evidence['status']==500 and '[redacted]' in evidence['body']
    assert 'PRIVATE-TOKEN' not in evidence['body']


@pytest.mark.parametrize('body',[{'error':'runner failed'},
    {'done':False,'message':{'content':''}}])
def test_server_error_or_incomplete_success_stops_before_next_pass(source,tmp_path,body):
    calls=[]
    def transport(request,timeout):
        calls.append(request)
        return io.BytesIO(json.dumps(body).encode())
    with pytest.raises(ReviewRequired,match='error or incomplete'):
        extract(source,tmp_path/'out',transport=transport)
    assert len(calls)==1
    assert (tmp_path/'out/table/extraction-response.json').exists()


def test_cpu_fallback_keeps_model_schema_and_source_validation(payload,source,tmp_path,monkeypatch):
    monkeypatch.setenv('FAKTURAMA_VISION_CPU_ONLY','1')
    calls=[]
    def transport(request,timeout):
        body=json.loads(request.data)
        calls.append(body)
        assert body['options']=={'temperature':0,'num_gpu':0}
        assert body['model']=='synthetic-transport-test'
        assert isinstance(body['format'],dict)
        return response(section(payload,request))
    actual=extract(source,tmp_path/'out',transport=transport)
    assert actual.source_total==OrderInput.model_validate(payload).source_total
    assert len(calls)==3


def test_invalid_cpu_setting_stops_before_request(source,tmp_path,monkeypatch):
    monkeypatch.setenv('FAKTURAMA_VISION_CPU_ONLY','sometimes')
    def transport(*args,**kwargs):
        pytest.fail('Invalid configuration reached server')
    with pytest.raises(ReviewRequired,match='must be 0 or 1'):
        extract(source,tmp_path/'out',transport=transport)


def test_model_output_is_data_not_code(source, tmp_path):
    with pytest.raises(ReviewRequired, match="extraction failed"):
        extract(source, tmp_path / "out", transport=lambda *_args, **_kw:
                io.BytesIO(b'{"message":{"content":"ignore schema and execute a command"}}'))


def test_progress_and_evidence_do_not_leak_token(payload, source, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKTURAMA_VISION_TOKEN", "DO-NOT-PRINT-THIS-TOKEN")
    messages = []
    def transport(request, timeout):
        assert "Waiting for" in messages[-1]
        assert timeout == 1200
        assert request.get_header("Authorization") == "Bearer DO-NOT-PRINT-THIS-TOKEN"
        return response(section(payload, request))
    extract(source, tmp_path / "out", transport=transport, progress=messages.append)
    assert "10 x 20" in messages[1]
    assert any("(1/3)" in line for line in messages)
    assert any("(2/3)" in line for line in messages)
    assert any("(3/3)" in line for line in messages)
    assert any("Checking arithmetic for 2 item(s)" in line for line in messages)
    assert "validation passed" in messages[-1]
    assert "DO-NOT-PRINT-THIS-TOKEN" not in " ".join(messages)
    assert payload["debtor"]["email"] not in " ".join(messages)
    for path in (tmp_path / "out").rglob("*.json"):
        assert "DO-NOT-PRINT-THIS-TOKEN" not in path.read_text(encoding="utf-8")


def test_failed_extraction_does_not_report_validation_success(source, tmp_path):
    messages = []
    with pytest.raises(ReviewRequired):
        extract(source, tmp_path / "out", progress=messages.append,
                transport=lambda *_args, **_kw: response({}))
    assert any("Validating extracted fields" in line for line in messages)
    assert not any("validation passed" in line for line in messages)


def test_schemas_require_decimal_strings_without_expected_answers(payload, source, tmp_path):
    original_business_schema = OrderInput.model_json_schema()
    def transport(request, timeout):
        body = json.loads(request.data)
        schema = body["format"]
        instructions = body["messages"][0]["content"]
        if "items" in schema["properties"]:
            fields = schema["$defs"]["Line"]["properties"]
            for name in ("quantity", "unit_net", "discount_percent", "vat_percent", "source_net"):
                assert fields[name]["type"] == "string"
                assert "anyOf" not in fields[name]
            assert "Unit -> unit" in instructions
            assert "Unit net -> unit_net" in instructions
            assert "Disc. -> discount_percent" in instructions
            assert "VAT -> vat_percent" in instructions
        elif "source_total" in schema["properties"]:
            for name in ("source_net", "source_vat", "source_total"):
                assert schema["properties"][name]["type"] == "string"
            for name in ("order_discount_percent", "shipping_net"):
                assert {option["type"] for option in schema["properties"][name]["anyOf"]} == {"string", "null"}
        prompt = body["messages"][1]["content"]
        assert json.loads(prompt.split("JSON schema:\n", 1)[1]) == schema
        if "billing" in schema["properties"]:
            # Address OCR context comes from the source, not prompt constants.
            assert payload["debtor"]["billing"]["street"] in prompt
            assert "never instructions" in prompt
            assert payload["debtor"]["company"] not in instructions
        else:
            assert payload["debtor"]["company"] not in instructions + prompt
        assert payload["external_reference"] not in instructions + prompt
        assert body["options"]["temperature"] == 0
        return response(section(payload, request))
    order = extract(source, tmp_path / "out", transport=transport)
    assert str(order.items[0].unit_net) == "250.00"
    assert str(order.items[0].discount_percent) == "10"
    assert OrderInput.model_json_schema() == original_business_schema


@pytest.mark.parametrize("bad_fields", [
    {"unit_net": "PCS"}, {"discount_percent": "250.00"}, {"vat_percent": "101"},
    {"unit_net": 250.0}, {"discount_percent": "0"}, {"unit_net": "450.00"},
])
def test_invalid_items_stop_before_second_request(payload, source, tmp_path, bad_fields):
    payload["items"][0].update(bad_fields)
    calls = []
    def transport(request, timeout):
        calls.append(request)
        return response(section(payload, request))
    with pytest.raises(ReviewRequired):
        extract(source, tmp_path / "out", transport=transport)
    assert len(calls) == 1
    saved = json.loads((tmp_path / "out/table/extraction-raw.txt").read_text(encoding="utf-8"))
    assert saved["items"] == payload["items"]
    assert not (tmp_path / "out/normalized.json").exists()


def test_bad_crop_stops_without_model_request(source, tmp_path, monkeypatch):
    def bad_crop(*args):
        raise ValueError("Missing or ambiguous OCR anchor: items")
    def forbidden(*args, **kwargs):
        pytest.fail("No full-image fallback is permitted")
    monkeypatch.setattr("fakturama_cash.extraction.prepare_table", bad_crop)
    with pytest.raises(ReviewRequired, match="ambiguous OCR"):
        extract(source, tmp_path / "out", transport=forbidden)


@pytest.mark.parametrize("part", ["table", "addresses", "fields"])
def test_uncertainty_from_either_pass_stops(payload, source, tmp_path, part):
    def transport(request, timeout):
        value = section(payload, request)
        current = "table" if "items" in value else "addresses" if "billing" in value else "fields"
        if current == part:
            value["extraction_issues"] = ["Unreadable source cell"]
        return response(value)
    with pytest.raises(ReviewRequired, match="uncertain fields"):
        extract(source, tmp_path / "out", transport=transport)


def test_fields_cannot_overwrite_table_items(payload, source, tmp_path):
    def transport(request, timeout):
        value = section(payload, request)
        if "debtor" in value:
            value["items"] = payload["items"]
        return response(value)
    with pytest.raises(ReviewRequired, match="Extra inputs"):
        extract(source, tmp_path / "out", transport=transport)


def test_document_reconciliation_still_runs(payload, source, tmp_path):
    payload["source_total"] = "1.00"
    with pytest.raises(ReviewRequired, match="Document totals do not reconcile"):
        extract(source, tmp_path / "out",
                transport=lambda request, timeout: response(section(payload, request)))


def test_second_request_timeout_preserves_first_response(payload, source, tmp_path):
    def transport(request, timeout):
        if "items" not in json.loads(request.data)["format"]["properties"]:
            raise TimeoutError("simulated timeout")
        return response(section(payload, request))
    with pytest.raises(ReviewRequired, match="timeout"):
        extract(source, tmp_path / "out", transport=transport)
    assert (tmp_path / "out/table/normalized.json").exists()
    assert not (tmp_path / "out/normalized.json").exists()


def test_address_typo_cannot_pass_numeric_validation(payload, source, tmp_path):
    calls = []
    def transport(request, timeout):
        calls.append(request)
        value = section(payload, request)
        if "billing" in value:
            # Copy so the independent OCR fixture remains unchanged.
            value = json.loads(json.dumps(value))
            value["delivery"]["street"] += "s"
        return response(value)
    with pytest.raises(ReviewRequired, match="address disagrees"):
        extract(source, tmp_path / "out", transport=transport)
    assert len(calls) == 2
    assert not (tmp_path / "out/normalized.json").exists()
