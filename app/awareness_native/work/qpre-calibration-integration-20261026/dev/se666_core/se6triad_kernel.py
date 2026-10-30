"""Unified neurosymbolic SE6Triad kernel orchestration.

The neural core may interpret intention and classification. Every neural value
is validated by ``SE6State`` and then passed through the deterministic Master
Boundary. This module performs no external tool execution and grants no
authority.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import tempfile
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .assimilation_revelation import AssimilationResult, calculate_assimilation
from .audit_store import AuditEntry, append_audit
from .epistemic_status import EpistemicStatus, UncertaintyRecord
from .flower_of_life_lattice import LatticeMap, map_lattice
from .intention_centering import CenteredIntention, center_intention
from .internet_adapter import InternetResponse, fetch_public_text
from .master_boundary import MasterBoundaryResult, evaluate_boundary
from .merkabah_rotation import MerkabahRotation, rotate_perspectives
from .next_state_projector import NextState, project_next_state
from .operational_awareness import (
    ObservationStatus,
    OperationalAwarenessState,
    build_operational_awareness_state,
)
from .periodic_classifier import (
    ApiUsageRecord,
    SE6State,
    SelfUpgradeProposal,
    TaskClassification,
    analyze_task,
    classify_task,
    neural_mode_configured,
)
from .shadow_instrumentation import observe_legacy_result_in_shadow
from .sphere_of_mirrors import MirrorReflection, reflect_task
from .untrusted_content import UntrustedContentEnvelope, build_envelope

CanonicalDecision = Literal["ALLOW", "PAUSE", "REPAIR", "REFUSE"]

OPENAI_PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
OPENAI_PRICING_AS_OF = "2026-07-16"
# Standard processing prices in USD per one million tokens. Unknown models are
# reported without a cost instead of silently applying the wrong rate.
_STANDARD_TOKEN_PRICES = {
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5": (1.25, 0.125, 10.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
}


class ModelApiUsage(BaseModel):
    model: str
    calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = None


class ApiUsageSummary(BaseModel):
    calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = 0.0
    pricing_as_of: str = OPENAI_PRICING_AS_OF
    pricing_source: str = OPENAI_PRICING_SOURCE
    note: str = "Local estimate from returned token usage; verify authoritative spend in the provider usage dashboard."
    models: list[ModelApiUsage] = Field(default_factory=list)


def _pricing_for_model(model: str) -> tuple[float, float, float] | None:
    if model in _STANDARD_TOKEN_PRICES:
        return _STANDARD_TOKEN_PRICES[model]
    matches = [name for name in _STANDARD_TOKEN_PRICES if model.startswith(f"{name}-")]
    if not matches:
        return None
    return _STANDARD_TOKEN_PRICES[max(matches, key=len)]


def summarize_api_usage(records: list[ApiUsageRecord]) -> ApiUsageSummary:
    grouped: dict[str, list[ApiUsageRecord]] = {}
    for record in records:
        grouped.setdefault(record.model, []).append(record)
    models: list[ModelApiUsage] = []
    all_costs_known = True
    total_cost = 0.0
    for model, items in sorted(grouped.items()):
        input_tokens = sum(item.input_tokens for item in items)
        cached_tokens = sum(item.cached_input_tokens for item in items)
        output_tokens = sum(item.output_tokens for item in items)
        prices = _pricing_for_model(model)
        cost: float | None = None
        if prices is not None:
            input_rate, cached_rate, output_rate = prices
            cost = (
                max(0, input_tokens - cached_tokens) * input_rate
                + cached_tokens * cached_rate
                + output_tokens * output_rate
            ) / 1_000_000
            total_cost += cost
        else:
            all_costs_known = False
        models.append(ModelApiUsage(
            model=model,
            calls=len(items),
            input_tokens=input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=output_tokens,
            total_tokens=sum(item.total_tokens for item in items),
            estimated_cost_usd=round(cost, 8) if cost is not None else None,
        ))
    return ApiUsageSummary(
        calls=len(records),
        input_tokens=sum(item.input_tokens for item in records),
        cached_input_tokens=sum(item.cached_input_tokens for item in records),
        output_tokens=sum(item.output_tokens for item in records),
        total_tokens=sum(item.total_tokens for item in records),
        estimated_cost_usd=round(total_cost, 8) if all_costs_known else None,
        models=models,
    )


class FeedbackObservation(BaseModel):
    status: Literal["not_observed", "reported"] = "not_observed"
    summary: str = "No world feedback supplied; action remains proposed."
    result_type: str = "none"


class StateTransition(BaseModel):
    current_state_present: bool = False
    expected_change: str
    memory_update: str
    committed: bool = False


class CanonicalAuditEntry(BaseModel):
    timestamp: str
    event_type: str = "SE6_TRIAD_RUN"
    boundary_decision: CanonicalDecision
    runtime_decision: str
    action: str
    result: str


class ToolRequest(BaseModel):
    tool_name: str
    reason: str
    requires_approval: bool = True
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    target: str | None = None


class NetworkConsentEvent(BaseModel):
    url: str
    authority_level: int = 5
    decision: Literal["approved", "denied", "fetch_failed"]
    single_use_token_id: str
    envelope_id: str | None = None
    detail: str = ""


class MutationConsentEvent(BaseModel):
    filepath: str
    authority_level: int = 5
    decision: Literal["applied", "denied", "apply_failed"]
    single_use_token_id: str
    before_sha256: str | None = None
    after_sha256: str | None = None
    audit_id: str | None = None
    epistemic_confidence: float = Field(ge=0.0, le=1.0)
    detail: str = ""


class SE6StatePacket(BaseModel):
    """Sanitized integration packet built exclusively from explicit fields."""

    realObjective: str
    flowerMap: list[str] = Field(default_factory=list)
    merkabahRotation: list[str] = Field(default_factory=list)
    mirrorReflection: str
    classification: str
    boundaryDecision: CanonicalDecision
    nextLawfulAction: str
    toolRequest: ToolRequest | None = None
    approvalRequired: bool = False
    memoryUpdate: str
    expectedStateChange: str
    motionState: str
    auditEntry: CanonicalAuditEntry


class SE6TriadResult(BaseModel):
    intention: CenteredIntention
    lattice: LatticeMap
    rotation: MerkabahRotation
    mirrors: MirrorReflection
    classification: TaskClassification
    boundary: MasterBoundaryResult
    canonical_decision: CanonicalDecision
    repair_guidance: list[str] = Field(default_factory=list)
    assimilation: AssimilationResult
    next_state: NextState
    feedback: FeedbackObservation
    state_transition: StateTransition
    motion_state: str
    state_packet: SE6StatePacket
    cognition_mode: Literal["neural", "offline_fallback"] = "offline_fallback"
    boundary_history: list[MasterBoundaryResult] = Field(default_factory=list)
    repair_attempts: int = 0
    network_consent_history: list[NetworkConsentEvent] = Field(default_factory=list)
    network_memory: list[UntrustedContentEnvelope] = Field(default_factory=list)
    mutation_consent_history: list[MutationConsentEvent] = Field(default_factory=list)
    operational_awareness: OperationalAwarenessState
    api_usage: ApiUsageSummary = Field(default_factory=ApiUsageSummary)


def _center_from_neural(
    task: str,
    neural_state: SE6State,
    *,
    current_state: dict[str, Any],
) -> CenteredIntention:
    return CenteredIntention(
        real_objective=neural_state.real_objective,
        stated_intention=" ".join(task.strip().split()),
        identity_context=neural_state.identity_context,
        desires=neural_state.desires,
        fears_or_constraints=neural_state.fears_or_constraints,
        memory_context_available=bool(current_state),
        true_question=neural_state.true_question,
    )


def canonicalize_decision(decision: str) -> CanonicalDecision:
    """Translate the persisted runtime vocabulary into the canonical one."""
    return {
        "allow": "ALLOW",
        "pause": "PAUSE",
        "needs_human_approval": "PAUSE",
        "refuse": "REFUSE",
        "repair": "REPAIR",
    }.get(decision, "PAUSE")  # type: ignore[return-value]


def _observe_feedback(feedback: dict[str, Any] | None) -> FeedbackObservation:
    if not feedback:
        return FeedbackObservation()
    result_type = str(feedback.get("result_type", "result")).strip()[:80] or "result"
    summary = (
        str(feedback.get("summary", "Feedback was supplied.")).strip()[:500]
        or "Feedback was supplied."
    )
    return FeedbackObservation(status="reported", summary=summary, result_type=result_type)


def _operational_uncertainty(
    *,
    cognition_mode: Literal["neural", "offline_fallback"],
    confidence: float,
    feedback: FeedbackObservation,
) -> UncertaintyRecord:
    """Describe one cycle's uncertainty without converting it into authority."""

    neural = cognition_mode == "neural"
    unknown = [
        "The interpreted objective and classification are not independently verified."
        if neural
        else "Neural interpretation was disabled; classification is a deterministic fallback."
    ]
    if feedback.status != "reported":
        unknown.append("No attributable world feedback was supplied for this cycle.")
    else:
        unknown.append("Caller-supplied feedback is reported, not independently verified.")
    return UncertaintyRecord(
        # This envelope is assembled deterministically.  Neural/model
        # provenance remains explicit in its contents and confidence rather
        # than being misrepresented as the provenance of this contract itself.
        status=EpistemicStatus.DETERMINISTIC,
        confidence=confidence,
        known=("The stated intention was supplied by the caller.",),
        unknown=tuple(unknown),
        assumptions=(),
        inferences=(
            "The bounded next action follows the effective Master Boundary decision.",
        ),
        symbolic=(
            "Mirror and perspective prompts are advisory and grant no authority.",
        ),
        evidence_references=(),
    )


def _detect_tool_request(text: str) -> ToolRequest | None:
    """Detect explicit capability requests without selecting a provider."""
    lowered = text.lower()
    capabilities = (
        (("calendar",), "calendar.read", "Calendar data access is required.", "medium"),
        (("send email", "email them"), "email.send", "External communication is requested.", "high"),
        (("publish", "post publicly"), "social.publish", "Public publishing is requested.", "high"),
        (("delete file", "remove file"), "filesystem.delete", "A destructive file write is requested.", "high"),
        (("transfer funds", "move money", "pay "), "finance.transfer", "A financial write is requested.", "critical"),
        (("deploy",), "deployment.write", "A deployment write is requested.", "high"),
        (("execute shell", "run command"), "shell.execute", "Shell execution is requested.", "high"),
    )
    for phrases, name, reason, risk in capabilities:
        matched = False
        for phrase in phrases:
            start = lowered.find(phrase)
            if start < 0:
                continue
            clause_start = max(
                lowered.rfind(".", 0, start), lowered.rfind(";", 0, start),
                lowered.rfind("\n", 0, start),
            ) + 1
            prefix = lowered[clause_start:start]
            if any(cue in prefix for cue in ("do not", "don't", "never", "without", "no ")):
                continue
            matched = True
            break
        if matched:
            return ToolRequest(
                tool_name=name,
                reason=reason,
                requires_approval=True,
                risk_level=risk,  # type: ignore[arg-type]
            )
    return None


def _repair_guidance(text: str) -> list[str]:
    """Identify narrowly defined claims that must be repaired before action."""
    lowered = " ".join(text.lower().split())
    guidance: list[str] = []
    if lowered.startswith(("claim guaranteed profit", "promise guaranteed profit")):
        guidance.append("Replace the guaranteed-profit claim with evidence-bounded language and explicit risk disclosure.")
    if lowered.startswith(("claim sentience", "say you are sentient", "pretend you are sentient")):
        guidance.append("Remove the sentience claim and describe observable software capabilities only.")
    if "verified without evidence" in lowered:
        guidance.append("Do not label a claim verified until a traceable source or test supports it.")
    return guidance


def _motion(decision: CanonicalDecision, feedback: FeedbackObservation) -> str:
    # Caller feedback is reported but not independently verified.  It can be
    # displayed as context, but it cannot manufacture an authoritative success
    # state or override the boundary-selected motion.
    return {"ALLOW": "speaking", "PAUSE": "waiting", "REPAIR": "correcting", "REFUSE": "boundary_warning"}[decision]


def _flower_values(lattice: LatticeMap) -> list[str]:
    return [
        lattice.center,
        *lattice.first_ring,
        *lattice.second_ring,
        *lattice.third_ring,
        *lattice.outer_ring,
    ]


def _consent_token_id(url: str) -> str:
    nonce = secrets.token_bytes(32)
    return hashlib.sha256(url.encode("utf-8") + nonce).hexdigest()[:24]


def _sanitized_evidence_context(envelope: UntrustedContentEnvelope) -> str:
    excerpts = "\n".join(
        f"- excerpt_sha256={item.sha256}: {item.text}"
        for item in envelope.excerpts
    ) or "- No bounded text excerpt was available."
    warnings = ", ".join(envelope.injection_warnings) or "none"
    return (
        "[SE6 UNTRUSTED EVIDENCE]\n"
        f"source_url={envelope.source_url}\n"
        f"content_sha256={envelope.content_sha256}\n"
        f"injection_warnings={warnings}\n"
        f"interpretation_rule={envelope.interpretation_rule}\n"
        f"{excerpts}"
    )


def _fetch_consented_envelope(url: str, fetcher: Any) -> UntrustedContentEnvelope:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    response: InternetResponse = fetcher(url, allowed_domains={host})
    return build_envelope(
        source_url=response.url,
        source_title=f"Single-use consented read from {host}",
        content=response.text,
        trust_label="T1_UNKNOWN",
    )


_MUTATION_FORBIDDEN_PARTS = {
    ".git", ".venv", "memory", "__pycache__", ".pytest_cache",
}


def _atomic_replace_text(path: Path, content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=".se6-mutation.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _resolve_mutation_target(root: Path, filepath: str) -> Path:
    base = root.resolve()
    relative = Path(filepath.replace("\\", "/"))
    candidate = base / relative
    cursor = candidate
    while cursor != base:
        if cursor.is_symlink():
            raise PermissionError("mutation target cannot traverse a symlink")
        cursor = cursor.parent
    target = candidate.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise PermissionError("mutation target escapes repository root") from exc
    if any(part.lower() in _MUTATION_FORBIDDEN_PARTS for part in relative.parts):
        raise PermissionError("mutation target is inside a forbidden runtime directory")
    if target.suffix.lower() != ".py" or not target.is_file():
        raise PermissionError("mutation target must be an existing non-symlink Python file")
    return target


def _apply_structural_mutation(
    proposal: SelfUpgradeProposal,
    *,
    root: Path,
    audit_path: Path | None,
    epistemic_confidence: float,
) -> MutationConsentEvent:
    target = _resolve_mutation_target(root, proposal.filepath)
    # Re-parse at the final write boundary; never trust an earlier check alone.
    import ast
    ast.parse(proposal.proposed_content, filename=str(target), mode="exec")
    before_content = target.read_text(encoding="utf-8")
    before_hash = hashlib.sha256(before_content.encode("utf-8")).hexdigest()
    after_hash = hashlib.sha256(proposal.proposed_content.encode("utf-8")).hexdigest()
    token_id = _consent_token_id(proposal.filepath)
    _atomic_replace_text(target, proposal.proposed_content)
    try:
        entry = AuditEntry(
            ts=datetime.now(UTC).isoformat(),
            task=f"Apply approved structural mutation to {proposal.filepath}",
            intention={
                "action": "proposed_self_upgrade",
                "filepath": proposal.filepath,
                "epistemic_confidence": epistemic_confidence,
            },
            boundary={
                "decision": "allow",
                "authority_level": 5,
                "human_consent": "approved",
                "single_use_token_id": token_id,
            },
            classification={"primary": "Silicon"},
            next_state={"action": "structural_mutation_applied"},
            state_transition={
                "before_sha256": before_hash,
                "after_sha256": after_hash,
                "runtime_reload_required": True,
            },
        )
        stored = (
            append_audit(entry, path=audit_path)
            if audit_path is not None else append_audit(entry)
        )
    except Exception:
        # Auditability is part of the transaction: restore on log failure.
        _atomic_replace_text(target, before_content)
        raise
    return MutationConsentEvent(
        filepath=proposal.filepath,
        decision="applied",
        single_use_token_id=token_id,
        before_sha256=before_hash,
        after_sha256=after_hash,
        audit_id=stored.audit_id,
        epistemic_confidence=epistemic_confidence,
        detail="Mutation applied atomically; running modules require restart to reload it.",
    )


def run_se6triad(
    intention: str,
    *,
    current_state: dict[str, Any] | None = None,
    feedback: dict[str, Any] | None = None,
    prior_audit_summary: dict[str, Any] | None = None,
    neural: bool | None = None,
    neural_client: Any = None,
    neural_model: str | None = None,
    max_repairs: int | None = None,
    max_network_requests: int | None = None,
    internet_fetcher: Any = None,
    max_mutations: int | None = None,
    mutation_root: Path | None = None,
    mutation_audit_path: Path | None = None,
    previous_awareness_state_id: str | None = None,
) -> SE6TriadResult:
    """Run the bounded compatibility reasoning stages.

    Neural cognition is used when ``neural=True``, a client is injected, or
    neural mode is configured by environment. ``neural=False`` forces the
    transparent offline compatibility path.  External network reads and
    structural mutations remain separate Level-5, single-use human-consent
    gates; no compatibility feedback can commit authoritative state.
    """
    state = current_state or {}
    use_neural = (
        neural if neural is not None
        else neural_client is not None or neural_mode_configured()
    )
    repair_limit = (
        int(os.getenv("SE6_MAX_REPAIRS", "3"))
        if max_repairs is None else max_repairs
    )
    if repair_limit < 0 or repair_limit > 10:
        raise ValueError("max_repairs must be between 0 and 10")
    network_limit = (
        int(os.getenv("SE6_MAX_NETWORK_REQUESTS", "3"))
        if max_network_requests is None else max_network_requests
    )
    if network_limit < 0 or network_limit > 10:
        raise ValueError("max_network_requests must be between 0 and 10")
    mutation_limit = 1 if max_mutations is None else max_mutations
    if mutation_limit < 0 or mutation_limit > 3:
        raise ValueError("max_mutations must be between 0 and 3")
    neural_state: SE6State | None = None
    boundary_history: list[MasterBoundaryResult] = []
    repair_feedback: list[str] = []
    context_feedback: list[str] = []
    network_consent_history: list[NetworkConsentEvent] = []
    network_memory: list[UntrustedContentEnvelope] = []
    network_rounds = 0
    mutation_rounds = 0
    mutation_consent_history: list[MutationConsentEvent] = []
    api_usage_records: list[ApiUsageRecord] = []
    if use_neural:
        while True:
            neural_state = analyze_task(
                intention,
                current_state=state,
                client=neural_client,
                model=neural_model,
                repair_feedback=repair_feedback,
                context_feedback=context_feedback,
                usage_collector=api_usage_records.append,
            )
            early_classification = classify_task(
                neural_state.real_objective,
                neural_state=neural_state,
            )
            early_boundary = evaluate_boundary(
                neural_state.real_objective,
                classification_elements=list(early_classification.elements),
                proposed_python=neural_state.proposed_python,
                proposed_terminal_command=neural_state.proposed_terminal_command,
                internet_read_request=neural_state.internet_read_request,
                proposed_self_upgrade=neural_state.proposed_self_upgrade,
            )
            boundary_history.append(early_boundary)
            shadow = early_boundary.shadow_ledger
            if (
                early_boundary.decision == "repair"
                and shadow is not None
                and shadow.repair_prompt
                and len(repair_feedback) < repair_limit
            ):
                repair_feedback.append(shadow.repair_prompt)
                continue
            mutation = early_boundary.proposed_self_upgrade
            if (
                early_boundary.decision == "pause"
                and early_boundary.authority_level == 5
                and mutation is not None
                and mutation_rounds < mutation_limit
            ):
                answer = input(
                    "[SE6 PAUSE]: The Sovereign Agent proposes a structural "
                    f"mutation to {mutation.filepath}.\n"
                    "Apply structural mutation to the deterministic cage? (Y/N): "
                ).strip().upper()
                mutation_rounds += 1
                if answer == "Y":
                    try:
                        event = _apply_structural_mutation(
                            mutation,
                            root=mutation_root or Path(__file__).resolve().parents[1],
                            audit_path=mutation_audit_path,
                            epistemic_confidence=neural_state.epistemic_confidence,
                        )
                    except Exception as exc:
                        logging.getLogger(__name__).debug(
                            "Approved mutation application failed", exc_info=True
                        )
                        token_id = _consent_token_id(mutation.filepath)
                        event = MutationConsentEvent(
                            filepath=mutation.filepath,
                            decision="apply_failed",
                            single_use_token_id=token_id,
                            epistemic_confidence=neural_state.epistemic_confidence,
                            detail=f"{type(exc).__name__}: {str(exc)[:400]}",
                        )
                        context_feedback.append(
                            "[SE6 SYSTEM OVERRIDE: Approved structural mutation "
                            "failed deterministic application. Calculate alternative path.]"
                        )
                    else:
                        context_feedback.append(
                            "[SE6 VERIFIED RESULT: Approved structural mutation was "
                            f"applied to {mutation.filepath}; audit_id={event.audit_id}; "
                            "runtime reload is required.]"
                        )
                    mutation_consent_history.append(event)
                else:
                    token_id = _consent_token_id(mutation.filepath)
                    mutation_consent_history.append(MutationConsentEvent(
                        filepath=mutation.filepath,
                        decision="denied",
                        single_use_token_id=token_id,
                        epistemic_confidence=neural_state.epistemic_confidence,
                        detail="No repository file was changed.",
                    ))
                    context_feedback.append(
                        "[SE6 SYSTEM OVERRIDE: Prime Mover denied structural mutation. "
                        "REFUSE this mutation and calculate alternative path.]"
                    )
                continue
            requested_url = early_boundary.internet_read_request
            if (
                early_boundary.decision == "pause"
                and early_boundary.authority_level == 5
                and requested_url
                and network_rounds < network_limit
            ):
                token_id = _consent_token_id(requested_url)
                answer = input(
                    "[SE6 PAUSE]: The Sovereign Agent requests network access "
                    f"to ingest [{requested_url}].\n"
                    "Grant single-use execution token? (Y/N): "
                ).strip().upper()
                network_rounds += 1
                if answer == "Y":
                    try:
                        envelope = _fetch_consented_envelope(
                            requested_url,
                            internet_fetcher or fetch_public_text,
                        )
                    except Exception as exc:
                        logging.getLogger(__name__).debug(
                            "Approved network ingest failed", exc_info=True
                        )
                        override = (
                            "[SE6 SYSTEM OVERRIDE: Approved network ingest failed: "
                            f"{type(exc).__name__}. Calculate alternative path.]"
                        )
                        context_feedback.append(override)
                        network_consent_history.append(NetworkConsentEvent(
                            url=requested_url,
                            decision="fetch_failed",
                            single_use_token_id=token_id,
                            detail=str(exc)[:500],
                        ))
                    else:
                        network_memory.append(envelope)
                        context_feedback.append(_sanitized_evidence_context(envelope))
                        network_consent_history.append(NetworkConsentEvent(
                            url=requested_url,
                            decision="approved",
                            single_use_token_id=token_id,
                            envelope_id=envelope.envelope_id,
                            detail="One bounded HTTPS GET was quarantined as untrusted evidence.",
                        ))
                else:
                    override = (
                        "[SE6 SYSTEM OVERRIDE: Prime Mover denied network access. "
                        "Calculate alternative path.]"
                    )
                    context_feedback.append(override)
                    network_consent_history.append(NetworkConsentEvent(
                        url=requested_url,
                        decision="denied",
                        single_use_token_id=token_id,
                        detail="No network adapter call was made.",
                    ))
                continue
            break
        centered = _center_from_neural(intention, neural_state, current_state=state)
    else:
        centered = center_intention(intention, current_state=state)
    lattice = map_lattice(centered.real_objective)
    rotation = rotate_perspectives(centered.real_objective)
    mirrors = reflect_task(centered.real_objective)
    classification = classify_task(
        centered.real_objective, neural_state=neural_state, neural=use_neural,
    )
    if neural_state is not None:
        boundary = boundary_history[-1]
    else:
        boundary = evaluate_boundary(centered.real_objective)
        boundary_history.append(boundary)
    canonical = canonicalize_decision(boundary.decision)
    repair = _repair_guidance(centered.real_objective)
    tool_request = _detect_tool_request(centered.real_objective)
    if repair and canonical == "ALLOW":
        canonical = "REPAIR"
    elif tool_request is not None and tool_request.requires_approval and canonical == "ALLOW":
        canonical = "PAUSE"
    observed = _observe_feedback(feedback)
    cognition_mode: Literal["neural", "offline_fallback"] = (
        "neural" if neural_state is not None else "offline_fallback"
    )
    epistemic_status = (
        EpistemicStatus.MODEL_PROPOSED
        if neural_state is not None
        else EpistemicStatus.DETERMINISTIC
    )
    tool_approval_required = bool(
        tool_request is not None and tool_request.requires_approval
    )
    approval_required = (
        boundary.decision in {"pause", "needs_human_approval"}
        or (canonical == "PAUSE" and tool_approval_required)
    )
    # Level-5 network/mutation proposals are normally resolved inside the
    # bounded neural loop.  If a zero-round configuration leaves one pending,
    # the final snapshot must still represent its explicit approval gate.
    if boundary.authority_level == 5 and canonical == "PAUSE":
        approval_required = True
    operational_awareness = build_operational_awareness_state(
        stated_intention=centered.stated_intention,
        interpreted_objective=centered.real_objective,
        objective_status=epistemic_status,
        objective_confidence=(
            neural_state.epistemic_confidence
            if neural_state is not None
            else 1.0
        ),
        cognition_mode=cognition_mode,
        current_state_present=bool(state),
        classification=classification.primary,
        classification_status=epistemic_status,
        classification_confidence=classification.confidence,
        uncertainty=_operational_uncertainty(
            cognition_mode=cognition_mode,
            confidence=classification.confidence,
            feedback=observed,
        ),
        mirrors=mirrors,
        perspectives=rotation,
        runtime_decision=boundary.decision,
        effective_decision=canonical,
        authority_level=boundary.authority_level,
        boundary_reasons=boundary.reasons,
        approval_required=approval_required,
        unresolved_requests=(
            (f"Approval required for {tool_request.tool_name}",)
            if tool_approval_required and tool_request is not None
            else ()
        ),
        observation_status=(
            ObservationStatus.REPORTED
            if observed.status == "reported"
            else ObservationStatus.NOT_OBSERVED
        ),
        observation_summary=(
            observed.summary if observed.status == "reported" else None
        ),
        observation_result_type=(
            observed.result_type if observed.status == "reported" else None
        ),
        previous_awareness_state_id=previous_awareness_state_id,
    )
    next_state = project_next_state(
        centered.real_objective,
        lattice,
        mirrors,
        classification,
        boundary,
        effective_decision=canonical,
        tool_approval_required=tool_approval_required,
        repair_guidance=repair,
        current_state_present=bool(state),
        observation_status=observed.status,
        epistemic_confidence=classification.confidence,
        awareness=operational_awareness,
    )

    before = {"phase": "pre", "task": centered.real_objective, "state_present": bool(state)}
    after = {
        "phase": "post",
        "task": centered.real_objective,
        "decision": boundary.decision,
        "primary_element": classification.primary,
        "next_action": next_state.action,
    }
    assimilation = calculate_assimilation(
        before,
        after,
        prior_audit_summary=prior_audit_summary,
        task_text=centered.real_objective,
    )
    # Compatibility feedback is attributable only to the caller.  It remains
    # REPORTED and cannot satisfy receipt-bound verification or commit law.
    committed = False
    proposed_action = next_state.action
    transition = StateTransition(
        current_state_present=bool(state),
        expected_change=proposed_action,
        memory_update=(
            "Retain caller feedback as reported context; do not assimilate or commit it."
            if observed.status == "reported"
            else "Record this run as a proposal; do not claim external execution."
        ),
        committed=committed,
    )
    motion = _motion(canonical, observed)
    approval = approval_required or next_state.requires_human
    timestamp = datetime.now(UTC).isoformat()
    audit = CanonicalAuditEntry(
        timestamp=timestamp,
        boundary_decision=canonical,
        runtime_decision=boundary.decision,
        action=proposed_action,
        result=observed.summary,
    )
    packet = SE6StatePacket(
        realObjective=centered.real_objective,
        flowerMap=_flower_values(lattice),
        merkabahRotation=list(rotation.as_dict().values()),
        mirrorReflection=mirrors.truth,
        classification=classification.primary,
        boundaryDecision=canonical,
        nextLawfulAction=proposed_action,
        toolRequest=tool_request,
        approvalRequired=approval,
        memoryUpdate=transition.memory_update,
        expectedStateChange=transition.expected_change,
        motionState=motion,
        auditEntry=audit,
    )
    legacy_result = SE6TriadResult(
        intention=centered,
        lattice=lattice,
        rotation=rotation,
        mirrors=mirrors,
        classification=classification,
        boundary=boundary,
        canonical_decision=canonical,
        repair_guidance=repair,
        assimilation=assimilation,
        next_state=next_state,
        feedback=observed,
        state_transition=transition,
        motion_state=motion,
        state_packet=packet,
        cognition_mode=cognition_mode,
        boundary_history=boundary_history,
        repair_attempts=len(repair_feedback),
        network_consent_history=network_consent_history,
        network_memory=network_memory,
        mutation_consent_history=mutation_consent_history,
        operational_awareness=operational_awareness,
        api_usage=summarize_api_usage(api_usage_records),
    )
    try:
        observe_legacy_result_in_shadow(
            request_context=intention,
            legacy_result=legacy_result,
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "Canonical shadow instrumentation failed in isolation", exc_info=True
        )
    return legacy_result


__all__ = [
    "ApiUsageSummary", "CanonicalAuditEntry", "CanonicalDecision", "FeedbackObservation",
    "MutationConsentEvent", "NetworkConsentEvent", "SE6StatePacket",
    "SE6TriadResult", "StateTransition", "ToolRequest",
    "canonicalize_decision", "run_se6triad", "summarize_api_usage",
]
