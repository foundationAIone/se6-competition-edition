import copy,json,subprocess,sys
from pathlib import Path
import pytest
from research_memory.sessions import SessionMemory
from research_memory.sessions_format import validate_history,history_sha256,canonicalbytes,render_session,history_spans

def fixture():
    return dict(source_id='PUBLIC_HISTORY_CONTENT_ID_NOT_QUESTION_ID',
        provenance={'dataset_revision':'TEST_ONLY_SOURCE'},sessions=[
        dict(session_id='s0',timestamp='2024-01-01',turns=[dict(role='user',content='I need an export.'),dict(role='assistant',content='Reports supports PDF export.')]),
        dict(session_id='s1',timestamp='2024-01-02',turns=[dict(role='user',content='The bike is blue.'),dict(role='assistant',content='The road bicycle is blue.')])])

def test_lossless_full_history_is_actual_provisional_entity_memory(tmp_path):
    source=fixture();m=SessionMemory(tmp_path/'memory');result=m.ingest(source)
    assert result['session_count']==2 and result['turn_count']==4 and result['entity_version']==1
    snapshot=m.store.reconstruct();record=snapshot.state.memory.records[0]
    assert record.status.value=='PROVISIONAL' and record.epistemic_status.value=='reported'
    assert snapshot.state.shadow_mode and not snapshot.state.production_authoritative
    assert m._collections(snapshot)[0][1]==source
    selected=m.retrieve('Where is PDF export?',question_date='2024-01-03')['sessions']
    assert selected[0]['session_id']=='s0' and selected[0]['turns']==source['sessions'][0]['turns']
    assert m.last_trace['selected'][0]['memory_id']==record.memory_id
    offsets=selected[0]['source_offsets'];raw=canonicalbytes(source)
    assert json.loads(raw[offsets['byte_start']:offsets['byte_end']])==source['sessions'][0]
    assert [json.loads(raw[t['byte_start']:t['byte_end']]) for t in offsets['turns']]==source['sessions'][0]['turns']
    before=m.store.reconstruct().state.entity_state_id;m.ingest(source)
    assert m.store.reconstruct().state.entity_state_id==before

def test_large_unicode_history_exceeds_old_limit_without_loss(tmp_path):
    source=fixture();source['sessions'][0]['turns'][1]['content']='é🚲 export '*60000
    assert len(canonicalbytes(source))>524288
    m=SessionMemory(tmp_path/'large');m.ingest(source)
    restored=m._collections(m.store.reconstruct())[0][1]
    assert restored==source and m.last_insert['chunk_count']>8
    assert m.retrieve('export')['sessions'][0]['turns'][1]['content']==source['sessions'][0]['turns'][1]['content']

def test_cold_backup_sources_survive_distinct_process(tmp_path):
    root=tmp_path/'cold';m=SessionMemory(root);m.ingest(fixture());m.save(root/'snapshot')
    expected=m.retrieve('PDF export')['sessions']
    script='from research_memory.sessions import SessionMemory;import json,sys;m=SessionMemory(sys.argv[1]);m.load(sys.argv[2]);print(json.dumps(m.retrieve("PDF export")))'
    p=subprocess.run([sys.executable,'-B','-c',script,str(root),str(root/'snapshot')],capture_output=True,text=True,check=True)
    actual=json.loads(p.stdout)
    assert actual['sessions']==expected and actual['trace']['entity_version']==1
    assert actual['trace']['process_id']!=m.last_trace['process_id']

def test_withdrawal_changes_real_context_without_deleting_source(tmp_path):
    m=SessionMemory(tmp_path/'lifecycle');m.ingest(fixture());before=m.retrieve('PDF export')
    mid=before['trace']['selected'][0]['memory_id'];m.mark_inactive(mid)
    assert m.retrieve('PDF export')['sessions']==[]
    assert any(m.payload_root.rglob('*.chunk'))

def test_recursive_labels_and_unknown_fields_refused():
    for key in ['has_answer','answer_session_ids','question_type','question_id','answer']:
        row=fixture();row['provenance'][key]=True
        with pytest.raises(ValueError,match='PRIVATE_LABEL'):validate_history(row)
    row=fixture();row['sessions'][0]['turns'][0]['has_answer']=True
    with pytest.raises(ValueError,match='PRIVATE_LABEL'):validate_history(row)

def test_duplicate_logical_ids_preserve_different_dates_and_dedup_after_ranking(tmp_path):
    row=fixture();row['sessions']=([dict(session_id='duplicate',timestamp='2024-01-01',turns=[dict(role='user',content='export pdf')]),
        dict(session_id='duplicate',timestamp='2024-02-02',turns=[dict(role='user',content='export pdf')])]+
        [dict(session_id=f'unique-{i}',timestamp='2024-01-01',turns=[dict(role='user',content='export')]) for i in range(5)])
    m=SessionMemory(tmp_path/'duplicates');m.ingest(row)
    assert m._collections(m.store.reconstruct())[0][1]==row
    result=m.retrieve('export pdf 02',k=5)
    assert len(result['sessions'])==5 and len({s['session_id'] for s in result['sessions']})==5
    assert result['sessions'][0]['session_id']=='duplicate' and result['sessions'][0]['session_index']==1
    assert result['sessions'][0]['timestamp']=='2024-02-02'
    assert result['trace']['source_session_occurrences']==7 and result['trace']['available_unique_sessions']==6

def test_payload_and_snapshot_tamper_fail_closed(tmp_path):
    m=SessionMemory(tmp_path/'tamper');m.ingest(fixture());m.save(m.root/'snapshot')
    first=next(m.payload_root.rglob('*.chunk'));first.write_bytes(first.read_bytes()+b'bad')
    with pytest.raises(ValueError,match='CHUNK_CONTENT_PIN'):m.retrieve('PDF export')
    # The genuine saved source is separate and retains the original bytes.
    m.load(m.root/'snapshot');assert m.retrieve('PDF export')['sessions']
    part=next((m.root/'snapshot/session-sources').rglob('*.chunk'));part.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='COLD_SOURCE_FILE_PIN'):SessionMemory(m.root).load(m.root/'snapshot')

def test_unique_session_allowance_and_unchanged_lexical_rule(tmp_path):
    row=fixture();row['sessions']=[dict(session_id=f's{i}',timestamp='2024-01-01',turns=[dict(role='user',content='export '+('pdf' if i==3 else 'html'))]) for i in range(7)]
    m=SessionMemory(tmp_path/'rank');m.ingest(row);answer=m.retrieve('export PDF',k=5)
    assert [s['session_id'] for s in answer['sessions']]==['s3','s0','s1','s2','s4']
    assert len(set(s['session_id'] for s in answer['sessions']))==5
    with pytest.raises(ValueError,match='ALLOWANCE'):m.retrieve('export',k=6)
    assert m.retrieve('not_a_presentword')['sessions']==[]

def test_existing_text_query_consumes_actual_session_selection(tmp_path):
    m=SessionMemory(tmp_path/'interface');m.ingest(fixture());context=m.query('PDF export')
    assert context[0]['type']=='text' and 'Reports supports PDF export.' in context[0]['value']
    assert m.last_retrieval['sessions'][0]['session_id']=='s0'
    assert m.last_trace['selected'][0]['memory_id'].startswith('entity_memory_')
    assert m.last_trace['reader_context_sha256']
    with pytest.raises(ValueError,match='MODALITY'):m.query('export','image.png')
