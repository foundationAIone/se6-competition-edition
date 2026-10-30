"""Failure-isolated, off-by-default live canonical shadow observation."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .canonical_contracts import CANONICALIZATION_VERSION, SCHEMA_VERSION
from .canonical_shadow import (
    ConstructionStatus,
    LegacyShadowRequest,
    ShadowConstructionResult,
    ShadowSuppliedContext,
    build_shadow_transaction,
)
from .decision_comparison import (
    DecisionComparison,
    compare_decisions,
)
from .shadow_telemetry import (
    ShadowTelemetryEvent,
    TelemetryError,
    serialize_telemetry_event,
    write_temp_telemetry,
)

RUNTIME_VERSION = "se6-compatibility-shadow-hook-v1"
DEFAULT_LATENCY_BUDGET_MS = 100


class ShadowMode(str, Enum):
    OFF = "off"
    OBSERVE = "observe"


class ShadowSinkMode(str, Enum):
    NONE = "none"
    TEMP_JSONL = "temp_jsonl"


class InstrumentationStatus(str, Enum):
    DISABLED = "disabled"
    OBSERVED = "observed"
    OBSERVED_OVER_BUDGET = "observed_over_budget"
    FAILED_ISOLATED = "failed_isolated"
    REENTRY_SKIPPED = "reentry_skipped"


class ShadowErrorCode(str, Enum):
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    SHADOW_CONSTRUCTION_FAILED = "SHADOW_CONSTRUCTION_FAILED"
    SNAPSHOT_FAILED = "SNAPSHOT_FAILED"
    SNAPSHOT_INTEGRITY_FAILED = "SNAPSHOT_INTEGRITY_FAILED"
    COMPARISON_FAILED = "COMPARISON_FAILED"
    REDACTION_FAILED = "REDACTION_FAILED"
    TELEMETRY_SERIALIZATION_FAILED = "TELEMETRY_SERIALIZATION_FAILED"
    TELEMETRY_WRITE_FAILED = "TELEMETRY_WRITE_FAILED"
    LATENCY_BUDGET_EXCEEDED = "LATENCY_BUDGET_EXCEEDED"


class ShadowInstrumentationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    shadow_mode: ShadowMode = ShadowMode.OFF
    sink_mode: ShadowSinkMode = ShadowSinkMode.NONE
    latency_budget_ms: StrictInt = Field(default=DEFAULT_LATENCY_BUDGET_MS, gt=0)
    configuration_valid: bool = True


class ShadowInstrumentationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: InstrumentationStatus
    error_code: ShadowErrorCode | None = None
    legacy_result_unchanged: bool = True
    observation_performed: bool = False
    telemetry_written: bool = False
    latency_budget_exceeded: bool = False
    observation_duration_ms: float = Field(default=0.0, ge=0.0)
    event: ShadowTelemetryEvent | None = None


_guard = threading.local()
_SAFE_REASON_CODES = frozenset({
    "decisions_exactly_match", "decision_vocabulary_normalized",
    "canonical_shadow_is_more_restrictive", "legacy_is_more_restrictive",
    "decision_semantics_incomparable", "canonical_construction_failed",
    "legacy_decision_unknown", "consequential_information_missing",
    "policy_version_mismatch", "bounded_non_effectful_proposal",
    "proposal_mode_no_external_execution", "consequential_authority_not_established",
    "consequential_destination_unknown", "exact_approval_not_supplied",
    "untrusted_content_is_not_authority", "explicit_authority_and_approval_supplied",
})


def load_shadow_config(environ: Mapping[str, str] | None = None) -> ShadowInstrumentationConfig:
    values = os.environ if environ is None else environ
    raw_mode = values.get("SE6_CANONICAL_SHADOW")
    raw_sink = values.get("SE6_CANONICAL_SHADOW_SINK")
    raw_budget = values.get("SE6_CANONICAL_SHADOW_MAX_MS")
    valid = True
    if raw_mode in (None, "off"):
        mode = ShadowMode.OFF
    elif raw_mode == "observe":
        mode = ShadowMode.OBSERVE
    else:
        mode = ShadowMode.OFF
        valid = False
    if raw_sink in (None, "none"):
        sink = ShadowSinkMode.NONE
    elif raw_sink == "temp_jsonl":
        sink = ShadowSinkMode.TEMP_JSONL
    else:
        sink = ShadowSinkMode.NONE
        valid = False
    if raw_budget is None:
        budget = DEFAULT_LATENCY_BUDGET_MS
    elif raw_budget.isascii() and raw_budget.isdigit() and int(raw_budget) > 0:
        budget = int(raw_budget)
    else:
        budget = DEFAULT_LATENCY_BUDGET_MS
        valid = False
    return ShadowInstrumentationConfig(
        shadow_mode=mode,
        sink_mode=sink,
        latency_budget_ms=budget,
        configuration_valid=valid,
    )


def _safe_reasons(*groups: tuple[str, ...]) -> tuple[str, ...]:
    result = []
    for group in groups:
        for reason in group:
            safe = reason if reason in _SAFE_REASON_CODES else "UNRECOGNIZED_REASON_CODE"
            if safe not in result:
                result.append(safe)
    return tuple(result)


def _event_id(timestamp: str, duration_ns: int, material_hash: str | None) -> str:
    seed = f"shadow-event-v1:{timestamp}:{duration_ns}:{material_hash or 'none'}"
    return f"evt_{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _default_supplied_context() -> ShadowSuppliedContext:
    # Deliberately empty: the compatibility runtime has no authenticated actor,
    # canonical authority, or policy context to supply without invention.
    return ShadowSuppliedContext()


def _construct_shadow(
    request_context: str,
    legacy_result: Any,
    supplied_context: ShadowSuppliedContext,
) -> ShadowConstructionResult:
    request = LegacyShadowRequest(intention=request_context)
    return build_shadow_transaction(request, legacy_result, supplied_context)


def _build_event(
    *,
    config: ShadowInstrumentationConfig,
    construction: ShadowConstructionResult,
    comparison: DecisionComparison,
    supplied_context: ShadowSuppliedContext,
    duration_ns: int,
    latency_exceeded: bool,
    snapshot_integrity_valid: bool,
    status: InstrumentationStatus,
    error_code: ShadowErrorCode | None,
) -> ShadowTelemetryEvent:
    transaction = construction.canonical_transaction
    snapshot = construction.canonical_snapshot
    timestamp = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    duration_ms = duration_ns / 1_000_000.0
    eligible = (
        construction.eligible_for_future_promotion
        and comparison.eligible_for_future_promotion
        and snapshot_integrity_valid
        and not latency_exceeded
        and error_code is None
    )
    reasons = _safe_reasons(
        comparison.reason_codes,
        construction.shadow_decision.reason_codes if construction.shadow_decision else (),
    )
    return ShadowTelemetryEvent(
        event_id=_event_id(timestamp, duration_ns, construction.material_transaction_hash),
        timestamp_utc=timestamp,
        runtime_version=RUNTIME_VERSION,
        canonical_contract_version=SCHEMA_VERSION,
        canonicalization_version=CANONICALIZATION_VERSION,
        shadow_mode=config.shadow_mode.value,
        sink_mode=config.sink_mode.value,
        legacy_decision=comparison.legacy_decision,
        canonical_shadow_decision=comparison.canonical_shadow_decision.value if comparison.canonical_shadow_decision else None,
        comparison_class=comparison.comparison_class.value,
        severity=comparison.severity.value,
        eligible_for_future_promotion=eligible,
        reason_codes=reasons,
        missing_field_count=len(comparison.missing_information),
        unknown_field_count=len(construction.unknown_fields),
        synthetic_field_count=len(construction.synthetic_fields),
        lossy_field_count=len(construction.lossy_fields),
        rejected_field_count=len(construction.rejected_fields),
        snapshot_id=snapshot.snapshot_id if snapshot else None,
        transaction_id=snapshot.transaction_id if snapshot else None,
        canonical_arguments_hash=construction.canonical_arguments_hash,
        material_transaction_hash=construction.material_transaction_hash,
        policy_version_present=bool(transaction and transaction.policy_version),
        actor_present=bool(transaction and transaction.actor_identity),
        owner_present=bool(transaction and transaction.owner_identity),
        authority_present=supplied_context.authority_established is not None,
        destination_present=bool(transaction and transaction.destination),
        external_effect=transaction.external_effect_classification.value if transaction else None,
        irreversible_effect=transaction.irreversible_effect_classification.value if transaction else None,
        snapshot_integrity_valid=snapshot_integrity_valid,
        observation_duration_ms=duration_ms,
        latency_budget_ms=config.latency_budget_ms,
        latency_budget_exceeded=latency_exceeded,
        instrumentation_status=status.value,
        error_code=error_code.value if error_code else None,
    )


def observe_legacy_result_in_shadow(
    *,
    request_context: str,
    legacy_result: Any,
    supplied_context: ShadowSuppliedContext | None = None,
    config: ShadowInstrumentationConfig | None = None,
) -> ShadowInstrumentationOutcome:
    """Observe once; every failure is isolated and the result is never mutated."""
    resolved_config = config or load_shadow_config()
    if resolved_config.shadow_mode is ShadowMode.OFF:
        return ShadowInstrumentationOutcome(
            status=InstrumentationStatus.DISABLED,
            error_code=None if resolved_config.configuration_valid else ShadowErrorCode.INVALID_CONFIGURATION,
        )
    if getattr(_guard, "active", False):
        return ShadowInstrumentationOutcome(status=InstrumentationStatus.REENTRY_SKIPPED)

    _guard.active = True
    start_ns = time.monotonic_ns()
    context = supplied_context or _default_supplied_context()
    construction: ShadowConstructionResult | None = None
    comparison: DecisionComparison | None = None
    snapshot_valid = False
    error_code: ShadowErrorCode | None = (
        None if resolved_config.configuration_valid else ShadowErrorCode.INVALID_CONFIGURATION
    )
    event: ShadowTelemetryEvent | None = None
    telemetry_written = False
    try:
        try:
            construction = _construct_shadow(request_context, legacy_result, context)
        except Exception:
            logging.getLogger(__name__).debug(
                "Shadow construction failed in isolation", exc_info=True
            )
            error_code = ShadowErrorCode.SHADOW_CONSTRUCTION_FAILED
            return ShadowInstrumentationOutcome(
                status=InstrumentationStatus.FAILED_ISOLATED,
                error_code=error_code,
                observation_performed=True,
                observation_duration_ms=(time.monotonic_ns() - start_ns) / 1_000_000.0,
            )

        if construction.canonical_snapshot is not None:
            try:
                snapshot_valid = construction.canonical_snapshot.verify_integrity().valid
            except Exception:
                logging.getLogger(__name__).debug(
                    "Shadow snapshot verification failed in isolation",
                    exc_info=True,
                )
                error_code = ShadowErrorCode.SNAPSHOT_FAILED
                snapshot_valid = False
            if not snapshot_valid and error_code is None:
                error_code = ShadowErrorCode.SNAPSHOT_INTEGRITY_FAILED
        else:
            snapshot_valid = False

        try:
            comparison = compare_decisions(construction)
        except Exception:
            logging.getLogger(__name__).debug(
                "Shadow decision comparison failed in isolation", exc_info=True
            )
            error_code = ShadowErrorCode.COMPARISON_FAILED
            return ShadowInstrumentationOutcome(
                status=InstrumentationStatus.FAILED_ISOLATED,
                error_code=error_code,
                observation_performed=True,
                observation_duration_ms=(time.monotonic_ns() - start_ns) / 1_000_000.0,
            )

        duration_ns = time.monotonic_ns() - start_ns
        over_budget = duration_ns > resolved_config.latency_budget_ms * 1_000_000
        if over_budget:
            error_code = ShadowErrorCode.LATENCY_BUDGET_EXCEEDED
        elif construction.construction_status is ConstructionStatus.FAILED:
            error_code = ShadowErrorCode.SHADOW_CONSTRUCTION_FAILED
        status = (
            InstrumentationStatus.OBSERVED_OVER_BUDGET
            if over_budget
            else InstrumentationStatus.FAILED_ISOLATED
            if error_code is not None
            else InstrumentationStatus.OBSERVED
        )
        try:
            event = _build_event(
                config=resolved_config,
                construction=construction,
                comparison=comparison,
                supplied_context=context,
                duration_ns=duration_ns,
                latency_exceeded=over_budget,
                snapshot_integrity_valid=snapshot_valid,
                status=status,
                error_code=error_code,
            )
        except Exception:
            logging.getLogger(__name__).debug(
                "Shadow telemetry redaction failed in isolation", exc_info=True
            )
            return ShadowInstrumentationOutcome(
                status=InstrumentationStatus.FAILED_ISOLATED,
                error_code=ShadowErrorCode.REDACTION_FAILED,
                observation_performed=True,
                latency_budget_exceeded=over_budget,
                observation_duration_ms=duration_ns / 1_000_000.0,
            )

        try:
            if resolved_config.sink_mode is ShadowSinkMode.TEMP_JSONL:
                write_temp_telemetry(event)
                telemetry_written = True
            else:
                serialize_telemetry_event(event)
        except TelemetryError as exc:
            fixed = (
                ShadowErrorCode.TELEMETRY_WRITE_FAILED
                if exc.error_code in {"TELEMETRY_WRITE_FAILED", "TELEMETRY_SINK_SYMLINK_REJECTED", "TELEMETRY_SINK_INSIDE_REPOSITORY", "TELEMETRY_PATH_VALIDATION_FAILED"}
                else ShadowErrorCode.TELEMETRY_SERIALIZATION_FAILED
            )
            return ShadowInstrumentationOutcome(
                status=InstrumentationStatus.FAILED_ISOLATED,
                error_code=fixed,
                observation_performed=True,
                latency_budget_exceeded=over_budget,
                observation_duration_ms=duration_ns / 1_000_000.0,
                event=event,
            )
        except Exception:
            logging.getLogger(__name__).debug(
                "Shadow telemetry persistence failed in isolation", exc_info=True
            )
            return ShadowInstrumentationOutcome(
                status=InstrumentationStatus.FAILED_ISOLATED,
                error_code=(
                    ShadowErrorCode.TELEMETRY_WRITE_FAILED
                    if resolved_config.sink_mode is ShadowSinkMode.TEMP_JSONL
                    else ShadowErrorCode.TELEMETRY_SERIALIZATION_FAILED
                ),
                observation_performed=True,
                latency_budget_exceeded=over_budget,
                observation_duration_ms=duration_ns / 1_000_000.0,
                event=event,
            )
        return ShadowInstrumentationOutcome(
            status=status,
            error_code=error_code,
            observation_performed=True,
            telemetry_written=telemetry_written,
            latency_budget_exceeded=over_budget,
            observation_duration_ms=duration_ns / 1_000_000.0,
            event=event,
        )
    finally:
        _guard.active = False


__all__ = [
    "DEFAULT_LATENCY_BUDGET_MS",
    "RUNTIME_VERSION",
    "InstrumentationStatus",
    "ShadowErrorCode",
    "ShadowInstrumentationConfig",
    "ShadowInstrumentationOutcome",
    "ShadowMode",
    "ShadowSinkMode",
    "load_shadow_config",
    "observe_legacy_result_in_shadow",
]
