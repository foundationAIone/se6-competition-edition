"""Stable private code-object descriptor, independent of marshal interning flags."""
import hashlib,json
from pathlib import Path
from types import CodeType
def describe(value):
    if isinstance(value,CodeType):
        fields={k:getattr(value,k) for k in ['co_name','co_qualname','co_argcount','co_posonlyargcount',
            'co_kwonlyargcount','co_nlocals','co_stacksize','co_flags','co_firstlineno','co_names',
            'co_varnames','co_freevars','co_cellvars','co_consts','co_code','co_linetable','co_exceptiontable']}
        fields['file_name']=Path(value.co_filename).name
        return {'code':{k:describe(v) for k,v in fields.items()}}
    if isinstance(value,tuple):return {'tuple':[describe(v) for v in value]}
    if isinstance(value,frozenset):return {'frozenset':sorted((describe(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))}
    if isinstance(value,bytes):return {'bytes':value.hex()}
    if value is None or type(value) in (bool,int,str):return {type(value).__name__:value}
    if type(value) in (float,complex) or value is Ellipsis:return {type(value).__name__:repr(value)}
    raise TypeError(type(value).__name__)
def fingerprint(function):
    return hashlib.sha256(json.dumps(describe(function.__code__),sort_keys=True,separators=(',',':')).encode()).hexdigest()
