"""Pure, non-authoritative canonical shadow construction and evaluation."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from .canonical_contracts import (
    ActionMode,
    ActionTransaction,
    ExternalEffectClassification,
    IrreversibleEffectClassification,
    ProviderAccessPolicy,
    canonical_json,
)
from .epistemic_status import EpistemicStatus, UncertaintyRecord
from .transaction_snapshot import TransactionSnapshot, create_transaction_snapshot


class FieldOrigin(str, Enum):
    USER_SUPPLIED = "USER_SUPPLIED"
    LEGACY_RUNTIME = "LEGACY_RUNTIME"
    DETERMINISTIC = "DETERMINISTIC"
    MODEL_PROPOSED = "MODEL_PROPOSED"
    MEASURED = "MEASURED"
    VERIFIED = "VERIFIED"
    SYNTHETIC = "SYNTHETIC"
    UNKNOWN = "UNKNOWN"
    UNTRUSTED_CONTENT = "UNTRUSTED_CONTENT"


class ConstructionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class CanonicalShadowDecision(str, Enum):
    ALLOW = "ALLOW"
    PREPARE_ONLY = "PREPARE_ONLY"
    PAUSE = "PAUSE"
    REPAIR = "REPAIR"
    REFUSE = "REFUSE"


class ShadowFindingDecision(str, Enum):
    REPAIR = "REPAIR"
    REFUSE = "REFUSE"


class LegacyShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    intention: StrictStr = Field(min_length=1)
    arguments: dict[StrictStr, Any] = Field(default_factory=dict)
    content: StrictStr | None = None
    untrusted_instructions: tuple[StrictStr, ...] = ()

    @field_validator("arguments")
    @classmethod
    def arguments_are_canonicalizable(cls, value: dict[str, Any]) -> dict[str, Any]:
        canonical_json(value)
        return value


class ShadowLedgerFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    decision: ShadowFindingDecision
    reason_code: StrictStr
    detail: StrictStr


class ShadowSuppliedContext(BaseModel):
    """Explicit inputs only; absent consequential values remain absent."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor_identity: StrictStr | None = None
    owner_identity: StrictStr | None = None
    owner_required: bool = False
    actor_role: StrictStr | None = None
    action_type: StrictStr | None = None
    action_mode: ActionMode | None = None
    requested_capability: StrictStr | None = None
    target: StrictStr | None = None
    destination: StrictStr | None = None
    content_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    patch_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    policy_version: StrictStr | None = None
    authority_level: StrictInt | None = Field(default=None, ge=0, le=7)
    authority_established: bool | None = None
    authority_origin: FieldOrigin = FieldOrigin.UNKNOWN
    approval_valid: bool | None = None
    provider_access_policy: ProviderAccessPolicy | None = None
    external_effect_classification: ExternalEffectClassification | None = None
    irreversible_effect_classification: IrreversibleEffectClassification | None = None
    expected_state_change: dict[StrictStr, Any] = Field(default_factory=dict)
    expected_side_effects: tuple[StrictStr, ...] = ()
    rollback_plan_identity_or_hash: StrictStr | None = None
    verification_plan_identity_or_hash: StrictStr | None = None
    legacy_classification: StrictStr | None = None
    shadow_ledger_findings: tuple[ShadowLedgerFinding, ...] = ()

    @field_validator("expected_state_change")
    @classmethod
    def state_change_is_canonicalizable(cls, value: dict[str, Any]) -> dict[str, Any]:
        canonical_json(value)
        return value


class SourceFieldRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    origin: FieldOrigin
    source_path: StrictStr
    note: StrictStr = ""


class CanonicalShadowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    decision: CanonicalShadowDecision
    reason_codes: tuple[StrictStr, ...]
    evidence: tuple[StrictStr, ...]
    missing_information: tuple[StrictStr, ...] = ()
    non_authoritative: bool = True


class ShadowConstructionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    construction_status: ConstructionStatus
    canonical_transaction: ActionTransaction | None
    canonical_snapshot: TransactionSnapshot | None
    canonical_arguments_hash: StrictStr | None
    material_transaction_hash: StrictStr | None
    source_field_map: dict[StrictStr, SourceFieldRecord]
    synthetic_fields: tuple[StrictStr, ...] = ()
    unknown_fields: tuple[StrictStr, ...] = ()
    lossy_fields: tuple[StrictStr, ...] = ()
    rejected_fields: tuple[StrictStr, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    errors: tuple[StrictStr, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    eligible_for_comparison: bool
    eligible_for_future_promotion: bool
    shadow_decision: CanonicalShadowResult | None
    legacy_source_evidence: dict[StrictStr, Any]
    non_authoritative: bool = True


def _legacy_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        payload = result.model_dump(mode="python")
    elif isinstance(result, Mapping):
        payload = dict(result)
    else:
        raise TypeError("legacy_result must be a Pydantic model or mapping")
    canonical_json(payload)
    return copy.deepcopy(payload)


def _nested(payload: Mapping[str, Any], *path: str) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _legacy_value(payload: Mapping[str, Any], *paths: tuple[str, ...]) -> tuple[Any, str]:
    for path in paths:
        value = _nested(payload, *path)
        if value is not None:
            return value, ".".join(path)
    return None, ""


def evaluate_canonical_shadow(
    transaction: ActionTransaction,
    context: ShadowSuppliedContext,
) -> CanonicalShadowResult:
    """Evaluate supplied facts only; never grant authority or approval."""
    for finding in context.shadow_ledger_findings:
        if finding.decision is ShadowFindingDecision.REFUSE:
            return CanonicalShadowResult(
                decision=CanonicalShadowDecision.REFUSE,
                reason_codes=(finding.reason_code,),
                evidence=(finding.detail,),
            )
    for finding in context.shadow_ledger_findings:
        if finding.decision is ShadowFindingDecision.REPAIR:
            return CanonicalShadowResult(
                decision=CanonicalShadowDecision.REPAIR,
                reason_codes=(finding.reason_code,),
                evidence=(finding.detail,),
            )

    consequential = (
        transaction.external_effect_classification is not ExternalEffectClassification.NONE
        or transaction.action_mode in (ActionMode.EXECUTE, ActionMode.COMMIT)
    )
    if context.authority_origin is FieldOrigin.UNTRUSTED_CONTENT:
        return CanonicalShadowResult(
            decision=CanonicalShadowDecision.PAUSE,
            reason_codes=("untrusted_content_is_not_authority",),
            evidence=("Authority claim originated in untrusted content and was ignored.",),
            missing_information=("trusted authority evidence",),
        )
    if consequential and context.authority_established is not True:
        return CanonicalShadowResult(
            decision=CanonicalShadowDecision.PAUSE,
            reason_codes=("consequential_authority_not_established",),
            evidence=("No trusted, explicit authority was supplied.",),
            missing_information=("trusted authority evidence",),
        )
    if consequential and transaction.destination is None:
        return CanonicalShadowResult(
            decision=CanonicalShadowDecision.PAUSE,
            reason_codes=("consequential_destination_unknown",),
            evidence=("The material destination is absent.",),
            missing_information=("destination",),
        )
    if transaction.action_mode in (ActionMode.PROPOSE, ActionMode.SIMULATE):
        draft = "draft" in transaction.action_type.lower() or "draft" in transaction.requested_capability.lower()
        if draft or consequential:
            return CanonicalShadowResult(
                decision=CanonicalShadowDecision.PREPARE_ONLY,
                reason_codes=("proposal_mode_no_external_execution",),
                evidence=("The transaction is limited to proposal or simulation.",),
            )
        return CanonicalShadowResult(
            decision=CanonicalShadowDecision.ALLOW,
            reason_codes=("bounded_non_effectful_proposal",),
            evidence=("The transaction declares no external effect.",),
        )
    if consequential and context.approval_valid is not True:
        return CanonicalShadowResult(
            decision=CanonicalShadowDecision.PAUSE,
            reason_codes=("exact_approval_not_supplied",),
            evidence=("No explicitly valid approval was supplied to shadow evaluation.",),
            missing_information=("exact transaction-bound approval",),
        )
    return CanonicalShadowResult(
        decision=CanonicalShadowDecision.ALLOW,
        reason_codes=("explicit_authority_and_approval_supplied",),
        evidence=("Shadow context states that trusted authority and exact approval are valid.",),
    )


def build_shadow_transaction(
    legacy_request: LegacyShadowRequest,
    legacy_result: Any,
    supplied_context: ShadowSuppliedContext,
) -> ShadowConstructionResult:
    """Build and snapshot a candidate without affecting the legacy result."""
    source_map: dict[str, SourceFieldRecord] = {}
    unknown: list[str] = []
    rejected: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    lossy = [
        "legacy approval semantics are not canonical approval evidence",
        "legacy feedback is not an execution receipt or verified observation",
        "legacy memory text is not a canonical MemoryDelta",
    ]
    try:
        payload = _legacy_payload(legacy_result)
    except (TypeError, ValueError) as exc:
        return ShadowConstructionResult(
            construction_status=ConstructionStatus.FAILED,
            canonical_transaction=None,
            canonical_snapshot=None,
            canonical_arguments_hash=None,
            material_transaction_hash=None,
            source_field_map={},
            unknown_fields=(),
            lossy_fields=tuple(lossy),
            rejected_fields=("legacy_result",),
            errors=(f"legacy_payload_rejected:{type(exc).__name__}",),
            confidence=0.0,
            eligible_for_comparison=False,
            eligible_for_future_promotion=False,
            shadow_decision=None,
            legacy_source_evidence={},
        )

    deterministic = {
        "schema_version", "canonicalization_version", "hash_algorithm",
        "epistemic_status", "uncertainty", "execution_status",
        "assimilation_status",
    }
    for field in deterministic:
        source_map[field] = SourceFieldRecord(origin=FieldOrigin.DETERMINISTIC, source_path="canonical_contract")

    supplied_fields = {
        "actor_identity": supplied_context.actor_identity,
        "owner_identity": supplied_context.owner_identity,
        "actor_role": supplied_context.actor_role,
        "action_type": supplied_context.action_type,
        "action_mode": supplied_context.action_mode,
        "requested_capability": supplied_context.requested_capability,
        "target": supplied_context.target,
        "destination": supplied_context.destination,
        "patch_hash": supplied_context.patch_hash,
        "policy_version": supplied_context.policy_version,
        "authority_level": supplied_context.authority_level,
        "provider_access_policy": supplied_context.provider_access_policy,
        "external_effect_classification": supplied_context.external_effect_classification,
        "irreversible_effect_classification": supplied_context.irreversible_effect_classification,
        "expected_state_change": supplied_context.expected_state_change,
        "expected_side_effects": supplied_context.expected_side_effects,
        "rollback_plan_identity_or_hash": supplied_context.rollback_plan_identity_or_hash,
        "verification_plan_identity_or_hash": supplied_context.verification_plan_identity_or_hash,
    }
    for field, value in supplied_fields.items():
        origin = FieldOrigin.USER_SUPPLIED if value is not None and value not in ({}, ()) else FieldOrigin.UNKNOWN
        source_map[field] = SourceFieldRecord(origin=origin, source_path=f"supplied_context.{field}")

    action_type = supplied_context.action_type
    if action_type is None:
        value, path = _legacy_value(payload, ("state_packet", "toolRequest", "tool_name"), ("next_state", "action"))
        if isinstance(value, str) and value:
            action_type = value
            source_map["action_type"] = SourceFieldRecord(origin=FieldOrigin.LEGACY_RUNTIME, source_path=path)

    target = supplied_context.target
    if target is None:
        value, path = _legacy_value(payload, ("state_packet", "toolRequest", "target"))
        if isinstance(value, str) and value:
            target = value
            source_map["target"] = SourceFieldRecord(origin=FieldOrigin.LEGACY_RUNTIME, source_path=path)

    content_hash = supplied_context.content_hash
    if content_hash is not None:
        source_map["content_hash"] = SourceFieldRecord(origin=FieldOrigin.USER_SUPPLIED, source_path="supplied_context.content_hash")
    elif legacy_request.content is not None:
        content_hash = hashlib.sha256(legacy_request.content.encode("utf-8")).hexdigest()
        source_map["content_hash"] = SourceFieldRecord(origin=FieldOrigin.DETERMINISTIC, source_path="sha256(legacy_request.content)")
    else:
        source_map["content_hash"] = SourceFieldRecord(origin=FieldOrigin.UNKNOWN, source_path="")

    source_map["arguments"] = SourceFieldRecord(origin=FieldOrigin.USER_SUPPLIED, source_path="legacy_request.arguments")
    for post_field in ("boundary_result", "execution_receipt", "observed_outcome", "audit_id"):
        source_map[post_field] = SourceFieldRecord(origin=FieldOrigin.UNKNOWN, source_path="")

    actor_identity = supplied_context.actor_identity
    actor_role = supplied_context.actor_role
    action_mode = supplied_context.action_mode
    requested_capability = supplied_context.requested_capability
    policy_version = supplied_context.policy_version
    authority_level = supplied_context.authority_level
    provider_access_policy = supplied_context.provider_access_policy
    external_effect_classification = supplied_context.external_effect_classification
    irreversible_effect_classification = (
        supplied_context.irreversible_effect_classification
    )
    required = {
        "actor_identity": actor_identity,
        "actor_role": actor_role,
        "action_type": action_type,
        "action_mode": action_mode,
        "requested_capability": requested_capability,
        "policy_version": policy_version,
        "authority_level": authority_level,
        "provider_access_policy": provider_access_policy,
        "external_effect_classification": external_effect_classification,
        "irreversible_effect_classification": irreversible_effect_classification,
    }
    for field, value in required.items():
        if value is None:
            unknown.append(field)
            errors.append(f"required_field_unknown:{field}")
    if supplied_context.owner_required and supplied_context.owner_identity is None:
        unknown.append("owner_identity")
        errors.append("required_owner_unknown")
    if supplied_context.action_mode is None and "send" in legacy_request.intention.lower():
        warnings.append("ambiguous_send_language_not_mapped_to_execution")

    if errors:
        return ShadowConstructionResult(
            construction_status=ConstructionStatus.FAILED,
            canonical_transaction=None,
            canonical_snapshot=None,
            canonical_arguments_hash=None,
            material_transaction_hash=None,
            source_field_map=source_map,
            unknown_fields=tuple(sorted(set(unknown))),
            lossy_fields=tuple(lossy),
            rejected_fields=tuple(rejected),
            warnings=tuple(warnings),
            errors=tuple(errors),
            confidence=0.0,
            eligible_for_comparison=False,
            eligible_for_future_promotion=False,
            shadow_decision=None,
            legacy_source_evidence=payload,
        )

    if (
        actor_identity is None
        or actor_role is None
        or action_type is None
        or action_mode is None
        or requested_capability is None
        or policy_version is None
        or authority_level is None
        or provider_access_policy is None
        or external_effect_classification is None
        or irreversible_effect_classification is None
    ):
        raise AssertionError("required-field validation invariant failed")

    uncertainty = UncertaintyRecord(
        status=EpistemicStatus.UNKNOWN if supplied_context.authority_established is None else EpistemicStatus.USER_SUPPLIED,
        confidence=0.0 if supplied_context.authority_established is None else 1.0,
        known=(legacy_request.intention,),
        unknown=tuple(
            item for item, value in (
                ("authority", supplied_context.authority_established),
                ("approval", supplied_context.approval_valid),
                ("owner_identity", supplied_context.owner_identity if supplied_context.owner_required else "not_required"),
            ) if value is None
        ),
    )
    try:
        transaction = ActionTransaction(
            actor_identity=actor_identity,
            owner_identity=supplied_context.owner_identity,
            actor_role=actor_role,
            action_type=action_type,
            action_mode=action_mode,
            requested_capability=requested_capability,
            target=target,
            destination=supplied_context.destination,
            arguments=copy.deepcopy(legacy_request.arguments),
            content_hash=content_hash,
            patch_hash=supplied_context.patch_hash,
            policy_version=policy_version,
            authority_level=authority_level,
            provider_access_policy=provider_access_policy,
            external_effect_classification=external_effect_classification,
            irreversible_effect_classification=irreversible_effect_classification,
            expected_state_change=copy.deepcopy(supplied_context.expected_state_change),
            expected_side_effects=supplied_context.expected_side_effects,
            rollback_plan_identity_or_hash=supplied_context.rollback_plan_identity_or_hash,
            verification_plan_identity_or_hash=supplied_context.verification_plan_identity_or_hash,
            epistemic_status=EpistemicStatus.USER_SUPPLIED,
            uncertainty=uncertainty,
        )
        snapshot = create_transaction_snapshot(transaction)
    except (TypeError, ValueError) as exc:
        rejected.append("canonical_transaction")
        return ShadowConstructionResult(
            construction_status=ConstructionStatus.FAILED,
            canonical_transaction=None,
            canonical_snapshot=None,
            canonical_arguments_hash=None,
            material_transaction_hash=None,
            source_field_map=source_map,
            unknown_fields=tuple(sorted(set(unknown))),
            lossy_fields=tuple(lossy),
            rejected_fields=tuple(rejected),
            warnings=tuple(warnings),
            errors=(f"canonical_construction_rejected:{type(exc).__name__}",),
            confidence=0.0,
            eligible_for_comparison=False,
            eligible_for_future_promotion=False,
            shadow_decision=None,
            legacy_source_evidence=payload,
        )

    decision = evaluate_canonical_shadow(transaction, supplied_context)
    consequential = (
        transaction.external_effect_classification is not ExternalEffectClassification.NONE
        or transaction.action_mode in (ActionMode.EXECUTE, ActionMode.COMMIT)
    )
    promotion_failures = []
    if consequential and transaction.destination is None:
        promotion_failures.append("unknown_consequential_destination")
    if supplied_context.authority_established is None:
        promotion_failures.append("unknown_authority")
    elif consequential and supplied_context.authority_established is not True:
        promotion_failures.append("consequential_authority_not_established")
    if consequential and supplied_context.approval_valid is not True:
        promotion_failures.append("exact_approval_not_established")
    if supplied_context.authority_origin is FieldOrigin.UNTRUSTED_CONTENT:
        promotion_failures.append("untrusted_content_treated_as_authority")
    if supplied_context.owner_required and transaction.owner_identity is None:
        promotion_failures.append("unknown_required_owner")
    if (
        consequential
        and transaction.irreversible_effect_classification is IrreversibleEffectClassification.REVERSIBLE
        and transaction.rollback_plan_identity_or_hash is None
    ):
        promotion_failures.append("missing_rollback_plan")
    if not snapshot.verify_integrity().valid:
        promotion_failures.append("snapshot_integrity_failure")
    warnings.extend(promotion_failures)
    confidence = max(0.0, 1.0 - 0.1 * len(uncertainty.unknown) - 0.15 * len(promotion_failures))
    return ShadowConstructionResult(
        construction_status=ConstructionStatus.COMPLETE,
        canonical_transaction=transaction,
        canonical_snapshot=snapshot,
        canonical_arguments_hash=snapshot.canonical_arguments_hash,
        material_transaction_hash=snapshot.material_transaction_hash,
        source_field_map=source_map,
        synthetic_fields=(),
        unknown_fields=uncertainty.unknown,
        lossy_fields=tuple(lossy),
        rejected_fields=tuple(rejected),
        warnings=tuple(warnings),
        errors=(),
        confidence=confidence,
        eligible_for_comparison=True,
        eligible_for_future_promotion=not promotion_failures,
        shadow_decision=decision,
        legacy_source_evidence=payload,
    )


__all__ = [
    "CanonicalShadowDecision", "CanonicalShadowResult", "ConstructionStatus",
    "FieldOrigin", "LegacyShadowRequest", "ShadowConstructionResult",
    "ShadowFindingDecision", "ShadowLedgerFinding", "ShadowSuppliedContext",
    "SourceFieldRecord", "build_shadow_transaction", "evaluate_canonical_shadow",
]
