"""One owner-authorized evaluation scope, not general provider readiness.

No answer key, scorer import, model invocation or production Entity access.
The existing diagnostic establishes short completion only, not task reliability.
"""
import hashlib
import json
from pathlib import Path

CONTROL = 'NEBIUS_NEMOTRON_LINEAR_EVAL_V1'
QUESTION_SHA256 = '50f191239262bed9dcab9ee43114190749e5bf57db5616b68277c5886f6237c7'
DIAGNOSTIC_ID = '946928ce9e304bbc8d1d02e0097d684d'
DIAGNOSTIC_SHA256 = 'fc342700b11bcc3220ca51685b0850760955f6b90f9fff21c26faeb4d1d76790'
INPUT_BYTES = 16384
OUTPUT_NOTICE = (
    'Return one JSON object only, without markdown. relation is an object with '
    'coefficients (variable to integer or rational fraction string) and rhs. '
    'steps is a nonempty list of at most 8 objects: id, weights (public equation '
    'labels or earlier step ids to integer or rational fraction string), conclusion '
    '(the same equation shape). Each step must be the exact weighted sum of its '
    'named premises. State an algebraic certificate, not merely that a result was '
    'verified. execution_receipts is a list of hashes actually supplied to your '
    'lane, or empty. unique_solution and world_facts_verified are booleans: do not '
    'claim full-system uniqueness or independent real-world verification without '
    'support. These five fields are the complete output schema. No tools or '
    'external actions are available. Native receipts describe host work, not '
    'actions performed by the language model.'
)


def task_question():
    path = Path(__file__).resolve().parents[2] / 'benchmarks/first_paired_linear_v1/public/problem.txt'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != QUESTION_SHA256:
        raise ValueError('Pinned evaluation question mismatch')
    return raw.decode('utf-8')


def contract():
    return {'id': CONTROL, 'scope': 'ONE_EXACT_LINEAR_DERIVATION_EVALUATION_ONLY',
            'question_sha256': QUESTION_SHA256, 'diagnostic_task_id': DIAGNOSTIC_ID,
            'maximum_calls': 2, 'maximum_rounds': 1, 'maximum_completion_tokens': 384,
            'maximum_combined_input_bytes': INPUT_BYTES,
            'provider_fields': {'reasoning_effort': 'none'},
            'task_reliability': 'UNVERIFIED', 'general_auto_readiness': 'PROBE_REQUIRED',
            'authorization': 'Separate explicit owner authorization and RUN required.'}


def status(config, records, credentials, text):
    blocked = lambda reason: {'status': 'BLOCKED', 'blocker': reason}
    if not credentials:
        return blocked('Configured provider credential unavailable; no provider switch.')
    if text != task_question():
        return blocked('Evaluation profile permits only its exact pinned public question.')
    if any(t.get('settings', {}).get('pair', {}).get('se6', {}).get('provider_reasoning_control') == CONTROL for t in records):
        return blocked('This one-round evaluation profile has already been admitted; no repeat.')
    evidence = next((t for t in records if t.get('id') == DIAGNOSTIC_ID), None)
    if evidence is None:
        return blocked('Frozen short diagnostic evidence missing.')
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if digest != DIAGNOSTIC_SHA256:
        return blocked('Frozen short diagnostic evidence mismatch.')
    return {'status': 'ELIGIBLE_SCOPED_EVALUATION', 'blocker': None,
            'profile': contract(), 'completion_evidence_sha256': digest,
            'scope': 'Diagnostic completion evidence only; harder-task success unverified.'}
