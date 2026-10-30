"""Deterministic, effect-free SHADOW continuation evaluator.

The evaluator returns a proposal about what could happen next.  It performs no
I/O, model call, network operation, notification, mutation, assimilation, or
authority action.  Even states named NOTIFY, ASSIMILATE, and BECOME are only
bounded recommendations in the returned immutable record.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from se666_core.canonical_contracts import canonical_sha256

CONTINUATION_SCHEMA_VERSION = "se6-continuation-shadow-v-next-1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def _content_id(prefix: str, material: object) -> str:
    return f"{prefix}_{canonical_sha256(material)}"


class ContinuationState(str, Enum):
    REST = "REST"
    OBSERVE = "OBSERVE"
    MAP = "MAP"
    REFLECT = "REFLECT"
    PROPOSE = "PROPOSE"
    NOTIFY = "NOTIFY"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    REQUEST_AUTHORITY = "REQUEST_AUTHORITY"
    VERIFY = "VERIFY"
    ASSIMILATE = "ASSIMILATE"
    BECOME = "BECOME"
    PAUSE = "PAUSE"
    STOP = "STOP"


class ContinuationReason(str, Enum):
    STOP_REQUESTED = "STOP_REQUESTED"
    EMERGENCY_STOP_OBSERVED = "EMERGENCY_STOP_OBSERVED"
    INTERRUPTED = "INTERRUPTED"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    SILENCE_REQUESTED = "SILENCE_REQUESTED"
    STEP_BUDGET_EXHAUSTED = "STEP_BUDGET_EXHAUSTED"
    PROPOSAL_BUDGET_EXHAUSTED = "PROPOSAL_BUDGET_EXHAUSTED"
    NOTIFICATION_BUDGET_EXHAUSTED = "NOTIFICATION_BUDGET_EXHAUSTED"
    INFORMATION_MISSING = "INFORMATION_MISSING"
    AUTHORITY_REQUIRED = "AUTHORITY_REQUIRED"
    VERIFICATION_DUE = "VERIFICATION_DUE"
    VERIFIED_ASSIMILATION_AVAILABLE = "VERIFIED_ASSIMILATION_AVAILABLE"
    BECOMING_DUE = "BECOMING_DUE"
    NOTIFICATION_DUE = "NOTIFICATION_DUE"
    PROPOSAL_DUE = "PROPOSAL_DUE"
    REFLECTION_DUE = "REFLECTION_DUE"
    MAPPING_DUE = "MAPPING_DUE"
    OBSERVATION_DUE = "OBSERVATION_DUE"
    QUIESCENT = "QUIESCENT"


class ContinuationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    maximum_steps: StrictInt = Field(ge=0)
    used_steps: StrictInt = Field(default=0, ge=0)
    maximum_proposals: StrictInt = Field(default=0, ge=0)
    used_proposals: StrictInt = Field(default=0, ge=0)
    maximum_notifications: StrictInt = Field(default=0, ge=0)
    used_notifications: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_usage(self) -> ContinuationBudget:
        if self.used_steps > self.maximum_steps:
            raise ValueError("used_steps exceeds maximum_steps")
        if self.used_proposals > self.maximum_proposals:
            raise ValueError("used_proposals exceeds maximum_proposals")
        if self.used_notifications > self.maximum_notifications:
            raise ValueError("used_notifications exceeds maximum_notifications")
        return self


class ContinuationSignals(BaseModel):
    """Already-available, caller-supplied signals; never gathered here."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    stop_requested: StrictBool = False
    emergency_stop_observed: StrictBool = False
    interrupt_requested: StrictBool = False
    pause_requested: StrictBool = False
    silence_requested: StrictBool = False
    information_missing: StrictBool = False
    authority_required: StrictBool = False
    verification_requested: StrictBool = False
    assimilation_requested: StrictBool = False
    becoming_requested: StrictBool = False
    notification_requested: StrictBool = False
    proposal_requested: StrictBool = False
    reflection_requested: StrictBool = False
    mapping_requested: StrictBool = False
    observation_requested: StrictBool = False
    verified_consequence_reference: StrictStr | None = None
    verified_assimilation_reference: StrictStr | None = None

    @field_validator(
        "verified_consequence_reference", "verified_assimilation_reference"
    )
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        if value is not None and not _REF_RE.fullmatch(value):
            raise ValueError("verification references must be safe references")
        return value

    @model_validator(mode="after")
    def validate_assimilation_signal(self) -> ContinuationSignals:
        references = (
            self.verified_consequence_reference is not None,
            self.verified_assimilation_reference is not None,
        )
        if any(references) and not all(references):
            raise ValueError(
                "verified consequence and assimilation references are a pair"
            )
        if self.assimilation_requested and not all(references):
            raise ValueError(
                "assimilation_requested requires independently verified references"
            )
        return self


class ContinuationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-continuation-shadow-v-next-1"] = (
        CONTINUATION_SCHEMA_VERSION
    )
    decision_id: StrictStr
    source_state_hash: StrictStr
    frame_hash: StrictStr
    state_before: ContinuationState
    state_after: ContinuationState
    reason: ContinuationReason
    signals: ContinuationSignals
    budget_before: ContinuationBudget
    budget_after: ContinuationBudget
    proposal_only: Literal[True] = True
    emitted_output: Literal[False] = False
    authority_granted: Literal[False] = False
    io_performed: Literal[False] = False
    network_performed: Literal[False] = False
    model_called: Literal[False] = False
    state_mutated: Literal[False] = False

    @field_validator("source_state_hash", "frame_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("hash must be a lowercase SHA-256 digest")
        return value

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"decision_id"})

    @model_validator(mode="after")
    def validate_contract(self) -> ContinuationDecision:
        if self.state_after == ContinuationState.ASSIMILATE and (
            self.signals.verified_consequence_reference is None
            or self.signals.verified_assimilation_reference is None
        ):
            raise ValueError("ASSIMILATE requires independently verified references")
        if self.decision_id != _content_id("continuation_decision", self.material_fields()):
            raise ValueError("decision_id must match canonical content")
        return self


def _select_state(
    signals: ContinuationSignals, budget: ContinuationBudget
) -> tuple[ContinuationState, ContinuationReason]:
    """Select one state by a fixed safety-first priority order."""

    if signals.emergency_stop_observed:
        return ContinuationState.STOP, ContinuationReason.EMERGENCY_STOP_OBSERVED
    if signals.stop_requested:
        return ContinuationState.STOP, ContinuationReason.STOP_REQUESTED
    if signals.interrupt_requested:
        return ContinuationState.PAUSE, ContinuationReason.INTERRUPTED
    if signals.pause_requested:
        return ContinuationState.PAUSE, ContinuationReason.PAUSE_REQUESTED
    if signals.silence_requested:
        return ContinuationState.REST, ContinuationReason.SILENCE_REQUESTED
    if budget.used_steps >= budget.maximum_steps:
        return ContinuationState.REST, ContinuationReason.STEP_BUDGET_EXHAUSTED
    if signals.information_missing:
        return (
            ContinuationState.REQUEST_INFORMATION,
            ContinuationReason.INFORMATION_MISSING,
        )
    if signals.authority_required:
        return ContinuationState.REQUEST_AUTHORITY, ContinuationReason.AUTHORITY_REQUIRED
    if signals.verification_requested:
        return ContinuationState.VERIFY, ContinuationReason.VERIFICATION_DUE
    if signals.assimilation_requested:
        return (
            ContinuationState.ASSIMILATE,
            ContinuationReason.VERIFIED_ASSIMILATION_AVAILABLE,
        )
    if signals.becoming_requested:
        return ContinuationState.BECOME, ContinuationReason.BECOMING_DUE
    if signals.notification_requested:
        if budget.used_notifications >= budget.maximum_notifications:
            return (
                ContinuationState.REST,
                ContinuationReason.NOTIFICATION_BUDGET_EXHAUSTED,
            )
        return ContinuationState.NOTIFY, ContinuationReason.NOTIFICATION_DUE
    if signals.proposal_requested:
        if budget.used_proposals >= budget.maximum_proposals:
            return ContinuationState.REST, ContinuationReason.PROPOSAL_BUDGET_EXHAUSTED
        return ContinuationState.PROPOSE, ContinuationReason.PROPOSAL_DUE
    if signals.reflection_requested:
        return ContinuationState.REFLECT, ContinuationReason.REFLECTION_DUE
    if signals.mapping_requested:
        return ContinuationState.MAP, ContinuationReason.MAPPING_DUE
    if signals.observation_requested:
        return ContinuationState.OBSERVE, ContinuationReason.OBSERVATION_DUE
    return ContinuationState.REST, ContinuationReason.QUIESCENT


def _consume_budget(
    budget: ContinuationBudget, state: ContinuationState
) -> ContinuationBudget:
    if state in {ContinuationState.REST, ContinuationState.PAUSE, ContinuationState.STOP}:
        return budget
    return ContinuationBudget(
        maximum_steps=budget.maximum_steps,
        used_steps=budget.used_steps + 1,
        maximum_proposals=budget.maximum_proposals,
        used_proposals=budget.used_proposals
        + (1 if state == ContinuationState.PROPOSE else 0),
        maximum_notifications=budget.maximum_notifications,
        used_notifications=budget.used_notifications
        + (1 if state == ContinuationState.NOTIFY else 0),
    )


def evaluate_continuation(
    *,
    source_state_hash: str,
    frame_hash: str,
    state_before: ContinuationState,
    signals: ContinuationSignals,
    budget: ContinuationBudget,
) -> ContinuationDecision:
    """Return one deterministic, immutable, proposal-only next-state record."""

    state_after, reason = _select_state(signals, budget)
    budget_after = _consume_budget(budget, state_after)
    material = {
        "schema_version": CONTINUATION_SCHEMA_VERSION,
        "source_state_hash": source_state_hash,
        "frame_hash": frame_hash,
        "state_before": state_before,
        "state_after": state_after,
        "reason": reason,
        "signals": signals,
        "budget_before": budget,
        "budget_after": budget_after,
        "proposal_only": True,
        "emitted_output": False,
        "authority_granted": False,
        "io_performed": False,
        "network_performed": False,
        "model_called": False,
        "state_mutated": False,
    }
    draft = ContinuationDecision.model_construct(
        decision_id="continuation_decision_draft", **material
    )
    normalized = draft.material_fields()
    return ContinuationDecision.model_validate(
        {
            "decision_id": _content_id("continuation_decision", normalized),
            **normalized,
        }
    )


__all__ = [
    "CONTINUATION_SCHEMA_VERSION",
    "ContinuationBudget",
    "ContinuationDecision",
    "ContinuationReason",
    "ContinuationSignals",
    "ContinuationState",
    "evaluate_continuation",
]
