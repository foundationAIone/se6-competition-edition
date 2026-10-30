"""Narrow Linux user/mount/network namespace + chroot for memory adapters.

Run --setup ONLY below the declared unshare command. No host evaluator tree is
mounted. This grants no model/paid authority. It is a local execution boundary.
"""
from pathlib import Path
import argparse,ctypes,json,os,resource,subprocess,sys,tempfile

def require(ok,code):
    if not ok:raise ValueError(code)

def run_checked(words):
    result=subprocess.run(words,capture_output=True,text=True,timeout=15)
    require(result.returncode==0,'OS_SANDBOX_SETUP_FAILED')

def bind(source,target,*,readonly):
    source=Path(source).resolve(strict=True);target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.is_dir():target.mkdir(exist_ok=True)
    else:target.touch(exist_ok=False)
    run_checked(['/usr/bin/mount','--bind',str(source),str(target)])
    if readonly:run_checked(['/usr/bin/mount','-o','remount,bind,ro,nosuid,nodev',str(target)])

def capdrop():
    libc=ctypes.CDLL(None,use_errno=True)
    require(libc.prctl(38,1,0,0,0)==0,'OS_NO_NEW_PRIVS_FAILED')
    # NOROOT + NO_SETUID_FIXUP and both locks preserve zero capabilities on
    # exec, even though the isolated user-namespace UID is zero.
    require(libc.prctl(28,15,0,0,0)==0,'OS_SECUREBITS_FAILED')
    class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
    class Data(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
    header=Header(0x20080522,0);data=(Data*2)()
    require(libc.capset(ctypes.byref(header),ctypes.byref(data))==0,'OS_CAPABILITY_DROP_FAILED')

def seal_namespaces():
    """Inherited kernel filter prevents re-gaining capabilities in nested userns."""
    libc=ctypes.CDLL(None,use_errno=True)
    class Filter(ctypes.Structure):_fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint32)]
    class Program(ctypes.Structure):_fields_=[('length',ctypes.c_ushort),('filter',ctypes.POINTER(Filter))]
    deny=0x00050000|1;allow=0x7fff0000
    rules=[(0x20,0,0,4),(0x15,1,0,0xc000003e),(0x06,0,0,0x80000000),
        (0x20,0,0,0),(0x45,0,1,0x40000000),(0x06,0,0,deny)]
    # x86_64 only. No mount/namespace/privileged cross-process bypasses remain.
    for nr in [272,308,165,166,155,161,304,101,310,311,321,323,435,246,169,175,313,176,425,428,429,430,431,432,442]:
        rules.extend([(0x15,0,1,nr),(0x06,0,0,deny)])
    rules.extend([(0x15,0,3,56),(0x20,0,0,16),(0x45,0,1,0x7e020080),(0x06,0,0,deny),(0x06,0,0,allow)])
    array=(Filter*len(rules))(*(Filter(*r) for r in rules));program=Program(len(rules),array)
    require(libc.prctl(22,2,ctypes.byref(program),0,0)==0,'OS_SECCOMP_FILTER_FAILED')

def setup(source,deps,workroot,adapter,canary):
    require(sys.platform=='linux' and os.getuid()==0,'OS_USER_NAMESPACE_REQUIRED')
    source=Path(source).resolve(strict=True);deps=Path(deps).resolve(strict=True);work=Path(workroot).resolve(strict=True)
    require(source.name=='app' and (source/'research_memory').is_dir() and (source/'research_controls').is_dir(),'OS_SOURCE_SCOPE')
    require(work.name.startswith('SE6-MEMORY-') and (work/'.SE6_MEMORY_DISPOSABLE').read_text()=='CUSTOM_DEVELOPMENT_MEMORY_ONLY','OS_REGISTERED_WORKROOT')
    require(not any(p.is_symlink() for p in [source,deps,work]),'OS_LINKED_ROOT')
    require(adapter in {'se6','conventional'},'OS_ADAPTER_ENUM')
    run_checked(['/usr/bin/mount','--make-rprivate','/'])
    jail=Path(tempfile.mkdtemp(prefix='SE6-MEMORY-JAIL-'))
    run_checked(['/usr/bin/mount','-t','tmpfs','-o','size=16m,nosuid,nodev','tmpfs',str(jail)])
    for path in ['usr/bin','usr/lib','lib','lib64','dev','app/research_evaluation','tmp']:(jail/path).mkdir(parents=True,exist_ok=True)
    bind('/usr/bin/python3.12',jail/'usr/bin/python3.12',readonly=True)
    (jail/'usr/bin/python3').symlink_to('python3.12')
    bind('/usr/lib/python3.12',jail/'usr/lib/python3.12',readonly=True)
    bind('/usr/lib/x86_64-linux-gnu',jail/'usr/lib/x86_64-linux-gnu',readonly=True)
    (jail/'lib/x86_64-linux-gnu').symlink_to('/usr/lib/x86_64-linux-gnu')
    (jail/'lib64/ld-linux-x86-64.so.2').symlink_to('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')
    bind('/dev/null',jail/'dev/null',readonly=False)
    bind('/dev/urandom',jail/'dev/urandom',readonly=True)
    bind(source/'research_memory',jail/'app/research_memory',readonly=True)
    bind(source/'research_controls',jail/'app/research_controls',readonly=True)
    core='awareness_native/work/qpre-calibration-integration-20261026/dev'
    bind(source/core,jail/('app/'+core),readonly=True)
    for name in ['__init__.py','measurement.py','isolation_worker.py','os_probe.py']:
        bind(source/'research_evaluation'/name,jail/('app/research_evaluation/'+name),readonly=True)
    bind(deps,jail/'deps',readonly=True)
    bind(work,jail/'work',readonly=False)
    run_checked(['/usr/bin/mount','-t','tmpfs','-o','size=32m,nosuid,nodev,noexec','tmpfs',str(jail/'tmp')])
    os.chroot(jail);os.chdir('/')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128));resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
    resource.setrlimit(resource.RLIMIT_FSIZE,(134217728,134217728))
    capdrop();seal_namespaces();os.closerange(3,1024)
    environment={'PATH':'/usr/bin','PYTHONPATH':'/app:/deps','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','HOME':'/work','TMPDIR':'/tmp',
        'SE6_OS_SANDBOX_REQUIRED':'1'}
    os.execve('/usr/bin/python3.12',['/usr/bin/python3.12','-B','/app/research_evaluation/isolation_worker.py',
        '--root','/work','--adapter',adapter,'--canary',canary],environment)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--setup',action='store_true');parser.add_argument('--source',required=True)
    parser.add_argument('--deps',required=True);parser.add_argument('--workroot',required=True);parser.add_argument('--adapter',required=True);parser.add_argument('--canary',required=True)
    args=parser.parse_args();require(args.setup,'OS_SANDBOX_SETUP_ONLY')
    setup(args.source,args.deps,args.workroot,args.adapter,args.canary)
