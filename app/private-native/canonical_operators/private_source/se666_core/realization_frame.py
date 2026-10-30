"""Pure shadow contracts for SE6 state/frame representation.

The models in this module make ``X`` (the represented state) and ``Theta``
(the frame used to represent it) explicit and independently content addressed.
Frame expansion is representational only: it preserves the exact ``X`` object
and every immutable source-observation identifier/hash binding.

This module performs no I/O, persistence, network access, model calls,
approval handling, authority decisions, or production-state mutation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)

from .canonical_contracts import canonical_sha256
from .epistemic_status import EpistemicStatus

OBSERVATION_SCHEMA_VERSION = "se6-source-observation-v1-shadow"
STATE_SCHEMA_VERSION = "se6-realization-state-v1-shadow"
FRAME_SCHEMA_VERSION = "se6-realization-frame-v1-shadow"

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_OBSERVATION_ID_PATTERN = r"^source_observation_[0-9a-f]{64}$"
_X_ID_PATTERN = r"^x_[0-9a-f]{64}$"
_THETA_ID_PATTERN = r"^theta_[0-9a-f]{64}$"
_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"


class _ShadowContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SourceObservation(_ShadowContract):
    """One immutable source claim with explicit epistemic provenance.

    A source observation is not automatically a verified fact. ``VERIFIED``
    and ``MEASURED`` observations require evidence references, while reported,
    inferred, assumed, symbolic, and unknown material retain their own status.
    """

    schema_version: Literal["se6-source-observation-v1-shadow"] = (
        OBSERVATION_SCHEMA_VERSION
    )
    observation_id: StrictStr = Field(pattern=_OBSERVATION_ID_PATTERN)
    observation_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    source_reference: StrictStr = Field(
        min_length=1, max_length=256, pattern=_REFERENCE_PATTERN
    )
    summary: StrictStr = Field(min_length=1, max_length=4_000)
    epistemic_status: EpistemicStatus
    evidence_references: tuple[StrictStr, ...] = Field(
        default=(), max_length=64
    )
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def observation_is_content_addressed(self) -> SourceObservation:
        if len(self.evidence_references) != len(set(self.evidence_references)):
            raise ValueError("observation evidence references must be unique")
        if self.epistemic_status in {
            EpistemicStatus.MEASURED,
            EpistemicStatus.VERIFIED,
        } and not self.evidence_references:
            raise ValueError("measured or verified observation requires evidence")
        expected = canonical_sha256(self.material_fields())
        if self.observation_hash != expected:
            raise ValueError("observation_hash must derive from observation material")
        if self.observation_id != f"source_observation_{expected}":
            raise ValueError("observation_id must derive from observation material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"observation_id", "observation_hash"}
        )

    @property
    def binding(self) -> ObservationBinding:
        return ObservationBinding(
            observation_id=self.observation_id,
            observation_hash=self.observation_hash,
        )


class ObservationBinding(_ShadowContract):
    """Exact immutable reference to a source observation."""

    observation_id: StrictStr = Field(pattern=_OBSERVATION_ID_PATTERN)
    observation_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def id_and_hash_match(self) -> ObservationBinding:
        if self.observation_id != f"source_observation_{self.observation_hash}":
            raise ValueError("observation binding id/hash mismatch")
        return self


class SE6ZeroReference(_ShadowContract):
    """The canonical computational reference origin, never a physics claim."""

    reference_id: Literal["0_SE6"] = "0_SE6"
    meaning: Literal["computational/reference origin"] = (
        "computational/reference origin"
    )
    physical_energy_claim: Literal[False] = False
    reference_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def reference_is_content_addressed(self) -> SE6ZeroReference:
        if self.reference_hash != canonical_sha256(self.material_fields()):
            raise ValueError("reference_hash must derive from reference material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"reference_hash"})


class RealizationState(_ShadowContract):
    """One immutable shadow ``X`` snapshot with explicit predecessor lineage."""

    schema_version: Literal["se6-realization-state-v1-shadow"] = (
        STATE_SCHEMA_VERSION
    )
    x_id: StrictStr = Field(pattern=_X_ID_PATTERN)
    x_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    previous_x_id: StrictStr | None = Field(default=None, pattern=_X_ID_PATTERN)
    previous_x_hash: StrictStr | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    state_version: StrictInt = Field(default=0, ge=0)
    state_summary: StrictStr = Field(min_length=1, max_length=4_000)
    source_observations: tuple[SourceObservation, ...] = Field(
        min_length=1, max_length=256
    )
    shadow_only: Literal[True] = True
    production_authoritative: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def state_is_content_addressed_and_linear(self) -> RealizationState:
        predecessor_pair = (self.previous_x_id, self.previous_x_hash)
        if (predecessor_pair[0] is None) != (predecessor_pair[1] is None):
            raise ValueError("previous X id and hash must appear together")
        if self.state_version == 0 and self.previous_x_id is not None:
            raise ValueError("genesis X cannot have a predecessor")
        if self.state_version > 0 and self.previous_x_id is None:
            raise ValueError("advanced X requires a predecessor")
        if self.previous_x_id is not None:
            if self.previous_x_id != f"x_{self.previous_x_hash}":
                raise ValueError("previous X id/hash mismatch")
            if self.previous_x_id == self.x_id:
                raise ValueError("X cannot reference itself as predecessor")
        ids = tuple(item.observation_id for item in self.source_observations)
        if len(ids) != len(set(ids)):
            raise ValueError("source observations must be unique")
        expected = canonical_sha256(self.material_fields())
        if self.x_hash != expected:
            raise ValueError("x_hash must derive from X material")
        if self.x_id != f"x_{expected}":
            raise ValueError("x_id must derive from X material")
        return self

    @property
    def observation_bindings(self) -> tuple[ObservationBinding, ...]:
        return tuple(item.binding for item in self.source_observations)

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"x_id", "x_hash"})


class RealizationFrame(_ShadowContract):
    """One immutable ``Theta`` representation of an exact shadow ``X``.

    ``EXPANSION`` frames carry the predecessor frame and predecessor ``X``
    bindings. The factory below permits expansion only while reusing the same
    frozen ``RealizationState`` object and exact source-observation bindings.
    """

    schema_version: Literal["se6-realization-frame-v1-shadow"] = (
        FRAME_SCHEMA_VERSION
    )
    theta_id: StrictStr = Field(pattern=_THETA_ID_PATTERN)
    theta_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    previous_theta_id: StrictStr | None = Field(
        default=None, pattern=_THETA_ID_PATTERN
    )
    previous_theta_hash: StrictStr | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    predecessor_x_id: StrictStr | None = Field(default=None, pattern=_X_ID_PATTERN)
    predecessor_x_hash: StrictStr | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    generation: StrictInt = Field(default=0, ge=0)
    operation: Literal["GENESIS", "EXPANSION"]
    frame_name: StrictStr = Field(min_length=1, max_length=256)
    x: RealizationState
    zero_reference: SE6ZeroReference
    dimensions: tuple[StrictStr, ...] = Field(min_length=1, max_length=128)
    representation_rules: tuple[StrictStr, ...] = Field(
        default=(), max_length=128
    )
    preserved_observation_bindings: tuple[ObservationBinding, ...] = Field(
        min_length=1, max_length=256
    )
    shadow_only: Literal[True] = True
    production_authoritative: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def frame_is_content_addressed_and_safe(self) -> RealizationFrame:
        theta_pair = (self.previous_theta_id, self.previous_theta_hash)
        x_pair = (self.predecessor_x_id, self.predecessor_x_hash)
        if (theta_pair[0] is None) != (theta_pair[1] is None):
            raise ValueError("previous Theta id and hash must appear together")
        if (x_pair[0] is None) != (x_pair[1] is None):
            raise ValueError("predecessor X id and hash must appear together")
        if self.operation == "GENESIS":
            if self.generation != 0 or any(item is not None for item in theta_pair + x_pair):
                raise ValueError("genesis Theta cannot have predecessor lineage")
        else:
            if self.generation < 1 or any(item is None for item in theta_pair + x_pair):
                raise ValueError("expanded Theta requires complete predecessor lineage")
            if self.previous_theta_id != f"theta_{self.previous_theta_hash}":
                raise ValueError("previous Theta id/hash mismatch")
            if self.predecessor_x_id != f"x_{self.predecessor_x_hash}":
                raise ValueError("predecessor X id/hash mismatch")
            if (
                self.predecessor_x_id != self.x.x_id
                or self.predecessor_x_hash != self.x.x_hash
            ):
                raise ValueError("frame expansion must preserve the exact X")
        if self.previous_theta_id == self.theta_id:
            raise ValueError("Theta cannot reference itself as predecessor")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("frame dimensions must be unique")
        if len(self.representation_rules) != len(set(self.representation_rules)):
            raise ValueError("frame representation rules must be unique")
        if self.preserved_observation_bindings != self.x.observation_bindings:
            raise ValueError("Theta must preserve exact source observation bindings")
        expected = canonical_sha256(self.material_fields())
        if self.theta_hash != expected:
            raise ValueError("theta_hash must derive from Theta material")
        if self.theta_id != f"theta_{expected}":
            raise ValueError("theta_id must derive from Theta material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"theta_id", "theta_hash"})


def create_source_observation(
    *,
    source_reference: str,
    summary: str,
    epistemic_status: EpistemicStatus,
    evidence_references: Sequence[str] = (),
) -> SourceObservation:
    """Construct one deterministic immutable source observation."""

    material = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "source_reference": source_reference,
        "summary": summary,
        "epistemic_status": epistemic_status,
        "evidence_references": tuple(evidence_references),
        "shadow_only": True,
        "authority_effect": "NONE",
    }
    digest = canonical_sha256(material)
    return SourceObservation(
        observation_id=f"source_observation_{digest}",
        observation_hash=digest,
        **material,
    )


def create_zero_reference() -> SE6ZeroReference:
    """Return the fixed, non-physical ``0_SE6`` computational origin."""

    material = {
        "reference_id": "0_SE6",
        "meaning": "computational/reference origin",
        "physical_energy_claim": False,
    }
    return SE6ZeroReference(
        reference_hash=canonical_sha256(material),
        **material,
    )


ZERO_SE6_REFERENCE = create_zero_reference()


def create_realization_state(
    *,
    state_summary: str,
    source_observations: Sequence[SourceObservation],
) -> RealizationState:
    """Create a genesis shadow ``X`` from immutable observations."""

    return _build_state(
        previous=None,
        state_summary=state_summary,
        source_observations=tuple(source_observations),
    )


def advance_realization_state(
    previous: RealizationState,
    *,
    state_summary: str,
    additional_observations: Sequence[SourceObservation] = (),
) -> RealizationState:
    """Append observations and create the next content-addressed ``X``.

    Existing source observations are copied exactly and cannot be replaced.
    A changed claim must therefore become a new, separately identified source
    observation rather than rewriting prior material.
    """

    return _build_state(
        previous=previous,
        state_summary=state_summary,
        source_observations=(
            previous.source_observations + tuple(additional_observations)
        ),
    )


def create_realization_frame(
    x: RealizationState,
    *,
    frame_name: str,
    dimensions: Sequence[str],
    representation_rules: Sequence[str] = (),
) -> RealizationFrame:
    """Create a genesis ``Theta`` bound to one exact ``X``."""

    return _build_frame(
        previous=None,
        x=x,
        frame_name=frame_name,
        dimensions=tuple(dimensions),
        representation_rules=tuple(representation_rules),
    )


def expand_realization_frame(
    previous: RealizationFrame,
    *,
    frame_name: str,
    added_dimensions: Sequence[str],
    added_representation_rules: Sequence[str] = (),
) -> RealizationFrame:
    """Expand ``Theta`` without changing ``X`` or any source observation."""

    return _build_frame(
        previous=previous,
        x=previous.x,
        frame_name=frame_name,
        dimensions=_append_unique(previous.dimensions, added_dimensions),
        representation_rules=_append_unique(
            previous.representation_rules, added_representation_rules
        ),
    )


def _build_state(
    *,
    previous: RealizationState | None,
    state_summary: str,
    source_observations: tuple[SourceObservation, ...],
) -> RealizationState:
    material = {
        "schema_version": STATE_SCHEMA_VERSION,
        "previous_x_id": previous.x_id if previous is not None else None,
        "previous_x_hash": previous.x_hash if previous is not None else None,
        "state_version": previous.state_version + 1 if previous is not None else 0,
        "state_summary": state_summary,
        "source_observations": source_observations,
        "shadow_only": True,
        "production_authoritative": False,
        "authority_effect": "NONE",
    }
    draft = RealizationState.model_construct(
        x_id=f"x_{'0' * 64}", x_hash="0" * 64, **material
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return RealizationState(x_id=f"x_{digest}", x_hash=digest, **normalized)


def _build_frame(
    *,
    previous: RealizationFrame | None,
    x: RealizationState,
    frame_name: str,
    dimensions: tuple[str, ...],
    representation_rules: tuple[str, ...],
) -> RealizationFrame:
    material = {
        "schema_version": FRAME_SCHEMA_VERSION,
        "previous_theta_id": previous.theta_id if previous is not None else None,
        "previous_theta_hash": previous.theta_hash if previous is not None else None,
        "predecessor_x_id": x.x_id if previous is not None else None,
        "predecessor_x_hash": x.x_hash if previous is not None else None,
        "generation": previous.generation + 1 if previous is not None else 0,
        "operation": "EXPANSION" if previous is not None else "GENESIS",
        "frame_name": frame_name,
        "x": x,
        "zero_reference": ZERO_SE6_REFERENCE,
        "dimensions": dimensions,
        "representation_rules": representation_rules,
        "preserved_observation_bindings": x.observation_bindings,
        "shadow_only": True,
        "production_authoritative": False,
        "authority_effect": "NONE",
    }
    draft = RealizationFrame.model_construct(
        theta_id=f"theta_{'0' * 64}", theta_hash="0" * 64, **material
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return RealizationFrame(
        theta_id=f"theta_{digest}", theta_hash=digest, **normalized
    )


def _append_unique(existing: tuple[str, ...], additions: Sequence[str]) -> tuple[str, ...]:
    combined = list(existing)
    seen = set(existing)
    for item in additions:
        if item not in seen:
            combined.append(item)
            seen.add(item)
    return tuple(combined)


__all__ = [
    "FRAME_SCHEMA_VERSION",
    "OBSERVATION_SCHEMA_VERSION",
    "STATE_SCHEMA_VERSION",
    "ZERO_SE6_REFERENCE",
    "ObservationBinding",
    "RealizationFrame",
    "RealizationState",
    "SE6ZeroReference",
    "SourceObservation",
    "advance_realization_state",
    "create_realization_frame",
    "create_realization_state",
    "create_source_observation",
    "create_zero_reference",
    "expand_realization_frame",
]
