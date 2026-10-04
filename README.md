# Workspace layout

- **[code/](code/README.md)** — Python source, tests, configuration, dependency setup, run evidence and document-generation scripts.
- **[documents/](documents/)** — assignment, design documents, simple/detailed flowcharts, implementation notes and document-review assets.
- `.venv/`, `.git/` and the existing `.pytest_cache/` remain shared workspace tooling. Windows prevented moving the active environment/cache; no dependencies were removed.

Run the project from `code/`:

```powershell
cd "D:\TJM Task\Implementation\TJM-Task\code"
New-Item -ItemType Directory -Path '.pytest_runs' -Force | Out-Null
$testRun = Join-Path '.pytest_runs' ([guid]::NewGuid().ToString('N'))
..\.venv\Scripts\python.exe -m pytest -q --basetemp $testRun
..\.venv\Scripts\fakturama-cash.exe --help
```

Full setup and current implementation limits are in [code/README.md](code/README.md).

The unique test directory avoids a Windows ownership conflict in the existing system pytest temp directory. The shared environment uses Python 3.12, matching its installed native dependencies.
