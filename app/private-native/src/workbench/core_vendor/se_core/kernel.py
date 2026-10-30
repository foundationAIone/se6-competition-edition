"""A bounded executable subset, not a numerical solution of the Symbolic Equation.

MAP -> RELATE -> MIRROR -> PROJECT -> BOUND -> ACT -> VERIFY -> ASSIMILATE
-> NEXT_STATE. Authority context comes from the trusted host, never a model.
Default actions are deterministic local receipts, with no external effects.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from typing import Callable, Mapping


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SERelation:
    subject: str
    predicate: str
    value: str
    source_ids: tuple[str, ...]
    epistemic_status: str = "OWNER_SUPPLIED"

    @property
    def key(self) -> tuple[str, str]:
        return self.subject.casefold(), self.predicate.casefold()


@dataclass(frozen=True)
class SEState:
    identity: str
    version: int = 0
    relations: tuple[SERelation, ...] = ()
    actions_used: int = 0

    @property
    def state_hash(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class SEObservation:
    kind: str  # ASSERT or RECALL; structured input, not arbitrary natural language.
    subject: str
    predicate: str
    value: str | None = None
    source: str = ""
    evidence_refs: tuple[str, ...] = ()
    correction: bool = False

    @property
    def observation_id(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class SEAction:
    kind: str
    payload: str  # Canonical JSON; no mutable nested object.

    @property
    def action_id(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class SECandidateTransition:
    state_before_hash: str
    observation_id: str
    relation: SERelation | None
    prior_relations: tuple[SERelation, ...]
    conflict: bool
    action: SEAction
    expected_consequence: str

    @property
    def candidate_id(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class SEBoundaryDecision:
    outcome: str
    checks: tuple[tuple[str, bool, str], ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SEConsequence:
    action_id: str
    success: bool
    result: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SEVerification:
    passed: bool
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SETransitionReceipt:
    state_before: SEState
    observation: SEObservation
    relationships: tuple[SERelation, ...]
    candidate: SECandidateTransition
    boundary: SEBoundaryDecision
    authority: str  # Canonical host-context JSON, including exact approval binding.
    action: SEAction | None
    expected_consequence: str
    observed_consequence: SEConsequence | None
    verification: SEVerification
    assimilation: tuple[SERelation, ...]
    state_after: SEState
    previous_receipt_hash: str | None

    @property
    def receipt_hash(self) -> str:
        return _hash(asdict(self))

    def to_record(self) -> dict:
        return {**asdict(self), "receipt_hash": self.receipt_hash}


_CONTEXT_FIELDS = frozenset({
    "identity", "authorized", "permissions", "integrity_valid", "evidence_valid",
    "max_actions", "risk", "max_risk", "sensitive", "human_approval_for",
})
_EXECUTE = object()


def _context(value: Mapping) -> dict:
    if set(value) != _CONTEXT_FIELDS:
        raise ValueError("exact host boundary context required")
    result = dict(value)
    for name in ("authorized", "integrity_valid", "evidence_valid", "sensitive"):
        if type(result[name]) is not bool:
            raise ValueError(f"{name} must be boolean")
    for name in ("max_actions", "risk", "max_risk"):
        if type(result[name]) is not int or result[name] < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if not isinstance(result["identity"], str):
        raise ValueError("identity required")
    permissions = result["permissions"]
    if not isinstance(permissions, (tuple, list)) or not all(isinstance(p, str) for p in permissions):
        raise ValueError("permissions must be an explicit sequence")
    result["permissions"] = sorted(set(permissions))
    if result["human_approval_for"] is not None and not isinstance(result["human_approval_for"], str):
        raise ValueError("approval must bind a candidate ID")
    return result


def _validate_state(state: SEState) -> None:
    if not isinstance(state, SEState) or not isinstance(state.identity, str) or not state.identity:
        raise ValueError("state identity required")
    if any(type(n) is not int or n < 0 for n in (state.version, state.actions_used)):
        raise ValueError("invalid state counters")
    if type(state.relations) is not tuple or not all(isinstance(r, SERelation) for r in state.relations):
        raise ValueError("immutable relations required")
    for r in state.relations:
        if not all(isinstance(s, str) and s for s in (r.subject, r.predicate, r.value)):
            raise ValueError("nonempty relation fields required")
        if type(r.source_ids) is not tuple or not r.source_ids or not all(isinstance(s, str) and s for s in r.source_ids):
            raise ValueError("immutable provenance required")
        if r.epistemic_status != "OWNER_SUPPLIED":
            raise ValueError("this kernel retains source assertions, not verified world facts")
    if len({r.key for r in state.relations}) != len(state.relations):
        raise ValueError("one current relation per normalized subject/property")


def _candidate(state: SEState, obs: SEObservation) -> SECandidateTransition:
    if not isinstance(obs, SEObservation) or obs.kind not in ("ASSERT", "RECALL"):
        raise ValueError("supported structured observation required")
    if not all(isinstance(s, str) and s.strip() for s in (obs.subject, obs.predicate)):
        raise ValueError("subject and predicate required")
    if not isinstance(obs.source, str) or type(obs.correction) is not bool or type(obs.evidence_refs) is not tuple:
        raise ValueError("immutable observation metadata required")
    if not all(isinstance(s, str) and s for s in obs.evidence_refs):
        raise ValueError("invalid observation evidence")
    if obs.kind == "ASSERT" and (not isinstance(obs.value, str) or not obs.value.strip()):
        raise ValueError("assertion value required")
    if obs.kind == "RECALL" and (obs.value is not None or obs.correction):
        raise ValueError("recall cannot supply its answer or a correction")
    key = (obs.subject.strip().casefold(), obs.predicate.strip().casefold())
    prior = tuple(r for r in state.relations if r.key == key)
    relation = None
    conflict = False
    if obs.kind == "ASSERT":
        conflict = bool(prior and prior[0].value != obs.value.strip() and not obs.correction)
        conflict = conflict or bool(obs.correction and not prior)
        sources = tuple(sorted(set(obs.evidence_refs + (obs.observation_id,))))
        relation = SERelation(obs.subject.strip(), obs.predicate.strip(), obs.value.strip(), sources)
        expected = _json({"retained_assertion": asdict(relation)})
        action = SEAction("RETAIN_ASSERTION", expected)
    else:
        # The value and provenance come only from the supplied durable state.
        expected = _json({"value": prior[0].value if prior else None,
                          "source_ids": prior[0].source_ids if prior else (),
                          "epistemic_status": "OWNER_SUPPLIED" if prior else "UNKNOWN"})
        action = SEAction("RECALL", expected)
    return SECandidateTransition(state.state_hash, obs.observation_id, relation,
                                 prior, conflict, action, expected)


def _bound(state: SEState, obs: SEObservation, candidate: SECandidateTransition,
           ctx: dict) -> SEBoundaryDecision:
    checks = (
        ("identity", ctx["identity"] == state.identity, "IDENTITY_MISMATCH"),
        ("authority", ctx["authorized"], "AUTHORITY_ABSENT"),
        ("permissions", candidate.action.kind in ctx["permissions"], "PERMISSION_ABSENT"),
        ("integrity", ctx["integrity_valid"], "INTEGRITY_INVALID"),
        ("evidence", ctx["evidence_valid"] and bool(obs.source and obs.evidence_refs), "EVIDENCE_ABSENT"),
        ("resource_limits", state.actions_used < ctx["max_actions"], "ACTION_BUDGET_EXHAUSTED"),
        ("risk", ctx["risk"] <= ctx["max_risk"], "RISK_LIMIT_EXCEEDED"),
        ("expected_consequence", bool(candidate.expected_consequence), "EXPECTED_CONSEQUENCE_ABSENT"),
        ("human_approval", not ctx["sensitive"] or ctx["human_approval_for"] == candidate.candidate_id, "EXACT_HUMAN_APPROVAL_REQUIRED"),
        ("transition_coherence", not candidate.conflict, "EXPLICIT_CORRECTION_REQUIRED"),
    )
    failed = {name for name, ok, _ in checks if not ok}
    if failed - {"resource_limits", "human_approval"}:
        outcome = "REFUSE"
    elif "resource_limits" in failed:
        outcome = "PAUSE"
    elif "human_approval" in failed:
        outcome = "REQUIRE_HUMAN_APPROVAL"
    else:
        outcome = "ALLOW"
    return SEBoundaryDecision(outcome, checks,
        tuple(reason for _, ok, reason in checks if not ok) or ("ALL_BOUNDARY_CHECKS_PASSED",))


def _local_action(action: SEAction) -> SEConsequence:
    return SEConsequence(action.action_id, True, action.payload,
                         ("local-action:" + action.action_id,))


class SE:
    """Host-owned transition engine. Models have no mutation or authority API."""

    def __init__(self, initial_state: SEState,
                 executor: Callable[[SEAction], SEConsequence] | None = None):
        _validate_state(initial_state)
        self._initial = self._state = initial_state
        self._receipts: tuple[SETransitionReceipt, ...] = ()
        self._executor = executor or _local_action

    @property
    def state(self) -> SEState:
        return self._state

    @property
    def receipts(self) -> tuple[SETransitionReceipt, ...]:
        return self._receipts

    def transition(self, state: SEState, observation: SEObservation,
                   boundary_context: Mapping) -> tuple[SEState, SETransitionReceipt]:
        return self._transition(state, observation, boundary_context, _EXECUTE)

    def _transition(self, state, observation, boundary_context, recorded):
        if state != self._state:
            raise ValueError("transition must bind the current state")
        ctx = _context(boundary_context)
        candidate = _candidate(state, observation)
        boundary = _bound(state, observation, candidate, ctx)
        action = None
        consequence = None
        verification = SEVerification(False, ("ACTION_NOT_AUTHORIZED",))
        assimilation = ()
        after = state
        if boundary.outcome == "ALLOW":
            action = candidate.action
            if recorded is _EXECUTE:
                try:
                    consequence = self._executor(action)
                except Exception:
                    consequence = SEConsequence(action.action_id, False, "EXECUTOR_FAILED", ())
            else:
                consequence = recorded
            if (not isinstance(consequence, SEConsequence) or not isinstance(consequence.action_id, str) or
                type(consequence.success) is not bool or
                not isinstance(consequence.result, str) or type(consequence.evidence_refs) is not tuple or
                not all(isinstance(ref, str) and ref for ref in consequence.evidence_refs)):
                consequence = SEConsequence(action.action_id, False, "INVALID_CONSEQUENCE", ())
            passed = (consequence.success and consequence.action_id == action.action_id and
                      consequence.result == candidate.expected_consequence and bool(consequence.evidence_refs))
            verification = SEVerification(passed, ("EXACT_LOCAL_CONSEQUENCE_VERIFIED" if passed else
                                                    "CONSEQUENCE_MISMATCH_OR_FAILURE",), consequence.evidence_refs)
            if passed and candidate.relation is not None:
                assimilation = (candidate.relation,)
            relations = state.relations
            if assimilation:
                relations = tuple(r for r in relations if r.key != candidate.relation.key) + assimilation
            # A failed action still consumes resources; it never contributes learned relations.
            after = replace(state, version=state.version + 1, actions_used=state.actions_used + 1,
                            relations=relations)
        receipt = SETransitionReceipt(state, observation, candidate.prior_relations,
            candidate, boundary, _json(ctx), action, candidate.expected_consequence,
            consequence, verification, assimilation, after,
            self._receipts[-1].receipt_hash if self._receipts else None)
        self._receipts += (receipt,)
        self._state = after
        return after, receipt

    def dumps(self) -> str:
        return _json({"schema": "se-core-v0.1", "initial_state": asdict(self._initial),
                      "state": asdict(self._state),
                      "receipts": [r.to_record() for r in self._receipts]})

    @classmethod
    def restore(cls, serialized: str, *, expected_head: str | None = None) -> SE:
        """Inspect/reconstruct recorded transitions; never rerun their actions."""
        data = json.loads(serialized)
        if set(data) != {"schema", "initial_state", "state", "receipts"} or data["schema"] != "se-core-v0.1":
            raise ValueError("unsupported checkpoint")
        initial = dict(data["initial_state"])
        initial["relations"] = tuple(SERelation(**{**r, "source_ids": tuple(r["source_ids"])})
                                     for r in initial["relations"])
        engine = cls(SEState(**initial))
        for saved in data["receipts"]:
            obs = {**saved["observation"], "evidence_refs": tuple(saved["observation"]["evidence_refs"])}
            observed = saved["observed_consequence"]
            consequence = None if observed is None else SEConsequence(**{
                **observed, "evidence_refs": tuple(observed["evidence_refs"])})
            _, rebuilt = engine._transition(engine.state, SEObservation(**obs),
                                             json.loads(saved["authority"]), consequence)
            if _json(rebuilt.to_record()) != _json(saved):
                raise ValueError("receipt chain or transition mismatch")
        if _json(asdict(engine.state)) != _json(data["state"]):
            raise ValueError("checkpoint state mismatch")
        if expected_head is not None and (not engine.receipts or engine.receipts[-1].receipt_hash != expected_head):
            raise ValueError("external receipt anchor mismatch")
        return engine
