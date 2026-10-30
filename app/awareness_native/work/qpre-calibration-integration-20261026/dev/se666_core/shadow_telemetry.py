"""Strictly whitelisted temporary telemetry for canonical shadow observation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

TELEMETRY_SCHEMA_VERSION = "1.0"
TELEMETRY_FILENAME = "shadow_events.jsonl"
TELEMETRY_FIELD_WHITELIST = frozenset({
    "telemetry_schema_version", "event_id", "timestamp_utc", "runtime_version",
    "canonical_contract_version", "canonicalization_version", "shadow_mode",
    "sink_mode", "legacy_decision", "canonical_shadow_decision",
    "comparison_class", "severity", "eligible_for_future_promotion",
    "reason_codes", "missing_field_count", "unknown_field_count",
    "synthetic_field_count", "lossy_field_count", "rejected_field_count",
    "snapshot_id", "transaction_id", "canonical_arguments_hash",
    "material_transaction_hash", "policy_version_present", "actor_present",
    "owner_present", "authority_present", "destination_present",
    "external_effect", "irreversible_effect", "snapshot_integrity_valid",
    "observation_duration_ms", "latency_budget_ms", "latency_budget_exceeded",
    "instrumentation_status", "error_code",
})

_KNOWN_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*\b", re.IGNORECASE),
)


class TelemetryError(RuntimeError):
    """Carries a fixed code only; raw exception text is never retained."""

    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


class ShadowTelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    telemetry_schema_version: StrictStr = TELEMETRY_SCHEMA_VERSION
    event_id: StrictStr = Field(pattern=r"^evt_[0-9a-f]{64}$")
    timestamp_utc: StrictStr
    runtime_version: StrictStr
    canonical_contract_version: StrictStr
    canonicalization_version: StrictStr
    shadow_mode: StrictStr
    sink_mode: StrictStr
    legacy_decision: StrictStr | None = None
    canonical_shadow_decision: StrictStr | None = None
    comparison_class: StrictStr | None = None
    severity: StrictStr | None = None
    eligible_for_future_promotion: bool
    reason_codes: tuple[StrictStr, ...] = ()
    missing_field_count: StrictInt = Field(ge=0)
    unknown_field_count: StrictInt = Field(ge=0)
    synthetic_field_count: StrictInt = Field(ge=0)
    lossy_field_count: StrictInt = Field(ge=0)
    rejected_field_count: StrictInt = Field(ge=0)
    snapshot_id: StrictStr | None = None
    transaction_id: StrictStr | None = None
    canonical_arguments_hash: StrictStr | None = None
    material_transaction_hash: StrictStr | None = None
    policy_version_present: bool
    actor_present: bool
    owner_present: bool
    authority_present: bool
    destination_present: bool
    external_effect: StrictStr | None = None
    irreversible_effect: StrictStr | None = None
    snapshot_integrity_valid: bool
    observation_duration_ms: StrictFloat = Field(ge=0.0)
    latency_budget_ms: StrictInt = Field(gt=0)
    latency_budget_exceeded: bool
    instrumentation_status: StrictStr
    error_code: StrictStr | None = None


def resolve_temp_telemetry_path() -> Path:
    """Return the one fixed sink path or raise a fixed-code error."""
    try:
        temp_root = Path(tempfile.gettempdir())
        candidate = temp_root / "se6triad" / "canonical_shadow" / TELEMETRY_FILENAME
        repo_root = Path(__file__).resolve().parents[1]
        for component in (temp_root, temp_root / "se6triad", temp_root / "se6triad" / "canonical_shadow", candidate):
            if component.exists() and component.is_symlink():
                raise TelemetryError("TELEMETRY_SINK_SYMLINK_REJECTED")
        resolved = candidate.resolve(strict=False)
        if resolved == repo_root or resolved.is_relative_to(repo_root):
            raise TelemetryError("TELEMETRY_SINK_INSIDE_REPOSITORY")
        return resolved
    except TelemetryError:
        raise
    except (OSError, TypeError, ValueError):
        raise TelemetryError("TELEMETRY_PATH_VALIDATION_FAILED") from None


def serialize_telemetry_event(event: ShadowTelemetryEvent) -> str:
    try:
        payload = event.model_dump(mode="json")
        if frozenset(payload) != TELEMETRY_FIELD_WHITELIST:
            raise TelemetryError("TELEMETRY_WHITELIST_VIOLATION")
        rendered = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        if any(pattern.search(rendered) for pattern in _KNOWN_SECRET_PATTERNS):
            raise TelemetryError("TELEMETRY_SECRET_PATTERN_REJECTED")
        return rendered
    except TelemetryError:
        raise
    except (TypeError, ValueError):
        raise TelemetryError("TELEMETRY_SERIALIZATION_FAILED") from None


def write_temp_telemetry(event: ShadowTelemetryEvent) -> Path:
    """Append one sanitized event to the fixed OS-temporary sink."""
    rendered = serialize_telemetry_event(event)
    destination = resolve_temp_telemetry_path()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Revalidate after directory creation to catch pre-existing links.
        destination = resolve_temp_telemetry_path()
        if destination.exists() and destination.is_symlink():
            raise TelemetryError("TELEMETRY_SINK_SYMLINK_REJECTED")
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        descriptor = os.open(destination, flags, 0o600)
        try:
            os.write(descriptor, (rendered + "\n").encode("utf-8"))
        finally:
            os.close(descriptor)
        return destination
    except TelemetryError:
        raise
    except (OSError, TypeError, ValueError):
        raise TelemetryError("TELEMETRY_WRITE_FAILED") from None


__all__ = [
    "TELEMETRY_FIELD_WHITELIST",
    "TELEMETRY_FILENAME",
    "TELEMETRY_SCHEMA_VERSION",
    "ShadowTelemetryEvent",
    "TelemetryError",
    "resolve_temp_telemetry_path",
    "serialize_telemetry_event",
    "write_temp_telemetry",
]
