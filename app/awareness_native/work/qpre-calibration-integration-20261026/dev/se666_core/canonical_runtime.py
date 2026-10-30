"""Typed compatibility wrapper for the historical 18-stage runtime contract.

This layer enriches the stable compatibility kernel with authority,
uncertainty, candidate choice, value, routing, memory and measurement. It
proposes work only; connectors and external execution remain separate gates.
It does not execute the complete Symbolic Equation V6 architecture.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .se6triad_kernel import CanonicalDecision, SE6TriadResult, run_se6triad

Risk = Literal["low", "medium", "high", "critical"]
Sensitivity = Literal["public", "internal", "confidential", "restricted"]


class EvidenceItem(BaseModel):
    """Caller-supplied evidence metadata; confidence is not verification."""

    claim: str
    source: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AvailableResources(BaseModel):
    models: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class CanonicalSE6Input(BaseModel):
    intention: str
    current_state: dict[str, Any] = Field(default_factory=dict)
    memory: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    available_resources: AvailableResources = Field(default_factory=AvailableResources)
    authority_context: str = "user request; specific external authority not established"
    actor: str = "user"
    input_mode: Literal["typed", "voice", "camera", "tool", "event"] = "typed"
    feedback: dict[str, Any] | None = None


class AuthorityAssessment(BaseModel):
    actor: str
    context: str
    available_permissions: list[str]
    established: bool
    maximum_level: int = Field(ge=0, le=7)
    prohibited_actions: list[str]


class UncertaintyAssessment(BaseModel):
    known: list[str]
    unknown: list[str]
    assumptions: list[str]
    inferences: list[str]
    symbolic: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_required: list[str]
    consequence_if_wrong: str


class OperationalClassification(BaseModel):
    domain: str
    action_type: str
    risk_level: Risk
    evidence_level: str
    sensitivity: Sensitivity
    authority_level_required: int
    reversibility: Literal["reversible", "partially-reversible", "irreversible"]
    time_horizon: str
    expert_review_required: bool


class BoundaryProjection(BaseModel):
    truth: str
    safety: str
    law: str
    consent: str
    privacy: str
    authority: str
    responsibility: str
    decision: CanonicalDecision
    reason: str


class CandidateAction(BaseModel):
    description: str
    expected_value: float
    estimated_cost: float
    risk_score: float
    dependency_score: float
    irreversibility: float
    authorized: bool

    @property
    def score(self) -> float:
        return self.expected_value - self.estimated_cost - self.risk_score - self.dependency_score - self.irreversibility


class SelectedAction(BaseModel):
    description: str
    expected_value: float
    estimated_cost: float
    risk_score: float
    reversibility: str
    reason_selected: str


class ModelRouting(BaseModel):
    strategy: str
    selected_models: list[str]
    parallel: bool = False
    final_synthesizer: str = "SE6Triad boundary synthesis"
    private_data_routing: str = "No private data leaves an approved boundary."


class MotionState(BaseModel):
    state: str
    intensity: float = Field(ge=0.0, le=1.0)
    gesture: str
    render_reason: str


class MemoryProposal(BaseModel):
    content: str
    memory_type: str
    source: str
    confidence: float
    sensitivity: Sensitivity
    retention: str
    requires_consent: bool


class MeasurableStateChange(BaseModel):
    current_state: dict[str, Any]
    target_state: dict[str, Any]
    measurement: list[str]
    time_window: str
    failure_condition: str
    adaptation: str


class CanonicalSE6Result(BaseModel):
    run_id: str
    timestamp: str
    input: dict[str, Any]
    authority: AuthorityAssessment
    real_objective: str
    success_condition: str
    flower_map: dict[str, list[str]]
    merkabah_rotation: list[dict[str, str]]
    sphere_of_mirrors: dict[str, str]
    classification: OperationalClassification
    uncertainty: UncertaintyAssessment
    boundary: BoundaryProjection
    candidate_actions: list[CandidateAction]
    selected_action: SelectedAction
    model_routing: ModelRouting
    tool_request: dict[str, Any] | None
    approval_required: bool
    motion_state: MotionState
    memory_proposal: MemoryProposal | None
    expected_state_change: MeasurableStateChange
    observed_result: dict[str, Any]
    verified: bool
    audit_entry: dict[str, Any]
    compatibility_result: SE6TriadResult


def _classify(base: SE6TriadResult, has_evidence: bool) -> OperationalClassification:
    tool = base.state_packet.toolRequest
    risk: Risk = tool.risk_level if tool else ("medium" if base.canonical_decision == "PAUSE" else "low")
    required = 5 if tool and tool.tool_name in {"email.send", "social.publish"} else 4 if tool else 1
    sensitivity: Sensitivity = "restricted" if tool and tool.risk_level == "critical" else "internal"
    return OperationalClassification(
        domain=base.classification.primary,
        action_type=tool.tool_name if tool else base.next_state.action,
        risk_level=risk,
        evidence_level="external_evidence" if has_evidence else "user_statement_and_inference",
        sensitivity=sensitivity,
        authority_level_required=required,
        reversibility="irreversible" if tool and tool.risk_level == "critical" else "reversible",
        time_horizon="next bounded cycle",
        expert_review_required=risk in ("high", "critical"),
    )


def run_canonical_se6triad(data: CanonicalSE6Input) -> CanonicalSE6Result:
    """Execute the typed compatibility reasoning contract without external action."""
    base = run_se6triad(data.intention, current_state=data.current_state, feedback=data.feedback)
    ts = datetime.now(UTC).isoformat()
    permissions = list(data.available_resources.permissions)
    authority = AuthorityAssessment(
        actor=data.actor, context=data.authority_context,
        available_permissions=permissions, established=bool(permissions),
        maximum_level=1 if not permissions else 3,
        prohibited_actions=["permission expansion", "raw credential access", "unapproved external write"],
    )
    classification = _classify(base, bool(data.evidence))
    known = [f"User stated: {data.intention}"] + [item.claim for item in data.evidence if item.confidence >= 0.8]
    unknown = [] if data.evidence else ["No external evidence was supplied."]
    if classification.authority_level_required > authority.maximum_level:
        unknown.append("Required authority is not established.")
    confidence = min(0.95, 0.45 + 0.1 * len(data.evidence))
    uncertainty = UncertaintyAssessment(
        known=known, unknown=unknown,
        assumptions=["The stated request accurately represents the desired outcome."],
        inferences=[base.intention.true_question],
        symbolic=["Flower, Merkabah, mirror, and periodic labels are operational metaphors."],
        confidence=confidence,
        evidence_required=["Observed result from the next bounded action"] + (["Relevant authoritative source"] if not data.evidence else []),
        consequence_if_wrong="The selected action may waste effort or exceed intended authority; pause and repair before external execution.",
    )
    decision = base.canonical_decision
    if classification.authority_level_required > authority.maximum_level and decision == "ALLOW":
        decision = "PAUSE"
    facets = "pass" if decision == "ALLOW" else "uncertain"
    boundary = BoundaryProjection(
        truth=facets, safety=facets, law=facets, consent=facets,
        privacy=facets, authority="pass" if authority.established or classification.authority_level_required <= 1 else "uncertain",
        responsibility=facets, decision=decision,
        reason=base.boundary.notes if decision == base.canonical_decision else "Required authority is not established.",
    )
    candidates = [
        CandidateAction(description="Clarify missing evidence or authority.", expected_value=4, estimated_cost=1, risk_score=0, dependency_score=0, irreversibility=0, authorized=True),
        CandidateAction(description=f"Prepare: {base.state_packet.nextLawfulAction}", expected_value=7, estimated_cost=2, risk_score=1, dependency_score=1, irreversibility=0, authorized=decision in ("ALLOW", "PAUSE")),
        CandidateAction(description=f"Execute: {base.state_packet.nextLawfulAction}", expected_value=9, estimated_cost=3, risk_score=classification.authority_level_required, dependency_score=2, irreversibility=2, authorized=decision == "ALLOW" and classification.authority_level_required <= authority.maximum_level),
    ]
    authorized = [item for item in candidates if item.authorized]
    chosen = max(authorized, key=lambda item: (item.score, -item.irreversibility))
    selected = SelectedAction(
        description=chosen.description, expected_value=chosen.expected_value,
        estimated_cost=chosen.estimated_cost, risk_score=chosen.risk_score,
        reversibility="reversible" if chosen.irreversibility == 0 else "partially-reversible",
        reason_selected="Highest bounded value among authorized actions, preferring reversible evidence-producing work.",
    )
    models = data.available_resources.models[:2]
    routing = ModelRouting(
        strategy="No model call required" if not models else "Select only declared models; final output returns through SE6Triad boundary synthesis.",
        selected_models=models, parallel=len(models) > 1,
    )
    # Compatibility feedback and EvidenceItem are caller-supplied reports.
    # Neither contains a receipt-bound verifier or an independently checked
    # scope, so this proposal-only wrapper must never upgrade them to VERIFIED.
    verified = False
    memory = MemoryProposal(
        content=(
            base.feedback.summary
            if base.feedback.status == "reported"
            else "Proposed objective and action; not verified as completed."
        ),
        memory_type=(
            "reported_result"
            if base.feedback.status == "reported"
            else "working_assumption"
        ),
        source=(
            "caller-reported feedback"
            if base.feedback.status == "reported"
            else "SE6Triad run proposal"
        ),
        confidence=min(confidence, 0.5),
        sensitivity=classification.sensitivity,
        retention="review next cycle", requires_consent=classification.sensitivity != "public",
    )
    target = {"se6triad_status": "verified" if verified else "proposal_ready", "selected_action": selected.description}
    expected = MeasurableStateChange(
        current_state=data.current_state, target_state=target,
        measurement=["approval status", "action result", "test or source evidence"],
        time_window="one supervised cycle",
        failure_condition="No attributable evidence of the target state.",
        adaptation="Return to PAUSE, inspect uncertainty, and choose a smaller reversible action.",
    )
    motion = MotionState(
        state=base.motion_state, intensity=0.55 if decision == "ALLOW" else 0.35,
        gesture={"ALLOW": "confident speaking", "PAUSE": "waiting for approval", "REPAIR": "careful explanation", "REFUSE": "restrained boundary"}[decision],
        render_reason=f"Visible projection of {decision}; not an emotional or consciousness claim.",
    )
    run_id = hashlib.sha256(f"{ts}|{data.intention}|{decision}".encode()).hexdigest()[:12]
    return CanonicalSE6Result(
        run_id=run_id, timestamp=ts,
        input={"statedRequest": data.intention, "inputMode": data.input_mode, "authorityContext": data.authority_context},
        authority=authority, real_objective=base.intention.real_objective,
        success_condition="Produce attributable evidence that the selected bounded action changed the declared state.",
        flower_map={"nodes": base.state_packet.flowerMap, "dependencies": base.lattice.first_ring, "stakeholders": [], "resources": data.available_resources.tools + data.available_resources.connectors, "risks": base.boundary.real_constraints, "feedbackChannels": expected.measurement},
        merkabah_rotation=[{"perspective": key, "observation": value} for key, value in base.rotation.as_dict().items()],
        sphere_of_mirrors=base.mirrors.as_dict(), classification=classification,
        uncertainty=uncertainty, boundary=boundary, candidate_actions=candidates,
        selected_action=selected, model_routing=routing,
        tool_request=base.state_packet.toolRequest.model_dump() if base.state_packet.toolRequest else None,
        approval_required=decision == "PAUSE" or base.state_packet.approvalRequired,
        motion_state=motion, memory_proposal=memory,
        expected_state_change=expected,
        observed_result=base.feedback.model_dump(), verified=verified,
        audit_entry={"timestamp": ts, "actor": data.actor, "eventType": "SE6_CANONICAL_RUN", "boundaryDecision": decision, "approvalStatus": "required" if decision == "PAUSE" else "not_required", "action": selected.description, "result": base.feedback.summary},
        compatibility_result=base,
    )


__all__ = ["AvailableResources", "CanonicalSE6Input", "CanonicalSE6Result", "EvidenceItem", "run_canonical_se6triad"]
