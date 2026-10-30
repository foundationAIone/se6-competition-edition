"""Offline scoring entrypoint; never imported into model-facing execution.

Every completed raw capture is hash-checked before importing the deterministic
evaluator. No score influences the original responses and no answer key is read.
"""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path


def score_frozen_math_task(task, storage_root, *, actual_cost_by_lane=None):
    if (task.get('status') != 'COMPLETE' or task['settings']['integration'] != 'native_mathematics'
            or len(task['rounds']) != 2 or task['settings']['pair']['mode'] != 'matched'):
        raise ValueError('Two completed matched native mathematical rounds required before scoring')
    frozen = {}
    for step, row in enumerate(task['rounds']):
        if row['index'] != step or row['status'] != 'COMPLETE' or not row['review']['valid_complete_pair']:
            raise ValueError('Invalid or incomplete paired round; not scored')
        for lane in ('se6', 'baseline'):
            result = row['lanes'][lane]
            agents = result['agents']
            if len(agents) != 1 or result['status'] != 'COMPLETE' or agents[0]['status'] != 'COMPLETE':
                raise ValueError('Exactly one completed captured response per lane required')
            capture = Path(storage_root) / 'captures' / task['id'] / row['id'] / lane / agents[0]['id'] / 'response.txt'
            raw = capture.read_bytes()
            observed = hashlib.sha256(raw).hexdigest()
            if (observed != result['response_sha256'] or observed != agents[0]['response_sha256']
                    or raw != result['response'].encode('utf-8')):
                raise ValueError('Raw response freeze mismatch; scoring not started')
            frozen[(step, lane)] = raw
    # Gate is complete for ALL outputs before evaluator import or any scoring.
    from src.workbench.native_mathematics import PUBLIC_HASH, TASK_SCHEMA
    path = Path(__file__).resolve().parents[2] / 'benchmarks/math_constraints_v1/public/problem.json'
    raw_public = path.read_bytes()
    if hashlib.sha256(raw_public).hexdigest() != PUBLIC_HASH:
        raise ValueError('Frozen public challenge changed')
    public = json.loads(raw_public)
    for step, row in enumerate(task['rounds']):
        submitted = json.loads(row['problem'])
        if submitted != {'schema': TASK_SCHEMA, 'round': step, 'problem': public['statements'][step]}:
            raise ValueError('Scoring input does not match frozen public problem')
    from .verification import parse_model_response, evaluate_response
    from src.workbench.metrics import execution_metrics
    scores = {lane: [] for lane in ('se6', 'baseline')}
    parsed = {}
    for lane in ('se6', 'baseline'):
        for step in (0, 1):
            try:
                response = parse_model_response(frozen[(step, lane)])
                previous = parsed.get((step - 1, lane))
                score = evaluate_response(public['rounds'][step], response,
                    public['rounds'][0] if step and previous is not None else None, previous)
                parsed[(step, lane)] = response
                score['constraint_update_assignment_valid'] = score['exact_mathematical_correctness'] if step else None
            except ValueError as error:
                score = {'exact_mathematical_correctness': False, 'response_schema_error': str(error),
                         'correction_and_retention': 'UNASSESSABLE'}
            score['raw_sha256'] = hashlib.sha256(frozen[(step, lane)]).hexdigest()
            scores[lane].append(score)
    metrics = execution_metrics(task)
    round_seconds = []
    for row in task['rounds']:
        try:
            elapsed = (datetime.fromisoformat(row['completed_at']) - datetime.fromisoformat(row['started_at'])).total_seconds()
            round_seconds.append(elapsed if elapsed >= 0 else None)
        except (TypeError, ValueError):
            round_seconds.append(None)
    costs = actual_cost_by_lane or {'se6': None, 'baseline': None}
    if set(costs) != {'se6', 'baseline'} or any(v is not None and (type(v) not in (int, float) or not math.isfinite(v) or v < 0) for v in costs.values()):
        raise ValueError('Actual recorded monetary costs only; unavailable costs remain null')
    return {'schema': 'se6-native-math-frozen-scores-v1', 'scores': scores, 'execution_metrics': metrics,
            'round_end_to_end_seconds': round_seconds,
            'total_end_to_end_seconds': sum(round_seconds) if all(v is not None for v in round_seconds) else None,
            'cost_per_correctly_solved_problem': {lane: costs[lane] / correct if costs[lane] is not None and correct else None
                for lane in ('se6', 'baseline') for correct in [sum(bool(s['exact_mathematical_correctness']) for s in scores[lane])]},
            'scope': {'end_to_end_time': 'Round run intervals, including local processing/scheduling/provider capture; owner wait between rounds excluded.',
                      'model_latency': 'Measured transport request elapsed, including provider roundtrip/capture; no claim of provider-only inference time.',
                      'cost': 'Owner-supplied actual recorded costs only; no estimated token prices.',
                      'method': task['settings']['context_policy'], 'answer_key_access': False},
            'all_outputs_frozen_before_scoring': True, 'llm_judge_calls': 0}
