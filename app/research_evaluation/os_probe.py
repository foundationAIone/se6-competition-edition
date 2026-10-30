"""Kernel checks performed inside the sealed child, before Python audit."""
from pathlib import Path
import ctypes,errno,os

def verify_kernel_boundary(canary):
    if os.name!='posix':raise ValueError('OS_SANDBOX_LINUX_REQUIRED')
    libc=ctypes.CDLL(None,use_errno=True)
    class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
    class Data(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
    header=Header(0x20080522,0);data=(Data*2)()
    if libc.capget(ctypes.byref(header),ctypes.byref(data))!=0 or any(d.effective or d.permitted or d.inheritable for d in data):
        raise ValueError('OS_SANDBOX_CAPABILITIES_NOT_DROPPED')
    if libc.prctl(39,0,0,0,0)!=1 or libc.prctl(27,0,0,0,0)!=15:raise ValueError('OS_SANDBOX_PRIVILEGE_LOCKS_MISSING')
    if libc.prctl(21,0,0,0,0)!=2:raise ValueError('OS_SANDBOX_SECCOMP_MISSING')
    ctypes.set_errno(0)
    if libc.unshare(0)!=-1 or ctypes.get_errno()!=errno.EPERM:raise ValueError('OS_NAMESPACE_REENTRY_NOT_DENIED')
    if Path('/mnt/c').exists() or Path('/proc').exists() or Path('/home').exists():raise ValueError('OS_SANDBOX_HOST_TREE_VISIBLE')
    try:Path(canary).read_bytes()
    except FileNotFoundError:pass
    else:raise ValueError('OS_EVALUATOR_CANARY_VISIBLE')
    try:list(Path(canary).parent.iterdir())
    except FileNotFoundError:pass
    else:raise ValueError('OS_EVALUATOR_DIRECTORY_VISIBLE')
    try:Path('/app/research_controls/.OS_READONLY_PROBE').write_text('must-fail')
    except OSError as error:
        if error.errno!=errno.EROFS:raise ValueError('OS_SOURCE_READONLY_PROBE_UNEXPECTED') from None
    else:raise ValueError('OS_SOURCE_WAS_WRITABLE')
    return dict(kind='LINUX_USER_MOUNT_NET_CHROOT_CAPDROP_V1',kernel_boundary='VERIFIED',
        evaluator_file='NOT_MOUNTED',evaluator_directory='NOT_MOUNTED',source_write='EROFS',
        effective_permitted_inheritable_capabilities=0,no_new_privs=True,securebits_locked=True,
        seccomp_filter=True,native_namespace_reentry='EPERM',
        host_proc_mounted=False,host_drive_mounted=False,network='PRIVATE_UNSHARE_NET_NAMESPACE_NO_CAP_NET_ADMIN',
        metadata_echoed=False)
