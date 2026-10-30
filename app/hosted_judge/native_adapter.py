"""Execute reviewed Competition native operations. No copied native engine."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from . import canonical_bridge
from .paired_review import prepare as prepare_pair

MAX_CHECKPOINT_BYTES=4*1024*1024
ALLOWED_ROUTES={'LINEAR_MATH','LINEAR_DERIVATION','RELATIONAL','HOST_BUSINESS','HOST_BUDGET','DIRECT_MODEL','UNSUPPORTED'}


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(value):return hashlib.sha256(value).hexdigest()


def public_relation(context):
    """Present relation values without native receipt, action or state identifiers."""
    value=json.loads(context);rows=[]
    for item in value['results']:
        consequence=item.get('observed_consequence');observed=json.loads(consequence['result']) if consequence and consequence['success'] else {}
        relation=observed.get('retained_assertion')
        public={'boundary_outcome':item['boundary']['outcome'],
            'verification_passed':item['verification']['passed'],'conflict':item['conflict'],
            'operation_succeeded':bool(consequence and consequence['success'])}
        if relation is not None:
            public['retained_assertion']={k:relation[k] for k in ('subject','predicate','value','epistemic_status')}
        elif 'value' in observed:
            public['recall']={k:observed[k] for k in ('value','epistemic_status')}
        rows.append(public)
    return json.dumps({'scope':'Task-local supplied relation values; no verified world facts.',
        'results':rows},ensure_ascii=False)


def validate_bundle(bundle,manifest,expected):
    root=Path(bundle).resolve();manifest=Path(manifest).resolve()
    if 'se6triad' in {p.lower() for p in root.parts}:raise ValueError('Production source is not a Competition bundle')
    raw=manifest.read_bytes()
    if not isinstance(expected,str) or len(expected)!=64 or sha(raw)!=expected:
        raise ValueError('Owner-supplied competition manifest hash mismatch')
    files=json.loads(raw)
    if not isinstance(files,dict) or not files:raise ValueError('Competition source manifest required')
    actual={p.relative_to(root).as_posix() for p in (root/'src').rglob('*.py')}
    declared={name.replace('\\','/') for name in files if name.replace('\\','/').startswith('src/') and name.endswith('.py')}
    if actual!=declared:raise ValueError('Exact reviewed Competition source set required')
    for name,wanted in files.items():
        path=(root/name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root) or sha(path.read_bytes())!=wanted:
            raise ValueError('Reviewed Competition source bytes mismatch')
    operator_root=root/'canonical_operators'
    if operator_root.exists():
        operator_files={p.relative_to(root).as_posix() for p in operator_root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        declared_operators={name.replace('\\','/') for name in files if name.replace('\\','/').startswith('canonical_operators/')}
        if operator_files!=declared_operators:raise ValueError('Exact reviewed canonical operator source set required')
    return root,sha(raw)


def execute_native(bundle,manifest,manifest_sha256,question,checkpoint,task_id,round_id,field_checkpoint=None,realization_prior=None,loop_options=None,expected_wrapper=None,*,revision=None,field_mode='enabled',toroidal_mode=None,toroidal_parameters=None,canonical_governance=True):
    """Called only in a fresh disposable process. No credentials consulted."""
    whole_start=time.perf_counter();whole_cpu=time.process_time()
    if type(canonical_governance) is not bool or (not canonical_governance and loop_options is not None):raise ValueError('Conventional control cannot claim canonical loop execution')
    if loop_options is not None:
        if expected_wrapper!=wrapper_signature():raise ValueError('Recursive loaded wrapper differs from frozen parent')
        if not isinstance(loop_options,dict) or set(loop_options)!={'field_mode','toroidal_parameters'}:raise ValueError('Recursive HOST options')
        field_mode=loop_options['field_mode'];toroidal_parameters=loop_options['toroidal_parameters']
    sys.dont_write_bytecode=True
    root,bundle_hash=validate_bundle(bundle,manifest,manifest_sha256)
    sys.path.insert(0,str(root))
    # Compilation from frozen bytes makes this worker's source attestation real.
    from src.workbench.runtime_revision import freeze_sources
    if revision is None:revision=freeze_sources(root)
    elif Path(revision.root)!=root or not revision.public()['disk_matches_loaded']:raise ValueError('Existing frozen revision differs')
    import socket,sqlite3
    def denied(*args,**kwargs):raise ValueError('Hosted judge forbids provider, database and outbound network operations')
    socket.socket.connect=denied;socket.create_connection=denied;socket.getaddrinfo=denied;sqlite3.connect=denied
    socket.socket.connect_ex=denied;socket.socket.sendto=denied
    from src.workbench import provider_router,transport
    provider_router.credential_status=lambda settings:False
    provider_router.NebiusTransport.request=denied
    transport.ResponsesTransport.request=denied
    from src.workbench.auto_intake import AutoIntake
    from src.workbench.integrations import Integrations
    from src.workbench.native_core import NativeCore
    from src.workbench.native_mathematics import NativeMathematics
    from src.workbench.core_revisions import CANONICAL
    from src.workbench.orchestration import Orchestrator
    from src.workbench.config import Settings
    from src.workbench.models import ModelSettings,PairSettings
    projection=type('UnavailableProjection',(),{'blocker':'Hosted judge excludes historical fixture projection'})()
    class DisabledMirror:
        def capabilities(self):return {'id':'verified_mirror','connected':False,'blocker':'Hosted judge does not expose mirror fixtures'}
        def validate(self,*args):raise ValueError('Mirror fixture route unavailable in hosted judge')
    # Reuse canonical supplied adapters. No legacy/mirror fixture execution.
    engine=Orchestrator(AutoIntake(Integrations(projection,NativeCore(revision=CANONICAL),
        mirror_adapter=DisabledMirror(),math_adapter=NativeMathematics(revision=CANONICAL))))
    from .admission_memo import install as install_admission_memo
    memo=install_admission_memo(engine.auto,revision)
    presentation=None
    try:
        from .provisional_math_presentation import PresentationInvocation,formatter_policy
        from src.workbench.core_revisions import load_core
        presentation=PresentationInvocation(engine.auto,load_core(),formatter_policy(type(engine.auto)),lambda:memo._guard(None))
        model=ModelSettings();settings=Settings(PairSettings('matched',model,model),
            integration='auto',core_revision=CANONICAL,context_policy='audit_v3')
        before=deepcopy(checkpoint)
        plan=engine.plan(question,settings,[],False,checkpoint)
        if any(node['route'] not in ALLOWED_ROUTES for node in plan['nodes']):
            raise ValueError('This hosted demonstration supports native math, task-local relations and host business arithmetic only')
        canonical_context=canonical_bridge.begin(root,question,plan,checkpoint,field_checkpoint,field_mode=field_mode,toroidal_mode=toroidal_mode,toroidal_parameters=toroidal_parameters) if canonical_governance else None
        cp,out,answer=engine.advance(task_id,round_id,question,checkpoint,plan)
        raw_answer=answer
        if checkpoint!=before:raise ValueError('Native input checkpoint mutated')
        if out['production_connected'] or out['model_output_ingested']:
            raise ValueError('Hosted native boundary violation')
        if canonical_context is not None:
            canonical_context['presentation_captures']=presentation.captures
        canonical_public,canonical_attestation=canonical_bridge.finish(canonical_context,engine,task_id,cp,out,answer)
        completed_audit=(canonical_context or {}).get('completed_local_audit')
        if not canonical_governance and out['receipts']:
            completed_audit={}
            if not canonical_bridge.verify_native_checkpoint(engine,task_id,cp,out,answer,before=before,audit_sink=completed_audit,presentation_captures=presentation.captures):raise ValueError('Conventional tool evidence did not replay')
        if completed_audit:
            local=canonical_bridge.read_completed_audit(completed_audit,engine,task_id,before,cp,out,answer)
        else:
            local=engine.score_local({'id':task_id,'orchestration_checkpoint':cp,'rounds':[{
                'auto_execution':out,'lanes':{'se6':{'response':answer,'response_sha256':sha(answer.encode())}}}]})
        loop_proposal=None
        if loop_options is not None:
            tor=(canonical_attestation or {}).get('toroidal_realization')
            if tor and tor['feedback']['native_replay_passed'] and tor['feedback']['navigation']['status']=='HOST_VERIFIED_NAVIGATION' and tor['prepared']['typed']['selected_ids']:
                from .realization_loop import prepare_candidates
                loop_proposal=prepare_candidates(tor['prepared'],tor['feedback'],out,cp,realization_prior)
        if len(encode(cp))>MAX_CHECKPOINT_BYTES:raise ValueError('Hosted checkpoint memory cap reached')
        revision_state=revision.public()
        safe_nodes=[]
        for node in out['nodes']:
            shown=node['result'].get('answer') if node['result'] else None
            if node['route']=='RELATIONAL' and node['status']=='COMPLETE':
                context=node['result']['context'];shown=public_relation(context)
                answer=answer.replace(context,shown)
            safe_nodes.append({'id':node['id'],'route':node['route'],'status':node['status'],
                'knowledge_status':node.get('knowledge_status'),'answer':shown,'blocker':node.get('blocker')})
        summary={'answer':answer,'provider_calls':0,
            'production_connected':False,'native_receipt_count':len(out['receipts']),
            'receipts':[{'verification_passed':r['verification']['passed'],
                'boundary_outcome':r['boundary']['outcome']} for r in out['receipts']],
            'native_verification':'PINNED_COMPETITION_CORE_AND_LOCAL_CERTIFICATES_REPLAYED',
            'nodes':safe_nodes,
            'correction_state':{'current_constraint_count':len(out['correction_state']['current_constraints']),
                'invalidated_deduction_count':len(out['correction_state']['invalidated_deductions']),
                'active_deduction_count':len(out['correction_state']['active_deductions']),
                'supplied_signature_verified':False} if out['correction_state'] else None,
            'business_views':out['business']['views'] if out['business'] else None,
            'host_calculations_created':out['host_calculations_created'],
            'local_verification':local,'native_seconds':out['local_seconds'],
            'scope':'Real bounded Competition native receipts; business calculations are HOST operations. Conditional input facts; no paid model/baseline, world truth, production or external actions.'}
        pair_packet,pair_public=prepare_pair(question,answer)
        if canonical_public is not None:
            canonical_public['resources']['whole_execute_native_wall_seconds']=time.perf_counter()-whole_start
            canonical_public['resources']['whole_execute_native_cpu_seconds']=time.process_time()-whole_cpu
            summary['canonical']=canonical_public
        else:
            summary['native_resources']={'whole_execute_native_wall_seconds':time.perf_counter()-whole_start,
                'whole_execute_native_cpu_seconds':time.process_time()-whole_cpu,'provider_calls':0,
                'canonical_governance':canonical_governance,'local_monetary_cost_usd':None}
        summary['comparison']=pair_public
        summary['host_admission_reuse']={k:v for k,v in memo.public().items() if k not in ('classifier_sha256','source_hashes_sha256','revision_sha256')}
        if len(encode(summary))>65536:raise ValueError('Hosted result display cap reached')
        field_state=((canonical_attestation or {}).get('field_candidate') or {}).get('feedback',{}).get('checkpoint')
        relational_state=((canonical_attestation or {}).get('field_realization') or {}).get('feedback',{}).get('checkpoint')
        if field_state is not None and relational_state is not None:
            field_state=deepcopy(field_state);field_state['relational_checkpoint']=relational_state
        toroidal_state=((canonical_attestation or {}).get('toroidal_realization') or {}).get('feedback',{}).get('checkpoint')
        if toroidal_state is not None:
            field_state=deepcopy(field_state) if field_state is not None else {}
            field_state['toroidal_checkpoint']=toroidal_state
            navigation_state=(((canonical_attestation or {}).get('toroidal_realization') or {}).get('feedback',{}).get('navigation') or {}).get('checkpoint')
            if navigation_state is not None:field_state['navigation_checkpoint']=navigation_state
        return {'checkpoint':cp,'field_checkpoint':field_state,'public':summary,'operations':out['local_operations'],
            'attestation':{'source_hashes':out['source_hashes'],'bundle_manifest_sha256':bundle_hash,
                'loaded_source_revision_sha256':revision_state['source_manifest_sha256'],
                'compiled_native_modules':{name:row for name,row in revision_state['compiled_modules'].items() if '/canonical_core_vendor/' in '/'+row['path']},
                'correction_state':out['correction_state'],
                'native_receipts':out['receipts'],'realization_traces':out['realization_traces'],
                'plan':plan,'native_operations':out['local_operations'],
                'canonical':canonical_attestation,'prepared_pair':pair_packet,
                'raw_execution_out':out,'raw_answer':raw_answer,'realization_loop_proposal':loop_proposal,
                'host_admission_reuse':memo.public(),'admission_helper_fingerprints':memo.helper_fingerprints(),
                **({'wrapper_signature':expected_wrapper if loop_options is not None else wrapper_signature(),
                    'canonical_governance':canonical_governance} if loop_options is not None or not canonical_governance else {})}}
    finally:
        try:
            if presentation is not None:presentation.close()
        finally:
            memo.close()


def wrapper_signature():
    from . import realization_loop,recursive_controller,durable_sessions
    from tools.code_attestation_v7 import fingerprint
    from . import answer_contract,typed_native,typed_answer_state,typed_controls,admission_memo,provisional_math_presentation
    modules=(sys.modules[__name__],realization_loop,recursive_controller,durable_sessions,
        answer_contract,typed_native,typed_answer_state,typed_controls,admission_memo,canonical_bridge,provisional_math_presentation)
    return {'modules':{Path(m.__file__).name:sha(Path(m.__file__).read_bytes()) for m in modules},
        'functions':{name:fingerprint(fn) for name,fn in {'execute_native':execute_native,'verify_realization':verify_realization,
            'controller_execute':recursive_controller.execute,'controller_restore':recursive_controller.restore,
            'loop_prepare':realization_loop.prepare_candidates,'loop_act':realization_loop.act_verify_assimilate,
            'loop_finalize':realization_loop.finalize_verified,'loop_load':realization_loop.load_restore,
            'sessions_save':durable_sessions.DurableSessions.save,'sessions_restore':durable_sessions.DurableSessions.restore,
            'typed_prepare':typed_native.prepare,'typed_finalize':typed_native.finalize,
            'answer_verify':answer_contract.verify_user_answer,'answer_decode':answer_contract.decode_final,
            'typed_append':typed_answer_state.append,'typed_restore':typed_answer_state.verify_retained,
            'typed_native_input':typed_controls.native_input,'selected_tool_context':typed_controls.selected_context,
            'admission_install':admission_memo.install,'admission_init':admission_memo.ClassificationMemo.__init__,
            'admission_classify':admission_memo.ClassificationMemo.classify,'admission_guard':admission_memo.ClassificationMemo._guard,
            'admission_same_callable':admission_memo._same_callable,'admission_close':admission_memo.ClassificationMemo.close,
            'completed_audit_binding':canonical_bridge.completed_audit_binding,'read_completed_audit':canonical_bridge.read_completed_audit,
            'completed_manifest_pin':canonical_bridge.completed_audit_manifest_pin,
            'checkpoint_verify':canonical_bridge.verify_native_checkpoint,'canonical_finish':canonical_bridge.finish,
            'presentation_init':provisional_math_presentation.PresentationInvocation.__init__,
            'presentation_close':provisional_math_presentation.PresentationInvocation.close,
            'presentation_policy':provisional_math_presentation.formatter_policy,
            'presentation_decode':provisional_math_presentation.decode_state,
            'presentation_format':provisional_math_presentation.provisional_math,
            'presentation_semantics':provisional_math_presentation.semantic_view,
            'presentation_verify':provisional_math_presentation.verify_presentations}.items()}}


def verify_realization(bundle,manifest,pin,task_id,before,result,loop_state=None,observation=None):
    """Fresh source-pinned verification/typed finalization; never advances a task."""
    start=time.perf_counter();cpu=time.process_time();sys.dont_write_bytecode=True
    root,bundle_hash=validate_bundle(bundle,manifest,pin);sys.path.insert(0,str(root))
    from src.workbench.runtime_revision import freeze_sources
    revision=freeze_sources(root)
    import socket,sqlite3
    def deny(*args,**kwargs):raise ValueError('Recursive proof worker has no network/database authority')
    socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.socket.sendto=deny
    socket.create_connection=deny;socket.getaddrinfo=deny;sqlite3.connect=deny
    from src.workbench.orchestration import Orchestrator
    from src.workbench.core_revisions import load_core
    from . import realization_loop as loop
    att=result['attestation'];out=att['raw_execution_out'];cp=result['checkpoint']
    if att.get('wrapper_signature')!=wrapper_signature():raise ValueError('Recursive proof wrapper source/code differs')
    verified=canonical_bridge.verify_native_checkpoint(Orchestrator(None),task_id,cp,out,att['raw_answer'],before=before)
    if not verified:raise ValueError('Recursive proof requires actual native evidence')
    canonical_bridge.load_bridge(root)
    proposal=att.get('realization_loop_proposal')
    if proposal is not None:
        tor=att['canonical']['toroidal_realization']
        from .toroidal_field_oracle import verify_result
        from .navigation_oracle import verify_navigation
        verify_result(tor['prepared']['result'])
        t=tor['prepared'];verify_navigation(t['environment'],t['navigation'],t['navigation_prior'],t['result'],t['plan'],t['actual_plan_mapping'])
        loop.verify_prepared(proposal,out,cp,t,tor['feedback'],proposal['prior_state'])
    typed=None
    if loop_state is not None:
        loop.verify_restored_canonical(loop_state)
        if loop_state['native_checkpoint_identity']==cp['checkpoint_hash']:loop.renew(loop_state,cp)
        elif proposal is None or loop_state!=proposal['prior_state']:raise ValueError('Recursive prior state substitution')
    if observation is not None:
        if proposal is None:raise ValueError('Recursive finalization requires proposal')
        typed=loop.finalize_verified(proposal,observation,proposal['prior_state'])
    # The renewed goal is discovered from actually restored, still-active
    # conditional proof state. No fixture answer or owner adapter is supplied.
    renewal=None;auto=Orchestrator(None)._restore(cp,task_id)
    if auto.get('math'):
        retained=auto['math'];api=load_core();state=api.SE.restore(retained['journal'],expected_head=retained['head']).state
        preferred=[n['result'].get('deduction_reference') for n in reversed(out['nodes']) if n['status']=='COMPLETE' and n['route'] in ('LINEAR_MATH','LINEAR_DERIVATION')]
        if proposal is not None:
            selected=proposal['artifact']['selected_id']
            selected_node=next(n for n in out['nodes'] if n['id']==selected)
            if selected_node['result'].get('deduction_reference'):preferred.insert(0,selected_node['result']['deduction_reference'])
        deductions=list(state.active_deductions)
        deductions.sort(key=lambda d:(preferred.index(d.reference) if d.reference in preferred else len(preferred),d.reference))
        import re
        for d in deductions:
            if len(d.equation.coefficients)==1:
                name=d.equation.coefficients[0][0]
                if re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,31}',name):renewal='Derive a relation involving '+name+'.';break
    if renewal is None and auto.get('relations'):
        import re
        for receipt in reversed(out['receipts']):
            consequence=receipt.get('observed_consequence') or {}
            if not consequence.get('success'):continue
            value=json.loads(consequence['result']).get('retained_assertion')
            if value and all(isinstance(value.get(k),str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,31}',value[k]) for k in ('subject','predicate')):
                renewal="What is "+value['subject']+"'s "+value['predicate']+"?";break
    return {'verified':True,'bundle_manifest_sha256':bundle_hash,'loaded_revision':revision.public()['source_manifest_sha256'],
        'native_receipts':len(out['receipts']),'checkpoint_sha256':loop.digest(cp),'typed_finalization':typed,
        'renewal_question':renewal,'resources':{'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'provider_calls':0}}
