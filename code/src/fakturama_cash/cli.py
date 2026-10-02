import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from .errors import ReviewRequired
from .extraction import extract
from .models import OrderInput
from .progress import TerminalProgress
from .state import Journal, fingerprint, semantic_fingerprint, write_json
from .ui import UIAAdapter, load_profile
from .workflow import ACTIONS, QUERIES, Workflow


def parser():
    progress_options = argparse.ArgumentParser(add_help=False)
    # SUPPRESS lets --quiet work before or after the subcommand without one
    # parser's default overwriting the explicitly supplied value from the other.
    progress_options.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS,
                                  help="Suppress progress lines; preserve the final result/error")
    result = argparse.ArgumentParser(description="Fakturama image-to-cash prototype; local evidence is private",
                                     parents=[progress_options])
    sub = result.add_subparsers(dest="command", required=True)
    for command in ("validate", "run"):
        p = sub.add_parser(command, parents=[progress_options])
        p.add_argument("image", type=Path)
        p.add_argument("--runs", type=Path, default=Path(os.environ.get("FAKTURAMA_RUNS", "runs")))
        if command == "run":
            p.add_argument("--profile", type=Path, default=Path(os.environ.get("FAKTURAMA_UI_PROFILE", "config/live.json")))
    p = sub.add_parser("validate-json", parents=[progress_options], help="Validate extracted JSON or a synthetic test fixture; never writes to Fakturama")
    p.add_argument("json", type=Path)
    p = sub.add_parser("diagnose", parents=[progress_options], help="Read-only capture of the Fakturama UI tree and screenshot")
    p.add_argument("--profile", type=Path, default=Path("config/observed.partial.json"))
    p.add_argument("--out", type=Path, default=Path("evidence/private/diagnostics"))
    p = sub.add_parser("ocr", parents=[progress_options], help="Capture raw Windows OCR; does not produce an approved order or modify Fakturama")
    p.add_argument("image", type=Path)
    p.add_argument("--out", type=Path, default=Path("evidence/private/ocr"))
    p = sub.add_parser("check-profile", parents=[progress_options], help="Report missing UI calibration without writing to Fakturama")
    p.add_argument("profile", type=Path)
    p = sub.add_parser("reconcile", parents=[progress_options], help="Read-only persisted-document inspection; never resumes writes")
    p.add_argument("checkpoint", type=Path)
    p.add_argument("--profile", type=Path, required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    with TerminalProgress(enabled=not getattr(args, "quiet", False)) as progress:
        return execute(args, progress)


def execute(args, progress):
    error_path = None
    progress.update(f"Starting {args.command}")
    try:
        if args.command == "validate-json":
            progress.update("Reading structured input and checking fields and arithmetic (no UI writes)")
            order = OrderInput.model_validate_json(args.json.read_text(encoding="utf-8")).reconcile()
            progress.finish("JSON validation complete")
            print(json.dumps({"status": "validated_json_only", "items": len(order.items), "total": str(order.source_total)}))
            return 0
        if args.command == "diagnose":
            progress.update("Connecting to Fakturama and capturing UI tree/screenshot (read-only)")
            adapter = UIAAdapter(load_profile(args.profile))
            evidence = adapter.capture(args.out, "fakturama")
            progress.finish("Diagnostic capture complete")
            print(json.dumps(evidence))
            return 0
        if args.command == "ocr":
            progress.update("Running Windows OCR and saving raw observations (no UI writes)")
            from .windows_ocr import capture_ocr
            capture_ocr(args.image, args.out)
            progress.finish("Raw OCR capture complete; not validated business input")
            print(json.dumps({"status": "raw_ocr_only", "evidence": str(args.out),
                              "warning": "OCR is not validated business input; no UI actions performed"}))
            return 0
        if args.command == "check-profile":
            progress.update("Checking required UI mappings without connecting to Fakturama")
            # Profile completeness can be checked on any OS without importing pywinauto.
            UIAAdapter(load_profile(args.profile), desktop=object()).preflight(ACTIONS, QUERIES, connect=False)
            progress.finish("UI mapping completeness check passed; live behavior remains unverified")
            print("Profile complete; live behavior still needs verification")
            return 0
        if args.command == "reconcile":
            progress.update("Reading checkpoint and inspecting persisted documents (no business writes)")
            checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
            ui = UIAAdapter(load_profile(args.profile))
            ui.preflight({"open_documents"}, {"documents"})
            ui.act("open_documents", {})
            rows = ui.read("documents", {})
            identifiers = set(checkpoint.get("identifiers", {}).values())
            matched = [r for r in rows if r.get("no") in identifiers]
            progress.finish("Document inspection complete; manual review required, no automatic resume")
            print(json.dumps({"status": "inspection_only", "rows": matched,
                              "checkpoint": checkpoint, "safe_next_action": "Review persisted data. Automatic resume is not implemented."}, default=str))
            return 2
        if args.command == "run":
            # Reject incomplete configuration before a slow model request. Use a
            # non-connected adapter here; the workflow rechecks the live UI later.
            progress.update("Checking UI profile before image extraction (no desktop actions)")
            UIAAdapter(load_profile(args.profile), desktop=object()).preflight(ACTIONS, QUERIES, connect=False)
        progress.update("Fingerprinting input and preparing private extraction evidence")
        image_hash = fingerprint(args.image)
        # Preserve each extraction attempt, including failed/changed model output.
        # The stable hash directory still owns the write-ahead workflow checkpoint.
        directory = args.runs / image_hash / "extractions" / uuid4().hex
        directory.mkdir(parents=True, exist_ok=True)
        error_path = directory / "review-required.json"
        progress.update(f"Extraction evidence: {directory}")
        order = extract(args.image, directory, progress=progress.update)
        if args.command == "validate":
            progress.finish("Validation-only command complete; Fakturama was not modified")
            print(json.dumps({"status": "validated_image", "items": len(order.items), "total": str(order.source_total), "evidence": str(directory)}))
            return 0
        progress.update("Acquiring run lock and preparing the desktop workflow")
        with Journal(args.runs, image_hash, semantic_fingerprint(order)) as journal:
            ui = UIAAdapter(load_profile(args.profile))
            identifiers = Workflow(ui, journal, progress=progress.update).run(order)
        progress.finish("Workflow complete; persisted Order and Invoice verified")
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
        progress.finish(f"STOPPED at {details['stage']}: review required; see the error details below")
        print(json.dumps({"status": "review_required", **details, "evidence": str(error_path) if error_path else None}, default=str), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
