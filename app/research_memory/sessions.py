"""Lossless session reports attached to actual SE6 provisional Entity memory.

One memory record denotes one complete source-history collection. Its active
lifecycle gates access to every member session. Session payloads are immutable
content-addressed attachments, not an independent retrieval/index database.
Selection consumes a source-pinned, retained development method preference;
without an applicable preference it preserves the original lexical rule.
No per-session lifecycle, general learned ranking or verified World fact is claimed.
"""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json,os,shutil,time,stat
from contextlib import contextmanager
from .adapter import Memory,_write,_sha,_read
from .format import tokens,require,encode,digest
from .sessions_format import VERSION,canonicalbytes,validate_history,history_sha256,session_sha256,render_session,history_spans
from . import entity
from . import session_selection as selection

CHUNK_BYTES=65536
RESERVE_BYTES=2*1024*1024

class SessionMemory(Memory):
    memory_type='se6_source_reported_session_collection_v1'
    def __init__(self,root,*,storage_byte_budget=134217728):
        self.phase_metrics={};self._validated_payloads={}
        super().__init__(root,context_char_budget=16384,storage_byte_budget=storage_byte_budget)
        self.payload_root=self.root/'session-sources'
        self.last_trace=None
        self.last_retrieval=None

    def _sources(self):
        return {**super()._sources(),**{'session:'+p.name:_sha(p) for p in
            (Path(__file__),Path(__file__).with_name('sessions_format.py'),*selection.source_files())}}

    @contextmanager
    def _phase(self,name,scope):
        wall,cpu=time.perf_counter(),time.process_time()
        try:yield
        finally:
            m=self.phase_metrics.setdefault(name,dict(wall_seconds=0.0,cpu_seconds=0.0,calls=0,scope=scope))
            m['wall_seconds']+=time.perf_counter()-wall;m['cpu_seconds']+=time.process_time()-cpu;m['calls']+=1

    def _verify(self):
        with self._phase('source_validation_hashing','Inclusive source/store reconstruction and current storage accounting; other named phases may contain this validation and must not be blindly summed.'):
            return super()._verify()

    def _bytes(self):
        # Fresh accounting on every call, one stat per entry. No mtime/size
        # cache and no skipped source/integrity check; links fail closed.
        total=0;pending=[self.root]
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    info=entry.stat(follow_symlinks=False)
                    require(not stat.S_ISLNK(info.st_mode) and not (getattr(info,'st_file_attributes',0)&0x400),'MEMORY_STORAGE_LINK_REJECTED')
                    if stat.S_ISDIR(info.st_mode):pending.append(entry.path)
                    elif stat.S_ISREG(info.st_mode):total+=info.st_size
                    else:raise ValueError('MEMORY_STORAGE_SPECIAL_FILE_REJECTED')
        return total

    def _payload(self,source,expected_manifest):
        with self._phase('source_validation_hashing','Every payload read freshly hashes manifest and all chunk bytes; byte-identical validated source may reuse schema/span validation, never file integrity.'):
            return self._payload_checked(source,expected_manifest)

    def _payload_checked(self,source,expected_manifest):
        require(type(source) is str and len(source)==64 and all(c in '0123456789abcdef' for c in source),'SESSION_SOURCE_HASH')
        directory=self.payload_root/source;path=directory/'manifest.json'
        require(not path.is_symlink() and path.is_file(),'SESSION_PAYLOAD_MANIFEST_PIN')
        manifest_raw=path.read_bytes();require(hashlib.sha256(manifest_raw).hexdigest()==expected_manifest,'SESSION_PAYLOAD_MANIFEST_PIN')
        manifest=json.loads(manifest_raw)
        require(manifest['version']==VERSION and manifest['source_sha256']==source,'SESSION_PAYLOAD_MANIFEST')
        pieces=[];offset=0
        for index,chunk in enumerate(manifest['chunks']):
            require(set(chunk)=={'name','sha256','start','end'} and chunk['name']==f'{index:06d}.chunk'
                and chunk['start']==offset and type(chunk['end']) is int and chunk['end']>offset,'SESSION_CHUNK_ORDER_OR_OFFSET')
            part=directory/chunk['name']
            require(not part.is_symlink() and part.is_file(),'SESSION_CHUNK_CONTENT_PIN')
            data=part.read_bytes();require(hashlib.sha256(data).hexdigest()==chunk['sha256'],'SESSION_CHUNK_CONTENT_PIN')
            require(len(data)==chunk['end']-offset and len(data)<=CHUNK_BYTES,'SESSION_CHUNK_LENGTH')
            pieces.append(data);offset=chunk['end']
        raw=b''.join(pieces)
        require(offset==manifest['bytes'] and hashlib.sha256(raw).hexdigest()==source,'SESSION_LOSSLESS_SOURCE_HASH')
        history=json.loads(raw);cache_key=(source,expected_manifest)
        if self._validated_payloads.get(cache_key)!=(raw,manifest_raw):
            validate_history(history)
            require(canonicalbytes(history)==raw and len(history['sessions'])==manifest['session_count'],'SESSION_EXACT_SOURCE_RECONSTRUCTION')
            require(manifest['session_spans']==history_spans(history),'SESSION_SOURCE_SPAN_MANIFEST')
            self._validated_payloads[cache_key]=(raw,manifest_raw)
        return history,manifest

    def _collections(self,snapshot):
        active=snapshot.state.memory.active_at(datetime.now(UTC));active_ids={r.memory_id for r in active};events={e.event_id:e for e in snapshot.historical_events}
        results=[]
        for record in snapshot.state.memory.records:
            if not record.subject.startswith('session_history:') or record.status.value!='PROVISIONAL' or record.epistemic_status.value!='reported':continue
            if record.memory_id not in active_ids:continue
            material=json.loads(record.content_summary);source=material['source_sha256']
            require(material['version']==VERSION and record.subject=='session_history:'+source,'SESSION_MEMORY_MANIFEST')
            require('collection_sha256:'+source in record.evidence_references and
                'payload_manifest_sha256:'+material['payload_manifest_sha256'] in record.evidence_references,'SESSION_MEMORY_PROVENANCE')
            source_events=[events[x] for x in record.source_event_ids if x in events]
            require(any(isinstance(e.payload,entity.MemoryPayload) and e.payload.operation is entity.MemoryEventOperation.CANDIDATE
                and e.payload.content_summary==record.content_summary and e.provenance is entity.ObservationProvenance.EXTERNAL_RETRIEVED
                and e.epistemic_status is entity.EpistemicStatus.REPORTED for e in source_events),'SESSION_ACTUAL_MEMORY_SOURCE_EVENT')
            history,manifest=self._payload(source,material['payload_manifest_sha256'])
            require(len(history['sessions'])==material['session_count'] and digest(history['source_id'])==material['source_id_sha256'],'SESSION_HISTORY_BINDING')
            results.append((record,history,manifest))
        return results

    def admit_method_report(self,report):
        """Retain independently pinned development evidence, without World trust."""
        require(not self.read_only_loaded,'MEMORY_LOADED_CHECKPOINT_QUERY_ONLY')
        admitted=selection.read_admitted_development_report()
        require(canonicalbytes(report)==canonicalbytes(admitted),'METHOD_REPORT_CALLER_ECHO_REJECTED')
        pin=selection.admitted_report_pin();snapshot=self._verify();subject='retrieval_method_policy:'+pin
        if any(r.subject==subject for r in snapshot.state.memory.records):
            require(any(r.subject==subject for r in snapshot.state.memory.active_at(datetime.now(UTC))),'METHOD_POLICY_WITHDRAWN_REQUIRES_EXPLICIT_LIFECYCLE')
            return dict(status='ALREADY_RETAINED_METHOD_REPORT',report_sha256=pin)
        material=selection.policy_material(admitted)
        with self._phase('durable_writes','Actual Entity commit including its required transaction/audit; non-authorizing development policy, not benchmark truth.'):
            step=entity.commit_candidate(self.store,subject=subject,text=encode(material).decode(),
                refs=['development_report_sha256:'+pin,'development_capture_sha256:'+admitted['old_capture_sha256']],key=subject)
        self._verify()
        return dict(status='PROVISIONAL_REPORTED_METHOD_POLICY_RETAINED',method=material['method'],report_sha256=pin,
            receipt_id=step.receipt.receipt_id,entity_state_id=step.receipt.state_after_id,authority_effect='NONE')

    def _selected_method(self,snapshot,collections):
        active=snapshot.state.memory.active_at(datetime.now(UTC))
        policies=[r for r in active if r.subject.startswith('retrieval_method_policy:')]
        if not policies:return selection.LEGACY,dict(status='NO_ACTIVE_RETAINED_POLICY_LEGACY_EXPLICIT',authority_effect='NONE')
        require(len(policies)==1,'METHOD_POLICY_AMBIGUOUS')
        report=selection.read_admitted_development_report();pin=selection.admitted_report_pin();record=policies[0];material=json.loads(record.content_summary)
        require(canonicalbytes(material)==canonicalbytes(selection.policy_material(report)),'METHOD_POLICY_EXACT_REPORT_BINDING')
        require(record.status.value=='PROVISIONAL' and record.epistemic_status.value=='reported'
            and material['report_sha256']==pin and material['representation_version']==VERSION
            and material['method']==report['recommended_method'] and material['scope']==selection.SCOPE
            and record.subject=='retrieval_method_policy:'+pin and 'development_report_sha256:'+pin in record.evidence_references,'METHOD_POLICY_BINDING')
        events={e.event_id:e for e in snapshot.historical_events}
        require(any(x in events and isinstance(events[x].payload,entity.MemoryPayload)
            and events[x].payload.operation is entity.MemoryEventOperation.CANDIDATE
            and events[x].payload.content_summary==record.content_summary
            and events[x].provenance is entity.ObservationProvenance.EXTERNAL_RETRIEVED
            and events[x].epistemic_status is entity.EpistemicStatus.REPORTED for x in record.source_event_ids),'METHOD_POLICY_ACTUAL_SOURCE_EVENT')
        # The report supports this source-reported task representation only.
        # Do not silently apply a dataset-scoped preference to arbitrary history.
        if collections and not all(h.get('provenance',{}).get('dataset_revision')==report['dataset_revision'] for _,h,_ in collections):
            return selection.LEGACY,dict(status='RETAINED_POLICY_INAPPLICABLE_SOURCE_TASK_LEGACY_EXPLICIT',
                memory_id=record.memory_id,report_sha256=pin,authority_effect='NONE')
        return material['method'],dict(status='ACTIVE_SOURCE_PINNED_PROVISIONAL_DEVELOPMENT_POLICY_CONSUMED',method=material['method'],
            report_sha256=pin,memory_id=record.memory_id,source_event_ids=list(record.source_event_ids),authority_effect='NONE')

    def ingest(self,history):
        require(not self.read_only_loaded,'MEMORY_LOADED_CHECKPOINT_QUERY_ONLY');validate_history(history)
        start,cpu=time.perf_counter(),time.process_time();before=self._verify();source=history_sha256(history)
        collections=self._collections(before)
        for record,old,_ in collections:
            if history_sha256(old)==source:
                return dict(status='ALREADY_ADMITTED_NO_MUTATION',source_sha256=source,entity_state_id=before.state.entity_state_id)
            require(old['source_id']!=history['source_id'],'SESSION_SOURCE_ID_CHANGED_REQUIRES_EXPLICIT_LIFECYCLE')
        require(not any(r.subject=='session_history:'+source for r in before.state.memory.records),'SESSION_WITHDRAWN_SOURCE_REQUIRES_EXPLICIT_LIFECYCLE')
        require(len(before.state.memory.records)+1<=384,'MEMORY_RECORD_BUDGET')
        raw=canonicalbytes(history);directory=self.payload_root/source
        require(not directory.exists(),'SESSION_PARTIAL_ADMISSION_REQUIRES_RECONCILIATION')
        require(self._bytes()+len(raw)+RESERVE_BYTES<=self.storage_byte_budget,'SESSION_PRECOMMIT_STORAGE_RESERVE')
        directory.mkdir(parents=True,exist_ok=False);chunks=[]
        for index,start_offset in enumerate(range(0,len(raw),CHUNK_BYTES)):
            data=raw[start_offset:start_offset+CHUNK_BYTES];name=f'{index:06d}.chunk'
            with (directory/name).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            chunks.append(dict(name=name,sha256=hashlib.sha256(data).hexdigest(),start=start_offset,end=start_offset+len(data)))
        manifest=dict(version=VERSION,source_sha256=source,bytes=len(raw),session_count=len(history['sessions']),chunks=chunks,
            offset_frame='Canonical public history UTF-8 projection; raw evaluator labels excluded before admission',session_spans=history_spans(history))
        _write(directory/'manifest.json',manifest);manifest_pin=_sha(directory/'manifest.json')
        self._payload(source,manifest_pin)
        material=dict(version=VERSION,source_sha256=source,payload_manifest_sha256=manifest_pin,
            source_id_sha256=digest(history['source_id']),session_count=len(history['sessions']),scope='REPORTED_HISTORICAL_COLLECTION_NOT_WORLD_VERIFIED')
        with self._phase('durable_writes','Actual Entity source-history transaction and required commit audit.'):
            step=entity.commit_candidate(self.store,subject='session_history:'+source,text=encode(material).decode(),
                refs=['collection_sha256:'+source,'payload_manifest_sha256:'+manifest_pin],key='session_history:'+source)
        after=self._verify();require(any(history_sha256(h)==source for _,h,_ in self._collections(after)),'SESSION_ADMISSION_NOT_VISIBLE')
        self.last_insert=dict(status='ACTUAL_ENTITY_PROVISIONAL_REPORTED_COLLECTION_ADMITTED',source_sha256=source,
            payload_manifest_sha256=manifest_pin,session_count=len(history['sessions']),turn_count=sum(len(s['turns']) for s in history['sessions']),
            source_bytes=len(raw),chunk_count=len(chunks),receipt_id=step.receipt.receipt_id,entity_id=after.state.identity.instance_id,
            entity_state_id=after.state.entity_state_id,entity_version=after.state.state_version,
            wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,storage_bytes=self._bytes(),
            provider_calls=0,world_effects=0)
        return self.last_insert

    def retrieve(self,question,question_date=None,k=5):
        require(type(question) is str and 1<=len(question)<=16000,'SESSION_QUERY_TEXT')
        require(question_date is None or type(question_date) is str,'SESSION_QUERY_DATE')
        require(type(k) is int and 0<=k<=5,'SESSION_RETRIEVAL_ALLOWANCE')
        start,cpu=time.perf_counter(),time.process_time();snapshot=self._verify();collections=self._collections(snapshot)
        method,policy=self._selected_method(snapshot,collections);candidates=[];available_ids=set();occurrences=0
        with self._phase('representation_index_build','Render complete source-validated sessions and source/session/turn membership mapping; BM25 index construction itself is included in candidate kernel timing.'):
            for record,history,manifest in collections:
                source=manifest['source_sha256']
                for index,session in enumerate(history['sessions']):
                    span=manifest['session_spans'][index];sid=session['session_id'];available_ids.add(sid);occurrences+=1
                    candidates.append(dict(index=index,sid=sid,pin=span['sha256'],source=source,session=session,
                        record=record,span=span,text=render_session(session)))
        with self._phase('candidate_generation_ranking','Includes actual shared BM25 index construction+scoring+ordering on each call, or explicit legacy overlap; neither method caches a BM25 index here.'):
            if method==selection.BM25 and candidates:
                rankings=selection.bm25_candidates(question,[row['text'] for row in candidates])
            else:
                query_tokens=tokens(question);rankings=[(i,len(query_tokens & tokens(row['text']))) for i,row in enumerate(candidates)]
                rankings=sorted([(i,s) for i,s in rankings if s>0],key=lambda item:(-item[1],candidates[item[0]]['index'],candidates[item[0]]['sid'],candidates[item[0]]['source']))
        selected=[];consumed=[];returned_ids=set();duplicates=0
        with self._phase('source_retrieval_context_packing','Resolve capability indices through authenticated source/session mapping; complete messages are returned, with five-unique-session dedup and exact spans.'):
            for candidate_index,score in rankings:
                if len(selected)>=k:break
                require(type(candidate_index) is int and 0<=candidate_index<len(candidates),'METHOD_CANDIDATE_MAPPING')
                row=candidates[candidate_index];sid=row['sid']
                if sid in returned_ids:duplicates+=1;continue
                returned_ids.add(sid);index,pin,source,session,record,span=(row[x] for x in ['index','pin','source','session','record','span'])
                source_ref=f'session-report:{source}:session:{index}:sha256:{pin}'
                selected.append({**session,'source_ref':source_ref,'content_sha256':pin,'history_sha256':source,'session_index':index,'score':score,'source_offsets':span})
                consumed.append(dict(session_id=sid,session_index=index,session_sha256=pin,source_ref=source_ref,
                    memory_id=record.memory_id,source_event_ids=list(record.source_event_ids),evidence_references=list(record.evidence_references),score=score))
        self.last_trace=dict(version=VERSION,consumer='Actual EntityMemoryState.active_at -> authenticated collection/session mapping -> retained task-method preference -> executed retrieval capability -> source-bound unique selection',
            method=method,method_policy=policy,
            scoring='Shared official flat-bm25 capability scores, gated by genuine SE6 source/lifecycle mapping.' if method==selection.BM25 else 'Explicit legacy distinct casefolded Unicode token overlap; no active retained method policy.',
            tie_break='Shared capability native ordering, then unique logical session dedup.' if method==selection.BM25 else 'Original session order then public session ID then history hash',query_sha256=digest(question),question_date_sha256=digest(question_date),
            question_date_use='Preserved in request; no invented temporal ranking semantics',entity_id=snapshot.state.identity.instance_id,
            entity_state_id=snapshot.state.entity_state_id,entity_version=snapshot.state.state_version,process_id=os.getpid(),
            collection_count=len(collections),available_unique_sessions=len(available_ids),source_session_occurrences=occurrences,
            ranked_duplicate_occurrences_skipped=duplicates,selected=consumed,k=k,
            candidate_occurrence_count=len(candidates),ranked_candidates=[dict(session_id=candidates[i]['sid'],session_index=candidates[i]['index'],score=s) for i,s in rankings],
            context_sha256=digest(selected),returned_bytes=len(canonicalbytes(selected)),storage_bytes=self._bytes(),
            wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,
            provider_calls=0,world_effects=0,epistemic_promotion=False,lifecycle_scope='Whole historical source collection, not per-session lifecycle',
            phase_metrics={name:dict(value) for name,value in self.phase_metrics.items()})
        return dict(sessions=selected,trace=self.last_trace)

    def query(self,question,query_image=None):
        """Existing text-memory interface, causally using the session consumer.

        Primary retrieval is capped by five complete sessions. A later answering
        runner must apply the SAME separately frozen reader-context allowance to
        both methods; this method does not silently truncate source messages.
        """
        require(query_image is None,'UNSUPPORTED_MODALITY_QUERY_IMAGE')
        result=self.retrieve(question,k=5);self.last_retrieval=result
        context=[dict(type='text',value='Historical source evidence; REPORTED / PROVISIONAL.\nSource: '+s['source_ref']+'\n'+
            render_session(s)) for s in result['sessions']]
        self.last_trace['reader_context_sha256']=digest(context)
        return context

    def save(self,path):
        target=self._inside(path);snapshot=self._verify();self._collections(snapshot)
        source_files=[p for p in self.payload_root.rglob('*') if p.is_file()] if self.payload_root.exists() else []
        payload_bytes=sum(p.stat().st_size for p in source_files)
        require(self._bytes()+payload_bytes+RESERVE_BYTES<=self.storage_byte_budget,'SESSION_SNAPSHOT_STORAGE_RESERVE')
        result=super().save(path);files={}
        for source in source_files:
            require(not source.is_symlink(),'SESSION_LINKED_SOURCE');name=source.relative_to(self.payload_root).as_posix()
            dest=target/'session-sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);files[name]=_sha(dest)
        _write(target/'collection_snapshot.json',dict(version=VERSION,files=files,inventory_sha256=digest(files)))
        require(self._bytes()<=self.storage_byte_budget,'SESSION_SNAPSHOT_STORAGE_BUDGET')
        return {**result,'source_files':len(files),'payload_bytes':payload_bytes,'collection_inventory_sha256':digest(files)}

    def load(self,path):
        target=self._inside(path);material=_read(target/'collection_snapshot.json')
        require(material['version']==VERSION and digest(material['files'])==material['inventory_sha256'],'SESSION_COLD_SOURCE_INVENTORY')
        for name,pin in material['files'].items():
            p=target/'session-sources'/name
            require(p.resolve().is_relative_to((target/'session-sources').resolve()) and not p.is_symlink()
                and p.is_file() and _sha(p)==pin,'SESSION_COLD_SOURCE_FILE_PIN')
        actual={p.relative_to(target/'session-sources').as_posix() for p in (target/'session-sources').rglob('*') if p.is_file()}
        require(actual==set(material['files']),'SESSION_COLD_SOURCE_EXACT_INVENTORY')
        previous,previous_store,previous_mode=self.payload_root,self.store,self.read_only_loaded
        try:
            result=super().load(path);self.payload_root=target/'session-sources';self._collections(self._verify())
        except BaseException:
            self.payload_root,self.store,self.read_only_loaded=previous,previous_store,previous_mode
            raise
        return {**result,'source_inventory_sha256':material['inventory_sha256']}
