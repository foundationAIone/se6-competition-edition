"""Append-only JSONL audit log (V2).

Owns ``memory/audit_log.jsonl``.

Public surface is intentionally append + read only — there is **no**
delete, truncate, rotate, or overwrite API. Every entry is tolerated in
either V1 or V2 shape; missing fields default safely.

Local-only. No network, no shell, no writes outside ``memory/``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .project_memory import MEMORY_DIR, _resolve_under_memory  # type: ignore

DEFAULT_AUDIT_PATH: Path = MEMORY_DIR / "audit_log.jsonl"

CURRENT_AUDIT_SCHEMA_VERSION: int = 2


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _make_audit_id(ts: str, task: str, decision: str) -> str:
    h = hashlib.sha256(f"{ts}|{task}|{decision}".encode()).hexdigest()
    return h[:12]


class AuditEntry(BaseModel):
    """Tolerant V1/V2 audit entry.

    Only ``ts`` and ``task`` are strictly required; everything else
    defaults so old V1 lines load cleanly.
    """

    ts: str
    task: str
    intention: dict[str, Any] = Field(default_factory=dict)
    boundary: dict[str, Any] = Field(default_factory=dict)
    lattice: dict[str, Any] = Field(default_factory=dict)
    rotation: dict[str, Any] = Field(default_factory=dict)
    mirrors: dict[str, Any] = Field(default_factory=dict)
    classification: dict[str, Any] = Field(default_factory=dict)
    assimilation: dict[str, Any] = Field(default_factory=dict)
    next_state: dict[str, Any] = Field(default_factory=dict)
    feedback: dict[str, Any] = Field(default_factory=dict)
    state_transition: dict[str, Any] = Field(default_factory=dict)
    canonical_packet: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = CURRENT_AUDIT_SCHEMA_VERSION
    audit_id: str | None = None

    # Convenience accessors --------------------------------------------------

    @property
    def decision(self) -> str:
        return str(self.boundary.get("decision", "")) if self.boundary else ""

    @property
    def primary_element(self) -> str:
        return (
            str(self.classification.get("primary", ""))
            if self.classification
            else ""
        )

    @property
    def assimilation_score(self) -> float | None:
        if not self.assimilation:
            return None
        v = self.assimilation.get("score")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def ensure_audit_id(self) -> AuditEntry:
        if self.audit_id:
            return self
        new_id = _make_audit_id(self.ts, self.task, self.decision)
        data = self.model_dump()
        data["audit_id"] = new_id
        return AuditEntry(**data)


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------


def append_audit(
    entry: AuditEntry,
    path: Path = DEFAULT_AUDIT_PATH,
) -> AuditEntry:
    """Append *entry* as a single JSONL line. Returns the stored entry
    (with ``audit_id`` materialized if it was missing).
    """
    if not isinstance(entry, AuditEntry):
        raise TypeError("entry must be an AuditEntry")

    p = _resolve_under_memory(Path(path))
    p.parent.mkdir(parents=True, exist_ok=True)

    stored = entry.ensure_audit_id()
    line = stored.model_dump_json()
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return stored


# ---------------------------------------------------------------------------
# Read / iterate / filter
# ---------------------------------------------------------------------------


def _parse_line(line: str) -> AuditEntry | None:
    line = line.strip()
    if not line:
        return None
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    if "ts" not in raw or "task" not in raw:
        return None
    try:
        entry = AuditEntry(**raw)
    except (TypeError, ValueError):
        return None
    return entry.ensure_audit_id()


def iter_audit(path: Path = DEFAULT_AUDIT_PATH) -> Iterator[AuditEntry]:
    """Yield each :class:`AuditEntry` from *path* in file order.

    Tolerates V1-shaped lines (missing fields default).
    """
    p = _resolve_under_memory(Path(path))
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            entry = _parse_line(line)
            if entry is not None:
                yield entry


def find_audit(
    audit_id: str,
    path: Path = DEFAULT_AUDIT_PATH,
) -> AuditEntry | None:
    """Return the first entry whose ``audit_id`` matches, or ``None``."""
    if not isinstance(audit_id, str) or not audit_id:
        return None
    for entry in iter_audit(path):
        if entry.audit_id == audit_id:
            return entry
    return None


def filter_audit(
    decision: str | None = None,
    element: str | None = None,
    grep: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    path: Path = DEFAULT_AUDIT_PATH,
) -> list[AuditEntry]:
    """Return entries matching all supplied filters (read-only)."""
    grep_l = grep.lower() if isinstance(grep, str) and grep else None
    out: list[AuditEntry] = []
    for entry in iter_audit(path):
        if decision is not None and entry.decision != decision:
            continue
        if element is not None and entry.primary_element != element:
            continue
        if grep_l is not None and grep_l not in entry.task.lower():
            continue
        if min_score is not None or max_score is not None:
            score = entry.assimilation_score
            if score is None:
                continue
            if min_score is not None and score < min_score:
                continue
            if max_score is not None and score > max_score:
                continue
        out.append(entry)
    return out


__all__ = [
    "CURRENT_AUDIT_SCHEMA_VERSION",
    "DEFAULT_AUDIT_PATH",
    "AuditEntry",
    "append_audit",
    "filter_audit",
    "find_audit",
    "iter_audit",
]
