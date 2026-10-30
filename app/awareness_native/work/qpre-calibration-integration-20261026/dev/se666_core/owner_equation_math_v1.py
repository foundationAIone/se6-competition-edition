"""SE6-MATH-COMPLETION-v1: reference semantics for a bounded admitted domain.

NOT the September owner equation and NOT production SE6. This module explicitly
selects an operator-combination law that was previously undefined. It provides
an executable, typed mathematical *candidate* for review, with zero I/O,
zero authority, and no direct World action.

The information field and operators are bounded finite-dimensional data. V6's
independent World/verification requirements remain outside this pure model.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
import json
import math
from typing import Callable

CONTRACT = "se6-math-completion-v1.0.0-development-proposal"
STAGES = ("FLOWER", "ETHICAL_PROJECTION", "KNOWLEDGE", "MERKABAH_ADJOINT", "CUBE_STABILIZATION")
MAX_DIM = 12
MAX_POINTS = 128
MAX_HORIZON = 96
MAX_INTEGER_ABS = 10**9


def exact(value) -> Fraction:
    if type(value) is int:
        value = Fraction(value)
    if type(value) is not Fraction or abs(value.numerator) > MAX_INTEGER_ABS or value.denominator > MAX_INTEGER_ABS:
        raise ValueError("BOUNDED_RATIONAL_REQUIRED")
    return value


def scalar_decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def vec(values) -> tuple[Fraction, ...]:
    if type(values) is not tuple or not 1 <= len(values) <= MAX_DIM:
        raise ValueError("BOUNDED_VECTOR_REQUIRED")
    return tuple(exact(v) for v in values)


def vector_add(a, b):
    if len(a) != len(b):
        raise ValueError("VECTOR_DOMAIN_MISMATCH")
    return tuple(x + y for x, y in zip(a, b))


def vector_scale(c, a):
    return tuple(c * x for x in a)


def dot(a, b):
    if len(a) != len(b):
        raise ValueError("DOT_DIMENSION_MISMATCH")
    return sum((x*y for x, y in zip(a, b)), Fraction())


@dataclass(frozen=True)
class Linear:
    """Rational linear map; all operator symbols are mathematical, not authority."""
    rows: tuple[tuple[Fraction, ...], ...]

    def __post_init__(self):
        if type(self.rows) is not tuple or not 1 <= len(self.rows) <= MAX_DIM:
            raise ValueError("MATRIX_ROWS")
        n = len(self.rows)
        if any(type(row) is not tuple or len(row) != n for row in self.rows):
            raise ValueError("MATRIX_MUST_BE_SQUARE")
        for row in self.rows:
            for v in row:
                exact(v)

    @property
    def dimension(self):
        return len(self.rows)

    def apply(self, v):
        v = vec(v)
        if len(v) != self.dimension:
            raise ValueError("MATRIX_VECTOR_DOMAIN")
        return tuple(dot(row, v) for row in self.rows)

    def transpose(self):
        return Linear(tuple(tuple(row[j] for row in self.rows) for j in range(self.dimension)))

    def then(self, successor: "Linear"):
        if self.dimension != successor.dimension:
            raise ValueError("MATRIX_COMPOSE_DOMAIN")
        return Linear(tuple(
            tuple(sum((successor.rows[i][k]*self.rows[k][j] for k in range(self.dimension)), Fraction())
                  for j in range(self.dimension))
            for i in range(self.dimension)))

    def is_projection(self):
        return self.then(self) == self and self.transpose() == self

    @classmethod
    def identity(cls, n):
        if type(n) is not int or not 1 <= n <= MAX_DIM:
            raise ValueError("IDENTITY_DIMENSION")
        return cls(tuple(tuple(Fraction(int(i == j)) for j in range(n)) for i in range(n)))


def _canonical(value):
    if isinstance(value, Fraction):
        return {"num": value.numerator, "den": value.denominator}
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Linear):
        return _canonical(value.rows)
    if isinstance(value, tuple):
        return [_canonical(v) for v in value]
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical type: {type(value).__name__}")


def digest(value):
    return sha256(json.dumps(_canonical(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class OperatorSet:
    flower: Linear
    ethical_projection: Linear
    knowledge: Linear
    merkabah_forward: Linear
    cube_stabilizer: Linear

    def __post_init__(self):
        dims = {x.dimension for x in (self.flower, self.ethical_projection,
                                     self.knowledge, self.merkabah_forward, self.cube_stabilizer)}
        if len(dims) != 1:
            raise ValueError("FIVE_OPERATOR_DOMAIN_MISMATCH")
        if not self.ethical_projection.is_projection() or not self.cube_stabilizer.is_projection():
            raise ValueError("ETHICAL_AND_CUBE_PROJECTIONS_REQUIRED")

    @property
    def dimension(self):
        return self.flower.dimension

    def fold(self, h):
        """A *declared new law*: T* ∘ G† ∘ K ∘ Eeth ∘ Phi applied to H.

        G† is the actual transpose with respect to the Euclidean inner product;
        T* is a symmetric idempotent stabilizing projection. Preliminary ethical
        projection is NOT the authoritative Four Pillars / Master Boundary.
        """
        h = vec(h)
        trace = (h,)
        for op in (self.flower, self.ethical_projection, self.knowledge,
                   self.merkabah_forward.transpose(), self.cube_stabilizer):
            h = op.apply(h)
            trace += (h,)
        return h, trace


@dataclass(frozen=True)
class FieldPoint:
    identifier: str
    source_ref: str
    h: tuple[Fraction, ...]
    mass: Fraction
    epistemic_status: str = "REPORTED"

    def __post_init__(self):
        if not self.identifier or not self.source_ref or self.epistemic_status not in ("REPORTED", "VERIFIED", "PREDICTED"):
            raise ValueError("SOURCE_BOUND_FIELD_POINT")
        vec(self.h)
        if exact(self.mass) < 0:
            raise ValueError("NEGATIVE_MEASURE")


@dataclass(frozen=True)
class Policy:
    """Declared domain of the owner integral (no automatic canonical adoption)."""
    eps: Decimal
    arbitration: Decimal
    eta: Fraction
    rho: Fraction
    gamma: Fraction
    beta: Fraction
    utility_bound: Fraction
    utility_bound_ref: str
    max_information_gain: Decimal = Decimal("100")

    def __post_init__(self):
        if type(self.eps) is not Decimal or not self.eps.is_finite() or not Decimal(0) < self.eps <= Decimal(1):
            raise ValueError("POSITIVE_ARBITRATION_REGULARIZER")
        if (type(self.arbitration) is not Decimal or not self.arbitration.is_finite()
                or abs(self.arbitration) > 12):
            raise ValueError("BOUNDED_ARBITRATION_INTENSITY")
        for x in (self.eta, self.rho, self.gamma, self.beta, self.utility_bound):
            exact(x)
        if not Fraction() < self.beta < Fraction(1):
            raise ValueError("DISCOUNT_MUST_BE_BETWEEN_ZERO_AND_ONE")
        if self.utility_bound < 0 or not self.utility_bound_ref:
            raise ValueError("SOURCE_BOUND_FUTURE_UTILITY_CAP")
        if (type(self.max_information_gain) is not Decimal or not self.max_information_gain.is_finite()
                or self.max_information_gain <= 0 or self.max_information_gain > Decimal("1000000")):
            raise ValueError("DECLARED_INFORMATION_AMPLIFICATION_CAP")

    def denominator(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 60
            # sech²(x)=4/(exp(x)+exp(-x))² is stable near tanh saturation.
            ex = self.arbitration.exp()
            sech2 = Decimal(4) / (ex + (Decimal(1)/ex))**2
            d = (self.eps + sech2).sqrt()
            if not d.is_finite() or d <= 0 or d*d < self.eps - Decimal('1e-55'):
                raise ValueError("ARBITRATION_DENOMINATOR_INVALID")
            return +d


@dataclass(frozen=True)
class Contribution:
    """All additive owner terms live in this declared proposal-vector space."""
    base_ref: str
    inherited: tuple[Fraction, ...]
    field: tuple[FieldPoint, ...]
    self_model: tuple[Fraction, ...]
    self_source_ref: str
    projected_utility: tuple[tuple[Fraction, ...], ...]

    def __post_init__(self):
        if not self.base_ref or not self.self_source_ref:
            raise ValueError("STATE_AND_SELF_SOURCE_REQUIRED")
        vec(self.inherited)
        vec(self.self_model)
        if len(self.field) > MAX_POINTS or len(self.projected_utility) > MAX_HORIZON:
            raise ValueError("FIELD_OR_HORIZON_CAP")
        ids = [p.identifier for p in self.field]
        if len(set(ids)) != len(ids):
            raise ValueError("DUPLICATE_INFORMATION_FIELD_ID")
        for p in self.field:
            if len(p.h) != len(self.inherited):
                raise ValueError("H_FIELD_DIMENSION_MISMATCH")
        for u in self.projected_utility:
            if vec(u) != u or len(u) != len(self.inherited):
                raise ValueError("FUTURE_UTILITY_DIMENSION_MISMATCH")
        if len(self.self_model) != len(self.inherited):
            raise ValueError("SELF_DOMAIN_MISMATCH")


@dataclass(frozen=True)
class EvaluatedProposal:
    base_ref: str
    actualized: bool
    vector: tuple[Decimal, ...]
    uncertainty_radius: Decimal
    terms: dict
    stage_traces: tuple[dict, ...]
    proposal_hash: str


def evaluate(ops: OperatorSet, p: Policy, c: Contribution) -> EvaluatedProposal:
    """Exact rational finite integration and bounded discounted sum; Decimal
    transcendental normalization. No World operation, no permission, no commit.
    """
    n = ops.dimension
    if n != len(c.inherited):
        raise ValueError("OWNER_TOTAL_STATE_OPERATOR_DOMAIN")
    with localcontext() as ctx:
        ctx.prec = 60
        field = (Fraction(),)*n
        traces = []
        for item in c.field:
            transformed, steps = ops.fold(item.h)
            field = vector_add(field, vector_scale(item.mass, transformed))
            traces.append({"evidence": item.identifier, "source_ref": item.source_ref,
                           "epistemic_status": item.epistemic_status,
                           "stages": dict(zip(("H",)+STAGES, steps)),
                           "stage_hash": digest(steps)})
        future = (Fraction(),)*n
        for tau, u in enumerate(c.projected_utility, 1):
            if any(abs(x) > p.utility_bound for x in u):
                raise ValueError("PROJECTED_UTILITY_EXCEEDS_CERTIFIED_BOUND")
            future = vector_add(future, vector_scale(p.beta**tau, u))
        horizon = len(c.projected_utility)
        tail = abs(p.gamma)*p.utility_bound*p.beta**(horizon+1)/(1-p.beta)
        d = p.denominator()
        # The given normalization *amplifies* the field as |I| increases.
        # Preserve the original denominator, but require an explicit external
        # bound on that amplification before scoring a proposed action.
        if Decimal(1)/d > p.max_information_gain:
            raise ValueError("ARBITRATION_NORMALIZATION_GAIN_EXCEEDS_BOUND")
        out = tuple(
            scalar_decimal(c.inherited[i])
            + scalar_decimal(p.eta*field[i])/d
            + scalar_decimal(p.rho*c.self_model[i])
            + scalar_decimal(p.gamma*future[i])
            for i in range(n))
        terms = {"inherited": c.inherited, "field_integral_numerator": field,
                 "normalizer": d, "normalization_gain": Decimal(1)/d,
                 "arbitration": p.arbitration, "max_information_gain": p.max_information_gain,
                 "self_model": c.self_model,
                 "future_prefix": future, "future_horizon": horizon,
                 "future_tail_bound_per_coordinate": tail,
                 "utility_bound_source": p.utility_bound_ref,
                 "self_source": c.self_source_ref,
                 "operator_contract": CONTRACT,
                 "formula_law": "ORDERED_TYPED_COMPOSITION"}
        proto = {"base_ref": c.base_ref, "vector": out, "radius": tail,
                 "terms": terms, "traces": traces}
        return EvaluatedProposal(
            c.base_ref, False, tuple(+v for v in out),
            +scalar_decimal(tail), terms, tuple(traces), digest(proto))


@dataclass(frozen=True)
class Action:
    identifier: str
    evaluation: EvaluatedProposal
    valuation: tuple[Fraction, ...]
    cost: Fraction
    risk: Fraction
    irreversibility: Fraction
    conduct: tuple[bool, bool, bool, bool]

    def __post_init__(self):
        if not self.identifier or not self.evaluation.proposal_hash:
            raise ValueError("ACTION_ID_REQUIRED")
        vec(self.valuation)
        if len(self.valuation) != len(self.evaluation.vector):
            raise ValueError("ACTION_VALUATION_DOMAIN")
        if not all(type(v) is bool for v in self.conduct) or len(self.conduct) != 4:
            raise ValueError("FOUR_PILLARS_REQUIRED")
        for x in (self.cost, self.risk, self.irreversibility):
            if exact(x) < 0:
                raise ValueError("COST_RISK_IRREVERSIBILITY_NONNEGATIVE")

    def score(self):
        with localcontext() as ctx:
            ctx.prec = 60
            value = sum((v * scalar_decimal(w) for v, w in zip(self.evaluation.vector, self.valuation)), Decimal())
            score = value - sum((scalar_decimal(v) for v in (self.cost, self.risk, self.irreversibility)), Decimal())
            # Components of unknown discounted future can independently move by tail.
            radius = self.evaluation.uncertainty_radius * sum((abs(scalar_decimal(x)) for x in self.valuation), Decimal())
            return score, radius


@dataclass(frozen=True)
class Selection:
    status: str
    action_id: str | None
    candidate_hash: str | None
    reason: str


def choose(actions: tuple[Action, ...], *, base_ref: str, eligible: frozenset[str]) -> Selection:
    """Eligibility is independently supplied; it is never inferred from utility."""
    if type(actions) is not tuple or type(eligible) is not frozenset or not base_ref:
        raise ValueError("BOUNDED_SELECTION_ARGUMENT")
    names = [a.identifier for a in actions]
    if len(set(names)) != len(names):
        raise ValueError("DUPLICATE_CANDIDATE_ID")
    if any(a.evaluation.base_ref != base_ref for a in actions):
        raise ValueError("STATE_ANCESTRY_MISMATCH")
    admissible = [a for a in actions if a.identifier in eligible and all(a.conduct)]
    if not admissible:
        return Selection("REFUSE", None, None, "NO_BOUNDARY_AND_CONDUCT_ADMISSIBLE_ACTION")
    scores = {a.identifier: a.score() for a in admissible}
    # Deterministic order agrees with V6's low-risk/low-cost tie preference.
    ordered = sorted(admissible, key=lambda a: (
        -scores[a.identifier][0], a.irreversibility, a.risk, a.cost, a.evaluation.proposal_hash, a.identifier))
    top = ordered[0]
    if len(ordered) > 1:
        top_score, top_rad = scores[top.identifier]
        for competitor in ordered[1:]:
            other_score, other_rad = scores[competitor.identifier]
            if top_score - top_rad <= other_score + other_rad:
                # Exact same scores + *zero* uncertainty may use the declared tie rule.
                if not (top_score == other_score and top_rad == other_rad == 0):
                    return Selection("PAUSE", None, None, "FUTURE_UTILITY_BOUND_OVERLAP")
    return Selection("PROPOSED", top.identifier, top.evaluation.proposal_hash,
                     "ELIGIBLE_DETERMINISTIC_SELECTION_NOT_WORLD_TRUTH")


def verify_return_renewal(*, decision: Selection, source_ref: str,
                          witnessed_action: str | None, independently_verified: bool,
                          final_gate_allowed: bool, cold_restore_evidence: bool) -> str:
    """Pure proof-obligation checker. It does not issue authority or commit.

    Live V4 coordinator owns the real independently authenticated witness,
    state CAS and durable writes. This checker is intentionally incapable of
    constructing a World receipt or changing Entity state.
    """
    if decision.status != "PROPOSED" or decision.action_id is None:
        return "REFUSE_NO_ELIGIBLE_SELECTION"
    if not source_ref or witnessed_action != decision.action_id:
        return "REFUSE_WITNESS_NOT_BOUND"
    if not independently_verified:
        return "REFUSE_WORLD_UNVERIFIED"
    if not final_gate_allowed:
        return "REFUSE_FINAL_BOUNDARY"
    if not cold_restore_evidence:
        return "UNKNOWN_DURABLE_RENEWAL"
    return "CONDITIONAL_RETURN_RENEWAL_OBLIGATIONS_MET"
