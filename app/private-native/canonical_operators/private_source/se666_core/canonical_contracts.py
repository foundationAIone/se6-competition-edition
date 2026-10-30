"""Pure, strict, versioned contracts for future canonical SE6 execution.

Nothing in this module executes an action, contacts a provider, accesses the
network, spawns a process, writes memory, consumes approval, or mutates files.
An :class:`ActionTransaction` is a proposal/state object only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    computed_field,
    field_validator,
    model_validator,
)

from .epistemic_status import EpistemicStatus, UncertaintyRecord

SCHEMA_VERSION = "1.0"
CANONICALIZATION_VERSION = "se6-c14n-json-v1"
HASH_ALGORITHM = "sha256"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_KEYS = {
    "api_key", "authorization", "credential", "credentials", "password",
    "passwd", "private_key", "refresh_token", "secret", "token",
    "access_token",
}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*\b", re.IGNORECASE),
)


class ActionMode(str, Enum):
    PROPOSE = "PROPOSE"
    SIMULATE = "SIMULATE"
    EXECUTE = "EXECUTE"
    COMMIT = "COMMIT"


class ProviderAccessPolicy(str, Enum):
    OFFLINE_REQUIRED = "OFFLINE_REQUIRED"
    PROVIDER_ALLOWED = "PROVIDER_ALLOWED"
    NETWORK_READ_APPROVAL_REQUIRED = "NETWORK_READ_APPROVAL_REQUIRED"
    EXTERNAL_EXECUTION_APPROVAL_REQUIRED = "EXTERNAL_EXECUTION_APPROVAL_REQUIRED"


class ExternalEffectClassification(str, Enum):
    NONE = "none"
    PROVIDER_CALL = "provider_call"
    NETWORK_READ = "network_read"
    EXTERNAL_WRITE = "external_write"
    EXTERNAL_EXECUTION = "external_execution"


class IrreversibleEffectClassification(str, Enum):
    NONE = "none"
    REVERSIBLE = "reversible"
    PARTIALLY_REVERSIBLE = "partially_reversible"
    IRREVERSIBLE = "irreversible"


class BoundaryDecision(str, Enum):
    ALLOW = "ALLOW"
    PAUSE = "PAUSE"
    REPAIR = "REPAIR"
    REFUSE = "REFUSE"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "not_executed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class AssimilationStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    PROPOSED = "proposed"
    ASSIMILATED = "assimilated"
    REJECTED = "rejected"
    REVOKED = "revoked"


class MemoryOperation(str, Enum):
    PROPOSE_ADD = "propose_add"
    PROPOSE_SUPERSEDE = "propose_supersede"
    PROPOSE_REVOKE = "propose_revoke"


class SecretReference(BaseModel):
    """Opaque identifier for a secret held outside canonical payloads."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    reference_id: StrictStr = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    provider: StrictStr = Field(min_length=1, max_length=128)

    @field_validator("reference_id", "provider")
    @classmethod
    def reference_is_not_secret_material(cls, value: str) -> str:
        if _looks_secret(value):
            raise ValueError("secret references must be opaque identifiers, not secret material")
        return value


def _looks_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)


def _canonical_node(value: Any, *, path: str = "$") -> dict[str, Any]:
    """Return a type-tagged, JSON-compatible canonical node."""
    if isinstance(value, SecretReference):
        return {
            "$type": "secret_reference",
            "provider": value.provider,
            "reference_id": value.reference_id,
        }
    if isinstance(value, BaseModel):
        model_type = f"{value.__class__.__module__}.{value.__class__.__qualname__}"
        return {
            "$type": "pydantic_model",
            "model_type": model_type,
            "value": _canonical_node(value.model_dump(mode="python"), path=path),
        }
    if value is None:
        return {"$type": "null"}
    if isinstance(value, bool):
        return {"$type": "boolean", "value": value}
    if isinstance(value, int):
        return {"$type": "integer", "value": value}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float at {path}")
        return {"$type": "float", "value": value}
    if isinstance(value, str):
        if _looks_secret(value):
            raise ValueError(f"raw secret-like value at {path}; use SecretReference")
        return {"$type": "string", "value": value}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"naive datetime at {path}; timezone is required")
        utc_value = value.astimezone(UTC)
        normalized = utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return {"$type": "datetime", "value": normalized}
    if isinstance(value, Enum):
        enum_type = f"{value.__class__.__module__}.{value.__class__.__qualname__}"
        return {"$type": "enum", "enum_type": enum_type, "value": _canonical_node(value.value, path=path)}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"object key at {path} must be a string")
            normalized_key = key.strip().lower().replace("-", "_")
            if (
                normalized_key in _SECRET_KEYS
                or normalized_key.endswith(("_password", "_secret"))
            ) and not isinstance(item, SecretReference):
                raise ValueError(
                    f"raw secret field at {path}.{key}; use SecretReference"
                )
            result[key] = _canonical_node(item, path=f"{path}.{key}")
        return {"$type": "object", "value": result}
    if isinstance(value, list):
        return {"$type": "list", "value": [_canonical_node(item, path=f"{path}[{index}]") for index, item in enumerate(value)]}
    if isinstance(value, tuple):
        return {"$type": "tuple", "value": [_canonical_node(item, path=f"{path}[{index}]") for index, item in enumerate(value)]}
    if isinstance(value, (set, frozenset)):
        encoded = [_canonical_node(item, path=f"{path}{{item}}") for item in value]
        encoded.sort(key=_dump_node)
        set_type = "frozenset" if isinstance(value, frozenset) else "set"
        return {"$type": set_type, "value": encoded}
    raise TypeError(f"unsupported canonical type at {path}: {type(value).__name__}")


def _dump_node(node: dict[str, Any]) -> str:
    return json.dumps(node, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def canonical_json(value: Any) -> str:
    """Serialize with SE6 canonicalization v1 (UTF-8 when hashed)."""
    return _dump_node(_canonical_node(value))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class CanonicalContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class BoundaryResult(CanonicalContractModel):
    transaction_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    decision: BoundaryDecision
    policy_version: StrictStr = Field(min_length=1)
    reasons: tuple[StrictStr, ...] = ()
    evaluated_at: datetime
    authority_satisfied: bool

    @field_validator("evaluated_at")
    @classmethod
    def evaluated_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value


class ExecutionReceipt(CanonicalContractModel):
    transaction_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    status: ExecutionStatus
    executor_identity: StrictStr = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    effect_summary: tuple[StrictStr, ...] = ()
    verification_references: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def chronological(self) -> ExecutionReceipt:
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("receipt datetimes must be timezone-aware")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        return self


class Observation(CanonicalContractModel):
    observed_at: datetime
    observer_identity: StrictStr = Field(min_length=1)
    status: EpistemicStatus
    summary: StrictStr
    evidence_references: tuple[StrictStr, ...] = ()
    content_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class MemoryDelta(CanonicalContractModel):
    operation: MemoryOperation
    subject_id: StrictStr = Field(min_length=1)
    proposed_content_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    supersedes_id: StrictStr | None = None
    reason: StrictStr = Field(min_length=1)
    epistemic_status: EpistemicStatus
    evidence_references: tuple[StrictStr, ...] = ()


class ActionTransaction(CanonicalContractModel):
    """Pre/post action state. Construction never executes the proposed action."""

    schema_version: StrictStr = Field(default=SCHEMA_VERSION, pattern=r"^1\.0$")
    canonicalization_version: StrictStr = Field(default=CANONICALIZATION_VERSION, pattern=r"^se6-c14n-json-v1$")
    hash_algorithm: StrictStr = Field(default=HASH_ALGORITHM, pattern=r"^sha256$")

    actor_identity: StrictStr = Field(min_length=1)
    owner_identity: StrictStr | None = None
    actor_role: StrictStr = Field(min_length=1)
    action_type: StrictStr = Field(min_length=1)
    action_mode: ActionMode
    requested_capability: StrictStr = Field(min_length=1)
    target: StrictStr | None = None
    destination: StrictStr | None = None
    arguments: dict[StrictStr, Any] = Field(default_factory=dict)
    content_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    patch_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    policy_version: StrictStr = Field(min_length=1)
    authority_level: StrictInt = Field(ge=0, le=7)
    provider_access_policy: ProviderAccessPolicy
    external_effect_classification: ExternalEffectClassification
    irreversible_effect_classification: IrreversibleEffectClassification
    expected_state_change: dict[StrictStr, Any] = Field(default_factory=dict)
    expected_side_effects: tuple[StrictStr, ...] = ()
    rollback_plan_identity_or_hash: StrictStr | None = None
    verification_plan_identity_or_hash: StrictStr | None = None
    epistemic_status: EpistemicStatus
    uncertainty: UncertaintyRecord

    # Post-decision/execution state: intentionally excluded from material hash.
    boundary_result: BoundaryResult | None = None
    execution_status: ExecutionStatus = ExecutionStatus.NOT_EXECUTED
    execution_receipt: ExecutionReceipt | None = None
    observed_outcome: tuple[Observation, ...] = ()
    assimilation_status: AssimilationStatus = AssimilationStatus.NOT_EVALUATED
    audit_id: StrictStr | None = None

    @field_validator("arguments", "expected_state_change")
    @classmethod
    def validate_canonical_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        canonical_json(value)
        return value

    @field_validator("content_hash", "patch_hash")
    @classmethod
    def lowercase_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError("hash must be lowercase SHA-256 hex")
        return value

    @model_validator(mode="after")
    def validate_material_payload(self) -> ActionTransaction:
        canonical_json(self.material_fields())
        return self

    @computed_field(return_type=str)
    @property
    def canonical_arguments_hash(self) -> str:
        return canonical_sha256(self.arguments)

    def material_fields(self) -> dict[str, Any]:
        """Return exactly the pre-execution fields bound by the material hash."""
        return {
            "schema_version": self.schema_version,
            "canonicalization_version": self.canonicalization_version,
            "hash_algorithm": self.hash_algorithm,
            "actor_identity": self.actor_identity,
            "owner_identity": self.owner_identity,
            "actor_role": self.actor_role,
            "action_type": self.action_type,
            "action_mode": self.action_mode,
            "requested_capability": self.requested_capability,
            "target": self.target,
            "destination": self.destination,
            "canonical_arguments_hash": self.canonical_arguments_hash,
            "content_hash": self.content_hash,
            "patch_hash": self.patch_hash,
            "policy_version": self.policy_version,
            "authority_level": self.authority_level,
            "provider_access_policy": self.provider_access_policy,
            "external_effect_classification": self.external_effect_classification,
            "irreversible_effect_classification": self.irreversible_effect_classification,
            "expected_state_change": self.expected_state_change,
            "expected_side_effects": self.expected_side_effects,
            "rollback_plan_identity_or_hash": self.rollback_plan_identity_or_hash,
            "verification_plan_identity_or_hash": self.verification_plan_identity_or_hash,
            "epistemic_status": self.epistemic_status,
            "uncertainty": self.uncertainty,
        }

    @computed_field(return_type=str)
    @property
    def material_transaction_hash(self) -> str:
        return canonical_sha256(self.material_fields())


class CompatibilityConversion(CanonicalContractModel):
    """Loss-aware envelope retaining the complete legacy payload."""

    source_contract: StrictStr = "SE6TriadResult"
    legacy_payload: dict[StrictStr, Any]
    canonical_transaction: ActionTransaction | None = None
    lossy: bool
    losses: tuple[StrictStr, ...]
    synthetic_or_unavailable_fields: tuple[StrictStr, ...]


_LEGACY_LOSSES = (
    "authenticated actor and owner identities are unavailable",
    "canonical capability, target, destination, and policy version are unavailable",
    "authority and approval are not bound to canonical transaction arguments",
    "legacy observations and feedback do not constitute an execution receipt",
    "legacy memory update text is not a canonical MemoryDelta",
)


def convert_legacy_result(result: Any, *, acknowledge_lossy: bool = False) -> CompatibilityConversion:
    """Retain a legacy result without fabricating a canonical transaction.

    Lossy conversion must be explicitly acknowledged.  The full legacy payload
    is preserved; canonical authority/evidence/outcomes remain unavailable.
    """
    from .se6triad_kernel import SE6TriadResult

    if not isinstance(result, SE6TriadResult):
        raise TypeError("result must be an SE6TriadResult")
    if not acknowledge_lossy:
        raise ValueError("legacy conversion is lossy; pass acknowledge_lossy=True")
    return CompatibilityConversion(
        legacy_payload=result.model_dump(mode="python"),
        canonical_transaction=None,
        lossy=True,
        losses=_LEGACY_LOSSES,
        synthetic_or_unavailable_fields=(
            "actor_identity", "owner_identity", "requested_capability",
            "policy_version", "execution_receipt", "verified_observation",
        ),
    )


__all__ = [
    "CANONICALIZATION_VERSION",
    "HASH_ALGORITHM",
    "SCHEMA_VERSION",
    "ActionMode",
    "ActionTransaction",
    "AssimilationStatus",
    "BoundaryDecision",
    "BoundaryResult",
    "CompatibilityConversion",
    "ExecutionReceipt",
    "ExecutionStatus",
    "ExternalEffectClassification",
    "IrreversibleEffectClassification",
    "MemoryDelta",
    "MemoryOperation",
    "Observation",
    "ProviderAccessPolicy",
    "SecretReference",
    "canonical_json",
    "canonical_sha256",
    "convert_legacy_result",
]
