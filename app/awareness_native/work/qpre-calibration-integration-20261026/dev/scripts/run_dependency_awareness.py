"""One frozen, offline, disposable dependency-awareness evaluation; never production."""
from pathlib import Path
from datetime import datetime,UTC
from copy import deepcopy
from fractions import Fraction
import argparse,hashlib,json,os,random,subprocess,sys,time,tempfile,uuid,tracemalloc
from urllib.parse import urlsplit,unquote
CORE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
from scripts.run_native_qpre_learning import dependencies,new_root,check_root,read,write_once
from se666_core.observation_grounding import digest,require,raw_id
from se666_core.grounded_native_input import GroundedNativeConsumer
from se666_core.native_dependency_agent import DependencyRepairAgent,verified_capability
from se666_core import native_dependency_relation_v1 as domain
from se666_core.entity_store import EntityStore
from se666_core.situated_entity import RepositoryObservationPort,read_situated_entity
from se666_core.local_entity_observers import RepositoryObservationPolicy,repository_snapshot_event
from se666_core.native_situated_awareness import NativeSituatedPort,VERSION as SITUATED_VERSION
from se666_core.three_loop_entity import SE6TriLoopCoordinator
from se666_core.entity_runtime import LocalEntityRuntime
from se666_core.grounded_general_action_cycle import _commit
from se666_core.entity_events import EntityEventDraft,EventType,LoopName,EventEndpoint,EventSourceKind,ObservationPayload,ObservationProvenance,AuthorityStatus,VerificationPayload,VerificationResult
from se666_core.epistemic_status import EpistemicStatus

WORKLOAD='''import json,sys\nfrom pathlib import Path\nm=json.loads(Path('manifest.json').read_text());s=json.loads(Path('goal.json').read_text())\np=m['profiles'][m['entry']];c=json.loads(Path(p['config']).read_text())\ny=p['gain']*c['limit']+p['offset']\nprint(json.dumps({'output':y,'cwd':str(Path.cwd().resolve())},sort_keys=True))\nraise SystemExit(0 if y==s['goal'] else 3)\n'''
SOURCE='independent-local-cli-dependency-development'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):write_once(Path(p),v)
def child(root,operation,phase,world,arm):
    p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--child',operation,
        '--root',str(root),'--phase',str(phase),'--world',world,'--arm',arm],cwd=root/world,
        capture_output=True,text=True,timeout=75,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    require(p.returncode==0,'AWARENESS_CHILD_FAILED:'+p.stderr[-3000:])
    return json.loads(p.stdout)

def observe(root,world):
    root=check_root(root);cwd=(root/world).resolve();require(Path.cwd().resolve()==cwd,'ACTUAL_WORKING_ROOT')
    files={p.name:json.loads(p.read_bytes()) for p in sorted(cwd.glob('*.json'))}
    require(len(files)<=12 and all(p.is_file() and not p.is_symlink() and p.stat().st_size<4096 for p in cwd.iterdir()),'BOUNDED_PUBLIC_WORLD')
    run=subprocess.run([sys.executable,'-I','-B','workload.py'],cwd=cwd,capture_output=True,text=True,timeout=5)
    require(run.returncode in (0,3),'PUBLIC_CLI_FAILED')
    result=json.loads(run.stdout);require(result['cwd']==str(cwd),'CLI_ACTUAL_SELF_CONTEXT')
    return dict(manifest=files['manifest.json'],schema=files['goal.json'],
        configs={k:v for k,v in files.items() if k not in ('manifest.json','goal.json')},
        context=dict(cwd=str(cwd),observed_root=str(cwd)),failure=dict(output=result['output'],returncode=run.returncode),
        file_hashes={p.name:sha(p) for p in cwd.iterdir() if p.is_file()})

def commit_draft(store,draft,key,at):
    runtime=LocalEntityRuntime(store=store,runtime_session_id='runtime_cognition_test',clock=lambda:at)
    ingress=runtime.enqueue(draft=draft,ingress_key=key)
    for _ in range(16):
        step=runtime.process_one()
        require(step is not None,'DURABLE_ENTITY_TARGET_NOT_PENDING')
        if step.ingress.ingress_id==ingress.ingress_id:return step.receipt
    raise ValueError('BOUNDED_ENTITY_FIFO_PREDECESSOR_LIMIT')

def commit_observation(store,relation,value,refs,phase):
    at=datetime.now(UTC);before=store.reconstruct()
    co=SE6TriLoopCoordinator(state=before.state,historical_events=before.historical_events)
    draft=EntityEventDraft(event_type=EventType.OBSERVATION,occurred_at_utc=at,originating_loop=LoopName.EXTERNAL,
        source=EventEndpoint(kind=EventSourceKind.COMPONENT,identifier=SOURCE),
        target=EventEndpoint(kind=EventSourceKind.SE6,identifier=before.state.identity.instance_id),
        relation=relation,provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,epistemic_status=EpistemicStatus.VERIFIED,
        authority_status=AuthorityStatus.NOT_REQUIRED,correlation_id=relation+'-'+str(phase),
        payload=ObservationPayload(world_node='disposable-local-cli',relation=relation,value_summary=json.dumps(value,sort_keys=True),
            provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,observed_at_utc=at,
            evidence_references=tuple(refs),confidence_basis_points=10000))
    return commit_draft(store,draft,relation+'-'+str(phase),at)

class Ports:
    """Real local host ports: raw observation authentication, no solver here."""
    def __init__(self,root):self.root=check_root(root);self.store=EntityStore.for_testing(self.root/'entity.sqlite3')
    def read_verified_agent_capability(self,prior,phase):
        retained=read(self.root/f'retained-{phase}.json');renewal=read(self.root/f'renewal-{phase}.json')
        result=read(self.root/f'result-{phase}.json');effect=read(self.root/f'effect-{phase}.json')
        configuration=read(self.root/f'agent-config-{phase}.json')
        require(prior==retained and renewal['state_sha256']==digest(prior)==result['retained_state_sha256']
            and result['goal'] is True and result['actual_effects']==1
            and prior['renewals'][-1]['passed'] is True
            and result['witness_sha256']==digest(effect['witness'])==prior['renewals'][-1]['witness_sha256']
            and effect['witness']['goal'] is True and effect['after']['failure']['returncode']==0,
            'AGENT_COMPLETED_INDEPENDENT_RENEWAL_REQUIRED')
        audited=self.store.inspect_read_only()[2]
        require(renewal['entity_state_id'] in [s.entity_state_id for s in audited.states]
            and renewal['entity_receipt_id']==result['entity_receipt_id'],'AGENT_ENTITY_RENEWAL_ANCESTRY')
        return verified_capability(effect['before'],result['selected_action'],configuration,effect['witness'])
    def authenticate_dependency_certificate(self,value):
        obs=value['observation'];phase=obs['context']['phase'];f=read(self.root/f'observed-{phase}.json')
        require(f==obs and digest(value['history'])==read(self.root/f'history-{phase}.json')['sha256'],'INDEPENDENT_OBSERVER_EXACT_BYTES')
        lineage=self.store.reconstruct();require(obs['context']['entity_id']==lineage.state.identity.instance_id and
            obs['context']['identity_state_id']==lineage.state.identity.identity_state_id,'OBSERVED_ENTITY_IDENTITY')
        audited=self.store.inspect_read_only()[2]
        require(obs['context']['entity_state_id'] in [s.entity_state_id for s in audited.states],'OBSERVED_ENTITY_ANCESTRY')
        if value['memory'] is not None:
            mem=value['memory'];prior=read(self.root/f'retained-{phase-1}.json');renew=read(self.root/f'renewal-{phase-1}.json')
            require(renew['state_sha256']==digest(prior)==mem['retained_state_sha256'] and
                prior['renewals'][-1]['passed'] is True and
                mem['observation']==prior['certificate']['observation'],'VERIFIED_RETAINED_RELATION_SOURCE')
        return True

def snapshot(root,world,ports,obs,phase):
    repo=RepositoryObservationPort(root/world,policy=RepositoryObservationPolicy(max_files=16))
    at=datetime.now(UTC);measured=repo.read_snapshot(observed_at_utc=at)
    lineage=ports.store.reconstruct();co=SE6TriLoopCoordinator(state=lineage.state,historical_events=lineage.historical_events)
    commit_draft(ports.store,repository_snapshot_event(measured,correlation_id='dependency-metadata-'+str(phase)),
        'dependency-metadata-'+str(phase),at)
    actual=ports.store.reconstruct().state
    situated=read_situated_entity(ports.store,expected_entity_id=actual.identity.instance_id,
        expected_identity_state_id=actual.identity.identity_state_id,expected_entity_state_id=actual.entity_state_id,
        observation_port=repo,as_of_utc=datetime.now(UTC))
    native_port=NativeSituatedPort(ports.store,repo)
    projection=native_port.read(dict(version=SITUATED_VERSION,snapshot=situated.model_dump(mode='json'),require_complete_environment=True),
        dict(entity_id=actual.identity.instance_id,entity_state='observation-only',source=SOURCE,epoch='dependency-v1',memory_head='observation'))
    obs['context'].update(entity_id=actual.identity.instance_id,identity_state_id=actual.identity.identity_state_id,
        entity_state_id=actual.entity_state_id,phase=phase,situated_projection_sha256=projection['projection_sha256'],
        situated_frame_hash=projection['context']['situated_frame_hash'])
    dump(root/f'situated-{phase}.json',projection)

def conventional(obs,actions):
    profile=obs['manifest']['profiles'][obs['manifest']['entry']]
    needed=Fraction(obs['schema']['goal']-profile['offset'],profile['gain'])
    require(needed.denominator==1 and 0<=needed<=100,'CONTROL_UNSUPPORTED_INTEGER')
    action=next(a for a in actions if a['payload']['path']==profile['config'])
    return {**action,'payload':{**action['payload'],'value':int(needed)}}

def worker(root,world,phase,arm,*,model_proposal=None,proposal_gate=None,action_executor=None,allow_missing_prior=False,agent_memory_enabled=True):
    whole_wall=time.perf_counter();whole_cpu=time.process_time();tracemalloc.start()
    root=check_root(root);ports=Ports(root);reference,composer,attempts_type=dependencies()
    initial=read(root/'native-genesis.json');prior=None
    if phase>1 and (not allow_missing_prior or (root/f'retained-{phase-1}.json').is_file()):
        prior=read(root/f'retained-{phase-1}.json');renewal=read(root/f'renewal-{phase-1}.json')
        require(renewal['state_sha256']==digest(prior),'EXTERNAL_COLD_RENEWAL_PIN')
        require(ports.store.reconstruct().state.entity_state_id==renewal['entity_state_id'],'COLD_ENTITY_NATIVE_CROSS_REFERENCE')
        old=read(root/f'effect-{phase-1}.json');w=old['witness']
        require(w['goal'] is True and old['after']['failure']['returncode']==0 and
            old['after']['failure']['output']==old['before']['schema']['goal'],'COLD_INDEPENDENT_EFFECT_EVIDENCE')
        if arm!='conventional':require(prior['renewals'][-1]['witness_sha256']==digest(w),'COLD_NATIVE_WORLD_WITNESS_ANCESTRY')
    elif phase>1:
        refusal_path=root/f'model-refused-{phase-1}.json'
        if refusal_path.is_file():
            refused=read(refusal_path)
            require(refused['status']=='REFUSED_PROPOSAL' and refused['actual_effects']==0
                and refused['pending_created'] is False,'UNVERIFIED_PRIOR_OUTCOME_NO_CONTINUATION')
        else:
            # An abstained/invalid model command may never have invoked the
            # Native stage. No prior verified knowledge is then available.
            # A pending selection or any nonrefundable attempt blocks this
            # conservative genesis continuation; it is never cleared/reset.
            require(not (root/f'selection-{phase-1}.json').exists()
                and not (root/f'effect-{phase-1}.json').exists()
                and not (root/'attempts').exists(),'UNVERIFIED_PRIOR_OUTCOME_NO_CONTINUATION')
    # Deny evaluator/private-file reads and all networking at the actual solver
    # boundary. Imports are already loaded; allowed source reads are read-only.
    runtime_paths=[Path(sys.base_prefix).resolve(),Path(sys.prefix).resolve(),CORE.resolve()]
    tools=[]
    def audit(event,args):
        if event.startswith('socket.'):raise RuntimeError('AWARENESS_NETWORK_DENIED')
        if event=='sqlite3.connect':
            address=str(args[0])
            if address.startswith('file:'):
                address=unquote(urlsplit(address).path)
                if os.name=='nt' and address.startswith('/') and len(address)>2 and address[2]==':':address=address[1:]
            require(Path(address).resolve().is_relative_to(root),'SOLVER_DATABASE_SCOPE')
        if event=='subprocess.Popen':
            commands={'cli':[sys.executable,'-I','-B','workload.py']}
            for operation in ('observe','readback'):
                commands[operation]=[sys.executable,'-B',str(Path(__file__).resolve()),'--child',operation,
                    '--root',str(root),'--phase',str(phase),'--world',world,'--arm',arm]
            raw=args[1]
            matches=[name for name,cmd in commands.items() if raw==(subprocess.list2cmdline(cmd) if isinstance(raw,str) else cmd)]
            require(len(matches)==1,'SOLVER_SUBPROCESS_TOOL_SCOPE');tools.append(matches[0])
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve();mode=str(args[1])
            if path.is_relative_to(root):return
            if path==Path(__file__).resolve() or (not any(c in mode for c in 'wax+') and any(path.is_relative_to(p) for p in runtime_paths)):return
            raise PermissionError('SOLVER_FILE_SCOPE_DENIED')
    # Reference uses externally pinned module files; these are public source,
    # never evaluator answers. Keep their exact declared directories read-only.
    runtime_paths += [CORE.parents[2]/'work/codex-vscode-research/operational-realization/engine',
        CORE.parents[2]/'work/codex-vscode-research/alpha-continuation/engine',
        CORE.parents[2]/'work/se6-reference-continuity-v010-448349319aa1/SE6_Reference_Continuity_v0.1.0']
    sys.addaudithook(audit)
    forbidden=root.parent/'SE6_AWARENESS_EVALUATOR_ONLY'/ 'not-solver-input.json'
    try:forbidden.read_bytes()
    except PermissionError:isolation=True
    else:raise ValueError('EVALUATOR_READ_NOT_BLOCKED')
    for name,pin in read(root/'source-pins.json').items():require(sha(name)==pin,'FROZEN_SOLVER_SOURCE_CHANGED')
    consumer=(DependencyRepairAgent.restore(reference,prior,ports,composer,expected_sha256=renewal['state_sha256'])
        if prior else DependencyRepairAgent(reference,initial,ports,composer)) if arm!='conventional' else None
    before=observe(root,world);independent=child(root,'observe',phase,world,arm)
    require(before==independent,'INDEPENDENT_RAW_OBSERVATION_DISAGREEMENT')
    require(before['failure']['returncode']==3,'FRESH_FAILING_WORKLOAD_REQUIRED')
    snapshot(root,world,ports,before,phase)
    actions=[dict(id='set:'+name,payload=dict(op='SET_INTEGER',path=name,field='limit'),cost=1) for name in sorted(before['configs'])]
    agent_configuration=None;consume_verified_memory=False
    if consumer:
        actions,agent_configuration,consume_verified_memory=consumer.configure(before,actions,prior=prior,
            phase=phase,memory_enabled=agent_memory_enabled and arm=='retained')
        before['context']['agent_configuration_sha256']=digest(agent_configuration)
        dump(root/f'agent-config-{phase}.json',agent_configuration)
    if model_proposal is not None:
        require(arm=='retained' and callable(proposal_gate),'MODEL_NATIVE_PROPOSAL_PORT_REQUIRED')
        before['context']['model_proposal']=dict(status='UNTRUSTED_MODEL_PROPOSAL',value=deepcopy(model_proposal))
    dump(root/f'observed-{phase}.json',before)
    commit_observation(ports.store,'observed_dependency_bytes',dict(observation_sha256=digest(before),root_sha256=digest(before['context']['cwd'])),[digest(before)],phase)
    history=[dict(id=f'phase-{phase}',source=SOURCE,epoch=sha(root/world/'workload.py'),episode=phase,index=0,action=None,
        raw=[before['failure']['output']],goal=None)]
    dump(root/f'history-{phase}.json',dict(sha256=digest(history)))
    memory=None
    if prior and arm=='retained' and consume_verified_memory:
        memory=dict(observation=prior['certificate']['observation'],retained_state_sha256=digest(prior))
    entity=ports.store.reconstruct().state;attempt=f'awareness-{phase}'
    binding=dict(entity_id=entity.identity.instance_id,entity_state=consumer.engine.state.state_hash if consumer else 'CONTROL',
        memory_head=(consumer.engine.receipts[-1].receipt_hash if consumer and consumer.engine.receipts else 'dependency-genesis'),source=SOURCE,epoch=history[0]['epoch'])
    cpu=time.process_time();wall=time.perf_counter()
    if consumer:
        cert=domain.certificate(before,history,binding,memory=memory)
        boundary=dict(identity=binding['entity_id'],authorized=True,permissions=[a['id'] for a in actions],
            native_permissions=['GROUNDING_EVALUATE'],max_native_actions=10,remaining_actions=1,remaining_effects=1,
            remaining_cost=1,retention_permissions=['READ_CURRENT','ARCHIVE_RETAIN'],selection_policy={})
        model_gate=None
        if model_proposal is not None:
            # Existing pure Native preparation verifies the source-defined
            # candidate relation before select can create a pending effect.
            # A rejected model proposal is not a contradiction of its source.
            from se666_core.grounded_native_input import prepare_native_input
            prepared=prepare_native_input(cert,history,binding,actions,ports)
            model_gate=proposal_gate(model_proposal,before,prepared,consumer,boundary,actions)
            dump(root/f'model-gate-{phase}.json',model_gate)
            if not model_gate['allowed']:
                result=dict(phase=phase,arm=arm,status='REFUSED_PROPOSAL',goal=False,
                    actual_effects=0,pending_created=False,model_proposal_sha256=digest(model_proposal),
                    proposal_gate=model_gate,proposal_gate_sha256=digest(model_gate),
                    native_receipt_hash=None,entity_state_id=ports.store.reconstruct().state.entity_state_id,
                    cold_restored=prior is not None,verified_prior_memory_available=prior is not None,
                    native_preflight_calls=1,native_evaluations=0,
                    worker_cpu_seconds=time.process_time()-whole_cpu,worker_wall_seconds=time.perf_counter()-whole_wall,
                    peak_traced_python_bytes=tracemalloc.get_traced_memory()[1],model_calls=0,
                    limitation='Native affine operator independently validates; model values are never silently corrected.')
                dump(root/f'model-refused-{phase}.json',result)
                dump(root/f'result-{phase}.json',result)
                return result
        selection=consumer.select(cert,history,binding,actions,boundary,attempt)
        require(selection['status']=='SELECTED_PENDING_EXECUTION','NATIVE_NO_DERIVED_ACTION')
        pending=consumer.pending;selected=pending['action']
        dump(root/f'selection-{phase}.json',selection)
        if model_proposal is not None:
            require(selected['payload']==dict(op='SET_INTEGER',path=model_proposal['path'],
                field='limit',value=model_proposal['value']),
                'MODEL_PROPOSAL_NATIVE_SELECTION_MISMATCH_NO_FALLBACK')
    else:
        selected=conventional(before,actions);pending=dict(action=selected,attempt_id=attempt,prepared={'binding':binding})
    decision_cost=dict(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall)
    def permission(p):
        grant=read(root/'development-authority.json')
        require(grant['scope']=='DISPOSABLE_DEVELOPMENT_ONLY_NOT_OWNER_AUTHENTICATION' and
            grant['entity_id']==binding['entity_id'] and type(grant['max_effects']) is int
            and 1<=grant['max_effects']<=3 and phase<=grant['max_effects'] and
            world in grant['worlds'],'EXPLICIT_TEST_ONLY_ACTION_AUTHORITY')
        require(p['attempt_id']==attempt and ports.store.reconstruct().state.identity.instance_id==binding['entity_id'],'CURRENT_DEV_IDENTITY')
        require(Path.cwd().resolve()==root/world and observe(root,world)['file_hashes']==before['file_hashes'],'PRE_EFFECT_SOURCE_SELF_FRESHNESS')
        a=p['action'];require(a['id'] in [x['id'] for x in actions] and a['payload']['path'] in before['configs'] and
            a['payload']['op']=='SET_INTEGER' and a['payload']['field']=='limit' and type(a['payload']['value']) is int
            and 0<=a['payload']['value']<=100,'CURRENT_DISPOSABLE_PERMISSION')
    def dispatch(p):
        permission(p)
        if action_executor is not None:
            require(model_proposal is not None,'MODEL_SHARED_EXECUTOR_REQUIRES_PROPOSAL')
            return action_executor(deepcopy(p),permission)
        target=root/world/p['action']['payload']['path']
        material=read(target);material['limit']=p['action']['payload']['value']
        temporary=target.with_suffix('.new');dump(temporary,material);os.replace(temporary,target)
    if consumer:
        old_head=None if not prior else prior['current_core_head']
        consumer.dispatch(current_head=binding['memory_head'],current_permission_verifier=permission,
            existing_dispatcher=dispatch,durable_attempts=attempts_type(root/'attempts',binding['entity_id']),durable_prior_head=old_head)
    else:
        claims=attempts_type(root/'attempts',binding['entity_id']);claims.begin(attempt,pending,None if phase==1 else 'control-'+str(phase-1))
        try:dispatch(pending);claims.complete({'core_head':'control-'+str(phase),'pending':pending})
        finally:claims.close()
    after=child(root,'observe',phase,world,arm)
    changed=[n for n in before['file_hashes'] if before['file_hashes'][n]!=after['file_hashes'][n]]
    require(changed==[selected['payload']['path']],'INDEPENDENT_EXACT_FILE_MUTATION')
    goal=after['failure']['returncode']==0 and after['failure']['output']==before['schema']['goal']
    row={**history[-1],'id':f'effect-{phase}','index':1,'action':selected['id'],'raw':[after['failure']['output']],'goal':goal}
    witness=dict(purpose='GROUNDING_WORLD_EFFECT',entity_id=binding['entity_id'],attempt_id=attempt,
        source=SOURCE,epoch=binding['epoch'],action_sha256=digest(selected),before_head=binding['memory_head'],
        raw=row['raw'],goal=goal,observation_row=row,after_sha256=digest(after))
    dump(root/f'effect-{phase}.json',dict(before=before,after=after,witness=witness))
    entity_commit=commit_observation(ports.store,'verified_dependency_consequence',dict(witness_sha256=digest(witness),
        goal=goal,observation_sha256=digest(before),native_head=pending.get('core_head','CONVENTIONAL')),[digest(witness),digest(before)],phase)
    independent_effect_passed=False
    def verify_effect(w,p):
        nonlocal independent_effect_passed
        observed=child(root,'observe',phase,world,arm)
        require(observed==after and w==witness and digest(p['action'])==w['action_sha256'],'FRESH_INDEPENDENT_EFFECT_READBACK')
        independent_effect_passed=True
        return True
    def writer(state,previous):
        nonlocal entity_commit
        if consumer:
            require(independent_effect_passed and goal,'AGENT_VERIFICATION_BEFORE_ASSIMILATION')
            capability=verified_capability(before,selected,agent_configuration,witness)
            summary=json.dumps(capability,sort_keys=True,separators=(',',':'))
            source_event=next(e for e in reversed(ports.store.reconstruct().historical_events)
                if isinstance(e.payload,ObservationPayload) and e.payload.relation=='verified_dependency_consequence'
                and digest(witness) in e.payload.evidence_references)
            at=datetime.now(UTC);actual=ports.store.reconstruct().state
            draft=EntityEventDraft(event_type=EventType.VERIFICATION,occurred_at_utc=at,
                originating_loop=LoopName.EXTERNAL,source=EventEndpoint(kind=EventSourceKind.COMPONENT,identifier=SOURCE),
                target=EventEndpoint(kind=EventSourceKind.SE6,identifier=actual.identity.instance_id),
                relation='verified_native_dependency_capability',provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
                epistemic_status=EpistemicStatus.VERIFIED,authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id='verified-capability-'+str(phase),payload=VerificationPayload(
                    subject_event_id=source_event.event_id,result=VerificationResult.PASSED,independently_verified=True,
                    evidence_references=(digest(capability),digest(witness),digest(agent_configuration)),summary=summary))
            entity_commit=commit_draft(ports.store,draft,'verified-capability-'+str(phase),at)
        dump(root/f'retained-{phase}.json',state)
        receipt=dict(purpose='GROUNDING_DURABLE_RENEWAL',state_sha256=digest(state),previous_head=previous,
            entity_receipt_id=entity_commit.receipt_id,entity_state_id=ports.store.reconstruct().state.entity_state_id)
        dump(root/f'renewal-{phase}.json',receipt);return receipt
    def verifier(receipt,state,previous):
        checked=child(root,'readback',phase,world,arm)
        require(checked['state_sha256']==digest(state)==receipt['state_sha256'] and
            checked['entity_state_id']==receipt['entity_state_id'],'INDEPENDENT_ENTITY_NATIVE_RENEWAL')
        return True
    if consumer:
        renewal=consumer.verify_cycle(witness,independent_effect_verifier=verify_effect,
            durable_renewal_writer=writer,independent_renewal_verifier=verifier)
        require(renewal['passed'] and renewal['goal'],'ACTUAL_PREDICTION_CONSEQUENCE')
        restored=prior is not None;native_head=consumer.engine.receipts[-1].receipt_hash
        used=json.loads(consumer.engine.receipts[-1].observed_consequence.result)['decision']['prediction']['reused_edge_ids']
    else:
        state=dict(certificate={'observation':before},renewals=[dict(passed=goal)],current_core_head='control-'+str(phase))
        receipt=writer(state,binding['memory_head']);verifier(receipt,state,binding['memory_head']);used=[];native_head=None;restored=phase>1
    result=dict(phase=phase,arm=arm,pid=os.getpid(),actual_root=str(Path.cwd()),goal=goal,selected_action=selected,
        changed_files=changed,decision_cost=decision_cost,cold_restored=restored,maintained_edges_consumed=used,
        observation_sha256=digest(before),certificate_sha256=consumer.current_certificate['certificate_sha256'] if consumer else None,
        mapper_sha256=consumer.grounding_records[-1]['material']['mapped']['map_hash'] if consumer else None,
        previous_retained_state_sha256=digest(prior) if prior else None,
        entity_receipt_id=entity_commit.receipt_id,renewal_receipt_sha256=digest(read(root/f'renewal-{phase}.json')),
        native_receipt_hash=native_head,entity_state_id=ports.store.reconstruct().state.entity_state_id,
        entity_version=ports.store.reconstruct().state.state_version,witness_sha256=digest(witness),
        retained_state_sha256=sha(root/f'retained-{phase}.json'),solver_evaluator_reads_blocked=isolation,
        agent_configuration=agent_configuration,verified_capability_memory_consumed=consume_verified_memory,
        agent_implementation=type(consumer).__name__ if consumer else None,
        actual_effects=1,failed_attempts=0,observed_cli_processes=sum(t in ('cli','observe') for t in tools),
        tool_invocations=tools,worker_wall_seconds=time.perf_counter()-whole_wall,
        worker_cpu_seconds=time.process_time()-whole_cpu,peak_traced_python_bytes=tracemalloc.get_traced_memory()[1],
        child_cpu_seconds=None,local_monetary_cost=None,model_calls=0)
    if model_proposal is not None:
        result.update(model_proposal_sha256=digest(model_proposal),proposal_gate_sha256=digest(model_gate),
            proposal_gate=model_gate,native_preflight_calls=1,native_evaluations=1,
            verified_prior_memory_available=prior is not None,fallback_used=False)
    dump(root/f'result-{phase}.json',result);return result

def generate_templates(rng):
    names=['cfg_'+uuid.UUID(int=rng.getrandbits(128)).hex[:8]+'.json' for _ in range(3)]
    profiles=['node_'+uuid.UUID(int=rng.getrandbits(128)).hex[:8] for _ in range(3)]
    goal=rng.randrange(45,75);templates=[];expected=[]
    for self_phase in range(2):
        rows={};configs={}
        for i in range(3):
            desired=rng.randrange(4,15);gain=rng.randrange(2,7);offset=goal-gain*desired
            rows[profiles[i]]=dict(config=names[i],gain=gain,offset=offset);configs[names[i]]={'limit':desired-2}
        templates.append(dict(manifest={'entry':profiles[0],'profiles':rows},configs=configs,
            schema={'version':domain.VERSION,'goal':goal,'setting_bounds':[0,100],'operation':'gain*limit+offset'}))
        expected.append(dict(targets=names,values=[(goal-rows[p]['offset'])//rows[p]['gain'] for p in profiles]))
    return templates,expected

def source_pins():
    names=['se666_core/grounded_native_input.py','se666_core/native_dependency_relation_v1.py',
        'se666_core/native_situated_awareness.py','se666_core/situated_entity.py','se666_core/entity_store.py',
        'se666_core/three_loop_entity.py','se666_core/observation_grounding.py',
        'scripts/run_dependency_awareness.py','scripts/run_native_qpre_learning.py',
        'tests/test_entity_cognition_layer.py','tests/test_local_entity_runtime.py','tests/test_native_dependency_relation_v1.py']
    pins={str(CORE/n):sha(CORE/n) for n in names}
    for directory in ('se666_core','se_core'):
        for p in (CORE/directory).rglob('*.py'):pins[str(p.resolve())]=sha(p)
    reference,_,_=dependencies()
    m=CORE.parents[2]
    for p in [m/'work/codex-vscode-research/operational-realization/engine/typed_composer.py',
        m/'work/codex-vscode-research/alpha-continuation/engine/durable_attempts.py',
        m/'work/se6-reference-continuity-v010-448349319aa1/SE6_Reference_Continuity_v0.1.0/PACKAGE_MANIFEST.json']:
        pins[str(p)]=sha(p)
    return pins

def install_world(root,templates):
    for name,template in zip(('projectA','projectB'),templates):
        path=root/name;path.mkdir();(path/'workload.py').write_text(WORKLOAD,encoding='utf-8')
        dump(path/'manifest.json',template['manifest']);dump(path/'goal.json',template['schema'])
        for n,v in template['configs'].items():dump(path/n,v)

def sequence(out,templates,arms,pins):
    from tests.test_entity_cognition_layer import _entity_store
    roots={};results={};reference,_,_=dependencies()
    for arm in arms:
        root=new_root();roots[arm]=str(root);store=_entity_store(root);entity=store.reconstruct().state
        engine=reference.canonical.core.SE(reference.canonical.core.SEState(identity=entity.identity.instance_id))
        dump(root/'native-genesis.json',dict(core_journal=engine.dumps(),core_head=None));dump(root/'source-pins.json',pins)
        dump(root/'development-authority.json',dict(scope='DISPOSABLE_DEVELOPMENT_ONLY_NOT_OWNER_AUTHENTICATION',
            entity_id=entity.identity.instance_id,max_effects=3,worlds=['projectA','projectB'],
            actions=['SET_INTEGER_EXISTING_CONFIG_LIMIT_0_TO_100'],source_fingerprint=digest(pins),
            authority_source='Explicit owner awareness task authorizes these disposable local effects; no production or network authority'))
        install_world(root,templates);results[arm]=[]
        for phase in (1,2,3):
            world='projectA' if phase<3 else 'projectB'
            if phase==2:
                m=read(root/world/'manifest.json');m['entry']=next(n for n in sorted(m['profiles']) if n!=m['entry'])
                (root/world/'manifest.json').write_text(json.dumps(m,sort_keys=True),encoding='utf-8')
            try:observed=child(root,'solve',phase,world,arm)
            except Exception as error:
                observed=dict(phase=phase,arm=arm,status='FAILED_NO_RETRY',error=str(error));results[arm].append(observed);break
            results[arm].append(observed)
    dump(out/'RUN_ROOTS.json',roots);dump(out/'SEQUENCE_RESULTS.json',results)
    return results

def run(out,development=False):
    out=Path(out).resolve();require(out.is_dir(),'EXISTING_TASK_OUTPUT_REQUIRED')
    if development:
        stage=out/('development-'+uuid.uuid4().hex[:8]);stage.mkdir();templates,expected=generate_templates(random.Random(23))
        results=sequence(stage,templates,['retained'],source_pins())
        ok=len(results['retained'])==3 and all(r.get('goal') for r in results['retained'])
        dump(stage/'DEVELOPMENT_RESULT.json',dict(status='PASS' if ok else 'FAIL',results=results,unblinded=True))
        return dict(status='PASS' if ok else 'FAIL',development=str(stage))
    frozen=out/'FROZEN_AWARENESS_PROTOCOL.json'
    require(not frozen.exists(),'ONE_FROZEN_EVALUATION_ONLY')
    require(any((p/'DEVELOPMENT_RESULT.json').exists() and read(p/'DEVELOPMENT_RESULT.json')['status']=='PASS'
        for p in out.glob('development-*')),'DEVELOPMENT_READINESS_REQUIRED')
    pins=source_pins()
    protocol=dict(version='dependency-awareness-frozen-evaluation-v1',source_pins=pins,operator=domain.VERSION,
        domain='Public affine CLI; manifest entry->profile->configuration; exact integer SET_INTEGER primitive',
        arms=['retained','memory-ablated','conventional'],phases=['seed','changed-manifest-entry','changed-actual-cwd'],
        primary_measures=['successful_behavior','wrong_target_mutations','failed_attempts','cold_restored_use'],
        secondary_measures=['tool_invocations','worker_wall_cpu','peak_python_heap'],
        limits={'effects_per_phase':1,'phases_per_arm':3,'child_deadline_seconds':75,'model_calls':0},
        isolation='Solver file/SQLite/network/subprocess audit; evaluator answers are outside permitted roots. Serialized raw files only; no expected action or patch input.',
        ablation='Remove only the retained source-bound dependency-edge memory capsule; keep raw observations, Mapper, actions, tools and budget.',
        authority='Explicit test-only disposable local action scope; not authenticated production owner or canonical adoption',
        mathematical_scope='Bounded development operator, not full owner-equation realization',
        generated_cases='Fresh only after this file is frozen; no tuning/rescoring on failure')
    dump(frozen,protocol)
    # No solver is invoked in generation. Private desired settings generate the
    # public goal relation and remain outside all solver input/effect roots.
    templates,expected=generate_templates(random.Random(int.from_bytes(os.urandom(16),'big')))
    private=out/'evaluator-only';private.mkdir();dump(private/'EXPECTED_PRIVATE.json',expected)
    probe=Path(tempfile.gettempdir())/'SE6_AWARENESS_EVALUATOR_ONLY';probe.mkdir(exist_ok=True)
    if not (probe/'not-solver-input.json').exists():dump(probe/'not-solver-input.json',{'guard':'Never delivered to a solver'})
    stage=out/'frozen-evaluation';stage.mkdir()
    results=sequence(stage,templates,protocol['arms'],pins)
    ok=all(len(rows)==3 and all(r.get('goal') for r in rows) for rows in results.values())
    changed=all(rows[0].get('selected_action')!=rows[1].get('selected_action') for rows in results.values() if len(rows)>1)
    self_ok=all(len(rows)==3 and rows[1].get('actual_root')!=rows[2].get('actual_root') for rows in results.values())
    result=dict(status='BOUNDED_OPERATIONAL_AWARENESS_DEMONSTRATED' if ok else 'FROZEN_EVALUATION_FAILED_PRESERVED',
        implementation='PASS',actual_effect_verification='PASS' if ok else 'FAIL',persistence='PASS' if ok else 'NOT_FULLY_VERIFIED',
        cold_restart='PASS' if ok else 'NOT_FULLY_VERIFIED',changed_relation='PASS' if ok and changed else 'FAIL',
        self_context='PASS' if ok and self_ok else 'NOT_FULLY_VERIFIED',comparisons=results,
        maintained_edges_consumed=results['retained'][1].get('maintained_edges_consumed',[]) if len(results['retained'])>1 else [],
        measured_advantage='NOT_ESTABLISHED',protocol_sha256=sha(frozen),source_pins=pins,
        production_changes=0,provider_calls=0,alpha_delta=0,
        limitations=['Bounded authored dependency operator and constrained primitives, not novel action discovery.',
            'Both controls may solve the same task; no general SE6 superiority is inferred.',
            'Python audit restricts this fixed trusted solver and tool surface, not an adversarial OS sandbox.',
            'Worker CPU/heap exclude child processes; complete CPU and monetary costs remain unknown.'])
    dump(out/'RESULT.json',result)
    with (out/'TRACE.jsonl').open('x',encoding='utf-8') as f:
        for arm,rows in results.items():
            for row in rows:f.write(json.dumps(dict(arm=arm,**{k:v for k,v in row.items() if k!='arm'}),sort_keys=True)+'\n')
    return dict(status=result['status'],measured_advantage=result['measured_advantage'])

def mode(args):
    root=check_root(Path(args.root));world=args.world;phase=args.phase
    if args.child=='observe':return observe(root,world)
    if args.child=='readback':
        receipt=read(root/f'renewal-{phase}.json');state=read(root/f'retained-{phase}.json');actual=EntityStore.for_testing(root/'entity.sqlite3').reconstruct().state
        require(receipt['state_sha256']==digest(state),'COLD_FILE_RENEWAL_PIN')
        return dict(state_sha256=digest(state),entity_state_id=actual.entity_state_id,pid=os.getpid())
    return worker(root,world,phase,args.arm)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--child');p.add_argument('--root');p.add_argument('--phase',type=int,default=1)
    p.add_argument('--world',default='projectA');p.add_argument('--arm',default='retained');p.add_argument('--out')
    p.add_argument('--development',action='store_true')
    a=p.parse_args();print(json.dumps(mode(a) if a.child else run(a.out,a.development),sort_keys=True))
