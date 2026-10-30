"""Exact, bounded mathematical operators for the existing SE transition engine.

Premises are task assumptions, not verified world facts. A verified deduction
means entailment from the cited, versioned premises within the stated domain.
No parser, model, network, hidden solution, production imports, or new store.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from itertools import combinations, product
import math
import re

from .kernel import SECandidateTransition, SEAction, SEState, _hash, _json

SCHEMA = "se-core-math-v1"
MIXED_SCHEMA = "se-core-math-relational-v1"
MAX_CHECK_CELLS = 250_000
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z")


@dataclass(frozen=True)
class IntegerVariable:
    name: str
    lower: int
    upper: int

    def __post_init__(self):
        if (not isinstance(self.name, str) or not _NAME.fullmatch(self.name)
                or type(self.lower) is not int or type(self.upper) is not int
                or not -10_000 <= self.lower <= self.upper <= 10_000
                or self.upper - self.lower >= 128):
            raise ValueError("bounded integer variable required")


@dataclass(frozen=True)
class LinearEquation:
    coefficients: tuple[tuple[str, int], ...]
    rhs: int

    def __post_init__(self):
        if (type(self.coefficients) is not tuple or not self.coefficients
                or len(self.coefficients) > 8 or type(self.rhs) is not int):
            raise ValueError("immutable nonempty integer equation required")
        for term in self.coefficients:
            if (type(term) is not tuple or len(term) != 2
                    or not isinstance(term[0], str) or not _NAME.fullmatch(term[0])
                    or type(term[1]) is not int or not 0 < abs(term[1]) <= 1_000_000):
                raise ValueError("exact nonzero integer coefficients required")
        names = tuple(name for name, _ in self.coefficients)
        if names != tuple(sorted(set(names))):
            raise ValueError("coefficients must be sorted and unique")

    @classmethod
    def from_coefficients(cls, coefficients: dict[str, int], rhs: int):
        # No mathematical text is evaluated or executed.
        if not isinstance(coefficients, dict) or any(type(v) is not int for v in coefficients.values()):
            raise ValueError("integer coefficient mapping required")
        return cls(tuple(sorted((k, v) for k, v in coefficients.items() if v)), rhs)

    def holds(self, assignment: dict[str, int]) -> bool:
        return sum(coefficient * assignment[name] for name, coefficient in self.coefficients) == self.rhs

    def isolate(self, variable: str) -> str:
        coefficient = dict(self.coefficients).get(variable, 0)
        if not coefficient:
            raise ValueError("isolation requires a nonzero pivot")
        terms = tuple((name, Fraction(-value, coefficient))
                      for name, value in self.coefficients if name != variable)
        return f"{variable} = {_expression(terms, Fraction(self.rhs, coefficient))}"

    def display(self) -> str:
        return f"{_expression(self.coefficients)} = {self.rhs}"


def _expression(terms, constant=0):
    parts = []
    for name, value in (*terms, ("", constant)):
        if not value:
            continue
        magnitude = abs(value)
        body = ("" if name and magnitude == 1 else str(magnitude)) + name
        sign = "-" if value < 0 else "+"
        parts.append((sign, body))
    if not parts:
        return "0"
    return ("-" if parts[0][0] == "-" else "") + parts[0][1] + "".join(
        f" {sign} {body}" for sign, body in parts[1:])


@dataclass(frozen=True)
class EquationInput:
    label: str
    equation: LinearEquation

    def __post_init__(self):
        if not isinstance(self.label, str) or not _NAME.fullmatch(self.label) or not isinstance(self.equation, LinearEquation):
            raise ValueError("named typed equation required")


@dataclass(frozen=True)
class MathConstraint:
    label: str
    equation: LinearEquation
    source_ids: tuple[str, ...]
    previous_ref: str | None = None

    @property
    def reference(self):
        return "math-premise:" + _hash(asdict(self))


@dataclass(frozen=True)
class MathProof:
    premise_refs: tuple[str, ...]
    weights: tuple[int, ...]
    rule: str = "INTEGER_LINEAR_COMBINATION_V1"

    def __post_init__(self):
        if (self.rule != "INTEGER_LINEAR_COMBINATION_V1"
                or type(self.premise_refs) is not tuple or type(self.weights) is not tuple
                or not 1 <= len(self.weights) <= 4 or len(self.premise_refs) != len(self.weights)
                or len(set(self.premise_refs)) != len(self.premise_refs)
                or not all(isinstance(ref, str) and ref for ref in self.premise_refs)
                or not all(type(w) is int and 0 < abs(w) <= 16 for w in self.weights)):
            raise ValueError("bounded reproducible linear-combination rule required")


@dataclass(frozen=True)
class MathCheck:
    passed: bool
    reason: str
    premise_refs: tuple[str, ...]
    cells_checked: int = 0
    satisfying_assignments: int = 0
    counterexample: tuple[tuple[str, int], ...] = ()
    method: str = "INDEPENDENT_ROW_CERTIFICATE_AND_FINITE_ENTAILMENT_V1"

    @property
    def reference(self):
        return "math-check:" + _hash(asdict(self))


@dataclass(frozen=True)
class MathDeduction:
    equation: LinearEquation
    proof: MathProof
    verification: MathCheck
    isolate_variable: str | None = None

    @property
    def reference(self):
        return "math-deduction:" + _hash(asdict(self))


@dataclass(frozen=True)
class SEMathState(SEState):
    """Typed domain of SEState. Histories append; active views reconstruct."""
    variables: tuple[IntegerVariable, ...] = ()
    constraint_history: tuple[MathConstraint, ...] = ()
    deduction_history: tuple[MathDeduction, ...] = ()

    @property
    def current_constraints(self):
        current = {item.label: item for item in self.constraint_history}
        return tuple(current[label] for label in sorted(current))

    @property
    def active_deductions(self):
        active = {item.reference for item in self.current_constraints}
        result = []
        for item in self.deduction_history:
            if all(ref in active for ref in item.proof.premise_refs):
                active.add(item.reference)
                result.append(item)
        return tuple(result)

    @property
    def invalidated_deductions(self):
        active = {item.reference for item in self.active_deductions}
        return tuple(item for item in self.deduction_history if item.reference not in active)


@dataclass(frozen=True)
class SEMathObservation:
    kind: str  # MATH_MAP, MATH_EXTEND, MATH_DERIVE, MATH_CORRECT
    source: str
    evidence_refs: tuple[str, ...]
    variables: tuple[IntegerVariable, ...] = ()
    equations: tuple[EquationInput, ...] = ()
    proof: MathProof | None = None
    proposed_equation: LinearEquation | None = None
    isolate_variable: str | None = None

    @property
    def observation_id(self):
        return _hash(asdict(self))


def _inputs(state: SEMathState, observation: SEMathObservation):
    if not isinstance(state, SEMathState) or not isinstance(observation, SEMathObservation):
        raise ValueError("typed mathematical state and observation required")
    if (not isinstance(observation.source, str) or type(observation.evidence_refs) is not tuple
            or not all(isinstance(ref, str) and ref for ref in observation.evidence_refs)
            or type(observation.variables) is not tuple or type(observation.equations) is not tuple
            or not all(isinstance(v, IntegerVariable) for v in observation.variables)
            or not all(isinstance(e, EquationInput) for e in observation.equations)):
        raise ValueError("immutable typed mathematical observation required")
    if observation.kind == "MATH_MAP":
        if (state.variables or state.constraint_history or state.deduction_history
                or not 1 <= len(observation.variables) <= 8 or not 1 <= len(observation.equations) <= 32
                or tuple(v.name for v in observation.variables) != tuple(sorted({v.name for v in observation.variables}))
                or len({e.label for e in observation.equations}) != len(observation.equations)):
            raise ValueError("one initial map with unique sorted bounded variables and named premises required")
    elif observation.kind == "MATH_EXTEND":
        if (observation.variables or not state.variables or not 1 <= len(observation.equations) <= 32
                or len({e.label for e in observation.equations}) != len(observation.equations)
                or any(e.label in {c.label for c in state.current_constraints} for e in observation.equations)
                or len(state.current_constraints) + len(observation.equations) > 32):
            raise ValueError("bounded new named premises require an existing map")
    elif observation.kind == "MATH_CORRECT":
        if observation.variables or len(observation.equations) != 1 or not state.variables:
            raise ValueError("one existing constraint correction required")
        item = observation.equations[0]
        old = next((e for e in state.current_constraints if e.label == item.label), None)
        if old is None or old.equation == item.equation:
            raise ValueError("correction must change an existing premise")
    elif observation.kind == "MATH_DERIVE":
        if observation.variables or observation.equations or not isinstance(observation.proof, MathProof) or not state.variables:
            raise ValueError("derivation requires current premises and an exact inference rule")
        if observation.proposed_equation is not None and not isinstance(observation.proposed_equation, LinearEquation):
            raise ValueError("typed proposed equation required")
    else:
        raise ValueError("unsupported mathematical observation")
    if observation.kind != "MATH_DERIVE" and (observation.proof is not None or observation.proposed_equation is not None or observation.isolate_variable is not None):
        raise ValueError("mapping/correction cannot supply a verified deduction")
    variables = observation.variables or state.variables
    names = {v.name for v in variables}
    for item in observation.equations:
        if not set(dict(item.equation.coefficients)) <= names:
            raise ValueError("equation refers to an unmapped variable")


def _premises(state: SEMathState, proof: MathProof):
    available = {item.reference: item for item in (*state.current_constraints, *state.active_deductions)}
    if any(ref not in available for ref in proof.premise_refs):
        raise ValueError("unknown or superseded premise reference")
    return tuple(available[ref] for ref in proof.premise_refs)


def mirror_equations(premises):
    """MIRROR: compare coefficient structure; agreement grants no truth."""
    return tuple({
        "left": left.reference, "right": right.reference,
        "shared_variables": tuple(sorted(set(dict(left.equation.coefficients)) & set(dict(right.equation.coefficients)))),
        "shared_coefficients": tuple((name, dict(left.equation.coefficients)[name], dict(right.equation.coefficients)[name])
            for name in sorted(set(dict(left.equation.coefficients)) & set(dict(right.equation.coefficients))))
    } for left, right in combinations(premises, 2))


def transform_equations(premises, proof: MathProof):
    """General exact row combination; never consults a desired answer."""
    coefficients = {}
    rhs = 0
    for premise, weight in zip(premises, proof.weights, strict=True):
        rhs += weight * premise.equation.rhs
        for name, coefficient in premise.equation.coefficients:
            coefficients[name] = coefficients.get(name, 0) + weight * coefficient
    return LinearEquation.from_coefficients(coefficients, rhs)


def _assignments(variables, names):
    relevant = tuple(v for v in variables if v.name in names)
    if {v.name for v in relevant} != names:
        raise ValueError("unmapped proof variable")
    cells = math.prod(v.upper - v.lower + 1 for v in relevant)
    if cells > MAX_CHECK_CELLS:
        raise ValueError("finite proof resource limit exceeded")
    return cells, (dict(zip((v.name for v in relevant), values, strict=True))
                   for values in product(*(range(v.lower, v.upper + 1) for v in relevant)))


def verify_deduction(state: SEMathState, equation: LinearEquation, proof: MathProof,
                     *, _path: frozenset[str] = frozenset()):
    """Independent checker. Does NOT invoke the candidate transformation.

    Exact row certificate AND non-vacuous finite entailment must pass. Only
    cited premises are considered; unrelated equations cannot rescue a claim.
    """
    try:
        premises = _premises(state, proof)
        for premise in premises:
            if isinstance(premise, MathDeduction):
                if premise.reference in _path or len(_path) >= 32:
                    return MathCheck(False, "CYCLIC_OR_EXCESSIVE_PROOF_DEPTH", proof.premise_refs)
                parent_check = verify_deduction(state, premise.equation, premise.proof,
                                               _path=_path | {premise.reference})
                if not parent_check.passed or parent_check != premise.verification:
                    return MathCheck(False, "UNVERIFIED_OR_TAMPERED_DERIVED_PREMISE", proof.premise_refs)
        names = set(dict(equation.coefficients))
        names.update(name for p in premises for name, _ in p.equation.coefficients)
        # Independent column-wise certificate, distinct from transform's row accumulation.
        for name in names:
            expected = sum(proof.weights[index] * dict(item.equation.coefficients).get(name, 0)
                           for index, item in enumerate(premises))
            if dict(equation.coefficients).get(name, 0) != expected:
                return MathCheck(False, "ROW_CERTIFICATE_MISMATCH", proof.premise_refs)
        if equation.rhs != sum(proof.weights[index] * item.equation.rhs for index, item in enumerate(premises)):
            return MathCheck(False, "ROW_CERTIFICATE_MISMATCH", proof.premise_refs)
        _, assignments = _assignments(state.variables, names)
        witnesses = cells = 0
        for assignment in assignments:
            cells += 1
            if all(item.equation.holds(assignment) for item in premises):
                witnesses += 1
                if not equation.holds(assignment):
                    return MathCheck(False, "COUNTEREXAMPLE", proof.premise_refs, cells, witnesses, tuple(sorted(assignment.items())))
        return MathCheck(bool(witnesses), "MATHEMATICAL_ENTAILMENT_VERIFIED" if witnesses else "INCONSISTENT_OR_EMPTY_PREMISES",
                         proof.premise_refs, cells, witnesses)
    except ValueError as error:
        return MathCheck(False, str(error), proof.premise_refs)


def project_equation(variables, equation: LinearEquation, source_ref: str):
    """PROJECT single-relation domain support, not a complete-system solver."""
    names = set(dict(equation.coefficients))
    cells, assignments = _assignments(variables, names)
    supports = {name: set() for name in names}
    for assignment in assignments:
        if equation.holds(assignment):
            for name, value in assignment.items():
                supports[name].add(value)
    return {"status": "PROJECTED", "source_ref": source_ref,
            "method": "SINGLE_RELATION_DOMAIN_SUPPORT_V1", "cells_checked": cells,
            "domains": tuple({"variable": v.name, "before": (v.lower, v.upper),
                              "supported_values": tuple(sorted(supports[v.name]))}
                             for v in variables if v.name in supports),
            "complete_system_solved": False}


def project_retained(state: SEMathState, deduction_ref: str):
    item = next((d for d in state.active_deductions if d.reference == deduction_ref), None)
    if item is None:
        raise ValueError("projection requires an active retained deduction")
    return project_equation(state.variables, item.equation, item.reference)


def _plan(state: SEMathState, obs: SEMathObservation):
    _inputs(state, obs)
    sources = tuple(sorted(set((*obs.evidence_refs, obs.observation_id))))
    if obs.kind == "MATH_DERIVE":
        premises = _premises(state, obs.proof)
        computed = transform_equations(premises, obs.proof)
        equation = obs.proposed_equation if obs.proposed_equation is not None else computed
        isolated = equation.isolate(obs.isolate_variable) if obs.isolate_variable is not None else None
        check = verify_deduction(state, equation, obs.proof)
        deduction = MathDeduction(equation, obs.proof, check, obs.isolate_variable)
        after = replace(state, deduction_history=(*state.deduction_history, deduction))
        record = {"MIRROR": mirror_equations(premises), "TRANSFORM": asdict(equation),
                  "isolated_relation": isolated, "proof": asdict(obs.proof),
                  "proof_check": asdict(check), "PROJECT": project_equation(state.variables, equation, deduction.reference)}
        return after, (deduction,), premises, record, check
    history = state.constraint_history
    prior = ()
    retained = []
    for item in sorted(obs.equations, key=lambda item: item.label):
        old = next((c for c in state.current_constraints if c.label == item.label), None)
        constraint = MathConstraint(item.label, item.equation, sources, old.reference if old else None)
        retained.append(constraint)
        if old:
            prior = (old,)
    after = replace(state, variables=obs.variables or state.variables, constraint_history=(*history, *retained))
    record = {"MAP": {"variables": tuple(asdict(v) for v in after.variables),
                      "constraints": tuple(asdict(c) for c in retained), "premise_status": "OWNER_SUPPLIED"},
              "correction": {"previous_refs": tuple(c.reference for c in prior),
                             "invalidated": tuple(d.reference for d in after.invalidated_deductions if d not in state.invalidated_deductions),
                             "preserved": tuple(d.reference for d in after.active_deductions)}}
    return after, tuple(retained), prior, record, MathCheck(True, "TYPED_TASK_PREMISES_RETAINED_NOT_WORLD_VERIFIED", tuple(c.reference for c in retained))


def _candidate_record(state, obs, after, prior, stages):
    payload = _json({"schema": SCHEMA, "state_before_hash": state.state_hash,
                     "observation_id": obs.observation_id, "operators": stages,
                     "proposed_mathematics_hash": after.state_hash})
    action = SEAction(obs.kind, payload)
    return SECandidateTransition(state.state_hash, obs.observation_id, None, prior, False, action, payload)


def mathematical_candidate(state, obs):
    after, _, prior, stages, _ = _plan(state, obs)
    return _candidate_record(state, obs, after, prior, stages)


def mathematical_boundary(state, obs, candidate):
    # Rebuild the operator record and binding; don't trust caller payload/check flags.
    after, _, prior, stages, check = _plan(state, obs)
    rebuilt = _candidate_record(state, obs, after, prior, stages)
    if candidate != rebuilt:
        return MathCheck(False, "MATHEMATICAL_CANDIDATE_BINDING_MISMATCH", ())
    return check


def assimilate_mathematics(state, obs):
    after, retained, _, _, check = _plan(state, obs)
    if not check.passed:
        raise ValueError("unverified deduction cannot be assimilated")
    return after, retained, check


def validate_initial_math_state(state):
    # No caller can seed VERIFIED deductions; restoration replays canonical receipts.
    if (type(state.variables) is not tuple or type(state.constraint_history) is not tuple
            or type(state.deduction_history) is not tuple or state.variables
            or state.constraint_history or state.deduction_history or state.relations):
        raise ValueError("mathematical initial state must be empty; map premises through SE.transition")


def math_observation_from_record(data):
    material = dict(data)
    material["evidence_refs"] = tuple(material["evidence_refs"])
    material["variables"] = tuple(IntegerVariable(**v) for v in material["variables"])
    material["equations"] = tuple(EquationInput(e["label"], LinearEquation(
        tuple(tuple(t) for t in e["equation"]["coefficients"]), e["equation"]["rhs"])) for e in material["equations"])
    if material["proof"] is not None:
        p = material["proof"]
        material["proof"] = MathProof(tuple(p["premise_refs"]), tuple(p["weights"]), p["rule"])
    if material["proposed_equation"] is not None:
        e = material["proposed_equation"]
        material["proposed_equation"] = LinearEquation(tuple(tuple(t) for t in e["coefficients"]), e["rhs"])
    return SEMathObservation(**material)
