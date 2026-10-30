"""Read-only, pinned projection. It never authenticates spending or an effect."""
import hashlib,json,re
from pathlib import Path

def load(path,pin):
    path=Path(path).resolve(strict=True)
    if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('Pilot projection bound')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Pilot projection source changed')
    value=json.loads(raw)
    if value.get('schema')!='se6-model-workflow-view-v1' or type(value.get('responses_committed')) is not bool:raise ValueError('Pilot projection schema')
    if value.get('status') not in {'BLOCKED_PENDING_EXACT_BUDGET','RUNNING','CAPTURED_AWAITING_EVALUATION','COMPLETE','INCOMPLETE','INVALIDATED'}:raise ValueError('Pilot projection status')
    if value.get('record_kind') not in {'PREPARED','RECORDED'}:raise ValueError('Pilot projection provenance')
    if not value['responses_committed'] and (value.get('projects') or value.get('aggregate') is not None):raise ValueError('Uncommitted pilot outcomes must remain private')
    def inspect(node):
        if isinstance(node,dict):
            for key,item in node.items():
                if key.lower() in {'api_key','password','csrf','session_token','cookie','authorization'}:raise ValueError('Private pilot field')
                inspect(item)
        elif isinstance(node,list):
            for item in node:inspect(item)
        elif isinstance(node,str) and re.search(r'[A-Za-z]:[\\/]',node):raise ValueError('Private workstation path')
    inspect(value)
    return value
