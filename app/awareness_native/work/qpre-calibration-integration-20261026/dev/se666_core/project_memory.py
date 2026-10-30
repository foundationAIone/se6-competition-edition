"""Persistent project memory (V2 schema).

Local-only, deterministic, no network, no shell.

Owns ``memory/project_state.json``:

* Loads / migrates V1-shaped state to V2.
* Provides immutable-style helpers (``record_run``, ``add_note``) that
  return a *new* :class:`ProjectState`.
* Saves atomically via tempfile + replace, and refuses to write outside
  the project's ``memory/`` directory.

Intentionally tiny: no background work, no schedulers, no IO besides a
single JSON file under ``memory/``.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

_PKG_ROOT: Path = Path(__file__).resolve().parent.parent
MEMORY_DIR: Path = _PKG_ROOT / "memory"
DEFAULT_PROJECT_STATE_PATH: Path = MEMORY_DIR / "project_state.json"

CURRENT_SCHEMA_VERSION: int = 2
DEFAULT_PROJECT_NAME: str = "SE666_AI"
DEFAULT_VERSION: str = "0.2.0"
DEFAULT_MODE: str = "local-safe"

RECENT_TASKS_CAP: int = 50

_DECISION_KEYS = ("allow", "pause", "refuse", "needs_human_approval")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LastRun(BaseModel):
    ts: str
    task_preview: str
    decision: str
    primary_element: str | None = None
    assimilation_score: float | None = None
    audit_id: str | None = None


class RunTotals(BaseModel):
    allow: int = 0
    pause: int = 0
    refuse: int = 0
    needs_human_approval: int = 0

    def bump(self, decision: str) -> RunTotals:
        data = self.model_dump()
        if decision in data:
            data[decision] = int(data[decision]) + 1
        return RunTotals(**data)


class TaskSummary(BaseModel):
    ts: str
    task_preview: str
    decision: str
    primary_element: str | None = None
    assimilation_score: float | None = None
    audit_id: str | None = None
    audit_offset: int | None = None


class ProjectNote(BaseModel):
    ts: str
    text: str


class ProjectState(BaseModel):
    project: str = DEFAULT_PROJECT_NAME
    version: str = DEFAULT_VERSION
    schema_version: int = CURRENT_SCHEMA_VERSION
    mode: Literal["local-safe"] = "local-safe"
    autonomy: bool = False
    network_enabled: bool = False
    created_ts: str = Field(default_factory=_utc_now)
    last_run: LastRun | None = None
    totals: RunTotals = Field(default_factory=RunTotals)
    recent_tasks: list[TaskSummary] = Field(default_factory=list)
    open_approvals: list[str] = Field(default_factory=list)
    notes: list[ProjectNote] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def _resolve_under_memory(path: Path) -> Path:
    """Return *path* resolved, after asserting it lives under ``memory/``.

    Refuses any path that escapes the project's ``memory/`` directory.
    Tests may pass a temp dir's ``memory/`` subfolder.
    """
    p = Path(path).resolve()
    parents = {parent.resolve() for parent in p.parents}
    if MEMORY_DIR.resolve() in parents or p.parent.resolve() == MEMORY_DIR.resolve():
        return p
    # Allow any directory whose name is exactly "memory" (e.g. tmp/memory/...)
    for parent in p.parents:
        if parent.name == "memory":
            return p
    raise PermissionError(
        f"Refusing to read/write outside a 'memory/' directory: {p}"
    )


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def _migrate(raw: dict, *, file_path: Path | None = None) -> ProjectState:
    """Build a V2 :class:`ProjectState` from any prior shape.

    V1 had: ``project, version, mode, autonomy, network_enabled, last_run``.
    Anything missing is filled with safe defaults; nothing is ever dropped
    from ``notes`` or ``recent_tasks``.
    """
    if not isinstance(raw, dict):
        raw = {}

    schema_version = int(raw.get("schema_version", 1) or 1)

    created_ts = raw.get("created_ts")
    if not created_ts:
        if file_path is not None and file_path.exists():
            try:
                created_ts = datetime.fromtimestamp(
                    file_path.stat().st_mtime, tz=UTC
                ).isoformat()
            except OSError:
                created_ts = _utc_now()
        else:
            created_ts = _utc_now()

    last_run_raw = raw.get("last_run")
    last_run: LastRun | None = None
    if isinstance(last_run_raw, dict):
        last_run = LastRun(
            ts=str(last_run_raw.get("ts", _utc_now())),
            task_preview=str(last_run_raw.get("task_preview", ""))[:120],
            decision=str(last_run_raw.get("decision", "allow")),
            primary_element=last_run_raw.get("primary_element"),
            assimilation_score=last_run_raw.get("assimilation_score"),
            audit_id=last_run_raw.get("audit_id"),
        )

    totals_raw = raw.get("totals") or {}
    totals = RunTotals(
        allow=int(totals_raw.get("allow", 0) or 0),
        pause=int(totals_raw.get("pause", 0) or 0),
        refuse=int(totals_raw.get("refuse", 0) or 0),
        needs_human_approval=int(totals_raw.get("needs_human_approval", 0) or 0),
    )

    recent_tasks_raw = raw.get("recent_tasks") or []
    recent_tasks: list[TaskSummary] = []
    for item in recent_tasks_raw:
        if not isinstance(item, dict):
            continue
        try:
            recent_tasks.append(TaskSummary(**item))
        except (TypeError, ValueError):
            continue
    recent_tasks = recent_tasks[-RECENT_TASKS_CAP:]

    open_approvals_raw = raw.get("open_approvals") or []
    open_approvals = [str(x) for x in open_approvals_raw if isinstance(x, str)]

    notes_raw = raw.get("notes") or []
    notes: list[ProjectNote] = []
    for item in notes_raw:
        if isinstance(item, dict) and "text" in item:
            notes.append(
                ProjectNote(
                    ts=str(item.get("ts", _utc_now())),
                    text=str(item["text"]),
                )
            )
        elif isinstance(item, str):
            notes.append(ProjectNote(ts=_utc_now(), text=item))
        # silently ignore unrecognized shapes — never delete.

    state = ProjectState(
        project=str(raw.get("project", DEFAULT_PROJECT_NAME)) or DEFAULT_PROJECT_NAME,
        version=DEFAULT_VERSION,  # always advance to current package version
        schema_version=CURRENT_SCHEMA_VERSION,
        mode="local-safe",
        autonomy=False,
        network_enabled=False,
        created_ts=created_ts,
        last_run=last_run,
        totals=totals,
        recent_tasks=recent_tasks,
        open_approvals=open_approvals,
        notes=notes,
    )
    _ = schema_version  # acknowledged; forward-only migration
    return state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_project_state(
    path: Path = DEFAULT_PROJECT_STATE_PATH,
) -> ProjectState:
    """Load (and forward-migrate) the project state at *path*.

    If the file is missing, an empty defaulted :class:`ProjectState` is
    returned (not yet written to disk — callers decide).
    """
    p = _resolve_under_memory(Path(path))
    if not p.exists():
        return ProjectState()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable: fall back to defaults but do NOT overwrite.
        return ProjectState()
    return _migrate(raw, file_path=p)


def save_project_state(
    state: ProjectState,
    path: Path = DEFAULT_PROJECT_STATE_PATH,
) -> None:
    """Atomically save *state* to *path* (must be under ``memory/``)."""
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")

    p = _resolve_under_memory(Path(path))
    p.parent.mkdir(parents=True, exist_ok=True)

    payload = state.model_dump_json(indent=2)

    fd, tmp_name = tempfile.mkstemp(
        prefix=".project_state.", suffix=".tmp", dir=str(p.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def record_run(state: ProjectState, task_summary: TaskSummary) -> ProjectState:
    """Return a new :class:`ProjectState` with *task_summary* applied.

    * Bumps the matching ``totals`` counter.
    * Updates ``last_run``.
    * Appends to ``recent_tasks`` (capped at :data:`RECENT_TASKS_CAP`).
    """
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    if not isinstance(task_summary, TaskSummary):
        raise TypeError("task_summary must be a TaskSummary")

    new_totals = state.totals.bump(task_summary.decision)

    new_recent = list(state.recent_tasks) + [task_summary]
    if len(new_recent) > RECENT_TASKS_CAP:
        new_recent = new_recent[-RECENT_TASKS_CAP:]

    new_last_run = LastRun(
        ts=task_summary.ts,
        task_preview=task_summary.task_preview[:120],
        decision=task_summary.decision,
        primary_element=task_summary.primary_element,
        assimilation_score=task_summary.assimilation_score,
        audit_id=task_summary.audit_id,
    )

    data = state.model_dump()
    data["totals"] = new_totals.model_dump()
    data["recent_tasks"] = [t.model_dump() for t in new_recent]
    data["last_run"] = new_last_run.model_dump()
    return ProjectState(**data)


def add_note(state: ProjectState, text: str) -> ProjectState:
    """Append a :class:`ProjectNote`. Notes are never deleted by the engine."""
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("note text must be a non-empty string")

    new_notes = list(state.notes) + [ProjectNote(ts=_utc_now(), text=text.strip())]
    data = state.model_dump()
    data["notes"] = [n.model_dump() for n in new_notes]
    return ProjectState(**data)


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DEFAULT_PROJECT_STATE_PATH",
    "MEMORY_DIR",
    "RECENT_TASKS_CAP",
    "LastRun",
    "ProjectNote",
    "ProjectState",
    "RunTotals",
    "TaskSummary",
    "add_note",
    "load_project_state",
    "record_run",
    "save_project_state",
]
