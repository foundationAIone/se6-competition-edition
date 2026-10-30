"""Post-freeze random case generation. No scored instance exists on import."""
from datetime import UTC,datetime
from pathlib import Path
import json,random,secrets
from .protocol import NATIVE_DOMAIN,PROTOCOL,digest,encode,require,validate_freeze

WORKLOAD="""import json,sys
from pathlib import Path
m=json.loads(Path('manifest.json').read_text());s=json.loads(Path('goal.json').read_text())
p=m['profiles'][m['entry']];c=json.loads(Path(p['config']).read_text())
y=p['gain']*c['limit']+p['offset']
print(json.dumps({'output':y,'cwd':str(Path.cwd().resolve())},sort_keys=True))
raise SystemExit(0 if y==s['goal'] else 3)
"""

def exclusive(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(value if type(value) is bytes else encode(value))

def _sample(rng,number,change):
    names=rng.sample(['amber','birch','coral','delta','elm','fjord','grove','hazel'],rng.randint(3,5))
    goal=rng.randint(100,220);profiles={};configs={}
    for name in names:
        gain=rng.randint(2,7)
        lower=max(0,-(-(goal-100)//gain));upper=min(100,(goal+100)//gain)
        target=rng.randint(lower,upper);offset=goal-gain*target
        path=name+'-settings.json';profiles[name]=dict(config=path,gain=gain,offset=offset)
        wrong=rng.choice([n for n in range(101) if n!=target]);configs[path]={'limit':wrong}
    active=rng.choice(names);second=rng.choice([n for n in names if n!=active]) if change!='SELF_ROOT' else active
    profile=profiles[second];target=(goal-profile['offset'])//profile['gain']
    wrong=rng.choice([n for n in range(101) if n!=target])
    return dict(project_id=f'project-{number:03d}',change_kind=change,
        public_files={'workload.py':WORKLOAD,'manifest.json':{'entry':active,'profiles':profiles},
            'goal.json':{'version':NATIVE_DOMAIN,'goal':goal,'setting_bounds':[0,100],'operation':'gain*limit+offset'},**configs},
        stage2_change=dict(entry=second,root_alias='projectB' if change!='DEPENDENCY' else 'projectA',
            reset_config=profile['config'],reset_limit=wrong),
        private_scope='EVALUATOR_ONLY_NOT_SOLVER_INPUT')

def generate_scored_cases(output,freeze,source_root):
    """Coordinator-only after whole-source freeze; one exclusive generation."""
    freeze_hash=validate_freeze(freeze,source_root)
    root=Path(output).resolve(strict=False)
    require(not root.is_relative_to(Path(source_root).resolve(strict=True)),'PILOT_PRIVATE_CASES_OUTSIDE_SOLVER_SOURCE')
    require(not root.exists(),'PILOT_GENERATION_ALREADY_EXISTS')
    root.mkdir(parents=True)
    private=root/'EVALUATOR_ONLY';private.mkdir()
    records=[]
    for number,change in enumerate(PROTOCOL['variations'],start=1):
        seed=secrets.token_hex(32)
        case=_sample(random.Random(int(seed,16)),number,change)
        exclusive(private/(case['project_id']+'.json'),case)
        records.append(dict(project_id=case['project_id'],case_sha256=digest(case),seed=seed))
    receipt=dict(status='FRESH_CASES_GENERATED_AFTER_SOURCE_FREEZE',generated_at_utc=datetime.now(UTC).isoformat(),
        freeze_sha256=freeze_hash,protocol_sha256=digest(PROTOCOL),private_cases=records,
        independent_units=3,stages_per_project=2)
    exclusive(private/'generation.json',receipt)
    return dict(status=receipt['status'],freeze_sha256=freeze_hash,project_ids=[r['project_id'] for r in records],
        generation_receipt_sha256=digest(receipt))

def install_initial_project(case,public_root):
    root=Path(public_root).resolve(strict=False);require(not root.exists(),'PILOT_INITIAL_WORLD_EXISTS');root.mkdir(parents=True)
    for name,value in case['public_files'].items():
        exclusive(root/name,value.encode('utf-8') if type(value) is str else value)

def apply_stage2_change(case,previous_root,new_root):
    """Copy that arm's ACTUAL predecessor, never insert a correct repair."""
    from .tools import checked_files
    previous=Path(previous_root).resolve(strict=True);destination=Path(new_root).resolve(strict=False)
    before=checked_files(previous)
    if destination!=previous:
        require(not destination.exists(),'PILOT_COLD_WORLD_EXISTS');destination.mkdir(parents=True)
        for name,value in before.items():exclusive(destination/name,value)
    change=case['stage2_change'];manifest=json.loads(before['manifest.json']);manifest['entry']=change['entry']
    (destination/'manifest.json').write_bytes(encode(manifest))
    if change['reset_config'] is not None:
        require(change['reset_config'] in before,'PILOT_STAGE2_PUBLIC_CONFIG')
        (destination/change['reset_config']).write_bytes(encode({'limit':change['reset_limit']}))
    return dict(change_kind=case['change_kind'],root_alias=change['root_alias'],
        copied_actual_predecessor=True,inserted_expected_repair=False)
