"""Bounded action-conditioned observation learning, upstream of semantic inputs.

No field-to-meaning table, privileged state labels, equivalence oracle, I/O or
authority is accepted here. Latent states are introduced by first encounter.
Models describe tested predictive distinctions, not proven world equivalence.
"""
from collections import deque
from copy import deepcopy
import hashlib
import json

VERSION = 'observation-grounding-1'
PRIORS = {
    'parser': 'opaque-json-value-canonical-hash-v1; no named field extraction',
    'system': 'finite deterministic partially observed action system',
    'reset': 'permitted reset returns the same initial state within a source epoch',
    'goal': 'the familiar independently observed goal-success Boolean',
    'scope': 'finite evidence only; no exact-equivalence or unbounded generalization',
}
DEFAULT_LIMITS = dict(max_states=4, max_models=256, max_expansions=20000,
                      max_rows=96, max_actions=4, max_plan_depth=4)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def raw_id(value):
    require(len(json.dumps(value, allow_nan=False)) <= 4096, 'RAW_OBSERVATION_BOUND')
    return digest(value)


def validate_rows(rows, actions, limits):
    require(type(rows) is list and 1 <= len(rows) <= limits['max_rows'], 'ROW_BOUND')
    require(type(actions) is list and 1 <= len(actions) <= limits['max_actions']
            and len(set(actions)) == len(actions) and all(type(a) is str for a in actions), 'ACTION_INTERFACE')
    episode = None
    for i, row in enumerate(rows):
        require(set(row) == {'id', 'source', 'epoch', 'episode', 'index', 'action', 'raw', 'goal'}, 'RAW_ROW_SCHEMA')
        require(type(row['id']) is str and row['source'] and row['epoch'], 'SOURCE_BINDING')
        raw_id(row['raw'])
        if row['episode'] != episode:
            require(row['index'] == 0 and row['action'] is None and row['goal'] is None, 'RESET_OBSERVATION')
            require(row['episode'] not in {r['episode'] for r in rows[:i]}, 'EPISODE_REOPENED')
            episode = row['episode']
        else:
            require(row['index'] == rows[i-1]['index']+1 and row['action'] in actions
                    and type(row['goal']) is bool, 'CHRONOLOGICAL_ACTION_CONSEQUENCE')
    require(len({r['id'] for r in rows}) == len(rows) and len({r['source'] for r in rows}) == 1
            and len({r['epoch'] for r in rows}) == 1, 'SINGLE_SOURCE_EPOCH_UNIQUE_ROWS')


def fit(rows, actions, *, limits=None):
    """Enumerate all consistent partial models within disclosed finite bounds.

    A missing transition is UNKNOWN. Truncation invalidates consensus: a
    convenient prefix of the candidate set is never reported as knowledge.
    """
    caps = {**DEFAULT_LIMITS, **(limits or {})}
    require(set(caps) == set(DEFAULT_LIMITS) and all(type(v) is int and 0 < v <= 100000
            for v in caps.values()), 'LEARNER_LIMITS')
    validate_rows(rows, actions, caps)
    first = raw_id(rows[0]['raw'])
    models = [{'observations': [first], 'transitions': {}, 'current': 0}]
    expansions = 0
    for row in rows:
        observed = raw_id(row['raw'])
        next_models = {}
        for old in models:
            if row['action'] is None:
                if old['observations'][0] == observed:
                    model = deepcopy(old); model['current'] = 0
                    next_models[digest(model)] = model
                continue
            key = str(old['current']) + ':' + row['action']
            if key in old['transitions']:
                dest, goal = old['transitions'][key]
                if goal == row['goal'] and old['observations'][dest] == observed:
                    model = deepcopy(old); model['current'] = dest
                    next_models[digest(model)] = model
                continue
            destinations = [i for i, token in enumerate(old['observations']) if token == observed]
            if len(old['observations']) < caps['max_states']:
                destinations.append(len(old['observations']))
            for dest in destinations:
                expansions += 1
                if expansions > caps['max_expansions']:
                    return _proposal(rows, actions, caps, [], 'BUDGET_UNKNOWN', expansions)
                model = deepcopy(old)
                if dest == len(model['observations']):
                    model['observations'].append(observed)
                model['transitions'][key] = [dest, row['goal']]
                model['current'] = dest
                next_models[digest(model)] = model
                if len(next_models) > caps['max_models']:
                    return _proposal(rows, actions, caps, [], 'BUDGET_UNKNOWN', expansions)
        models = list(next_models.values())
        if not models:
            return _proposal(rows, actions, caps, [], 'CONTRADICTED_OR_MODEL_CLASS_INSUFFICIENT', expansions)
    return _proposal(rows, actions, caps, sorted(models, key=digest), 'BOUNDED_CONSISTENT', expansions)


def _proposal(rows, actions, limits, models, status, expansions):
    return dict(version=VERSION, priors=deepcopy(PRIORS), limits=limits, actions=actions,
                source=rows[0]['source'], epoch=rows[0]['epoch'], training_sha256=digest(rows),
                raw_hashes=[raw_id(r['raw']) for r in rows], models=models, status=status,
                search_expansions=expansions, equivalence_proven=False)


def beliefs(proposal, history):
    require(proposal['status'] == 'BOUNDED_CONSISTENT', 'NO_COMPLETE_BOUNDED_VERSION_SPACE')
    require(type(history) is list and history and history[0]['action'] is None, 'RESET_HISTORY_REQUIRED')
    validate_rows(history,proposal['actions'],proposal['limits'])
    require(len({r['episode'] for r in history})==1 and history[0]['source']==proposal['source']
            and history[0]['epoch']==proposal['epoch'],'CURRENT_HISTORY_SCOPE')
    result = []
    for model in proposal['models']:
        state = 0
        if model['observations'][0] != raw_id(history[0]['raw']):
            continue
        for row in history[1:]:
            edge = model['transitions'].get(str(state)+':'+row['action'])
            if edge is None or model['observations'][edge[0]] != raw_id(row['raw']) or edge[1] != row['goal']:
                break
            state = edge[0]
        else:
            result.append((model, state))
    require(result, 'CURRENT_HISTORY_NOT_SUPPORTED')
    return result


def predict(proposal, history, continuation):
    require(0 < len(continuation) <= proposal['limits']['max_plan_depth']
            and set(continuation) <= set(proposal['actions']), 'CONTINUATION_BOUND')
    alternatives = set()
    for model, state in beliefs(proposal, history):
        result = []
        for action in continuation:
            edge = model['transitions'].get(str(state)+':'+action)
            if edge is None:
                result = None; break
            state, goal = edge
            result.append((model['observations'][state], goal))
        alternatives.add(None if result is None else tuple(result))
    known = None not in alternatives and len(alternatives) == 1
    value = next(iter(alternatives)) if known else None
    return {'status': 'PREDICTED_WITHIN_BOUND' if known else 'UNKNOWN',
            'outcomes': [list(x) for x in value] if value is not None else None,
            'alternative_count': len(alternatives), 'belief_count': len(beliefs(proposal, history)),
            'history_sha256': digest(history), 'continuation': list(continuation)}


def plan(proposal, history, permitted_actions):
    """Find a consensus goal continuation or an authorized discriminating probe."""
    require(set(permitted_actions) <= set(proposal['actions']), 'UNKNOWN_AUTHORIZED_ACTION')
    queue = deque((a,) for a in permitted_actions)
    tested = []
    while queue:
        word = queue.popleft(); prediction = predict(proposal, history, word)
        tested.append(prediction)
        if prediction['outcomes'] and prediction['outcomes'][-1][1] is True:
            return {'status': 'GOAL_PATH_PREDICTED', 'actions': list(word), 'prediction': prediction}
        if len(word) < proposal['limits']['max_plan_depth']:
            queue.extend(word+(a,) for a in permitted_actions)
    probes = [p for p in tested if len(p['continuation']) == 1 and p['status'] == 'UNKNOWN']
    probe = max(probes, key=lambda p: (p['alternative_count'], p['continuation'])) if probes else None
    return {'status': 'UNKNOWN', 'actions': [], 'probe': probe,
            'reason': 'No completely observed unanimous goal path; finite tests do not prove equivalence.'}


def commit(proposal, history, continuations, binding):
    require(set(binding) == {'entity_id', 'entity_state', 'memory_head', 'source', 'epoch'}, 'CURRENT_ENTITY_BINDING')
    require(binding['source'] == proposal['source'] and binding['epoch'] == proposal['epoch'], 'CURRENT_SOURCE_EPOCH')
    material = {'version': VERSION, 'proposal_sha256': digest(proposal), 'binding': deepcopy(binding),
                'history': deepcopy(history), 'predictions': [predict(proposal, history, word) for word in continuations]}
    return {**material, 'commitment': digest(material)}


def verify_prediction(proposal, committed, released, authority, batch_key):
    """Use the existing independently pinned observation-batch authentication port.

    The authority is supplied by the admitted host, never constructed by this
    learner. A producer's flag, model JSON or newly minted hash is insufficient.
    """
    require(authority is not None, 'INDEPENDENT_OBSERVATION_AUTHORITY_REQUIRED')
    require(authority.authenticate_rows(released, proposal['epoch'], batch_key), 'AUTHENTIC_OBSERVATION_BATCH')
    require(type(released) is list and 0 < len(released) <= proposal['limits']['max_plan_depth'], 'RELEASE_BOUND')
    for i,row in enumerate(released):
        require(set(row)=={'id','source','epoch','episode','index','action','raw','goal'}
                and type(row['goal']) is bool and row['action'] in proposal['actions'], 'RELEASE_ROW_SCHEMA')
        prior=committed['history'][-1] if i==0 else released[i-1]
        require(row['episode']==prior['episode'] and row['index']==prior['index']+1, 'CONTIGUOUS_RELEASE_HISTORY')
    require(not ({r['id'] for r in released}&{r['id'] for r in committed['history']}), 'RELEASE_EVENT_UNIQUENESS')
    material = {k: v for k, v in committed.items() if k != 'commitment'}
    require(digest(material) == committed['commitment'] and committed['proposal_sha256'] == digest(proposal), 'COMMITMENT_BINDING')
    require(commit(proposal,committed['history'],[p['continuation'] for p in committed['predictions']],
                   committed['binding'])==committed,'RECOMPUTED_PROSPECTIVE_PREDICTIONS')
    require(all(r['source'] == proposal['source'] and r['epoch'] == proposal['epoch'] for r in released), 'RELEASE_SOURCE_EPOCH')
    expected = [p for p in committed['predictions'] if p['continuation'] == [r['action'] for r in released]]
    require(len(expected) == 1 and expected[0]['outcomes'] is not None, 'PROSPECTIVE_KNOWN_PREDICTION_REQUIRED')
    actual = [[raw_id(r['raw']), r['goal']] for r in released]
    return {'passed': actual == expected[0]['outcomes'], 'commitment': committed['commitment'],
            'proposal_sha256': digest(proposal), 'readback_sha256': digest(released), 'batch_key': batch_key,
            'scope': 'Finite prospective prediction; chronology must separately prove commit before release.'}
