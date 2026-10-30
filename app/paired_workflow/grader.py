"""Independent post-action evaluation; never part of a solver request/tool."""
from fractions import Fraction
import hashlib,json,time
from .protocol import digest,require
from .tools import checked_files,cli_readback

def grade_stage(public_root,before_files,proposal,*,witness_runner=None,simulation=False):
    """Fresh actual CLI consequence plus independent target/untouched-file check.

    The private expected interpretation is constructed ONLY after the model's
    action/abstention was committed. It is never supplied to either arm.
    """
    require(not simulation or witness_runner is not None,'PILOT_SIMULATED_GRADER_WITNESS_REQUIRED')
    start,cpu=time.perf_counter(),time.process_time()
    before={k:(v.encode() if type(v) is str else v) for k,v in before_files.items()}
    manifest=json.loads(before['manifest.json']);goal=json.loads(before['goal.json'])['goal']
    profile=manifest['profiles'][manifest['entry']]
    needed=Fraction(goal-profile['offset'],profile['gain'])
    require(needed.denominator==1 and 0<=needed<=100,'PILOT_GENERATOR_UNSUPPORTED_ORACLE')
    after=checked_files(public_root)
    changed=sorted(k for k in before if before[k]!=after[k])
    witness=(witness_runner or cli_readback)(public_root)
    require(witness['source_hashes']=={k:hashlib.sha256(v).hexdigest() for k,v in after.items()},'PILOT_GRADER_WITNESS_SOURCE')
    actual_goal=witness['returncode']==0 and witness['output']==goal
    wrong_target=any(k!=profile['config'] for k in changed)
    intended_value=json.loads(after[profile['config']])['limit']==int(needed)
    unchanged_contract=all(after[k]==before[k] for k in before if k!=profile['config'])
    if proposal and proposal.get('type')=='act':
        intended_action=proposal['path']==profile['config'] and proposal['value']==int(needed)
        success=actual_goal and intended_value and unchanged_contract and intended_action and changed==[profile['config']]
    else:success=actual_goal and not changed
    result=dict(status='INDEPENDENTLY_VERIFIED' if success else 'NOT_VERIFIED',
        assessment_status='INDEPENDENTLY_ASSESSED',goal=bool(success),task_outcome='GOAL_REACHED' if success else 'GOAL_NOT_REACHED',
        actual_cli_goal=actual_goal,wrong_target_edits=int(wrong_target),changed_files=changed,
        prediction_correct=(proposal['prediction']['expected_output']==witness['output']) if proposal and proposal.get('type')=='act' else None,
        public_contract_unchanged=unchanged_contract,independent_cli_witness=witness,
        private_expected_target_disclosed_to_solver=False,
        record_kind='SIMULATED_TEST_ONLY' if simulation else 'ACTUAL_LOCAL_CONSEQUENCE',
        cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-start)
    result['verdict_sha256']=digest(result)
    return result

def public_verdict(verdict):
    """No private expected action or absolute working directory in UI export."""
    witness={k:v for k,v in verdict['independent_cli_witness'].items() if k!='cwd'}
    public={k:v for k,v in verdict.items() if k!='verdict_sha256'}
    public.update(independent_cli_witness=witness,private_verdict_sha256=verdict['verdict_sha256'])
    public['public_verdict_sha256']=digest(public)
    return public
