"""Isolated fixed Native stage; no provider calls or evaluator input.

Reuse the exact existing worker with additive untrusted-proposal and shared
action-tool ports. Default historical runner behavior is unchanged.
"""
from pathlib import Path
import argparse,json,os,sys

APP=Path(__file__).resolve().parents[1]
CORE=APP/'awareness_native/work/qpre-calibration-integration-20261026/dev'
sys.path.insert(0,str(APP));sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
from scripts import run_dependency_awareness as original
from scripts.run_native_qpre_learning import dependencies,new_root,check_root,read,write_once
from hosted_judge.model_native_workflow import proposal_gate,require_exact_selected_action,validate_proposal
from paired_workflow.tools import ProjectTools
from paired_workflow.protocol import digest as shared_digest


def initialize():
    from tests.test_entity_cognition_layer import _entity_store
    root=new_root();store=_entity_store(root);entity=store.reconstruct().state
    reference,_,_=dependencies()
    engine=reference.canonical.core.SE(reference.canonical.core.SEState(identity=entity.identity.instance_id))
    write_once(root/'native-genesis.json',dict(core_journal=engine.dumps(),core_head=None))
    write_once(root/'source-pins.json',original.source_pins())
    write_once(root/'development-authority.json',dict(scope='DISPOSABLE_DEVELOPMENT_ONLY_NOT_OWNER_AUTHENTICATION',
        entity_id=entity.identity.instance_id,max_effects=2,worlds=['projectA','projectB'],
        actions=['SET_INTEGER_EXISTING_CONFIG_LIMIT_0_TO_100'],
        authority_source='Explicit isolated model-workflow task; two stages, one effect per stage; no production/network/provider authority'))
    return dict(status='INITIALIZED_DISPOSABLE_NATIVE',root=str(root),entity_id=entity.identity.instance_id,
        production=False,world_effects=0)


def run(root,world,phase,proposal):
    root=check_root(root);proposal=validate_proposal(proposal)
    if world not in ('projectA','projectB') or phase not in (1,2):raise ValueError('MODEL_STAGE_SCOPE')
    # Import all shared host tooling before the original worker installs its
    # fixed file/database/subprocess boundary. No model call is imported here.
    tools=ProjectTools(root/world,root_alias=world,state_root=root/'paired-tool-state',stage_id='native-'+str(phase),
        effect_admission=lambda _: (_ for _ in ()).throw(ValueError('UNBOUND_NATIVE_ADMISSION')))
    def execute(pending,permission):
        require_exact_selected_action(proposal,pending['action'])
        def admission(request):
            permission(pending)  # actual existing Native current authority/source checks
            if (request['stage_id']!=tools.stage_id or request['root']!=str((root/world).resolve())
                    or request['proposal']!=proposal):raise ValueError('MODEL_SHARED_ACTION_BINDING')
            observation=original.observe(root,world)
            if request['source_hashes']!=observation['file_hashes']:raise ValueError('MODEL_SHARED_ACTION_STALE')
            return dict(status='ADMITTED',stage_id=tools.stage_id,max_effects=1,
                root_sha256=shared_digest(str((root/world).resolve())),
                authority_source='EXISTING_NATIVE_CURRENT_PERMISSION_PORT',
                native_pending_sha256=original.digest(pending),world_scope='DISPOSABLE_LOCAL_PROJECT_ONLY')
        tools.effect_admission=admission
        return tools.apply_action(proposal)
    os.chdir(root/world)
    result=original.worker(root,world,phase,'retained',model_proposal=proposal,
        proposal_gate=proposal_gate,action_executor=execute,allow_missing_prior=True)
    result.update(model_role='UNTRUSTED_REPAIR_PROPOSER',native_role='SOURCE_BOUND_VALIDATOR_AND_SELECTOR',
        fallback_used=False,shared_action_tool='paired_workflow.tools.ProjectTools.apply_action')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--operation',choices=['initialize','run'],required=True)
    parser.add_argument('--root');parser.add_argument('--world');parser.add_argument('--phase',type=int)
    args=parser.parse_args()
    if args.operation=='initialize':value=initialize()
    else:value=run(Path(args.root),args.world,args.phase,json.loads(sys.stdin.read())['proposal'])
    print(json.dumps(value,sort_keys=True))
