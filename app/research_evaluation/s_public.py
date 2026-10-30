"""TRUSTED evaluator-only cleaned LongMemEval-S scrubber and exact scorer.

Never bind this file, raw data, annotations or case manifests into contestants.
Session aliases hide the answer/noans markers present in some source IDs.
"""
from copy import deepcopy
import hashlib,json

PRIVATE={'answer','answers','answer_session_ids','has_answer','question_id','question_type',
    'eval_function','evaluation','evaluator','gold','gold_answer','reference_answer','labels','label','metadata'}
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def require(ok,code):
    if not ok:raise ValueError(code)
def scrub_recursive(value):
    if isinstance(value,dict):
        return {k:scrub_recursive(v) for k,v in value.items() if k.casefold() not in PRIVATE and not k.casefold().startswith(('gold_','eval_'))}
    if isinstance(value,list):return [scrub_recursive(v) for v in value]
    return deepcopy(value)
def assert_no_private(value):
    if isinstance(value,dict):
        require(not any(k.casefold() in PRIVATE or k.casefold().startswith(('gold_','eval_')) for k in value),'PRIVATE_METADATA_IN_PUBLIC_PAYLOAD')
        for v in value.values():assert_no_private(v)
    elif isinstance(value,list):
        for v in value:assert_no_private(v)

def removed_key_counts(value):
    counts={}
    def visit(node):
        if isinstance(node,dict):
            for key,child in node.items():
                name=key.casefold()
                if name in PRIVATE or name.startswith(('gold_','eval_')):counts[name]=counts.get(name,0)+1
                visit(child)
        elif isinstance(node,list):
            for child in node:visit(child)
    visit(value);return counts

def sanitize_case(raw,*,dataset_sha256,dataset_revision):
    ids=raw['haystack_session_ids'];dates=raw['haystack_dates'];sessions=raw['haystack_sessions']
    require(len(ids)==len(dates)==len(sessions),'SOURCE_SESSION_ALIGNMENT')
    clean=[];aliases={}
    for sid,date,turns in zip(ids,dates,sessions):
        require(type(sid) is str and type(date) is str and type(turns) is list,'SOURCE_SESSION_TYPES')
        alias='session_'+hashlib.sha256((dataset_sha256+':'+sid).encode()).hexdigest()[:32]
        aliases[sid]=alias;turns=scrub_recursive(turns)
        require(all(type(t) is dict and set(t)=={'role','content'} and type(t['role']) is str and type(t['content']) is str for t in turns),
            'UNSUPPORTED_LEGITIMATE_TURN_SCHEMA_NOT_SILENTLY_DROPPED')
        clean.append(dict(session_id=alias,timestamp=date,turns=turns))
    history=dict(source_id='history_'+sha(clean),sessions=clean,
        provenance=dict(dataset_revision=dataset_revision,source_file_sha256=dataset_sha256))
    public=dict(history=history,question=raw['question'],question_date=raw['question_date'])
    assert_no_private(public)
    required=list(dict.fromkeys(raw['answer_session_ids']))
    require(required and all(s in aliases for s in required),'REQUIRED_SOURCE_SESSION_NOT_IN_HISTORY')
    private=dict(question_id=raw['question_id'],question_type=raw['question_type'],answer=raw['answer'],
        required_session_ids=[aliases[s] for s in required],original_session_aliases=aliases,
        source_history_sha256=sha(history),public_payload_sha256=sha(public),removed_private_key_counts=removed_key_counts(raw))
    return public,private

def score_case(public,required_session_ids,result,*,failure=None,k=5):
    """All selected cases contribute, including failed ingest/query => zero."""
    required=set(required_session_ids);require(required,'ABSTENTION_EXCLUDED_FROM_LOCATION_RECALL')
    reasons=[];valid=[]
    if failure is not None:
        return dict(recall_at_5=0.0,all_evidence_success=0,coverage=False,failed=True,failure=failure,
            returned_session_ids=[],resolved_session_ids=[],required_count=len(required),retrieved_required_count=0,
            empty_retrieval=True,invalid_evidence=[],evidence_bytes=0)
    returned=result.get('sessions') if isinstance(result,dict) else None
    if not isinstance(returned,list) or len(returned)>k:
        return score_case(public,required_session_ids,{},failure='INVALID_OR_OVERLIMIT_SESSION_RESPONSE',k=k)
    originals=public['history']['sessions'];seen=set()
    source=canonical(public['history']);history_hash=sha(public['history'])
    for entry in returned:
        if not isinstance(entry,dict):reasons.append('NON_OBJECT_SESSION');continue
        sid=entry.get('session_id')
        if sid in seen:continue
        seen.add(sid)
        index=entry.get('session_index')
        if type(index) is not int or not 0<=index<len(originals) or originals[index]['session_id']!=sid:
            reasons.append('UNRESOLVED_SESSION_ID_OR_OCCURRENCE');continue
        expected=originals[index]
        actual={key:entry.get(key) for key in ['session_id','timestamp','turns']}
        if actual!=expected:reasons.append('SOURCE_CONTENT_MISMATCH');continue
        if entry.get('content_sha256')!=sha(expected):reasons.append('SOURCE_HASH_MISMATCH');continue
        if entry.get('history_sha256')!=history_hash or entry.get('session_index')!=index:
            reasons.append('HISTORY_OR_ORDER_PROVENANCE_MISMATCH');continue
        ref=entry.get('source_ref')
        suffix=f'{history_hash}:session:{index}:sha256:{sha(expected)}'
        if ref not in {'session-report:'+suffix,'history:'+suffix}:
            reasons.append('UNRESOLVED_SOURCE_REFERENCE');continue
        span=entry.get('source_offsets',{})
        a,b=span.get('byte_start'),span.get('byte_end')
        if type(a) is not int or type(b) is not int or not 0<=a<b<=len(source) or source[a:b]!=canonical(expected):
            reasons.append('SOURCE_BYTE_SPAN_MISMATCH');continue
        offsets=span.get('turns')
        if not isinstance(offsets,list) or len(offsets)!=len(expected['turns']):
            reasons.append('TURN_SOURCE_SPAN_COUNT_MISMATCH');continue
        turn_ok=True
        for i,(turn,offset) in enumerate(zip(expected['turns'],offsets)):
            ta,tb=offset.get('byte_start'),offset.get('byte_end')
            if (type(ta) is not int or type(tb) is not int or not a<=ta<tb<=b or offset.get('turn_index')!=i
                or source[ta:tb]!=canonical(turn) or offset.get('sha256')!=sha(turn)):
                turn_ok=False;break
        if not turn_ok:reasons.append('TURN_SOURCE_BYTE_SPAN_MISMATCH');continue
        valid.append(sid)
    hits=set(valid)&required
    return dict(recall_at_5=len(hits)/len(required),all_evidence_success=int(hits==required),coverage=True,
        failed=False,failure=None,returned_session_ids=[s.get('session_id') for s in returned if isinstance(s,dict)],
        resolved_session_ids=valid,required_count=len(required),retrieved_required_count=len(hits),
        empty_retrieval=not returned,invalid_evidence=reasons,evidence_bytes=len(canonical(returned)))

def aggregate(rows):
    require(rows,'EMPTY_FROZEN_EVALUATION')
    arms={}
    for arm in ['se6','bm25']:
        scores=[r['arms'][arm]['score'] for r in rows]
        arms[arm]=dict(cases=len(scores),recall_at_5=sum(s['recall_at_5'] for s in scores)/len(scores),
            all_evidence_success=sum(s['all_evidence_success'] for s in scores)/len(scores),
            successfully_processed=sum(not s['failed'] for s in scores),failures=sum(s['failed'] for s in scores),
            empty_retrievals=sum(s['empty_retrieval'] for s in scores))
    wins=sum(r['arms']['se6']['score']['recall_at_5']>r['arms']['bm25']['score']['recall_at_5'] for r in rows)
    losses=sum(r['arms']['se6']['score']['recall_at_5']<r['arms']['bm25']['score']['recall_at_5'] for r in rows)
    return dict(arms=arms,paired_se6_wins=wins,paired_se6_losses=losses,paired_ties=len(rows)-wins-losses,
        primary='Arithmetic mean session evidence recall@5 over EVERY frozen selected case; failures contribute0.',
        scope='Custom LongMemEval-S retrieval subset — SE6 versus BM25 — no answering model.')
