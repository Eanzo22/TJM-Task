"""Run a labelled synthetic transaction in an explicitly authorized test workspace.

This exercises Workflow directly from validated JSON; image extraction is checked
separately by the normal validate/run CLI. Writes use the same mutation journal.
"""
import argparse
import json
from pathlib import Path

from fakturama_cash.models import OrderInput
from fakturama_cash.state import Journal, fingerprint, semantic_fingerprint
from fakturama_cash.ui import UIAAdapter, load_profile
from fakturama_cash.workflow import Workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--profile', type=Path, default=Path('config/live-profile.json'))
    parser.add_argument('--runs', type=Path, default=Path('evidence/private/live-smoke'))
    args = parser.parse_args()
    order = OrderInput.model_validate_json(args.fixture.read_text(encoding='utf-8')).reconcile()
    if not order.external_reference.startswith('CODEX-'):
        parser.error('The smoke fixture must have a CODEX- test reference')
    with Journal(args.runs, fingerprint(args.fixture), semantic_fingerprint(order)) as journal:
        ui = UIAAdapter(load_profile(args.profile))
        result = Workflow(ui, journal, progress=lambda text: print(text, flush=True)).run(order)
        print(json.dumps({'status': 'complete', **result}), flush=True)


if __name__ == '__main__':
    main()
