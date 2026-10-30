"""The same bounded public project tools for both arms, with no shell tool."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import hashlib,json,os,re,subprocess,sys,time
from .protocol import NATIVE_DOMAIN,directive,digest,encode,require,sha
from .tasks import WORKLOAD,exclusive

def _plain_file(path):
    require(path.is_file() and not path.is_symlink()
        and not (hasattr(path,'is_junction') and path.is_junction())
        and path.stat().st_size<=4096,'PILOT_PUBLIC_FILE_BOUND')
    return path.read_bytes()

def checked_files(root):
    """No arbitrary read: exact known public manifest/goal/config/script set."""
    raw=Path(root)
    require(not raw.is_symlink() and not (hasattr(raw,'is_junction') and raw.is_junction()),'PILOT_PUBLIC_ROOT_REPARSE')
    root=raw.resolve(strict=True);require(root.is_dir(),'PILOT_PUBLIC_ROOT')
    manifest=json.loads(_plain_file(root/'manifest.json'))
    require(type(manifest) is dict and set(manifest)=={'entry','profiles'} and type(manifest['profiles']) is dict
        and 2<=len(manifest['profiles'])<=8 and manifest['entry'] in manifest['profiles'],'PILOT_PUBLIC_MANIFEST')
    configs=[]
    for name,row in manifest['profiles'].items():
        require(type(name) is str and re.fullmatch('[A-Za-z0-9_-]{1,80}',name) is not None
            and type(row) is dict and set(row)=={'config','gain','offset'}
            and type(row['gain']) is int and 1<=row['gain']<=16
            and type(row['offset']) is int and abs(row['offset'])<=100,'PILOT_PUBLIC_PROFILE')
        path=row['config']
        require(type(path) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.json',path) is not None
            and path not in {'manifest.json','goal.json'},'PILOT_PUBLIC_CONFIG_PATH')
        configs.append(path)
    require(len(set(configs))==len(configs),'PILOT_PUBLIC_CONFIG_ALIAS')
    allowed={'manifest.json','goal.json','workload.py',*configs}
    require({p.name for p in root.iterdir()}==allowed,'PILOT_UNEXPECTED_PUBLIC_FILE')
    files={name:_plain_file(root/name) for name in sorted(allowed)}
    require(sum(map(len,files.values()))<=16384 and files['workload.py']==WORKLOAD.encode(),'PILOT_PUBLIC_SOURCE_PIN')
    goal=json.loads(files['goal.json'])
    require(type(goal) is dict and set(goal)=={'version','goal','setting_bounds','operation'}
        and goal['version']==NATIVE_DOMAIN and type(goal['goal']) is int
        and goal['setting_bounds']==[0,100] and goal['operation']=='gain*limit+offset','PILOT_PUBLIC_GOAL_NO_PRIVATE_FIELDS')
    for name in configs:
        config=json.loads(files[name]);require(type(config) is dict and set(config)=={'limit'}
            and type(config['limit']) is int and 0<=config['limit']<=100,'PILOT_PUBLIC_CONFIG_VALUE')
    return files

def cli_readback(root):
    """Execute only the frozen public CLI; no model-generated code or paths."""
    root=Path(root).resolve(strict=True);before=checked_files(root)
    environment={key:os.environ[key] for key in ('SYSTEMROOT','WINDIR','TEMP','TMP') if key in os.environ}
    environment.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    wall,cpu=time.perf_counter(),time.process_time()
    result=subprocess.run([sys.executable,'-I','-B',str(root/'workload.py')],cwd=root,
        capture_output=True,text=True,timeout=5,env=environment,shell=False)
    require(result.returncode in (0,3) and len(result.stdout)<=4096 and not result.stderr,'PILOT_CLI_READBACK_FAILED')
    value=json.loads(result.stdout);require(set(value)=={'output','cwd'} and type(value['output']) is int
        and value['cwd']==str(root),'PILOT_CLI_CONTEXT_BINDING')
    after=checked_files(root);require(after==before,'PILOT_READ_ONLY_CLI_MUTATED_PROJECT')
    return dict(output=value['output'],returncode=result.returncode,cwd=str(root),
        source_hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in before.items()},
        host_cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,child_cpu_seconds=None)

class ProjectTools:
    """Host tools expose public JSON only. No evaluator object is accepted."""
    def __init__(self,public_root,*,root_alias,state_root,stage_id,effect_admission,readback=None,simulation=False):
        self.root=Path(public_root).resolve(strict=True)
        self.root_alias=root_alias;self.state_root=Path(state_root).resolve(strict=False)
        require(root_alias==self.root.name and root_alias in {'projectA','projectB'},'PILOT_ROOT_ALIAS')
        require(type(stage_id) is str and re.fullmatch('[A-Za-z0-9_-]{1,120}',stage_id) is not None,'PILOT_STAGE_ID')
        require(not self.state_root.is_relative_to(self.root),'PILOT_STATE_NOT_PUBLIC_PROJECT')
        self.stage_id=stage_id;self.effect_admission=effect_admission
        require(not simulation or readback is not None,'PILOT_SIMULATION_TRANSPORT_REQUIRED')
        require(simulation or readback is None or readback is cli_readback,'PILOT_TEST_WITNESS_CANNOT_BECOME_ACTUAL')
        self._readback_impl=readback or cli_readback;self.simulation=simulation
        self.events=[];self.inspected=[];self.act_proposals=0
        self.cli_processes=0
        self.effect_attempt_state='NOT_ATTEMPTED'
        self.initial_files=checked_files(self.root)
        self._completion_witness=None

    def readback(self,root):
        self.cli_processes+=1
        return self._readback_impl(root)

    def observe(self):
        files=checked_files(self.root);outcome=self.readback(self.root)
        require(outcome['source_hashes']=={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},'PILOT_OBSERVATION_WITNESS_BINDING')
        self._remember_completion_witness(outcome,files)
        return dict(manifest=json.loads(files['manifest.json']),schema=json.loads(files['goal.json']),
            configs={k:json.loads(v) for k,v in files.items() if k.endswith('.json') and k not in {'manifest.json','goal.json'}},
            context=dict(cwd=str(self.root),observed_root=str(self.root)),
            failure={'output':outcome['output'],'returncode':outcome['returncode']},
            file_hashes=outcome['source_hashes'])

    def _remember_completion_witness(self,outcome,files):
        """Only this stage's actual allowlisted CLI read can supply completion.

        Retained model notes are never loaded here. In this frozen deterministic
        CLI domain, exact current file hashes, goal and working root establish
        whether an existing observation can still be used without a repeat read.
        """
        hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}
        require(type(outcome) is dict and outcome.get('cwd')==str(self.root)
            and outcome.get('source_hashes')==hashes and type(outcome.get('output')) is int
            and type(outcome.get('returncode')) is int and outcome['returncode'] in (0,3),
            'PILOT_COMPLETION_WITNESS_BINDING')
        self._completion_witness=dict(root=str(self.root),public_goal=json.loads(files['goal.json'])['goal'],
            witness=deepcopy(outcome))

    def check_completion(self,*,allow_observation=True):
        """Shared, non-authorizing finish check; no repair or target is supplied.

        A current witness is reused even when it reports failure. Missing or
        stale evidence gets at most one existing run_cli observation when the
        caller has remaining time/tool authority. No World action is performed.
        """
        require(type(allow_observation) is bool,'PILOT_COMPLETION_OBSERVATION_POLICY')
        def current():
            files=checked_files(self.root);goal=json.loads(files['goal.json'])['goal']
            hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()};saved=self._completion_witness
            valid=(type(saved) is dict and saved.get('root')==str(self.root) and saved.get('public_goal')==goal
                and type(saved.get('witness')) is dict and saved['witness'].get('cwd')==str(self.root)
                and saved['witness'].get('source_hashes')==hashes)
            return goal,hashes,saved['witness'] if valid else None
        goal,hashes,witness=current();observed=False
        if witness is None and allow_observation:
            self.execute_non_effect({'type':'run_cli'});observed=True
            goal,hashes,witness=current()
        if witness is None:
            return dict(status='INCOMPLETE_CURRENT_EVIDENCE_REQUIRED',goal=False,
                reason_codes=['CURRENT_SOURCE_ROOT_BOUND_GOAL_WITNESS_REQUIRED'],
                root_alias=self.root_alias,public_goal=goal,current_output=None,
                source_hashes=hashes,observation_performed=observed,evidence_sha256=None,
                record_kind='SIMULATED_TEST_ONLY' if self.simulation else 'ACTUAL_LOCAL_TASK')
        reached=witness['returncode']==0 and witness['output']==goal
        return dict(status='CURRENT_GOAL_VERIFIED' if reached else 'CURRENT_GOAL_NOT_REACHED',goal=reached,
            reason_codes=[] if reached else ['CURRENT_CLI_OUTPUT_DOES_NOT_MEET_PUBLIC_GOAL'],
            root_alias=self.root_alias,public_goal=goal,current_output=witness['output'],
            returncode=witness['returncode'],source_hashes=hashes,observation_performed=observed,
            evidence_sha256=digest(self._completion_witness),
            record_kind='SIMULATED_TEST_ONLY' if self.simulation else 'ACTUAL_LOCAL_TASK')

    def public_context(self):
        obs=self.observe()
        return dict(root_alias=self.root_alias,public_goal=obs['schema']['goal'],
            developer_request='Diagnose and repair the active CLI configuration so its output meets the public goal. Inspect current dependencies and working context before acting.',
            initial_cli=obs['failure'],allowed_files=sorted(obs['file_hashes']),
            supported_operations=['inspect','calculate','run_cli','act','finish'],
            private_evaluator_access='DENIED',record_kind='SIMULATED_TEST_ONLY' if self.simulation else 'ACTUAL_LOCAL_TASK')

    def read_file(self,name):
        files=checked_files(self.root)
        require(type(name) is str and name in files,'PILOT_FILE_READ_DENIED')
        return files[name].decode('utf-8')

    def inspect(self,target):
        files=checked_files(self.root)
        values=dict(manifest=json.loads(files['manifest.json']),goal=json.loads(files['goal.json']),
            configs={k:json.loads(v) for k,v in files.items() if k.endswith('.json') and k not in {'manifest.json','goal.json'}},
            context={'root_alias':self.root_alias,'allowed_files':sorted(files)})
        self.inspected.append(target)
        return values if target=='project' else values[target]

    def execute_non_effect(self,command):
        command=directive(command);kind=command['type'];wall,cpu=time.perf_counter(),time.process_time()
        require(kind in {'inspect','calculate','run_cli','finish'},'PILOT_EFFECT_REQUIRES_STAGE_ADAPTER')
        if kind=='inspect':value=self.inspect(command['target'])
        elif kind=='calculate':
            solution=Fraction(command['goal']-command['offset'],command['gain'])
            value=dict(numerator=solution.numerator,denominator=solution.denominator,
                integer_solution=solution.denominator==1,within_setting_bounds=0<=solution<=100,
                scope='COMMON_EXACT_ARITHMETIC_NOT_TARGET_SELECTION_OR_WORLD_EVIDENCE')
        elif kind=='run_cli':
            observed=self.readback(self.root)
            self._remember_completion_witness(observed,checked_files(self.root))
            value={k:v for k,v in observed.items() if k!='cwd'};value['root_alias']=self.root_alias
        else:value=dict(status='ABSTAINED',notes=command['notes'])
        self.events.append(dict(command=deepcopy(command),observation=deepcopy(value),
            cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall))
        return value

    def apply_action(self,proposal):
        """One atomic, current-file-bound setting edit; not a success verdict."""
        proposal=directive(proposal);require(proposal['type']=='act','PILOT_ACTION_REQUIRED')
        self.act_proposals+=1;require(self.act_proposals==1,'PILOT_ONE_ACTION_PROPOSAL')
        require(not self.simulation,'PILOT_SIMULATED_TRANSPORT_CANNOT_WRITE_WORLD')
        files=checked_files(self.root);require(proposal['path'] in files and proposal['path'] not in {'manifest.json','goal.json','workload.py'},'PILOT_ACTION_PUBLIC_TARGET')
        require(callable(self.effect_admission),'PILOT_EFFECT_ADMISSION_REQUIRED')
        admission=self.effect_admission(dict(stage_id=self.stage_id,root=str(self.root),proposal=deepcopy(proposal),
            source_hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}))
        require(type(admission) is dict and admission.get('status')=='ADMITTED'
            and admission.get('stage_id')==self.stage_id and admission.get('max_effects')==1
            and admission.get('root_sha256')==digest(str(self.root)),'PILOT_EXACT_EFFECT_ADMISSION')
        claim=self.state_root/('effect-claim-'+self.stage_id+'.json')
        exclusive(claim,dict(status='EFFECT_ATTEMPTED_OUTCOME_NOT_YET_VERIFIED',proposal=proposal,
            source_hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},admission=admission))
        self.effect_attempt_state='CLAIMED_OUTCOME_UNKNOWN'
        require(checked_files(self.root)==files,'PILOT_PRE_EFFECT_STALE_SOURCE')
        target=self.root/proposal['path'];temporary=self.root/('.effect-'+os.urandom(8).hex()+'.tmp')
        with temporary.open('xb') as stream:
            stream.write(encode({'limit':proposal['value']}));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target)
        after=checked_files(self.root)
        receipt=dict(status='APPLIED_UNVERIFIED',proposal=deepcopy(proposal),before_hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
            after_hashes={k:hashlib.sha256(v).hexdigest() for k,v in after.items()},claim_sha256=sha(claim),
            effect_count=1,world_goal='NOT_VERIFIED_BY_DISPATCH',authority_scope='DISPOSABLE_LOCAL_PROJECT_ONLY')
        self.events.append(dict(command=deepcopy(proposal),action_receipt=receipt))
        self.effect_attempt_state='APPLIED_AWAITING_INDEPENDENT_READBACK'
        return receipt
