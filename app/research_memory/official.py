"""Optional registration using the actual official Memory base supplied by host.

The official base imports all benchmark backends and their dependencies. This
adapter does not install them, monkeypatch them, or silently replace that base.
The custom isolated JSON interface can use research_memory.Memory directly.
"""
from pathlib import Path
from .adapter import Memory

def register_with_official(memory_module):
    class SE6ReportedTextMemory(memory_module.Memory):
        memory_type=Memory.memory_type
        def __init__(self,memory_params):
            super().__init__(memory_params)
            expected={'root','context_char_budget','storage_byte_budget'}
            if set(memory_params)!=expected:raise ValueError('MEMORY_OFFICIAL_EXACT_CONFIG')
            self.backend=Memory(**memory_params)
        def insert(self,trajectory):self.backend.insert(trajectory)
        def query(self,query,query_image=None):return self.backend.query(query,query_image)
        def save_memory(self,output_dir):
            self.backend._inside(output_dir)  # Reject outside-root before official mkdir/write.
            return super().save_memory(output_dir)
        def _save_backend(self,output_dir):self.backend.save(Path(output_dir)/'se6-entity')
        def _load_backend(self,input_dir):self.backend.load(Path(input_dir)/'se6-entity')
    return memory_module.register_memory(SE6ReportedTextMemory)
