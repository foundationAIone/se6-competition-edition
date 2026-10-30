"""Deterministic BM25 + extractive chronological notes, no provider/embedding.

Indexes the SAME admitted complete text chunks as the SE6 adapter. It retains
ordinary persistent memory, full source text and notes; no evaluator access.
This is a custom conventional baseline, not the official dense RAG baseline.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,math,os,re

def require(ok,code):
    if not ok:raise ValueError(code)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def terms(text):return re.findall(r'[\w]+',text.casefold())

class Memory:
    memory_type='se6-custom-bm25-extractive-notes-v1'
    def __init__(self,*,root,context_char_budget=16384,storage_byte_budget=134217728):
        raw=Path(root);require(not any(p.is_symlink() for p in (raw,*raw.parents)),'CONTROL_LINKED_ROOT')
        self.root=raw.resolve()
        require(type(context_char_budget) is int and 1<=context_char_budget<=65536,'CONTEXT_BUDGET')
        require(type(storage_byte_budget) is int and 1<=storage_byte_budget<=1073741824,'STORAGE_BUDGET')
        self.root.mkdir(parents=True,exist_ok=True);self.context_char_budget=context_char_budget;self.storage_byte_budget=storage_byte_budget
        self.documents=[];self.notes=[];self.sources=[];self.last_trace=None
    def _inside(self,path):
        raw=Path(path);p=raw.resolve();require(p==self.root or p.is_relative_to(self.root),'CONTROL_OWN_ROOT_ONLY')
        require(not any(x.is_symlink() for x in (raw,*raw.parents)),'CONTROL_LINKED_PATH');return p
    def insert(self,trajectory):
        from research_memory.format import trajectory_chunks
        admitted=trajectory_chunks(trajectory)
        if admitted['trajectory_sha256'] in self.sources:return dict(status='ALREADY_INDEXED',provider_calls=0)
        old=(list(self.documents),list(self.notes),list(self.sources))
        for chunk in admitted['chunks']:
            self.documents.append(dict(text=chunk['text'],source_ref=chunk['source_ref'],chunk_sha256=chunk['chunk_sha256'],
                trajectory_sha256=admitted['trajectory_sha256'],order=len(self.documents)))
        self.sources.append(admitted['trajectory_sha256'])
        # Extractive notes are verbatim, not invented summaries. Full chunks
        # remain indexed, so notes cannot silently delete required evidence.
        note='\n'.join(d['text'][:220] for d in self.documents if d['trajectory_sha256']==admitted['trajectory_sha256'])
        self.notes.append(dict(source_sha256=admitted['trajectory_sha256'],text=note))
        self.documents.append(dict(text=note,source_ref='extractive-notes:'+admitted['trajectory_sha256'],
            chunk_sha256=hashlib.sha256(note.encode()).hexdigest(),trajectory_sha256=admitted['trajectory_sha256'],
            order=len(self.documents),kind='VERBATIM_EXTRACTIVE_NOTES'))
        try:require(len(canonical(self._state()))<=self.storage_byte_budget,'CONTROL_STORAGE_BUDGET_EXCEEDED')
        except BaseException:self.documents,self.notes,self.sources=old;raise
        return dict(status='INDEXED_HISTORICAL_TEXT',source_sha256=admitted['trajectory_sha256'],chunks=len(admitted['chunks']),
            provider_calls=0,embedding_calls=0,epistemic_status='REPORTED_HISTORICAL_EVIDENCE_NOT_WORLD_VERIFICATION')
    def _state(self):
        return dict(version=self.memory_type,context_char_budget=self.context_char_budget,
            storage_byte_budget=self.storage_byte_budget,documents=self.documents,notes=self.notes,sources=self.sources)
    def query(self,question,query_image=None):
        require(query_image is None,'UNSUPPORTED_MODALITY')
        require(type(question) is str and question.strip(),'QUESTION_REQUIRED')
        query=Counter(terms(question));docwords=[Counter(terms(d['text'])) for d in self.documents];n=len(docwords)
        avg=sum(sum(c.values()) for c in docwords)/max(n,1);scores=[]
        df={word:sum(word in c for c in docwords) for word in query}
        for index,counts in enumerate(docwords):
            length=sum(counts.values());score=0.0
            for word in query:
                freq=counts[word]
                if freq:score+=math.log(1+(n-df[word]+.5)/(df[word]+.5))*freq*2.2/(freq+1.2*(.25+.75*length/max(avg,1)))
            scores.append((score,index))
        chosen={};used=0
        # Ranked evidence plus immediate chronological neighbours preserves
        # action/state context needed for workflow and dynamic-state questions.
        for score,index in sorted(scores,key=lambda x:(-x[0],x[1])):
            if score<=0:continue
            for i in [index,index-1,index+1]:
                if not 0<=i<n or i in chosen:continue
                d=self.documents[i]
                if i!=index and d['trajectory_sha256']!=self.documents[index]['trajectory_sha256']:continue
                label='[REPORTED HISTORICAL SOURCE '+d['source_ref']+']\n'
                if used+len(label)>=self.context_char_budget:continue
                amount=min(len(d['text']),self.context_char_budget-used-len(label))
                if amount>0:chosen[i]=amount;used+=len(label)+amount
            if used>=self.context_char_budget:break
        values=[];remaining=self.context_char_budget;refs=[]
        for i in sorted(chosen):
            d=self.documents[i];label='[REPORTED HISTORICAL SOURCE '+d['source_ref']+']\n'
            # Keep the ranking-time allocation when restoring chronological
            # order; a preceding neighbour must not steal a top-ranked slice.
            value=label+d['text'][:chosen[i]];remaining-=len(value)
            if value:values.append({'type':'text','value':value});refs.append(d['source_ref'])
        self.last_trace=dict(version=self.memory_type,source_refs=refs,context_sha256=digest(values),
            context_characters=sum(len(v['value']) for v in values),provider_calls=0,embedding_calls=0,
            source_status='REPORTED_HISTORICAL_EVIDENCE',ordinary_memory_enabled=True)
        return values
    def save(self,path):
        p=self._inside(path);p.mkdir(parents=True,exist_ok=True);material=self._state();payload=dict(material=material,sha256=digest(material))
        target=p/'control-memory.json';temporary=p/'control-memory.pending';raw=canonical(payload)
        current=sum(x.stat().st_size for x in self.root.rglob('*') if x.is_file())
        previous=target.stat().st_size if target.exists() else 0
        require(current-previous+len(raw)<=self.storage_byte_budget,'CONTROL_DISK_BUDGET_EXCEEDED')
        with temporary.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temporary,target)
        require(sum(x.stat().st_size for x in self.root.rglob('*') if x.is_file())<=self.storage_byte_budget,'CONTROL_DISK_BUDGET_EXCEEDED')
        return dict(status='SAVED',source_sha256=payload['sha256'],provider_calls=0)
    def load(self,path):
        p=self._inside(path)/'control-memory.json';require(p.is_file() and not p.is_symlink(),'CONTROL_SAVED_STATE_REQUIRED')
        value=json.loads(p.read_bytes());j=value['material'];require(digest(j)==value['sha256'],'CONTROL_COLD_HASH')
        require(j['version']==self.memory_type and j['context_char_budget']==self.context_char_budget
            and j['storage_byte_budget']==self.storage_byte_budget,'CONTROL_COLD_CONFIG')
        self.documents=j['documents'];self.notes=j['notes'];self.sources=j['sources'];return dict(status='COLD_LOADED',provider_calls=0)
    def save_memory(self,path):return self.save(path)
    def _save_backend(self,path):return self.save(path)
    def _load_backend(self,path):return self.load(path)
