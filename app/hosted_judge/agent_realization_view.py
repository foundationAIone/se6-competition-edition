"""Pinned, public-only development evidence; no model or action entrypoint."""
import hashlib,json,math,re
from pathlib import Path

SCHEMA='se6-agent-realization-development-view-v1'
STATUS='VERIFIED_DEVELOPMENT_CONNECTION'
KIND='ACTUAL_DISPOSABLE_DEVELOPMENT_NO_MODEL'
HASH=re.compile('[0-9a-f]{64}')


def _require(value,message):
    if not value:raise ValueError(message)


def _public(node):
    if isinstance(node,dict):
        for key,value in node.items():
            name=key.lower().replace('-','_')
            _require(name not in {'api_key','password','csrf','csrf_token','session_token','cookie',
                'authorization','secret','credentials','root','cwd','private_root','absolute_path'}
                and 'api_key' not in name and not name.endswith(('_password','_secret','_token')),'Private development field')
            _public(value)
    elif isinstance(node,list):
        _require(len(node)<=128,'Development list bound')
        for value in node:_public(value)
    elif isinstance(node,str):
        _require(len(node)<=8192 and not re.search(r'[A-Za-z]:[\\/]|(?:^|[\s=])/[A-Za-z0-9_.-]|file://|\\\\',node),
            'Private development path or string bound')
    elif isinstance(node,float):_require(math.isfinite(node),'Development finite number required')
    else:_require(node is None or type(node) in (int,bool),'Development JSON type')


def load(path,pin):
    raw_path=Path(path)
    _require(not raw_path.is_symlink() and not (hasattr(raw_path,'is_junction') and raw_path.is_junction()),'Development regular file required')
    path=raw_path.resolve(strict=True)
    _require(path.is_file() and path.stat().st_size<=256*1024,'Development projection bound')
    _require(type(pin) is str and HASH.fullmatch(pin) is not None,'Exact development projection pin required')
    raw=path.read_bytes();_require(hashlib.sha256(raw).hexdigest()==pin,'Development projection source changed')
    value=json.loads(raw,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Development finite number required')))
    _require(type(value) is dict and value.get('schema')==SCHEMA and value.get('status')==STATUS
        and value.get('record_kind')==KIND,'Development projection schema or provenance')
    _require(type(value.get('provider_calls')) is int and value['provider_calls']==0
        and value.get('production_connected') is False and value.get('alpha_changed') is False,'Development non-authorizing scope')
    for name in ('source_manifest_sha256','raw_result_sha256','independent_review_sha256'):
        _require(type(value.get(name)) is str and HASH.fullmatch(value[name]) is not None,'Development evidence hash required')
    repair=value.get('completion_repair')
    _require(type(repair) is dict and repair.get('regrade') is False,'Historical results must remain unchanged')
    conditions=value.get('conditions')
    _require(type(conditions) is list and len(conditions)==2
        and {x.get('name') for x in conditions if type(x) is dict}=={'retained-bridge','bridge-disabled'},'Two Native development conditions required')
    for condition in conditions:
        phases=condition.get('phases')
        _require(type(phases) is list and len(phases)==2 and {x.get('phase') for x in phases if type(x) is dict}=={1,2},'Two recorded development phases required')
        for phase in phases:
            _require(type(phase.get('phase')) is int,'Development phase integer field')
            for name in ('pid','public_goal','actual_effects','candidate_count','entity_version'):
                _require(type(phase.get(name)) is int and phase[name]>=0,'Development phase integer field')
            _require(phase['pid']>0 and phase['actual_effects']<=1,'Development phase effect bound')
            for name in ('goal','memory_consumed','cold_restored'):_require(type(phase.get(name)) is bool,'Development phase Boolean field')
            candidates=phase.get('configured_candidates')
            _require(type(candidates) is list and len(candidates)<=8 and len(candidates)==phase['candidate_count'],'Development candidate binding')
            for name in ('native_receipt_hash','witness_sha256','retained_state_sha256'):
                _require(type(phase.get(name)) is str and HASH.fullmatch(phase[name]) is not None,'Development receipt hash required')
    _require(type(value.get('limitations')) is list and all(type(x) is str for x in value['limitations']),'Development limitations required')
    _public(value)
    return value
