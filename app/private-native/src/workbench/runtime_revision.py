"""Frozen source loader/start attestation. No disk hashes masquerade as imports.

Install before operational repository modules import. Scoped loaders compile
exact frozen startup bytes, bypassing bytecode caches. Standard library and
already-imported bootstrap packages are explicitly outside attested scope.
"""
from copy import deepcopy
import hashlib
import importlib.abc
import importlib.machinery
import json
from pathlib import Path
import sys
import threading


def digest(value):return hashlib.sha256(value).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


class FrozenRevision(importlib.abc.MetaPathFinder):
    def __init__(self,root):
        self.root=Path(root).resolve();self.lock=threading.RLock()
        self.sources={str(p.resolve()):p.read_bytes() for name in ('src','scripts')
                      for p in (self.root/name).rglob('*.py')}
        self.manifest={str(Path(p).relative_to(self.root)).replace('\\','/'):digest(raw)
                       for p,raw in self.sources.items()}
        self.revision=digest(encoded(self.manifest));self.loaded={}
        self.bootstrap={}
        for name,module in list(sys.modules.items()):
            path=getattr(module,'__file__',None)
            if path and str(Path(path).resolve()) in self.sources:
                entrypoint=name=='__main__' and Path(path).resolve()==self.root/'scripts/run_comparison_ui.py'
                if name not in ('src','src.workbench','src.workbench.runtime_revision') and not entrypoint:
                    raise ValueError('Operational module already imported before source freeze: '+name)
                self.bootstrap[name]='ALREADY_IMPORTED_BOOTSTRAP_NOT_ATTESTED'

    def install(self):
        sys.meta_path.insert(0,self)
        return self

    def uninstall(self):
        if self in sys.meta_path:sys.meta_path.remove(self)

    def find_spec(self,fullname,path=None,target=None):
        if not (fullname.startswith('src.') or fullname=='src' or fullname.startswith('scripts.') or fullname=='scripts'):
            return None
        spec=importlib.machinery.PathFinder.find_spec(fullname,path)
        if spec is None or spec.origin is None:return None
        origin=str(Path(spec.origin).resolve())
        if origin not in self.sources:
            raise ImportError('Repository module absent from frozen startup source: '+fullname)
        owner=self;raw=self.sources[origin]
        class Loader(importlib.machinery.SourceFileLoader):
            def get_code(self,name):
                code=compile(raw,origin,'exec',dont_inherit=True)
                import marshal
                with owner.lock:
                    owner.loaded[name]={'path':str(Path(origin).relative_to(owner.root)).replace('\\','/'),
                        'source_sha256':digest(raw),'compiled_code_sha256':digest(marshal.dumps(code))}
                return code
        spec.loader=Loader(fullname,origin)
        return spec

    def public(self):
        with self.lock:
            loaded=deepcopy(self.loaded)
        changed=[]
        for name,expected in self.manifest.items():
            try:actual=digest((self.root/name).read_bytes())
            except OSError:actual=None
            if actual!=expected:changed.append(name)
        for folder in ('src','scripts'):
            for path in (self.root/folder).rglob('*.py'):
                name=str(path.relative_to(self.root)).replace('\\','/')
                if name not in self.manifest:changed.append(name)
        return {'schema':'se6-frozen-runtime-revision-v1','startup_source_revision_sha256':self.revision,
                'source_manifest_sha256':self.revision,'disk_matches_loaded':not changed,
                'startup_manifest':deepcopy(self.manifest),'compiled_modules':loaded,
                'bootstrap_modules':deepcopy(self.bootstrap),'disk_matches_startup':not changed,
                'changed_disk_source_files':sorted(set(changed)),
                'scope':'Recorded modules compile exact frozen startup bytes; bootstrap and external libraries unattested.'}


def freeze_sources(root):return FrozenRevision(root).install()
