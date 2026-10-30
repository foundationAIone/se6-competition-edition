"""Durable, Entity-bound, deny-by-default capability gateway.

A capability name describes what an adapter could do; it is not authority.
This gateway records only grants accepted by an injected external authority
verifier, rechecks the current canonical Entity lifecycle on every request,
and appends an audit decision before returning.  This contract version fixes
network authority to ``NONE`` and external requests to ``BLOCKED``.
"""

from __future__ import annotations

import ipaddress
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

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

from .canonical_contracts import canonical_sha256
from .entity_cognition import CapabilityType
from .entity_cognition_store import CognitionStoreError, EntityCognitionStore
from .entity_state import (
    ControllerStatus,
    EmergencyStopState,
    OperationalConnectionState,
)

CAPABILITY_GATEWAY_POLICY_VERSION = "se6-entity-capability-gateway-v2"

_HASH = r"^[0-9a-f]{64}$"
_ENTITY_ID = r"^instance_[0-9a-f]{64}$"
_IDENTITY_ID = r"^identity_[0-9a-f]{64}$"
_ENTITY_STATE_ID = r"^entity_state_[0-9a-f]{64}$"
_GRANT_ID = r"^capability_grant_[0-9a-f]{64}$"
_REVOCATION_ID = r"^capability_revocation_[0-9a-f]{64}$"
_REQUEST_ID = r"^capability_request_[0-9a-f]{64}$"
_DECISION_ID = r"^capability_decision_[0-9a-f]{64}$"
_AUDIT_ID = r"^capability_audit_[0-9a-f]{64}$"
_REFERENCE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$"

_NETWORK_CAPABILITIES = frozenset(
    {CapabilityType.WEB_SEARCH, CapabilityType.HTTP_READ_ALLOWLISTED}
)


class CapabilityGatewayError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CapabilityAuthoritySource(str, Enum):
    OWNER_AUTHENTICATED = "OWNER_AUTHENTICATED"
    CONSTITUTIONAL_POLICY = "CONSTITUTIONAL_POLICY"


class CapabilityAuditOperation(str, Enum):
    GRANT_RECORDED = "GRANT_RECORDED"
    REQUEST_EVALUATED = "REQUEST_EVALUATED"
    GRANT_REVOKED = "GRANT_REVOKED"


class CapabilityBudget(_Contract):
    maximum_requests: StrictInt = Field(ge=1, le=1_000_000)
    maximum_bytes: StrictInt = Field(ge=0, le=10_000_000_000)
    maximum_elapsed_ms: StrictInt = Field(ge=1, le=86_400_000)


class CapabilityRateLimit(_Contract):
    maximum_requests: StrictInt = Field(ge=1, le=100_000)
    window_seconds: StrictInt = Field(ge=1, le=86_400)


class CapabilityGrantRecord(_Contract):
    schema_version: Literal["se6-capability-grant-v1"] = (
        "se6-capability-grant-v1"
    )
    grant_id: StrictStr = Field(pattern=_GRANT_ID)
    grant_hash: StrictStr = Field(pattern=_HASH)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    capability: CapabilityType
    authority_source: CapabilityAuthoritySource
    authority_reference: StrictStr = Field(pattern=_REFERENCE)
    scopes: tuple[StrictStr, ...] = Field(min_length=1, max_length=64)
    allowed_targets: tuple[StrictStr, ...] = Field(min_length=1, max_length=256)
    budget: CapabilityBudget
    rate_limit: CapabilityRateLimit
    issued_at_utc: datetime
    expires_at_utc: datetime
    revocable: Literal[True] = True
    audit_reference: StrictStr = Field(pattern=_REFERENCE)
    credentials_visible_to_cognition: Literal[False] = False
    blanket_network: Literal[False] = False
    unrestricted_shell: Literal[False] = False
    unrestricted_filesystem: Literal[False] = False
    self_granted: Literal[False] = False

    @field_validator("issued_at_utc", "expires_at_utc")
    @classmethod
    def times_are_aware(cls, value: datetime) -> datetime:
        return _utc(value, "capability grant timestamp")

    @field_validator("scopes", "allowed_targets")
    @classmethod
    def values_are_unique_and_bounded(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("capability grant values must be unique")
        if any(not item.strip() or item != item.strip() or "*" in item for item in value):
            raise ValueError("capability grant cannot contain blank or wildcard values")
        return value

    @model_validator(mode="after")
    def grant_is_bounded_and_canonical(self) -> CapabilityGrantRecord:
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("capability grant expiry must follow issuance")
        if (
            self.capability in _NETWORK_CAPABILITIES
            and "READ_ONLY_OBSERVATION" not in self.scopes
        ):
            raise ValueError(
                "network observation grant requires READ_ONLY_OBSERVATION"
            )
        if self.capability in _NETWORK_CAPABILITIES:
            for target in self.allowed_targets:
                _normalize_host(target)
        expected = canonical_sha256(self.material_fields())
        if self.grant_hash != expected:
            raise ValueError("capability grant hash mismatch")
        if self.grant_id != f"capability_grant_{expected}":
            raise ValueError("capability grant ID mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"grant_id", "grant_hash"})


class CapabilityRevocationRecord(_Contract):
    schema_version: Literal["se6-capability-revocation-v1"] = (
        "se6-capability-revocation-v1"
    )
    revocation_id: StrictStr = Field(pattern=_REVOCATION_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    grant_id: StrictStr = Field(pattern=_GRANT_ID)
    authority_source: CapabilityAuthoritySource
    authority_reference: StrictStr = Field(pattern=_REFERENCE)
    reason: StrictStr = Field(min_length=1, max_length=1_000)
    revoked_at_utc: datetime
    self_revoked_for_expansion: Literal[False] = False
    authority_effect: Literal["REVOKE_EXACT_GRANT"] = "REVOKE_EXACT_GRANT"

    @field_validator("revoked_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "revoked_at_utc")

    @model_validator(mode="after")
    def revocation_is_canonical(self) -> CapabilityRevocationRecord:
        expected = canonical_sha256(self.material_fields())
        if self.revocation_id != f"capability_revocation_{expected}":
            raise ValueError("capability revocation ID mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"revocation_id"})


class CapabilityUseRequest(_Contract):
    schema_version: Literal["se6-capability-request-v1"] = (
        "se6-capability-request-v1"
    )
    request_id: StrictStr = Field(pattern=_REQUEST_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    grant_id: StrictStr = Field(pattern=_GRANT_ID)
    capability: CapabilityType
    target: StrictStr = Field(min_length=1, max_length=2_048)
    target_hash: StrictStr = Field(pattern=_HASH)
    requested_scopes: tuple[StrictStr, ...] = Field(min_length=1, max_length=64)
    requested_bytes: StrictInt = Field(ge=0)
    requested_elapsed_ms: StrictInt = Field(ge=0)
    requested_at_utc: datetime
    credential_reference: None = None
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("requested_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "requested_at_utc")

    @model_validator(mode="after")
    def request_is_canonical(self) -> CapabilityUseRequest:
        if len(self.requested_scopes) != len(set(self.requested_scopes)):
            raise ValueError("requested capability scopes must be unique")
        if self.target_hash != canonical_sha256(self.target):
            raise ValueError("capability request target hash mismatch")
        expected = canonical_sha256(self.material_fields())
        if self.request_id != f"capability_request_{expected}":
            raise ValueError("capability request ID mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"request_id"})


class CapabilityDecision(_Contract):
    schema_version: Literal["se6-capability-decision-v1"] = (
        "se6-capability-decision-v1"
    )
    decision_id: StrictStr = Field(pattern=_DECISION_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    request_id: StrictStr = Field(pattern=_REQUEST_ID)
    grant_id: StrictStr = Field(pattern=_GRANT_ID)
    capability: CapabilityType
    allowed: StrictBool
    reason_codes: tuple[StrictStr, ...] = Field(max_length=32)
    evaluated_at_utc: datetime
    network_authority: Literal["NONE", "EXACT_OWNER_ACTION"] = "NONE"
    external_requests: Literal["BLOCKED", "EXACT_REQUEST"] = "BLOCKED"
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("evaluated_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "evaluated_at_utc")

    @model_validator(mode="after")
    def decision_is_canonical(self) -> CapabilityDecision:
        if self.allowed != (not self.reason_codes):
            raise ValueError("capability decision and reason codes disagree")
        exact_network = self.network_authority == "EXACT_OWNER_ACTION"
        if exact_network != (self.external_requests == "EXACT_REQUEST"):
            raise ValueError("capability network authority fields disagree")
        if exact_network and (
            not self.allowed or self.capability not in _NETWORK_CAPABILITIES
        ):
            raise ValueError("exact network authority requires an allowed network request")
        expected = canonical_sha256(self.material_fields())
        if self.decision_id != f"capability_decision_{expected}":
            raise ValueError("capability decision ID mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"decision_id"})


class CapabilityAuditRecord(_Contract):
    schema_version: Literal["se6-capability-audit-v1"] = (
        "se6-capability-audit-v1"
    )
    audit_id: StrictStr = Field(pattern=_AUDIT_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    operation: CapabilityAuditOperation
    grant_id: StrictStr = Field(pattern=_GRANT_ID)
    capability: CapabilityType
    request_id: StrictStr | None = Field(default=None, pattern=_REQUEST_ID)
    decision_id: StrictStr | None = Field(default=None, pattern=_DECISION_ID)
    allowed: StrictBool
    reason_codes: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    target_hash: StrictStr | None = Field(default=None, pattern=_HASH)
    requested_bytes: StrictInt = Field(default=0, ge=0)
    requested_elapsed_ms: StrictInt = Field(default=0, ge=0)
    recorded_at_utc: datetime
    network_used: Literal[False] = False
    credential_material_recorded: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("recorded_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "recorded_at_utc")

    @model_validator(mode="after")
    def audit_is_canonical(self) -> CapabilityAuditRecord:
        if self.operation is CapabilityAuditOperation.REQUEST_EVALUATED:
            if self.request_id is None or self.decision_id is None:
                raise ValueError("request audit requires request and decision IDs")
        elif self.request_id is not None or self.decision_id is not None:
            raise ValueError("grant audit cannot claim a request decision")
        expected = canonical_sha256(self.material_fields())
        if self.audit_id != f"capability_audit_{expected}":
            raise ValueError("capability audit ID mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"audit_id"})


AuthorityVerifier = Callable[[str, CapabilityAuthoritySource], bool]
NetworkAuthorityVerifier = Callable[
    [CapabilityUseRequest, CapabilityGrantRecord, Any], bool
]


class EntityCapabilityGateway:
    """Evaluate exact capability requests against durable, external authority."""

    def __init__(
        self,
        *,
        store: EntityCognitionStore,
        authority_verifier: AuthorityVerifier | None = None,
        network_authority_verifier: NetworkAuthorityVerifier | None = None,
    ) -> None:
        if not isinstance(store, EntityCognitionStore):
            raise TypeError("store must be EntityCognitionStore")
        self.store = store
        self._authority_verifier = authority_verifier
        self._network_authority_verifier = network_authority_verifier

    def record_grant(
        self,
        grant: CapabilityGrantRecord,
        *,
        accepted_ancestor_entity_state_id: str | None = None,
    ) -> CapabilityGrantRecord:
        self._require_external_authority(
            grant.authority_reference, grant.authority_source
        )
        if any(item.grant_id == grant.grant_id for item in self.grants()):
            raise CapabilityGatewayError("CAPABILITY_GRANT_REPLAY_REJECTED")
        binding = self.store.binding()
        if (
            grant.entity_id != binding.entity_id
            or grant.identity_state_id != binding.current_identity_state_id
        ):
            raise CapabilityGatewayError("CAPABILITY_GRANT_ENTITY_BINDING_MISMATCH")
        if grant.entity_state_id != binding.current_entity_state_id:
            lineage = self.store.entity_store.state_receipt_lineage_read_only()
            anchors = tuple(
                item
                for item in lineage.states
                if item.entity_state_id == grant.entity_state_id
            )
            if (
                accepted_ancestor_entity_state_id != grant.entity_state_id
                or grant.capability not in _NETWORK_CAPABILITIES
                or "READ_ONLY_OBSERVATION" not in grant.scopes
                or len(anchors) != 1
                or anchors[0].identity.instance_id != grant.entity_id
                or anchors[0].identity.identity_state_id
                != grant.identity_state_id
                or lineage.states[-1].identity.instance_id
                != grant.entity_id
                or lineage.states[-1].identity.identity_state_id
                != grant.identity_state_id
            ):
                raise CapabilityGatewayError(
                    "CAPABILITY_GRANT_ENTITY_BINDING_MISMATCH"
                )
        audit = self._create_audit(
            operation=CapabilityAuditOperation.GRANT_RECORDED,
            grant=grant,
            request=None,
            decision=None,
            allowed=True,
            reason_codes=(),
            recorded_at_utc=grant.issued_at_utc,
            binding=binding,
        )
        self.store.append_raw_records(
            (
                (
                    "CAPABILITY_GRANT",
                    grant.grant_id,
                    grant,
                    grant.issued_at_utc,
                    None,
                ),
                (
                    "CAPABILITY_AUDIT",
                    audit.audit_id,
                    audit,
                    audit.recorded_at_utc,
                    None,
                ),
            ),
            accepted_ancestor_entity_state_id=(
                accepted_ancestor_entity_state_id
                if grant.entity_state_id != binding.current_entity_state_id
                else None
            ),
        )
        return grant

    def record_revocation(
        self, revocation: CapabilityRevocationRecord
    ) -> CapabilityRevocationRecord:
        self._require_external_authority(
            revocation.authority_reference, revocation.authority_source
        )
        grant = self._grant(revocation.grant_id)
        if grant is None:
            raise CapabilityGatewayError("CAPABILITY_GRANT_NOT_FOUND")
        if (
            revocation.entity_id != grant.entity_id
            or revocation.identity_state_id != grant.identity_state_id
            or revocation.entity_state_id
            != self.store.binding().current_entity_state_id
        ):
            raise CapabilityGatewayError("CAPABILITY_REVOCATION_BINDING_MISMATCH")
        if any(
            item.grant_id == revocation.grant_id for item in self.revocations()
        ):
            raise CapabilityGatewayError("CAPABILITY_GRANT_ALREADY_REVOKED")
        audit = self._create_audit(
            operation=CapabilityAuditOperation.GRANT_REVOKED,
            grant=grant,
            request=None,
            decision=None,
            allowed=False,
            reason_codes=("CAPABILITY_GRANT_REVOKED",),
            recorded_at_utc=revocation.revoked_at_utc,
        )
        self.store.append_raw_records(
            (
                (
                    "CAPABILITY_REVOCATION",
                    revocation.revocation_id,
                    revocation,
                    revocation.revoked_at_utc,
                    None,
                ),
                (
                    "CAPABILITY_AUDIT",
                    audit.audit_id,
                    audit,
                    audit.recorded_at_utc,
                    None,
                ),
            )
        )
        return revocation

    def evaluate(self, request: CapabilityUseRequest) -> CapabilityDecision:
        grant = self._grant(request.grant_id)
        state = self.store.entity_store.reconstruct().state
        reasons: list[str] = []
        if grant is None:
            reasons.append("CAPABILITY_GRANT_NOT_FOUND")
        else:
            if request.entity_id != grant.entity_id or request.entity_id != state.identity.instance_id:
                reasons.append("CAPABILITY_ENTITY_MISMATCH")
            if (
                request.identity_state_id != state.identity.identity_state_id
                or grant.identity_state_id not in state.identity.identity_lineage
            ):
                reasons.append("CAPABILITY_IDENTITY_MISMATCH")
            if request.capability is not grant.capability:
                reasons.append("CAPABILITY_MISMATCH")
            if request.requested_at_utc < grant.issued_at_utc:
                reasons.append("CAPABILITY_GRANT_NOT_YET_VALID")
            if request.requested_at_utc >= grant.expires_at_utc:
                reasons.append("CAPABILITY_GRANT_EXPIRED")
            if not set(request.requested_scopes).issubset(grant.scopes):
                reasons.append("CAPABILITY_SCOPE_NOT_ALLOWED")
            if not _target_allowed(grant, request.target):
                reasons.append("CAPABILITY_TARGET_NOT_ALLOWED")
        if state.lifecycle.emergency_stop is not EmergencyStopState.ARMED:
            reasons.append("EMERGENCY_STOP_ACTIVE")
        if (
            state.lifecycle.controller_status is not ControllerStatus.ACTIVE
            or not state.lifecycle.controller_authoritative
            or state.lifecycle.operational_state
            is not OperationalConnectionState.CONNECTED
        ):
            reasons.append("ENTITY_RUNTIME_NOT_AUTHORITATIVE")
        exact_network_authority = False
        if request.capability in _NETWORK_CAPABILITIES:
            if grant is None or "READ_ONLY_OBSERVATION" not in grant.scopes:
                reasons.append("READ_ONLY_OBSERVATION_GRANT_REQUIRED")
            if grant is not None and self._network_authority_verifier is not None:
                try:
                    exact_network_authority = self._network_authority_verifier(
                        request, grant, state
                    ) is True
                except Exception:  # noqa: BLE001 - adapter/process boundary retains failure without leaking input or granting authority
                    exact_network_authority = False
            if not exact_network_authority:
                reasons.extend(("NETWORK_AUTHORITY_NONE", "EXTERNAL_REQUESTS_BLOCKED"))
        def build_records(
            final_reasons: tuple[str, ...], current_state: Any
        ) -> tuple[CapabilityDecision, CapabilityAuditRecord]:
            decision = _create_capability_decision(
                request=request,
                entity_id=current_state.identity.instance_id,
                identity_state_id=current_state.identity.identity_state_id,
                entity_state_id=current_state.entity_state_id,
                reason_codes=final_reasons,
                exact_network_authority=(
                    request.capability in _NETWORK_CAPABILITIES
                    and exact_network_authority
                    and not final_reasons
                ),
            )
            audit = _build_capability_audit(
                entity_id=current_state.identity.instance_id,
                identity_state_id=current_state.identity.identity_state_id,
                entity_state_id=current_state.entity_state_id,
                operation=CapabilityAuditOperation.REQUEST_EVALUATED,
                grant_id=request.grant_id,
                capability=request.capability,
                request=request,
                decision=decision,
                allowed=decision.allowed,
                reason_codes=decision.reason_codes,
                recorded_at_utc=request.requested_at_utc,
            )
            return decision, audit

        decision, _audit = self.store.append_capability_evaluation(
            grant_id=request.grant_id,
            requested_at_utc=request.requested_at_utc,
            requested_bytes=request.requested_bytes,
            requested_elapsed_ms=request.requested_elapsed_ms,
            maximum_requests=(grant.budget.maximum_requests if grant else None),
            maximum_bytes=(grant.budget.maximum_bytes if grant else None),
            maximum_elapsed_ms=(
                grant.budget.maximum_elapsed_ms if grant else None
            ),
            rate_limit_requests=(
                grant.rate_limit.maximum_requests if grant else None
            ),
            rate_window_seconds=(grant.rate_limit.window_seconds if grant else None),
            base_reason_codes=tuple(dict.fromkeys(reasons)),
            record_factory=build_records,
        )
        if not isinstance(decision, CapabilityDecision):
            raise CapabilityGatewayError("CAPABILITY_DECISION_COMMIT_INVALID")
        return decision

    def consume_prevalidated_exact_request(
        self,
        *,
        grant: CapabilityGrantRecord,
        request: CapabilityUseRequest,
        current_state: Any,
        accepted_ancestor_entity_state_id: str,
        minimum_state_version: int,
        expected_binding_id: str,
        evaluated_at_utc: datetime,
    ) -> CapabilityDecision:
        """Atomically record one fully pre-audited exact network use."""

        at = _utc(evaluated_at_utc, "evaluated_at_utc")
        self._require_external_authority(
            grant.authority_reference, grant.authority_source
        )
        reasons: list[str] = []
        if (
            grant.entity_id != current_state.identity.instance_id
            or request.entity_id != grant.entity_id
        ):
            reasons.append("CAPABILITY_ENTITY_MISMATCH")
        if (
            request.identity_state_id != grant.identity_state_id
            or grant.identity_state_id
            != current_state.identity.identity_state_id
            or grant.identity_state_id
            not in current_state.identity.identity_lineage
        ):
            reasons.append("CAPABILITY_IDENTITY_MISMATCH")
        if (
            grant.entity_state_id != accepted_ancestor_entity_state_id
            or current_state.state_version < minimum_state_version
        ):
            reasons.append("CAPABILITY_ENTITY_ANCESTRY_MISMATCH")
        if (
            request.grant_id != grant.grant_id
            or request.capability is not grant.capability
            or request.requested_at_utc != grant.issued_at_utc
        ):
            reasons.append("CAPABILITY_REQUEST_BINDING_MISMATCH")
        if not set(request.requested_scopes).issubset(grant.scopes):
            reasons.append("CAPABILITY_SCOPE_NOT_ALLOWED")
        if not _target_allowed(grant, request.target):
            reasons.append("CAPABILITY_TARGET_NOT_ALLOWED")
        if at < grant.issued_at_utc:
            reasons.append("CAPABILITY_GRANT_NOT_YET_VALID")
        if at >= grant.expires_at_utc:
            reasons.append("CAPABILITY_GRANT_EXPIRED")
        if current_state.lifecycle.emergency_stop is not EmergencyStopState.ARMED:
            reasons.append("EMERGENCY_STOP_ACTIVE")
        if (
            current_state.lifecycle.controller_status
            is not ControllerStatus.ACTIVE
            or not current_state.lifecycle.controller_authoritative
            or current_state.lifecycle.operational_state
            is not OperationalConnectionState.CONNECTED
        ):
            reasons.append("ENTITY_RUNTIME_NOT_AUTHORITATIVE")
        if (
            current_state.environment_access.online_observation_enabled
            or current_state.environment_access.network_authority != "NONE"
            or current_state.environment_access.external_requests != "BLOCKED"
        ):
            reasons.append("ENTITY_NETWORK_POLICY_CHANGED")
        exact_network_authority = False
        if (
            grant.capability in _NETWORK_CAPABILITIES
            and "READ_ONLY_OBSERVATION" in grant.scopes
            and self._network_authority_verifier is not None
        ):
            try:
                exact_network_authority = self._network_authority_verifier(
                    request, grant, current_state
                ) is True
            except Exception:  # noqa: BLE001 - adapter/process boundary retains failure without leaking input or granting authority
                exact_network_authority = False
        if not exact_network_authority:
            reasons.extend(("NETWORK_AUTHORITY_NONE", "EXTERNAL_REQUESTS_BLOCKED"))
        normalized_reasons = tuple(dict.fromkeys(reasons))
        if normalized_reasons:
            raise CapabilityGatewayError(normalized_reasons[0])
        decision = _create_capability_decision(
            request=request,
            entity_id=current_state.identity.instance_id,
            identity_state_id=current_state.identity.identity_state_id,
            entity_state_id=current_state.entity_state_id,
            reason_codes=(),
            exact_network_authority=True,
            evaluated_at_utc=at,
        )
        grant_audit = _build_capability_audit(
            entity_id=current_state.identity.instance_id,
            identity_state_id=current_state.identity.identity_state_id,
            entity_state_id=current_state.entity_state_id,
            operation=CapabilityAuditOperation.GRANT_RECORDED,
            grant_id=grant.grant_id,
            capability=grant.capability,
            request=None,
            decision=None,
            allowed=True,
            reason_codes=(),
            recorded_at_utc=at,
        )
        request_audit = _build_capability_audit(
            entity_id=current_state.identity.instance_id,
            identity_state_id=current_state.identity.identity_state_id,
            entity_state_id=current_state.entity_state_id,
            operation=CapabilityAuditOperation.REQUEST_EVALUATED,
            grant_id=grant.grant_id,
            capability=grant.capability,
            request=request,
            decision=decision,
            allowed=True,
            reason_codes=(),
            recorded_at_utc=at,
        )
        try:
            self.store.append_prevalidated_capability_consumption(
                grant=grant,
                grant_audit=grant_audit,
                request_audit=request_audit,
                state=current_state,
                expected_binding_id=expected_binding_id,
            )
        except CognitionStoreError as exc:
            raise CapabilityGatewayError(exc.code) from exc
        return decision

    def grants(self) -> tuple[CapabilityGrantRecord, ...]:
        return tuple(
            CapabilityGrantRecord.model_validate_json(_json(item))
            for item in self.store.raw_records("CAPABILITY_GRANT")
        )

    def revocations(self) -> tuple[CapabilityRevocationRecord, ...]:
        return tuple(
            CapabilityRevocationRecord.model_validate_json(_json(item))
            for item in self.store.raw_records("CAPABILITY_REVOCATION")
        )

    def audit_records(self) -> tuple[CapabilityAuditRecord, ...]:
        return tuple(
            CapabilityAuditRecord.model_validate_json(_json(item))
            for item in self.store.raw_records("CAPABILITY_AUDIT")
        )

    def _grant(self, grant_id: str) -> CapabilityGrantRecord | None:
        return next((item for item in self.grants() if item.grant_id == grant_id), None)

    def _require_external_authority(
        self, reference: str, source: CapabilityAuthoritySource
    ) -> None:
        if self._authority_verifier is None:
            raise CapabilityGatewayError("CAPABILITY_AUTHORITY_VERIFIER_UNAVAILABLE")
        try:
            verified = self._authority_verifier(reference, source)
        except Exception as exc:
            raise CapabilityGatewayError("CAPABILITY_AUTHORITY_VERIFICATION_FAILED") from exc
        if verified is not True:
            raise CapabilityGatewayError("CAPABILITY_AUTHORITY_NOT_VERIFIED")

    def _create_audit(
        self,
        *,
        operation: CapabilityAuditOperation,
        grant: CapabilityGrantRecord,
        request: CapabilityUseRequest | None,
        decision: CapabilityDecision | None,
        allowed: bool,
        reason_codes: tuple[str, ...],
        recorded_at_utc: datetime,
        binding: Any | None = None,
    ) -> CapabilityAuditRecord:
        current_binding = binding or self.store.binding()
        return _build_capability_audit(
            entity_id=current_binding.entity_id,
            identity_state_id=current_binding.current_identity_state_id,
            entity_state_id=current_binding.current_entity_state_id,
            operation=operation,
            grant_id=grant.grant_id,
            capability=grant.capability,
            request=request,
            decision=decision,
            allowed=allowed,
            reason_codes=reason_codes,
            recorded_at_utc=recorded_at_utc,
        )


def create_capability_grant(
    *,
    entity_id: str,
    identity_state_id: str,
    entity_state_id: str,
    capability: CapabilityType,
    authority_source: CapabilityAuthoritySource,
    authority_reference: str,
    scopes: tuple[str, ...],
    allowed_targets: tuple[str, ...],
    budget: CapabilityBudget,
    rate_limit: CapabilityRateLimit,
    issued_at_utc: datetime,
    expires_at_utc: datetime,
    audit_reference: str,
) -> CapabilityGrantRecord:
    material = {
        "schema_version": "se6-capability-grant-v1",
        "entity_id": entity_id,
        "identity_state_id": identity_state_id,
        "entity_state_id": entity_state_id,
        "capability": capability,
        "authority_source": authority_source,
        "authority_reference": authority_reference,
        "scopes": scopes,
        "allowed_targets": allowed_targets,
        "budget": budget,
        "rate_limit": rate_limit,
        "issued_at_utc": _utc(issued_at_utc, "issued_at_utc"),
        "expires_at_utc": _utc(expires_at_utc, "expires_at_utc"),
        "revocable": True,
        "audit_reference": audit_reference,
        "credentials_visible_to_cognition": False,
        "blanket_network": False,
        "unrestricted_shell": False,
        "unrestricted_filesystem": False,
        "self_granted": False,
    }
    normalized = CapabilityGrantRecord.model_construct(
        grant_id=f"capability_grant_{'0' * 64}",
        grant_hash="0" * 64,
        **material,
    ).material_fields()
    digest = canonical_sha256(normalized)
    return CapabilityGrantRecord(
        grant_id=f"capability_grant_{digest}", grant_hash=digest, **material
    )


def create_capability_revocation(
    *,
    grant: CapabilityGrantRecord,
    entity_state_id: str,
    authority_source: CapabilityAuthoritySource,
    authority_reference: str,
    reason: str,
    revoked_at_utc: datetime,
) -> CapabilityRevocationRecord:
    material = {
        "schema_version": "se6-capability-revocation-v1",
        "entity_id": grant.entity_id,
        "identity_state_id": grant.identity_state_id,
        "entity_state_id": entity_state_id,
        "grant_id": grant.grant_id,
        "authority_source": authority_source,
        "authority_reference": authority_reference,
        "reason": reason,
        "revoked_at_utc": _utc(revoked_at_utc, "revoked_at_utc"),
        "self_revoked_for_expansion": False,
        "authority_effect": "REVOKE_EXACT_GRANT",
    }
    return CapabilityRevocationRecord(
        revocation_id=f"capability_revocation_{canonical_sha256(material)}",
        **material,
    )


def create_capability_request(
    *,
    grant: CapabilityGrantRecord,
    target: str,
    requested_scopes: tuple[str, ...],
    requested_bytes: int,
    requested_elapsed_ms: int,
    requested_at_utc: datetime,
) -> CapabilityUseRequest:
    material = {
        "schema_version": "se6-capability-request-v1",
        "entity_id": grant.entity_id,
        "identity_state_id": grant.identity_state_id,
        "grant_id": grant.grant_id,
        "capability": grant.capability,
        "target": target,
        "target_hash": canonical_sha256(target),
        "requested_scopes": requested_scopes,
        "requested_bytes": requested_bytes,
        "requested_elapsed_ms": requested_elapsed_ms,
        "requested_at_utc": _utc(requested_at_utc, "requested_at_utc"),
        "credential_reference": None,
        "authority_effect": "NONE",
    }
    return CapabilityUseRequest(
        request_id=f"capability_request_{canonical_sha256(material)}", **material
    )


def _create_capability_decision(
    *,
    request: CapabilityUseRequest,
    entity_id: str,
    identity_state_id: str,
    entity_state_id: str,
    reason_codes: tuple[str, ...],
    exact_network_authority: bool = False,
    evaluated_at_utc: datetime | None = None,
) -> CapabilityDecision:
    material = {
        "schema_version": "se6-capability-decision-v1",
        "entity_id": entity_id,
        "identity_state_id": identity_state_id,
        "entity_state_id": entity_state_id,
        "request_id": request.request_id,
        "grant_id": request.grant_id,
        "capability": request.capability,
        "allowed": not reason_codes,
        "reason_codes": reason_codes,
        "evaluated_at_utc": _utc(
            evaluated_at_utc or request.requested_at_utc,
            "evaluated_at_utc",
        ),
        "network_authority": (
            "EXACT_OWNER_ACTION" if exact_network_authority else "NONE"
        ),
        "external_requests": (
            "EXACT_REQUEST" if exact_network_authority else "BLOCKED"
        ),
        "authority_effect": "NONE",
    }
    normalized = CapabilityDecision.model_construct(
        decision_id=f"capability_decision_{'0' * 64}", **material
    ).material_fields()
    return CapabilityDecision(
        decision_id=f"capability_decision_{canonical_sha256(normalized)}",
        **material,
    )


def _build_capability_audit(
    *,
    entity_id: str,
    identity_state_id: str,
    entity_state_id: str,
    operation: CapabilityAuditOperation,
    grant_id: str,
    capability: CapabilityType,
    request: CapabilityUseRequest | None,
    decision: CapabilityDecision | None,
    allowed: bool,
    reason_codes: tuple[str, ...],
    recorded_at_utc: datetime,
) -> CapabilityAuditRecord:
    material = {
        "schema_version": "se6-capability-audit-v1",
        "entity_id": entity_id,
        "identity_state_id": identity_state_id,
        "entity_state_id": entity_state_id,
        "operation": operation,
        "grant_id": grant_id,
        "capability": capability,
        "request_id": request.request_id if request is not None else None,
        "decision_id": decision.decision_id if decision is not None else None,
        "allowed": allowed,
        "reason_codes": reason_codes,
        "target_hash": request.target_hash if request is not None else None,
        "requested_bytes": request.requested_bytes if request is not None else 0,
        "requested_elapsed_ms": (
            request.requested_elapsed_ms if request is not None else 0
        ),
        "recorded_at_utc": _utc(recorded_at_utc, "recorded_at_utc"),
        "network_used": False,
        "credential_material_recorded": False,
        "authority_effect": "NONE",
    }
    return CapabilityAuditRecord(
        audit_id=f"capability_audit_{canonical_sha256(material)}", **material
    )


def _target_allowed(grant: CapabilityGrantRecord, target: str) -> bool:
    if grant.capability in _NETWORK_CAPABILITIES:
        try:
            host = _host_from_target(target)
        except ValueError:
            return False
        return any(
            host == allowed or host.endswith(f".{allowed}")
            for allowed in (_normalize_host(item) for item in grant.allowed_targets)
        )
    return any(
        target == allowed or target.startswith(f"{allowed.rstrip('/')}/")
        for allowed in grant.allowed_targets
    )


def _host_from_target(target: str) -> str:
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme:
        if parsed.scheme.lower() != "https":
            raise ValueError("network target must use HTTPS")
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("network target credentials or custom port rejected")
        return _normalize_host(parsed.hostname or "")
    return _normalize_host(target)


def _normalize_host(value: str) -> str:
    host = value.strip().rstrip(".").lower()
    if not host or "/" in host or ":" in host or "@" in host:
        raise ValueError("allowed network target must be a host")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("network target host is invalid") from exc
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local network targets are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("non-public network target is not allowed")
    if "." not in host:
        raise ValueError("network target must be a qualified host")
    return host


def _json(value: Any) -> str:
    import json

    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "CAPABILITY_GATEWAY_POLICY_VERSION",
    "CapabilityAuditOperation",
    "CapabilityAuditRecord",
    "CapabilityAuthoritySource",
    "CapabilityBudget",
    "CapabilityDecision",
    "CapabilityGatewayError",
    "CapabilityGrantRecord",
    "CapabilityRateLimit",
    "CapabilityRevocationRecord",
    "CapabilityUseRequest",
    "EntityCapabilityGateway",
    "create_capability_grant",
    "create_capability_request",
    "create_capability_revocation",
]
