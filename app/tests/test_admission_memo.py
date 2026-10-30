"""Pure HOST memo guards; no Native/provider/source execution."""
from pathlib import Path
import sys,types
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'hosted_judge'))
from admission_memo import install,digest
SOURCE_HASHES={'kernel.py':'DEV_PIN'}
CONTRACT='se6-universal-auto-v1'
CHECKS={'count':0,'failed':False}
def check_sources():
    CHECKS['count']+=1
    if CHECKS['failed']:raise ValueError('DEV_SOURCE_CHANGED')
def relation(text):return text

class Revision:
    def __init__(self):self.clean=True;self.identity='DEV_FROZEN_REVISION'
    def public(self):return {'disk_matches_loaded':self.clean,'disk_matches_startup':self.clean,'startup_source_revision_sha256':self.identity}
class Auto:
    def __init__(self):self.calls=0;self.integrations=types.SimpleNamespace(math=types.SimpleNamespace(revision='canonical'))
    def classify(self,text,checkpoint=None):
        check_sources();self.calls+=1
        if text=='error':raise ValueError('DEV_ORIGINAL_ERROR')
        if text=='mutate':checkpoint['extra']='mutated'
        return {'route':'DIRECT_MODEL' if text=='plugin' else 'LINEAR_DERIVATION','data':[text],'bytes':'x'*2000 if text=='big' else 'small'}

def cp(v=1):
    value={'schema':CONTRACT,'source_hashes':dict(SOURCE_HASHES),'data':v}
    return {**value,'checkpoint_hash':digest(value)}
@pytest.fixture(autouse=True)
def clean():CHECKS.update(count=0,failed=False)


def test_equivalent_results_deepcopy_and_everyhit_source_check():
    a=Auto();m=install(a,Revision());state=cp();plain=Auto().classify('q',state)
    first=a.classify('q',state);assert first==plain
    first['data'].append('caller mutation')
    count=CHECKS['count'];hit=a.classify('q',state)
    assert hit==plain and CHECKS['count']==count+1 and a.calls==1
    hit['data'].clear();assert a.classify('q',state)==plain
    assert m.public()['hits']==2 and m.public()['policy']=='SAME_B_C_D_INVOCATION_LOCAL'
    assert all(type(v) is not dict or 'checkpoint' not in v for v in m.cache.values())


def test_none_distinct_wholecp_rehashed_changed_input_misses():
    a=Auto();m=install(a,Revision())
    for text,state in [('q',None),('q',cp()),('q',cp(2)),('other',cp())]:a.classify(text,state)
    assert a.calls==4 and m.public()['hits']==0
    a.classify('q',cp());assert m.public()['hits']==1

@pytest.mark.parametrize('change',['bad_hash','source','schema','runtime_method','helper','helper_code','revision','adapter','source_disk'])
def test_tamper_after_valid_cache_rejects_and_clears(monkeypatch,change):
    a=Auto();rev=Revision();m=install(a,rev);state=cp();a.classify('q',state)
    if change=='bad_hash':state['data']=2
    if change=='source':monkeypatch.setitem(SOURCE_HASHES,'kernel.py','ALTERED')
    if change=='schema':state['schema']='OTHER'
    if change=='runtime_method':monkeypatch.setattr(Auto,'classify',lambda *a: {'route':'LINEAR_DERIVATION'})
    if change=='helper':monkeypatch.setitem(globals(),'relation',lambda x:'ALTERED')
    if change=='helper_code':monkeypatch.setattr(relation,'__code__',(lambda text:'ALTERED').__code__)
    if change=='revision':rev.clean=False
    if change=='adapter':a.integrations.math.revision='legacy'
    if change=='source_disk':CHECKS['failed']=True
    with pytest.raises(ValueError):a.classify('q',state)
    assert m.closed and m.used==0 and not m.cache


def test_instance_method_or_class_change_rejects_captured_wrapper():
    a=Auto();m=install(a,Revision());wrapper=a.classify;a.classify=lambda *a:None
    with pytest.raises(ValueError):wrapper('q',None)
    assert m.closed


def test_missmutation_noexceptioncache_and_nonpure_oversize_uncached():
    a=Auto();m=install(a,Revision(),max_bytes=1024)
    for _ in range(2):
        with pytest.raises(ValueError,match='ORIGINAL_ERROR'):a.classify('error')
    assert not m.cache and a.calls==2
    for text in ('plugin','big'):
        a.classify(text);a.classify(text)
    assert a.calls==6 and m.public()['hits']==0
    with pytest.raises(ValueError,match='MUTATED_INPUT'):a.classify('mutate',cp())
    assert m.closed and not m.cache


def test_cap_eviction_close_and_no_crossinstance_reuse():
    a=Auto();m=install(a,Revision(),max_entries=1,max_bytes=1024)
    a.classify('one');a.classify('two');a.classify('one')
    assert m.public()['evictions']==2 and m.public()['serialized_bytes']<=1024
    b=Auto();n=install(b,Revision());b.classify('one');assert b.calls==1 and n.public()['hits']==0
    m.clear();assert not m.cache and m.used==0
    stale=a.classify;m.close();assert 'classify' not in a.__dict__
    with pytest.raises(ValueError):stale('one')

@pytest.mark.parametrize('bounds',[{'max_entries':True},{'max_entries':33},{'max_bytes':65537},{'max_bytes':True}])
def test_invalid_caps_reject(bounds):
    with pytest.raises(ValueError):install(Auto(),Revision(),**bounds)


def test_changed_frozen_loader_bytes_reject_and_no_crossworker(monkeypatch):
    a=Auto();rev=Revision();rev.sources={'dev.py':b'original'};m=install(a,rev);a.classify('q')
    rev.sources['dev.py']=b'changed'
    with pytest.raises(ValueError,match='LOADER_RUNTIME'):a.classify('q')
    assert m.closed
    b=Auto();n=install(b,Revision());b.classify('q');n.owner_pid=-1
    with pytest.raises(ValueError,match='WORKER_LIFETIME'):b.classify('q')


def test_full_source_or_valid_resealed_checkpoint_never_reuses_old_selection():
    a=Auto();m=install(a,Revision());a.classify('q',cp(1));a.classify('q',cp(2))
    assert a.calls==2 and m.public()['misses']==2
    assert len(m.cache)==2 and m.public()['serialized_bytes']<=65536


def test_dataclass_default_factory_sentinel_is_not_false_runtime_change():
    from dataclasses import dataclass,field
    from admission_memo import _capture_callable,_same_callable
    @dataclass
    class Dev:
        items:list=field(default_factory=list)
    capture=_capture_callable(Dev)
    assert _same_callable(Dev,capture)
    original=Dev.__init__.__defaults__
    Dev.__init__.__defaults__=('altered',)
    assert not _same_callable(Dev,capture)
    Dev.__init__.__defaults__=original
