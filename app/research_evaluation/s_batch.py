"""Trusted, no-provider, once-only selected LongMemEval-S paired batch.

Raw/gold data and grading remain here; only scrubbed history/question/date cross
the sealed worker boundary. This module is never mounted in a contestant.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,time,uuid
from .s_public import assert_no_private,score_case,aggregate,sha,require

APP=Path(__file__).resolve().parents[1];LANE=APP.parent
def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def linux(path):
    p=str(Path(path).resolve());return '/mnt/'+p[0].lower()+p[2:].replace('\\','/') if len(p)>2 and p[1]==':' else p
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as file:json.dump(value,file,indent=2,ensure_ascii=True);file.write('\n')
def verify_source(manifest):
    path=Path(manifest['source_manifest_path']).resolve(strict=True)
    require(path==APP/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json' and file_sha(path)==manifest['source_manifest_sha256'],'S_BATCH_SOURCE_MANIFEST_BINDING')
    source=json.loads(path.read_bytes())['files']
    for name,pin in source.items():
        file=APP/name
        require(not file.is_symlink() and file.resolve().is_relative_to(APP) and file.is_file() and file_sha(file)==pin,'S_BATCH_SOURCE_MEMBER_CHANGED')
    require(all(name in source for name in ['research_memory/sessions.py','research_controls/official_bm25_s.py',
        'research_evaluation/s_public.py','research_evaluation/s_namespace.py','research_evaluation/s_worker.py','research_evaluation/s_batch.py']),
        'S_BATCH_REQUIRED_EXECUTING_SOURCE_NOT_PINNED')
    return file_sha(path)

def run_child(work,canary,arm,payload,output,*,development_repeat=False):
    command=['wsl.exe','-d','Ubuntu','--exec','/usr/bin/timeout','--signal=TERM','--kill-after=5s','120s',
        '/usr/bin/unshare','--user','--map-root-user','--mount','--net','--fork','/usr/bin/python3.12',
        linux(APP/'research_evaluation/s_namespace.py'),'--source',linux(APP),'--deps',linux(LANE/'linux-deps'),
        '--workroot',linux(work),'--arm',arm,'--canary',linux(canary)]
    if development_repeat:command.append('--development-repeat')
    start=time.perf_counter();cpu=time.process_time()
    try:
        completed=subprocess.run(command,input=json.dumps(payload,ensure_ascii=True),capture_output=True,
            text=True,encoding='utf-8',timeout=135)
        stdout,stderr=completed.stdout,completed.stderr;returncode=completed.returncode;timeout=False
    except subprocess.TimeoutExpired as error:
        stdout=error.stdout or '';stderr=error.stderr or ''
        if isinstance(stdout,bytes):stdout=stdout.decode('utf-8',errors='replace')
        if isinstance(stderr,bytes):stderr=stderr.decode('utf-8',errors='replace')
        returncode=None;timeout=True
    (output.with_suffix('.stdout')).write_text(stdout,encoding='utf-8');(output.with_suffix('.stderr')).write_text(stderr,encoding='utf-8')
    transport=dict(returncode=returncode,timeout=timeout,parent_wall_seconds=time.perf_counter()-start,
        parent_cpu_seconds=time.process_time()-cpu,retry_permitted=False,
        public_input_sha256=sha(payload),stdout_sha256=hashlib.sha256(stdout.encode()).hexdigest(),
        stderr_sha256=hashlib.sha256(stderr.encode()).hexdigest())
    write(output.with_suffix('.transport.json'),transport)
    if timeout:return None,transport,'CHILD_TIMEOUT_NO_RETRY'
    if returncode!=0:return None,transport,'CHILD_EXIT_'+str(returncode)
    try:value=json.loads(stdout)
    except json.JSONDecodeError:return None,transport,'CHILD_RESPONSE_NOT_JSON'
    write(output.with_suffix('.json'),value)
    if value.get('status')!='COMPLETE':return value,transport,value.get('reason','CHILD_FAILED_CLOSED')
    if value.get('os_sandbox',{}).get('kernel_boundary')!='VERIFIED':return value,transport,'KERNEL_BOUNDARY_NOT_VERIFIED'
    return value,transport,None

def run_arm(public,arm,case_root,canary,*,development_repeat=False):
    work=case_root/('SE6-MEMORY-'+arm+'-'+uuid.uuid4().hex);work.mkdir()
    (work/'.SE6_MEMORY_DISPOSABLE').write_text('CUSTOM_DEVELOPMENT_MEMORY_ONLY')
    phases=[];result=None;failure=None
    for operation in ['ingest','query']:
        payload=dict(operation='ingest',history=public['history']) if operation=='ingest' else dict(
            operation='query',question=public['question'],question_date=public['question_date'],k=5)
        value,transport,failure=run_child(work,canary,arm,payload,case_root/(arm+'-'+operation),development_repeat=development_repeat and operation=='query')
        phases.append(dict(operation=operation,transport=transport,worker=value))
        if failure:break
        if operation=='query':result=value['result']
    if failure is None:
        require(phases[0]['worker']['pid']!=phases[1]['worker']['pid'],'S_BATCH_COLD_PROCESS_NOT_DISTINCT')
    return dict(status='SUCCESSFULLY_PROCESSED' if failure is None else 'FAILED',failure=failure,
        result=result,phases=phases,provider_calls=0,World_effects=0)

def summarize_timing(rows):
    """Comparable outer totals and nonoverlapping complete worker call phases."""
    arms={}
    for arm in ['se6','bm25']:
        operations={};outer=0.0;worker_cpu=0.0;worker_count=0;missing=0;rss=[]
        for row in rows:
            for phase in row['arms'][arm].get('phases',[]):
                outer+=phase['transport']['parent_wall_seconds']
                worker=phase.get('worker')
                if not worker or worker.get('status')!='COMPLETE':missing+=1;continue
                worker_count+=1
                resources=worker.get('resources',{});cpu=resources.get('host_cpu_seconds')
                if type(cpu) in {int,float}:worker_cpu+=cpu
                peak=resources.get('peak_process_rss_bytes')
                if type(peak) is int:rss.append(peak)
                for name,item in worker.get('timing',{}).get('operations',{}).items():
                    target=operations.setdefault(name,dict(wall_seconds=0.0,cpu_seconds=0.0,measurements=0))
                    target['wall_seconds']+=item['wall_seconds'];target['cpu_seconds']+=item['cpu_seconds'];target['measurements']+=1
        setup_names=['adapter_import','store_initialization','complete_ingest','development_method_source_read',
            'development_method_admission','durable_snapshot']
        arms[arm]=dict(enclosing_all_child_wall_seconds=outer,complete_worker_processes=worker_count,
            missing_or_failed_worker_timings=missing,complete_operations=operations,
            setup_wall_seconds=sum(operations.get(name,{}).get('wall_seconds',0.0) for name in setup_names),
            cold_restore_wall_seconds=operations.get('complete_cold_restore',{}).get('wall_seconds'),
            retrieve_with_actual_index_build_wall_seconds=operations.get('complete_retrieve_including_index',{}).get('wall_seconds'),
            metered_worker_cpu_seconds=worker_cpu,peak_worker_rss_bytes=max(rss) if rss else None,
            attribution='Only complete outer operation boundaries are additive. Source/index/ranking subphases are separately preserved per worker, inclusive and never double-summed.',
            repeated_query_seconds=operations.get('development_repeated_retrieve_including_index',{}).get('wall_seconds'),
            repeated_query_scope='One exposed-development repeat only when explicitly selected; primary frozen held-out pass remains one cold query. Baseline index reconstruction on every call remains included; no general warm-speed superiority claim.')
    return dict(schema='se6-matched-phase-summary-v1',arms=arms,
        comparison='Both arms charged complete ingest, durable writes, constructor/import, cold restore, and retrieval INCLUDING whichever index build occurs there; additional SE6 policy admission is charged to SE6.',
        unknown=['Whole-system/WSL CPU','Engineering/Codex usage','Energy','Unmeasured failed or timed-out child phases'],
        no_query_speed_claim_from_mismatched_timers=True)

def verify_development_source(manifest):
    files=manifest.get('development_executing_source_files')
    require(type(files) is dict and files and sha(files)==manifest.get('development_executing_source_sha256'),'DEVELOPMENT_EXECUTING_SOURCE_BINDING')
    path=Path(manifest.get('development_source_manifest_path','')).resolve(strict=True)
    require(path.is_file() and not path.is_relative_to(APP) and file_sha(path)==manifest.get('development_source_manifest_sha256'),'DEVELOPMENT_IMMUTABLE_SOURCE_MANIFEST')
    frozen=json.loads(path.read_bytes())
    require(frozen.get('files')==files and frozen.get('source_sha256')==sha(files),'DEVELOPMENT_IMMUTABLE_SOURCE_CONTENT')
    for name,pin in files.items():
        path=APP/name
        require(path.resolve().is_relative_to(APP) and not path.is_symlink() and path.is_file() and file_sha(path)==pin,'DEVELOPMENT_EXECUTING_SOURCE_CHANGED')
    return sha(files)

def run_batch(manifest_path,out,partition,*,development_unfrozen=False,development_repeat_case=None):
    start=time.perf_counter();cpu=time.process_time()
    manifest_path=Path(manifest_path).resolve(strict=True);manifest=json.loads(manifest_path.read_bytes())
    require(partition in {'development','evaluation'},'S_BATCH_PARTITION')
    require(not development_unfrozen or partition=='development','UNFROZEN_HELDOUT_FORBIDDEN')
    require(development_repeat_case is None or (development_unfrozen and partition=='development'),'HELDOUT_REPEAT_FORBIDDEN')
    entries=[e for e in manifest['cases'] if e['partition']==partition]
    require(entries and len({e['case_id'] for e in entries})==len(entries),'S_BATCH_CASE_MANIFEST')
    if not development_unfrozen:verify_source(manifest)
    else:verify_development_source(manifest)
    require(development_repeat_case is None or development_repeat_case in {e['case_id'] for e in entries},'DEVELOPMENT_REPEAT_CASE_NOT_SELECTED')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    write(out/'EXCLUSIVE_BATCH_CLAIM.json',dict(partition=partition,manifest_sha256=file_sha(manifest_path),
        selected_cases=[e['case_id'] for e in entries],started_at_utc=datetime.now(timezone.utc).isoformat(),
        purpose='LOCAL_RETRIEVAL_ONLY_NO_PROVIDER',retry_permitted=False,development_repeat_case=development_repeat_case))
    private=out/'trusted_evaluator';private.mkdir();canary=private/'canary.txt'
    canary.write_text('PRIVATE_S_EVALUATOR_CANARY_'+uuid.uuid4().hex)
    rows=[]
    for entry in entries:
        if not development_unfrozen:verify_source(manifest)
        else:verify_development_source(manifest)
        case_root=out/entry['case_id'];case_root.mkdir()
        require(file_sha(entry['public_path'])==entry['public_sha256'] and file_sha(entry['private_path'])==entry['private_sha256'],'S_BATCH_DATA_MEMBER_CHANGED')
        public=json.loads(Path(entry['public_path']).read_bytes());annotations=json.loads(Path(entry['private_path']).read_bytes())
        assert_no_private(public);require(sha(public)==annotations['public_payload_sha256'],'S_BATCH_PUBLIC_ANNOTATION_BINDING')
        row=dict(case_id=entry['case_id'],partition=partition,question_id=annotations['question_id'],
            question_type=annotations['question_type'],public_payload_sha256=sha(public),arms={})
        # Counterbalance order prospectively by case-token hash; no score input.
        arms=['se6','bm25'] if int(hashlib.sha256(entry['case_id'].encode()).hexdigest(),16)%2 else ['bm25','se6']
        row['arm_order']=arms
        for arm in arms:
            outcome=run_arm(public,arm,case_root,canary,development_repeat=entry['case_id']==development_repeat_case)
            outcome['score']=score_case(public,annotations['required_session_ids'],outcome['result'],failure=outcome['failure'])
            row['arms'][arm]=outcome
        write(case_root/'RESULT.json',row);rows.append(row)
        with (out/'PER_CASE_RESULTS.jsonl').open('a',encoding='utf-8') as file:file.write(json.dumps(row,ensure_ascii=True)+'\n')
        print(json.dumps(dict(case_id=entry['case_id'],status='RECORDED',provider_calls=0)),flush=True)
    report=dict(status='DEVELOPMENT_CALIBRATION_COMPLETE_UNFROZEN' if development_unfrozen else 'COMPLETED_FROZEN_SELECTED_RETRIEVAL_PASS',partition=partition,cases_selected=len(entries),cases_attempted=len(rows),
        results=aggregate(rows),source_manifest_sha256=None if development_unfrozen else manifest.get('source_manifest_sha256'),selection_manifest_sha256=file_sha(manifest_path),
        provider_calls=0,answering_model='NONE',World_effects=0,production_connected=False,alpha_changed=False,
        outer_wall_seconds=time.perf_counter()-start,outer_parent_cpu_seconds=time.process_time()-cpu,
        preprocessing=manifest.get('preprocessing_measurements','UNKNOWN_NOT_ZERO'),
        resource_scope='Outer wall includes namespace/startup/import/ingest/cold/query/grading. Parent CPU excludes child CPU; each worker records its own CPU/RSS. Total engineering/Codex/WSL setup CPU UNKNOWN.',
        label=manifest.get('label','Custom LongMemEval-S retrieval subset — SE6 versus BM25 — no answering model.'),
        comparison_contract=manifest.get('comparison_contract','Historical pilot comparison; see frozen protocol.'),
        retrieval_foundation=manifest.get('retrieval_foundation','See frozen method descriptions.'),
        claims='Descriptive selected-case component pilot only; not final-answer accuracy, official full score or broad superiority.')
    report['matched_timing']=summarize_timing(rows)
    report['development_executing_source_sha256']=manifest.get('development_executing_source_sha256') if development_unfrozen else None
    report['development_source_manifest_path']=manifest.get('development_source_manifest_path') if development_unfrozen else None
    report['development_source_manifest_sha256']=manifest.get('development_source_manifest_sha256') if development_unfrozen else None
    report['development_repeat_case']=development_repeat_case
    write(out/'RESULT.json',report)
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--partition',choices=['development','evaluation'],required=True);parser.add_argument('--development-unfrozen',action='store_true')
    parser.add_argument('--development-repeat-case')
    args=parser.parse_args();print(json.dumps(run_batch(args.manifest,args.out,args.partition,development_unfrozen=args.development_unfrozen,development_repeat_case=args.development_repeat_case),ensure_ascii=True))
