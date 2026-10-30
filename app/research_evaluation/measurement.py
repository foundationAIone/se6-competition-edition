"""Own-process resource measurements; unavailable descendants remain UNKNOWN."""
import os,sys,time,tracemalloc
_WINDOWS_RSS_READER=None

def own_peak_rss():
    global _WINDOWS_RSS_READER
    if sys.platform=='win32':
        try:
            if _WINDOWS_RSS_READER is not None:return _WINDOWS_RSS_READER()
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
                    ('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),
                    ('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
            kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
            kernel.GetCurrentProcess.restype=wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
            getprocess=kernel.GetCurrentProcess;getinfo=psapi.GetProcessMemoryInfo
            def reader():
                values=Counters();values.cb=ctypes.sizeof(values)
                return int(values.PeakWorkingSetSize) if getinfo(getprocess(),ctypes.byref(values),values.cb) else None
            _WINDOWS_RSS_READER=reader
            return reader()
        except (OSError,ImportError,AttributeError):return None
    try:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform=='darwin' else value*1024)
    except ImportError:return None

class Meter:
    def __init__(self):
        self.wall=time.perf_counter();self.cpu=time.process_time();tracemalloc.start()
    def read(self):
        return dict(wall_seconds=time.perf_counter()-self.wall,host_cpu_seconds=time.process_time()-self.cpu,
            peak_traced_python_bytes=tracemalloc.get_traced_memory()[1],peak_process_rss_bytes=own_peak_rss(),
            provider_calls=0,embedding_calls=0,subordinate_agent_calls=0,child_cpu_seconds=None,
            actual_invoice_usd=None,scope='Own process only. Initialization/index/query phases are separate; descendant CPU and invoice are UNKNOWN.')
