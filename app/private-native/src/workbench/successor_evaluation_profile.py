"""Exact prospective public campaign preparation; no provider or rubric access.

Readiness never grants authorization. Runner durably commits returned ledger
reservations BEFORE dispatch and never refunds/retries uncertain calls.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from .linear_output_context import provider_linear_context

CONTROL = 'NEBIUS_NEMOTRON_SUCCESSOR_EVAL_V2'
CAMPAIGN = 'mission-successor-v2'
PUBLIC_SHA256 = '33d1694ecd49004416e84d0c1fb623d3559f16810088923ea8d532566a3a565a'
SCOPE_SHA256 = 'f2146ccd67436a97e85ebfabfc3733aa1b715dd9fddc4c9383c55ec23d01b1f7'
FREEZE_SHA256 = 'b002640bd29c64458fc437d04c0b4258edc5e8c87d6527f2efc61c4acdd95f75'
INPUT_BYTES = 49152
PER_ROUND_INPUT_BYTES = 16384
MAX_COMPLETION_TOKENS = 1024
ORDER = [('linear-correction',0),('linear-correction',1),('mixed-business',0)]
CAPS = {'calls':6,'rounds':3,'output_tokens_per_call':1024,
        'total_output_tokens':6144,'combined_input_bytes':49152,
        'automatic_retries':0,'usd':0.5}
NOTICE = (
    'Follow the exact JSON schema requested in the shared public question. '
    'For linear correction the top-level fields are answer, retained_step_ids, '
    'invalidated_step_ids; answer has relation, steps, execution_receipts, '
    'unique_solution, world_facts_verified. Every affine equation has exactly '
    'coefficients and rhs. coefficients MUST be a JSON OBJECT mapping variable '
    'names to integers or exact fraction strings, never an array of pairs. '
    'Illustrative shape only (not a task answer): '
    '{"coefficients":{"example_variable":1},"rhs":0}. '
    'Each step has id, weights, conclusion; weights is a JSON OBJECT mapping '
    'public equation labels or earlier same-lane step ids to exact weights. '
    'At most eight steps. In follow-ups classify only your own previous steps. '
    'For business use exactly the fields requested in that public question. '
    'Native journal encoding is internal evidence, not your answer schema. '
    'The public answer contract requires execution_receipts to be an empty '
    'array; do not copy host receipt hashes into that output field. '
    'Receipt hashes describe host work actually supplied to your lane; do not '
    'claim you executed it. No tools or external actions are available. '
    'All facts are conditional supplied inputs, not independent world truth.'
)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def load_public(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[2]
    base=root/'benchmarks/mission_successor_v2'
    public=(base/'public/cases.json').read_bytes()
    scope=(base/'campaign-scope.json').read_bytes()
    if sha((base/'freeze.json').read_bytes())!=FREEZE_SHA256:
        raise ValueError('Frozen scoring contract manifest mismatch')
    if sha(public)!=PUBLIC_SHA256 or sha(scope)!=SCOPE_SHA256:
        raise ValueError('Successor public/scope pins mismatch; no execution')
    cases=json.loads(public)
    if [(c['id'],len(c['rounds'])) for c in cases['cases']] != [('linear-correction',2),('mixed-business',1)]:
        raise ValueError('Successor scope shape mismatch')
    return {c['id']:tuple(c['rounds']) for c in cases['cases']}


def exact_question(case_id,round_index,question,root=None):
    if type(round_index) is not int or (case_id,round_index) not in ORDER:
        raise ValueError('Unknown scoped successor round')
    expected=load_public(root)[case_id][round_index]
    if question!=expected:
        raise ValueError('Successor exact public question mismatch')
    return expected


def contract():
    return {'id':CONTROL,'campaign':CAMPAIGN,'public_sha256':PUBLIC_SHA256,
            'scope_sha256':SCOPE_SHA256,'freeze_sha256':FREEZE_SHA256,'caps':deepcopy(CAPS),
            'maximum_combined_input_bytes':INPUT_BYTES,
            'maximum_completion_tokens':MAX_COMPLETION_TOKENS,
            'provider_fields':{'reasoning_effort':'none'},
            'authorization':'NEW EXPLICIT CAPPED OWNER APPROVAL REQUIRED',
            'dashboard_dispatch':'BLOCKED; dedicated persistent-ledger runner only'}


def native_question(case_id,round_index,question,root=None):
    exact_question(case_id,round_index,question,root)
    if case_id=='linear-correction':
        if round_index==0:
            native='Given equations:\nE1: p + q + r = 24\nE2: r + s = 12\nDerive the relation between p, q, s.'
        else:
            native='Correct E2 to r + s = 15.\nDerive the relation between p, q, s.'
    else:
        native=question
    return {'original_question':question,'question_sha256':sha(question.encode()),
            'native_question':native,'native_question_sha256':sha(native.encode()),
            'scope':'Exact pinned public premise/derivation mapping only; baseline retains original prompt.'}


def projected_context(native_context):
    """Bounded explicit evidence view, with full source context hashed/archived.

    Preserve host arithmetic views and mathematical derivations; omit duplicated
    host calculation records from provider input. This is deliberate projection,
    never truncation or a claim that omitted records were sent to the model.
    """
    context=json.loads(native_context)
    if isinstance(context,dict) and 'results' in context:
        selected=[]
        fields=('contract','kind','answer','derivation','equation','proof','verification',
                'receipt_hashes','deduction_reference','book_hash','currency','views',
                'scope','source_facts_class','signature_authenticity','complete_system_solved')
        for row in context['results']:
            evidence=row.get('evidence',{})
            selected.append({k:deepcopy(row[k]) for k in
                ('node','answer','knowledge_status','original_question_sha256') if k in row})
            selected[-1]['evidence']={k:deepcopy(evidence[k]) for k in fields if k in evidence}
        context={'scope':context.get('scope'),'results':selected,
                 'unresolved':context.get('unresolved',[]),
                 'projection_policy':'Selected native derivations and host views; full immutable records remain in archive.',
                 'full_native_context_sha256':sha(native_context.encode())}
    return provider_linear_context(json.dumps(context,ensure_ascii=False,allow_nan=False))


def prepare_pair(case_id,round_index,question,model,history,native_context,root=None):
    exact_question(case_id,round_index,question,root)
    from .provider_reasoning_control import provider_fields
    from .provider_router import payload_bytes
    if model.provider_reasoning_control!=CONTROL or model.temperature is not None:
        raise ValueError('Successor exact model/control/temperature required')
    provider_fields(model)
    if not isinstance(history,dict) or set(history)!={'se6','baseline'}:
        raise ValueError('Independent same-lane histories required')
    publics=load_public(root)[case_id]
    for lane,prior in history.items():
        if (not isinstance(prior,list) or len(prior)!=round_index or
                any(not isinstance(s,str) or not s.strip() for s in prior)):
            raise ValueError('Prior own response missing; no partial-history comparison')
    if not isinstance(native_context,str) or not native_context:
        raise ValueError('Actual native context required')
    assisted=projected_context(native_context)
    messages={}
    for lane in ('se6','baseline'):
        rows=[{'role':'developer','content':NOTICE}]
        for index,response in enumerate(history[lane]):
            rows.extend([{'role':'user','content':publics[index]},
                         {'role':'assistant','content':response}])
        rows.append({'role':'user','content':question})
        if lane=='se6':
            rows.append({'role':'user','content':assisted})
        messages[lane]=rows
    raw={lane:payload_bytes(model,{'input':rows}) for lane,rows in messages.items()}
    sizes={lane:len(value) for lane,value in raw.items()}
    if sum(sizes.values())>PER_ROUND_INPUT_BYTES:
        raise ValueError('Transformed matched payloads exceed round byte cap; no dispatch')
    return {'case_id':case_id,'round_index':round_index,'question_sha256':sha(question.encode()),
            'messages':messages,'payloads':{lane:json.loads(value) for lane,value in raw.items()},
            'payload_bytes':sizes,'payload_sha256':{lane:sha(value) for lane,value in raw.items()},
            'total_input_bytes':sum(sizes.values()),'model_settings':model.stored(),
            'native_context':native_context,
            'native_context_sha256':sha(native_context.encode()),
            'provider_projection_sha256':sha(assisted.encode())}


def validate_authorization(approval):
    if (not isinstance(approval,dict) or approval.get('campaign')!=CAMPAIGN or
            approval.get('owner_authorized') is not True or approval.get('caps')!=CAPS or
            approval.get('public_sha256')!=PUBLIC_SHA256 or approval.get('scope_sha256')!=SCOPE_SHA256 or
            not isinstance(approval.get('owner_approval_text'),str) or not approval['owner_approval_text'].strip()):
        raise ValueError('Separate explicit successor capped owner authorization missing/mismatch')
    return sha(json.dumps(approval,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def initial_ledger(approval):
    return {'schema':'se6-successor-reservations-v2','campaign':CAMPAIGN,
            'approval_sha256':validate_authorization(approval),
            'calls_reserved':0,'output_tokens_reserved':0,'input_bytes_reserved':0,'reservations':[]}


def reserve_round(ledger,prepared,case_id,round_index,approval):
    """Pure irreversible reservation candidate; runner must atomically persist.

    All requests count before any send. On any uncertain outcome stop campaign;
    reservations are never refunded. Historical authorizations are rejected.
    """
    approval_hash=validate_authorization(approval)
    if (ledger.get('schema')!='se6-successor-reservations-v2' or ledger.get('campaign')!=CAMPAIGN or
            ledger.get('approval_sha256')!=approval_hash):
        raise ValueError('Ledger authorization/identity mismatch')
    reservations=ledger['reservations']
    if len(reservations)>=len(ORDER) or (case_id,round_index)!=ORDER[len(reservations)]:
        raise ValueError('Campaign sequence exhausted/repeated/out of order')
    if [(r['case_id'],r['round_index']) for r in reservations]!=ORDER[:len(reservations)]:
        raise ValueError('Reservation sequence tampered')
    from .models import ModelSettings
    from .provider_router import payload_bytes
    model=ModelSettings.from_change(prepared['model_settings'])
    rebuilt=prepare_pair(case_id,round_index,load_public()[case_id][round_index],model,
        {lane:[m['content'] for m in prepared['messages'][lane] if m['role']=='assistant'] for lane in ('se6','baseline')},
        prepared['native_context'])
    if rebuilt!=prepared:
        raise ValueError('Prepared provenance/schema mismatch')
    raw={lane:payload_bytes(model,{'input':prepared['messages'][lane]}) for lane in ('se6','baseline')}
    sizes={lane:len(value) for lane,value in raw.items()}
    if sizes!=prepared['payload_bytes'] or {lane:sha(v) for lane,v in raw.items()}!=prepared['payload_sha256']:
        raise ValueError('Prepared payload hash/size mismatch')
    amount=sum(sizes.values())
    if (amount!=prepared['total_input_bytes'] or amount>PER_ROUND_INPUT_BYTES or
            prepared['case_id']!=case_id or prepared['round_index']!=round_index):
        raise ValueError('Prepared round identity/byte mismatch')
    if (ledger['calls_reserved']!=2*len(reservations) or
            ledger['output_tokens_reserved']!=2048*len(reservations) or
            ledger['input_bytes_reserved']!=sum(r['input_bytes'] for r in reservations)):
        raise ValueError('Reservation counters mismatch')
    value=deepcopy(ledger)
    value['calls_reserved']+=2;value['output_tokens_reserved']+=2048;value['input_bytes_reserved']+=amount
    if value['calls_reserved']>6 or value['output_tokens_reserved']>6144 or value['input_bytes_reserved']>INPUT_BYTES:
        raise ValueError('Capped campaign exhausted')
    value['reservations'].append({'case_id':case_id,'round_index':round_index,'input_bytes':amount,
                                'payload_sha256':prepared['payload_sha256']})
    return value
