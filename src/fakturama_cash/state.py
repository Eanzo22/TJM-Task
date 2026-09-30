"""Private evidence and a write-ahead mutation journal (not automatic crash resume)."""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .errors import ReviewRequired


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def semantic_fingerprint(order):
    return hashlib.sha256(order.model_dump_json().encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    # Windows indexers/AV can briefly hold the destination. Retry the atomic file
    # replacement only; never retry the business action that follows this write.
    for attempt in range(5):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


class Journal:
    def __init__(self, root, image_hash, order_hash):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.directory = self.root / image_hash
        self.directory.mkdir(exist_ok=True)
        self.path = self.directory / "checkpoint.json"
        self.data = {"image_fingerprint": image_hash, "order_fingerprint": order_hash,
                     "stage": "new", "status": "new", "identifiers": {}, "actions": {}, "evidence": []}
        self.lock_path = self.root / ".active-run.lock"
        self.lock_fd = None

    def __enter__(self):
        try:
            self.lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.lock_fd, str(os.getpid()).encode())
        except FileExistsError as exc:
            raise ReviewRequired("Another run or a stale lock exists", stage="preflight",
                                 next_action="Check the process in .active-run.lock. Reconcile any unfinished run before removing a stale lock.") from exc
        return self

    def __exit__(self, *_):
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_path.unlink(missing_ok=True)

    def guard_prior_run(self):
        for path in self.root.glob("*/checkpoint.json"):
            previous = json.loads(path.read_text(encoding="utf-8"))
            same = (previous.get("image_fingerprint") == self.data["image_fingerprint"]
                    or previous.get("order_fingerprint") == self.data["order_fingerprint"])
            if same and previous.get("actions"):
                raise ReviewRequired("A prior run recorded business actions for this input", stage="preflight",
                                     observed={"checkpoint": str(path), "status": previous.get("status"),
                                               "identifiers": previous.get("identifiers")},
                                     next_action="Run reconcile against the recorded checkpoint. Do not delete it to force a rerun.")

    def event(self, event, **fields):
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, default=str) + "\n")

    def flush(self):
        write_json(self.path, self.data)

    def mutate(self, name, operation):
        if name in self.data["actions"]:
            raise ReviewRequired("Refusing to repeat a mutation", stage=name, observed=self.data["actions"][name])
        self.data.update(stage=name, status="running")
        # Persist intent before the click. A timeout could occur after Fakturama accepted it.
        self.data["actions"][name] = "pending"
        self.flush()
        self.event("mutation_intent", action=name)
        try:
            result = operation()
        except Exception:
            self.data["actions"][name] = "uncertain"
            self.flush()
            raise
        self.data["actions"][name] = "returned_unverified"
        self.flush()
        return result

    def verified(self, name):
        self.data["stage"] = name
        self.event("verified", stage=name)
        self.flush()

    def record_evidence(self, evidence):
        self.data["evidence"].append(evidence)
        if self.data["actions"]:
            self.flush()
