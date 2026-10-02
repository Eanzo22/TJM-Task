"""Read-only address diagnostic: fresh OCR, source crop, local vision, consistency.

This is not a transaction runner and does not reuse a saved model response.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from fakturama_cash.address_crop import ADDRESS_SYSTEM, AddressPair, prepare_addresses, verify_addresses
from fakturama_cash.extraction import request_section
from fakturama_cash.progress import TerminalProgress
from fakturama_cash.windows_ocr import capture_ocr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    directory = Path("evidence/private/address-check") / uuid4().hex
    directory.mkdir(parents=True)
    with TerminalProgress() as progress:
        try:
            model = os.environ.get("FAKTURAMA_VISION_MODEL")
            if not model:
                raise ValueError("FAKTURAMA_VISION_MODEL is not configured")
            progress.update("Capturing fresh local source OCR")
            ocr = capture_ocr(args.image, directory)
            crop, lines = prepare_addresses(args.image, directory, ocr)
            pair = request_section(crop, directory, AddressPair, ADDRESS_SYSTEM, "address-only response",
                                   url=os.environ.get("FAKTURAMA_VISION_URL", "http://localhost:11434/api/chat"),
                                   model=model, transport=urlopen, report=progress.update,
                                   source_observations=lines)
            verify_addresses(pair, lines)
            result = {"status": "address_consistency_passed", "evidence": str(directory.resolve())}
        except Exception as exc:
            result = {"status": "review_required", "reason": str(exc), "evidence": str(directory.resolve())}
        (directory / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        progress.finish("Address diagnostic complete; no UI actions")
        print(json.dumps(result))
    return 0 if result["status"] == "address_consistency_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
