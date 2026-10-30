"""Bounded fresh-worker HOST reuse of pure admission, never receipt verification.

Install identically for B/C/D after frozen native source load. No core/global class
patch, restored engine cache, transition cache, disk persistence or cross-call use.
Original graph reconstruction and mandatory independent postflight stay unchanged.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib,json,marshal,sys,time,types,os,threading

PURE_ROUTES=frozenset(('LINEAR_DERIVATION','LINEAR_MATH','RELATIONAL'))
SCHEMA='se6-host-invocation-admission-memo-v1'

def encoded(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encoded(v)).hexdigest()
def _fingerprint(fn):
    return hashlib.sha256(marshal.dumps(fn.__code__)).hexdigest()
def _functions(value):
    if isinstance(value,types.FunctionType):return [(None,value)]
    if isinstance(value,type):
        return [(name, v.__func__ if isinstance(v,(staticmethod,classmethod)) else v) for name,v in vars(value).items() if isinstance(v,(types.FunctionType,staticmethod,classmethod))]
    return []
def _constants(fn):
    out={}
    for n in fn.__code__.co_names:
        if n not in fn.__globals__:continue
        v=fn.__globals__[n]
        if type(v) in (str,int,bool,float,type(None),tuple):
            try:out[n]=encoded(v)
            except (TypeError,ValueError):pass
    return out

def _default_bytes(value):
    try:return encoded(value)
    except (TypeError,ValueError):return None

def _capture_callable(value):
    return (value,[(n,f,f.__code__,f.__defaults__,f.__kwdefaults__,_default_bytes(f.__defaults__),_default_bytes(f.__kwdefaults__),_constants(f)) for n,f in _functions(value)])
def _same_callable(value,expected):
    if value is not expected[0]:return False
    current=dict(_functions(value))
    return all(current.get(n) is f and f.__code__ is code and f.__defaults__ is defaults and f.__kwdefaults__ is kw and _default_bytes(f.__defaults__)==default_bytes and _default_bytes(f.__kwdefaults__)==kw_bytes and _constants(f)==constants for n,f,code,defaults,kw,default_bytes,kw_bytes,constants in expected[1])

class ClassificationMemo:
    def __init__(self,auto,revision,*,max_entries=8,max_bytes=65536):
        if type(max_entries) is not int or not 1<=max_entries<=32 or type(max_bytes) is not int or not 1024<=max_bytes<=65536:raise ValueError('MEMO_BOUND')
        if 'classify' in vars(auto):raise ValueError('MEMO_CLASSIFIER_ALREADY_OVERRIDDEN')
        self.owner_pid=os.getpid();self.owner_thread=threading.get_ident()
        self.auto=auto;self.cls=type(auto);self.original=auto.classify;self.fn=self.original.__func__
        self.fn_capture=_capture_callable(self.fn);self.globals=self.fn.__globals__
        self.helpers={n:_capture_callable(v) for n,v in self.globals.items() if callable(v)}
        self.check_sources=self.globals['check_sources'];self.source_object=self.globals['SOURCE_HASHES']
        self.source_hashes=deepcopy(self.source_object);self.contract=self.globals['CONTRACT']
        self.revision=revision;self.revision_method=revision.public;self.revision_method_capture=_capture_callable(self.revision_method.__func__)
        self.revision_hash=self._revision_check();self.revision_manifest=digest(revision.public().get('startup_manifest'))
        self.revision_sources=digest({k:hashlib.sha256(v).hexdigest() for k,v in getattr(revision,'sources',{}).items()})
        self.classifier_fp=_fingerprint(self.fn)
        self.integrations=auto.integrations
        self.adapters={n:(v,type(v),_capture_callable(type(v)),{k:x for k,x in vars(v).items() if type(x) in (str,int,bool,float,type(None))}) for n,v in vars(self.integrations).items() if hasattr(v,'__dict__')}
        prefix='src.workbench.canonical_core_vendor.se_core'
        self.core_runtime={n:(mod,{k:_capture_callable(v) for k,v in vars(mod).items() if isinstance(v,(types.FunctionType,type))}) for n,mod in list(sys.modules.items()) if n==prefix or n.startswith(prefix+'.')}
        self.cache=OrderedDict();self.used=0;self.max_entries=max_entries;self.max_bytes=max_bytes;self.closed=False
        self.stats={'calls':0,'hits':0,'misses':0,'uncached':0,'evictions':0,'source_checks':0,'guard_wall_seconds':0.0,'guard_cpu_seconds':0.0}
        owner=self
        def wrapper(this,text,checkpoint=None):
            if this is not owner.auto:raise ValueError('MEMO_INSTANCE_IDENTITY')
            return owner.classify(text,checkpoint)
        self.wrapper=types.MethodType(wrapper,auto);auto.classify=self.wrapper
    def _revision_check(self,value=None):
        if value is None:value=self.revision.public()
        if value.get('disk_matches_loaded') is not True or value.get('disk_matches_startup') is not True:raise ValueError('MEMO_REVISION_CHANGED')
        return value['startup_source_revision_sha256']
    def _guard(self,checkpoint):
        start=time.perf_counter();cpu=time.process_time()
        try:
            if os.getpid()!=self.owner_pid or threading.get_ident()!=self.owner_thread:raise ValueError('MEMO_WORKER_LIFETIME')
            if self.closed or type(self.auto) is not self.cls or self.auto.classify is not self.wrapper or self.cls.classify is not self.fn or not _same_callable(self.fn,self.fn_capture):raise ValueError('MEMO_CLASSIFIER_RUNTIME_CHANGED')
            if self.auto.integrations is not self.integrations:raise ValueError('MEMO_INTEGRATION_CHANGED')
            for n,(value,cls,cls_capture,attrs) in self.adapters.items():
                if getattr(self.integrations,n,None) is not value or type(value) is not cls or not _same_callable(cls,cls_capture) or any(getattr(value,k,None)!=v for k,v in attrs.items()):raise ValueError('MEMO_ADAPTER_CHANGED')
            if {n for n,v in self.globals.items() if callable(v)}!=set(self.helpers) or any(not _same_callable(self.globals.get(n),v) for n,v in self.helpers.items()):raise ValueError('MEMO_HELPER_RUNTIME_CHANGED')
            for name,(mod,items) in self.core_runtime.items():
                if sys.modules.get(name) is not mod or any(not _same_callable(getattr(mod,n,None),value) for n,value in items.items()):raise ValueError('MEMO_CORE_RUNTIME_CHANGED')
            if self.globals.get('SOURCE_HASHES') is not self.source_object or self.source_object!=self.source_hashes or self.globals.get('CONTRACT')!=self.contract:raise ValueError('MEMO_SOURCE_BINDING')
            if not _same_callable(self.revision.public.__func__,self.revision_method_capture):raise ValueError('MEMO_REVISION_CHANGED')
            revision_value=self.revision.public()
            if self._revision_check(revision_value)!=self.revision_hash:raise ValueError('MEMO_REVISION_CHANGED')
            if digest(revision_value.get('startup_manifest'))!=self.revision_manifest or digest({k:hashlib.sha256(v).hexdigest() for k,v in getattr(self.revision,'sources',{}).items()})!=self.revision_sources:raise ValueError('MEMO_LOADER_RUNTIME_CHANGED')
            self.check_sources();self.stats['source_checks']+=1
            if checkpoint is not None and (not isinstance(checkpoint,dict) or checkpoint.get('schema')!=self.contract or checkpoint.get('source_hashes')!=self.source_hashes or checkpoint.get('checkpoint_hash')!=digest({k:v for k,v in checkpoint.items() if k!='checkpoint_hash'})):raise ValueError('MEMO_CHECKPOINT_BINDING')
        except Exception:
            self.clear();self.closed=True
            raise
        finally:
            self.stats['guard_wall_seconds']+=time.perf_counter()-start;self.stats['guard_cpu_seconds']+=time.process_time()-cpu
    def classify(self,text,checkpoint=None):
        self.stats['calls']+=1;self._guard(checkpoint)
        raw=encoded({'text':text,'checkpoint':checkpoint,'source_hashes':self.source_hashes,'classifier_fp':self.classifier_fp,'revision':self.revision_hash})
        key=hashlib.sha256(raw).hexdigest();cached=self.cache.get(key)
        if cached is not None:
            self.stats['hits']+=1;self.cache.move_to_end(key);return deepcopy(cached[0])
        self.stats['misses']+=1;before=encoded({'text':text,'checkpoint':checkpoint})
        value=self.original(text,checkpoint) # Exceptions never cached.
        if encoded({'text':text,'checkpoint':checkpoint})!=before:
            self.clear();self.closed=True;raise ValueError('MEMO_CLASSIFIER_MUTATED_INPUT')
        self._guard(checkpoint) # A miss may not change helper/runtime/revision identity.
        size=len(key)
        try:size+=len(encoded(value))
        except (TypeError,ValueError):size=self.max_bytes+1
        if type(value) is not dict or value.get('route') not in PURE_ROUTES or size>self.max_bytes:
            self.stats['uncached']+=1;return deepcopy(value)
        while self.cache and (len(self.cache)>=self.max_entries or self.used+size>self.max_bytes):
            _,old=self.cache.popitem(last=False);self.used-=old[1];self.stats['evictions']+=1
        self.cache[key]=(deepcopy(value),size);self.used+=size
        return deepcopy(value)
    def helper_fingerprints(self):
        return {n:{str(k):_fingerprint(f) for k,f,code,defaults,kw,default_bytes,kw_bytes,constants in capture[1]} for n,capture in self.helpers.items()}
    def public(self):
        return {'schema':SCHEMA,'scope':'HOST reuse of byte-identical pure admission within one frozen worker; no native receipt/proof or field authority','policy':'SAME_B_C_D_INVOCATION_LOCAL','classifier_sha256':self.classifier_fp,'source_hashes_sha256':digest(self.source_hashes),'revision_sha256':self.revision_hash,'entries':len(self.cache),'serialized_bytes':self.used,'max_entries':self.max_entries,'max_bytes':self.max_bytes,**deepcopy(self.stats)}
    def clear(self):self.cache.clear();self.used=0
    def close(self):
        self.clear();self.closed=True
        if self.auto.classify is self.wrapper:del self.auto.__dict__['classify']

def install(auto,revision,**bounds):return ClassificationMemo(auto,revision,**bounds)
