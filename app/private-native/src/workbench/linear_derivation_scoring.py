"""Post-freeze certificate checking for the preregistered held-out relation.

This verifies declared row arithmetic. It does not generate a deduction or
solve a new problem. Only this module reads the existing private rubric.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import time

from .linear_evaluation_profile import CONTROL, QUESTION_SHA256
from .linear_admission import expression
from .math_scoring import _raw
from .metrics import execution_metrics

RUBRIC_SHA256 = '193b5972756eb582785c3b96f17c230e050258c095b59ac7dfaf9a4b599a34c1'


def rational(value):
    if type(value) is int:
        result = Fraction(value)
    elif isinstance(value, str) and re.fullmatch(r'-?\d{1,7}(?:/[1-9]\d{0,6})?', value):
        result = Fraction(value)
    else:
        raise ValueError('Bounded integer or rational fraction required')
    if abs(result.numerator) > 1000000 or result.denominator > 1000000:
        raise ValueError('Rational outside scoring bounds')
    return result


def equation(value, variables):
    if not isinstance(value, dict) or set(value) != {'coefficients', 'rhs'}:
        raise ValueError('Equation schema mismatch')
    terms = value['coefficients']
    if not isinstance(terms, dict) or not terms or set(terms)-variables:
        raise ValueError('Unknown variable or empty equation')
    coefficients = {k: rational(v) for k, v in terms.items() if rational(v)}
    if not coefficients:
        raise ValueError('Zero equation is not a relation')
    return coefficients, rational(value['rhs'])


def equivalent(left, right):
    keys = set(left[0]) | set(right[0])
    pivot = next((k for k in keys if right[0].get(k)), None)
    if pivot is None:
        return False
    ratio = left[0].get(pivot, Fraction(0)) / right[0][pivot]
    return bool(ratio) and left[1] == ratio*right[1] and all(
        left[0].get(k, 0) == ratio*right[0].get(k, 0) for k in keys)


def public_rows(text):
    rows = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(E\d+):\s*(.+)', line)
        if match:
            left, right = map(expression, match[2].split('='))
            keys = set(left[0]) | set(right[0])
            rows[match[1]] = ({k: left[0].get(k, 0)-right[0].get(k, 0) for k in keys}, right[1]-left[1])
    return rows


def no_duplicate_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate output field')
        value[key] = item
    return value


def assess_output(raw, expected, premises, allowed_receipts):
    """Same closed output contract for both lanes; no prose plausibility judge."""
    value = json.loads(raw, object_pairs_hook=no_duplicate_fields,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite output')))
    fields = {'relation', 'steps', 'execution_receipts', 'unique_solution', 'world_facts_verified'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('Incomplete or unsupported final-output schema')
    variables = set().union(*(set(row[0]) for row in premises.values()))
    final = equation(value['relation'], variables)
    steps = value['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
        raise ValueError('At least one bounded explicit proof step required')
    available = dict(premises)
    verified, invalid = [], []
    for step in steps:
        try:
            if not isinstance(step, dict) or set(step) != {'id', 'weights', 'conclusion'}:
                raise ValueError('Proof-step schema mismatch')
            label = step['id']
            if not isinstance(label, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', label) or label in available:
                raise ValueError('Duplicate or invalid proof id')
            weights = step['weights']
            if not isinstance(weights, dict) or not weights or set(weights)-set(available):
                raise ValueError('Unknown or forward premise reference')
            coefficients, rhs = {}, Fraction(0)
            weights = {k: rational(v) for k, v in weights.items()}
            if not any(weights.values()):
                raise ValueError('Zero certificate')
            for name, weight in weights.items():
                row = available[name]
                rhs += weight*row[1]
                for variable, coefficient in row[0].items():
                    coefficients[variable] = coefficients.get(variable, 0)+weight*coefficient
            coefficients = {k:v for k,v in coefficients.items() if v}
            conclusion = equation(step['conclusion'], variables)
            if conclusion != (coefficients, rhs):
                raise ValueError('Claimed row is not the stated weighted sum')
            available[label] = conclusion
            verified.append(conclusion)
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
            invalid.append(str(exc))
    receipts = value['execution_receipts']
    if not isinstance(receipts, list) or len(receipts)>8 or any(not isinstance(r,str) for r in receipts):
        raise ValueError('Receipt claim schema mismatch')
    if type(value['unique_solution']) is not bool or type(value['world_facts_verified']) is not bool:
        raise ValueError('Epistemic claims must be booleans')
    unsupported = sum(r not in allowed_receipts for r in receipts)
    unsupported += int(value['unique_solution'])+int(value['world_facts_verified'])
    correct = equivalent(final, expected)
    proof = not invalid and any(equivalent(row, final) for row in verified)
    # Three equal, independently reported checks; efficiency is not a tiebreaker.
    discipline = unsupported == 0 and not invalid and correct
    return {'status':'ASSESSABLE', 'correct_answer':correct, 'valid_derivation':proof,
            'incorrect_deductions':len(invalid), 'unsupported_claims':unsupported,
            'proof_errors':invalid, 'epistemic_discipline':discipline,
            'task_success':correct and proof and discipline,
            'score':int(correct)+int(proof)+int(discipline), 'maximum_score':3}


def score_pair(root, task):
    started = time.monotonic()
    root = Path(root)
    row = task['rounds'][-1]
    if (len(task['rounds']) != 1 or task['settings']['integration'] != 'auto' or
            task['settings']['pair']['se6'].get('provider_reasoning_control') != CONTROL or
            hashlib.sha256(row['problem'].encode()).hexdigest() != QUESTION_SHA256):
        raise ValueError('Wrong frozen evaluation scope')
    frozen, errors = {}, {}
    for lane in ('se6', 'baseline'):
        result = row['lanes'][lane]
        try:
            if result['status'] != 'COMPLETE' or not result['response'].strip():
                raise ValueError('Missing or failed final response')
            raw, digest = _raw(root, task, row, lane)
            agent = result['agents'][0]
            directory = root/'captures'/task['id']/row['id']/lane/agent['id']
            path = directory/'provider.json'
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Provider capture path mismatch')
            provider = json.loads(path.read_bytes())
            choice = provider['choices'][0]
            if (choice['finish_reason'] != 'stop' or choice['message']['content'].encode() != raw or
                    provider['model'] != task['settings']['pair'][lane]['model'] or
                    provider['usage'] != agent['usage']):
                raise ValueError('Incomplete or mismatched frozen provider response')
            frozen[lane] = (raw, digest)
        except (ValueError, KeyError, TypeError, OSError, IndexError, AttributeError) as exc:
            errors[lane] = str(exc)
    if not frozen:
        return {'schema':'se6-first-scored-linear-v1', 'winner':None,
                'scores':{lane:{'status':'UNASSESSABLE','score':None,'reason':errors[lane]} for lane in errors},
                'measurements':execution_metrics(task),'scoring_seconds':time.monotonic()-started}
    from .core_revisions import load_core, verify_traces
    checkpoint = task['auto_checkpoint']['math']
    api = load_core()
    engine = api.SE.restore(checkpoint['journal'], expected_head=checkpoint['head'])
    verify_traces(api, engine, checkpoint['traces'])
    receipts = row['auto_execution']['receipts']
    if ([r.receipt_hash for r in engine.receipts] != [r['receipt_hash'] for r in receipts] or
            any(not r.verification.passed or r.boundary.outcome != 'ALLOW' for r in engine.receipts)):
        raise ValueError('Canonical receipt provenance mismatch')
    # The private rubric is not opened until raw capture validation has finished.
    path = Path(__file__).resolve().parents[2]/'benchmarks/first_paired_linear_v1/private/rubric.json'
    key = path.read_bytes()
    if hashlib.sha256(key).hexdigest() != RUBRIC_SHA256:
        raise ValueError('Existing preregistered rubric hash mismatch')
    expected_record = json.loads(key)['private_answers'][0]['rounds'][0]
    expected = (dict((n,Fraction(c)) for n,c in expected_record['coefficients']),Fraction(expected_record['rhs']))
    premises = public_rows(row['problem'])
    scores = {}
    for lane in ('se6','baseline'):
        if lane in errors:
            scores[lane] = {'status':'UNASSESSABLE','score':None,'reason':errors[lane]}
            continue
        try:
            receipts = {r['receipt_hash'] for r in row['auto_execution']['receipts']} if lane=='se6' else set()
            scores[lane] = assess_output(frozen[lane][0], expected, premises, receipts)
            scores[lane]['response_sha256'] = frozen[lane][1]
        except (ValueError, KeyError, TypeError, ZeroDivisionError, RecursionError) as exc:
            scores[lane] = {'status':'UNASSESSABLE','score':None,'reason':str(exc)}
    winner = None
    if all(s['status']=='ASSESSABLE' for s in scores.values()):
        a,b = scores['se6']['score'],scores['baseline']['score']
        winner = 'TIE' if a==b else 'se6' if a>b else 'baseline'
    return {'schema':'se6-first-scored-linear-v1','scores':scores,'winner':winner,
            'rubric_sha256':RUBRIC_SHA256,'question_sha256':QUESTION_SHA256,
            'scoring_rule':'One point each: correct relation up to nonzero rational scaling, valid explicit row certificate, epistemic discipline. Costs reported separately; unassessable lanes produce no winner.',
            'measurements':execution_metrics(task),
            'scoring_seconds':time.monotonic()-started,
            'scope':'One local-tool-assisted system comparison, not intrinsic model intelligence or general prose verification.'}
