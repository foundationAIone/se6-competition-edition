"""Offline new profile admission and complete-response contract; zero providers."""
from dataclasses import replace
import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'private-native'))
from src.workbench.models import ModelSettings,PairSettings
from src.workbench.provider_reasoning_control import COMPLETE_PAIR,MODEL,PROVIDER,NONE_PROBE,provider_fields,complete_pair_contract
from src.workbench.provider_router import payload_for,parse_nebius_completion,completion_token_counts
from src.workbench.transport import ProviderFailure
from src.workbench.config import Settings,Limits

def model(**changes):return ModelSettings(**{'model':MODEL,'temperature':0,'max_output_tokens':2048,'provider_reasoning_control':COMPLETE_PAIR,**changes})
def response(content='{"answer":"conditional"}',finish='stop',reasoning=0):
 usage={'prompt_tokens':12,'completion_tokens':8,'total_tokens':20}
 if reasoning!='missing':usage['completion_tokens_details']={'reasoning_tokens':reasoning}
 return json.dumps({'model':MODEL,'choices':[{'message':{'content':content,'reasoning_content':'Not a final answer'},'finish_reason':finish}],'usage':usage}).encode()
def parse(**kw):return parse_nebius_completion(response(**kw),MODEL,provider_reasoning_control=COMPLETE_PAIR)

def test_new_profile_wire_and_public_contract_no_credential_lookup(monkeypatch):
 from src.workbench import provider_router
 monkeypatch.setattr(provider_router,'credential_status',lambda settings:pytest.fail('No key lookup allowed'))
 settings=model();wire=payload_for(settings,{'input':[{'role':'user','content':'Return a JSON object.'}]})
 assert wire=={'model':MODEL,'messages':[{'role':'user','content':'Return a JSON object.'}],'max_tokens':2048,'stream':False,'temperature':0,'reasoning_effort':'none','response_format':{'type':'json_object'}}
 assert settings.public()['provider_reasoning_control']==complete_pair_contract()
 assert 'UNVERIFIED' in settings.public()['reasoning_policy']
 assert settings.stored()['provider_reasoning_control']==COMPLETE_PAIR
 assert ModelSettings.from_change(settings.stored())==settings

@pytest.mark.parametrize('changes',[{'temperature':None},{'temperature':1},{'temperature':True},{'max_output_tokens':1024},{'max_output_tokens':4096},{'reasoning_effort':'none'},{'response_policy':'invented'},{'model':'gpt-4.1-mini-2025-04-14'},{'provider_reasoning_control':'UNKNOWN'}])
def test_bad_profile_has_no_fallback(changes):
 with pytest.raises(ValueError):model(**changes)

def test_matched_settings_and_new_exact_session_budget_no_authority():
 m=model();limits=Limits(active_tasks=1,active_workers=2,rounds_per_task=1,calls_per_task=2,output_reservation_per_task=4096,input_bytes_per_task=49152)
 settings=Settings(PairSettings('matched',m,m),limits=limits,integration='auto',core_revision='canonical-realization-v1',context_policy='audit_v3')
 assert settings.pair.se6==settings.pair.baseline
 for altered in (replace(limits,calls_per_task=4),replace(limits,rounds_per_task=2),replace(limits,input_bytes_per_task=65536)):
  with pytest.raises(ValueError,match='Complete pair'):replace(settings,limits=altered)
 with pytest.raises(ValueError):PairSettings('matched',m,ModelSettings(model=MODEL,temperature=0,max_output_tokens=2048))
 with pytest.raises(ValueError,match='Complete pair'):replace(settings,pair=PairSettings('independent',m,m))

def test_reported_zero_reasoning_and_unknown_remain_distinct():
 value=parse();assert value['complete_final_json']=={'answer':'conditional'}
 assert value['completion_accounting']=={'completion_tokens':8,'reasoning_tokens':0,'reported_non_reasoning_completion_tokens':8}
 assert value['reasoning_suppression']=='PROVIDER_REPORTED_ZERO_REASONING_TOKENS'
 unknown=parse(reasoning='missing');assert unknown['completion_accounting']['reasoning_tokens'] is None and unknown['completion_accounting']['reported_non_reasoning_completion_tokens'] is None
 assert unknown['reasoning_suppression']=='UNKNOWN_NOT_REPORTED'

@pytest.mark.parametrize('reasoning',[1,9,-1,0.5,True,'0'])
def test_reported_positive_or_contradictory_reasoning_rejected(reasoning):
 with pytest.raises(ProviderFailure,match='REASONING_ACCOUNTING'):parse(reasoning=reasoning)

@pytest.mark.parametrize('content',['{"answer":','```json\n{}\n```','[]','{} {}','{"a":1,"a":2}','{"a":NaN}','',None])
def test_only_complete_single_final_json_object(content):
 with pytest.raises(ProviderFailure):parse(content=content)

@pytest.mark.parametrize('finish',['length','tool_calls','content_filter',None])
def test_stop_only_no_repair_retry_or_reasoning_substitution(finish):
 with pytest.raises(ProviderFailure):parse(finish=finish)
 with pytest.raises(ProviderFailure,match='NO_FINAL_CONTENT'):parse(content=None)


def test_final_byte_bound_and_unknown_parser_profile():
 with pytest.raises(ProviderFailure,match='BYTE_CAP'):parse(content=json.dumps({'value':'x'*32769}))
 with pytest.raises(ProviderFailure,match='no fallback'):parse_nebius_completion(response(),MODEL,provider_reasoning_control='UNKNOWN')


def test_legacy_controls_wire_and_generic_parse_unchanged():
 from src.workbench.successor_evaluation_profile import CONTROL as successor
 old=ModelSettings(model=MODEL,temperature=None,max_output_tokens=1024,provider_reasoning_control=successor)
 assert provider_fields(old)=={'reasoning_effort':'none'}
 assert 'response_format' not in payload_for(old,{'input':[{'role':'user','content':'old'}]})
 probe=ModelSettings(model=MODEL,temperature=0,max_output_tokens=384,provider_reasoning_control=NONE_PROBE)
 assert provider_fields(probe)=={'reasoning_effort':'none'}
 with pytest.raises(ValueError):replace(probe,max_output_tokens=2048)
 legacy=parse_nebius_completion(response(content='Legacy ordinary prose',reasoning=3),MODEL)
 assert legacy['text']=='Legacy ordinary prose' and 'complete_final_json' not in legacy and 'reasoning_suppression' not in legacy
 assert legacy['completion_accounting']['reported_non_reasoning_completion_tokens']==5
