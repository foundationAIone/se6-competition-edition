"""Focused prospective resource correction; explicit simulations never call a provider."""
import hashlib,json,time
from fractions import Fraction
from pathlib import Path
from hosted_judge.pair_gateway import PairGateway,native_metrics
from hosted_judge.service import JudgeService

ROOT=Path(__file__).resolve().parents[1]
QUESTION=('ROUTINE: 1 technician-hours, $11 materials cost, $62 customer revenue.\n'
 'DEEP: 3 technician-hours, $29 materials cost, $158 customer revenue.\n'
 'We completed 13 jobs. The original log recorded 23 technician-hours. The materials budget is $240.\n'
 'Calculate revenue, materials and gross contribution.\nDetermine whether materials exceed budget.')

def test_recursive_metrics_include_renewal_and_do_not_invent_total_cpu():
    public={'native_seconds':1,'native_receipt_count':3,'canonical':{'resources':{
        'whole_execute_native_wall_seconds':2,'whole_execute_native_cpu_seconds':1.5}},
        'realization_loop':{'resources':{'controller_wall_seconds':15,'native_actions':4,
            'controller_cpu_seconds':.5,'native_cpu_seconds_sum':4,
            'proof_worker_cpu_seconds_sum':5,'fresh_file_readback_child_cpu_seconds':None}}}
    got=native_metrics(public)
    assert got['native_wall_seconds']==got['native_seconds']==15
    assert got['native_operations']==4 and got['native_cpu_seconds'] is None
    assert got['local_monetary_cost_usd'] is None and got['provider_calls']==0
    assert public['realization_loop']['resources']['native_cpu_seconds_sum']==4

def test_legacy_primary_only_metrics_keep_their_original_scope():
    got=native_metrics({'native_seconds':1,'native_receipt_count':3,'canonical':{'resources':{
        'whole_execute_native_wall_seconds':2,'whole_execute_native_cpu_seconds':1.5}}})
    assert got['native_operations']==3 and got['native_cpu_seconds']==1.5
    assert got['native_seconds']==1 and got['native_wall_seconds']==2

def test_fresh_business_two_simulated_responses_with_actual_recursive_native_work(tmp_path):
    manifest=ROOT/'native-manifest.json';pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
    gateway=PairGateway(ROOT/'private-native',tmp_path/'pair',native_manifest=manifest,
        native_manifest_sha256=pin,simulated=True)
    service=JudgeService(ROOT/'private-native',manifest,pin,pair_gateway=gateway,
        asynchronous=True,realization_root=tmp_path/'recursive')
    token,session=service.new_session();request='3'*32
    value={'question':QUESTION,'request_id':request}
    ack=service.run(token,session['csrf_token'],value);assert ack['status']=='RUNNING'
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        with service.lock:result=service.sessions[token].requests[request][1]
        if result.get('status')!='RUNNING':break
        time.sleep(.03)
    else:raise AssertionError('Actual recursive simulated pair did not finish')
    assert result['provider_calls']==0
    loop=result['realization_loop'];assert loop['after_step']==2 and len(loop['cycles'])==2
    assert loop['resources']['artifact_actions']==2 and loop['resources']['native_actions']==4
    comparison=result['comparison']
    assert comparison['mode']=='SIMULATED_TEST' and comparison['simulated_calls']==2
    assert comparison['assisted_answer'] and comparison['baseline_answer']
    assert comparison['score']['answer_protocol']=='SE6_COMMON_PUBLIC_ANSWER_V1'
    assert comparison['score']['common_user_answer_winner'] is None and comparison['score']['overall_winner'] is None
    assert all(x['score']==x['maximum']==1 and x['schema_compliance'] is True and x['semantic_correctness'] is True and x['user_answer_status']=='PASS' for x in comparison['score']['lanes'].values())
    # Independent direct conservation arithmetic over the declared public facts.
    # One complete current answer is scored, not seven independent task wins.
    deep=(Fraction(23)-Fraction(13)*1)/(3-1);routine=Fraction(13)-deep
    revenue=routine*62+deep*158;materials=routine*11+deep*29
    expected={'revenue':revenue,'materials_cost':materials,'gross_contribution':revenue-materials,'budget_variance':materials-240}
    assert routine==8 and deep==5 and revenue==1286 and materials==233
    for text in (comparison['assisted_answer'],comparison['baseline_answer']):
        proposed=json.loads(text)
        assert set(proposed)=={'allocations',*expected,'budget_exceeded'}
        assert set(proposed['allocations'])=={'routine','deep'}
        assert {k:Fraction(v) for k,v in proposed['allocations'].items()}=={'routine':routine,'deep':deep}
        assert all(Fraction(proposed[k])==v for k,v in expected.items())
        assert proposed['budget_exceeded'] is False
    assert comparison['score']['arithmetic_winner'] is None
    directory=Path(service.sessions[token].attestation['matched_pair']['archive'])
    metrics=json.loads((directory/'native-metrics.json').read_bytes())
    assert metrics['native_operations']==4 and metrics['native_cpu_seconds'] is None
    assert metrics['native_wall_seconds']==loop['resources']['controller_wall_seconds']
    packet=json.loads((directory/'prepared.json').read_bytes())
    assert packet['messages']['se6'][:-1]==packet['messages']['baseline']
    assert not any('LOCAL SE6 CONTEXT' in x['content'] for x in packet['messages']['baseline'])
    assert service.run(token,session['csrf_token'],value)==result
