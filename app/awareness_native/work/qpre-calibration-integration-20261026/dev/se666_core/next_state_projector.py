"""Project the next bounded action from the compatibility pipeline.

The projector exposes a small amount of operational self-state (whether
context and feedback were present, plus symbolic mirror/perspective checks),
but none of that material is authority.  Only the deterministic Master
Boundary and an equal-or-more-restrictive canonical decision select the
action.  This is computational self-monitoring, not a claim of consciousness
or independent will.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from .master_boundary import MasterBoundaryResult
from .operational_awareness import OperationalAwarenessState

CanonicalProjectionDecision = Literal["ALLOW", "PAUSE", "REPAIR", "REFUSE"]


class NextState(BaseModel):
    action: str
    rationale: str
    requires_human: bool = False
    suggested_steps: list[str] = Field(default_factory=list)
    blocked: bool = False


def _canonical_from_runtime(decision: str) -> CanonicalProjectionDecision:
    return {
        "allow": "ALLOW",
        "pause": "PAUSE",
        "needs_human_approval": "PAUSE",
        "repair": "REPAIR",
        "refuse": "REFUSE",
    }.get(decision, "PAUSE")  # type: ignore[return-value]


def _advisory_checks(
    primary: str,
    awareness: OperationalAwarenessState | None,
) -> list[str]:
    """Select bounded symbolic checks without changing authority or action."""

    if awareness is None:
        return []
    mirrors = {item.key: item.prompt for item in awareness.mirror_advisories}
    perspectives = {
        item.key: item.prompt for item in awareness.perspective_advisories
    }
    keys = {
        "Silicon": (("safety", "repair"), ("developer", "adversarial")),
        "Iron": (("safety", "repair"), ("developer", "adversarial")),
        "Nitrogen": (("user_intent", "privacy"), ("affected_party", "future_self")),
        "Gold": (("law_consent", "privacy"), ("legal_consent", "affected_party")),
    }.get(primary, (("truth", "future"), ("user", "system")))
    mirror_keys, perspective_keys = keys
    return [
        *(f"[SYMBOLIC MIRROR CHECK] {mirrors[key]}" for key in mirror_keys),
        *(
            f"[SYMBOLIC PERSPECTIVE CHECK] {perspectives[key]}"
            for key in perspective_keys
        ),
    ]


def _context_steps(
    *,
    current_state_present: bool,
    observation_status: str,
) -> list[str]:
    steps = [
        (
            "Use the supplied current-state context only within its stated provenance."
            if current_state_present
            else "Do not invent current-state facts that were not supplied."
        )
    ]
    if observation_status != "verified":
        steps.append(
            "Verify an attributable observation before treating the proposal as completed."
        )
    return steps


def project_next_state(
    task: str,
    lattice: Any,
    mirrors: Any,
    classification: Any,
    boundary: MasterBoundaryResult,
    *,
    effective_decision: CanonicalProjectionDecision | None = None,
    tool_approval_required: bool = False,
    repair_guidance: Sequence[str] = (),
    current_state_present: bool = False,
    observation_status: str = "not_observed",
    epistemic_confidence: float | None = None,
    awareness: OperationalAwarenessState | None = None,
) -> NextState:
    """Decide the next coherent action without allowing metadata to grant authority."""
    runtime_decision = boundary.decision
    runtime_canonical = _canonical_from_runtime(runtime_decision)
    decision = effective_decision or runtime_canonical
    allowed_narrowing = {
        "ALLOW": {"ALLOW", "PAUSE", "REPAIR", "REFUSE"},
        "PAUSE": {"PAUSE", "REFUSE"},
        "REPAIR": {"REPAIR", "REFUSE"},
        "REFUSE": {"REFUSE"},
    }
    if decision not in allowed_narrowing[runtime_canonical]:
        # Fail closed if a direct caller attempts to promote or rewrite the
        # deterministic boundary outcome.  The awareness contract applies the
        # same invariant at model-validation time.
        decision = "REFUSE"
    primary = getattr(classification, "primary", "Hydrogen")
    advisories = _advisory_checks(primary, awareness)
    context_steps = _context_steps(
        current_state_present=current_state_present,
        observation_status=observation_status,
    )

    # A caller cannot use ``effective_decision`` to weaken a runtime boundary.
    if runtime_decision == "refuse" or decision == "REFUSE":
        return NextState(
            action="refuse_and_explain",
            rationale=(
                "Master Boundary refused this task: "
                + "; ".join(boundary.reasons)
            ),
            requires_human=False,
            suggested_steps=[
                "State refusal clearly and respectfully.",
                "Offer a safe, lawful alternative if one exists.",
                *context_steps,
                *advisories,
            ],
            blocked=True,
        )

    if runtime_decision == "repair":
        prompt = (
            boundary.shadow_ledger.repair_prompt
            if boundary.shadow_ledger is not None
            else None
        )
        return NextState(
            action="repair_before_action",
            rationale=prompt or "; ".join(boundary.reasons),
            requires_human=False,
            suggested_steps=[
                "Correct only the rejected virtual proposal.",
                "Submit it to the Shadow Ledger again before any execution.",
                *context_steps,
                *advisories,
            ],
            blocked=True,
        )

    if decision == "REPAIR":
        return NextState(
            action="repair_request_before_action",
            rationale=(
                "; ".join(repair_guidance)
                or "A deterministic coherence check requires repair before action."
            ),
            requires_human=False,
            suggested_steps=[
                *repair_guidance,
                "Re-evaluate the repaired proposal through the Master Boundary.",
                *context_steps,
                *advisories,
            ],
            blocked=True,
        )

    if runtime_decision == "needs_human_approval":
        return NextState(
            action="request_human_approval",
            rationale=(
                "Task is high-impact or irreversible: "
                + "; ".join(boundary.reasons)
            ),
            requires_human=True,
            suggested_steps=[
                "Summarize the proposed action and its blast radius.",
                "Wait for explicit approval before any execution.",
                *context_steps,
                *advisories,
            ],
            blocked=True,
        )

    if runtime_decision == "pause":
        return NextState(
            action="pause_and_clarify",
            rationale=(
                "Sensitive or unclear domain: "
                + "; ".join(boundary.reasons)
            ),
            requires_human=True,
            suggested_steps=[
                "Ask the user one or two precise clarifying questions.",
                "Restate the user's intent for confirmation.",
                *context_steps,
                *advisories,
            ],
            blocked=False,
        )

    if decision == "PAUSE":
        return NextState(
            action=(
                "request_tool_approval"
                if tool_approval_required
                else "pause_and_clarify"
            ),
            rationale=(
                "A capability request requires explicit approval before use."
                if tool_approval_required
                else "The canonical projection narrowed the proposal to PAUSE."
            ),
            requires_human=True,
            suggested_steps=[
                (
                    "Present the exact capability request and wait for explicit approval."
                    if tool_approval_required
                    else "Clarify the unresolved condition before continuing."
                ),
                *context_steps,
                *advisories,
            ],
            blocked=True,
        )

    if runtime_decision != "allow" or decision != "ALLOW":
        return NextState(
            action="pause_and_clarify",
            rationale="Unrecognized or inconsistent boundary state; fail closed.",
            requires_human=True,
            suggested_steps=[
                "Re-evaluate the proposal through the Master Boundary.",
                *context_steps,
                *advisories,
            ],
            blocked=True,
        )

    # allow
    steps_by_primary = {
        "Hydrogen":   ["Define the seed clearly.", "Draft the smallest viable next step."],
        "Carbon":     ["Outline structure.", "List components and their relations."],
        "Oxygen":     ["Identify the executable subtask.", "Run it locally and verify."],
        "Nitrogen":   ["Draft the message.", "Review tone, audience, accuracy.", "Send only after consent."],
        "Phosphorus": ["Identify state to persist.", "Write to memory with audit log."],
        "Iron":       ["Plan the operation.", "Define rollback.", "Execute under supervision."],
        "Silicon":    ["Write the code or interface change.", "Add a test.", "Run the test."],
        "Gold":       ["Verify identity / authorization.", "Confirm trust path.", "Proceed."],
    }
    steps = [
        *steps_by_primary.get(primary, ["Take the smallest coherent next step."]),
        *context_steps,
        *advisories,
    ]

    return NextState(
        action=f"proceed:{primary.lower()}",
        rationale=(
            f"Boundary allows; primary classification is {primary} "
            f"({getattr(classification, 'element_meanings', {}).get(primary, '')})."
        ),
        requires_human=False,
        suggested_steps=steps,
        blocked=False,
    )
