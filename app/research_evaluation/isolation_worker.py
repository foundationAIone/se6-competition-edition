"""Development-only Python audit scope, explicitly NOT an OS security sandbox.

Paid admission must require an additional independently established OS sandbox.
This worker verifies actual file/list denial and strips evaluator metadata at
the process boundary. No provider or subprocess is available inside it.
"""
from pathlib import Path
import argparse,importlib,json,os,sqlite3,sys,time

APP=Path(__file__).resolve().parents[1]
CORE=APP/'awareness_native/work/qpre-calibration-integration-20261026/dev'
sys.path.insert(0,str(APP));sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
from research_evaluation.measurement import Meter

def require(ok,code):
    if not ok:raise ValueError(code)

def install_audit(root,canary):
    root=Path(root).resolve(strict=True);canary=Path(canary).resolve(strict=False)
    allowed=[APP/'research_memory',APP/'research_controls',CORE,Path(sys.base_prefix),Path(sys.prefix)]
    exact={Path(__file__).resolve(),APP/'research_evaluation/__init__.py',APP/'research_evaluation/measurement.py',APP/'research_evaluation/os_probe.py'}
    if Path('/deps').is_dir():allowed.append(Path('/deps'))
    def permitted(path,write=False):
        p=Path(os.fsdecode(path)).resolve(strict=False)
        return p==root or p.is_relative_to(root) or (not write and (p in exact or any(p==r or p.is_relative_to(r) for r in allowed)))
    def audit(event,args):
        if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.posix_spawn','ctypes.dlopen','ctypes.dlsym'}:
            raise PermissionError('MEMORY_WORKER_EXTERNAL_OPERATION_DENIED')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            mode=str(args[1] or '');flags=args[2] if len(args)>2 and type(args[2]) is int else 0
            write=any(x in mode for x in 'wax+') or bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if not permitted(args[0],write):raise PermissionError('MEMORY_WORKER_FILE_SCOPE_DENIED')
        if event in {'os.listdir','os.scandir'} and isinstance(args[0],(str,bytes,os.PathLike)):
            if not permitted(args[0]):raise PermissionError('MEMORY_WORKER_DIRECTORY_SCOPE_DENIED')
        if event in {'os.remove','os.rmdir','os.mkdir','os.chmod'}:
            if not permitted(args[0],True):raise PermissionError('MEMORY_WORKER_MUTATION_SCOPE_DENIED')
        if event in {'os.rename','os.replace'}:
            if not all(permitted(p,True) for p in args[:2]):raise PermissionError('MEMORY_WORKER_MUTATION_SCOPE_DENIED')
        if event in {'os.link','os.symlink'}:raise PermissionError('MEMORY_WORKER_LINK_DENIED')
        if event=='sqlite3.connect':
            address=str(args[0])
            if address.startswith('file:'):
                from urllib.parse import urlsplit,unquote
                address=unquote(urlsplit(address).path)
                if os.name=='nt' and address.startswith('/') and len(address)>2 and address[2]==':':address=address[1:]
            if not permitted(address,True):raise PermissionError('MEMORY_WORKER_DATABASE_SCOPE_DENIED')
    sys.addaudithook(audit)
    try:canary.read_bytes()
    except PermissionError as error:require(str(error)=='MEMORY_WORKER_FILE_SCOPE_DENIED','MEMORY_WORKER_CANARY_CODE')
    else:raise ValueError('MEMORY_WORKER_CANARY_NOT_DENIED')
    try:list(canary.parent.iterdir())
    except PermissionError as error:require(str(error)=='MEMORY_WORKER_DIRECTORY_SCOPE_DENIED','MEMORY_WORKER_DIRECTORY_CANARY_CODE')
    else:raise ValueError('MEMORY_WORKER_DIRECTORY_NOT_DENIED')
    return dict(kind='PYTHON_AUDIT_DEVELOPMENT_ONLY_NOT_OS_SANDBOX',file_canary='DENIED',directory_canary='DENIED',
        os_filesystem_isolation=False,metadata_echoed=False,limitation='Python/native-code bypass is outside this guard; paid runner requires a real OS filesystem sandbox.')

def execute(root,adapter,payload,canary):
    require(adapter in {'se6','conventional'},'MEMORY_ADAPTER_ENUM')
    require(type(payload) is dict and payload.get('operation') in {'insert','query'},'PUBLIC_MEMORY_OPERATION')
    op=payload['operation'];expected={'operation','trajectory'} if op=='insert' else {'operation','question','query_image'}
    require(set(payload)==expected,'PUBLIC_PAYLOAD_NO_EVALUATOR_METADATA')
    if op=='query':require(payload['query_image'] is None,'UNSUPPORTED_MODALITY')
    root=Path(root).resolve(strict=True);meter=Meter();kernel=None
    if os.environ.get('SE6_OS_SANDBOX_REQUIRED')=='1':
        from research_evaluation.os_probe import verify_kernel_boundary
        kernel=verify_kernel_boundary(canary)
    # Warm the own-process RSS implementation before restricting native imports.
    meter.read();isolation=install_audit(root,canary)
    start=time.perf_counter();cpu=time.process_time()
    module=importlib.import_module('research_memory.adapter' if adapter=='se6' else 'research_controls.bm25_notes')
    memory_root=root/'memory'
    memory=module.Memory(root=memory_root,context_char_budget=16384,storage_byte_budget=134217728)
    initialization=dict(wall_seconds=time.perf_counter()-start,host_cpu_seconds=time.process_time()-cpu)
    start=time.perf_counter();cpu=time.process_time()
    if op=='insert':
        result=memory.insert(payload['trajectory']);memory.save(memory_root/'snapshot');context=None
    else:
        memory.load(memory_root/'snapshot');loaded=dict(wall_seconds=time.perf_counter()-start,host_cpu_seconds=time.process_time()-cpu)
        start=time.perf_counter();cpu=time.process_time();context=memory.query(payload['question'],payload['query_image']);result=None
    phase=dict(wall_seconds=time.perf_counter()-start,host_cpu_seconds=time.process_time()-cpu)
    measured=meter.read();measured['disk_bytes']=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    require(measured['disk_bytes']<=134217728,'MEMORY_STORAGE_BUDGET_EXCEEDED')
    return dict(record_kind='NO_PROVIDER_CONTRACT_DEVELOPMENT',operation=op,pid=os.getpid(),isolation=isolation,
        os_sandbox=kernel,initialization=initialization,load=loaded if op=='query' else None,index=phase if op=='insert' else None,
        query=phase if op=='query' else None,context=context,diagnostic=result,trace=getattr(memory,'last_trace',None),resources=measured)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--adapter',required=True);p.add_argument('--canary',required=True)
    a=p.parse_args()
    try:
        value=execute(a.root,a.adapter,json.loads(sys.stdin.read()),a.canary)
    except Exception as error:
        # No record content, question IDs/types, private path or secret is echoed.
        value=dict(status='FAILED_CLOSED',error_type=type(error).__name__,reason=str(error) if str(error).isupper() and len(str(error))<128 else 'MEMORY_WORKER_EXCEPTION',retry_permitted=False)
    print(json.dumps(value,sort_keys=True))
