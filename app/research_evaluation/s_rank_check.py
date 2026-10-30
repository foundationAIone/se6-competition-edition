"""Trusted synthetic parity check against exact original flat-bm25 code."""
from pathlib import Path
import ast,hashlib,json,sys
APP=Path(__file__).resolve().parents[1];LANE=APP.parent
sys.path.insert(0,str(APP));sys.path.insert(0,str(LANE/'linux-deps'))
import numpy as np
from rank_bm25 import BM25Okapi
from research_controls.official_bm25_s import rank

def run():
    path=LANE/'external/longmemeval/src/retrieval/run_retrieval.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='444c13d05787b26338b233ac10d953ea65c065f8ba1ecfeccb9ea938d129e87f'
    tree=ast.parse(path.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DenseRetrievalMaster')
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='run_flat_retrieval')
    scope={'np':np,'BM25Okapi':BM25Okapi}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),scope)
    tests=[('amber cabinet',['user: cabinet amber','assistant: blue shelves','unrelated dates']),
        ('Word',['word lower','Word upper','WORD caps']),('missing',['tie item','tie other','tie third'])]
    for query,corpus in tests:
        actual,scores=rank(query,corpus);expected=scope['run_flat_retrieval'](None,query,'flat-bm25',corpus)
        assert list(actual)==list(expected)
    print(json.dumps(dict(status='EXACT_OFFICIAL_FLAT_BM25_KERNEL_PARITY',synthetic_checks=len(tests),
        numpy=np.__version__,provider_calls=0,external_cases=0,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
if __name__=='__main__':run()
