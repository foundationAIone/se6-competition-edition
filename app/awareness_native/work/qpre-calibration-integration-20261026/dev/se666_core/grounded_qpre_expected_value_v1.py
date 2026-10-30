"""SE6 exact QPRE probability -> bounded expected-value evidence, development v1.

NO authority, World effects, Entity writes, gate overrides, or adoption of the
owner equation. This is conditional arithmetic on a real validated, hash-bound
QPREProbabilityRender and an *explicitly declared* utility policy. Arithmetic
intervals are exact conditional on those declarations; QPRE probability bands
are NOT statistically guaranteed coverage intervals.

Supports mutually exclusive EXHAUSTIVE / OPEN_WORLD distributions only;
OVERLAPPING marginals cannot generally price nonlinear/joint outcomes.
Unknown OUTSIDE-OF-FIELD utility must be bounded explicitly, not zeroed.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from hashlib import sha256
from typing import Sequence
import json
import re

from .qpre_calibration_v1 import (
    QPREProbabilityRender, DistributionSemantics, ProbabilityBasis, TOTAL,
)

VERSION = 'se6-qpre-exact-conditional-value-shadow-v1'
_SHA = re.compile(r'^[0-9a-f]{64}$')
_MAX = F(1_000_000)


class ValueRefusal(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise ValueRefusal(code)


def _ref(value):
    need(type(value) is str and 0 < len(value) <= 256 and
         re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*',value) is not None,
         'VALUE_REFERENCE_REQUIRED')


def _f(value):
    need(type(value) is F and value.denominator <= 10**12 and
         abs(value) <= _MAX, 'VALUE_EXACT_BOUNDED_RATIONAL_REQUIRED')
    return value


def _rat(value):
    return [value.numerator,value.denominator]


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                             ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ValueInterval:
    """Exact, source-declared valuation band in ONE specified unit."""
    lower: F
    point: F
    upper: F

    def __post_init__(self):
        for v in (self.lower,self.point,self.upper):_f(v)
        need(self.lower <= self.point <= self.upper,'VALUE_INTERVAL_ORDER')

    def wire(self):
        return {'lo':_rat(self.lower),'point':_rat(self.point), 'hi':_rat(self.upper)}


@dataclass(frozen=True)
class CandidateValue:
    candidate_id: str
    outcome_values: tuple[tuple[str,ValueInterval],...]
    other_value: ValueInterval | None
    # Penalty is explicitly declared (cost/risk/irreversibility in same units).
    penalty: ValueInterval

    def __post_init__(self):
        _ref(self.candidate_id)
        need(type(self.outcome_values) is tuple and 1 <= len(self.outcome_values)<=64,
             'VALUE_OUTCOME_CATALOG_BOUNDS')
        names=[]
        for entry in self.outcome_values:
            need(type(entry) is tuple and len(entry)==2 and
                 type(entry[1]) is ValueInterval,'VALUE_TYPED_OUTCOME')
            _ref(entry[0]); names.append(entry[0])
        need(len(names)==len(set(names)),'VALUE_DUPLICATE_OUTCOME')
        need(self.other_value is None or type(self.other_value) is ValueInterval,
             'VALUE_OUTSIDE_BOUNDS_REQUIRED')
        need(type(self.penalty) is ValueInterval and self.penalty.lower>=0,
             'VALUE_NONNEGATIVE_PENALTY')

    def wire(self):
        return {'candidate_id':self.candidate_id,
                'outcomes':[[k,v.wire()] for k,v in self.outcome_values],
                'outside_field':None if self.other_value is None else self.other_value.wire(),
                'penalty':self.penalty.wire()}


@dataclass(frozen=True)
class ValuePolicy:
    source_state_hash: str
    frame_hash: str
    probability_render_id: str
    model_version: str
    calibration_state_hash: str
    # Host must independently authenticate this declaration before allowing
    # it to influence an authoritative decision. Presence of ref is not proof.
    declaration_reference: str
    unit_reference: str
    values: tuple[CandidateValue,...]
    policy_sha256: str

    def material(self):
        return dict(version=VERSION,source_state_hash=self.source_state_hash,
                    frame_hash=self.frame_hash,probability_render_id=self.probability_render_id,
                    model_version=self.model_version,
                    calibration_state_hash=self.calibration_state_hash,
                    declaration_reference=self.declaration_reference,
                    unit_reference=self.unit_reference,
                    values=[v.wire() for v in self.values])

    def validate(self):
        need(_SHA.fullmatch(self.source_state_hash) is not None and
             _SHA.fullmatch(self.frame_hash) is not None and
             _SHA.fullmatch(self.calibration_state_hash) is not None,
             'VALUE_SOURCE_HASH_REQUIRED')
        for ref in (self.probability_render_id,self.model_version,
                    self.declaration_reference,self.unit_reference):_ref(ref)
        need(type(self.values) is tuple and 1<=len(self.values)<=64 and
             all(type(v) is CandidateValue for v in self.values),
             'VALUE_TYPED_COMPLETE_CANDIDATES')
        need(len({v.candidate_id for v in self.values})==len(self.values),
             'VALUE_DUPLICATE_CANDIDATES')
        need(type(self.policy_sha256) is str and self.policy_sha256==_hash(self.material()),
             'VALUE_POLICY_HASH_CHANGED')


def build_policy(render: QPREProbabilityRender, *, declaration_reference: str,
                 unit_reference: str, values: Sequence[CandidateValue]) -> ValuePolicy:
    need(type(render) is QPREProbabilityRender,'VALUE_RENDER_REQUIRED')
    render=QPREProbabilityRender.model_validate_json(render.model_dump_json())
    need(type(values) in (tuple,list),'VALUE_CANDIDATE_LIST_REQUIRED')
    material=dict(source_state_hash=render.base_render.source_state_hash,
        frame_hash=render.base_render.frame_hash,probability_render_id=render.render_id,
        model_version=render.model_version,calibration_state_hash=render.calibration_state_hash,
        declaration_reference=declaration_reference,unit_reference=unit_reference,
        values=tuple(values))
    draft=ValuePolicy(policy_sha256='',**material)
    policy=ValuePolicy(policy_sha256=_hash(draft.material()),**material)
    policy.validate()
    return policy


def _mul_interval(prob_lo:F, prob_hi:F, value:ValueInterval):
    choices=(prob_lo*value.lower,prob_lo*value.upper,
             prob_hi*value.lower,prob_hi*value.upper)
    return min(choices),max(choices)


def _value_for(distribution, policy: CandidateValue):
    need(distribution.candidate_id==policy.candidate_id,'VALUE_CANDIDATE_MISMATCH')
    need(distribution.semantics is not DistributionSemantics.OVERLAPPING,
         'VALUE_OVERLAPPING_REQUIRES_EXPLICIT_JOINT_OR_ADDITIVE_MARGINAL_MODEL')
    need({k for k,_ in policy.outcome_values}=={p.outcome_id for p in distribution.outcomes},
         'VALUE_OUTCOME_CATALOG_NOT_BOUND')
    need((distribution.semantics is DistributionSemantics.OPEN_WORLD)==
         (policy.other_value is not None), 'VALUE_OPEN_WORLD_NEEDS_OUTSIDE_UTILITY')
    by_id=dict(policy.outcome_values)
    p_total=F(0);lower=F(0);upper=F(0);known_low=0;known_high=0
    for outcome in distribution.outcomes:
        need(outcome.basis is not ProbabilityBasis.UNCALIBRATED and
             type(outcome.point_bp) is int,
             'VALUE_UNCALIBRATED_DISTRIBUTION')
        band=by_id[outcome.outcome_id]
        p=F(outcome.point_bp,TOTAL)
        low=F(outcome.lower_bp,TOTAL)
        high=F(outcome.upper_bp,TOTAL)
        l,h=_mul_interval(low,high,band)
        lower+=l;upper+=h;p_total+=p*band.point
        known_low+=outcome.lower_bp;known_high+=outcome.upper_bp
    if distribution.semantics is DistributionSemantics.OPEN_WORLD:
        need(type(distribution.residual_bp) is int,
             'VALUE_RESIDUAL_MASS_REQUIRED')
        # Coherent conservative bounds from the simplex constraints, even
        # though the source contract only supplies a residual *point* mass.
        res_lo=F(max(0,TOTAL-known_high),TOTAL)
        res_hi=F(min(TOTAL,TOTAL-known_low),TOTAL)
        res_point=F(distribution.residual_bp,TOTAL)
        need(res_lo<=res_point<=res_hi,'VALUE_RESIDUAL_MASS_INCOHERENT')
        l,h=_mul_interval(res_lo,res_hi,policy.other_value)
        lower+=l;upper+=h;p_total+=res_point*policy.other_value.point
    lower-=policy.penalty.upper
    upper-=policy.penalty.lower
    p_total-=policy.penalty.point
    need(lower<=p_total<=upper,'VALUE_ARITHMETIC_BAND_INCOHERENT')
    return ValueInterval(lower,p_total,upper)


def evaluate_shadow(*, render:QPREProbabilityRender,policy:ValuePolicy,
                    eligible_candidate_ids:tuple[str,...],
                    eligibility_provenance:str, minimum_lower_gain:F=F(0))->dict:
    """Compute exact conditional arithmetic. NEVER ALLOW, REFUSE or execute.

    `eligible_candidate_ids` is the caller's already-filtered candidate set;
    this calculation cannot create a new eligible candidate or grant authority.
    In particular, its `CERTIFIED_INTERVAL_LEADER` is a conditional
    mathematical observation, NOT an authorized decision.
    """
    need(type(render) is QPREProbabilityRender and type(policy) is ValuePolicy,
         'VALUE_QPRE_AND_POLICY_REQUIRED')
    render=QPREProbabilityRender.model_validate_json(render.model_dump_json())
    policy.validate()
    _ref(eligibility_provenance)
    _f(minimum_lower_gain)
    need(policy.probability_render_id==render.render_id and
         policy.source_state_hash==render.base_render.source_state_hash and
         policy.frame_hash==render.base_render.frame_hash and
         policy.model_version==render.model_version and
         policy.calibration_state_hash==render.calibration_state_hash,
         'VALUE_EXACT_QPRE_CALIBRATION_BINDING_MISMATCH')
    candidates={d.candidate_id:d for d in render.distributions}
    valuations={v.candidate_id:v for v in policy.values}
    need(set(candidates)==set(valuations), 'VALUE_ALL_RENDER_CANDIDATES_MUST_BE_VALUED')
    need(type(eligible_candidate_ids) is tuple and
         len(eligible_candidate_ids)==len(set(eligible_candidate_ids)) and
         set(eligible_candidate_ids).issubset(candidates),
         'VALUE_CANNOT_WIDEN_BOUNDARY_ELIGIBILITY')
    estimates={cid:_value_for(distribution,valuations[cid])
               for cid,distribution in candidates.items()}
    eligible=sorted(eligible_candidate_ids)
    status='NO_ELIGIBLE';winner=None;reason='BOUNDARY_ADMITTED_SET_EMPTY'
    if eligible:
        qualified=[cid for cid in eligible if estimates[cid].lower>minimum_lower_gain]
        if not qualified:
            status='ABSTAIN';reason='NO_STRICTLY_POSITIVE_CERTIFIED_LOWER_GAIN'
        else:
            leaders=[cid for cid in qualified if all(
                estimates[cid].lower>estimates[other].upper
                for other in eligible if other!=cid)]
            if len(leaders)==1:
                status='CERTIFIED_INTERVAL_LEADER';winner=leaders[0]
                reason='STRICT_CONDITIONAL_INTERVAL_DOMINANCE'
            else:
                status='ABSTAIN';reason='OVERLAPPING_OR_INDETERMINATE_INTERVALS'
    material=dict(version=VERSION,status=status,reason=reason,winner=winner,
        authority_effect='NONE',production_eligible=False,world_effect=False,
        full_owner_equation_equivalence=False,statistical_coverage_proven=False,
        source_state_hash=policy.source_state_hash,frame_hash=policy.frame_hash,
        probability_render_id=render.render_id,
        calibration_state_hash=render.calibration_state_hash,
        policy_sha256=policy.policy_sha256,unit_reference=policy.unit_reference,
        declaration_reference=policy.declaration_reference,
        eligibility_provenance=eligibility_provenance,
        eligible_candidate_ids=eligible,
        arithmetic_scope='CONDITIONAL_EXACT_EXPECTATION_OF_DECLARED_FINITE_UTILITIES',
        estimates={k:estimates[k].wire() for k in sorted(estimates)},
        minimum_lower_gain=_rat(minimum_lower_gain))
    material['result_sha256']=_hash(material)
    return material


__all__=['VERSION','ValueRefusal','ValueInterval','CandidateValue',
         'ValuePolicy','build_policy','evaluate_shadow']
