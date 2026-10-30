"""One bounded offline development bridge proof; no model or benchmark run.

Two fresh processes operate each disposable Entity. Raw public goals/programs
are supplied, never a proposed patch. The memory-disabled condition keeps the
same Native/Boundary/tools and verified retention, disabling only the new
Entity-capability-to-configuration bridge. No comparison superiority follows.
"""
from pathlib import Path
from datetime import datetime,UTC
import argparse,json,os,subprocess,sys,time

APP=Path(__file__).resolve().parents[1]
CORE=APP/'awareness_native/work/qpre-calibration-integration-20261026/dev'
sys.path.insert(0,str(APP));sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
from hosted_judge.model_native_workflow import initialize_native_instance
from scripts import run_dependency_awareness as original
from scripts.run_native_qpre_learning import read,write_once,check_root
from se666_core.observation_grounding import digest,require


def child(root,phase,enabled):
    root=check_root(root)
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--child','--root',str(root),
        '--phase',str(phase),'--memory',str(int(enabled))]
    start=time.perf_counter()
    logs=root/'agent-proof-transport';logs.mkdir(exist_ok=True)
    try:
        result=subprocess.run(command,cwd=APP,capture_output=True,text=True,timeout=120,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    except subprocess.TimeoutExpired as error:
        raw=lambda v:v if isinstance(v,bytes) else (v or '').encode()
        stdout,stderr=raw(error.stdout),raw(error.stderr)
        write_once(logs/f'phase-{phase}.json',dict(status='INTERRUPTED_OUTCOME_UNKNOWN',
            wall_seconds=time.perf_counter()-start,stdout_sha256=original.hashlib.sha256(stdout).hexdigest(),
            stderr_sha256=original.hashlib.sha256(stderr).hexdigest(),retry_permitted=False))
        with (logs/f'phase-{phase}.stdout').open('xb') as f:f.write(stdout)
        with (logs/f'phase-{phase}.stderr').open('xb') as f:f.write(stderr)
        raise ValueError('AGENT_DEVELOPMENT_CHILD_TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY') from None
    # Any failure/timeout is terminal. Never retry an uncertain operation.
    write_once(logs/f'phase-{phase}.json',dict(returncode=result.returncode,
        wall_seconds=time.perf_counter()-start,stdout_sha256=original.hashlib.sha256(result.stdout.encode()).hexdigest(),
        stderr_sha256=original.hashlib.sha256(result.stderr.encode()).hexdigest(),retry_permitted=False))
    with (logs/f'phase-{phase}.stdout').open('x',encoding='utf-8') as f:f.write(result.stdout)
    with (logs/f'phase-{phase}.stderr').open('x',encoding='utf-8') as f:f.write(result.stderr)
    require(result.returncode==0,'AGENT_DEVELOPMENT_CHILD_FAILED_NO_RETRY')
    return json.loads(result.stdout)


def run(out):
    out=Path(out).resolve();require(not out.exists() and not out.is_relative_to(APP),'NEW_EXTERNAL_DEVELOPMENT_OUTPUT_REQUIRED')
    out.mkdir(parents=True);runs={};roots={}
    for label,enabled in [('retained-bridge',True),('bridge-disabled',False)]:
        root=initialize_native_instance();roots[label]=str(root)
        write_once(out/f'{label}-root.json',dict(root=str(root),scope='DISPOSABLE_DEVELOPMENT_ONLY',provider_calls=0))
        world=root/'projectA';world.mkdir()
        (world/'workload.py').write_text(original.WORKLOAD,encoding='utf-8')
        write_once(world/'manifest.json',dict(entry='active',profiles={
            'active':dict(config='active-settings.json',gain=3,offset=2),
            'other':dict(config='other-settings.json',gain=5,offset=1)}))
        write_once(world/'active-settings.json',dict(limit=0));write_once(world/'other-settings.json',dict(limit=0))
        schema=dict(version=original.domain.VERSION,goal=20,setting_bounds=[0,100],operation='gain*limit+offset')
        write_once(world/'goal.json',schema)
        first=child(root,1,enabled)
        require(first['goal'] and first['actual_effects']==1,'AGENT_FIRST_CONSEQUENCE_NOT_VERIFIED')
        # An independent task change, not a supplied repair: retain the same
        # SELF root and structural relation but request a different public goal.
        schema['goal']=26
        temporary=world/'goal.next';write_once(temporary,schema);os.replace(temporary,world/'goal.json')
        second=child(root,2,enabled)
        require(second['pid']!=first['pid'] and second['goal'] and second['actual_effects']==1,'AGENT_COLD_CONSEQUENCE_NOT_VERIFIED')
        require(second['agent_implementation']=='DependencyRepairAgent','EXECUTABLE_AGENT_NOT_CONSTRUCTED')
        if enabled:
            require(second['verified_capability_memory_consumed']
                and second['agent_configuration']['verified_memory_id']
                and len(second['agent_configuration']['configured_candidates'])==1
                and bool(second['maintained_edges_consumed']),'VERIFIED_MEMORY_DID_NOT_AFFECT_AGENT_OPERATION')
        else:
            require(not second['verified_capability_memory_consumed']
                and len(second['agent_configuration']['configured_candidates'])==2
                and not second['maintained_edges_consumed'],'ABLATION_NOT_EXACT')
        runs[label]=[first,second]
        write_once(out/f'{label}.json',runs[label])
    report=dict(version='se6-agent-realization-development-proof-v1',at_utc=datetime.now(UTC).isoformat(),
        record_kind='ACTUAL_DISPOSABLE_DEVELOPMENT_NO_MODEL',provider_calls=0,network_calls=0,
        models='NONE: Native derives actions from raw public program/goal/current observations; no Codex/model patch supplied.',
        retained_bridge='Entity Becoming verified capability+applicability changes cold agent candidate catalog and supplies revalidated structural dependency edges.',
        ablation='Same Native/Boundary/World verification and durable retention; disable only verified Entity memory configuration consumption.',
        runs=runs,roots=roots,actual_effects=4,comparison='INTEGRATION_CAUSAL_CONNECTION_ONLY_NOT_A_BENEFIT_OR_SCORED_BENCHMARK',
        full_canonical=False,general_agent_nursery=False,production_connected=False,
        unknown_costs=['complete descendant CPU','OS-wide peak memory','local monetary cost'])
    write_once(out/'RESULT.json',report)
    print(json.dumps(dict(status='VERIFIED_DEVELOPMENT_AGENT_CONNECTION',output=str(out),actual_effects=4,provider_calls=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out');parser.add_argument('--child',action='store_true')
    parser.add_argument('--root');parser.add_argument('--phase',type=int);parser.add_argument('--memory',choices=['0','1'])
    args=parser.parse_args()
    if args.child:
        root=check_root(args.root);os.chdir(root/'projectA')
        result=original.worker(root,'projectA',args.phase,'retained',agent_memory_enabled=args.memory=='1')
        print(json.dumps(result,sort_keys=True))
    else:
        require(args.out is not None,'OUTPUT_REQUIRED');run(args.out)
