from pathlib import Path
from decimal import Decimal
import hashlib,json,subprocess,sys
import pytest
from research_controls.bm25_notes import Memory
from research_evaluation.manifests import prepare_manifests
from research_evaluation.paid_runner import preparation,preflight,TARIFF_BOUND
from research_evaluation.official_scoring import OfficialScoring
from research_evaluation.isolation_worker import execute
from research_evaluation.protocol import build_reader_request

APP=Path(__file__).resolve().parents[2]
LANE=APP.parent

def trajectory():
    return dict(id='SYNTHETIC_DEVELOPMENT_ONLY',goal='Inspect the export control',start_url='https://example.invalid/',
        outcome='Reported',states=[dict(url='https://example.invalid/',action='read',text='Reports contains Export PDF.',screenshot=None)])

def test_ranking_allocation_survives_chronological_reordering(tmp_path):
    memory=Memory(root=tmp_path,context_char_budget=260)
    memory.documents=[dict(text='background '*200,source_ref='earlier',trajectory_sha256='same',order=0),
        dict(text='needle THE_BEST_EVIDENCE',source_ref='best',trajectory_sha256='same',order=1)]
    context=memory.query('needle')
    assert 'THE_BEST_EVIDENCE' in ''.join(x['value'] for x in context)
    assert memory.last_trace['context_characters']<=260
    assert memory.last_trace['source_refs']==['earlier','best']

def test_control_real_save_load_and_exact_context(tmp_path):
    memory=Memory(root=tmp_path);memory.insert(trajectory());expected=memory.query('Export PDF')
    memory.save(tmp_path/'snapshot');cold=Memory(root=tmp_path);cold.load(tmp_path/'snapshot')
    assert cold.query('Export PDF')==expected
    assert cold.last_trace['ordinary_memory_enabled'] is True

def test_control_tampered_saved_state_rejected(tmp_path):
    memory=Memory(root=tmp_path);memory.insert(trajectory());memory.save(tmp_path/'snapshot')
    path=tmp_path/'snapshot/control-memory.json';state=json.loads(path.read_text())
    state['material']['documents'][0]['text']='FORGED'
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='CONTROL_COLD_HASH'):Memory(root=tmp_path).load(tmp_path/'snapshot')

@pytest.mark.parametrize('image',['','image.png'])
def test_query_image_contract_matches_se6_strict_none(tmp_path,image):
    with pytest.raises(ValueError,match='UNSUPPORTED_MODALITY'):Memory(root=tmp_path).query('question',image)
    with pytest.raises(ValueError,match='UNSUPPORTED_MODALITY'):
        execute(tmp_path,'conventional',dict(operation='query',question='question',query_image=image),tmp_path/'canary')

def test_shared_formatter_does_not_load_se6_into_conventional_process(tmp_path):
    code='import sys,json;sys.path.insert(0,'+repr(str(APP))+');from research_controls.bm25_notes import Memory;m=Memory(root='+repr(str(tmp_path))+');m.insert('+repr(trajectory())+');assert "se666_core.entity_store" not in sys.modules;assert "pydantic" not in sys.modules;print("PURE_FORMATTER_IMPORT_ONLY")'
    result=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='PURE_FORMATTER_IMPORT_ONLY'

def metadata(qid,histories,env,eligible=True):
    return dict(question_id=qid,question_type='synthetic_type',source_histories=histories,environment_ids=[env],
        modality_eligible=eligible,raw_data_sha256='a'*64)

def test_excluded_connector_still_prevents_history_split():
    rows=[metadata('a',['x'],'a'),metadata('bridge',['x','y'],'b',False),metadata('c',['y'],'c')]
    result=prepare_manifests(rows,development_questions=1,evaluation_questions=1,min_eval_clusters=1,max_per_cluster=1)
    assert result['status']=='BLOCKED' and not result['evaluation']['questions']

def test_gold_is_not_an_accepted_manifest_input():
    row=metadata('a',['x'],'a');row['answer']='do not expose'
    with pytest.raises(ValueError,match='TRUSTED_METADATA_SCHEMA_NO_GOLD'):prepare_manifests([row])

def test_paid_preflight_blocks_before_any_provider_or_credential_interface():
    quote=preparation({'status':'BLOCKED_NOT_A_FROZEN_RUN','evaluation_independent_units':1})
    assert quote['status']=='BLOCKED_NOT_AN_APPROVAL' and quote['provider_calls']==0
    assert quote['calls']['total']==48 and TARIFF_BOUND==Decimal('3.8633472')
    with pytest.raises(ValueError,match='EXTERNAL_DATA_CONTRACT_BLOCKED'):preflight(quote)

def test_paid_proposal_tampering_cannot_clear_blockers():
    quote=preparation({});quote['blockers']=[]
    with pytest.raises(ValueError,match='PAID_PROPOSAL_HASH'):preflight(quote)

def test_worker_refuses_private_evaluator_metadata_without_reading_canary(tmp_path):
    payload=dict(operation='query',question='question',query_image=None,question_id='private-evaluator-only')
    with pytest.raises(ValueError,match='PUBLIC_PAYLOAD_NO_EVALUATOR_METADATA'):
        execute(tmp_path,'conventional',payload,tmp_path/'canary')

def test_prepared_reader_input_consumes_exact_context_and_same_settings():
    contexts=[[dict(type='text',value='Reports contains Export PDF.')],
        [dict(type='text',value='REPORTED source evidence: Reports contains Export PDF.')]]
    bodies=[build_reader_request('Which tab?',context) for context in contexts]
    assert json.loads(bodies[0]['messages'][1]['content'])['historical_memory_context']==contexts[0]
    assert json.loads(bodies[1]['messages'][1]['content'])['historical_memory_context']==contexts[1]
    assert bodies[0]['messages'][0]==bodies[1]['messages'][0]
    assert {k:bodies[0][k] for k in ['model','temperature','max_tokens']}=={k:bodies[1][k] for k in ['model','temperature','max_tokens']}
    with pytest.raises(ValueError,match='READER_TEXT_CONTEXT_ONLY'):
        build_reader_request('Which tab?',[dict(type='text',value='Reported',question_id='private')])

def official():
    path=LANE/'external/longmemeval-v2/evaluation/qa_eval_metrics.py'
    return OfficialScoring(path,hashlib.sha256(path.read_bytes()).hexdigest())

def test_official_deterministic_semantics_are_used_without_provider():
    scoring=official()
    assert scoring.deterministic('norm_phrase_set_match','Red, blue.','red;blue')
    assert not scoring.deterministic('norm_phrase_set_match_ordered','blue red','red;blue')
    assert scoring.deterministic('mc_choice_set_match','A and C','AC')
    with pytest.raises(ValueError,match='UNSUPPORTED_OR_MODEL_JUDGED_EVALUATOR'):
        scoring.deterministic('llm_gotchas_checker','answer','reference')

def test_official_judge_prompts_are_exact_but_no_judgment_is_claimed():
    scoring=official();kwargs=dict(question_text='Synthetic question',reference_answer='Synthetic reference',
        model_full_response='Synthetic response',model_final_answer='Synthetic response')
    for kind in ['gotchas','abstention']:
        actual=scoring.judge_messages(kind,question=kwargs['question_text'],reference=kwargs['reference_answer'],response=kwargs['model_full_response'])
        assert actual==getattr(scoring.module,'_build_'+kind+'_judge_messages')(**kwargs)
        assert not any('arm' in message for message in actual)
    assert scoring.parse_judge('{"label":1,"reason":"synthetic parser check"}')[0]==1
