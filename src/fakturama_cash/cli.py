import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from .errors import ReviewRequired
from .extraction import extract
from .models import OrderInput
from .state import Journal, fingerprint, semantic_fingerprint, write_json
from .ui import UIAAdapter, load_profile
from .workflow import ACTIONS, QUERIES, Workflow


def parser():
    result = argparse.ArgumentParser(description="Fakturama image-to-cash prototype; local evidence is private")
    sub = result.add_subparsers(dest="command", required=True)
    for command in ("validate", "run"):
        p = sub.add_parser(command)
        p.add_argument("image", type=Path)
        p.add_argument("--runs", type=Path, default=Path(os.environ.get("FAKTURAMA_RUNS", "runs")))
        if command == "run":
            p.add_argument("--profile", type=Path, default=Path(os.environ.get("FAKTURAMA_UI_PROFILE", "config/live.json")))
    p = sub.add_parser("validate-json", help="Validate extracted JSON or a synthetic test fixture; never writes to Fakturama")
    p.add_argument("json", type=Path)
    p = sub.add_parser("diagnose", help="Read-only capture of the Fakturama UI tree and screenshot")
    p.add_argument("--profile", type=Path, default=Path("config/observed.partial.json"))
    p.add_argument("--out", type=Path, default=Path("evidence/private/diagnostics"))
    p = sub.add_parser("ocr", help="Capture raw Windows OCR; does not produce an approved order or modify Fakturama")
    p.add_argument("image", type=Path)
    p.add_argument("--out", type=Path, default=Path("evidence/private/ocr"))
    p = sub.add_parser("check-profile", help="Report missing UI calibration without writing to Fakturama")
    p.add_argument("profile", type=Path)
    p = sub.add_parser("reconcile", help="Read-only persisted-document inspection; never resumes writes")
    p.add_argument("checkpoint", type=Path)
    p.add_argument("--profile", type=Path, required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    error_path = None
    try:
        if args.command == "validate-json":
            order = OrderInput.model_validate_json(args.json.read_text(encoding="utf-8")).reconcile()
            print(json.dumps({"status": "validated_json_only", "items": len(order.items), "total": str(order.source_total)}))
            return 0
        if args.command == "diagnose":
            adapter = UIAAdapter(load_profile(args.profile))
            print(json.dumps(adapter.capture(args.out, "fakturama")))
            return 0
        if args.command == "ocr":
            from .windows_ocr import capture_ocr
            capture_ocr(args.image, args.out)
            print(json.dumps({"status": "raw_ocr_only", "evidence": str(args.out),
                              "warning": "OCR is not validated business input; no UI actions performed"}))
            return 0
        if args.command == "check-profile":
            # Profile completeness can be checked on any OS without importing pywinauto.
            UIAAdapter(load_profile(args.profile), desktop=object()).preflight(ACTIONS, QUERIES, connect=False)
            print("Profile complete; live behavior still needs verification")
            return 0
        if args.command == "reconcile":
            checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
            ui = UIAAdapter(load_profile(args.profile))
            ui.preflight({"open_documents"}, {"documents"})
            ui.act("open_documents", {})
            rows = ui.read("documents", {})
            identifiers = set(checkpoint.get("identifiers", {}).values())
            matched = [r for r in rows if r.get("no") in identifiers]
            print(json.dumps({"status": "inspection_only", "rows": matched,
                              "checkpoint": checkpoint, "safe_next_action": "Review persisted data. Automatic resume is not implemented."}, default=str))
            return 2
        image_hash = fingerprint(args.image)
        # Preserve each extraction attempt, including failed/changed model output.
        # The stable hash directory still owns the write-ahead workflow checkpoint.
        directory = args.runs / image_hash / "extractions" / uuid4().hex
        directory.mkdir(parents=True, exist_ok=True)
        error_path = directory / "review-required.json"
        order = extract(args.image, directory)
        if args.command == "validate":
            print(json.dumps({"status": "validated_image", "items": len(order.items), "total": str(order.source_total), "evidence": str(directory)}))
            return 0
        with Journal(args.runs, image_hash, semantic_fingerprint(order)) as journal:
            ui = UIAAdapter(load_profile(args.profile))
            identifiers = Workflow(ui, journal).run(order)
        print(json.dumps({"status": "complete", "identifiers": identifiers, "evidence": str(journal.directory),
                          "extraction_evidence": str(directory)}))
        return 0
    except Exception as exc:
        if isinstance(exc, ReviewRequired):
            details = exc.details
        else:
            details = {"stage": args.command, "reason": f"{type(exc).__name__}: {exc}",
                       "safe_next_action": "Inspect input/configuration and any private evidence. No automatic retry was attempted."}
        if error_path:
            write_json(error_path, details)
        print(json.dumps({"status": "review_required", **details, "evidence": str(error_path) if error_path else None}, default=str), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
