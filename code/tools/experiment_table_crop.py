"""Isolated OCR-anchored table experiment. Never invokes the Fakturama UI."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image

from fakturama_cash.progress import TerminalProgress
from fakturama_cash.windows_ocr import capture_ocr


from fakturama_cash.table_crop import ItemTable, TABLE_SYSTEM as SYSTEM, table_bounds


def run(image_path, output, report, *, crop_only=False):
    output.mkdir(parents=True, exist_ok=False)
    report("Reading original image with Windows OCR for table anchors")
    ocr = capture_ocr(image_path, output)
    box = table_bounds(ocr)
    with Image.open(image_path) as original:
        if original.size != (ocr["width"], ocr["height"]):
            raise ValueError("OCR coordinates do not match the source dimensions")
        original.crop(box).save(output / "table.png")
    metadata = {"source": str(image_path.resolve()),
                "source_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "crop_box": box, "resized": False, "scope": "table-only experiment"}
    (output / "crop.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    report(f"Saved original-resolution crop: {box[2]} x {box[3] - box[1]} pixels")
    if crop_only:
        return {"status": "crop_ready", "evidence": str(output.resolve())}
    return infer(output, report)


def infer(output, report):
    model = os.environ.get("FAKTURAMA_VISION_MODEL")
    if not model:
        raise ValueError("FAKTURAMA_VISION_MODEL is not configured")
    schema = ItemTable.model_json_schema(mode="serialization")
    prompt = "Transcribe the table. JSON schema:\n" + json.dumps(schema)
    body = {"model": model, "stream": False, "format": schema,
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt,
                          "images": [base64.b64encode((output / "table.png").read_bytes()).decode("ascii")]}]}
    # Preserve instructions without duplicating base64 image data or the token.
    (output / "request-metadata.json").write_text(json.dumps(
        {"model": model, "system": SYSTEM, "prompt": prompt, "schema": schema,
         "temperature": 0, "timeout_seconds": 1200}, indent=2), encoding="utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("FAKTURAMA_VISION_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(os.environ.get("FAKTURAMA_VISION_URL", "http://localhost:11434/api/chat"),
                      data=json.dumps(body).encode(), headers=headers, method="POST")
    report("Waiting for table-only model response; socket timeout is 1200s")
    with urlopen(request, timeout=1200) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("Response exceeds 4 MB")
    (output / "response.json").write_bytes(raw)
    envelope = json.loads(raw)
    content = envelope["message"]["content"]
    (output / "raw.txt").write_text(content, encoding="utf-8")
    table = ItemTable.model_validate_json(content)
    (output / "normalized.json").write_text(table.model_dump_json(indent=2), encoding="utf-8")
    checks = [{"row": i, "computed_net": str(line.net), "printed_net": str(line.source_net),
               "matches": line.net == line.source_net} for i, line in enumerate(table.items, 1)]
    result = {"status": "table_checks_passed_needs_visual_review" if not table.extraction_issues
              and all(check["matches"] for check in checks) else "review_required",
              "line_checks": checks, "extraction_issues": table.extraction_issues,
              "total_seconds": envelope.get("total_duration", 0) / 1e9,
              "evidence": str(output.resolve()), "production_integration": False}
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--crop-only", action="store_true")
    args = parser.parse_args()
    output = args.out or Path("evidence/private/table-crop") / uuid4().hex
    with TerminalProgress() as progress:
        try:
            result = run(args.image, output, progress.update, crop_only=args.crop_only)
        except Exception as exc:
            result = {"status": "experiment_failed", "reason": str(exc),
                      "evidence": str(output.resolve())}
            progress.finish("Experiment stopped; no Fakturama changes")
            print(json.dumps(result))
            return 1
        progress.finish("Experiment complete; no Fakturama changes")
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
