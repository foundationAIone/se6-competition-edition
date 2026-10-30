"""Bounded, non-secret local timings for the existing dashboard read path.

No request arguments, payloads, exceptions, or session material are captured.
Nested spans overlap; use the full-audit span sum, not the sum of all spans.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

_NAMES = frozenset({
    "digital_service_lock_wait", "digital_owner_and_source", "digital_prior_readback",
    "digital_final_owner", "digital_enqueue", "digital_result_readback",
    "owner_base_validation", "runtime_controller_lookup", "runtime_lock_wait",
    "entity_state_load", "entity_full_audit", "entity_delta_audit", "cognition_binding",
    "three_loop_projection", "historical_loop_projection", "integrity_continuity_projection",
    "entity_projection", "embodiment_projection", "serialization",
    "response_write", "audit_subject_digest",
    "runtime_ledger_projection", "runtime_schema_projection",
    "three_loop_lock_wait", "three_loop_snapshot_validation",
    "three_loop_shared_projection", "presence_projection",
    "awareness_projection", "becoming_projection",
    "resource_projection",
    "approval_audit_projection",
    "owner_record_projection",
    "owner_session_projection",
    "owner_authority_projection",
    "avatar_availability_projection",
    "presentation_envelope_issue",
})
_CURRENT: ContextVar[DashboardReadTiming | None] = ContextVar("se6_dashboard_timing", default=None)
_LOGGER = logging.getLogger(__name__)
_LOGGER_LOCK = Lock()


def _emit(label: str, report: dict[str, object]) -> None:
    # The launcher does not configure INFO logging. Enable only this bounded,
    # sanitized channel on its existing stderr; no root logging or new file.
    with _LOGGER_LOCK:
        if not _LOGGER.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            _LOGGER.addHandler(handler)
        _LOGGER.setLevel(logging.INFO)
        _LOGGER.propagate = False
    rendered = json.dumps(report, separators=(",", ":"))
    _LOGGER.info("%s %s", label, rendered)

    # Optional local diagnostic sink. The report is already bounded and
    # sanitized by DashboardReadTiming: no request arguments, payloads,
    # credentials, session material, or exception text are included.
    target = os.environ.get("SE6_DASHBOARD_TRACE_FILE")

    # SE6_LEVEL5_FIXED_TRACE_FALLBACK_R1
    # Diagnostic-only, fixed local destination.
    # The canonical launcher intentionally strips arbitrary environment
    # variables. Do not broaden that security boundary merely for tracing.
    if not target and (
        os.getenv("SE6_EMBODIMENT_DASHBOARD") == "local"
        and os.getenv("SE6_PRODUCTION_ENROLLMENT") == "local_interactive"
        and os.getenv("SE6_PRODUCTION_EMBODIMENT") == "local_persistent"
        and os.getenv("SE6_AVATAR_PROJECTION") == "state_reactive"
        and os.getenv("SE6_BACKEND_STATE_AUTHORITY") == "strict"
        and os.getenv("SE6_LEVEL5_CEREMONY_V2_ENABLED") == "1"
    ):
        repository_root = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )
        target = os.path.join(
            repository_root,
            ".runtime",
            "local_backups",
            "se6-dashboard-live-trace.jsonl",
        )

    if target:
        try:
            os.makedirs(
                os.path.dirname(target),
                exist_ok=True,
            )
            with _LOGGER_LOCK:
                mode = "a"
                try:
                    if os.path.getsize(target) >= 2_000_000:
                        mode = "w"
                except OSError:
                    pass
                with open(target, mode, encoding="utf-8", newline="\n") as handle:
                    handle.write(label + " " + rendered + "\n")
        except OSError:
            # Diagnostics must never affect the dashboard read contract.
            pass


@dataclass
class DashboardReadTiming:
    correlation_id: str = field(default_factory=lambda: "dashboard_read_" + uuid4().hex)
    started_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started: float = field(default_factory=time.perf_counter)
    spans: list[dict[str, object]] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    elapsed_ms: float | None = None
    polling: bool = False
    emit: bool = False
    _lock: Lock = field(default_factory=Lock, repr=False)

    def report(self) -> dict[str, object]:
        with self._lock:
            return {"schema_version": "se6-dashboard-read-timing-v1",
                "correlation_id": self.correlation_id, "started_at_utc": self.started_at_utc,
                "elapsed_ms": self.elapsed_ms, "spans": list(self.spans),
                "counters": dict(self.counters)}


@contextmanager
def dashboard_read_timing(*, emit: bool = False) -> Iterator[DashboardReadTiming]:
    existing = _CURRENT.get()
    if existing is not None:
        yield existing
        return
    trace = DashboardReadTiming(emit=emit)
    token = _CURRENT.set(trace)
    try:
        yield trace
    finally:
        trace.elapsed_ms = round((time.perf_counter() - trace.started) * 1000, 3)
        _CURRENT.reset(token)
        if emit:
            _emit("SE6_DASHBOARD_READ_TIMING", trace.report())


@contextmanager
def read_span(name: str) -> Iterator[dict[str, object]]:
    if name not in _NAMES:
        raise ValueError("unknown dashboard timing span")
    trace = _CURRENT.get()
    metadata: dict[str, object] = {}
    started = time.perf_counter()
    ok = False
    try:
        yield metadata
        ok = True
    finally:
        if trace is not None:
            item: dict[str, object] = {"name": name, "start_ms": round((started - trace.started) * 1000, 3),
                "duration_ms": round((time.perf_counter() - started) * 1000, 3), "completed": ok}
            # Only a digest and nonnegative counts: never free-form metadata.
            digest = metadata.get("subject_sha256")
            if isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
                item["subject_sha256"] = digest
            for key in ("state_count", "head_version"):
                value = metadata.get(key)
                if type(value) is int and value >= 0:
                    item[key] = value
            with trace._lock:
                if len(trace.spans) < 64:
                    trace.spans.append(item)


def read_count(name: str) -> None:
    if name not in {"full_audits", "incremental_audits", "verified_reuses", "invalidations", "integrity_pending",
                    "three_loop_snapshot_reuses", "three_loop_shared_builds"}:
        raise ValueError("unknown dashboard timing counter")
    trace = _CURRENT.get()
    if trace is not None:
        with trace._lock:
            trace.counters[name] = trace.counters.get(name, 0) + 1


def emit_audit_completion(*, verified: bool) -> None:
    """Complete the original request's trace after its pending reply was sent."""
    trace = _CURRENT.get()
    if trace is not None and trace.emit:
        report = trace.report()
        report["background_verification_complete"] = True
        report["background_verified"] = verified
        report["completed_at_utc"] = datetime.now(UTC).isoformat()
        _emit("SE6_DASHBOARD_AUDIT_COMPLETION", report)


def timing_active() -> bool:
    return _CURRENT.get() is not None


@contextmanager
def polling_read() -> Iterator[None]:
    trace = _CURRENT.get()
    previous = trace.polling if trace is not None else False
    if trace is not None:
        trace.polling = True
    try:
        yield
    finally:
        if trace is not None:
            trace.polling = previous


def is_polling_read() -> bool:
    trace = _CURRENT.get()
    return trace is not None and trace.polling
