"""Frozen comparison contract. Source freeze precedes all scored generation."""
from pathlib import Path
import hashlib,json,re

VERSION='se6-paired-developer-workflow-v1'
NATIVE_DOMAIN='se6-native-dependency-relation-development-v1'
LIMITS=dict(projects=3,stages_per_project=2,arms=2,max_model_turns_per_stage=3,
    max_provider_requests=36,max_effects_per_stage=1,max_effects=12,
    max_tools_per_stage=6,max_stage_seconds=360,max_model_loop_seconds=120,max_output_tokens=2048,
    max_request_wire_bytes=24576,model_context_token_upper_bound=262144,automatic_provider_retries=0)
MODEL_SETTINGS=dict(model='nvidia/nemotron-3-super-120b-a12b',temperature=0,
    max_tokens=2048,reasoning_effort='none',response_format={'type':'json_object'})
SYSTEM_PROMPT='''You are a competent stateful developer agent repairing a small Python CLI configuration.
Diagnose the unresolved public project using its actual manifest, public goal, configuration files,
observed CLI failure and current working-root alias. You may retain your own verified notes.
Do not assume a previous dependency, path or configuration is still current after restart.
Both conditions have identical general tools and one action opportunity per stage. No private grader,
expected repair or evaluator answer is available. An action must be your proposed repair; do not invent
a successful consequence. A real independent check follows the action. No shell, arbitrary file path,
network, package installation or additional effects are permitted.
Return exactly one JSON object per turn, using one supported command:
{"type":"inspect","target":"project|manifest|goal|configs|context"}
{"type":"calculate","gain":integer,"offset":integer,"goal":integer}
{"type":"run_cli"}
{"type":"act","path":"existing-config.json","field":"limit","value":integer0to100,"prediction":{"expected_output":integer}}
{"type":"finish","notes":"brief bounded reason for abstention"}
inspect/project returns raw public files, context and diagnostics, never a solved dependency map.
calculate is the same exact rational utility in both conditions. It does not choose a target.
The affine public program computes gain*limit+offset for the active manifest profile.
At most three model turns and one act proposal are allowed. Use your budget competently.
Do not write commentary outside the JSON object.'''
PROTOCOL=dict(version=VERSION,limits=LIMITS,model_settings=MODEL_SETTINGS,
    independent_unit='PROJECT_SEQUENCE_NOT_STAGE',primary='INDEPENDENTLY_VERIFIED_SUCCESS_WITHIN_BUDGET',
    secondary=['wrong_target_edits','interventions','repeated_inspections','model_calls','tool_calls',
        'input_tokens','output_tokens','whole_cpu_seconds','whole_wall_seconds','cost_estimate'],
    variations=['DEPENDENCY','SELF_ROOT','DEPENDENCY_AND_SELF_ROOT'],
    story_rule='LOWEST_NUMERIC_PROJECT_ID_REGARDLESS_OF_OUTCOME',
    conventional='Same model, raw task evidence, general tools and own verified durable notes',
    se6='Same model plus source-bound Native mapping, selection, boundary and verified retention',
    disclosure='Native already deterministically solves the bounded public affine task; count system computation. Model proposal/controller contribution is not proof of mathematical necessity or model superiority.',
    failure_rule='Preserve every response, refusal, failed or ambiguous attempt; no provider retry or replacement scored result',
    answer_boundary='Model has JSON tools only; allowlisted public project paths and own notes, no arbitrary reads/shell. Native subprocess must separately audit forbidden evaluator reads.',
    full_canonical=False)
PROTOCOL['tariff_estimate']=dict(input_usd_per_million='0.30',output_usd_per_million='0.90',
    conservative_max_usd='2.8975104',proposed_hard_cap_usd='3.00',actual_invoice='UNKNOWN',
    input_bound='24576 wire bytes; no verified tokenizer. 262144 model-context ceiling used conservatively for billing bound.')

def require(ok,code):
    if not ok:raise ValueError(code)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_freeze(freeze,source_root):
    require(type(freeze) is dict and freeze.get('status')=='SOURCE_FROZEN','PILOT_SOURCE_FREEZE_REQUIRED')
    require(freeze.get('protocol_sha256')==digest(PROTOCOL),'PILOT_PROTOCOL_PIN')
    root=Path(source_root).resolve(strict=True)
    sources=freeze.get('sources',{})
    required={'paired_workflow/'+name+'.py' for name in ('protocol','tools','tasks','grader','control','runner')}
    require(required.issubset(sources) and bool(freeze.get('native_source_paths')),'PILOT_WHOLE_IMPLEMENTATION_FREEZE')
    require(set(freeze['native_source_paths']).issubset(sources),'PILOT_NATIVE_SOURCE_PIN')
    for relative,pin in sources.items():
        path=(root/relative).resolve(strict=True)
        require(path.is_relative_to(root) and path.is_file() and not path.is_symlink()
            and re.fullmatch('[0-9a-f]{64}',pin) is not None and sha(path)==pin,'PILOT_FROZEN_SOURCE_CHANGED')
    return digest(freeze)

def directive(value):
    require(type(value) is dict and type(value.get('type')) is str,'PILOT_MODEL_JSON_COMMAND')
    kind=value['type']
    fields={'inspect':{'type','target'},'calculate':{'type','gain','offset','goal'},
        'run_cli':{'type'},'act':{'type','path','field','value','prediction'},'finish':{'type','notes'}}
    require(kind in fields and set(value)==fields[kind],'PILOT_COMMAND_FIELDS')
    if kind=='inspect':require(value['target'] in {'project','manifest','goal','configs','context'},'PILOT_INSPECT_TARGET')
    if kind=='calculate':require(all(type(value[k]) is int and abs(value[k])<=100000 for k in ('gain','offset','goal')) and value['gain']!=0,'PILOT_CALCULATE_DOMAIN')
    if kind=='act':
        require(type(value['path']) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.json',value['path']) is not None
            and value['path'] not in {'manifest.json','goal.json'} and value['field']=='limit'
            and type(value['value']) is int and 0<=value['value']<=100,'PILOT_ACTION_DOMAIN')
        require(type(value['prediction']) is dict and set(value['prediction'])=={'expected_output'}
            and type(value['prediction']['expected_output']) is int,'PILOT_ACTION_PREDICTION')
    if kind=='finish':require(type(value['notes']) is str and len(value['notes'])<=1000,'PILOT_NOTES_BOUND')
    return value
