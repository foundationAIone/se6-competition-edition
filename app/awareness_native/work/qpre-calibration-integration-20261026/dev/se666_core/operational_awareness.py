"""Pure contracts for a bounded operational-awareness snapshot.

The models in this module describe what the compatibility reasoning pipeline
represented during one cycle.  They do not grant authority, execute actions,
verify observations, persist memory, or claim subjective awareness.  Mirror
and perspective material is deliberately marked symbolic and advisory.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from .canonical_contracts import BoundaryDecision, canonical_sha256
from .epistemic_status import EpistemicStatus, EpistemicValue, UncertaintyRecord
from .merkabah_rotation import PERSPECTIVE_KEYS, MerkabahRotation
from .sphere_of_mirrors import MIRROR_KEYS, MirrorReflection

SCHEMA_VERSION = "se6-operational-awareness-v1"
_AWARENESS_ID_PATTERN = r"^awareness_[0-9a-f]{64}$"
_HASH_PATTERN = r"^[0-9a-f]{64}$"
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_ -]?key|password|private[_ -]?key|seed phrase)\s*[:=]", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\(?:Users|Documents|Desktop|AppData)\\", re.IGNORECASE),
)
_SENSITIVE_PLACEHOLDER = "[sensitive input withheld from awareness snapshot]"


def _awareness_text(value: str) -> str:
    """Return bounded non-secret text suitable for a descriptive snapshot.

    The compatibility result may retain caller text for its legacy fail-closed
    public scanner.  This hash-bound awareness view must not duplicate obvious
    credentials, private-key material, or private local paths.
    """

    if any(pattern.search(value) for pattern in _SENSITIVE_TEXT_PATTERNS):
        return _SENSITIVE_PLACEHOLDER
    return value


class AdvisorySource(str, Enum):
    MIRROR = "MIRROR"
    PERSPECTIVE = "PERSPECTIVE"


class RuntimeDecision(str, Enum):
    ALLOW = "allow"
    PAUSE = "pause"
    REPAIR = "repair"
    REFUSE = "refuse"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"


class ObservationStatus(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    REPORTED = "REPORTED"
    VERIFIED = "VERIFIED"


class AdvisoryConsideration(BaseModel):
    """A question to consider, never an authority or factual assertion."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source: AdvisorySource
    key: StrictStr = Field(min_length=1, max_length=64)
    prompt: StrictStr = Field(min_length=1, max_length=1_000)
    epistemic_status: EpistemicStatus = EpistemicStatus.SYMBOLIC
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("key", "prompt")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("advisory text must not be blank")
        return value

    @model_validator(mode="after")
    def advisory_cannot_grant_authority(self) -> AdvisoryConsideration:
        if self.epistemic_status is not EpistemicStatus.SYMBOLIC:
            raise ValueError("advisories must remain SYMBOLIC")
        if self.authority_effect != "NONE":
            raise ValueError("advisories cannot affect authority")
        return self


def _unknown_text() -> EpistemicValue[StrictStr]:
    return EpistemicValue[StrictStr](
        status=EpistemicStatus.UNKNOWN,
        value=None,
        confidence=0.0,
    )


def _unknown_string_tuple() -> EpistemicValue[tuple[StrictStr, ...]]:
    return EpistemicValue[tuple[StrictStr, ...]](
        status=EpistemicStatus.UNKNOWN,
        value=None,
        confidence=0.0,
    )


class OperationalSelfLocation(BaseModel):
    """Epistemically qualified location of the reasoning cycle itself."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    cognition_mode: Literal["neural", "offline_fallback"]
    current_state_present: StrictBool
    lifecycle: EpistemicValue[StrictStr] = Field(default_factory=_unknown_text)
    available_tools: EpistemicValue[tuple[StrictStr, ...]] = Field(
        default_factory=_unknown_string_tuple
    )
    established_permissions: EpistemicValue[tuple[StrictStr, ...]] = Field(
        default_factory=_unknown_string_tuple
    )
    unresolved_requests: tuple[StrictStr, ...] = Field(default=(), max_length=16)

    @field_validator("unresolved_requests")
    @classmethod
    def requests_are_bounded_and_unique(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 256 for item in value):
            raise ValueError("unresolved requests must be non-blank and at most 256 characters")
        if len(set(value)) != len(value):
            raise ValueError("unresolved requests must be unique")
        return value


class BoundaryAwareness(BaseModel):
    """Read-only representation of an already-computed boundary outcome."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source: Literal["MASTER_BOUNDARY"] = "MASTER_BOUNDARY"
    runtime_decision: RuntimeDecision
    effective_decision: BoundaryDecision
    authority_level: int = Field(default=0, ge=0, le=7)
    reasons: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    approval_required: StrictBool

    @field_validator("reasons")
    @classmethod
    def reasons_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not reason.strip() or len(reason) > 1_000 for reason in value):
            raise ValueError("boundary reasons must be non-blank and at most 1000 characters")
        return value

    @model_validator(mode="after")
    def effective_decision_cannot_weaken_boundary(self) -> BoundaryAwareness:
        permitted = {
            RuntimeDecision.REFUSE: {BoundaryDecision.REFUSE},
            RuntimeDecision.REPAIR: {
                BoundaryDecision.REPAIR,
                BoundaryDecision.REFUSE,
            },
            RuntimeDecision.PAUSE: {
                BoundaryDecision.PAUSE,
                BoundaryDecision.REFUSE,
            },
            RuntimeDecision.NEEDS_HUMAN_APPROVAL: {
                BoundaryDecision.PAUSE,
                BoundaryDecision.REFUSE,
            },
            RuntimeDecision.ALLOW: {
                BoundaryDecision.ALLOW,
                BoundaryDecision.PAUSE,
                BoundaryDecision.REPAIR,
                BoundaryDecision.REFUSE,
            },
        }
        if self.effective_decision not in permitted[self.runtime_decision]:
            raise ValueError("effective decision cannot weaken the Master Boundary")
        if self.effective_decision is BoundaryDecision.ALLOW and self.approval_required:
            raise ValueError("effective ALLOW cannot carry an unresolved approval requirement")
        if self.approval_required and self.effective_decision is not BoundaryDecision.PAUSE:
            raise ValueError("approval can only accompany an effective PAUSE")
        if (
            self.runtime_decision is RuntimeDecision.NEEDS_HUMAN_APPROVAL
            and self.effective_decision is BoundaryDecision.PAUSE
            and not self.approval_required
        ):
            raise ValueError("needs_human_approval requires an approval gate")
        if self.authority_level == 5 and (
            self.effective_decision is not BoundaryDecision.PAUSE
            or not self.approval_required
        ):
            raise ValueError("authority level 5 requires PAUSE and explicit approval")
        return self


class ObservationAwareness(BaseModel):
    """Distinguishes unverified reported feedback from verified evidence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: ObservationStatus = ObservationStatus.NOT_OBSERVED
    summary: StrictStr | None = Field(default=None, max_length=500)
    result_type: StrictStr | None = Field(default=None, max_length=80)
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)

    @field_validator("summary", "result_type")
    @classmethod
    def optional_text_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("observation text must not be blank")
        return value

    @field_validator("evidence_references")
    @classmethod
    def evidence_is_bounded_and_unique(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 256 for item in value):
            raise ValueError("evidence references must be non-blank and at most 256 characters")
        if len(set(value)) != len(value):
            raise ValueError("evidence references must be unique")
        return value

    @model_validator(mode="after")
    def status_matches_available_evidence(self) -> ObservationAwareness:
        if self.status is ObservationStatus.NOT_OBSERVED:
            if self.summary is not None or self.result_type is not None or self.evidence_references:
                raise ValueError("NOT_OBSERVED cannot contain a result or evidence")
            return self
        if self.summary is None:
            raise ValueError("an observed result requires a summary")
        if self.status is ObservationStatus.VERIFIED and not self.evidence_references:
            raise ValueError("VERIFIED observation requires evidence references")
        return self


class OperationalAwarenessState(BaseModel):
    """One immutable, non-authoritative representation of a reasoning cycle."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-operational-awareness-v1"] = SCHEMA_VERSION
    awareness_state_id: StrictStr = Field(pattern=_AWARENESS_ID_PATTERN)
    previous_awareness_state_id: StrictStr | None = Field(
        default=None, pattern=_AWARENESS_ID_PATTERN
    )
    observed_at_utc: datetime
    input_present: StrictBool
    sanitized_representation: Literal[True] = True
    redacted_fields: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    stated_intention: EpistemicValue[StrictStr]
    interpreted_objective: EpistemicValue[StrictStr]
    self_location: OperationalSelfLocation
    classification: EpistemicValue[StrictStr]
    uncertainty: UncertaintyRecord
    mirror_advisories: tuple[AdvisoryConsideration, ...]
    perspective_advisories: tuple[AdvisoryConsideration, ...]
    boundary: BoundaryAwareness
    last_observation: ObservationAwareness
    state_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @field_validator("observed_at_utc")
    @classmethod
    def observed_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at_utc must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("redacted_fields")
    @classmethod
    def redacted_fields_are_bounded_and_unique(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 128 for item in value):
            raise ValueError(
                "redacted field paths must be non-blank and at most 128 characters"
            )
        if len(set(value)) != len(value):
            raise ValueError("redacted field paths must be unique")
        return value

    @model_validator(mode="after")
    def validate_awareness_snapshot(self) -> OperationalAwarenessState:
        if self.stated_intention.status is not EpistemicStatus.USER_SUPPLIED:
            raise ValueError("stated intention provenance must remain USER_SUPPLIED")
        if self.input_present:
            if not self.stated_intention.value or not self.stated_intention.value.strip():
                raise ValueError("a present stated intention must be non-blank")
        elif self.stated_intention.value is not None:
            raise ValueError("an absent stated intention must not invent a value")

        expected_status = (
            EpistemicStatus.MODEL_PROPOSED
            if self.self_location.cognition_mode == "neural"
            else EpistemicStatus.DETERMINISTIC
        )
        for name, value in (
            ("interpreted objective", self.interpreted_objective),
            ("classification", self.classification),
        ):
            if value.status is not expected_status or not value.value or not value.value.strip():
                raise ValueError(
                    f"{name} provenance must match the declared cognition mode"
                )

        mirror_keys = tuple(item.key for item in self.mirror_advisories)
        perspective_keys = tuple(item.key for item in self.perspective_advisories)
        if mirror_keys != MIRROR_KEYS or any(
            item.source is not AdvisorySource.MIRROR for item in self.mirror_advisories
        ):
            raise ValueError("mirror advisories must contain each canonical mirror exactly once")
        if perspective_keys != PERSPECTIVE_KEYS or any(
            item.source is not AdvisorySource.PERSPECTIVE
            for item in self.perspective_advisories
        ):
            raise ValueError(
                "perspective advisories must contain each canonical perspective exactly once"
            )

        if (
            self.boundary.effective_decision is BoundaryDecision.ALLOW
            and self.self_location.unresolved_requests
        ):
            raise ValueError("unresolved requests prohibit an effective ALLOW snapshot")
        if self.previous_awareness_state_id == self.awareness_state_id:
            raise ValueError("an awareness state cannot be its own predecessor")

        expected_hash = canonical_sha256(self.material_fields())
        if self.state_hash != expected_hash:
            raise ValueError("state_hash mismatch")
        if self.awareness_state_id != f"awareness_{expected_hash}":
            raise ValueError("awareness_state_id must derive from state_hash")
        return self

    def material_fields(self) -> Mapping[str, object]:
        return self.model_dump(
            mode="python", exclude={"awareness_state_id", "state_hash"}
        )


def _source_mapping(
    value: MirrorReflection | MerkabahRotation | Mapping[str, str],
) -> Mapping[str, str]:
    if isinstance(value, (MirrorReflection, MerkabahRotation)):
        return value.as_dict()
    if isinstance(value, Mapping):
        return value
    raise TypeError("advisory source must be a reflection, rotation, or mapping")


def _build_advisories(
    value: MirrorReflection | MerkabahRotation | Mapping[str, str],
    *,
    source: AdvisorySource,
    expected_keys: tuple[str, ...],
) -> tuple[AdvisoryConsideration, ...]:
    items = _source_mapping(value)
    if set(items) != set(expected_keys):
        raise ValueError("advisory source keys must exactly match the canonical keys")
    return tuple(
        AdvisoryConsideration(
            source=source,
            key=key,
            prompt=_awareness_text(items[key]),
            epistemic_status=EpistemicStatus.SYMBOLIC,
            authority_effect="NONE",
        )
        for key in expected_keys
    )


def _runtime_decision(value: RuntimeDecision | str) -> RuntimeDecision:
    return value if isinstance(value, RuntimeDecision) else RuntimeDecision(value)


def _boundary_decision(value: BoundaryDecision | str) -> BoundaryDecision:
    return value if isinstance(value, BoundaryDecision) else BoundaryDecision(value)


def build_operational_awareness_state(
    *,
    stated_intention: str,
    interpreted_objective: str,
    objective_status: EpistemicStatus,
    objective_confidence: float,
    cognition_mode: Literal["neural", "offline_fallback"],
    current_state_present: bool,
    classification: str,
    classification_status: EpistemicStatus,
    classification_confidence: float,
    uncertainty: UncertaintyRecord,
    mirrors: MirrorReflection | Mapping[str, str],
    perspectives: MerkabahRotation | Mapping[str, str],
    runtime_decision: RuntimeDecision | str,
    effective_decision: BoundaryDecision | str,
    authority_level: int = 0,
    boundary_reasons: Sequence[str] = (),
    approval_required: bool = False,
    lifecycle: EpistemicValue[StrictStr] | None = None,
    available_tools: EpistemicValue[tuple[StrictStr, ...]] | None = None,
    established_permissions: EpistemicValue[tuple[StrictStr, ...]] | None = None,
    unresolved_requests: Sequence[str] = (),
    observation_status: ObservationStatus = ObservationStatus.NOT_OBSERVED,
    observation_summary: str | None = None,
    observation_result_type: str | None = None,
    observation_evidence_references: Sequence[str] = (),
    previous_awareness_state_id: str | None = None,
    observed_at_utc: datetime | None = None,
) -> OperationalAwarenessState:
    """Build a validated snapshot without performing I/O or granting authority."""

    timestamp = observed_at_utc or datetime.now(UTC)
    input_present = bool(stated_intention.strip())
    safe_stated_intention = (
        _awareness_text(stated_intention) if input_present else None
    )
    safe_interpreted_objective = _awareness_text(interpreted_objective)
    safe_boundary_reasons = tuple(_awareness_text(item) for item in boundary_reasons)
    safe_unresolved_requests = tuple(_awareness_text(item) for item in unresolved_requests)
    safe_observation_summary = (
        _awareness_text(observation_summary)
        if observation_summary is not None
        else None
    )
    safe_observation_result_type = (
        _awareness_text(observation_result_type)
        if observation_result_type is not None
        else None
    )
    redacted_fields = []
    for field_path, original, safe in (
        ("stated_intention", stated_intention, safe_stated_intention),
        ("interpreted_objective", interpreted_objective, safe_interpreted_objective),
        ("last_observation.summary", observation_summary, safe_observation_summary),
        ("last_observation.result_type", observation_result_type, safe_observation_result_type),
    ):
        if original is not None and original != safe:
            redacted_fields.append(field_path)
    redacted_fields.extend(
        f"boundary.reasons[{index}]"
        for index, (original, safe) in enumerate(
            zip(boundary_reasons, safe_boundary_reasons)
        )
        if original != safe
    )
    redacted_fields.extend(
        f"self_location.unresolved_requests[{index}]"
        for index, (original, safe) in enumerate(
            zip(unresolved_requests, safe_unresolved_requests)
        )
        if original != safe
    )
    mirror_advisories = _build_advisories(
        mirrors, source=AdvisorySource.MIRROR, expected_keys=MIRROR_KEYS
    )
    perspective_advisories = _build_advisories(
        perspectives,
        source=AdvisorySource.PERSPECTIVE,
        expected_keys=PERSPECTIVE_KEYS,
    )
    mirror_source = _source_mapping(mirrors)
    perspective_source = _source_mapping(perspectives)
    redacted_fields.extend(
        f"mirror_advisories[{index}].prompt"
        for index, item in enumerate(mirror_advisories)
        if mirror_source[item.key] != item.prompt
    )
    redacted_fields.extend(
        f"perspective_advisories[{index}].prompt"
        for index, item in enumerate(perspective_advisories)
        if perspective_source[item.key] != item.prompt
    )
    self_location = OperationalSelfLocation(
        cognition_mode=cognition_mode,
        current_state_present=current_state_present,
        lifecycle=lifecycle or _unknown_text(),
        available_tools=available_tools or _unknown_string_tuple(),
        established_permissions=established_permissions or _unknown_string_tuple(),
        unresolved_requests=safe_unresolved_requests,
    )
    material = {
        "schema_version": SCHEMA_VERSION,
        "previous_awareness_state_id": previous_awareness_state_id,
        "observed_at_utc": timestamp,
        "input_present": input_present,
        "sanitized_representation": True,
        "redacted_fields": tuple(redacted_fields),
        "stated_intention": EpistemicValue[StrictStr](
            status=EpistemicStatus.USER_SUPPLIED,
            value=safe_stated_intention,
            confidence=1.0 if input_present else 0.0,
        ),
        "interpreted_objective": EpistemicValue[StrictStr](
            status=objective_status,
            value=safe_interpreted_objective,
            confidence=objective_confidence,
        ),
        "self_location": self_location,
        "classification": EpistemicValue[StrictStr](
            status=classification_status,
            value=classification,
            confidence=classification_confidence,
        ),
        "uncertainty": uncertainty,
        "mirror_advisories": mirror_advisories,
        "perspective_advisories": perspective_advisories,
        "boundary": BoundaryAwareness(
            runtime_decision=_runtime_decision(runtime_decision),
            effective_decision=_boundary_decision(effective_decision),
            authority_level=authority_level,
            reasons=safe_boundary_reasons,
            approval_required=approval_required,
        ),
        "last_observation": ObservationAwareness(
            status=observation_status,
            summary=safe_observation_summary,
            result_type=safe_observation_result_type,
            evidence_references=tuple(observation_evidence_references),
        ),
    }
    draft = OperationalAwarenessState.model_construct(
        awareness_state_id=f"awareness_{'0' * 64}",
        state_hash="0" * 64,
        **material,
    )
    state_hash = canonical_sha256(draft.material_fields())
    return OperationalAwarenessState(
        awareness_state_id=f"awareness_{state_hash}",
        state_hash=state_hash,
        **material,
    )


__all__ = [
    "SCHEMA_VERSION",
    "AdvisoryConsideration",
    "AdvisorySource",
    "BoundaryAwareness",
    "ObservationAwareness",
    "ObservationStatus",
    "OperationalAwarenessState",
    "OperationalSelfLocation",
    "RuntimeDecision",
    "build_operational_awareness_state",
]
