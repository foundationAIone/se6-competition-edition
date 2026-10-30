"""Official flat-bm25 ranking kernel on complete all-role session documents.

Source: LongMemEval 9e0b455f4ef0e2ab8f2e582289761153549043fc,
src/retrieval/run_retrieval.py106-112, SHA256444c13d05787b26338b233ac10d953ea65c065f8ba1ecfeccb9ea938d129e87f.
The official user-only corpus/answer-marked IDs are deliberately NOT reused:
both methods receive full assistant/user content and opaque source aliases.
This is a declared custom corpus, not the official full benchmark invocation.
"""
from pathlib import Path
import hashlib,json,os
from research_memory.sessions_format import validate_history,render_session,canonicalbytes,session_sha256,history_sha256,history_spans

def require(ok,code):
    if not ok:raise ValueError(code)
def rank(query,corpus):
    import numpy as np
    from rank_bm25 import BM25Okapi
    tokenized_corpus=[doc.split(' ') for doc in corpus]
    bm25=BM25Okapi(tokenized_corpus)
    scores=bm25.get_scores(query.split(' '))
    return np.argsort(scores)[::-1],scores

class SessionMemory:
    def __init__(self,root,storage_byte_budget=134217728):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.storage_byte_budget=storage_byte_budget;self.history=None
    def ingest(self,history):
        self.history=validate_history(history)
        require(len(canonicalbytes(history))<=self.storage_byte_budget,'BM25_SOURCE_STORAGE_BOUND')
        return dict(status='COMPLETE_SOURCE_INGESTED',history_sha256=history_sha256(history),
            sessions=len(history['sessions']),provider_calls=0,epistemic_status='REPORTED_HISTORICAL_SOURCE')
    def save(self,path):
        target=Path(path).resolve();require(target.is_relative_to(self.root),'BM25_OWN_ROOT_ONLY')
        target.mkdir(parents=True,exist_ok=False)
        raw=canonicalbytes(self.history);require(len(raw)<=self.storage_byte_budget,'BM25_STORAGE_BOUND')
        with (target/'history.json').open('xb') as file:file.write(raw);file.flush();os.fsync(file.fileno())
        (target/'sha256').write_text(hashlib.sha256(raw).hexdigest())
        return dict(status='SAVED_REAL_SOURCE',history_sha256=history_sha256(self.history))
    def load(self,path):
        target=Path(path).resolve();require(target.is_relative_to(self.root),'BM25_OWN_ROOT_ONLY')
        raw=(target/'history.json').read_bytes()
        require(hashlib.sha256(raw).hexdigest()==(target/'sha256').read_text(),'BM25_COLD_SOURCE_HASH')
        self.history=validate_history(json.loads(raw))
        return dict(status='COLD_SOURCE_RESTORED',history_sha256=history_sha256(self.history))
    def retrieve(self,question,question_date=None,k=5):
        require(self.history is not None and type(question) is str and type(k) is int and 1<=k<=5,'BM25_QUERY_CONTRACT')
        corpus=[render_session(s) for s in self.history['sessions']]
        rankings,scores=rank(question,corpus);rows=[];hsha=history_sha256(self.history);spans=history_spans(self.history)
        seen=set()
        for index in rankings:
            i=int(index);session=self.history['sessions'][i]
            if session['session_id'] in seen:continue
            seen.add(session['session_id'])
            rows.append(dict(**session,source_ref=f'history:{hsha}:session:{i}:sha256:{session_sha256(session)}',
                content_sha256=session_sha256(session),history_sha256=hsha,session_index=i,score=float(scores[i]),source_offsets=spans[i]))
            if len(rows)>=k:break
        return dict(sessions=rows,trace=dict(selector='Official flat-bm25 score/space-tokenization/np.argsort kernel; all-role timestamped session corpus',
            history_sha256=hsha,query_sha256=hashlib.sha256(question.encode()).hexdigest(),
            question_date_supplied=question_date is not None,question_date_used_for_ranking=False,
            source_sessions=len(corpus),returned=len(rows),provider_calls=0))
