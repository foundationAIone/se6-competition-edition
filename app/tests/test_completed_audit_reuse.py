"""DEVELOPMENT-only HOST binding checks; no forged Native execution claim."""
from copy import deepcopy
import sys,types
import pytest
from hosted_judge import canonical_bridge as cb

class Engine:
    def score_local(self,value):return {'status':'LOCAL_CERTIFICATES_REPLAYED','checks':['DEV_ONLY']}

@pytest.fixture
def inputs(monkeypatch):
    m=types.ModuleType('src.workbench.core_revisions')
    m.SOURCE_HASHES={'kernel.py':'DEV_ONLY'}
    m.CANONICAL='DEV_ONLY';m.load_core=lambda:None;m.verify_traces=lambda *a:None
    monkeypatch.setitem(sys.modules,'src.workbench.core_revisions',m)
    return Engine(),'dev-task',{'old':'state'},{'new':'state'},{'receipts':['DEV_ONLY']},'DEV_ONLY_RAW_TEXT'

def test_completed_binding_covers_every_input_and_loaded_implementation(inputs,monkeypatch):
    original=cb.completed_audit_binding(*inputs)
    for i in range(1,6):
        changed=list(deepcopy(inputs));changed[i]='changed' if type(changed[i]) is str else {'changed':'value'}
        assert cb.completed_audit_binding(*changed)!=original
    monkeypatch.setattr(Engine,'score_local',lambda self,value:{'status':'DIFFERENT'})
    assert cb.completed_audit_binding(*inputs)!=original

def test_completed_audit_deepcopy_and_no_supplied_flags_grant_proof(inputs):
    audit={'status':'LOCAL_CERTIFICATES_REPLAYED','checks':['DEV_ONLY']}
    sink={'audit':audit,'audit_sha256':cb.digest(audit),'binding':cb.completed_audit_binding(*inputs),'origin':cb._COMPLETED_AUDIT_ORIGIN}
    value=cb.read_completed_audit(sink,*inputs)
    value['checks'].clear();assert sink['audit']['checks']==['DEV_ONLY']
    with pytest.raises(ValueError):cb.read_completed_audit({'verified':True},*inputs)
    with pytest.raises(ValueError):cb.read_completed_audit({},*inputs)
    with pytest.raises(ValueError):cb.read_completed_audit({**sink,'origin':'JSON cannot supply a capability'},*inputs)
    sink['audit']['checks'].append('forged')
    with pytest.raises(ValueError,match='binding changed'):cb.read_completed_audit(sink,*inputs)

def test_prepopulated_audit_sink_rejected_before_native_replay(inputs):
    e,task,before,cp,out,answer=inputs
    with pytest.raises(ValueError,match='fresh and empty'):
        cb.verify_native_checkpoint(e,task,cp,out,answer,before=before,audit_sink={'audit':{'status':'LOCAL_CERTIFICATES_REPLAYED'}})

def test_single_source_observation_per_memo_guard():
    from hosted_judge.admission_memo import install
    from test_admission_memo import Auto,Revision
    class CountedRevision(Revision):
        def __init__(self):super().__init__();self.calls=0
        def public(self):self.calls+=1;return super().public()
    rev=CountedRevision();a=Auto();m=install(a,rev);a.classify('DEV_ONLY')
    count=rev.calls;a.classify('DEV_ONLY')
    assert rev.calls==count+1 and m.stats['hits']==1
    m.close()

@pytest.mark.parametrize('kind',['missing','directory','symlink'])
def test_missing_or_nonregular_host_manifest_never_grants_audit_reuse(tmp_path,monkeypatch,kind):
    path=tmp_path/'manifest'
    if kind=='directory':path.mkdir()
    if kind=='symlink':
        path=types.SimpleNamespace(is_file=lambda:True,is_symlink=lambda:True)
    monkeypatch.setattr(cb,'_HOST_MANIFEST',path)
    with pytest.raises(ValueError,match='regular pinned HOST manifest'):cb.completed_audit_manifest_pin()
