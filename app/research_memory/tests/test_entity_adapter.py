"""Synthetic DEVELOPMENT contracts. No benchmark gold, model, or World run."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,os,subprocess,sys
import pytest
from research_memory import Memory
from research_memory import entity
from research_memory.format import digest,trajectory_chunks

def history(source='DEVELOPMENT-SOURCE-A',text='The orchid locker label is blue.'):
    return {'id':source,'domain':'SYNTHETIC_DEVELOPMENT','environment':'LOCAL_TEXT_FIXTURE',
        'goal':'Read the historical bulletin','start_url':'https://fixture.invalid/bulletin','outcome':'reported complete',
        'states':[{'state_index':0,'step':0,'url':'https://fixture.invalid/bulletin','action':'read',
            'text':text,'screenshot':None}]}

def memory(tmp_path):return Memory(tmp_path/'own',context_char_budget=12000,storage_byte_budget=16*1024*1024)
def text(context):return '\n'.join(x['value'] for x in context)

def test_actual_entity_candidate_becoming_query_and_duplicate_are_not_world_verification(tmp_path):
    m=memory(tmp_path);source=history();insert=m.insert(source);snapshot=m.store.reconstruct()
    assert insert['status']=='ADMITTED_AS_REPORTED_PROVISIONAL' and insert['trajectory_sha256']==digest(source)
    assert snapshot.state.shadow_mode and not snapshot.state.production_authoritative
    assert all(r.status.value=='PROVISIONAL' and r.epistemic_status.value=='reported' for r in snapshot.state.memory.records)
    assert not any(e.payload.payload_type=='verification' for e in snapshot.historical_events)
    context=m.query('What is the orchid locker label?');assert 'blue' in text(context)
    assert all(x['type']=='text' and 'REPORTED / PROVISIONAL' in x['value'] for x in context)
    assert m.last_trace['consumed'] and m.last_trace['world_verification'] is False
    for row in m.last_trace['consumed']:
        r=next(r for r in snapshot.state.memory.records if r.memory_id==row['memory_id'])
        assert row['content_sha256']==digest(r.content_summary) and row['source_event_ids']==list(r.source_event_ids)
        assert any(e.event_id in r.source_event_ids and e.provenance.value=='EXTERNAL_RETRIEVED' for e in snapshot.historical_events)
    pin=hashlib.sha256(m.store.path.read_bytes()).hexdigest();version=snapshot.state.state_version
    assert m.insert(source)['status']=='ALREADY_ADMITTED_NO_MUTATION'
    assert m.store.reconstruct().state.state_version==version and hashlib.sha256(m.store.path.read_bytes()).hexdigest()==pin
    changed=deepcopy(source);changed['states'][0]['text']='Different bytes under the same source identifier.'
    with pytest.raises(ValueError,match='SOURCE_ID_CHANGED'):m.insert(changed)


@pytest.mark.parametrize('fault',['image','raw_content','unknown','missing_text','ambiguous_text','wrong_header'])
def test_unsupported_modalities_and_shapes_are_rejected_without_memory_events(tmp_path,fault):
    m=memory(tmp_path);source=history();version=m.store.reconstruct().state.state_version
    if fault=='image':source['states'][0]['screenshot']='required-original.png'
    if fault=='raw_content':source={'id':'opaque','content':{'anything':'not arbitrarily flattened'}}
    if fault=='unknown':source['evaluator_answer']='forbidden-field'
    if fault=='missing_text':source['states'][0].pop('text')
    if fault=='ambiguous_text':source['states'][0]['accessibility_tree']='second source'
    if fault=='wrong_header':source['environment']={'private':'metadata'}
    with pytest.raises(ValueError):m.insert(source)
    assert m.store.reconstruct().state.state_version==version
    with pytest.raises(ValueError,match='UNSUPPORTED_MODALITY_QUERY_IMAGE'):m.query('Question','required.png')


def test_real_sqlite_checkpoint_is_consumed_by_a_distinct_cold_process(tmp_path):
    m=memory(tmp_path);m.insert(history());expected=m.query('orchid locker');trace=m.last_trace;saved=m.save(m.root/'checkpoint')
    request={'operation':'query','root':str(m.root),'context_char_budget':12000,'storage_byte_budget':16*1024*1024,
        'path':str(m.root/'checkpoint'),'question':'orchid locker','query_image':None}
    child=subprocess.run([sys.executable,'-B','-m','research_memory.worker'],input=json.dumps(request),
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=20,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'})
    assert child.returncode==0,child.stderr+child.stdout
    result=json.loads(child.stdout);assert result['context']==expected
    assert result['trace']['process_id']!=os.getpid() and result['trace']['entity_state_id']==saved['entity_state_id']
    assert result['trace']['context_sha256']==trace['context_sha256'] and result['trace']['consumed']==trace['consumed']
    assert hashlib.sha256((m.root/'checkpoint/entity.sqlite3').read_bytes()).hexdigest()==saved['database_sha256']


@pytest.mark.parametrize('operation',['REVOKE','MARK_EXPIRED','MARK_STALE'])
def test_actual_lifecycle_changes_downstream_context_and_preserves_unrelated_history(tmp_path,operation):
    m=memory(tmp_path);m.insert(history());m.insert(history('DEVELOPMENT-SOURCE-B','The weather bulletin reports cloudy skies.'))
    before=m.query('orchid weather');assert 'orchid' in text(before) and 'cloudy' in text(before)
    snapshot=m.store.reconstruct();target=next(r for r in snapshot.state.memory.records if r.subject.startswith('history_chunk:') and 'orchid locker' in r.content_summary)
    receipt=m.mark_inactive(target.memory_id,operation=operation)
    after=m.query('orchid weather');assert 'orchid locker' not in text(after) and 'cloudy' in text(after)
    assert target.memory_id not in {r['memory_id'] for r in m.last_trace['consumed']}
    assert m.store.reconstruct().state.state_version>snapshot.state.state_version and receipt['receipt_id']
    assert any(r.memory_id==target.memory_id for r in m.store.reconstruct().state.memory.records)  # append-only historical evidence.


def test_older_checkpoint_cannot_resurrect_revoked_memory_and_failed_load_restores_current_view(tmp_path):
    m=memory(tmp_path);m.insert(history());m.save(m.root/'checkpoint');m.query('orchid')
    target=m.last_trace['consumed'][0]['memory_id'];m.mark_inactive(target)
    with pytest.raises(ValueError,match='CHECKPOINT_STALE'):m.load(m.root/'checkpoint')
    assert m.query('orchid')==[]


def test_tampered_sqlite_snapshot_and_outside_save_paths_fail_closed(tmp_path):
    m=memory(tmp_path);m.insert(history());m.save(m.root/'checkpoint')
    db=m.root/'checkpoint/entity.sqlite3';db.write_bytes(db.read_bytes()+b'tamper')
    with pytest.raises(ValueError,match='COLD_CHECKPOINT_PIN'):m.load(m.root/'checkpoint')
    with pytest.raises(ValueError,match='OWN_ROOT_ONLY'):m.save(tmp_path/'outside')


def test_partial_ingestion_is_not_answerable_or_automatically_replayed(tmp_path,monkeypatch):
    m=memory(tmp_path);source=history();original=entity.commit_candidate;calls=[]
    def interrupted(*args,**kwargs):
        calls.append(kwargs['subject'])
        if len(calls)>1:raise OSError('DEVELOPMENT_ONLY interrupted admission before manifest')
        return original(*args,**kwargs)
    monkeypatch.setattr(entity,'commit_candidate',interrupted)
    with pytest.raises(OSError):m.insert(source)
    assert m.query('historical bulletin orchid')==[]
    with pytest.raises(ValueError,match='PARTIAL_INSERT'):m.insert(source)


def test_absent_applicable_evidence_remains_unknown_and_context_budget_is_exact(tmp_path):
    m=memory(tmp_path);assert m.query('unseen term')==[] and m.last_trace['status']=='UNKNOWN_NO_APPLICABLE_ACTIVE_MEMORY'
    m.insert(history(text='orchid '*700));context=m.query('orchid')
    assert sum(len(x['value']) for x in context)<=m.context_char_budget
    assert all('evaluator_answer' not in x['value'] for x in context)
