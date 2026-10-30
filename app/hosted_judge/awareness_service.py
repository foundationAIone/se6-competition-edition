"""Bounded asynchronous adapter to the shipped, genuine Native dev lifecycle.

The HTTP owner must validate its existing session, exact origin and CSRF first.
This adapter records one non-refundable request per session. It never retries
an interrupted or uncertain task and does not import Native into the web host.
"""
from copy import deepcopy
import hashlib, json, math, os, re, subprocess, sys, threading, time
from pathlib import Path
from . import realization_loop as loop

SCENARIO='dependency-self-v1'
MODE='LIVE_DISPOSABLE_DEVELOPMENT'
TERMINAL={'COMPLETE','FAILED_CLOSED','INTERRUPTED'}
MAX_JOBS=64
MAX_PUBLIC_BYTES=512*1024


def _require(ok, code):
    if not ok: raise ValueError(code)


def _safe(value, depth=0):
    _require(depth<=16, 'AWARENESS_OUTPUT_DEPTH')
    if value is None or type(value) in (bool,int): return
    if type(value) is float:
        _require(math.isfinite(value),'AWARENESS_NONFINITE_OUTPUT'); return
    if type(value) is str:
        _require(len(value)<=4096 and not re.search(r'[A-Za-z]:[\\/]',value)
            and not value.startswith(('/', '\\\\')), 'AWARENESS_PRIVATE_PATH')
        return
    if type(value) is list:
        _require(len(value)<=256,'AWARENESS_OUTPUT_BOUND')
        for row in value: _safe(row,depth+1)
        return
    _require(type(value) is dict and len(value)<=256,'AWARENESS_OUTPUT_SHAPE')
    for key,row in value.items():
        _require(type(key) is str and key.lower() not in {
            'password','csrf','session_token','cookie','api_key','raw_store','private_path'},'AWARENESS_PRIVATE_FIELD')
        _safe(key,depth+1); _safe(row,depth+1)


class AwarenessService:
    def __init__(self,root,*,runner=None,deadline_seconds=300,max_workers=1,shared_slots=None):
        self.root=loop.root_path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.deadline_seconds=deadline_seconds
        _require(type(deadline_seconds) in (int,float) and 0<deadline_seconds<=600,'AWARENESS_DEADLINE')
        _require(type(max_workers) is int and 1<=max_workers<=2,'AWARENESS_WORKER_BOUND')
        self._runner=runner or self._run_packaged
        self._slots=threading.BoundedSemaphore(max_workers)
        self._shared_slots=shared_slots
        self._lock=threading.RLock()
        self._owned=set()
        # A fresh service cannot establish a previous process's outcome.
        # Persist uncertainty instead of relaunching it.
        for path in self.root.glob('*/state.json'):
            record=self._read(path)
            if record['status']=='RUNNING':
                record.update(status='INTERRUPTED',error_code='AWARENESS_INTERRUPTED_NO_RETRY',finished_unix=time.time())
                self._write(path,record)

    @property
    def bundle_root(self): return Path(__file__).resolve().parents[1]/'awareness_native'

    def _directory(self,token):
        _require(type(token) is str and re.fullmatch('[0-9a-f]{64}',token),'AWARENESS_SESSION_REQUIRED')
        return loop.root_path(self.root/hashlib.sha256(token.encode()).hexdigest())

    @staticmethod
    def _read(path):
        loop.root_path(path)
        _require(path.is_file() and path.stat().st_size<=MAX_PUBLIC_BYTES,'AWARENESS_RECORD_BOUND')
        return loop.checked(json.loads(path.read_bytes()))

    @staticmethod
    def _write(path,record):
        raw=loop.encode(loop.seal({key:value for key,value in record.items() if key!='sha256'}))
        _require(len(raw)<=MAX_PUBLIC_BYTES,'AWARENESS_RECORD_BOUND')
        temporary=path.with_name(path.name+'.'+os.urandom(8).hex()+'.tmp')
        loop.exclusive(temporary,raw); os.replace(temporary,path)

    def active(self,session_token):
        directory=self._directory(session_token)
        with self._lock:
            path=directory/'state.json'
            return path.exists() and self._read(path)['status']=='RUNNING'

    def submit(self,session_token,value):
        _require(type(value) is dict and set(value)=={'request_id','scenario'},'AWARENESS_REQUEST_FIELDS')
        ident=value['request_id']
        _require(type(ident) is str and re.fullmatch('[0-9a-f]{32}',ident),'AWARENESS_REQUEST_ID')
        _require(value['scenario']==SCENARIO,'AWARENESS_SCENARIO_UNSUPPORTED')
        directory=self._directory(session_token)
        with self._lock:
            claim=directory/'claim.json'
            if claim.exists():
                old=self._read(claim)
                _require(old['request_id']==ident,'AWARENESS_SESSION_ALLOWANCE')
                path=directory/'state.json'
                if not path.exists():
                    self._write(path,self._base(ident,'INTERRUPTED',error_code='AWARENESS_UNCERTAIN_CLAIM_NO_RETRY'))
                return self.get(session_token,ident)
            _require(len(list(self.root.glob('*/claim.json')))<MAX_JOBS,'AWARENESS_STORE_CAP')
            _require(self._slots.acquire(blocking=False),'AWARENESS_BUSY')
            shared=False
            try:
                if self._shared_slots is not None:
                    shared=self._shared_slots.acquire(blocking=False)
                    _require(shared,'AWARENESS_SHARED_WORKER_BUSY')
                directory.mkdir(exist_ok=True)
                loop.exclusive(claim,loop.encode(loop.seal(dict(request_id=ident,scenario=SCENARIO,
                    status='CLAIMED_NONREFUNDABLE',created_unix=time.time()))))
                record=self._base(ident,'RUNNING',started_unix=time.time())
                self._write(directory/'state.json',record)
                self._owned.add(ident)
                worker=threading.Thread(target=self._execute,args=(directory,ident,shared),daemon=True,
                    name='se6-awareness-'+ident[:8])
                worker.start()
            except BaseException:
                self._slots.release()
                if shared:self._shared_slots.release()
                raise
            return deepcopy(record)

    @staticmethod
    def _base(ident,status,**fields):
        return dict(request_id=ident,status=status,mode=MODE,scenario=SCENARIO,phases=[],
            comparative_result='NOT_ESTABLISHED',resources={},source_hashes={},**fields)

    def _execute(self,directory,ident,shared):
        try:
            payload=self._runner(directory)
            _require(type(payload) is dict and set(payload)<= {'status','phases','comparative_result','resources',
                'source_hashes','limitations','development_case_visibility','error_code'},'AWARENESS_WORKER_OUTPUT_FIELDS')
            _safe(payload)
            status=payload.get('status','COMPLETE')
            _require(status in {'COMPLETE','FAILED_CLOSED'},'AWARENESS_WORKER_STATUS')
            record={**self._base(ident,status),**payload,'status':status,'finished_unix':time.time()}
        except subprocess.TimeoutExpired:
            record=self._base(ident,'INTERRUPTED',error_code='AWARENESS_DEADLINE_NO_RETRY',finished_unix=time.time())
        except BaseException:
            record=self._base(ident,'FAILED_CLOSED',error_code='AWARENESS_EXECUTION_FAILED_NO_RETRY',finished_unix=time.time())
        finally:
            try:
                with self._lock:
                    path=directory/'state.json'
                    # An interruption recorded by recovery/polling is permanent.
                    if path.exists() and self._read(path)['status']=='RUNNING': self._write(path,record)
                    self._owned.discard(ident)
            finally:
                self._slots.release()
                if shared:self._shared_slots.release()

    def get(self,session_token,request_id):
        _require(type(request_id) is str and re.fullmatch('[0-9a-f]{32}',request_id),'AWARENESS_REQUEST_ID')
        directory=self._directory(session_token)
        with self._lock:
            claim=directory/'claim.json'
            _require(claim.exists() and self._read(claim)['request_id']==request_id,'AWARENESS_REQUEST_NOT_FOUND')
            path=directory/'state.json'
            if not path.exists():
                return self._base(request_id,'INTERRUPTED',error_code='AWARENESS_UNCERTAIN_CLAIM_NO_RETRY')
            record=self._read(path)
            if record['status']=='RUNNING' and time.time()-record['started_unix']>self.deadline_seconds+2:
                record.update(status='INTERRUPTED',error_code='AWARENESS_DEADLINE_NO_RETRY',finished_unix=time.time())
                self._write(path,record)
            return {key:deepcopy(value) for key,value in record.items() if key!='sha256'}

    def export(self,session_token,request_id):
        return {**self.get(session_token,request_id),'export_format':'se6-awareness-public-v1'}

    def evidence(self):
        path=self.bundle_root/'frozen_evidence.json'
        result=json.loads(path.read_bytes()); _safe(result)
        return result

    def _run_packaged(self,directory):
        script=Path(__file__).resolve().parents[1]/'tools/run_awareness_worker.py'
        environment={key:value for key,value in os.environ.items() if key.upper() in {
            'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE'}}
        environment.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
        result=subprocess.run([sys.executable,'-B',str(script),'--out',str(directory)],cwd=script.parents[1],
            capture_output=True,text=True,timeout=self.deadline_seconds,env=environment)
        # Error logs stay private and are never returned through the API.
        for name,data in [('worker.stdout.txt',result.stdout),('worker.stderr.txt',result.stderr)]:
            loop.exclusive(directory/name,data[-16384:].encode('utf-8','replace'))
        _require(result.returncode==0,'AWARENESS_WORKER_FAILED')
        path=directory/'public-result.json'
        _require(path.is_file() and path.stat().st_size<=MAX_PUBLIC_BYTES,'AWARENESS_WORKER_RESULT')
        return json.loads(path.read_bytes())
