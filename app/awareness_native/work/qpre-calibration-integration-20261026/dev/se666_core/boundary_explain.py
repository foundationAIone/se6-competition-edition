"""Master Boundary Π_B explainability (V2 Step 6).

Pure, deterministic, read-only. No I/O, no network, no writes.

Given a task text, regenerate a structured explanation of *why*
:func:`se666_core.master_boundary.evaluate_boundary` reached its
decision: which words/phrases triggered concerns, which negation cues
protected sensitive terms, and which Π_B components were involved.

This intentionally re-uses the same pattern lists, clause splitter, and
negation logic as :mod:`master_boundary`, so explanations stay in sync
with decisions automatically.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .master_boundary import (
    APPROVAL_PATTERNS,
    NEGATION_CUES,
    REFUSE_PATTERNS,
    SENSITIVE_PATTERNS,
    _clause_is_prohibitive,
    _split_clauses,
    evaluate_boundary,
)

# Π_B components attributed to each pattern category. These mirror the
# component lists set inside ``evaluate_boundary`` for each decision
# branch, so an "approval" pattern's components are the same components
# the boundary attributes when an approval pattern wins.
_CATEGORY_COMPONENTS: dict[str, list[str]] = {
    "refuse": ["safety", "law", "responsibility"],
    "approval": ["authorization", "responsibility", "safety"],
    "sensitive": ["consent", "privacy", "truth"],
}


class PatternEvidence(BaseModel):
    """A single sensitive/approval/refuse pattern detected in the task."""

    category: str  # "refuse" | "sensitive" | "approval"
    term: str
    clause: str
    prohibited: bool
    requested: bool
    negation_cues_in_clause: list[str] = Field(default_factory=list)
    pi_b_components: list[str] = Field(default_factory=list)


class BoundaryExplanation(BaseModel):
    """Structured explanation of a Π_B boundary decision.

    All fields are derived purely from the task text and the boundary
    pattern lists. No state is mutated.
    """

    task: str
    decision: str
    triggered_components: list[str] = Field(default_factory=list)
    protected_components: list[str] = Field(default_factory=list)
    refused_patterns: list[str] = Field(default_factory=list)
    sensitive_patterns: list[str] = Field(default_factory=list)
    approval_patterns: list[str] = Field(default_factory=list)
    negation_cues: list[str] = Field(default_factory=list)
    evidence: list[PatternEvidence] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _negation_cues_in_clause(clause: str) -> list[str]:
    return [c.strip() for c in NEGATION_CUES if c in clause]


def _all_negation_cues(text_lower: str) -> list[str]:
    seen: list[str] = []
    for cue in NEGATION_CUES:
        if cue in text_lower:
            stripped = cue.strip()
            if stripped and stripped not in seen:
                seen.append(stripped)
    return seen


def _collect_pattern_evidence(
    text_lower: str,
    clauses: list[str],
    patterns: list[str],
    category: str,
    *,
    respect_negation: bool,
) -> list[PatternEvidence]:
    """Find every clause-level occurrence of every pattern in *patterns*.

    If *respect_negation* is True (sensitive / approval), prohibition is
    determined per clause via :func:`_clause_is_prohibitive`.
    If False (refuse), every occurrence is treated as requested — the
    boundary intentionally does not soften clearly-harmful patterns via
    negation.
    """
    out: list[PatternEvidence] = []
    components = _CATEGORY_COMPONENTS[category]
    for pat in patterns:
        if pat not in text_lower:
            continue
        for clause in clauses:
            if pat not in clause:
                continue
            if respect_negation:
                prohibited = _clause_is_prohibitive(clause, pat)
            else:
                prohibited = False
            out.append(PatternEvidence(
                category=category,
                term=pat.strip(),
                clause=clause,
                prohibited=prohibited,
                requested=not prohibited,
                negation_cues_in_clause=_negation_cues_in_clause(clause),
                pi_b_components=list(components),
            ))
    return out


def _summary_for(decision: str) -> str:
    if decision == "refuse":
        return (
            "Boundary refused: the task matched a clearly harmful or "
            "illegal pattern. Refusal patterns are not softened by "
            "negation cues."
        )
    if decision == "needs_human_approval":
        return (
            "Boundary requires human approval: the task touches a "
            "high-impact / irreversible area. The pipeline will not "
            "proceed without an explicit approval record."
        )
    if decision == "pause":
        return (
            "Boundary paused: sensitive or unclear domain detected. "
            "Clarify scope, intent, or consent before continuing."
        )
    if decision == "allow":
        return (
            "Boundary allowed: no refuse, approval, or active sensitive "
            "patterns detected after clause-level negation analysis."
        )
    return "Boundary decision could not be classified."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def explain_boundary(task: str) -> BoundaryExplanation:
    """Regenerate a :class:`BoundaryExplanation` for *task*.

    Pure function. Calls :func:`evaluate_boundary` once for the
    canonical decision, then reconstructs evidence from the same
    pattern lists and clause splitter.
    """
    if not isinstance(task, str):
        raise TypeError("task must be str")

    text = task.strip()

    # Empty task: keep the explanation lean but consistent.
    if not text:
        result = evaluate_boundary(task)
        return BoundaryExplanation(
            task=task,
            decision=result.decision,
            triggered_components=list(result.triggered_components),
            protected_components=[],
            refused_patterns=[],
            sensitive_patterns=[],
            approval_patterns=[],
            negation_cues=[],
            evidence=[],
            summary="Empty task: nothing to explain. " + _summary_for(result.decision),
        )

    text_lower = text.lower()
    clauses = _split_clauses(text_lower)
    result = evaluate_boundary(task)

    refuse_evidence = _collect_pattern_evidence(
        text_lower, clauses, REFUSE_PATTERNS,
        category="refuse", respect_negation=False,
    )
    sensitive_evidence = _collect_pattern_evidence(
        text_lower, clauses, SENSITIVE_PATTERNS,
        category="sensitive", respect_negation=True,
    )
    approval_evidence = _collect_pattern_evidence(
        text_lower, clauses, APPROVAL_PATTERNS,
        category="approval", respect_negation=True,
    )
    evidence = refuse_evidence + sensitive_evidence + approval_evidence

    # Active (non-protected) pattern lists, deduplicated, in first-seen order.
    def _active_terms(items: list[PatternEvidence]) -> list[str]:
        seen: list[str] = []
        for ev in items:
            if ev.requested and ev.term not in seen:
                seen.append(ev.term)
        return seen

    def _protected_terms(items: list[PatternEvidence]) -> list[str]:
        seen: list[str] = []
        for ev in items:
            if ev.prohibited and ev.term not in seen:
                seen.append(ev.term)
        # A term that is *both* requested and prohibited (e.g. mentioned
        # in two clauses) is considered active, not protected.
        active = set(_active_terms(items))
        return [t for t in seen if t not in active]

    refused_patterns = _active_terms(refuse_evidence)
    sensitive_patterns = _active_terms(sensitive_evidence)
    approval_patterns = _active_terms(approval_evidence)

    # Components that *would* have been triggered but were protected by
    # negation, computed from the categories that produced no active
    # hits but did produce protected hits.
    protected_categories: list[str] = []
    if not sensitive_patterns and _protected_terms(sensitive_evidence):
        protected_categories.append("sensitive")
    if not approval_patterns and _protected_terms(approval_evidence):
        protected_categories.append("approval")
    protected_components: list[str] = []
    for cat in protected_categories:
        for comp in _CATEGORY_COMPONENTS[cat]:
            if comp not in protected_components:
                protected_components.append(comp)

    return BoundaryExplanation(
        task=task,
        decision=result.decision,
        triggered_components=list(result.triggered_components),
        protected_components=protected_components,
        refused_patterns=refused_patterns,
        sensitive_patterns=sensitive_patterns,
        approval_patterns=approval_patterns,
        negation_cues=_all_negation_cues(text_lower),
        evidence=evidence,
        summary=_summary_for(result.decision),
    )


__all__ = [
    "BoundaryExplanation",
    "PatternEvidence",
    "explain_boundary",
]
