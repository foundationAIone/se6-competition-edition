"""One JSON IPC request in a host-constrained process; no provider client."""
import json,sys
from pathlib import Path
from .adapter import Memory
from .format import require

def execute(value):
    require(type(value) is dict and set(value)<={'root','context_char_budget','storage_byte_budget','operation','trajectory','question','query_image','path'},'MEMORY_IPC_FIELDS')
    memory=Memory(root=Path(value['root']),context_char_budget=value.get('context_char_budget',12000),storage_byte_budget=value.get('storage_byte_budget',512*1024*1024))
    operation=value['operation']
    if operation=='insert':return {'result':memory.insert(value['trajectory'])}
    if operation=='save':return {'result':memory.save(value['path'])}
    if operation=='load':return {'result':memory.load(value['path'])}
    if operation=='query':
        if value.get('path') is not None:memory.load(value['path'])
        context=memory.query(value['question'],value.get('query_image'))
        return {'context':context,'trace':memory.last_trace}
    raise ValueError('MEMORY_IPC_OPERATION')

if __name__=='__main__':
    if hasattr(sys.stdin,'reconfigure'):sys.stdin.reconfigure(encoding='utf-8')
    try:result=execute(json.loads(sys.stdin.read()));print(json.dumps(result,sort_keys=True,ensure_ascii=True))
    except Exception as error:
        print(json.dumps({'status':'FAILED_CLOSED','error_type':type(error).__name__,'code':str(error),'provider_calls':0,'world_effects':0},sort_keys=True));sys.exit(2)
