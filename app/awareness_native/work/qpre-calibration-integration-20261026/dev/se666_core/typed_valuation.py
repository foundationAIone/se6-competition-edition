"""Exact typed valuation declarations and partial numeric order; no authority.

Units and conversion factors are supplied mathematical declarations. A caller
must authenticate their source, policy scope/revision and authorization before
using them for a decision. This module cannot authenticate an owner, choose
preferences, grant ALLOW or make a World outcome true. Unit identity is not
collapsed merely because dimensions happen to match.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import re

VERSION = 'se6-typed-valuation-quantity-v1'
EXPECTATION_RULE = 'FINITE_EXCLUSIVE_SIMPLEX_EXPECTATION_V1'
KINDS = frozenset({'UTILITY', 'RESOURCE', 'COST', 'RISK', 'COUNT', 'MEASUREMENT', 'PROBABILITY'})
_REF = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$')


class TypedValuationRefusal(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise TypedValuationRefusal(code)


def _ref(value):
    need(type(value) is str and _REF.fullmatch(value) is not None, 'TYPED_VALUE_REFERENCE')


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _exact(value):
    need(type(value) is F and value.denominator <= 10**12 and abs(value) <= 10**12 and
        max(abs(value.numerator).bit_length(), value.denominator.bit_length()) <= 4096,
        'TYPED_VALUE_EXACT_BOUNDED_RATIONAL')
    return value


def rational_wire(value):
    value = _exact(value)
    return [value.numerator, value.denominator]


def rational_from_wire(value):
    need(type(value) is list and len(value) == 2 and all(type(n) is int for n in value)
        and value[1] > 0, 'TYPED_VALUE_RATIONAL_WIRE')
    result = _exact(F(*value))
    need(value == rational_wire(result), 'TYPED_VALUE_CANONICAL_RATIONAL')
    return result


def validate_unit(unit):
    need(type(unit) is dict and set(unit) == {'id', 'kind', 'dimension'}, 'TYPED_VALUE_UNIT_FIELDS')
    _ref(unit['id'])
    need(type(unit['kind']) is str and unit['kind'] in KINDS, 'TYPED_VALUE_UNIT_KIND')
    dims = unit['dimension']
    need(type(dims) is list and len(dims) <= 16 and all(type(r) is list and len(r) == 2 for r in dims),
        'TYPED_VALUE_DIMENSION_FIELDS')
    for name, power in dims:
        _ref(name)
        need(type(power) is int and 0 < abs(power) <= 16, 'TYPED_VALUE_DIMENSION_POWER')
    need(dims == sorted(dims) and len({r[0] for r in dims}) == len(dims), 'TYPED_VALUE_CANONICAL_DIMENSION')
    need(unit['kind'] != 'PROBABILITY' or not dims, 'TYPED_VALUE_PROBABILITY_DIMENSIONLESS')
    return unit


def interval_from_wire(value):
    need(type(value) is dict and set(value) == {'lo', 'point', 'hi'}, 'TYPED_VALUE_INTERVAL_FIELDS')
    result = tuple(rational_from_wire(value[k]) for k in ('lo', 'point', 'hi'))
    need(result[0] <= result[1] <= result[2], 'TYPED_VALUE_INTERVAL_ORDER')
    return result


def make_quantity(*, unit, lower, point, upper, source_identity, provenance, policy_revision, scope):
    validate_unit(unit)
    for value in (source_identity, policy_revision, scope):
        _ref(value)
    need(type(provenance) in (list, tuple) and 0 < len(provenance) <= 128, 'TYPED_VALUE_PROVENANCE')
    for ref in provenance:
        _ref(ref)
    values = tuple(_exact(value) for value in (lower, point, upper))
    need(values[0] <= values[1] <= values[2], 'TYPED_VALUE_INTERVAL_ORDER')
    if unit['kind'] == 'PROBABILITY':
        need(F(0) <= lower <= upper <= F(1), 'TYPED_VALUE_PROBABILITY_RANGE')
    material = dict(version=VERSION, source_identity=source_identity, unit=deepcopy(unit),
        interval={k:rational_wire(v) for k,v in zip(('lo', 'point', 'hi'),values)},
        provenance=sorted(set(provenance)), policy_revision=policy_revision, scope=scope)
    return {**material, 'quantity_sha256':_hash(material)}


def validate_quantity(quantity):
    need(type(quantity) is dict and set(quantity) == {'version', 'source_identity', 'unit', 'interval',
        'provenance', 'policy_revision', 'scope', 'quantity_sha256'}, 'TYPED_VALUE_QUANTITY_FIELDS')
    need(quantity['version'] == VERSION, 'TYPED_VALUE_VERSION')
    lo, point, hi = interval_from_wire(quantity['interval'])
    expected = make_quantity(unit=quantity['unit'], lower=lo, point=point, upper=hi,
        source_identity=quantity['source_identity'], provenance=quantity['provenance'],
        policy_revision=quantity['policy_revision'], scope=quantity['scope'])
    need(expected == quantity, 'TYPED_VALUE_QUANTITY_CONTENT')
    return quantity


def _same_context(left, right):
    need(all(left[k] == right[k] for k in ('source_identity', 'policy_revision', 'scope')),
        'TYPED_VALUE_SOURCE_SCOPE_REVISION')


def _compatible(left, right):
    validate_quantity(left); validate_quantity(right)
    _same_context(left, right)
    need(left['unit'] == right['unit'], 'TYPED_VALUE_IDENTICAL_UNIT_REQUIRED')


def _result(quantity, values, provenance, unit=None):
    return make_quantity(unit=unit or quantity['unit'], lower=values[0], point=values[1], upper=values[2],
        source_identity=quantity['source_identity'], provenance=provenance,
        policy_revision=quantity['policy_revision'], scope=quantity['scope'])


def add_quantities(left, right):
    _compatible(left, right)
    need(left['unit']['kind'] != 'PROBABILITY', 'TYPED_VALUE_PROBABILITY_SUM_NEEDS_EVENT_CONTRACT')
    values = tuple(a+b for a,b in zip(interval_from_wire(left['interval']), interval_from_wire(right['interval'])))
    return _result(left, values, left['provenance']+right['provenance']+
        ['typed-add:'+_hash([left['quantity_sha256'],right['quantity_sha256']])])


def scale_probability(quantity, probability):
    """Multiply a typed quantity by a declared dimensionless probability band.

    A Fraction gives a point probability; an interval wire gives uncertainty.
    It is not an operation on permission tokens or a joint-probability model.
    """
    validate_quantity(quantity)
    need(quantity['unit']['kind'] != 'PROBABILITY', 'TYPED_VALUE_PROBABILITY_PRODUCT_NEEDS_JOINT_MODEL')
    p = (probability,)*3 if type(probability) is F else interval_from_wire(probability)
    need(all(type(v) is F for v in p) and F(0) <= p[0] <= p[1] <= p[2] <= F(1), 'TYPED_VALUE_PROBABILITY_RANGE')
    for value in p:
        _exact(value)
    lo, point, hi = interval_from_wire(quantity['interval'])
    products = [a*b for a in (lo,hi) for b in (p[0],p[2])]
    return _result(quantity, (min(products),point*p[1],max(products)), quantity['provenance']+
        ['typed-probability-product:'+_hash([quantity['quantity_sha256'],[rational_wire(v) for v in p]])])


def validate_conversion(conversion):
    need(type(conversion) is dict and set(conversion) == {'source_unit', 'target_unit', 'factor', 'reference'},
        'TYPED_VALUE_CONVERSION_FIELDS')
    source=validate_unit(conversion['source_unit']); target=validate_unit(conversion['target_unit'])
    need(source['kind']==target['kind'] and source['dimension']==target['dimension'],
        'TYPED_VALUE_CONVERSION_DIMENSION_OR_KIND')
    need(source['kind'] != 'PROBABILITY', 'TYPED_VALUE_PROBABILITY_CONVERSION_UNSUPPORTED')
    factor=rational_from_wire(conversion['factor'])
    need(factor > 0, 'TYPED_VALUE_POSITIVE_LINEAR_CONVERSION')
    need(source['id']!=target['id'] or (source==target and factor==1), 'TYPED_VALUE_IDENTITY_CONVERSION')
    _ref(conversion['reference'])
    return conversion


def convert_quantity(quantity, target_unit, factor, transformation_reference, authorized_transformations):
    """Apply an exact policy-declared linear conversion; this grants no trust.

    Only the external producer can authenticate whether the exact supplied
    declaration belongs to a valid, current owner policy. No implicit identity,
    affine conversion, cross-kind valuation or arbitrary weighting is supplied.
    """
    validate_quantity(quantity)
    conversion = dict(source_unit=deepcopy(quantity['unit']), target_unit=deepcopy(target_unit),
        factor=rational_wire(factor), reference=transformation_reference)
    validate_conversion(conversion)
    need(type(authorized_transformations) is list and len(authorized_transformations) <= 64,
        'TYPED_VALUE_CONVERSION_DECLARATIONS')
    for row in authorized_transformations:
        validate_conversion(row)
    need(sum(row==conversion for row in authorized_transformations)==1,
        'TYPED_VALUE_EXACT_CONVERSION_NOT_DECLARED')
    values = tuple(v*factor for v in interval_from_wire(quantity['interval']))
    return _result(quantity,values,quantity['provenance']+[transformation_reference,
        'typed-conversion:'+_hash(conversion)],unit=target_unit)


def compare_vectors(left, right):
    """Numerical componentwise order only; it does not decide what is better.

    No default MAXIMIZE for cost/resource/risk exists. The external producer
    must authenticate preference directions before deriving a decision.
    """
    need(type(left) is dict and type(right) is dict and left and set(left)==set(right) and len(left)<=16,
        'TYPED_VALUE_COMPLETE_VECTOR_BASIS')
    try:
        for name in left:
            _ref(name); _compatible(left[name],right[name])
    except TypedValuationRefusal as error:
        if str(error)=='TYPED_VALUE_IDENTICAL_UNIT_REQUIRED':
            return dict(relation='INCOMPARABLE',reason='NO_AUTHORIZED_COMMON_UNIT',preference_applied=False,
                authority_effect='NONE',scalarized=False)
        raise
    l=[interval_from_wire(left[k]['interval']) for k in sorted(left)]
    r=[interval_from_wire(right[k]['interval']) for k in sorted(right)]
    if l==r and all(a[0]==a[2] for a in l): relation='EQUAL'
    elif all(a[0]>=b[2] for a,b in zip(l,r)) and any(a[0]>b[2] for a,b in zip(l,r)): relation='LEFT_DOMINATES'
    elif all(b[0]>=a[2] for a,b in zip(l,r)) and any(b[0]>a[2] for a,b in zip(l,r)): relation='RIGHT_DOMINATES'
    elif any(a[0]>b[2] for a,b in zip(l,r)) and any(b[0]>a[2] for a,b in zip(l,r)): relation='INCOMPARABLE'
    else: relation='ABSTAIN'
    return dict(relation=relation,reason='NUMERIC_COMPONENTWISE_INTERVAL_ORDER_ONLY',preference_applied=False,
        authority_effect='NONE',scalarized=False)


def _finite_simplex_extremum(probability_bounds, coefficients, *, maximize=False):
    """Exact finite linear extremum over nonnegative bounded unit mass.

    Start at every lower probability bound, then allocate the remaining mass
    to the least coefficient first (greatest for maximization). If mass sat
    at a greater coefficient while a lesser coefficient had spare capacity,
    exchanging their common feasible mass would decrease the objective.
    Thus this greedy allocation attains the global linear optimum. No joint
    distribution, statistical coverage, preference or authority is inferred.
    """
    need(type(probability_bounds) is tuple and type(coefficients) is tuple and
        1 <= len(probability_bounds) == len(coefficients) <= 65 and
        type(maximize) is bool, 'TYPED_VALUE_FINITE_SIMPLEX_DOMAIN')
    for bound, coefficient in zip(probability_bounds, coefficients):
        need(type(bound) is tuple and len(bound) == 2 and
            all(type(value) is F for value in bound) and
            F(0) <= bound[0] <= bound[1] <= F(1),
            'TYPED_VALUE_FINITE_SIMPLEX_PROBABILITY_BAND')
        _exact(coefficient)
    masses = [bound[0] for bound in probability_bounds]
    remaining = F(1) - sum(masses)
    need(F(0) <= remaining <= sum(hi-lo for lo, hi in probability_bounds),
        'TYPED_VALUE_FINITE_SIMPLEX_INFEASIBLE')
    order = sorted(range(len(coefficients)),
        key=lambda index: ((-coefficients[index] if maximize else coefficients[index]), index))
    for index in order:
        extra = min(remaining, probability_bounds[index][1] - masses[index])
        masses[index] += extra
        remaining -= extra
    need(remaining == 0 and sum(masses) == 1, 'TYPED_VALUE_FINITE_SIMPLEX_MASS')
    return sum(mass * coefficient for mass, coefficient in zip(masses, coefficients))


def expected_quantity(distribution, outcome_quantities, other_quantity=None):
    """Exact conditional finite expectation, preserving one declared unit.

    Statistical validity of probability bands and authenticity of policy
    valuations remain external obligations. OPEN_WORLD requires explicit
    other-quantity bounds; overlapping marginals remain unsupported. Bounds
    optimize over the supplied exclusive probability simplex and independent
    declared outcome-value bands, not independent probability boxes. They
    are tight over that admitted finite set, not a statistical truth claim.
    """
    from .qpre_calibration_v1 import ConditionalDistribution, DistributionSemantics, TOTAL
    from .grounded_qpre_expected_value_v1 import ValueInterval, CandidateValue, _value_for
    need(type(distribution) is ConditionalDistribution, 'TYPED_VALUE_ACTUAL_DISTRIBUTION')
    distribution=ConditionalDistribution.model_validate_json(distribution.model_dump_json())
    need(type(outcome_quantities) is dict and set(outcome_quantities)=={o.outcome_id for o in distribution.outcomes},
        'TYPED_VALUE_OUTCOME_CATALOG')
    quantities=list(outcome_quantities.values())
    need(quantities,'TYPED_VALUE_OUTCOMES_REQUIRED')
    first=validate_quantity(quantities[0])
    need(first['unit']['kind'] != 'PROBABILITY', 'TYPED_VALUE_OUTCOME_IS_NOT_PROBABILITY')
    for quantity in quantities[1:]: _compatible(first,quantity)
    if other_quantity is not None: _compatible(first,other_quantity);quantities.append(other_quantity)
    band=lambda q:ValueInterval(*interval_from_wire(q['interval']))
    declared=CandidateValue(distribution.candidate_id,tuple((key,band(quantity)) for key,quantity in sorted(outcome_quantities.items())),
        None if other_quantity is None else band(other_quantity),ValueInterval(F(0),F(0),F(0)))
    provenance=sorted({ref for quantity in quantities for ref in quantity['provenance']})
    provenance.append('qpre-distribution:'+_hash(distribution.model_dump(mode='json')))
    provenance.append('typed-rule:'+EXPECTATION_RULE)
    # Retain all existing catalog, calibration and explicit OTHER checks
    # without materializing a loose intermediate expectation. ValueInterval
    # above still enforces the existing bounded coefficient domain.
    zero=ValueInterval(F(0),F(0),F(0))
    validator=CandidateValue(distribution.candidate_id,
        tuple((key,zero) for key in sorted(outcome_quantities)),
        None if other_quantity is None else zero,zero)
    _value_for(distribution,validator)
    by_id=dict(declared.outcome_values)
    bounds=tuple((F(outcome.lower_bp,TOTAL),F(outcome.upper_bp,TOTAL))
        for outcome in distribution.outcomes)
    bands=tuple(by_id[outcome.outcome_id] for outcome in distribution.outcomes)
    points=tuple(F(outcome.point_bp,TOTAL) for outcome in distribution.outcomes)
    if distribution.semantics is DistributionSemantics.OPEN_WORLD:
        # residual_bp is a point estimate, not a fixed unknown probability.
        # These are precisely the complement bounds of the known outcomes.
        bounds+=((max(F(0),F(1)-sum(hi for _,hi in bounds)),
            min(F(1),F(1)-sum(lo for lo,_ in bounds))),)
        bands+=(declared.other_value,)
        points+=(F(distribution.residual_bp,TOTAL),)
    lower=_finite_simplex_extremum(bounds,tuple(value.lower for value in bands))
    upper=_finite_simplex_extremum(bounds,tuple(value.upper for value in bands),maximize=True)
    point=sum(probability*value.point for probability,value in zip(points,bands))
    need(lower <= point <= upper,'TYPED_VALUE_FINITE_SIMPLEX_POINT')
    common=interval_from_wire(first['interval'])
    if all(interval_from_wire(q['interval'])==common for q in quantities):
        provenance.append('typed-rule:CONSTANT_ON_COMPLETE_EXCLUSIVE_PARTITION')
    result=ValueInterval(lower,point,upper)
    return _result(first,(result.lower,result.point,result.upper),provenance)


__all__=['VERSION','TypedValuationRefusal','validate_unit','validate_quantity','make_quantity',
    'validate_conversion','convert_quantity','add_quantities','scale_probability','compare_vectors',
    'expected_quantity','rational_from_wire','rational_wire','interval_from_wire']
