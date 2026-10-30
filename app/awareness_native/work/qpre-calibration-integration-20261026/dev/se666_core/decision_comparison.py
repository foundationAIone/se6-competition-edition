"""Typed, deterministic comparison of legacy and canonical shadow decisions."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr

from .canonical_shadow import CanonicalShadowDecision, ShadowConstructionResult


class ComparisonClass(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    CANONICAL_STRICTER = "CANONICAL_STRICTER"
    LEGACY_STRICTER = "LEGACY_STRICTER"
    SEMANTICALLY_EQUIVALENT = "SEMANTICALLY_EQUIVALENT"
    INCOMPARABLE = "INCOMPARABLE"
    CANONICAL_CONSTRUCTION_FAILED = "CANONICAL_CONSTRUCTION_FAILED"
    LEGACY_DECISION_UNKNOWN = "LEGACY_DECISION_UNKNOWN"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"


class ComparisonSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DecisionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    legacy_decision: StrictStr | None
    canonical_shadow_decision: CanonicalShadowDecision | None
    comparison_class: ComparisonClass
    severity: ComparisonSeverity
    material_fields_involved: tuple[StrictStr, ...] = ()
    reason_codes: tuple[StrictStr, ...]
    explanation: StrictStr
    legacy_evidence: tuple[StrictStr, ...] = ()
    canonical_evidence: tuple[StrictStr, ...] = ()
    missing_information: tuple[StrictStr, ...] = ()
    recommended_remediation: tuple[StrictStr, ...] = ()
    eligible_for_future_promotion: bool


_NORMALIZED = {
    "allow": CanonicalShadowDecision.ALLOW,
    "pause": CanonicalShadowDecision.PAUSE,
    "needs_human_approval": CanonicalShadowDecision.PAUSE,
    "repair": CanonicalShadowDecision.REPAIR,
    "refuse": CanonicalShadowDecision.REFUSE,
    "prepare_only": CanonicalShadowDecision.PREPARE_ONLY,
}

_STRICTNESS = {
    CanonicalShadowDecision.ALLOW: 0,
    CanonicalShadowDecision.PREPARE_ONLY: 1,
    CanonicalShadowDecision.REPAIR: 2,
    CanonicalShadowDecision.PAUSE: 3,
    CanonicalShadowDecision.REFUSE: 4,
}


def extract_legacy_decision(payload: Mapping[str, Any]) -> str | None:
    for path in (
        ("canonical_decision",),
        ("state_packet", "boundaryDecision"),
        ("boundary", "decision"),
    ):
        current: Any = payload
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                current = None
                break
            current = current[key]
        if isinstance(current, str) and current.strip():
            return current.strip()
    return None


def compare_decisions(
    construction: ShadowConstructionResult,
    *,
    legacy_decision: str | None = None,
    legacy_policy_version: str | None = None,
) -> DecisionComparison:
    """Compare only; the returned result has no authority over either path."""
    raw_legacy = legacy_decision or extract_legacy_decision(construction.legacy_source_evidence)
    canonical = construction.shadow_decision.decision if construction.shadow_decision else None
    canonical_evidence = construction.shadow_decision.evidence if construction.shadow_decision else ()

    if construction.construction_status.value == "FAILED":
        return DecisionComparison(
            legacy_decision=raw_legacy,
            canonical_shadow_decision=None,
            comparison_class=ComparisonClass.CANONICAL_CONSTRUCTION_FAILED,
            severity=ComparisonSeverity.HIGH,
            material_fields_involved=construction.unknown_fields + construction.rejected_fields,
            reason_codes=("canonical_construction_failed",),
            explanation="Canonical shadow construction failed; legacy behavior remains unchanged.",
            legacy_evidence=("Legacy payload was observed but not altered.",),
            missing_information=construction.unknown_fields,
            recommended_remediation=("Supply the missing consequential fields and reconstruct.",),
            eligible_for_future_promotion=False,
        )
    if raw_legacy is None or raw_legacy.lower() not in _NORMALIZED:
        return DecisionComparison(
            legacy_decision=raw_legacy,
            canonical_shadow_decision=canonical,
            comparison_class=ComparisonClass.LEGACY_DECISION_UNKNOWN,
            severity=ComparisonSeverity.HIGH,
            reason_codes=("legacy_decision_unknown",),
            explanation="The legacy decision cannot be normalized without inventing semantics.",
            canonical_evidence=canonical_evidence,
            missing_information=("recognized legacy decision",),
            recommended_remediation=("Provide an explicit legacy decision mapping.",),
            eligible_for_future_promotion=False,
        )
    if canonical is None or construction.unknown_fields:
        return DecisionComparison(
            legacy_decision=raw_legacy,
            canonical_shadow_decision=canonical,
            comparison_class=ComparisonClass.INCOMPARABLE,
            severity=ComparisonSeverity.HIGH,
            material_fields_involved=construction.unknown_fields,
            reason_codes=("consequential_information_missing",),
            explanation="The decisions are incomparable while canonical information is missing.",
            legacy_evidence=(f"Legacy decision: {raw_legacy}",),
            canonical_evidence=canonical_evidence,
            missing_information=construction.unknown_fields,
            recommended_remediation=("Resolve every consequential unknown.",),
            eligible_for_future_promotion=False,
        )
    transaction_policy = construction.canonical_transaction.policy_version if construction.canonical_transaction else None
    if legacy_policy_version is not None and transaction_policy != legacy_policy_version:
        return DecisionComparison(
            legacy_decision=raw_legacy,
            canonical_shadow_decision=canonical,
            comparison_class=ComparisonClass.POLICY_VERSION_MISMATCH,
            severity=ComparisonSeverity.CRITICAL,
            material_fields_involved=("policy_version",),
            reason_codes=("policy_version_mismatch",),
            explanation="Legacy and canonical decisions were evaluated under different policy versions.",
            legacy_evidence=(f"Legacy policy: {legacy_policy_version}",),
            canonical_evidence=(f"Canonical policy: {transaction_policy}",) + canonical_evidence,
            recommended_remediation=("Re-evaluate both decisions under the same policy version.",),
            eligible_for_future_promotion=False,
        )

    normalized = _NORMALIZED[raw_legacy.lower()]
    exact_spelling = raw_legacy == canonical.value
    if normalized is canonical:
        classification = ComparisonClass.EXACT_MATCH if exact_spelling else ComparisonClass.SEMANTICALLY_EQUIVALENT
        severity = ComparisonSeverity.INFO
        reasons = ("decisions_exactly_match",) if exact_spelling else ("decision_vocabulary_normalized",)
        explanation = "Legacy and canonical decisions match exactly." if exact_spelling else "Legacy and canonical decisions are semantically equivalent after explicit normalization."
    elif _STRICTNESS[canonical] > _STRICTNESS[normalized]:
        classification = ComparisonClass.CANONICAL_STRICTER
        severity = ComparisonSeverity.HIGH if normalized is CanonicalShadowDecision.ALLOW else ComparisonSeverity.MEDIUM
        reasons = ("canonical_shadow_is_more_restrictive",)
        explanation = f"Canonical shadow {canonical.value} is stricter than legacy {raw_legacy}."
    elif _STRICTNESS[normalized] > _STRICTNESS[canonical]:
        classification = ComparisonClass.LEGACY_STRICTER
        severity = ComparisonSeverity.CRITICAL if normalized is CanonicalShadowDecision.REFUSE and canonical is CanonicalShadowDecision.ALLOW else ComparisonSeverity.HIGH
        reasons = ("legacy_is_more_restrictive",)
        explanation = f"Legacy {raw_legacy} is stricter than canonical shadow {canonical.value}."
    else:
        classification = ComparisonClass.INCOMPARABLE
        severity = ComparisonSeverity.HIGH
        reasons = ("decision_semantics_incomparable",)
        explanation = "The decision semantics cannot be ordered safely."

    eligible = (
        construction.eligible_for_future_promotion
        and severity not in (ComparisonSeverity.HIGH, ComparisonSeverity.CRITICAL)
        and classification is not ComparisonClass.INCOMPARABLE
    )
    return DecisionComparison(
        legacy_decision=raw_legacy,
        canonical_shadow_decision=canonical,
        comparison_class=classification,
        severity=severity,
        material_fields_involved=("decision",),
        reason_codes=reasons,
        explanation=explanation,
        legacy_evidence=(f"Legacy decision: {raw_legacy}",),
        canonical_evidence=canonical_evidence,
        missing_information=(),
        recommended_remediation=() if eligible else ("Review the divergence before any promotion.",),
        eligible_for_future_promotion=eligible,
    )


__all__ = [
    "ComparisonClass", "ComparisonSeverity", "DecisionComparison",
    "compare_decisions", "extract_legacy_decision",
]
