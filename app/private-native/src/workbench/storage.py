"""Local JSON snapshots with optimistic version checking and atomic replacement."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise ValueError("Invalid task or round identifier.")
    return value


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class VersionConflict(ValueError):
    pass


class TaskStore:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = RLock()

    def path(self, task_id):
        path = self.root / (validate_id(task_id) + ".json")
        if path.is_symlink():
            raise ValueError("Linked task files are not accepted.")
        return path

    def load(self, task_id):
        with self.lock:
            path = self.path(task_id)
            if not path.exists():
                raise KeyError(task_id)
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("id") != task_id or type(data.get("version")) is not int:
                raise ValueError("Task snapshot identity/version mismatch.")
            return data

    def load_all(self):
        if not self.root.exists():
            return []
        # An unreadable snapshot is a startup blocker, not silently lost history.
        return [self.load(p.stem) for p in sorted(self.root.glob("*.json"))]

    def commit(self, task, expected_version):
        with self.lock:
            path = self.path(task["id"])
            actual = self.load(task["id"])["version"] if path.exists() else -1
            if actual != expected_version:
                raise VersionConflict("State changed since the proposed update; no overwrite.")
            value = deepcopy(task)
            value["version"] = actual + 1
            value["updated_at"] = now()
            atomic_json(path, value)
            return value
