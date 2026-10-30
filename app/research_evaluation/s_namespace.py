"""Versioned S worker mounts; reuses the already verified sealing primitives."""
from pathlib import Path
import argparse,os,resource,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_evaluation.namespace import bind,capdrop,seal_namespaces,run_checked,require

def setup(source,deps,workroot,arm,canary,*,development_repeat=False):
    setup_started=time.monotonic()
    require(sys.platform=='linux' and os.getuid()==0,'S_OS_USER_NAMESPACE_REQUIRED')
    source=Path(source).resolve(strict=True);deps=Path(deps).resolve(strict=True);work=Path(workroot).resolve(strict=True)
    require(source.name=='app' and (source/'research_memory/sessions.py').is_file(),'S_OS_SOURCE_CONTRACT')
    require(work.name.startswith('SE6-MEMORY-') and (work/'.SE6_MEMORY_DISPOSABLE').read_text()=='CUSTOM_DEVELOPMENT_MEMORY_ONLY','S_OS_REGISTERED_WORKROOT')
    require(arm in {'se6','bm25'} and not any(p.is_symlink() for p in [source,deps,work]),'S_OS_SCOPE')
    run_checked(['/usr/bin/mount','--make-rprivate','/'])
    jail=Path(tempfile.mkdtemp(prefix='SE6-MEMORY-S-JAIL-'))
    run_checked(['/usr/bin/mount','-t','tmpfs','-o','size=16m,nosuid,nodev','tmpfs',str(jail)])
    for path in ['usr/bin','usr/lib','lib','lib64','dev','app/research_evaluation','tmp']:(jail/path).mkdir(parents=True,exist_ok=True)
    bind('/usr/bin/python3.12',jail/'usr/bin/python3.12',readonly=True)
    (jail/'usr/bin/python3').symlink_to('python3.12')
    bind('/usr/lib/python3.12',jail/'usr/lib/python3.12',readonly=True)
    bind('/usr/lib/x86_64-linux-gnu',jail/'usr/lib/x86_64-linux-gnu',readonly=True)
    (jail/'lib/x86_64-linux-gnu').symlink_to('/usr/lib/x86_64-linux-gnu')
    (jail/'lib64/ld-linux-x86-64.so.2').symlink_to('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')
    bind('/dev/null',jail/'dev/null',readonly=False);bind('/dev/urandom',jail/'dev/urandom',readonly=True)
    bind(source/'research_memory',jail/'app/research_memory',readonly=True)
    bind(source/'research_controls',jail/'app/research_controls',readonly=True)
    core='awareness_native/work/qpre-calibration-integration-20261026/dev'
    bind(source/core,jail/('app/'+core),readonly=True)
    for name in ['__init__.py','measurement.py','isolation_worker.py','os_probe.py','s_worker.py']:
        bind(source/'research_evaluation'/name,jail/('app/research_evaluation/'+name),readonly=True)
    bind(deps,jail/'deps',readonly=True);bind(work,jail/'work',readonly=False)
    run_checked(['/usr/bin/mount','-t','tmpfs','-o','size=32m,nosuid,nodev,noexec','tmpfs',str(jail/'tmp')])
    os.chroot(jail);os.chdir('/')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128));resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
    resource.setrlimit(resource.RLIMIT_FSIZE,(134217728,134217728))
    capdrop();seal_namespaces();os.closerange(3,1024)
    env={'PATH':'/usr/bin','PYTHONPATH':'/app:/deps','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1',
        'HOME':'/work','TMPDIR':'/tmp','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
        'SE6_NAMESPACE_SETUP_SECONDS':str(time.monotonic()-setup_started),
        'SE6_NAMESPACE_EXEC_MONOTONIC':str(time.monotonic())}
    command=['/usr/bin/python3.12','-B','/app/research_evaluation/s_worker.py','--root','/work','--arm',arm,'--canary',canary]
    if development_repeat:command.append('--development-repeat')
    os.execve('/usr/bin/python3.12',command,env)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--deps',required=True)
    parser.add_argument('--workroot',required=True);parser.add_argument('--arm',required=True);parser.add_argument('--canary',required=True)
    parser.add_argument('--development-repeat',action='store_true')
    args=parser.parse_args();setup(args.source,args.deps,args.workroot,args.arm,args.canary,development_repeat=args.development_repeat)
