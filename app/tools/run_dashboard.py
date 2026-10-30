"""Complete-source launcher. Default: local native work, zero inference."""
import argparse,datetime,hashlib,json,os,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from hosted_judge import __main__ as entry,service,native_adapter,canonical,canonical_bridge,replays,pair_gateway,v8_run_both,v8_scoring,field_pipeline,toroidal_pipeline,toroidal_field_oracle,navigation_oracle,realization_loop,recursive_controller,durable_sessions
from hosted_judge import benchmark_view,benchmark_campaign,benchmark_controls,benchmark_scoring
from hosted_judge import common_pair_contract,common_answer_scoring
from code_attestation_v7 import fingerprint
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--hosted',action='store_true')
    parser.add_argument('--simulation',action='store_true')
    parser.add_argument('--store',type=Path)
    parser.add_argument('--attestation',type=Path)
    parser.add_argument('--live-approval',type=Path)
    parser.add_argument('--live-approval-sha256')
    parser.add_argument('--disable-awareness',action='store_true',help='Disable new disposable awareness jobs; no production authority')
    parser.add_argument('--model-workflow-evidence',type=Path)
    parser.add_argument('--model-workflow-evidence-sha256')
    parser.add_argument('--agent-realization-evidence',type=Path)
    parser.add_argument('--agent-realization-evidence-sha256')
    parser.add_argument('--research-preparation-evidence',type=Path)
    parser.add_argument('--research-preparation-evidence-sha256')
    args=parser.parse_args()
    if bool(args.research_preparation_evidence)!=bool(args.research_preparation_evidence_sha256):raise ValueError('Exact research evidence file and pin required together')
    if bool(args.model_workflow_evidence)!=bool(args.model_workflow_evidence_sha256):raise ValueError('Exact pilot evidence file and pin required together')
    if bool(args.agent_realization_evidence)!=bool(args.agent_realization_evidence_sha256):raise ValueError('Exact agent development evidence file and pin required together')
    if args.simulation and (args.hosted or args.live_approval):raise ValueError('Simulation is isolated loopback only')
    if bool(args.live_approval)!=bool(args.live_approval_sha256):raise ValueError('Exact new private allowance and hash required together')
    store=args.store or Path(os.environ.get('SE6_PAIR_STORE',str(Path(tempfile.gettempdir())/'se6-competition-v11-private-runtime')))
    store=store.resolve()
    if store.is_relative_to(ROOT):raise ValueError('Private runtime store must remain outside the source package')
    if args.live_approval and args.store is None:raise ValueError('Live activation requires an explicit stable private claim store')
    original=entry.make_server
    def attested(*values,**kw):
        judge=values[0]
        from hosted_judge import model_workflow_view
        pilot_path=args.model_workflow_evidence or ROOT/'evidence/model-workflow-prepared.json'
        complete_manifest=json.loads((ROOT/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json').read_bytes())
        pilot_pin=args.model_workflow_evidence_sha256 or complete_manifest['files'].get('evidence/model-workflow-prepared.json')
        judge.model_workflow_evidence=model_workflow_view.load(pilot_path,pilot_pin)
        from hosted_judge import agent_realization_view
        if args.agent_realization_evidence:
            judge.agent_realization_evidence=agent_realization_view.load(args.agent_realization_evidence,args.agent_realization_evidence_sha256)
        from hosted_judge import research_preparation_view
        if args.research_preparation_evidence:
            judge.research_preparation_evidence=research_preparation_view.load(args.research_preparation_evidence,args.research_preparation_evidence_sha256)
        awareness_module=None
        if not args.disable_awareness and not args.hosted:
            from hosted_judge import awareness_service as awareness_module
            judge.awareness=awareness_module.AwarenessService(store/'awareness',shared_slots=judge.workers)
        model_evidence=ROOT/'evidence/model-integration.json'
        if model_evidence.is_file():
            complete=json.loads((ROOT/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json').read_bytes())
            if sha(model_evidence)!=complete['files'].get('evidence/model-integration.json'):
                raise ValueError('Recorded model evidence source pin mismatch')
            judge.model_integration_evidence=json.loads(model_evidence.read_bytes())
        server=original(*values,**kw)
        modules=(entry,service,native_adapter,canonical,canonical_bridge,replays,pair_gateway,v8_run_both,v8_scoring,field_pipeline,toroidal_pipeline,toroidal_field_oracle,navigation_oracle,realization_loop,recursive_controller,durable_sessions,benchmark_view,benchmark_campaign,benchmark_controls,benchmark_scoring,common_pair_contract,common_answer_scoring,model_workflow_view,agent_realization_view,research_preparation_view)
        functions={'main':entry.main,'make_server':original,'submit':service.JudgeService.submit,'job':service.JudgeService._execute_job,
            'run_sync':service.JudgeService._run_sync,'reset':service.JudgeService.reset,'native':native_adapter.execute_native,
            'validate_bundle':native_adapter.validate_bundle,'begin':canonical_bridge.begin,'finish':canonical_bridge.finish,
            'pair_child':pair_gateway._pair_child,'pair_run':pair_gateway.PairGateway.run,
            'coordinator_run':v8_run_both.RunBothCoordinator.run,'coordinator_replay':v8_run_both.RunBothCoordinator.replay,
            'score_pair':v8_scoring.score_pair,'load_replays':replays.load_replays,'load_current_coverage':canonical.load_current_coverage,
            'field_prepare':field_pipeline.prepare,'field_finish':field_pipeline.finish,'field_public':field_pipeline.public,'toroidal_prepare':toroidal_pipeline.prepare,'toroidal_finish':toroidal_pipeline.finish,'toroidal_public':toroidal_pipeline.public,'toroidal_oracle':toroidal_field_oracle.verify_result,'navigation_oracle':navigation_oracle.verify_navigation}
        functions.update({'loop_prepare':realization_loop.prepare_candidates,'loop_act':realization_loop.act_verify_assimilate,
            'loop_finalize':realization_loop.finalize_verified,'loop_restore':realization_loop.load_restore,
            'recursive_execute':recursive_controller.execute,'recursive_restore':recursive_controller.restore,
            'recursive_proof':native_adapter.verify_realization,'wrapper_signature':native_adapter.wrapper_signature,
            'durable_save':durable_sessions.DurableSessions.save,'durable_restore':durable_sessions.DurableSessions.restore})
        functions.update({'benchmark_load':benchmark_view.load_benchmark,'benchmark_native_repeat':benchmark_view.BenchmarkTaskRunner._run,
            'benchmark_native_submit':benchmark_view.BenchmarkTaskRunner.submit,'benchmark_native_get':benchmark_view.BenchmarkTaskRunner.get,
            'benchmark_control':benchmark_controls.run_condition,'benchmark_pilot_prepare':benchmark_campaign.prepare_pilot,
            'benchmark_pilot_run':benchmark_campaign.PilotCoordinator.run,'benchmark_pilot_authorize':benchmark_campaign.PilotCoordinator.authorize})
        functions.update({'common_spec':common_pair_contract.derive_public_spec,'common_shape':common_pair_contract.public_shape,
            'common_safe_spec':common_pair_contract.safe_spec,'common_score_pair':common_pair_contract.score_pair,
            'common_grade_answer':common_answer_scoring.grade_answer})
        functions.update({'agent_development_load':agent_realization_view.load,
            'agent_development_read':service.JudgeService.read_agent_realization_evidence})
        functions.update({'research_preparation_load':research_preparation_view.load,
            'research_preparation_read':service.JudgeService.read_research_preparation_evidence})
        if awareness_module is not None:
            modules=modules+(awareness_module,)
            functions.update({'awareness_submit':awareness_module.AwarenessService.submit,
                'awareness_get':awareness_module.AwarenessService.get,
                'awareness_export':awareness_module.AwarenessService.export})
        row={'schema':'se6-v11-owned-serving-attestation','actual_pid':os.getpid(),'origin':server.public_origin,
            'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_directory':str(ROOT),
            'loopback_only':kw.get('loopback_development') is True,'mode':'SIMULATED_TEST' if args.simulation else 'LIVE_EXACT_ALLOWANCE_CONFIGURED' if args.live_approval else 'OFFLINE_NATIVE_PREPARED_PAIR',
            'loaded_modules':{Path(m.__file__).name:sha(Path(m.__file__)) for m in modules},
            'loaded_function_codes':{name:fingerprint(f) for name,f in functions.items()},
            'static_files':{p.name:sha(p) for p in (ROOT/'hosted_judge/static').iterdir() if p.is_file()},
            'data_pins':{name:sha(ROOT/name) for name in ('native-manifest.json','public-review.json','frozen-replays.json','canonical/public-evidence.json','dynamic/public-evidence.json','current-operator-coverage.json','candidate-field-controls.json','heldout/public-tasks.json','heldout/benchmark-public-view.json') if (ROOT/name).is_file()},
            'new_provider_calls_at_startup':0,'production_connected':False,
            'awareness_enabled':judge.awareness is not None,
            'agent_development_evidence_configured':judge.agent_realization_evidence is not None,
            'scope':'Current parent code and frozen assets. Private native src/operator compilation is separately worker-attested; no container or historical runtime attestation.'}
        if args.attestation:
            args.attestation.parent.mkdir(parents=True,exist_ok=True)
            with args.attestation.open('x',encoding='utf-8') as stream:json.dump(row,stream,indent=2)
        print(json.dumps({'owned_pid':os.getpid(),'origin':server.public_origin,'mode':row['mode']}),flush=True)
        return server
    entry.make_server=attested
    argv=['se6-competition-v8','--port',str(args.port),'--pair-store',str(store),
        '--native-bundle',str(ROOT/'private-native'),'--native-manifest',str(ROOT/'native-manifest.json'),
        '--native-manifest-sha256',sha(ROOT/'native-manifest.json')]
    for flag,name in (('review','public-review.json'),('dynamic','dynamic/public-evidence.json'),('canonical','canonical/public-evidence.json'),('replays','frozen-replays.json'),('current-coverage','current-operator-coverage.json'),('field-controls','candidate-field-controls.json')):
        argv.extend(['--'+flag,str(ROOT/name),'--'+flag+'-sha256',sha(ROOT/name)])
    if (ROOT/'heldout/benchmark-public-view.json').is_file():
        argv.extend(['--benchmark',str(ROOT/'heldout/benchmark-public-view.json'),'--benchmark-sha256',sha(ROOT/'heldout/benchmark-public-view.json'),
            '--benchmark-tasks',str(ROOT/'heldout/public-tasks.json'),'--benchmark-tasks-sha256',sha(ROOT/'heldout/public-tasks.json')])
    if not args.hosted:argv.append('--loopback-development')
    elif not os.environ.get('PUBLIC_ORIGIN'):raise ValueError('Hosted mode requires exact PUBLIC_ORIGIN')
    if args.simulation:argv.append('--pair-simulation')
    if args.live_approval:argv.extend(['--live-pair','--pair-approval',str(args.live_approval),'--pair-approval-sha256',args.live_approval_sha256])
    sys.argv=argv;entry.main()

if __name__=='__main__':main()
