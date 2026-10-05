"""Run a labelled synthetic transaction in an explicitly authorized test workspace.

This exercises Workflow directly from validated JSON; image extraction is checked
separately by the normal validate/run CLI. Writes use the same mutation journal.
"""
import argparse
import json
from pathlib import Path

from fakturama_cash.models import OrderInput
from fakturama_cash.notifications import capture_finished
from fakturama_cash.state import Journal, fingerprint, semantic_fingerprint
from fakturama_cash.ui import UIAAdapter, load_profile
from fakturama_cash.workflow import Workflow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--profile', type=Path, default=Path('config/live-profile.json'))
    parser.add_argument('--runs', type=Path, default=Path('evidence/private/live-smoke'))
    parser.add_argument('--quiet', action='store_true', help='Suppress progress and completion sounds')
    args = parser.parse_args(argv)
    success = False
    try:
        order = OrderInput.model_validate_json(args.fixture.read_text(encoding='utf-8')).reconcile()
        if not order.external_reference.startswith('CODEX-'):
            parser.error('The smoke fixture must have a CODEX- test reference')
        with Journal(args.runs, fingerprint(args.fixture), semantic_fingerprint(order)) as journal:
            ui = UIAAdapter(load_profile(args.profile))
            progress = None if args.quiet else lambda text: print(text, flush=True)
            result = Workflow(ui, journal, progress=progress).run(order)
        print(json.dumps({'status': 'complete', **result,
                          'checkpoint': str(journal.path), 'evidence': str(journal.directory)}), flush=True)
        success = True
    finally:
        if not args.quiet:
            capture_finished(success=success)


if __name__ == '__main__':
    main()
