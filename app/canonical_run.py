"""Offline benchmark driver: exclusive archive, public inputs only to workers."""
import argparse,datetime,hashlib,json,os,secrets,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',required=True);p.add_argument('--archive',required=True);p.add_argument('--bundle',required=True)
    p.add_argument('--condition',choices=['SE6','DROP_RETAINED_STATE','ALL'],default='ALL');args=p.parse_args()
    root=Path(__file__).resolve().parent;archive=Path(args.archive).resolve();archive.mkdir(parents=True,exist_ok=False)
    sources=lambda:{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.py')}
    source_start=sources();spec_bytes=Path(args.spec).read_bytes();spec=json.loads(spec_bytes)
    spec_pin=hashlib.sha256(spec_bytes).hexdigest();bundle=Path(args.bundle).resolve();manifest=bundle/'hosted-test-manifest.json'
    pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
    env={n:v for n,v in os.environ.items() if n.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','SYSTEMDRIVE')}
    env['PYTHONPATH']=os.pathsep.join([str(root)]+[p for p in sys.path if 'site-packages' in p]);env['PYTHONDONTWRITEBYTECODE']='1'
    started=time.perf_counter();parent_cpu=time.process_time();rows=[];row_hashes={}
    inputs=archive/'private-inputs';inputs.mkdir()
    artifact=Path(args.spec).parent/'technical-artifact.json'
    if hashlib.sha256(artifact.read_bytes()).hexdigest()!=spec['technical_artifact_sha256']:raise ValueError('Artifact differs from public commitment')
    (inputs/'technical-artifact.json').write_bytes(artifact.read_bytes())
    conditions=['SE6','DROP_RETAINED_STATE'] if args.condition=='ALL' else [args.condition]
    for scenario in spec['scenarios']:
      for condition in conditions:
       for index,event in enumerate(scenario['events']):
        output=archive/f"{scenario['id']}-{condition}-{index}.json";wall=time.perf_counter()
        case={'task_namespace':hashlib.sha256((spec_pin+scenario['id']+condition).encode()).hexdigest()[:32],
          'scenario':{'id':scenario['id'],'domain':scenario['domain']},'event':event,'event_index':index,
          'technical_artifact_sha256':spec['technical_artifact_sha256'],'launch_nonce':secrets.token_hex(16)}
        case_path=inputs/output.name;case_path.write_text(json.dumps(case),encoding='utf-8')
        command=[sys.executable,'-B',str(root/'canonical_worker.py'),'--bundle',str(bundle),'--manifest',str(manifest),'--pin',pin,
            '--spec',str(case_path),'--scenario',scenario['id'],'--event',str(index),'--condition',condition,
            '--store',str(archive/'private-state'/condition/case['task_namespace']),'--output',str(output)]
        launched_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:stdout,stderr=process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill();stdout,stderr=process.communicate();stderr+='\nOwned benchmark worker exceeded 60s'
        if process.returncode:
            (archive/'INCOMPLETE.json').write_text(json.dumps({'scenario':scenario['id'],'event':index,'condition':condition,'stderr':stderr,'provider_calls':0},indent=2),encoding='utf-8')
            raise RuntimeError(stderr)
        value=json.loads(output.read_bytes());value['measurements']['subprocess_wall_seconds']=time.perf_counter()-wall
        value['driver_observation']={'actual_spawned_pid':process.pid,'launch_nonce':case['launch_nonce'],
          'launched_at_utc':launched_at,'observed_exit_code':process.returncode,
          'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        output.write_text(json.dumps(value,indent=2),encoding='utf-8');rows.append(output.name)
        row_hashes[output.name]=hashlib.sha256(output.read_bytes()).hexdigest()
       print(json.dumps({'scenario_finished':scenario['id'],'condition':condition,'rows':len(rows),'provider_calls':0}),flush=True)
    if sources()!=source_start or hashlib.sha256(Path(args.spec).read_bytes()).hexdigest()!=spec_pin:raise ValueError('Source or inputs changed during capture')
    totals={'rows':rows,'row_sha256':row_hashes,'conditions':conditions,'driver_wall_seconds':time.perf_counter()-started,'driver_cpu_seconds':time.process_time()-parent_cpu,'provider_calls':0,
        'source_files':source_start,'source_start_matches_end':True,
        'public_spec_sha256':spec_pin,'native_bundle_manifest_sha256':pin,
        'worker_input_scope':'Current event, opaque task namespace, own retained state and fixture only; no future events, seed or key. Python audited reads enforced, not an OS security sandbox.',
        'model_conditions':{'A':'NOT_EXECUTED','B':'NOT_EXECUTED','C_model':'NOT_EXECUTED'},
        'scope':'Offline integrated canonical/native pipeline acceptance; no new model call, memory ablation or conventional-model-agent winner'}
    (archive/'run-manifest.json').write_text(json.dumps(totals,indent=2),encoding='utf-8')
if __name__=='__main__':main()
