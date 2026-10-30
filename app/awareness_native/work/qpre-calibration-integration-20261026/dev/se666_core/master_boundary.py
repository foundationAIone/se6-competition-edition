"""Master Boundary Π_B evaluator.

Classifies a task into one of:
  - allow
  - pause
  - refuse
  - needs_human_approval

Heuristic, deterministic, local-only. No network calls.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from .live_loop_config import LIVE_LOOP_ADAPTER, LIVE_LOOP_POLICY_VERSION
from .live_loop_contracts import (
    AuthorityScope,
    CandidateTransition,
    LiveBoundaryDecision,
    LiveBoundaryResult,
    LiveLoopBudget,
    LiveLoopUsage,
    create_boundary_result,
)
from .periodic_classifier import SelfUpgradeProposal
from .shadow_ledger import ShadowLedgerResult, inspect_proposal, inspect_python

Decision = Literal["allow", "pause", "repair", "refuse", "needs_human_approval"]

BOUNDARY_COMPONENTS: list[str] = [
    "truth",
    "safety",
    "law",
    "consent",
    "privacy",
    "authorization",
    "coherence",
    "responsibility",
    "future_benefit",
]

# Clearly harmful / illegal -> refuse
REFUSE_PATTERNS: list[str] = [
    "kill", "murder", "bomb", "explosive", "weapon of mass",
    "child porn", "csam", "rape",
    "make meth", "synthesize fentanyl", "cook meth",
    "ddos", "botnet", "ransomware", "stalk ", "stalking ",
    "dox ", "doxx",
    "hack into", "break into someone", "bypass authentication of",
    "credit card numbers", "steal identity", "launder money",
    "human trafficking", "sex trafficking",
    "suicide method", "how to kill myself",
]

# Sensitive / unclear -> pause or needs_human_approval
SENSITIVE_PATTERNS: list[str] = [
    "medical", "diagnose", "prescribe",
    "legal advice", "lawsuit", "sue ",
    "investment advice", "financial advice", "trade for me",
    "delete production", "drop database", "rm -rf",
    "send email to", "post to", "publish to",
    "scrape ", "crawl ", "browser ", "web control",
    "self-update", "self update", "modify yourself", "rewrite your code",
    "credentials", "password", "api key", "private key",
    "transfer funds", "wire money",
    "autonomous", "autonomy",
    "internet", "external api",
]

APPROVAL_PATTERNS: list[str] = [
    "deploy", "production", "live system",
    "merge to main", "force push",
    "shutdown", "reboot",
    "execute shell", "run command", "system call",
    "system command", "execute system",
    "bypass approval", "bypass authorization",
]

# Cues that, when appearing earlier in the same clause as a sensitive /
# approval term, indicate the user is *prohibiting* that term rather than
# requesting it.  Scope is *clause-level* (see :func:`_split_clauses`),
# which lets a single cue ("Do not add ...") govern an entire comma-
# separated list of forbidden capabilities.
NEGATION_CUES: list[str] = [
    "do not ", "don't ", "dont ",
    "never ", "without ",
    "avoid ", "refrain from ",
    "must not ", "shouldn't ", "should not ",
    "cannot ", "can't ", "won't ", "will not ",
    "no ", "non-", "non ",
    "keep it non", "stay non", "remain non",
    "keep it local", "keep it safe", "keep it offline",
    "stay local", "stay offline",
    "prohibit ", "forbid ", "disallow ",
    "exclude ", "omit ", "skip ",
]

# Sentence terminators and intra-sentence contrast markers.  We split on
# both so that "Plan X but do not implement Y" yields two clauses, and
# the negation in the second clause does not bleed into the first.
_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")
_CLAUSE_SPLIT_RE = re.compile(
    r"\s+but\s+|\s+however\s+|\s+whereas\s+|;\s*",
    flags=re.IGNORECASE,
)


class MasterBoundaryResult(BaseModel):
    """Outcome of Π_B evaluation."""

    decision: Decision = Field(..., description="Boundary decision.")
    reasons: list[str] = Field(default_factory=list)
    triggered_components: list[str] = Field(default_factory=list)
    real_constraints: list[str] = Field(default_factory=list)
    illusion_constraints: list[str] = Field(default_factory=list)
    notes: str = ""
    shadow_ledger: ShadowLedgerResult | None = None
    authority_level: int = Field(default=0, ge=0, le=7)
    internet_read_request: str | None = None
    proposed_self_upgrade: SelfUpgradeProposal | None = None


REAL_CONSTRAINTS: list[str] = [
    "truth",
    "law",
    "safety",
    "privacy",
    "consent",
    "authorization",
    "technical_feasibility",
    "irreversible_harm_prevention",
]

ILLUSION_CONSTRAINTS: list[str] = [
    "shallow_assumptions",
    "confusion",
    "fragmented_context",
    "unnecessary_ceremony",
    "false_separation_symbolic_practical",
    "fear_of_mapping_complexity",
]


class LiveBoundaryContext(BaseModel):
    """Facts supplied by trusted runtime authority, never by a proposer."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    workspace_id: StrictStr = Field(min_length=1)
    authenticated_owner_id: StrictStr | None = None
    production_integrity_verified: bool
    emergency_stop_armed: bool
    lifecycle_permits_execution: bool
    target_is_disposable_workspace: bool
    immutable_zone_targeted: bool = False
    network_required: bool = False
    owner_policy_allows: bool = True
    constitution_allows: bool = True
    evidence_sufficient: bool = True
    repeated_equivalent_failures: int = Field(default=0, ge=0)
    budget: LiveLoopBudget = Field(default_factory=LiveLoopBudget)
    usage: LiveLoopUsage = Field(default_factory=LiveLoopUsage)
    registered_adapters: tuple[StrictStr, ...] = (LIVE_LOOP_ADAPTER,)


_LIVE_FORBIDDEN_AST = (
    ast.Import,
    ast.ImportFrom,
    ast.Attribute,
    ast.Global,
    ast.Nonlocal,
    ast.ClassDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Raise,
    ast.Delete,
)


def _live_result(
    candidate: CandidateTransition,
    *,
    decision: LiveBoundaryDecision,
    reason_codes: tuple[str, ...],
    evaluated_at_utc: datetime,
    context: LiveBoundaryContext,
    repair_instructions: tuple[str, ...] = (),
    scoped: bool = False,
) -> LiveBoundaryResult:
    scope = None
    adapter = None
    if scoped:
        adapter = LIVE_LOOP_ADAPTER
        scope = AuthorityScope(
            workspace_id=context.workspace_id,
            adapter=LIVE_LOOP_ADAPTER,
            target=candidate.target,
            max_files=context.budget.max_files,
            max_file_bytes=context.budget.max_file_bytes,
            max_runtime_seconds=context.budget.max_runtime_seconds,
            max_output_bytes=context.budget.max_output_bytes,
            network_allowed=False,
            shell_allowed=False,
        )
    return create_boundary_result(
        transaction_id=candidate.transaction_id,
        cycle_id=candidate.cycle_id,
        candidate_id=candidate.candidate_id,
        decision=decision,
        reason_codes=reason_codes,
        repair_instructions=repair_instructions,
        approved_adapter=adapter,
        authority_scope=scope,
        policy_version=LIVE_LOOP_POLICY_VERSION,
        evaluated_at_utc=evaluated_at_utc,
    )


def evaluate_live_candidate_boundary(
    candidate: CandidateTransition,
    context: LiveBoundaryContext,
    *,
    evaluated_at_utc: datetime | None = None,
) -> LiveBoundaryResult:
    """Deterministically project one typed v0.1 candidate through Π_B.

    This function is pure.  It does not approve, execute, persist, or create a
    workspace.  A proposer cannot supply any of the authority facts in
    ``context`` through candidate arguments.
    """

    if not isinstance(candidate, CandidateTransition):
        raise TypeError("candidate must be CandidateTransition")
    if not isinstance(context, LiveBoundaryContext):
        raise TypeError("context must be LiveBoundaryContext")
    now = evaluated_at_utc or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("evaluated_at_utc must be timezone-aware")

    if candidate.action_type not in context.registered_adapters or candidate.adapter != LIVE_LOOP_ADAPTER:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REFUSE,
            reason_codes=("UNREGISTERED_ADAPTER",),
            evaluated_at_utc=now,
            context=context,
        )
    if context.immutable_zone_targeted or not context.target_is_disposable_workspace:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REFUSE,
            reason_codes=("IMMUTABLE_OR_NONDISPOSABLE_TARGET",),
            evaluated_at_utc=now,
            context=context,
        )
    if context.network_required:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REFUSE,
            reason_codes=("NETWORK_NOT_AUTHORIZED_V0_1",),
            evaluated_at_utc=now,
            context=context,
        )
    if not context.constitution_allows or not context.owner_policy_allows:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REFUSE,
            reason_codes=("CONSTITUTION_OR_OWNER_POLICY_REFUSED",),
            evaluated_at_utc=now,
            context=context,
        )
    if not context.production_integrity_verified:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.PAUSE,
            reason_codes=("PRODUCTION_INTEGRITY_UNCERTAIN",),
            evaluated_at_utc=now,
            context=context,
        )
    if context.authenticated_owner_id is None:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.PAUSE,
            reason_codes=("AUTHENTICATED_OWNER_REQUIRED",),
            evaluated_at_utc=now,
            context=context,
        )
    if not context.emergency_stop_armed:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REFUSE,
            reason_codes=("EMERGENCY_STOP_ACTIVE",),
            evaluated_at_utc=now,
            context=context,
        )
    if not context.lifecycle_permits_execution:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.PAUSE,
            reason_codes=("LIFECYCLE_DOES_NOT_PERMIT_EXECUTION",),
            evaluated_at_utc=now,
            context=context,
        )
    if context.repeated_equivalent_failures >= 2:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.PAUSE,
            reason_codes=("REPEATED_EQUIVALENT_FAILURE_LIMIT",),
            evaluated_at_utc=now,
            context=context,
        )
    if not context.usage.within(context.budget):
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.PAUSE,
            reason_codes=("RESOURCE_BUDGET_EXHAUSTED",),
            evaluated_at_utc=now,
            context=context,
        )
    if not context.evidence_sufficient or not candidate.evidence_refs:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REPAIR,
            reason_codes=("EVIDENCE_OR_VERIFICATION_INSUFFICIENT",),
            repair_instructions=("Supply attributable observation and independent verification.",),
            evaluated_at_utc=now,
            context=context,
        )
    if set(candidate.structured_arguments) != {"proposed_content"}:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REFUSE,
            reason_codes=("ARGUMENT_CONTRACT_EXCEEDED",),
            evaluated_at_utc=now,
            context=context,
        )
    proposed = candidate.structured_arguments.get("proposed_content")
    if not isinstance(proposed, str) or not proposed:
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REPAIR,
            reason_codes=("PROPOSED_CONTENT_MISSING",),
            repair_instructions=("Provide non-empty Python candidate content.",),
            evaluated_at_utc=now,
            context=context,
        )
    try:
        tree = ast.parse(proposed, filename=candidate.target, mode="exec")
    except SyntaxError as exc:
        detail = f"SyntaxError at line {exc.lineno or 0}: {exc.msg}"
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REPAIR,
            reason_codes=("PYTHON_SYNTAX_INVALID",),
            repair_instructions=(detail,),
            evaluated_at_utc=now,
            context=context,
        )
    if any(isinstance(node, _LIVE_FORBIDDEN_AST) for node in ast.walk(tree)):
        return _live_result(
            candidate,
            decision=LiveBoundaryDecision.REFUSE,
            reason_codes=("PYTHON_AST_OUTSIDE_REPAIR_GRAMMAR",),
            evaluated_at_utc=now,
            context=context,
        )
    return _live_result(
        candidate,
        decision=LiveBoundaryDecision.REQUIRE_APPROVAL,
        reason_codes=("WORKSPACE_WRITE", "OWNER_APPROVAL_REQUIRED"),
        evaluated_at_utc=now,
        context=context,
        scoped=True,
    )


def _matches(text: str, patterns: list[str]) -> list[str]:
    t = text.lower()
    return [p.strip() for p in patterns if p in t]


def _split_clauses(text_lower: str) -> list[str]:
    """Split *text_lower* into clauses for negation-scoping.

    First splits on sentence terminators (``. ! ? \\n``), then each
    sentence is further split on intra-sentence contrast markers
    (``but``, ``however``, ``whereas``, ``;``).  Empty fragments are
    dropped.
    """
    clauses: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text_lower):
        sentence = sentence.strip()
        if not sentence:
            continue
        for clause in _CLAUSE_SPLIT_RE.split(sentence):
            clause = clause.strip()
            if clause:
                clauses.append(clause)
    return clauses


def _clause_is_prohibitive(clause: str, pattern: str) -> bool:
    """Return True iff *clause* contains a negation cue positioned at or
    before the first occurrence of *pattern* in that clause.

    A clause-level cue applies to every sensitive term that follows it
    in the same clause, which is what lets ``"Do not add internet
    access, external APIs, or self-update yet."`` correctly negate
    every listed term.
    """
    idx = clause.find(pattern)
    if idx == -1:
        return False
    head = clause[: idx + len(pattern)]
    return any(cue in head for cue in NEGATION_CUES)


def _matches_context_aware(text: str, patterns: list[str]) -> list[str]:
    """Like :func:`_matches`, but drops patterns whose every clause-level
    occurrence sits inside a prohibitive/negated clause.
    """
    t = text.lower()
    clauses = _split_clauses(t)
    hits: list[str] = []
    for p in patterns:
        if p not in t:
            continue
        appeared = False
        all_prohibited = True
        for clause in clauses:
            if p not in clause:
                continue
            appeared = True
            if not _clause_is_prohibitive(clause, p):
                all_prohibited = False
                break
        if appeared and all_prohibited:
            continue
        hits.append(p.strip())
    return hits


def evaluate_boundary(
    task: str,
    *,
    classification_elements: list[str] | None = None,
    proposed_python: str | None = None,
    proposed_terminal_command: str | None = None,
    internet_read_request: str | None = None,
    proposed_self_upgrade: SelfUpgradeProposal | None = None,
) -> MasterBoundaryResult:
    """Evaluate a task against Π_B and return a structured decision.

    Pure function. No I/O, no network.
    """
    if not isinstance(task, str):
        raise TypeError("task must be str")

    text = task.strip()
    if not text:
        return MasterBoundaryResult(
            decision="pause",
            reasons=["empty_task"],
            triggered_components=["coherence"],
            real_constraints=list(REAL_CONSTRAINTS),
            illusion_constraints=list(ILLUSION_CONSTRAINTS),
            notes="Task is empty; cannot evaluate intention.",
        )

    # Refuse stays strict (do not soften clearly-harmful patterns via negation).
    refuse_hits = _matches(text, REFUSE_PATTERNS)
    # Sensitive / approval are context-aware: a prohibition of a sensitive term
    # is *not* itself a request for that term.
    sensitive_hits = _matches_context_aware(text, SENSITIVE_PATTERNS)
    approval_hits = _matches_context_aware(text, APPROVAL_PATTERNS)

    shadow = inspect_proposal(
        elements=list(classification_elements or []),
        proposed_python=proposed_python,
        proposed_terminal_command=proposed_terminal_command,
    )

    if refuse_hits:
        return MasterBoundaryResult(
            decision="refuse",
            reasons=[f"matched_refuse_pattern:{p}" for p in refuse_hits],
            triggered_components=["safety", "law", "responsibility"],
            real_constraints=["safety", "law", "irreversible_harm_prevention"],
            illusion_constraints=[],
            notes="Task appears to request clearly harmful or illegal action.",
            shadow_ledger=shadow,
        )

    if shadow.decision == "refuse":
        return MasterBoundaryResult(
            decision="refuse",
            reasons=[f"banned_executable:{token}" for token in shadow.banned_tokens],
            triggered_components=["safety", "authorization", "responsibility"],
            real_constraints=["safety", "authorization", "irreversible_harm_prevention"],
            illusion_constraints=[],
            notes=shadow.reason,
            shadow_ledger=shadow,
        )

    if proposed_self_upgrade is not None:
        mutation_shadow = inspect_python(proposed_self_upgrade.proposed_content)
        if mutation_shadow.decision == "repair":
            return MasterBoundaryResult(
                decision="repair",
                reasons=[mutation_shadow.repair_prompt or "self_upgrade_syntax_repair"],
                triggered_components=["truth", "coherence", "technical_feasibility"],
                real_constraints=["truth", "technical_feasibility"],
                illusion_constraints=[],
                notes="Proposed structural mutation failed virtual AST validation.",
                shadow_ledger=mutation_shadow,
                proposed_self_upgrade=proposed_self_upgrade,
            )
        return MasterBoundaryResult(
            decision="pause",
            reasons=["authority_level_5:proposed_self_upgrade"],
            triggered_components=["authorization", "consent", "coherence", "responsibility"],
            real_constraints=["authorization", "consent", "rollback", "auditability"],
            illusion_constraints=[],
            notes="A syntax-valid structural mutation requires explicit human consent.",
            shadow_ledger=mutation_shadow,
            authority_level=5,
            proposed_self_upgrade=proposed_self_upgrade,
        )

    if internet_read_request:
        return MasterBoundaryResult(
            decision="pause",
            reasons=["authority_level_5:internet.read"],
            triggered_components=["authorization", "consent", "privacy", "truth"],
            real_constraints=["authorization", "consent", "privacy", "source_trust"],
            illusion_constraints=[],
            notes="Public HTTPS ingestion requires real-time, single-use human consent.",
            shadow_ledger=shadow,
            authority_level=5,
            internet_read_request=internet_read_request,
        )

    if shadow.decision == "repair":
        return MasterBoundaryResult(
            decision="repair",
            reasons=[shadow.repair_prompt or "shadow_ledger_repair"],
            triggered_components=["truth", "coherence", "technical_feasibility"],
            real_constraints=["truth", "technical_feasibility"],
            illusion_constraints=[],
            notes=shadow.reason,
            shadow_ledger=shadow,
        )

    if approval_hits:
        return MasterBoundaryResult(
            decision="needs_human_approval",
            reasons=[f"matched_approval_pattern:{p}" for p in approval_hits],
            triggered_components=["authorization", "responsibility", "safety"],
            real_constraints=["authorization", "irreversible_harm_prevention"],
            illusion_constraints=["unnecessary_ceremony"],
            notes="High-impact / irreversible scope; explicit human approval required.",
            shadow_ledger=shadow,
        )

    if sensitive_hits:
        return MasterBoundaryResult(
            decision="pause",
            reasons=[f"matched_sensitive_pattern:{p}" for p in sensitive_hits],
            triggered_components=["consent", "privacy", "truth"],
            real_constraints=["privacy", "consent", "truth"],
            illusion_constraints=["shallow_assumptions", "fragmented_context"],
            notes="Sensitive or unclear domain; pause and request clarification.",
            shadow_ledger=shadow,
        )

    return MasterBoundaryResult(
        decision="allow",
        reasons=["no_boundary_violations_detected"],
        triggered_components=list(BOUNDARY_COMPONENTS),
        real_constraints=list(REAL_CONSTRAINTS),
        illusion_constraints=list(ILLUSION_CONSTRAINTS),
        notes="Task appears safe, lawful, and constructive.",
        shadow_ledger=shadow,
    )
