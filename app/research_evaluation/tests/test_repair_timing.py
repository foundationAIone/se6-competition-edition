"""Timing/transport regressions only; no benchmark cases or model/World calls."""
from types import SimpleNamespace
from copy import deepcopy
import pytest
from research_evaluation.s_worker import timed_call,instrument_baseline,adapter_metrics,execute
from research_evaluation.s_batch import summarize_timing,verify_development_source,run_batch
from research_evaluation.s_public import sha

def test_complete_timing_preserved_when_call_refuses():
    phases={}
    def refuse():raise ValueError('TEST_ONLY_REFUSAL')
    with pytest.raises(ValueError,match='TEST_ONLY_REFUSAL'):timed_call(phases,'validation',refuse)
    assert phases['validation']['wall_seconds']>=0 and phases['validation']['cpu_seconds']>=0

def test_baseline_timing_does_not_replace_kernel_inputs_or_outputs():
    calls=[]
    def exact(*args,**kwargs):calls.append((args,kwargs));return ('UNCHANGED_KERNEL',args,kwargs)
    names=['validate_history','history_sha256','session_sha256','history_spans','canonicalbytes','render_session','rank']
    module=SimpleNamespace(**{name:exact for name in names})
    metrics=instrument_baseline(module)
    result=module.rank('question',['complete source'])
    assert result==('UNCHANGED_KERNEL',('question',['complete source']),{})
    assert calls==[(('question',['complete source']),{})]
    assert metrics['foundation_index_build_and_candidate_ranking']['calls']==1
    assert 'nested' in metrics['foundation_index_build_and_candidate_ranking']['scope']

def test_missing_adapter_subphases_are_unknown_not_zero():
    assert adapter_metrics(object())==dict(status='NOT_SEPARATELY_INSTRUMENTED',unmeasured_not_zero=True)

def test_invalid_subphase_contract_rejects():
    with pytest.raises(ValueError,match='S_WORKER_TIMING_CONTRACT'):adapter_metrics(SimpleNamespace(phase_metrics=[]))

@pytest.mark.parametrize('arm',['se6','bm25'])
def test_worker_rejects_evaluator_fields_before_any_memory_construction(tmp_path,arm):
    with pytest.raises(ValueError,match='S_WORKER_NO_EVALUATOR_FIELDS'):
        execute(tmp_path,arm,dict(operation='query',question='TEST_ONLY',question_date=None,k=5,answer='private'),tmp_path/'canary')

@pytest.mark.parametrize('arm',['se6','bm25'])
def test_worker_enforces_same_five_unique_session_allowance(tmp_path,arm):
    with pytest.raises(ValueError,match='S_WORKER_RETRIEVAL_ALLOWANCE'):
        execute(tmp_path,arm,dict(operation='query',question='TEST_ONLY',question_date=None,k=6),tmp_path/'canary')

def worker(operations):
    return dict(status='COMPLETE',resources=dict(host_cpu_seconds=7,peak_process_rss_bytes=100),
        timing=dict(operations={name:dict(wall_seconds=value,cpu_seconds=value/2) for name,value in operations.items()}))

def test_matched_summary_charges_index_build_inside_query_both_arms():
    phases=[dict(transport=dict(parent_wall_seconds=20),worker=worker(dict(adapter_import=1,store_initialization=2,
        complete_ingest=3,durable_snapshot=4))),dict(transport=dict(parent_wall_seconds=30),worker=worker(dict(
        adapter_import=1,store_initialization=2,complete_cold_restore=5,complete_retrieve_including_index=10)))]
    rows=[dict(arms={arm:dict(phases=deepcopy(phases)) for arm in ['se6','bm25']})]
    report=summarize_timing(rows)
    assert report['arms']['se6']==report['arms']['bm25']
    value=report['arms']['se6']
    assert value['enclosing_all_child_wall_seconds']==50
    assert value['setup_wall_seconds']==13 and value['cold_restore_wall_seconds']==5
    assert value['retrieve_with_actual_index_build_wall_seconds']==10
    assert value['repeated_query_seconds'] is None

def test_failed_worker_timing_is_reported_missing_not_successful_zero():
    phases=[dict(transport=dict(parent_wall_seconds=120),worker=None)]
    rows=[dict(arms={arm:dict(phases=deepcopy(phases)) for arm in ['se6','bm25']})]
    value=summarize_timing(rows)['arms']['se6']
    assert value['missing_or_failed_worker_timings']==1
    assert value['complete_worker_processes']==0
    assert value['cold_restore_wall_seconds'] is None

def test_additional_se6_development_admission_cost_is_not_hidden():
    arms={arm:dict(phases=[dict(transport=dict(parent_wall_seconds=10),worker=worker(dict(
        complete_ingest=2,development_method_source_read=1,development_method_admission=3)))]) for arm in ['se6','bm25']}
    del arms['bm25']['phases'][0]['worker']['timing']['operations']['development_method_source_read']
    del arms['bm25']['phases'][0]['worker']['timing']['operations']['development_method_admission']
    report=summarize_timing([dict(arms=arms)])
    assert report['arms']['se6']['setup_wall_seconds']==6
    assert report['arms']['bm25']['setup_wall_seconds']==2

def test_repeat_is_query_only_not_an_unchecked_extra_ingestion(tmp_path):
    with pytest.raises(ValueError,match='S_WORKER_DEVELOPMENT_REPEAT_ONLY_QUERY'):
        execute(tmp_path,'se6',dict(operation='ingest',history={}),tmp_path/'canary',development_repeat=True)

def test_dev_repeat_cannot_be_requested_for_heldout(tmp_path):
    path=tmp_path/'manifest.json';path.write_text('{}')
    with pytest.raises(ValueError,match='HELDOUT_REPEAT_FORBIDDEN'):
        run_batch(path,tmp_path/'never-created','evaluation',development_repeat_case='case-011')
    assert not (tmp_path/'never-created').exists()

def test_development_source_cannot_skip_actual_member_validation(tmp_path,monkeypatch):
    import hashlib,json
    import research_evaluation.s_batch as batch
    app=tmp_path/'app';app.mkdir();monkeypatch.setattr(batch,'APP',app)
    source=app/'fixture.py';source.write_bytes(b'TEST_ONLY_SOURCE')
    files={'fixture.py':hashlib.sha256(source.read_bytes()).hexdigest()}
    frozen=tmp_path/'immutable.json';frozen.write_text(json.dumps(dict(files=files,source_sha256=sha(files))))
    manifest=dict(development_executing_source_files=files,development_executing_source_sha256=sha(files),
        development_source_manifest_path=str(frozen),development_source_manifest_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest())
    assert verify_development_source(manifest)==sha(files)
    source.write_bytes(b'CHANGED_TEST_ONLY_SOURCE')
    with pytest.raises(ValueError,match='DEVELOPMENT_EXECUTING_SOURCE_CHANGED'):verify_development_source(manifest)

def test_absent_development_source_capture_refuses():
    with pytest.raises(ValueError,match='DEVELOPMENT_EXECUTING_SOURCE_BINDING'):verify_development_source({})

def test_exposed_repeat_is_separately_attributed_and_not_primary_first_query():
    phases=[dict(transport=dict(parent_wall_seconds=20),worker=worker(dict(
        complete_retrieve_including_index=10,development_repeated_retrieve_including_index=7)))]
    report=summarize_timing([dict(arms={arm:dict(phases=deepcopy(phases)) for arm in ['se6','bm25']})])
    assert report['arms']['se6']['retrieve_with_actual_index_build_wall_seconds']==10
    assert report['arms']['se6']['repeated_query_seconds']==7
