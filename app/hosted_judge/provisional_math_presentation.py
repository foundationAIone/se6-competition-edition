"""HOST provisional formatting; no receipt/proof replay is removed.

verify_presentations MUST be called with original independently replayed typed
receipts before any publication/context/ACT. Decoded journal state is untrusted
until that gate. AUTO prefix hashes are captured, not reconstructed.
"""
from copy import deepcopy
from dataclasses import asdict, fields
import hashlib
import json
import math
import types
import os
import threading

ROUTES = frozenset(('LINEAR_MATH', 'LINEAR_DERIVATION'))
SCHEMA = 'se6-host-provisional-math-presentation-v1'
MAX_BYTES = 4 * 1024 * 1024
RESULT_KEYS = frozenset(('contract', 'answer', 'derivation', 'deduction_reference', 'proof',
    'verification', 'receipt_hashes', 'checkpoint_hash', 'head', 'scope', 'limitations',
    'provider_calls', 'model_tokens', 'production_connected', 'local_seconds', 'complete_system_solved'))


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError(code)


def strict_object(cls, value):
    require(type(value) is dict and set(value) == {f.name for f in fields(cls)}, 'PRESENTATION_TYPED_SHAPE')
    return dict(value)


def decode_state(api, value):
    """Construct original typed classes only; never establish their truth here."""
    require(len(encoded(value)) <= MAX_BYTES, 'PRESENTATION_STATE_BOUND')
    data = strict_object(api.SEMathState, value)
    require(len(data['variables']) <= 8 and len(data['constraint_history']) <= 32
            and len(data['deduction_history']) <= 32 and len(data['relations']) <= 64,
            'PRESENTATION_HISTORY_BOUND')
    def equation(row):
        row = strict_object(api.LinearEquation, row)
        row['coefficients'] = tuple(tuple(x) for x in row['coefficients'])
        return api.LinearEquation(**row)
    def proof(row):
        row = strict_object(api.MathProof, row)
        row['premise_refs'], row['weights'] = tuple(row['premise_refs']), tuple(row['weights'])
        return api.MathProof(**row)
    def check(row):
        row = strict_object(api.MathCheck, row)
        require(type(row['passed']) is bool, 'PRESENTATION_CHECK_TYPE')
        row['premise_refs'] = tuple(row['premise_refs'])
        row['counterexample'] = tuple(tuple(x) for x in row['counterexample'])
        return api.MathCheck(**row)
    def constraint(row):
        row = strict_object(api.MathConstraint, row)
        row['equation'], row['source_ids'] = equation(row['equation']), tuple(row['source_ids'])
        return api.MathConstraint(**row)
    def deduction(row):
        row = strict_object(api.MathDeduction, row)
        row.update(equation=equation(row['equation']), proof=proof(row['proof']), verification=check(row['verification']))
        return api.MathDeduction(**row)
    data['variables'] = tuple(api.IntegerVariable(**strict_object(api.IntegerVariable, x)) for x in data['variables'])
    data['constraint_history'] = tuple(constraint(x) for x in data['constraint_history'])
    data['deduction_history'] = tuple(deduction(x) for x in data['deduction_history'])
    relations = []
    for row in data['relations']:
        row = strict_object(api.SERelation, row)
        row['source_ids'] = tuple(row['source_ids'])
        relations.append(api.SERelation(**row))
    data['relations'] = tuple(relations)
    require(type(data['version']) is int and type(data['actions_used']) is int
            and 0 <= data['actions_used'] <= 32 and data['version'] >= 0,
            'PRESENTATION_COUNTER_BOUND')
    state = api.SEMathState(**data)
    require(encoded(asdict(state)) == encoded(value), 'PRESENTATION_LOSSLESS_DECODE')
    return state


def formatter_policy(auto_class):
    """Read existing loaded source constants; no corrected display literals."""
    fn = auto_class.native_result
    def constants(code):
        for c in code.co_consts:
            if type(c) is str:
                yield c
            elif isinstance(c, types.CodeType):
                yield from constants(c)
            elif type(c) is tuple:
                yield from (v for v in c if type(v) is str)
    pieces = [c for c in constants(fn.__code__) if c.startswith(") ")]
    scopes = [c for c in constants(auto_class._math.__code__) if type(c) is str]
    require(len(pieces) == 1, "PRESENTATION_FORMAT_POLICY")
    single = [c for c in scopes if c.startswith("Verified conditional mathematical deduction")]
    multiple = [c for c in scopes if c.startswith("Exact row-certificate algebraic entailment")]
    require(len(single) == len(multiple) == 1, "PRESENTATION_SCOPE_POLICY")
    classify_literals = list(constants(auto_class.classify.__code__))
    prefixes = {'LINEAR_MATH': ('One-variable conditional deduction;',),
        'LINEAR_DERIVATION': ('Exact row-certificate entailment from public equations only;',
            'Unspecified domains use auxiliary host-only integer witness grids;',
            'Local checking assistance is a tooling advantage,')}
    limitations = {}
    for route, starts in prefixes.items():
        limitations[route] = []
        for prefix in starts:
            found = [c for c in classify_literals if c.startswith(prefix)]
            require(len(found) == 1, 'PRESENTATION_LIMITATION_POLICY')
            limitations[route].append(found[0])
    return {"limitations": limitations, "separator": pieces[0][2:], "contract": fn.__globals__["NATIVE_CONTRACT"],
            "scopes": {"LINEAR_MATH": single[0], "LINEAR_DERIVATION": multiple[0]}}


def semantic_view(state, pivot, hashes, head, separator):
    require(state.active_deductions, 'PRESENTATION_NO_ACTIVE_DEDUCTION')
    deduction = state.active_deductions[-1]
    require(deduction.verification.passed is True, 'PRESENTATION_UNVERIFIED_DEDUCTION')
    equation, proof = deduction.equation, asdict(deduction.proof)
    premises = {c.reference: c for c in state.current_constraints}
    require(all(ref in premises for ref in proof['premise_refs']), 'PRESENTATION_UNSUPPORTED_PREMISE')
    answer = equation.isolate(pivot)
    derivation = '\n'.join(f'{premises[ref].label}: {premises[ref].equation.display()}' for ref in proof['premise_refs'])
    derivation += '\nCombine: ' + ' + '.join(f'({weight}) {separator}{premises[ref].label}'
                   for weight, ref in zip(proof['weights'], proof['premise_refs']))
    return {'answer': answer, 'derivation': f'{derivation}\nVerified equation: {equation.display()}\nIsolate {pivot}: {answer}',
            'deduction_reference': deduction.reference, 'proof': proof,
            'verification': asdict(deduction.verification), 'receipt_hashes': list(hashes), 'head': head}


def provisional_math(api, selection, summary, checkpoint, policy):
    require(selection['route'] in ROUTES and summary['receipts'], 'PRESENTATION_ROUTE')
    require(encoded(selection['limitations']) == encoded(policy['limitations'][selection['route']]), 'PRESENTATION_LIMITATIONS_BINDING')
    require(all(r['boundary']['outcome'] == 'ALLOW' and r['verification']['passed'] is True
                for r in summary['receipts']), 'PRESENTATION_RECEIPT_DENIED')
    context = json.loads(summary['context'])
    retained = checkpoint['math']
    require(type(retained['journal']) is str and len(retained['journal'].encode()) <= MAX_BYTES, 'PRESENTATION_JOURNAL_BOUND')
    journal = json.loads(retained['journal'])
    require(set(journal) == {'schema', 'initial_state', 'state', 'receipts'}
            and journal['schema'] in ('se-core-math-v1', 'se-core-math-relational-v1'), 'PRESENTATION_JOURNAL_SHAPE')
    head = retained['head']
    hashes = [r['receipt_hash'] for r in summary['receipts']]
    require(context['head'] == head == hashes[-1] == journal['receipts'][-1]['receipt_hash'], 'PRESENTATION_HEAD')
    require(summary['checkpoint_hash'] == checkpoint['checkpoint_hash'], 'PRESENTATION_PREFIX_BINDING')
    cp = dict(checkpoint); cp.pop('checkpoint_hash')
    require(digest(cp) == checkpoint['checkpoint_hash'], 'PRESENTATION_CP_SEAL')
    state = decode_state(api, journal['state'])
    require(context.get('state_hash') == state.state_hash, 'PRESENTATION_STATE_HASH')
    pivot = (selection['math']['proof_candidate']['pivot'] if selection['route'] == 'LINEAR_DERIVATION'
             else selection['math']['variable']['name'])
    require(context['scope'] == policy['scopes'][selection['route']], 'PRESENTATION_SCOPE_BINDING')
    result = semantic_view(state, pivot, hashes, head, policy['separator'])
    result.update(contract=policy['contract'], checkpoint_hash=summary['checkpoint_hash'], scope=context['scope'],
                  limitations=deepcopy(selection['limitations']), provider_calls=0, model_tokens=0,
                  production_connected=False, local_seconds=summary['local_seconds'], complete_system_solved=False)
    # Keep output wire-identical to original formatter. Pending status belongs to
    # the private invocation handle; cannot contaminate published raw answer.
    require(type(result['local_seconds']) in (int, float) and math.isfinite(result['local_seconds'])
            and result['local_seconds'] >= 0, 'PRESENTATION_SECONDS')
    return result


class PresentationInvocation:
    """Instance-only lifetime. guard is trusted current source/runtime admission."""
    def __init__(self, auto, api, policy, guard):
        require(callable(guard), 'PRESENTATION_GUARD_REQUIRED')
        require('native_result' not in auto.__dict__, 'PRESENTATION_EXISTING_OVERRIDE')
        self.auto, self.api, self.policy, self.guard = auto, api, deepcopy(policy), guard
        self.owner = (os.getpid(), threading.get_ident())
        self.original = auto.native_result
        self.original_function = type(auto).native_result
        self.had_attribute = 'native_result' in auto.__dict__
        self.attribute = auto.__dict__.get('native_result')
        self.captures = {}
        self.closed = False
        guard()
        def wrapped(instance, selection, summary, checkpoint):
            require(self.owner == (os.getpid(), threading.get_ident()), 'PRESENTATION_OWNER')
            require(not self.closed and type(instance).native_result is self.original_function
                    and instance.native_result.__func__ is wrapped, 'PRESENTATION_RUNTIME_IDENTITY')
            guard()
            if selection.get('route') not in ROUTES:
                return self.original(selection, summary, checkpoint)
            before = digest([selection, summary, checkpoint])
            shown = provisional_math(api, selection, summary, checkpoint, self.policy)
            require(before == digest([selection, summary, checkpoint]), 'PRESENTATION_INPUT_MUTATION')
            require(len(self.captures) < 12, 'PRESENTATION_CAPTURE_BOUND')
            token = (shown['head'], shown['checkpoint_hash'])
            self.captures[token] = {'status': 'PENDING_INDEPENDENT_REPLAY_GATE',
                                    'shown_sha256': digest(shown), 'input_sha256': before}
            return deepcopy(shown)
        self.wrapped = wrapped
        auto.native_result = types.MethodType(wrapped, auto)
    def close(self):
        if self.closed:
            return
        require(self.auto.native_result.__func__ is self.wrapped, 'PRESENTATION_CLOSE_IDENTITY')
        if self.had_attribute:
            self.auto.native_result = self.attribute
        else:
            del self.auto.native_result
        self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, *unused):
        self.close()


def verify_presentations(api, out, replayed_receipts, raw_answer, checkpoint, policy, captures=None):
    """Only original SE.restore-produced typed receipts are trusted inputs here.

    Caller MUST retain all original full replay/trace/audit/source checks. This
    function does not reconstruct receipt truth or AUTO prefix checkpoint hashes.
    """
    require(type(out) is dict and len(out['nodes']) <= 12, 'PRESENTATION_NODE_BOUND')
    receipts = {}
    for receipt in replayed_receipts:
        require(type(receipt) is api.SETransitionReceipt, 'PRESENTATION_TYPED_RECEIPT_REQUIRED')
        require(receipt.receipt_hash not in receipts, 'PRESENTATION_DUPLICATE_REPLAY_RECEIPT')
        receipts[receipt.receipt_hash] = receipt
    declared = [r['receipt_hash'] for r in out['receipts']]
    require(len(declared) == len(set(declared)), 'PRESENTATION_RECEIPT_MEMBERSHIP')
    context = json.loads(out['context'])
    require(type(context['results']) is list, 'PRESENTATION_CONTEXT_SHAPE')
    nodes = {n['id']: n for n in out['nodes']}
    require(len(nodes) == len(out['nodes']), 'PRESENTATION_DUPLICATE_NODE')
    checked = []
    owned_hashes = []
    replay_order = list(receipts)
    for node in out['nodes']:
        if node['status'] != 'COMPLETE' or node['route'] not in ROUTES:
            continue
        shown = node['result']
        require(type(shown) is dict and set(shown) == RESULT_KEYS, 'PRESENTATION_RESULT_SCHEMA')
        require(encoded(shown.get('limitations')) == encoded(policy['limitations'][node['route']]), 'PRESENTATION_LIMITATIONS_BINDING')
        hashes = shown['receipt_hashes']
        require(hashes and len(hashes) == len(set(hashes)) and all(h in declared and h in receipts for h in hashes), 'PRESENTATION_NODE_RECEIPTS')
        positions = [replay_order.index(h) for h in hashes]
        require(positions == list(range(positions[0], positions[0] + len(hashes))), 'PRESENTATION_NODE_RECEIPT_ORDER')
        require(not set(hashes).intersection(owned_hashes), 'PRESENTATION_RECEIPT_NODE_OVERLAP')
        owned_hashes.extend(hashes)
        last = receipts[hashes[-1]]
        require(last.boundary.outcome == 'ALLOW' and last.verification.passed is True
                and last.observed_consequence is not None and last.observed_consequence.success is True
                and last.observation.kind == 'MATH_DERIVE'
                and type(last.state_after) is api.SEMathState, 'PRESENTATION_REPLAY_NOT_DERIVATION')
        require(all(receipts[h].boundary.outcome == 'ALLOW' and receipts[h].verification.passed is True for h in hashes),
                'PRESENTATION_NODE_RECEIPT_DENIED')
        expected = semantic_view(last.state_after, last.observation.isolate_variable, hashes, last.receipt_hash, policy['separator'])
        require(shown.get('contract') == policy['contract'] and shown.get('scope') == policy['scopes'][node['route']], 'PRESENTATION_SCOPE_BINDING')
        require(type(shown.get('local_seconds')) in (int, float) and math.isfinite(shown['local_seconds']) and shown['local_seconds'] >= 0, 'PRESENTATION_SECONDS')
        final_states = [r.state_after for r in replayed_receipts if type(r.state_after) is api.SEMathState]
        require(final_states, 'PRESENTATION_FINAL_STATE_REQUIRED')
        active = {d.reference for d in final_states[-1].active_deductions}
        expected_status = 'CURRENT' if expected['deduction_reference'] in active else 'SUPERSEDED'
        require(node.get('knowledge_status') == expected_status, 'PRESENTATION_KNOWLEDGE_STATUS')
        for key, value in expected.items():
            require(encoded(shown.get(key)) == encoded(value), 'PRESENTATION_MISMATCH_' + key.upper())
        require(shown.get('provider_calls') == 0 and type(shown.get('provider_calls')) is int
                and shown.get('model_tokens') == 0 and type(shown.get('model_tokens')) is int
                and shown.get('production_connected') is False and shown.get('complete_system_solved') is False,
                'PRESENTATION_SCOPE_FALSE')
        prefix = shown.get('checkpoint_hash')
        require(type(prefix) is str and len(prefix) == 64 and all(c in '0123456789abcdef' for c in prefix), 'PRESENTATION_PREFIX_FORMAT')
        if captures is not None:
            capture = captures.get((shown['head'], prefix))
            require(capture is not None and capture['shown_sha256'] == digest(shown), 'PRESENTATION_CAPTURE_MISMATCH')
        matching = [c for c in context['results'] if c.get('node') == node['id']]
        if node.get('knowledge_status') != 'SUPERSEDED':
            require(len(matching) == 1 and matching[0].get('knowledge_status') == 'CURRENT', 'PRESENTATION_CONTEXT_MEMBERSHIP')
        else:
            require(not matching, 'PRESENTATION_SUPERSEDED_CONTEXT')
        for row in matching:
            require(row.get('answer') == expected['answer'] and encoded(row.get('evidence')) == encoded(shown), 'PRESENTATION_CONTEXT_MISMATCH')
        checked.append({'node': node['id'], 'head': last.receipt_hash, 'shown_sha256': digest(shown)})
    declared_math = [h for h in declared if h in receipts and type(receipts[h].state_after) is api.SEMathState]
    require(owned_hashes == declared_math, 'PRESENTATION_MATH_RECEIPT_COVERAGE')
    require(all(row.get('node') in nodes for row in context['results']), 'PRESENTATION_CONTEXT_FOREIGN_NODE')
    rendered = '\n\n'.join(n['id'] + (' [HISTORICAL — SUPERSEDED]' if n.get('knowledge_status') == 'SUPERSEDED' else '') + ': ' +
               (n['result'].get('answer', n['result'].get('context', '')) if n['status'] == 'COMPLETE'
                else 'UNRESOLVED — ' + n['blocker']) for n in out['nodes'])
    business = out.get('business')
    if business:
        require(checkpoint.get('business') is not None, 'PRESENTATION_BUSINESS_RECORD_BINDING')
        rendered = business['answer'] + '\nCanonical SE6 receipts: ' + str(len(out['receipts'])) + '. Host financial records: ' + str(len(checkpoint['business']['records'])) + '.'
    require(raw_answer == rendered, 'PRESENTATION_RAW_ANSWER_MISMATCH')
    return {'schema': SCHEMA, 'status': 'REPLAYED_SEMANTIC_FIELDS_MATCH', 'nodes': checked,
            'prefix_checkpoint_scope': 'CAPTURED_NOT_INDEPENDENTLY_RECONSTRUCTED',
            'world_truth_verified': False, 'original_full_replay_required': True}
