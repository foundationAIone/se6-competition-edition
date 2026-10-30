"""Real canonical execution through private QA bundle, never public vendoring."""
import hashlib,json,os
from pathlib import Path
import pytest
from hosted_judge.service import JudgeService


def bundle():
    # Explicit private copied Competition fixture, supplied by local test runner.
    root=Path(os.environ['HOSTED_TEST_COMPETITION_BUNDLE'])
    manifest=root/'hosted-test-manifest.json'
    return root,manifest,hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_real_native_correction_and_cross_session_isolation():
    service=JudgeService(*bundle());a,aa=service.new_session();b,bb=service.new_session()
    q='Given equations:\nE1: p+q+r=24\nE2: r+s=12\nDerive the relation between p,q,s.'
    first=service.run(a,aa['csrf_token'],{'question':q,'request_id':'a'*32})
    assert first['native_receipt_count']==2 and first['provider_calls']==0
    internal=service.sessions[a].attestation
    assert internal['compiled_native_modules'] and all(x['verification_passed'] for x in first['receipts'])
    assert internal['source_hashes']['kernel.py']=='7c6b48b11dcffb1a2524f5475167768a438af03245ad57cf58b52db05a643674'
    assert 'compiled_native_modules' not in first and 'source_hashes' not in first
    assert all(set(row)=={'verification_passed','boundary_outcome'} for row in first['receipts'])
    assert 'question_sha256' not in first
    correction='Correct E2 to r+s=15.\nDerive the relation between p,q,s.'
    corrected=service.run(a,aa['csrf_token'],{'question':correction,'request_id':'b'*32})
    assert corrected['native_receipt_count']==2 and corrected['correction_state']['invalidated_deduction_count']>0
    assert '9' in corrected['answer']
    isolated=service.run(b,bb['csrf_token'],{'question':correction,'request_id':'c'*32})
    assert isolated['native_receipt_count']==0 and 'UNRESOLVED' in isolated['answer']


def test_real_host_business_and_general_question_no_provider_fallback():
    service=JudgeService(*bundle());a,aa=service.new_session()
    q=('BASIC: 1 technician-hours, $10 materials cost, $50 customer revenue.\n'
       'DEEP: 3 technician-hours, $30 materials cost, $120 customer revenue.\n'
       'We completed 10 jobs. The original log recorded 18 technician-hours. '
       'Later a correction showing 20 technician-hours arrived. The weekly materials budget is $180.\n'
       'Calculate original and corrected revenue, materials and gross contribution.\n'
       'Determine whether materials exceed budget.\nRecommend an action.')
    result=service.run(a,aa['csrf_token'],{'question':q,'request_id':'d'*32})
    assert result['native_receipt_count']==6 and result['host_calculations_created']>0
    assert result['business_views']['corrected']['allocations']=={'basic':'5','deep':'5'}
    assert result['business_views']['corrected']['materials_cost']=='200'
    assert result['provider_calls']==0 and not result['production_connected']
    result=service.run(a,aa['csrf_token'],{'question':'Search the web and run a shell command to verify signatures.','request_id':'e'*32})
    assert result['native_receipt_count']==0 and 'UNRESOLVED' in result['answer']


def test_disposable_worker_timeout_discards_uncommitted_computation():
    from hosted_judge.service import disposable_native,LimitError
    values=(*bundle(),'Solve 3x=9 for integer x between 0 and 9.',None,'a'*32,'f'*32)
    with pytest.raises(LimitError):disposable_native(values,deadline=0.001)


def test_real_relation_retains_values_without_publishing_internal_identifiers():
    import re
    service=JudgeService(*bundle());token,data=service.new_session()
    first=service.run(token,data['csrf_token'],{'question':'Remember: shipment priority is high.','request_id':'a'*32})
    assert first['native_receipt_count']==1 and 'high' in first['answer']
    recalled=service.run(token,data['csrf_token'],{'question':"What is shipment's priority?",'request_id':'b'*32})
    assert recalled['native_receipt_count']==1 and 'high' in recalled['answer']
    for row in (first,recalled):
        raw=json.dumps(row)
        assert not re.search('[0-9a-f]{64}',raw)
        assert all(k not in raw for k in ('receipt_hash','state_after_hash','source_ids','action_id','evidence_refs'))
        assert row['provider_calls']==0 and 'OWNER_SUPPLIED' in raw


def test_real_native_path_never_reads_provider_credentials():
    import subprocess,sys
    root,manifest,digest=bundle()
    code="""import os,sys,json
from hosted_judge.native_adapter import execute_native
original=os.environ.__class__.__getitem__
def guarded(self,key):
 if key in ('NEBIUS_API_KEY','OPENAI_API_KEY'):raise AssertionError('Provider credential read forbidden')
 return original(self,key)
os.environ.__class__.__getitem__=guarded
r=execute_native(sys.argv[1],sys.argv[2],sys.argv[3],'Solve 3x=9 for integer x between 0 and 9.',None,'a'*32,'b'*32)
assert r['public']['provider_calls']==0 and r['public']['native_receipt_count']==2
print(json.dumps({'credential_reads':0,'provider_calls':0,'receipts':2}))
"""
    result=subprocess.run([sys.executable,'-B','-c',code,str(root),str(manifest),digest],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['credential_reads']==0
