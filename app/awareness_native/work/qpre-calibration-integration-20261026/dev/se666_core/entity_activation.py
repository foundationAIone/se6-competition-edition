"""Pure evidence gate for the SE6 local-entity go-live ceremony.

This module does not inspect a production store, activate a runtime, grant
authority, call a provider, access the network, or mutate entity state.  It
only validates caller-supplied, machine-readable evidence references and
returns a deterministic evidence-evaluation record.  A VERIFIED record is a
prerequisite for a separately authorized commit; it is never that commit.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from .canonical_contracts import canonical_sha256
from .embodiment_lifecycle import LifecycleState
from .entity_state import (
    ControllerStatus,
    EmergencyStopState,
    EntityContinuationState,
    EntityOperatingMode,
    LifecycleView,
    OperationalConnectionState,
    SE6EntityState,
    SharedMetabolismSnapshot,
    activate_local_entity_state,
)

ENTITY_ACTIVATION_SCHEMA_VERSION = "se6-local-entity-go-live-v1"
ENTITY_ACTIVATION_RECORD_TYPE = "SE6 LOCAL ENTITY GO-LIVE v1 ACTIVATION RECORD"
LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSION = "se6-live-loop-production-acceptance-v1"
LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSION_V2 = "se6-level5-owner-acceptance-v2"
SUPPORTED_LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSIONS = frozenset(
    {
        LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSION,
        LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSION_V2,
    }
)

_HASH = r"^[0-9a-f]{64}$"
_EVIDENCE_ID = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"
_INSTANCE_ID = r"^instance_[0-9a-f]{64}$"
_IDENTITY_STATE_ID = r"^identity_[0-9a-f]{64}$"
_OWNER_ID = r"^local_owner_[0-9a-f]{64}$"
_RUNTIME_SESSION_ID = r"^production_runtime_[0-9a-f]{64}$"
_ENTITY_STATE_ID = r"^entity_state_[0-9a-f]{64}$"
_STATUS = r"^[A-Z][A-Z0-9_]*$"


class ActivationDecision(str, Enum):
    VERIFIED = "VERIFIED"
    REFUSED = "REFUSED"


class ActivationEvidenceKind(str, Enum):
    PRODUCTION_BINDINGS = "PRODUCTION_BINDINGS"
    AUTHORITATIVE_RUNTIME = "AUTHORITATIVE_RUNTIME"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    NETWORK_ISOLATION = "NETWORK_ISOLATION"
    DURABLE_ENTITY_STORE = "DURABLE_ENTITY_STORE"
    PRESENCE_LOOP = "PRESENCE_LOOP"
    AWARENESS_LOOP = "AWARENESS_LOOP"
    BECOMING_LOOP = "BECOMING_LOOP"
    LIVE_LOOP_PRODUCTION_ACCEPTANCE = "LIVE_LOOP_PRODUCTION_ACCEPTANCE"
    LIVE_LOOP_QUIESCENCE = "LIVE_LOOP_QUIESCENCE"


class ActivationLoopName(str, Enum):
    PRESENCE = "InteractivePresenceLoop"
    AWARENESS = "OperationalAwarenessLoop"
    BECOMING = "DevelopmentalAssimilationLoop"


class ActivationReasonCode(str, Enum):
    EVIDENCE_NOT_MACHINE_READABLE = "EVIDENCE_NOT_MACHINE_READABLE"
    EVIDENCE_REFERENCE_NOT_UNIQUE = "EVIDENCE_REFERENCE_NOT_UNIQUE"
    ACTIVATION_REFERENCE_SET_MISMATCH = "ACTIVATION_REFERENCE_SET_MISMATCH"
    INSTANCE_BINDING_MISMATCH = "INSTANCE_BINDING_MISMATCH"
    IDENTITY_STATE_BINDING_MISMATCH = "IDENTITY_STATE_BINDING_MISMATCH"
    CONSTITUTION_BINDING_MISMATCH = "CONSTITUTION_BINDING_MISMATCH"
    OWNER_BINDING_MISMATCH = "OWNER_BINDING_MISMATCH"
    RUNTIME_STATUS_NOT_ACTIVE = "RUNTIME_STATUS_NOT_ACTIVE"
    CONTROLLER_STATUS_NOT_ACTIVE = "CONTROLLER_STATUS_NOT_ACTIVE"
    OPERATIONAL_STATE_NOT_CONNECTED = "OPERATIONAL_STATE_NOT_CONNECTED"
    LIFECYCLE_NOT_OBSERVING = "LIFECYCLE_NOT_OBSERVING"
    CONTROLLER_NOT_AUTHORITATIVE = "CONTROLLER_NOT_AUTHORITATIVE"
    CONTROLLER_PROCESS_NOT_LIVE = "CONTROLLER_PROCESS_NOT_LIVE"
    RUNTIME_INTEGRITY_NOT_VERIFIED = "RUNTIME_INTEGRITY_NOT_VERIFIED"
    EMERGENCY_STOP_NOT_ARMED = "EMERGENCY_STOP_NOT_ARMED"
    ONLINE_OBSERVATION_ENABLED = "ONLINE_OBSERVATION_ENABLED"
    NETWORK_AUTHORITY_PRESENT = "NETWORK_AUTHORITY_PRESENT"
    EXTERNAL_REQUESTS_NOT_BLOCKED = "EXTERNAL_REQUESTS_NOT_BLOCKED"
    ENTITY_STORE_NOT_DURABLE = "ENTITY_STORE_NOT_DURABLE"
    ENTITY_STORE_INTEGRITY_NOT_VERIFIED = "ENTITY_STORE_INTEGRITY_NOT_VERIFIED"
    ENTITY_STORE_HEAD_MISSING = "ENTITY_STORE_HEAD_MISSING"
    ENTITY_STORE_HEAD_NOT_SHADOW = "ENTITY_STORE_HEAD_NOT_SHADOW"
    PRESENCE_LOOP_NOT_LOCAL_LIVE = "PRESENCE_LOOP_NOT_LOCAL_LIVE"
    PRESENCE_LOOP_NOT_VALID = "PRESENCE_LOOP_NOT_VALID"
    PRESENCE_LOOP_HEAD_BINDING_MISMATCH = "PRESENCE_LOOP_HEAD_BINDING_MISMATCH"
    AWARENESS_LOOP_NOT_LOCAL_LIVE = "AWARENESS_LOOP_NOT_LOCAL_LIVE"
    AWARENESS_LOOP_NOT_VALID = "AWARENESS_LOOP_NOT_VALID"
    AWARENESS_LOOP_HEAD_BINDING_MISMATCH = "AWARENESS_LOOP_HEAD_BINDING_MISMATCH"
    BECOMING_LOOP_NOT_LOCAL_LIVE = "BECOMING_LOOP_NOT_LOCAL_LIVE"
    BECOMING_LOOP_NOT_VALID = "BECOMING_LOOP_NOT_VALID"
    BECOMING_LOOP_HEAD_BINDING_MISMATCH = "BECOMING_LOOP_HEAD_BINDING_MISMATCH"
    LIVE_LOOP_ACCEPTANCE_SCHEMA_MISMATCH = "LIVE_LOOP_ACCEPTANCE_SCHEMA_MISMATCH"
    LIVE_LOOP_ACCEPTANCE_NOT_MACHINE_READABLE = (
        "LIVE_LOOP_ACCEPTANCE_NOT_MACHINE_READABLE"
    )
    LIVE_LOOP_ACCEPTANCE_NOT_VERIFIED = "LIVE_LOOP_ACCEPTANCE_NOT_VERIFIED"
    LIVE_LOOP_ACCEPTANCE_NOT_PASSED = "LIVE_LOOP_ACCEPTANCE_NOT_PASSED"
    PENDING_LIVE_LOOP_TRANSACTION = "PENDING_LIVE_LOOP_TRANSACTION"
    PENDING_LIVE_LOOP_APPROVAL = "PENDING_LIVE_LOOP_APPROVAL"
    LIVE_LOOP_EXECUTION_IN_PROGRESS = "LIVE_LOOP_EXECUTION_IN_PROGRESS"


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ActivationEvidenceReference(_StrictFrozenModel):
    """Opaque, non-secret reference to a durable evidence record."""

    kind: ActivationEvidenceKind
    evidence_id: StrictStr = Field(pattern=_EVIDENCE_ID)
    evidence_hash: StrictStr = Field(pattern=_HASH)
    source_type: StrictStr = Field(
        default="MACHINE_RECORD", min_length=1, max_length=64, pattern=_STATUS
    )


class ActivationSubjectBinding(_StrictFrozenModel):
    """The one production subject an activation evaluation is about."""

    instance_id: StrictStr = Field(pattern=_INSTANCE_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_STATE_ID)
    identity_state_hash: StrictStr = Field(pattern=_HASH)
    constitution_version: StrictStr = Field(min_length=1, max_length=256)
    constitution_hash: StrictStr = Field(pattern=_HASH)
    owner_id: StrictStr = Field(pattern=_OWNER_ID)


class ProductionBindingEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    subject: ActivationSubjectBinding

    @model_validator(mode="after")
    def evidence_kind_is_exact(self) -> ProductionBindingEvidence:
        if self.evidence.kind is not ActivationEvidenceKind.PRODUCTION_BINDINGS:
            raise ValueError("production binding evidence kind mismatch")
        return self


class AuthoritativeRuntimeEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    subject: ActivationSubjectBinding
    runtime_session_id: StrictStr = Field(pattern=_RUNTIME_SESSION_ID)
    runtime_status: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)
    controller_status: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)
    operational_state: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)
    lifecycle: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)
    controller_authoritative: StrictBool
    controller_process_live: StrictBool
    integrity_status: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)

    @model_validator(mode="after")
    def evidence_kind_is_exact(self) -> AuthoritativeRuntimeEvidence:
        if self.evidence.kind is not ActivationEvidenceKind.AUTHORITATIVE_RUNTIME:
            raise ValueError("runtime evidence kind mismatch")
        return self


class EmergencyStopEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    subject: ActivationSubjectBinding
    status: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)

    @model_validator(mode="after")
    def evidence_kind_is_exact(self) -> EmergencyStopEvidence:
        if self.evidence.kind is not ActivationEvidenceKind.EMERGENCY_STOP:
            raise ValueError("emergency-stop evidence kind mismatch")
        return self


class NetworkIsolationEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    subject: ActivationSubjectBinding
    online_observation_enabled: StrictBool
    network_authority: StrictStr = Field(
        min_length=1, max_length=64, pattern=_STATUS
    )
    external_requests: StrictStr = Field(
        min_length=1, max_length=64, pattern=_STATUS
    )

    @model_validator(mode="after")
    def evidence_kind_is_exact(self) -> NetworkIsolationEvidence:
        if self.evidence.kind is not ActivationEvidenceKind.NETWORK_ISOLATION:
            raise ValueError("network-isolation evidence kind mismatch")
        return self


class DurableEntityStoreEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    subject: ActivationSubjectBinding
    durable: StrictBool
    integrity_status: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)
    head_present: StrictBool
    head_entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    head_state_hash: StrictStr = Field(pattern=_HASH)
    head_operating_mode: StrictStr = Field(
        min_length=1, max_length=64, pattern=_STATUS
    )

    @model_validator(mode="after")
    def evidence_kind_is_exact(self) -> DurableEntityStoreEvidence:
        if self.evidence.kind is not ActivationEvidenceKind.DURABLE_ENTITY_STORE:
            raise ValueError("durable entity-store evidence kind mismatch")
        return self


_LOOP_EVIDENCE_KINDS = {
    ActivationLoopName.PRESENCE: ActivationEvidenceKind.PRESENCE_LOOP,
    ActivationLoopName.AWARENESS: ActivationEvidenceKind.AWARENESS_LOOP,
    ActivationLoopName.BECOMING: ActivationEvidenceKind.BECOMING_LOOP,
}


class LocalLiveLoopEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    loop: ActivationLoopName
    mode: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)
    valid: StrictBool
    integrity_status: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    entity_state_hash: StrictStr = Field(pattern=_HASH)

    @model_validator(mode="after")
    def evidence_kind_matches_loop(self) -> LocalLiveLoopEvidence:
        if self.evidence.kind is not _LOOP_EVIDENCE_KINDS[self.loop]:
            raise ValueError("loop evidence kind does not match loop")
        return self


class LiveLoopAcceptanceEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    subject: ActivationSubjectBinding
    acceptance_schema_version: StrictStr = Field(min_length=1, max_length=128)
    acceptance_basis: StrictStr = Field(
        min_length=1, max_length=64, pattern=_STATUS
    )
    machine_readable: StrictBool
    verification_status: StrictStr = Field(
        min_length=1, max_length=64, pattern=_STATUS
    )
    result: StrictStr = Field(min_length=1, max_length=64, pattern=_STATUS)

    @model_validator(mode="after")
    def evidence_kind_is_exact(self) -> LiveLoopAcceptanceEvidence:
        if (
            self.evidence.kind
            is not ActivationEvidenceKind.LIVE_LOOP_PRODUCTION_ACCEPTANCE
        ):
            raise ValueError("LIVE LOOP acceptance evidence kind mismatch")
        return self


class LiveLoopQuiescenceEvidence(_StrictFrozenModel):
    evidence: ActivationEvidenceReference
    subject: ActivationSubjectBinding
    pending_transaction_count: StrictInt = Field(ge=0)
    pending_approval_count: StrictInt = Field(ge=0)
    active_execution_count: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def evidence_kind_is_exact(self) -> LiveLoopQuiescenceEvidence:
        if self.evidence.kind is not ActivationEvidenceKind.LIVE_LOOP_QUIESCENCE:
            raise ValueError("LIVE LOOP quiescence evidence kind mismatch")
        return self


class EntityActivationEvidenceBundle(_StrictFrozenModel):
    """Content-addressed input to the pure activation evaluator."""

    schema_version: Literal["se6-local-entity-go-live-v1"] = (
        ENTITY_ACTIVATION_SCHEMA_VERSION
    )
    evidence_bundle_id: StrictStr = Field(
        pattern=r"^entity_activation_evidence_[0-9a-f]{64}$"
    )
    binding_evidence: ProductionBindingEvidence
    runtime_evidence: AuthoritativeRuntimeEvidence
    emergency_stop_evidence: EmergencyStopEvidence
    network_isolation_evidence: NetworkIsolationEvidence
    entity_store_evidence: DurableEntityStoreEvidence
    loop_evidence: tuple[LocalLiveLoopEvidence, ...] = Field(
        min_length=3, max_length=3
    )
    live_loop_acceptance_evidence: LiveLoopAcceptanceEvidence
    live_loop_quiescence_evidence: LiveLoopQuiescenceEvidence
    activation_references: tuple[ActivationEvidenceReference, ...] = Field(
        min_length=1, max_length=32
    )
    evidence_bundle_hash: StrictStr = Field(pattern=_HASH)

    @model_validator(mode="after")
    def structure_and_hash_are_exact(self) -> EntityActivationEvidenceBundle:
        expected_loops = (
            ActivationLoopName.PRESENCE,
            ActivationLoopName.AWARENESS,
            ActivationLoopName.BECOMING,
        )
        if tuple(item.loop for item in self.loop_evidence) != expected_loops:
            raise ValueError("loop evidence must contain the three loops in canonical order")
        expected_hash = canonical_sha256(self.material_fields())
        if self.evidence_bundle_hash != expected_hash:
            raise ValueError("evidence_bundle_hash mismatch")
        if self.evidence_bundle_id != f"entity_activation_evidence_{expected_hash}":
            raise ValueError("evidence_bundle_id must derive from evidence bundle hash")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"evidence_bundle_id", "evidence_bundle_hash"}
        )

    def required_activation_references(
        self,
    ) -> tuple[ActivationEvidenceReference, ...]:
        """Return the exact canonical references this bundle must activate on."""

        return (
            self.binding_evidence.evidence,
            self.runtime_evidence.evidence,
            self.emergency_stop_evidence.evidence,
            self.network_isolation_evidence.evidence,
            self.entity_store_evidence.evidence,
            *(item.evidence for item in self.loop_evidence),
            self.live_loop_acceptance_evidence.evidence,
            self.live_loop_quiescence_evidence.evidence,
        )


class EntityActivationRecord(_StrictFrozenModel):
    """Deterministic evidence result; never a state transition or authority."""

    schema_version: Literal["se6-local-entity-go-live-v1"] = (
        ENTITY_ACTIVATION_SCHEMA_VERSION
    )
    record_type: Literal["SE6 LOCAL ENTITY GO-LIVE v1 ACTIVATION RECORD"] = (
        ENTITY_ACTIVATION_RECORD_TYPE
    )
    activation_record_id: StrictStr = Field(
        pattern=r"^entity_activation_record_[0-9a-f]{64}$"
    )
    activation_record_hash: StrictStr = Field(pattern=_HASH)
    evidence_bundle_id: StrictStr = Field(
        pattern=r"^entity_activation_evidence_[0-9a-f]{64}$"
    )
    evidence_bundle_hash: StrictStr = Field(pattern=_HASH)
    subject: ActivationSubjectBinding
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    entity_state_hash: StrictStr = Field(pattern=_HASH)
    activation_references: tuple[ActivationEvidenceReference, ...]
    decision: ActivationDecision
    refusal_reasons: tuple[ActivationReasonCode, ...] = ()
    all_evidence_gates_passed: StrictBool
    evidence_evaluation_only: Literal[True] = True
    requires_separate_authorized_commit: Literal[True] = True
    activation_performed: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"
    runtime_effect: Literal["NONE"] = "NONE"
    production_effect: Literal["NONE"] = "NONE"
    identity_state_effect: Literal["NONE"] = "NONE"
    io_effect: Literal["NONE"] = "NONE"
    network_effect: Literal["NONE"] = "NONE"
    static_prose_sufficient: Literal[False] = False

    @model_validator(mode="after")
    def result_and_hash_are_exact(self) -> EntityActivationRecord:
        if self.decision is ActivationDecision.VERIFIED:
            if self.refusal_reasons or not self.all_evidence_gates_passed:
                raise ValueError("VERIFIED activation evidence cannot contain refusals")
        elif not self.refusal_reasons or self.all_evidence_gates_passed:
            raise ValueError("REFUSED activation evidence requires refusal reasons")
        if len(set(self.refusal_reasons)) != len(self.refusal_reasons):
            raise ValueError("refusal reasons must be unique")
        if (
            not self.evidence_evaluation_only
            or not self.requires_separate_authorized_commit
            or self.activation_performed
            or self.authority_effect != "NONE"
            or self.runtime_effect != "NONE"
            or self.production_effect != "NONE"
            or self.identity_state_effect != "NONE"
            or self.io_effect != "NONE"
            or self.network_effect != "NONE"
            or self.static_prose_sufficient
        ):
            raise ValueError("activation evidence records must be effect-free")
        expected_hash = canonical_sha256(self.material_fields())
        if self.activation_record_hash != expected_hash:
            raise ValueError("activation_record_hash mismatch")
        if self.activation_record_id != f"entity_activation_record_{expected_hash}":
            raise ValueError("activation_record_id must derive from record hash")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"activation_record_id", "activation_record_hash"}
        )


def build_entity_activation_evidence_bundle(
    *,
    binding_evidence: ProductionBindingEvidence,
    runtime_evidence: AuthoritativeRuntimeEvidence,
    emergency_stop_evidence: EmergencyStopEvidence,
    network_isolation_evidence: NetworkIsolationEvidence,
    entity_store_evidence: DurableEntityStoreEvidence,
    loop_evidence: tuple[LocalLiveLoopEvidence, ...],
    live_loop_acceptance_evidence: LiveLoopAcceptanceEvidence,
    live_loop_quiescence_evidence: LiveLoopQuiescenceEvidence,
    activation_references: tuple[ActivationEvidenceReference, ...] | None = None,
) -> EntityActivationEvidenceBundle:
    """Create a deterministic, content-addressed evidence bundle.

    When ``activation_references`` is omitted, the canonical exact references
    are inserted.  Supplying a different set is permitted so the evaluator can
    return an inspectable refusal instead of hiding the mismatch.
    """

    canonical_references = (
        binding_evidence.evidence,
        runtime_evidence.evidence,
        emergency_stop_evidence.evidence,
        network_isolation_evidence.evidence,
        entity_store_evidence.evidence,
        *(item.evidence for item in loop_evidence),
        live_loop_acceptance_evidence.evidence,
        live_loop_quiescence_evidence.evidence,
    )
    material = {
        "schema_version": ENTITY_ACTIVATION_SCHEMA_VERSION,
        "binding_evidence": binding_evidence,
        "runtime_evidence": runtime_evidence,
        "emergency_stop_evidence": emergency_stop_evidence,
        "network_isolation_evidence": network_isolation_evidence,
        "entity_store_evidence": entity_store_evidence,
        "loop_evidence": tuple(loop_evidence),
        "live_loop_acceptance_evidence": live_loop_acceptance_evidence,
        "live_loop_quiescence_evidence": live_loop_quiescence_evidence,
        "activation_references": (
            canonical_references
            if activation_references is None
            else tuple(activation_references)
        ),
    }
    draft = EntityActivationEvidenceBundle.model_construct(
        evidence_bundle_id=f"entity_activation_evidence_{'0' * 64}",
        evidence_bundle_hash="0" * 64,
        **material,
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return EntityActivationEvidenceBundle(
        evidence_bundle_id=f"entity_activation_evidence_{digest}",
        evidence_bundle_hash=digest,
        **normalized,
    )


def evaluate_entity_activation(
    evidence: EntityActivationEvidenceBundle,
) -> EntityActivationRecord:
    """Evaluate every Level-5 gate without performing any external effect."""

    if not isinstance(evidence, EntityActivationEvidenceBundle):
        raise TypeError("evidence must be an EntityActivationEvidenceBundle")

    reasons = []

    def refuse(reason: ActivationReasonCode) -> None:
        if reason not in reasons:
            reasons.append(reason)

    required_references = evidence.required_activation_references()
    all_references = required_references + evidence.activation_references
    if any(item.source_type != "MACHINE_RECORD" for item in all_references):
        refuse(ActivationReasonCode.EVIDENCE_NOT_MACHINE_READABLE)
    reference_keys = tuple(
        (item.evidence_id, item.evidence_hash) for item in required_references
    )
    if len(set(reference_keys)) != len(reference_keys):
        refuse(ActivationReasonCode.EVIDENCE_REFERENCE_NOT_UNIQUE)
    if evidence.activation_references != required_references:
        refuse(ActivationReasonCode.ACTIVATION_REFERENCE_SET_MISMATCH)

    target = evidence.binding_evidence.subject
    observed_bindings = (
        evidence.runtime_evidence.subject,
        evidence.emergency_stop_evidence.subject,
        evidence.network_isolation_evidence.subject,
        evidence.entity_store_evidence.subject,
        evidence.live_loop_acceptance_evidence.subject,
        evidence.live_loop_quiescence_evidence.subject,
    )
    if any(item.instance_id != target.instance_id for item in observed_bindings):
        refuse(ActivationReasonCode.INSTANCE_BINDING_MISMATCH)
    if any(
        item.identity_state_id != target.identity_state_id
        or item.identity_state_hash != target.identity_state_hash
        for item in observed_bindings
    ):
        refuse(ActivationReasonCode.IDENTITY_STATE_BINDING_MISMATCH)
    if any(
        item.constitution_version != target.constitution_version
        or item.constitution_hash != target.constitution_hash
        for item in observed_bindings
    ):
        refuse(ActivationReasonCode.CONSTITUTION_BINDING_MISMATCH)
    if any(item.owner_id != target.owner_id for item in observed_bindings):
        refuse(ActivationReasonCode.OWNER_BINDING_MISMATCH)

    runtime = evidence.runtime_evidence
    if runtime.runtime_status != "ACTIVE":
        refuse(ActivationReasonCode.RUNTIME_STATUS_NOT_ACTIVE)
    if runtime.controller_status != "ACTIVE":
        refuse(ActivationReasonCode.CONTROLLER_STATUS_NOT_ACTIVE)
    if runtime.operational_state != "CONNECTED":
        refuse(ActivationReasonCode.OPERATIONAL_STATE_NOT_CONNECTED)
    if runtime.lifecycle != "OBSERVING":
        refuse(ActivationReasonCode.LIFECYCLE_NOT_OBSERVING)
    if not runtime.controller_authoritative:
        refuse(ActivationReasonCode.CONTROLLER_NOT_AUTHORITATIVE)
    if not runtime.controller_process_live:
        refuse(ActivationReasonCode.CONTROLLER_PROCESS_NOT_LIVE)
    if runtime.integrity_status != "VERIFIED":
        refuse(ActivationReasonCode.RUNTIME_INTEGRITY_NOT_VERIFIED)

    if evidence.emergency_stop_evidence.status != "ARMED":
        refuse(ActivationReasonCode.EMERGENCY_STOP_NOT_ARMED)

    network = evidence.network_isolation_evidence
    if network.online_observation_enabled:
        refuse(ActivationReasonCode.ONLINE_OBSERVATION_ENABLED)
    if network.network_authority != "NONE":
        refuse(ActivationReasonCode.NETWORK_AUTHORITY_PRESENT)
    if network.external_requests != "BLOCKED":
        refuse(ActivationReasonCode.EXTERNAL_REQUESTS_NOT_BLOCKED)

    store = evidence.entity_store_evidence
    if not store.durable:
        refuse(ActivationReasonCode.ENTITY_STORE_NOT_DURABLE)
    if store.integrity_status != "VERIFIED":
        refuse(ActivationReasonCode.ENTITY_STORE_INTEGRITY_NOT_VERIFIED)
    if not store.head_present:
        refuse(ActivationReasonCode.ENTITY_STORE_HEAD_MISSING)
    if store.head_operating_mode != "SHADOW":
        refuse(ActivationReasonCode.ENTITY_STORE_HEAD_NOT_SHADOW)

    loop_reason_map = {
        ActivationLoopName.PRESENCE: (
            ActivationReasonCode.PRESENCE_LOOP_NOT_LOCAL_LIVE,
            ActivationReasonCode.PRESENCE_LOOP_NOT_VALID,
            ActivationReasonCode.PRESENCE_LOOP_HEAD_BINDING_MISMATCH,
        ),
        ActivationLoopName.AWARENESS: (
            ActivationReasonCode.AWARENESS_LOOP_NOT_LOCAL_LIVE,
            ActivationReasonCode.AWARENESS_LOOP_NOT_VALID,
            ActivationReasonCode.AWARENESS_LOOP_HEAD_BINDING_MISMATCH,
        ),
        ActivationLoopName.BECOMING: (
            ActivationReasonCode.BECOMING_LOOP_NOT_LOCAL_LIVE,
            ActivationReasonCode.BECOMING_LOOP_NOT_VALID,
            ActivationReasonCode.BECOMING_LOOP_HEAD_BINDING_MISMATCH,
        ),
    }
    for loop in evidence.loop_evidence:
        mode_reason, validity_reason, head_reason = loop_reason_map[loop.loop]
        if loop.mode != "LOCAL_LIVE":
            refuse(mode_reason)
        if not loop.valid or loop.integrity_status != "VERIFIED":
            refuse(validity_reason)
        if (
            loop.entity_state_id != store.head_entity_state_id
            or loop.entity_state_hash != store.head_state_hash
        ):
            refuse(head_reason)

    acceptance = evidence.live_loop_acceptance_evidence
    if (
        acceptance.acceptance_schema_version
        not in SUPPORTED_LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSIONS
    ):
        refuse(ActivationReasonCode.LIVE_LOOP_ACCEPTANCE_SCHEMA_MISMATCH)
    if (
        not acceptance.machine_readable
        or acceptance.acceptance_basis != "MACHINE_RECORD"
    ):
        refuse(ActivationReasonCode.LIVE_LOOP_ACCEPTANCE_NOT_MACHINE_READABLE)
    if acceptance.verification_status != "VERIFIED":
        refuse(ActivationReasonCode.LIVE_LOOP_ACCEPTANCE_NOT_VERIFIED)
    if acceptance.result != "PASSED":
        refuse(ActivationReasonCode.LIVE_LOOP_ACCEPTANCE_NOT_PASSED)

    quiescence = evidence.live_loop_quiescence_evidence
    if quiescence.pending_transaction_count != 0:
        refuse(ActivationReasonCode.PENDING_LIVE_LOOP_TRANSACTION)
    if quiescence.pending_approval_count != 0:
        refuse(ActivationReasonCode.PENDING_LIVE_LOOP_APPROVAL)
    if quiescence.active_execution_count != 0:
        refuse(ActivationReasonCode.LIVE_LOOP_EXECUTION_IN_PROGRESS)

    refusal_reasons = tuple(reasons)
    passed = not refusal_reasons
    material = {
        "schema_version": ENTITY_ACTIVATION_SCHEMA_VERSION,
        "record_type": ENTITY_ACTIVATION_RECORD_TYPE,
        "evidence_bundle_id": evidence.evidence_bundle_id,
        "evidence_bundle_hash": evidence.evidence_bundle_hash,
        "subject": target,
        "entity_state_id": store.head_entity_state_id,
        "entity_state_hash": store.head_state_hash,
        "activation_references": evidence.activation_references,
        "decision": (
            ActivationDecision.VERIFIED if passed else ActivationDecision.REFUSED
        ),
        "refusal_reasons": refusal_reasons,
        "all_evidence_gates_passed": passed,
        "evidence_evaluation_only": True,
        "requires_separate_authorized_commit": True,
        "activation_performed": False,
        "authority_effect": "NONE",
        "runtime_effect": "NONE",
        "production_effect": "NONE",
        "identity_state_effect": "NONE",
        "io_effect": "NONE",
        "network_effect": "NONE",
        "static_prose_sufficient": False,
    }
    draft = EntityActivationRecord.model_construct(
        activation_record_id=f"entity_activation_record_{'0' * 64}",
        activation_record_hash="0" * 64,
        **material,
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return EntityActivationRecord(
        activation_record_id=f"entity_activation_record_{digest}",
        activation_record_hash=digest,
        **normalized,
    )


def create_entity_activation_record(
    evidence: EntityActivationEvidenceBundle,
) -> EntityActivationRecord:
    """Named factory alias for :func:`evaluate_entity_activation`."""

    return evaluate_entity_activation(evidence)


class EntityActivationEligibilityError(ValueError):
    """A verified evidence record cannot safely derive a LOCAL_LIVE state."""


def activation_basis_references(
    record: EntityActivationRecord,
    evidence: EntityActivationEvidenceBundle,
) -> tuple[str, ...]:
    """Return the exact record/runtime/acceptance bindings for entity state.

    The returned strings are identifiers and SHA-256 digests only.  They are
    not credentials and confer no authority.
    """

    runtime_reference = evidence.runtime_evidence.evidence
    acceptance_reference = evidence.live_loop_acceptance_evidence.evidence
    return (
        f"activation-record:{record.activation_record_id}@sha256:{record.activation_record_hash}",
        f"runtime-evidence:{runtime_reference.evidence_id}@sha256:{runtime_reference.evidence_hash}",
        f"live-loop-acceptance-evidence:{acceptance_reference.evidence_id}@sha256:{acceptance_reference.evidence_hash}",
    )


def build_first_local_live_entity_state(
    current: SE6EntityState,
    *,
    activation_record: EntityActivationRecord,
    activation_evidence: EntityActivationEvidenceBundle,
    expected_state_version: int,
    event_head_id: str,
    event_sequence: int,
    updated_at_utc: datetime,
    lifecycle: LifecycleView,
    shared_metabolism: SharedMetabolismSnapshot,
    continuation: EntityContinuationState | None = None,
) -> SE6EntityState:
    """Purely derive the first LOCAL_LIVE state from exact verified evidence.

    The caller remains responsible for a separately authorized compare-and-
    swap commit.  This helper performs no persistence, runtime activation,
    owner action, approval consumption, network access, or IdentityState
    mutation.
    """

    if not isinstance(current, SE6EntityState):
        raise TypeError("current must be an SE6EntityState")
    if not isinstance(activation_record, EntityActivationRecord):
        raise TypeError("activation_record must be an EntityActivationRecord")
    if not isinstance(activation_evidence, EntityActivationEvidenceBundle):
        raise TypeError(
            "activation_evidence must be an EntityActivationEvidenceBundle"
        )

    recomputed = evaluate_entity_activation(activation_evidence)
    if recomputed != activation_record:
        raise EntityActivationEligibilityError(
            "activation record does not exactly match the supplied evidence"
        )
    if (
        activation_record.decision is not ActivationDecision.VERIFIED
        or not activation_record.all_evidence_gates_passed
    ):
        raise EntityActivationEligibilityError(
            "a REFUSED activation record cannot derive LOCAL_LIVE state"
        )
    if current.operating_mode is not EntityOperatingMode.SHADOW:
        raise EntityActivationEligibilityError(
            "the first LOCAL_LIVE state requires a SHADOW predecessor"
        )

    subject = activation_record.subject
    identity = current.identity
    if (
        identity.instance_id != subject.instance_id
        or identity.identity_state_id != subject.identity_state_id
        or identity.identity_state_hash != subject.identity_state_hash
        or identity.constitution_version != subject.constitution_version
        or identity.constitution_hash != subject.constitution_hash
        or identity.owner_identity_reference != subject.owner_id
    ):
        raise EntityActivationEligibilityError(
            "entity identity does not match the verified activation subject"
        )
    if (
        current.entity_state_id != activation_record.entity_state_id
        or current.state_hash != activation_record.entity_state_hash
    ):
        raise EntityActivationEligibilityError(
            "current entity state is not the verified durable store head"
        )

    runtime = activation_evidence.runtime_evidence
    emergency = activation_evidence.emergency_stop_evidence
    if (
        lifecycle.durable_state is not LifecycleState.OBSERVING
        or lifecycle.controller_status is not ControllerStatus.ACTIVE
        or lifecycle.operational_state is not OperationalConnectionState.CONNECTED
        or not lifecycle.controller_authoritative
        or lifecycle.emergency_stop is not EmergencyStopState.ARMED
        or lifecycle.durable_state.value != runtime.lifecycle
        or lifecycle.controller_status.value != runtime.controller_status
        or lifecycle.operational_state.value != runtime.operational_state
        or lifecycle.emergency_stop.value != emergency.status
    ):
        raise EntityActivationEligibilityError(
            "supplied lifecycle does not match verified live runtime evidence"
        )
    network = activation_evidence.network_isolation_evidence
    if (
        current.environment_access.online_observation_enabled
        != network.online_observation_enabled
        or current.environment_access.network_authority != network.network_authority
        or current.environment_access.external_requests != network.external_requests
    ):
        raise EntityActivationEligibilityError(
            "entity environment access does not match verified isolation evidence"
        )
    if shared_metabolism.pending_approval or shared_metabolism.transaction_id is not None:
        raise EntityActivationEligibilityError(
            "shared metabolism must be quiescent before LOCAL_LIVE derivation"
        )

    return activate_local_entity_state(
        current,
        expected_state_version=expected_state_version,
        event_head_id=event_head_id,
        event_sequence=event_sequence,
        updated_at_utc=updated_at_utc,
        lifecycle=lifecycle,
        shared_metabolism=shared_metabolism,
        activation_basis_references=activation_basis_references(
            activation_record, activation_evidence
        ),
        continuation=continuation,
    )


__all__ = [
    "ENTITY_ACTIVATION_RECORD_TYPE",
    "ENTITY_ACTIVATION_SCHEMA_VERSION",
    "LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSION",
    "LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSION_V2",
    "SUPPORTED_LIVE_LOOP_ACCEPTANCE_SCHEMA_VERSIONS",
    "ActivationDecision",
    "ActivationEvidenceKind",
    "ActivationEvidenceReference",
    "ActivationLoopName",
    "ActivationReasonCode",
    "ActivationSubjectBinding",
    "AuthoritativeRuntimeEvidence",
    "DurableEntityStoreEvidence",
    "EmergencyStopEvidence",
    "EntityActivationEligibilityError",
    "EntityActivationEvidenceBundle",
    "EntityActivationRecord",
    "LiveLoopAcceptanceEvidence",
    "LiveLoopQuiescenceEvidence",
    "LocalLiveLoopEvidence",
    "NetworkIsolationEvidence",
    "ProductionBindingEvidence",
    "activation_basis_references",
    "build_entity_activation_evidence_bundle",
    "build_first_local_live_entity_state",
    "create_entity_activation_record",
    "evaluate_entity_activation",
]
