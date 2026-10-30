"""Contestant-side full-session memory worker; no labels/evaluator mounted."""
from pathlib import Path
import argparse,importlib,json,os,sys,time
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP));sys.path.insert(0,'/deps');sys.dont_write_bytecode=True
from research_evaluation.measurement import Meter
from research_evaluation.isolation_worker import install_audit
from research_evaluation.os_probe import verify_kernel_boundary

def require(ok,code):
    if not ok:raise ValueError(code)

def timed_call(phases,name,function,*args,**kwargs):
    """Measure complete call boundaries equally; never relabel absent phases zero."""
    start=time.perf_counter();cpu=time.process_time()
    try:return function(*args,**kwargs)
    finally:
        phases[name]=dict(wall_seconds=time.perf_counter()-start,
            cpu_seconds=time.process_time()-cpu,scope='Complete inclusive call boundary')

def adapter_metrics(memory):
    value=getattr(memory,'phase_metrics',None)
    if value is None:return dict(status='NOT_SEPARATELY_INSTRUMENTED',unmeasured_not_zero=True)
    require(type(value) is dict,'S_WORKER_TIMING_CONTRACT')
    return value

def instrument_baseline(module):
    """Time unchanged official-kernel calls, not an alternate BM25 algorithm.

    These values are inclusive and can overlap; complete call boundaries remain
    the only additive totals. Missing source-packing attribution is UNKNOWN.
    """
    metrics={}
    for name,label in [('validate_history','source_validation_hashing'),
            ('history_sha256','source_validation_hashing'),('session_sha256','source_validation_hashing'),
            ('history_spans','source_validation_hashing'),('canonicalbytes','source_validation_hashing'),
            ('render_session','representation_index_build'),('rank','foundation_index_build_and_candidate_ranking')]:
        original=getattr(module,name)
        def wrapped(*args,_original=original,_label=label,**kwargs):
            start=time.perf_counter();cpu=time.process_time()
            try:return _original(*args,**kwargs)
            finally:
                item=metrics.setdefault(_label,dict(wall_seconds=0.0,cpu_seconds=0.0,calls=0,
                    scope='Inclusive unchanged function calls; nested totals may overlap'))
                item['wall_seconds']+=time.perf_counter()-start;item['cpu_seconds']+=time.process_time()-cpu;item['calls']+=1
        setattr(module,name,wrapped)
    return metrics

def execute(root,arm,payload,canary,*,development_repeat=False):
    require(arm in {'se6','bm25'} and type(payload) is dict,'S_WORKER_PUBLIC_CONTRACT')
    operation=payload.get('operation')
    require(operation in {'ingest','query'},'S_WORKER_OPERATION')
    require(set(payload)==({'operation','history'} if operation=='ingest' else {'operation','question','question_date','k'}),'S_WORKER_NO_EVALUATOR_FIELDS')
    if operation=='query':require(payload['k']==5,'S_WORKER_RETRIEVAL_ALLOWANCE')
    require(type(development_repeat) is bool and (not development_repeat or operation=='query'),'S_WORKER_DEVELOPMENT_REPEAT_ONLY_QUERY')
    worker_enter=time.monotonic();root=Path(root).resolve(strict=True);meter=Meter();operations={}
    kernel=timed_call(operations,'kernel_boundary_validation',verify_kernel_boundary,canary)
    meter.read();audit=timed_call(operations,'python_audit_installation',install_audit,root,canary)
    module=timed_call(operations,'adapter_import',importlib.import_module,
        'research_memory.sessions' if arm=='se6' else 'research_controls.official_bm25_s')
    baseline_metrics=instrument_baseline(module) if arm=='bm25' else None
    memory=timed_call(operations,'store_initialization',module.SessionMemory,root=root/'memory',storage_byte_budget=134217728)
    initialization={key:operations['adapter_import'][key]+operations['store_initialization'][key]
        for key in ['wall_seconds','cpu_seconds']}
    load=None;repeated=None
    if operation=='ingest':
        diagnostic=timed_call(operations,'complete_ingest',memory.ingest,payload['history'])
        if arm=='se6':
            from research_memory.session_selection import read_admitted_development_report
            report=timed_call(operations,'development_method_source_read',read_admitted_development_report)
            timed_call(operations,'development_method_admission',memory.admit_method_report,report)
        snapshot=timed_call(operations,'durable_snapshot',memory.save,root/'memory/snapshot');result=None
        phase={key:sum(operations[name][key] for name in ['complete_ingest','durable_snapshot','development_method_source_read','development_method_admission'] if name in operations)
            for key in ['wall_seconds','cpu_seconds']}
    else:
        diagnostic=timed_call(operations,'complete_cold_restore',memory.load,root/'memory/snapshot');load=operations['complete_cold_restore']
        result=timed_call(operations,'complete_retrieve_including_index',memory.retrieve,
            payload['question'],payload['question_date'],k=payload['k']);snapshot=None
        phase=operations['complete_retrieve_including_index']
        if development_repeat:
            repeated=timed_call(operations,'development_repeated_retrieve_including_index',memory.retrieve,
                payload['question'],payload['question_date'],k=payload['k'])
    storage=timed_call(operations,'final_storage_accounting',lambda:sum(p.stat().st_size for p in root.rglob('*') if p.is_file()))
    resources=meter.read();resources['storage_bytes']=storage
    require(resources['storage_bytes']<=134217728,'S_WORKER_STORAGE_ALLOWANCE')
    return dict(status='COMPLETE',record_kind='ACTUAL_LOCAL_CLEANED_S_MEMORY_PROCESS',operation=operation,pid=os.getpid(),arm=arm,
        os_sandbox=kernel,audit=audit,initialization=initialization,phase=phase,cold_restore=load,diagnostic=diagnostic,
        snapshot=snapshot,result=result,development_repeated_result=repeated,resources=resources,provider_calls=0,World_effects=0,
        timing=dict(schema='se6-matched-complete-phase-timing-v1',operations=operations,
            adapter_subphases=adapter_metrics(memory) if baseline_metrics is None else baseline_metrics,
            setup_policy='Both arms pay import, construction, complete ingest, durable snapshot, cold restore and complete retrieval; BM25 index construction is included wherever it actually executes.',
            repeated_query_policy='Primary pass is one query in a distinct cold process; repeated-query diagnostics must be a separate exposed-development run.',
            namespace_setup_wall_seconds=float(os.environ['SE6_NAMESPACE_SETUP_SECONDS']) if 'SE6_NAMESPACE_SETUP_SECONDS' in os.environ else None,
            namespace_exec_to_worker_enter_wall_seconds=worker_enter-float(os.environ['SE6_NAMESPACE_EXEC_MONOTONIC']) if 'SE6_NAMESPACE_EXEC_MONOTONIC' in os.environ else None,
            unknown='Parent/WSL scheduling, transport, whole-system CPU and energy remain outside own-process phase attribution. Inclusive subphase values must not be double-summed.'))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--arm',required=True);parser.add_argument('--canary',required=True)
    parser.add_argument('--development-repeat',action='store_true')
    args=parser.parse_args()
    try:value=execute(args.root,args.arm,json.loads(sys.stdin.read()),args.canary,development_repeat=args.development_repeat)
    except Exception as error:
        code=str(error)
        value=dict(status='FAILED_CLOSED',error_type=type(error).__name__,reason=code if code.isupper() and len(code)<180 else 'S_WORKER_EXCEPTION',provider_calls=0,retry_permitted=False)
    print(json.dumps(value,ensure_ascii=True,sort_keys=True,allow_nan=False))
