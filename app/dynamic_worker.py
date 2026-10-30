"""One disposable, no-provider executor using existing operations and TaskStore."""
import argparse,datetime,hashlib,json,os,secrets,sys,time,tracemalloc
from pathlib import Path
from copy import deepcopy
sys.dont_write_bytecode=True
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--manifest',required=True);p.add_argument('--pin',required=True)
    p.add_argument('--spec',required=True);p.add_argument('--scenario',required=True);p.add_argument('--event',type=int,required=True)
    p.add_argument('--condition',choices=['SE6','DROP_RETAINED_STATE'],required=True);p.add_argument('--store',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();started=time.perf_counter();started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat();cpu=time.process_time();tracemalloc.start()
    spec=json.loads(Path(args.spec).read_bytes());scenario=spec['scenario'];event=spec['event']
    if scenario['id']!=args.scenario or args.event<0 or spec['event_index']!=args.event:raise ValueError('Scenario/event differs from isolated event')
    if Path(args.output).exists():raise ValueError('Frozen captures cannot be overwritten')
    task_id=spec['task_namespace'];process_nonce=secrets.token_hex(16)
    source_root=Path(__file__).resolve().parent;store_root=Path(args.store).resolve();bundle_root=Path(args.bundle).resolve()
    exact={Path(args.spec).resolve(),Path(args.output).resolve(),Path(args.spec).parent.resolve()/'technical-artifact.json'}
    permitted_roots=(bundle_root,store_root,Path(sys.base_prefix).resolve(),*[Path(p).resolve() for p in sys.path if 'site-packages' in p])
    def audit(event_name,values):
        if event_name!='open' or not isinstance(values[0],(str,bytes,os.PathLike)):return
        path=Path(os.fsdecode(values[0])).resolve()
        if path in exact or any(path.is_relative_to(r) for r in permitted_roots):return
        if path.is_relative_to(source_root) and path.suffix=='.py':return
        raise PermissionError('Offline worker file access is outside its public event, source and own state allowance')
    sys.addaudithook(audit)
    from hosted_judge.native_adapter import execute_native,encode,validate_bundle
    validate_bundle(args.bundle,args.manifest,args.pin)
    sys.path.insert(0,args.bundle)
    from src.workbench.runtime_revision import freeze_sources
    revision=freeze_sources(args.bundle)
    import socket
    def denied(*args,**kwargs):raise ValueError('Offline benchmark has no outbound network authority')
    socket.socket.connect=denied;socket.create_connection=denied;socket.getaddrinfo=denied
    socket.socket.connect_ex=denied;socket.socket.sendto=denied
    from src.workbench.storage import TaskStore
    store=TaskStore(args.store)
    try:prior=store.load(task_id);version=prior['version'];cp=prior['checkpoint']
    except KeyError:prior=None;version=-1;cp=None
    if version!=args.event-1:raise ValueError('Event repetition, gap or reordered state update refused')
    # No shared controller store; a fresh OS process reobserves this evidence.
    round_id=hashlib.sha256((task_id+str(args.event)).encode()).hexdigest()[:32]
    before=deepcopy(cp);gate=event['source']!='MODEL_PROPOSED'
    host_artifact=None
    if event['source']=='HOST_VERIFIED_ARTIFACT':
        artifact=Path(args.spec).parent/'technical-artifact.json'
        host_artifact={'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'verified':True,'scope':'Exact local fixture bytes; not invoice signatures or production readiness'}
        if host_artifact['sha256']!=spec['technical_artifact_sha256']:raise ValueError('Technical artifact differs')
    if gate:
        result=execute_native(args.bundle,args.manifest,args.pin,event['question'],cp if args.condition=='SE6' else None,task_id,round_id,revision=revision)
    else:result={'checkpoint':cp,'operations':0,'attestation':{},'public':{'answer':'UNRESOLVED — MODEL_PROPOSED evidence not admitted as trusted knowledge.','native_receipt_count':0,'host_calculations_created':0,'provider_calls':0,'production_connected':False,'nodes':[],'business_views':None,'correction_state':None}}
    from src.workbench.core_revisions import load_core,verify_traces,SOURCE_HASHES
    api=load_core();knowledge={'constraints':[],'active':[],'invalidated':[],'relations':[],'math_head':None,'relation_head':None}
    after=result['checkpoint'];auto=(after or {}).get('auto_checkpoint') or {}
    if auto.get('math'):
        retained=auto['math'];engine=api.SE.restore(retained['journal'],expected_head=retained['head']);verify_traces(api,engine,retained['traces'])
        knowledge.update(constraints=[{'label':c.label,'reference':c.reference,'coefficients':list(c.equation.coefficients),'rhs':c.equation.rhs} for c in engine.state.current_constraints],
            active=[{'reference':d.reference,'coefficients':list(d.equation.coefficients),'rhs':d.equation.rhs} for d in engine.state.active_deductions],
            invalidated=[d.reference for d in engine.state.invalidated_deductions],math_head=retained['head'])
    if auto.get('relations'):
        retained=auto['relations'];engine=api.SE.restore(retained['journal'],expected_head=auto['relation_head']);verify_traces(api,engine,retained['traces'])
        knowledge.update(relations=[{'subject':r.subject,'predicate':r.predicate,'value':r.value,'status':r.epistemic_status} for r in engine.state.relations],relation_head=auto['relation_head'])
    operations=(prior or {}).get('operations',0)+result['operations']
    if operations>20:raise ValueError('Equal scenario action cap exceeded')
    self_model={'schema':'dynamic-operational-self-model-v1','actual_pid':os.getpid(),'process_start_nonce':process_nonce,'launch_nonce':spec['launch_nonce'],'python':sys.version.split()[0],
        'worker_kind':'disposable native backend process; not a new Codex agent','canonical_source_pins':SOURCE_HASHES,
        'persistent_checkpoint_loaded':before is not None,'persistent_checkpoint_applied':gate and before is not None and args.condition=='SE6','remaining_native_operations':20-operations,
        'provider_calls_authorized':False,'outbound_network_authorized':False,'production_connected':False,
        'supported':['bounded_linear','task_local_relations','host_business_arithmetic','local_artifact_checksum'],
        'unavailable':['web','shell','external_signature_authentication','model_weight_update','universal_domain_transfer'],
        'uncertainty':['supplied world facts unverified','backend restart verified separately from Codex specialist collaboration; no cognitive continuity claim']}
    if prior and prior['self_model']['provider_calls_authorized']:raise ValueError('Stale authority cannot be inherited')
    committed=store.commit({'id':task_id,'checkpoint':after,'operations':operations,'self_model':self_model,'event_index':args.event},version)
    if store.load(task_id)!=committed:raise ValueError('Persistent store roundtrip mismatch')
    output={'scenario':args.scenario,'domain':scenario['domain'],'condition':args.condition,'event':args.event,'phase':event['phase'],
        'question':event['question'],'source':event['source'],'public':result['public'],'knowledge':knowledge,
        'captured_at_utc':started_utc,'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'attestation':result.get('attestation',{}),'self_model':self_model,'host_artifact':host_artifact,
        'persistence':{'version':committed['version'],'before_checkpoint_sha256':digest(before),'after_checkpoint_sha256':digest(after),
            'checkpoint_bytes':len(encode(after)),'store_roundtrip_verified':True,'prior_worker_pid':(prior or {}).get('self_model',{}).get('actual_pid'),
            'prior_process_start_nonce':(prior or {}).get('self_model',{}).get('process_start_nonce')},
        'measurements':{'native_operations':result['operations'],'cumulative_native_operations':operations,
            'native_transition_attempts':result['operations'],
            'executed_native_actions':sum(max(0,r['state_after']['actions_used']-r['state_before']['actions_used']) for r in result.get('attestation',{}).get('native_receipts',[])),
            'worker_wall_seconds':time.perf_counter()-started,'worker_cpu_seconds':time.process_time()-cpu,
            'python_tracemalloc_peak_bytes':tracemalloc.get_traced_memory()[1],'provider_calls':0,'input_tokens':0,'output_tokens':0,
            'provider_cost_usd':0,'local_compute_monetary_cost_usd':None,'memory_scope':'Python heap only, not total RSS or native allocations'}}
    with Path(args.output).open('x',encoding='utf-8') as stream:json.dump(output,stream,indent=2)
    print(json.dumps({'scenario':args.scenario,'event':args.event,'native_operations':result['operations'],'provider_calls':0}))
if __name__=='__main__':main()
