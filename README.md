# Fakturama Image to Cash

Windows automation that reads one order image, creates an Order through Fakturama's UI, generates its linked Invoice, applies the source payment status, and verifies the saved records.

The implementation uses Python, Windows OCR, an Ollama-compatible vision model, and Microsoft UI Automation. It targets the observed English Fakturama 2.2.0 UI and the assignment's EUR image layout. Work is on the **Development** branch.

## Current status

The latest image-driven transaction saved **PO000011 → INV000005**, with Net EUR 570.00, VAT EUR 108.30, Total EUR 678.30, and paid Bank Transfer dated 18 July 2026. The command stopped at the final Invoice reopen because its table header differed from calibration. After correcting that mapping, a separate read-only check reopened and verified the saved Invoice. The original stopped checkpoint remains preserved; this result is not presented as a fresh uninterrupted run after the correction.

The current automated suite has **414 passing tests**. Tests do not perform live Fakturama writes. See [verification](documents/implementation/verification.md) for the evidence and practical limits.

## Setup and use

Use **Windows CMD** and follow [the setup and run guide](code/README.md). It covers Python, English Windows OCR, Ollama, device calibration, image validation, running the workflow, and recovery.

If the local GPU backend returns the HTTP 500/token-repeat error observed during development, the guide includes the explicit CPU-only fallback:

```bat
set "FAKTURAMA_VISION_CPU_ONLY=1"
```

Set it in the same CMD session as the automation, then validate the image again before running the UI workflow. CPU inference is slower; it uses the same model and validation rules.

## Repository

| Location | Purpose |
| --- | --- |
| [code/](code/README.md) | Source, tests, component mappings, profile builder, and CLI |
| [documents/implementation/](documents/implementation/) | Current requirements, UI contract, verification, and remaining work |
| [documents/HANDOFF.md](documents/HANDOFF.md) | Short continuation guide and latest saved transaction |

Source images, model responses, screenshots, run evidence, local profiles, and Word design artifacts are local deliverables and are not bundled in a clean clone. Supply a readable raster order image; the CLI does not accept the assignment DOCX directly.

Each explicit `run` starts a **new Order**. It does not resume a checkpoint or deduplicate earlier transactions. Review recorded identifiers after a failure before starting another run.
