"""Owner-side scoring only after immutable raw captures; never lane preparation."""
import hashlib
from pathlib import Path
from .core_revisions import CANONICAL

def _raw(root, task, round_, lane):
    row = round_['lanes'][lane]
    agents = [a for a in row['agents'] if a['role'] == 'answer']
    if len(agents) != 1:
        raise ValueError('Exactly one frozen answer capture required')
    agent = agents[0]
    path = root / 'captures' / task['id'] / round_['id'] / lane / agent['id'] / 'response.txt'
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Response capture escaped isolated task store')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != row['response_sha256'] or digest != agent.get('response_sha256') or raw != row['response'].encode('utf-8'):
        raise ValueError('Frozen response hash mismatch')
    return raw, digest

def score_frozen_round(root, task, adapter):
    if task['settings'].get('core_revision') != CANONICAL or adapter.revision != CANONICAL:
        raise ValueError('Scoring requires explicit canonical session')
    round_ = task['rounds'][-1]
    if round_['status'] not in ('COMPLETE', 'ERROR', 'CANCELLED_LOCAL', 'INTERRUPTED'):
        raise ValueError('Responses are not frozen')
    adapter.validate_task(round_['problem'], None if round_['index'] == 0 else {'step': 0})
    problem = adapter.public['rounds'][round_['index']]
    results = {}
    # This evaluator does not read the private answer-key file. No change to rules.
    from src.math_benchmark.verification import parse_model_response, evaluate_response
    from src.math_benchmark import verification as evaluator
    for lane in ('se6', 'baseline'):
        row = round_['lanes'][lane]
        if not row.get('response'):
            results[lane] = {'status':'UNASSESSABLE', 'reason':'NO_FINAL_ANSWER', 'score':None}
            continue
        try:
            raw, digest = _raw(root, task, round_, lane)
        except (OSError, ValueError, KeyError):
            results[lane] = {'status':'UNASSESSABLE', 'reason':'FROZEN_CAPTURE_MISMATCH', 'score':None}
            continue
        if row['status'] != 'COMPLETE':
            results[lane] = {'status':'UNASSESSABLE', 'reason':'INCOMPLETE_FINAL_ANSWER', 'response_sha256':digest, 'score':None}
            continue
        try:
            response = parse_model_response(raw)
            previous_problem = previous_response = None
            if round_['index']:
                prior = task['rounds'][-2]
                if prior['lanes'][lane]['status'] == 'COMPLETE':
                    previous_raw, _ = _raw(root, task, prior, lane)
                    try:
                        previous_response = parse_model_response(previous_raw)
                        # Validate schema using the unchanged scorer before reuse.
                        evaluate_response(adapter.public['rounds'][0], previous_response)
                        previous_problem = adapter.public['rounds'][0]
                    except (ValueError, TypeError, KeyError):
                        previous_response = None
            score = evaluate_response(problem, response, previous_problem, previous_response)
            results[lane] = {'status':'ASSESSED', 'response_sha256':digest, 'score':score}
        except (ValueError, TypeError, KeyError):
            results[lane] = {'status':'INVALID_RESPONSE', 'reason':'UNSUPPORTED_RESPONSE_SCHEMA', 'response_sha256':digest, 'score':None}
    return {'schema':'se6-frozen-math-evaluation-v1', 'round':round_['index'],
        'public_sha256':hashlib.sha256(adapter.public_path.read_bytes()).hexdigest(),
        'evaluator_sha256':hashlib.sha256(Path(evaluator.__file__).read_bytes()).hexdigest(),
        'scoring_rules':'UNCHANGED_src.math_benchmark.verification.evaluate_response',
        'model_judge_calls':0, 'lanes':results}
