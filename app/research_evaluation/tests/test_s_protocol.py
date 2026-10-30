from pathlib import Path
from copy import deepcopy
import hashlib,json
import pytest
from research_evaluation.s_public import sanitize_case,scrub_recursive,assert_no_private,score_case,aggregate,sha
from research_memory.sessions_format import history_sha256,session_sha256,history_spans

def raw_case():
    return dict(question_id='SYNTHETIC_ID_NOT_PUBLIC',question_type='single-session-assistant',answer='amber cabinet',
        question='Where are receipts?',question_date='2026-10-29',
        haystack_session_ids=['answer_source','other','answer_source'],haystack_dates=['2025-01-01','2025-01-02','2025-02-01'],
        haystack_sessions=[[dict(role='user',content='Remember this.',has_answer=False),dict(role='assistant',content='Amber cabinet.',HAS_ANSWER=True)],
            [dict(role='user',content='Unrelated weather.',has_answer=False)],
            [dict(role='user',content='Remember this.',has_answer=False),dict(role='assistant',content='Amber cabinet.',HAS_ANSWER=True)]],
        answer_session_ids=['answer_source'])
def clean():return sanitize_case(raw_case(),dataset_sha256='a'*64,dataset_revision='TEST_ONLY')
def entry(public,index):
    history=public['history'];session=history['sessions'][index];hsha=history_sha256(history);pin=session_sha256(session)
    return dict(**session,source_ref=f'session-report:{hsha}:session:{index}:sha256:{pin}',content_sha256=pin,
        history_sha256=hsha,session_index=index,source_offsets=history_spans(history)[index],score=1)

def test_full_history_preserves_assistant_turns_duplicate_occurrences_and_dates():
    public,private=clean();sessions=public['history']['sessions']
    assert len(sessions)==3 and sessions[0]['session_id']==sessions[2]['session_id']
    assert sessions[0]['timestamp']!=sessions[2]['timestamp']
    assert sessions[0]['turns'][1]==dict(role='assistant',content='Amber cabinet.')
    assert all('answer' not in s['session_id'] for s in sessions)
    assert private['removed_private_key_counts']['has_answer']==5
    assert_no_private(public)

def test_recursive_private_metadata_removed_without_changing_legitimate_text():
    value={'x':[{'has_answer':True,'HAS_ANSWER':False,'content':'The phrase has_answer is legitimate content.',
        'nested':{'answer':'private','keep':3}}]}
    assert scrub_recursive(value)=={'x':[{'content':'The phrase has_answer is legitimate content.','nested':{'keep':3}}]}

def test_unrecognized_legitimate_turn_fields_fail_instead_of_silent_truncation():
    raw=raw_case();raw['haystack_sessions'][0][0]['tool_calls']=['unmodelled']
    with pytest.raises(ValueError,match='UNSUPPORTED_LEGITIMATE_TURN_SCHEMA'):sanitize_case(raw,dataset_sha256='a'*64,dataset_revision='TEST_ONLY')

def test_any_exact_duplicate_id_occurrence_can_resolve_against_real_source():
    public,private=clean()
    for index in [0,2]:
        score=score_case(public,private['required_session_ids'],dict(sessions=[entry(public,index)]))
        assert score['recall_at_5']==1 and score['all_evidence_success']==1 and not score['invalid_evidence']

@pytest.mark.parametrize('fault',['invented_id','content','content_hash','history_hash','reference','offset','turn_offset'])
def test_asserted_or_corrupt_evidence_earns_no_credit(fault):
    public,private=clean();e=entry(public,0)
    if fault=='invented_id':e['session_id']='invented'
    if fault=='content':e['turns']=[]
    if fault=='content_hash':e['content_sha256']='0'*64
    if fault=='history_hash':e['history_sha256']='0'*64
    if fault=='reference':e['source_ref']='invented'
    if fault=='offset':e['source_offsets']['byte_end']-=1
    if fault=='turn_offset':e['source_offsets']['turns'][0]['byte_start']+=1
    score=score_case(public,private['required_session_ids'],dict(sessions=[e]))
    assert score['recall_at_5']==0 and score['all_evidence_success']==0 and score['invalid_evidence']

def test_multiple_chunks_same_session_id_cannot_inflate_recall():
    public,private=clean();e=entry(public,0)
    score=score_case(public,private['required_session_ids'],dict(sessions=[e,deepcopy(e)]))
    assert score['retrieved_required_count']==1 and score['recall_at_5']==1

def test_failures_remain_in_primary_mean_denominator():
    public,private=clean();success=score_case(public,private['required_session_ids'],dict(sessions=[entry(public,0)]))
    failed=score_case(public,private['required_session_ids'],None,failure='TIMEOUT')
    rows=[dict(arms={a:dict(score=s) for a in ['se6','bm25']}) for s in [success,failed]]
    report=aggregate(rows)
    assert report['arms']['se6']['cases']==2 and report['arms']['se6']['recall_at_5']==.5
    assert report['arms']['se6']['failures']==1

def test_no_empty_required_set_can_be_scored_as_success():
    public,_=clean()
    with pytest.raises(ValueError,match='ABSTENTION_EXCLUDED'):score_case(public,[],dict(sessions=[]))
