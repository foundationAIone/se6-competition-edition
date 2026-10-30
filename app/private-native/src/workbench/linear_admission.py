"""Bounded text-to-proof admission for the existing pinned mathematics core.

No eval, solver, model, store or desired answer. This adapter selects a bounded
row-combination candidate; only SE.realize can verify/retain its consequence.
Unspecified variable domains use a disclosed host-only integer witness grid.
That grid is not a claim about the user's variables and is never sent as a
restriction or solution. The exact row certificate establishes algebraic
entailment independently of the additional finite witness check.
"""
from fractions import Fraction
from itertools import combinations, product
import math
import re

CONTRACT = 'se6-linear-admission-v1'
MAX_EQUATIONS = 4
MAX_VARIABLES = 6
MAX_CANDIDATES = 40000
MAX_CELLS = 250000  # Existing canonical core limit, not a renewed allowance.
NAME = r'[A-Za-z][A-Za-z0-9_]{0,31}'
NUMBER = r'\d+(?:\s*/\s*\d+|\.\d+)?'


class UnsupportedLinear(ValueError):
    pass


def expression(text):
    """Affine terms only: signed rational coefficient, optional *, identifier."""
    if len(text) > 512:
        raise UnsupportedLinear('Linear expression exceeds bounded grammar.')
    text = text.replace('\u2212', '-').strip()
    terms = re.findall(r'[+-]?[^+-]+', text)
    if not terms or ''.join(terms) != text:
        raise UnsupportedLinear('Ambiguous signs or malformed affine expression.')
    coefficients, constant = {}, Fraction(0)
    for item in terms:
        sign = -1 if item.startswith('-') else 1
        body = item[1:] if item[:1] in '+-' else item
        body = body.strip()
        match = re.fullmatch(rf'(?:(?P<number>{NUMBER})\s*\*?\s*)?(?P<name>{NAME})', body)
        if match:
            number = match['number'] or '1'
            if len(number) > 16:
                raise UnsupportedLinear('Coefficient literal too large.')
            value = sign * Fraction(re.sub(r'\s+', '', number))
            coefficients[match['name']] = coefficients.get(match['name'], Fraction(0)) + value
        elif re.fullmatch(NUMBER, body):
            if len(body) > 16:
                raise UnsupportedLinear('Constant literal too large.')
            constant += sign * Fraction(re.sub(r'\s+', '', body))
        else:
            raise UnsupportedLinear('Only affine equality terms are supported; no products, powers, functions, parentheses or inequalities.')
    return coefficients, constant


def equation(text, api):
    if text.count('=') != 1:
        raise UnsupportedLinear('Exactly one equality is required per equation.')
    left, right = map(expression, text.split('='))
    names = set(left[0]) | set(right[0])
    coefficients = {n: left[0].get(n, Fraction(0)) - right[0].get(n, Fraction(0)) for n in names}
    coefficients = {n: v for n, v in coefficients.items() if v}
    rhs = right[1] - left[1]
    if not coefficients:
        raise UnsupportedLinear('Constant-only or cancelling equality is outside native admission; no vacuous deduction.')
    scale = math.lcm(*(v.denominator for v in (*coefficients.values(), rhs)))
    integers = {n: int(v * scale) for n, v in coefficients.items()}
    integer_rhs = int(rhs * scale)
    divisor = math.gcd(*(abs(v) for v in (*integers.values(), integer_rhs)))
    integers = {n: v // divisor for n, v in integers.items()}
    integer_rhs //= divisor
    native = api.LinearEquation.from_coefficients(integers, integer_rhs)
    normalization = {'original_equation': text, 'equivalent_row_scale': str(Fraction(scale, divisor)),
                     'coefficients': [[n, v] for n, v in native.coefficients], 'rhs': native.rhs}
    return native, normalization


def requested(text):
    text = re.sub(r'\s+', ' ', text).strip().rstrip('.')
    text = re.sub(r',?\s+and verify(?: it| the (?:relation|relationship))?$', '', text, flags=re.I)
    pivot = None
    match = re.fullmatch(r'Derive (?:(?:a|the) )?(?:(?:mathematical|linear) )?(?:relationship|relation) (?:between|among|involving) (.+)', text, re.I)
    if match:
        raw = match[1]
    else:
        match = re.fullmatch(rf'Derive ({NAME}) in terms of (.+)', text, re.I)
        if not match:
            raise UnsupportedLinear('An explicit supported linear derivation request is required.')
        pivot, raw = match[1], match[2]
    raw = re.sub(r',\s+and\s+', ',', raw)
    raw = re.sub(r'\s+and\s+', ',', raw)
    parts = [p.strip() for p in raw.split(',')]
    if not parts or not all(re.fullmatch(NAME, p) for p in parts):
        raise UnsupportedLinear('Requested variables must be unambiguous comma/and-separated identifiers.')
    names = ([pivot] if pivot else []) + parts
    if len(set(names)) != len(names) or not 1 <= len(names) <= MAX_VARIABLES:
        raise UnsupportedLinear('Requested variables must be distinct and bounded in number.')
    return tuple(sorted(names)), pivot


def choose_proof(rows, target, requested_pivot):
    """Choose native proof weights from coefficient cancellation, never RHS/answer."""
    checks = 0
    choices = tuple(v for n in range(1, 17) for v in (n, -n))
    for size in range(1, len(rows) + 1):
        for indexes in combinations(range(len(rows)), size):
            for weights in product(range(1, 17), *(choices for _ in range(size - 1))):
                checks += 1
                if checks > MAX_CANDIDATES:
                    raise UnsupportedLinear('Bounded native proof-candidate search exhausted; no automatic escalation.')
                if math.gcd(*weights) != 1:
                    continue
                coefficients = {}
                for index, weight in zip(indexes, weights):
                    for name, value in rows[index].coefficients:
                        coefficients[name] = coefficients.get(name, 0) + weight * value
                coefficients = {n: v for n, v in coefficients.items() if v}
                if set(coefficients) != set(target) or any(abs(v) > 1000000 for v in coefficients.values()):
                    continue
                # Explicit pivot wins. Otherwise prefer a positive unit pivot,
                # then sparse occurrence; no variable name or expected answer.
                pivot = requested_pivot or min(target, key=lambda n: (
                    coefficients[n] < 0, abs(coefficients[n]),
                    sum(n in dict(row.coefficients) for row in rows), n))
                return {'indexes': list(indexes), 'weights': list(weights), 'pivot': pivot,
                        'candidates_checked': checks}
    raise UnsupportedLinear('No native bounded row combination retains exactly the requested variables.')


def check_consistency(rows):
    for left, right in combinations(rows, 2):
        if set(dict(left.coefficients)) != set(dict(right.coefficients)):
            continue
        ratio = Fraction(left.coefficients[0][1], dict(right.coefficients)[left.coefficients[0][0]])
        if all(Fraction(value, dict(right.coefficients)[name]) == ratio for name, value in left.coefficients):
            if Fraction(left.rhs) != ratio * right.rhs:
                raise UnsupportedLinear('Conflicting proportional equalities; no consistent premise set or verified deduction admitted.')


def verification_domain(names, rows, explicit, previous, api):
    if previous:
        choices = [tuple(previous.variables)]
        origin = 'PUBLIC_INTEGER_BOUNDS' if explicit else 'HOST_VERIFICATION_GRID_ONLY'
        if explicit and any((v.lower, v.upper) != explicit for v in previous.variables):
            raise UnsupportedLinear('Correction cannot silently change the retained variable domain.')
    elif explicit:
        choices = [tuple(api.IntegerVariable(n, *explicit) for n in names)]
        origin = 'PUBLIC_INTEGER_BOUNDS'
    else:
        width = 12
        while width ** len(names) > MAX_CELLS:
            width -= 1
        ranges = ((-(width // 2), width - width // 2 - 1), (0, width - 1), (1 - width, 0))
        choices = [tuple(api.IntegerVariable(n, lo, hi) for n in names) for lo, hi in ranges]
        origin = 'HOST_VERIFICATION_GRID_ONLY'
    for variables in choices:
        cells = math.prod(v.upper - v.lower + 1 for v in variables)
        if cells > MAX_CELLS:
            raise UnsupportedLinear('Existing native finite-verification cell limit exceeded.')
        # Admission consistency check only; no solution/witness is returned or
        # sent to either model. The canonical verifier rechecks independently.
        if any(all(row.holds(dict(zip(names, values))) for row in rows)
               for values in product(*(range(v.lower, v.upper + 1) for v in variables))):
            return variables, origin
    raise UnsupportedLinear('No integer witness in the bounded native verification policy; this is not proof of global inconsistency. Model-only fallback required.')


def admit(text, api, previous=None, previous_policy=None):
    """Return typed admission material or a specific model-only limitation."""
    if not re.search(r'\bDerive\b', text, re.I):
        return None
    split = re.split(r'\b(Derive)\b', text, maxsplit=1, flags=re.I)
    if len(split) != 3:
        return None
    body, request = split[0].strip(), split[1] + split[2]
    try:
        target, pivot = requested(request)
        explicit = None
        domain = re.search(r'Variables are integers (?:between (-?\d+) and (-?\d+)|in \[(-?\d+),\s*(-?\d+)\])\.?', body, re.I)
        if domain:
            explicit = (int(domain[1] or domain[3]), int(domain[2] or domain[4]))
            body = body[:domain.start()] + body[domain.end():]
        correction = re.fullmatch(rf'Correct ({NAME}) to (.+?)\.?', body, re.I | re.S)
        rows, records = [], []
        if correction:
            if previous is None:
                raise UnsupportedLinear('Correction requires this session\'s retained canonical mathematical premises.')
            label, replacement = correction.groups()
            native, normalization = equation(replacement, api)
            current = {c.label: c.equation for c in previous.current_constraints}
            if label not in current or current[label] == native:
                raise UnsupportedLinear('Correction must change one existing labelled equality, not replay it.')
            current[label] = native
            for name in sorted(current):
                rows.append(current[name]); records.append({'label': name, 'equation': {
                    'coefficients': [list(t) for t in current[name].coefficients], 'rhs': current[name].rhs}})
            changed = label
            mode = 'CORRECT'
        elif not body:
            if previous is None:
                raise UnsupportedLinear('No canonical mathematical premises retained for this derivation.')
            for c in previous.current_constraints:
                rows.append(c.equation); records.append({'label': c.label, 'equation': {
                    'coefficients': [list(t) for t in c.equation.coefficients], 'rhs': c.equation.rhs}})
            normalization, changed, mode = None, None, 'DERIVE'
        else:
            if previous is not None:
                raise UnsupportedLinear('Existing mathematical state requires explicit correction or retained-state derivation; no silent remap.')
            block = re.fullmatch(r'Given(?: (?:the |these )?(?:linear )?equations)?:\s*(.+)', body, re.I | re.S)
            # A bare block must still parse completely as affine equalities.
            # No prelude is silently discarded or inferred.
            parts = [p.strip() for p in re.split(r'[\n;]', block[1] if block else body) if p.strip()]
            if not 1 <= len(parts) <= MAX_EQUATIONS:
                raise UnsupportedLinear('Native proof admission supports one to four equations.')
            for index, part in enumerate(parts):
                labelled = re.fullmatch(rf'({NAME}):\s*(.+)', part)
                label, literal = labelled.groups() if labelled else (f'E{index+1}', part)
                native, normalization = equation(literal, api)
                rows.append(native); records.append({'label': label, 'equation': {
                    'coefficients': [list(t) for t in native.coefficients], 'rhs': native.rhs}, 'normalization': normalization})
            if len({r['label'] for r in records}) != len(records):
                raise UnsupportedLinear('Duplicate equality labels are ambiguous.')
            changed, mode = None, 'MAP'
        names = tuple(sorted({n for row in rows for n, _ in row.coefficients}))
        if not 1 <= len(names) <= MAX_VARIABLES or not set(target) <= set(names):
            raise UnsupportedLinear('Unknown requested symbol or too many native variables.')
        if previous and names != tuple(v.name for v in previous.variables):
            raise UnsupportedLinear('Correction cannot silently add or remove retained variables.')
        check_consistency(rows)
        proof = choose_proof(rows, target, pivot)
        variables, origin = verification_domain(names, rows, explicit, previous, api)
        if previous_policy:
            origin = previous_policy['domain_origin']
        return {'contract': CONTRACT, 'mode': mode, 'equations': records, 'changed_label': changed,
                'variables': [{'name': v.name, 'lower': v.lower, 'upper': v.upper} for v in variables],
                'domain_origin': origin, 'domain_is_public_assumption': origin == 'PUBLIC_INTEGER_BOUNDS',
                'proof_candidate': proof, 'requested_variables': list(target),
                'correction_normalization': normalization if mode == 'CORRECT' else None,
                'required_actions': 1 if mode == 'DERIVE' else 2}
    except (ValueError, OverflowError, ZeroDivisionError) as error:
        return {'unsupported': str(error)}
