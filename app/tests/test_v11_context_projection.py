"""Prompt projection is separate from actual native execution and public grading."""
import json
import hashlib
from datetime import datetime,timezone,timedelta
import pytest
from pathlib import Path
from hosted_judge.pair_gateway import PairGateway
from hosted_judge.v8_run_both import prepare,RunBothCoordinator,Blocked,TARIFF,MAX_OUTPUT,encoded

QUESTION=('ROUTINE: 1 technician-hours, $11 materials cost, $62 customer revenue.\n'
 'DEEP: 3 technician-hours, $29 materials cost, $158 customer revenue.\n'
 'We completed 13 jobs. The original log recorded 23 technician-hours. The materials budget is $240.\n'
 'Calculate revenue, materials and gross contribution.\nDetermine whether materials exceed budget.')

def test_public_shape_instructions_have_keys_and_types_without_solutions():
    packet=prepare(QUESTION,'actual task-specific native data',[],{'se6':[],'baseline':[]})
    public=packet['messages']['baseline'][0]['content']
    assert '"business"' in public and '"routine":"RATIONAL"' in public and '"deep":"RATIONAL"' in public
    assert '"budget_exceeded":"BOOLEAN"' in public
    for solution in ('1286','1053','233','"routine":"8"','"deep":"5"'):
        assert solution not in public
    assert packet['messages']['se6'][:-1]==packet['messages']['baseline']
    assert 'actual task-specific native data' not in json.dumps(packet['messages']['baseline'])

def test_business_context_keeps_verified_values_and_excludes_runtime_metadata(tmp_path):
    gateway=PairGateway(tmp_path/'bundle',tmp_path/'store',native_manifest=tmp_path/'manifest',native_manifest_sha256='a'*64)
    views={'original':{'allocations':{'routine':'8','deep':'5'},'revenue':'1286','materials_cost':'233',
      'gross_contribution':'1053','budget_variance':'-7','budget_exceeded':False}}
    raw={'business_views':views,'canonical':{'independent_checkpoint_replay':True,'contract':'PRIVATE_CONTRACT_METADATA'},
      'local_verification':{'host_arithmetic':{'passed':True,'current':True}},
      'realization_loop':{'state':'PRIVATE_RUNTIME_STATE'},'receipts':['FULL_NATIVE_JOURNAL']}
    context=gateway.context(raw,'Very verbose duplicate answer; baseline not run; private runtime metadata')
    projected=json.loads(context)
    assert projected['verified_conditional_results']['business']==views
    assert projected['world_facts_verified'] is False
    assert 'PRIVATE_' not in context and 'FULL_NATIVE_JOURNAL' not in context and 'baseline not run' not in context
    assert raw['realization_loop']['state']=='PRIVATE_RUNTIME_STATE' and raw['receipts']==['FULL_NATIVE_JOURNAL']
    # Compression must not erase provenance from the caller's retained record.
    assert raw['canonical']['contract']=='PRIVATE_CONTRACT_METADATA'

def test_unverified_business_is_never_promoted_by_projection(tmp_path):
    gateway=PairGateway(tmp_path/'bundle',tmp_path/'store',native_manifest=tmp_path/'manifest',native_manifest_sha256='a'*64)
    raw={'business_views':{'original':{'revenue':'UNVERIFIED'}},'canonical':{'independent_checkpoint_replay':False}}
    context=json.loads(gateway.context(raw,'Native work unresolved'))
    assert context['verified_conditional_results']=={'answer':'Native work unresolved'}
    assert context['world_facts_verified'] is False

@pytest.mark.parametrize('claimed',['spent-permits','spent-questions'])
def test_known_spent_claim_refuses_before_credential_lookup(tmp_path,claimed):
    now=datetime.fromisoformat(TARIFF['verified_date']).replace(tzinfo=timezone.utc)
    packet=prepare(QUESTION,'native',[],{'se6':[],'baseline':[]})
    probe=[];path=tmp_path/'SIMULATED_UNIT_PERMIT_NOT_OWNER_AUTHORITY.json'
    c=RunBothCoordinator(tmp_path,approval_path=path,live_enabled=True,
        credential_probe=lambda model:probe.append(model),clock=lambda:now)
    permit={'schema':'se6-v8-one-pair-allowance-v1','permit_id':'2'*32,'campaign_id':'simulated-unit-permit-test',
      'approved':True,'purpose':'ONE_MATCHED_NEMOTRON_PAIR','expires_at_utc':(now+timedelta(hours=1)).isoformat(),
      'allowed_question_hashes':[packet['question_sha256']],'packet_sha256':packet['packet_sha256'],
      'model_settings':packet['model'],'source_contract':packet['source_contract'],'claim_store_sha256':c.store_identity(),
      'max_pairs':1,'max_calls':2,'max_output_tokens':MAX_OUTPUT,'max_input_bytes':49152,'usd_cap':'0.20','tariff':TARIFF}
    path.write_bytes(encoded(permit));c.approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    stem=permit['permit_id'] if claimed=='spent-permits' else packet['question_sha256']
    claim=c.path(claimed,stem+'.json');claim.parent.mkdir(parents=True);claim.write_bytes(encoded({'reserved':2}))
    with pytest.raises(Blocked):c.run('a'*32,'b'*32,QUESTION,'native',{},[])
    assert probe==[] and not list(c.root.rglob('attempt-*.json'))
