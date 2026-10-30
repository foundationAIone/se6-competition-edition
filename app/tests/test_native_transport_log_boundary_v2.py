"""Effect-free regression for the V1 post-commit transport logging defect.

The actual paired runner read boundary executes in a disposable child process.
Native/model dispatch is replaced by a labelled transport fixture; no provider,
Native transition, project mutation, or scored case is run or inspected.
"""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile
import pytest

APP=Path(__file__).resolve().parents[1]
LEGACY=APP.parents[1]/'competition-real-workflow-20261028T214113Z/app/hosted_judge/model_native_workflow.py'
LEGACY_SHA256='95788acf96b58d26cb090da4aa1685558111781adc10d3ef6629b0b7b8ae7fef'
PROPOSAL={'type':'act','path':'visible-unit.json','field':'limit','value':6,'prediction':{'expected_output':18}}


def child_case(kind):
    from hosted_judge import model_native_workflow as workflow
    from paired_workflow.runner import _install_read_boundary
    root=Path(tempfile.mkdtemp(prefix='SE6-NATIVE-QPRE-'))
    marker=root/'.SE6_NATIVE_QPRE_DISPOSABLE';marker.write_text('explicit-simulated-development-only-v1')
    workflow._register_native_root(root)
    # Keep the exact original bytes immutable; import is before the read boundary.
    legacy=None
    if kind=='legacy':
        assert hashlib.sha256(LEGACY.read_bytes()).hexdigest()==LEGACY_SHA256
        spec=importlib.util.spec_from_file_location('immutable_v1_transport_for_regression',LEGACY)
        legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    registration=root/workflow.ROOT_REGISTRATION
    if kind=='missing':registration.unlink()
    if kind=='corrupt':registration.write_text('{corrupt')
    if kind in ('wrong_parent','wrong_root','wrong_source','wrong_version'):
        value=json.loads(registration.read_bytes())
        field={'wrong_parent':'temp_parent','wrong_root':'root','wrong_source':'bridge_source_sha256','wrong_version':'version'}[kind]
        value[field]='wrong';registration.write_text(json.dumps(value))
    if kind=='wrong_marker':marker.write_text('wrong')
    if kind=='linked':
        target=root/'original-registration.json';registration.rename(target)
        try:registration.symlink_to(target)
        except OSError:
            # Windows systems without symlink privilege still exercise the
            # exact no-read branch, explicitly labelled as a link detector stub.
            registration.write_bytes(target.read_bytes())
            original=workflow._linked
            workflow._linked=lambda path:Path(path)==registration or original(path)
    specpath=root/'gateway-spec.json';specpath.write_text('{}')
    descriptor={'source_root':str(APP),'root':str(root),'output':str(root/'own-output'),
        'notes_directory':str(root/'own-notes'),'freeze_path':str(specpath),'world':'projectA',
        'gateway_config':{'root':str(root/'gateway'),'spec_path':str(specpath)}}
    calls=[]
    def controlled(*args,**kwargs):
        calls.append(args)
        if kind=='timeout':raise subprocess.TimeoutExpired(args[0],120,output=b'private partial stdout',stderr=b'private partial stderr')
        return subprocess.CompletedProcess(args[0],7 if kind=='nonzero' else 0,
            'private failed stdout' if kind=='nonzero' else '{"goal":true,"actual_effects":1,"record_kind":"TEST_ONLY_TRANSPORT_FIXTURE"}',
            'private stderr evidence')
    workflow.subprocess.run=controlled
    boundary=_install_read_boundary(descriptor)
    # Reproduce the actual uncached cold process condition. Environment changes
    # after registration cannot expand or relocate the accepted transport root.
    tempfile.tempdir=None
    os.environ['TEMP']=str(root.parent/'FORGED_TEMP_OUTSIDE_BOUNDARY')
    os.environ['TMP']=str(root.parent/'FORGED_TMP_OUTSIDE_BOUNDARY')
    result={'root':str(root),'kind':kind,'actual_boundary':boundary,
        'native_dispatches':0,'provider_calls':0,'project_effects':0}
    try:
        if kind=='legacy':
            legacy._private_stage_log(root,'run','projectA',1,PROPOSAL,{'returncode':0},'private stdout','private stderr')
            raise AssertionError('Old uncached probe unexpectedly accepted')
        value=workflow._command('run',root=root,world='projectA',phase=1,proposal=PROPOSAL)
        result.update(status='COMPLETED',value=value,transport_calls=len(calls),tempfile_remained_uncached=tempfile.tempdir is None)
        records=list((root/'model-stage-logs').glob('*.json'));assert len(records)==1
        record=json.loads(records[0].read_bytes());stem=records[0].stem
        stdout=(records[0].parent/(stem+'.stdout')).read_bytes();stderr=(records[0].parent/(stem+'.stderr')).read_bytes()
        assert hashlib.sha256(stdout).hexdigest()==record['stdout_sha256']
        assert hashlib.sha256(stderr).hexdigest()==record['stderr_sha256']
        assert workflow.digest(record)==value['private_evidence_sha256']
        assert 'private stderr' not in json.dumps(value) and str(root) not in json.dumps(value)
        result['private_log_integrity']='VERIFIED'
    except (ValueError,json.JSONDecodeError) as error:
        result.update(status='REJECTED',error_code=str(error),transport_calls=len(calls),
            logs_created=(root/'model-stage-logs').exists(),tempfile_remained_uncached=tempfile.tempdir is None)
    print(json.dumps(result,sort_keys=True))


def run_child(kind):
    child=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--child',kind],
        cwd=APP,capture_output=True,text=True,timeout=15,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    assert child.returncode==0,child.stderr
    value=json.loads(child.stdout)
    # The child has exited; clean only the exact verified disposable target.
    root=Path(value['root']).resolve(strict=True)
    assert root.parent==Path(tempfile.gettempdir()).resolve(strict=True) and root.name.startswith('SE6-NATIVE-QPRE-')
    shutil.rmtree(root)
    return value


def test_preserved_v1_exact_source_reproduces_uncached_temp_probe_failure_under_actual_boundary():
    value=run_child('legacy')
    assert value['status']=='REJECTED' and value['error_code']=='PILOT_SOLVER_FILE_SCOPE_DENIED'
    assert value['actual_boundary']['status']=='AUDIT_READ_BOUNDARY_VERIFIED'
    assert not value['logs_created'] and value['transport_calls']==0


@pytest.mark.parametrize('kind,status',[('success',None),('nonzero','FAILED_CLOSED'),('timeout','INTERRUPTED')])
def test_v2_private_logs_complete_without_temp_probe_or_retry_under_actual_boundary(kind,status):
    value=run_child(kind)
    assert value['status']=='COMPLETED' and value['private_log_integrity']=='VERIFIED'
    assert value['tempfile_remained_uncached'] and value['transport_calls']==1
    assert value['native_dispatches']==value['provider_calls']==value['project_effects']==0
    if status:
        assert value['value']['status']==status and value['value']['actual_effects'] is None
        assert value['value']['retry_permitted'] is False
    else:assert value['value']['goal'] is True  # TEST_ONLY return fixture, not an actual goal claim.


@pytest.mark.parametrize('kind',['missing','corrupt','wrong_parent','wrong_root','wrong_source','wrong_version','wrong_marker','linked'])
def test_unregistered_or_mismatched_roots_fail_closed_without_creating_logs(kind):
    value=run_child(kind)
    assert value['status']=='REJECTED' and not value['logs_created']
    assert value['tempfile_remained_uncached'] and value['native_dispatches']==0


def test_registration_rejects_external_parent_and_duplicate_registration(tmp_path):
    from hosted_judge import model_native_workflow as workflow
    external=tmp_path/'SE6-NATIVE-QPRE-visible-unit';external.mkdir()
    (external/'.SE6_NATIVE_QPRE_DISPOSABLE').write_text('explicit-simulated-development-only-v1')
    with pytest.raises(ValueError,match='REGISTERED_TEMP_PARENT'):workflow._register_native_root(external)
    assert not (external/workflow.ROOT_REGISTRATION).exists()
    root=Path(tempfile.mkdtemp(prefix='SE6-NATIVE-QPRE-'))
    (root/'.SE6_NATIVE_QPRE_DISPOSABLE').write_text('explicit-simulated-development-only-v1')
    try:
        workflow._register_native_root(root)
        with pytest.raises(FileExistsError):workflow._register_native_root(root)
    finally:
        assert root.parent==Path(tempfile.gettempdir()).resolve(strict=True)
        shutil.rmtree(root)


if __name__=='__main__':
    sys.path.insert(0,str(APP));child_case(sys.argv[2])
