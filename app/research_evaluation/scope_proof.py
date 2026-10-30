"""One synthetic no-provider Linux OS-scope/cold-memory development trace."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,time,uuid

APP=Path(__file__).resolve().parents[1]
LANE=APP.parent
def pin(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def linux(path):
    p=str(Path(path).resolve());return '/mnt/'+p[0].lower()+p[2:].replace('\\','/') if len(p)>2 and p[1]==':' else p
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    private=out/'trusted_evaluator';private.mkdir();canary=private/'canary.txt'
    canary.write_text('PRIVATE_EVALUATOR_CANARY_'+uuid.uuid4().hex,encoding='utf-8')
    trajectory=dict(id='SYNTHETIC_DEVELOPMENT_NOT_BENCHMARK',goal='Find the export control',
        start_url='https://example.invalid/reports',outcome='Reported historical observation, not a fresh World effect',
        states=[dict(url='https://example.invalid/reports',action='opened the Reports tab',
            text='The Reports tab contains an Export PDF button. The Home tab has no export control.',screenshot=None)])
    question='Which tab contains the Export PDF button?'
    rows=[]
    for arm in ['conventional','se6']:
        work=out/('SE6-MEMORY-'+arm+'-'+uuid.uuid4().hex);work.mkdir()
        (work/'.SE6_MEMORY_DISPOSABLE').write_text('CUSTOM_DEVELOPMENT_MEMORY_ONLY',encoding='utf-8')
        for operation in ['insert','query']:
            public=dict(operation='insert',trajectory=trajectory) if operation=='insert' else dict(operation='query',question=question,query_image=None)
            command=['wsl.exe','-d','Ubuntu','--exec','/usr/bin/timeout','--signal=TERM','--kill-after=5s','150s',
                '/usr/bin/unshare','--user','--map-root-user','--mount','--net','--fork','/usr/bin/python3.12',
                linux(APP/'research_evaluation/namespace.py'),'--setup','--source',linux(APP),'--deps',linux(LANE/'linux-deps'),
                '--workroot',linux(work),'--adapter',arm,'--canary',linux(canary)]
            start=time.perf_counter();result=subprocess.run(command,input=json.dumps(public),capture_output=True,text=True,timeout=165)
            label=arm+'-'+operation
            (out/(label+'.stdout')).write_text(result.stdout,encoding='utf-8');(out/(label+'.stderr')).write_text(result.stderr,encoding='utf-8')
            write(out/(label+'-transport.json'),dict(returncode=result.returncode,parent_wall_seconds=time.perf_counter()-start,
                stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),stderr_sha256=hashlib.sha256(result.stderr.encode()).hexdigest(),retry_permitted=False))
            if result.returncode!=0:raise ValueError('OS_SCOPE_CHILD_FAILED_NO_RETRY:'+label)
            value=json.loads(result.stdout)
            write(out/(label+'.json'),value)
            if value.get('status')=='FAILED_CLOSED':raise ValueError('OS_SCOPE_MEMORY_FAILED_CLOSED:'+label+':'+value.get('reason','UNKNOWN'))
            if value['os_sandbox']['kernel_boundary']!='VERIFIED':raise ValueError('REAL_OS_SCOPE_NOT_VERIFIED')
            if operation=='query' and not any('Reports' in item['value'] for item in value['context']):raise ValueError('DEVELOPMENT_CONTEXT_NOT_CONSUMED')
            rows.append(dict(arm=arm,operation=operation,pid=value['pid'],os_sandbox=value['os_sandbox'],
                context_sha256=hashlib.sha256(json.dumps(value.get('context'),sort_keys=True).encode()).hexdigest(),resources=value['resources']))
    if len({row['pid'] for row in rows})!=4:raise ValueError('COLD_PROCESS_NOT_DISTINCT')
    report=dict(schema='se6-memory-os-scope-development-proof-v1',at_utc=datetime.now(timezone.utc).isoformat(),
        status='VERIFIED_SYNTHETIC_CONTRACT_AND_REAL_OS_BOUNDARY',record_kind='UNSCORED_DEVELOPMENT_ONLY',
        dataset_cases=0,provider_calls=0,embedding_calls=0,World_effects=0,trajectory='SYNTHETIC_TEXT_ONLY_NOT_LONGMEMEVAL_DATA',
        rows=rows,pins={p.name:pin(p) for p in [APP/'research_evaluation/namespace.py',APP/'research_evaluation/os_probe.py',APP/'research_evaluation/isolation_worker.py']},
        limitations=['No benchmark accuracy score or model judgment exists.','OS namespace/chroot/seccomp bounds this local process; it is not a proof against kernel vulnerabilities.',
            'Actual LongMemEval-V2 multimodal/data-capacity/independent-cluster blockers remain.','Historical source claims remain REPORTED, not Native World-verified capabilities.'])
    write(out/'RESULT.json',report);print(json.dumps(dict(status=report['status'],output=str(out))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args();run(args.out)
