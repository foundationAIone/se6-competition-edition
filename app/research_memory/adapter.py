"""Historical source memory, not verified capabilities or Native World truth.

All retained text lives in actual Entity memory records. Retrieval is a new,
explicit bounded lexical reader of the existing active lifecycle projection;
it is not a claim that DependencyRepairAgent supports arbitrary trajectories.
"""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json,os,shutil,sqlite3,time,uuid
from .format import VERSION,encode,digest,require,tokens,trajectory_chunks
from . import entity
from .entity import EntityStore,LocalEntityRuntime,MemoryEventOperation

MARKER='.SE6_RESEARCH_MEMORY'
def _linked(p):return p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction())
def _write(path,value):
    with path.open('xb') as f:f.write(encode(value));f.flush();os.fsync(f.fileno())
def _read(path):return json.loads(path.read_bytes())
def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class Memory:
    memory_type='se6_entity_reported_text_development'
    def __init__(self,root,*,context_char_budget=12000,storage_byte_budget=512*1024*1024):
        require(type(context_char_budget) is int and 512<=context_char_budget<=64000,'MEMORY_CONTEXT_BOUND')
        require(type(storage_byte_budget) is int and 1024*1024<=storage_byte_budget<=2*1024**3,'MEMORY_STORAGE_BOUND')
        raw=Path(root);require(not any(_linked(p) for p in (raw,*raw.parents)),'MEMORY_ROOT_LINK')
        self.root=raw.resolve();require(not self.root.is_relative_to(Path(__file__).resolve().parents[1]),'MEMORY_ROOT_MUST_BE_PRIVATE')
        self.root.mkdir(parents=True,exist_ok=True);config=self.root/'adapter-config.json'
        self.context_char_budget=context_char_budget;self.storage_byte_budget=storage_byte_budget
        self.read_only_loaded=False;self.last_trace=None;self.last_insert=None
        self.store=EntityStore.for_testing(self.root/'entity.sqlite3')
        if not config.exists():
            require(not any(self.root.iterdir()),'MEMORY_NEW_ROOT_NOT_EMPTY')
            identity=digest({'scope':'disposable historical research','nonce':uuid.uuid4().hex})
            _write(self.root/MARKER,{'version':VERSION,'authority_effect':'NONE','production':False})
            entity.initialize(self.store,identity)
            _write(config,dict(version=VERSION,identity_pin=identity,context_char_budget=context_char_budget,
                storage_byte_budget=storage_byte_budget,source_pins=self._sources()))
        self.config=_read(config)
        require(self.config['context_char_budget']==context_char_budget and self.config['storage_byte_budget']==storage_byte_budget,'MEMORY_CONFIG_EXACT_BINDING')
        self._verify()

    def _sources(self):
        return {**entity.source_pins(),**{'adapter:'+p.name:_sha(p) for p in (Path(__file__),Path(__file__).with_name('entity.py'),Path(__file__).with_name('format.py'))}}
    def _verify(self):
        require(_read(self.root/MARKER)=={'version':VERSION,'authority_effect':'NONE','production':False},'MEMORY_ROOT_MARKER')
        require(self.config['version']==VERSION and self.config['source_pins']==self._sources(),'MEMORY_SOURCE_PIN_MISMATCH')
        snapshot=self.store.reconstruct()
        require(snapshot.state.shadow_mode is True and snapshot.state.production_authoritative is False
            and snapshot.state.identity.identity_state_hash==self.config['identity_pin'],'MEMORY_ENTITY_SCOPE_OR_IDENTITY')
        if self.read_only_loaded:
            current=EntityStore.for_testing(self.root/'entity.sqlite3').reconstruct()
            require(current.state.entity_state_id==snapshot.state.entity_state_id,'MEMORY_CHECKPOINT_STALE_RELATIVE_TO_ROOT')
        require(self._bytes()<=self.storage_byte_budget,'MEMORY_STORAGE_BYTE_BUDGET')
        return snapshot
    def _bytes(self):return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
    def _inside(self,path):
        raw=Path(path);require(not any(_linked(p) for p in (raw,*raw.parents)),'MEMORY_SNAPSHOT_LINK')
        target=raw.resolve();require(target.is_relative_to(self.root) and target!=self.root,'MEMORY_SNAPSHOT_OWN_ROOT_ONLY')
        return target
    def _inventory(self,snapshot):
        records=snapshot.state.memory.records;completed={}
        for record in records:
            if not record.subject.startswith('history_manifest:'):continue
            if record.status.value!='PROVISIONAL' or record.epistemic_status.value!='reported':continue
            material=json.loads(record.content_summary);source=material['trajectory_sha256']
            chunks=[r for r in records if r.subject.startswith('history_chunk:'+source+':') and r.status.value=='PROVISIONAL']
            chunks.sort(key=lambda r:tuple(map(int,r.subject.split(':')[-2:])))
            inventory=[dict(subject=r.subject,chunk_sha256=digest(r.content_summary)) for r in chunks]
            require(len(inventory)==material['chunks'] and digest(inventory)==material['inventory_sha256'],'MEMORY_ADMISSION_INCOMPLETE_OR_CORRUPT')
            segments={}
            for chunk in chunks:
                segment,part=map(int,chunk.subject.split(':')[-2:]);segments.setdefault(segment,[]).append((part,chunk.content_summary))
            require(sorted(segments)==list(range(len(segments))),'MEMORY_SOURCE_SEGMENT_SEQUENCE')
            source_parts=[]
            for index in sorted(segments):
                parts=sorted(segments[index]);require([p[0] for p in parts]==list(range(len(parts))),'MEMORY_SOURCE_PART_SEQUENCE')
                source_parts.append(json.loads(''.join(p[1] for p in parts)))
            header=source_parts[0]
            reconstructed=dict(id=header['historical_source_id'],goal=header['historical_goal'],start_url=header['historical_start_url'],
                outcome=header['reported_outcome'],states=[p['reported_state'] for p in source_parts[1:]])
            for key in ('domain','environment'):
                if 'historical_'+key in header:reconstructed[key]=header['historical_'+key]
            require(digest(reconstructed)==source,'MEMORY_EXACT_TRAJECTORY_SOURCE_HASH')
            completed[source]=record
        return completed

    def insert(self,trajectory):
        require(not self.read_only_loaded,'MEMORY_LOADED_CHECKPOINT_QUERY_ONLY')
        wall,cpu=time.perf_counter(),time.process_time();prepared=trajectory_chunks(trajectory);snapshot=self._verify();source=prepared['trajectory_sha256']
        if source in self._inventory(snapshot):
            self.last_insert=dict(status='ALREADY_ADMITTED_NO_MUTATION',trajectory_sha256=source,entity_state_id=snapshot.state.entity_state_id)
            return self.last_insert
        require(not any(json.loads(record.content_summary).get('source_id_sha256')==digest(trajectory['id'])
            for record in self._inventory(snapshot).values()),'HISTORY_SOURCE_ID_CHANGED_REQUIRES_EXPLICIT_LIFECYCLE')
        require(not any(r.subject.startswith('history_chunk:'+source+':') for r in snapshot.state.memory.records),'MEMORY_PARTIAL_INSERT_REQUIRES_RECONCILIATION')
        require(len(snapshot.state.memory.records)+len(prepared['chunks'])+1<=384,'MEMORY_RECORD_BUDGET')
        inventory=[];receipts=[]
        for chunk in prepared['chunks']:
            subject=f'history_chunk:{source}:{chunk["segment_index"]}:{chunk["part_index"]}'
            refs=[chunk['source_ref'],'trajectory_sha256:'+source,'chunk_sha256:'+chunk['chunk_sha256']]
            step=entity.commit_candidate(self.store,subject=subject,text=chunk['text'],refs=refs,key=subject)
            inventory.append(dict(subject=subject,chunk_sha256=chunk['chunk_sha256']));receipts.append(step.receipt.receipt_id)
            require(self._bytes()<=self.storage_byte_budget,'MEMORY_STORAGE_BYTE_BUDGET_AFTER_ATOMIC_COMMIT')
        manifest=dict(version=VERSION,trajectory_sha256=source,source_id_sha256=digest(trajectory['id']),chunks=len(inventory),inventory_sha256=digest(inventory),scope='REPORTED_HISTORICAL_SOURCE_NOT_WORLD_VERIFIED')
        step=entity.commit_candidate(self.store,subject='history_manifest:'+source,text=encode(manifest).decode(),
            refs=['trajectory_sha256:'+source],key='history_manifest:'+source);receipts.append(step.receipt.receipt_id)
        after=self._verify();require(source in self._inventory(after),'MEMORY_ADMISSION_MANIFEST')
        self.last_insert=dict(status='ADMITTED_AS_REPORTED_PROVISIONAL',trajectory_sha256=source,chunk_count=len(inventory),
            entity_id=after.state.identity.instance_id,entity_state_id=after.state.entity_state_id,entity_version=after.state.state_version,
            receipt_ids=receipts,source_refs=[x['source_ref'] for x in prepared['chunks']],storage_bytes=self._bytes(),
            wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,provider_calls=0,world_effects=0)
        return self.last_insert

    def query(self,question,query_image=None):
        require(query_image is None,'UNSUPPORTED_MODALITY_QUERY_IMAGE')
        require(type(question) is str and 1<=len(question.strip())<=16000,'MEMORY_QUESTION_BOUND')
        wall,cpu=time.perf_counter(),time.process_time();snapshot=self._verify();completed=self._inventory(snapshot)
        active=snapshot.state.memory.active_at(datetime.now(UTC));terms=tokens(question);ranked=[]
        active_ids={r.memory_id for r in active}
        for record in active:
            if not record.subject.startswith('history_chunk:') or record.status.value!='PROVISIONAL' or record.epistemic_status.value!='reported':continue
            source=record.subject.split(':')[1]
            if source not in completed or completed[source].memory_id not in active_ids:continue
            require('chunk_sha256:'+digest(record.content_summary) in record.evidence_references,'MEMORY_EXACT_CHUNK_SOURCE')
            score=len(terms & tokens(record.content_summary))
            if score:ranked.append((score,record))
        ranked.sort(key=lambda x:(-x[0],x[1].subject,x[1].memory_id));context=[];consumed=[];remaining=self.context_char_budget
        events={e.event_id:e for e in snapshot.historical_events}
        for score,record in ranked:
            source_events=[events[x] for x in record.source_event_ids if x in events]
            require(any(isinstance(e.payload,entity.MemoryPayload) and e.payload.operation is MemoryEventOperation.CANDIDATE
                and e.payload.content_summary==record.content_summary and e.provenance is entity.ObservationProvenance.EXTERNAL_RETRIEVED
                and e.epistemic_status is entity.EpistemicStatus.REPORTED for e in source_events),'MEMORY_ACTUAL_SOURCE_EVENT_REQUIRED')
            value='Historical source evidence; REPORTED / PROVISIONAL, not verified World truth.\nSource: '+record.subject+'\n'+record.content_summary
            if len(value)>remaining:continue
            context.append(dict(type='text',value=value));remaining-=len(value)
            consumed.append(dict(memory_id=record.memory_id,subject=record.subject,source_event_ids=list(record.source_event_ids),
                evidence_references=list(record.evidence_references),content_sha256=digest(record.content_summary),score=score))
        self.last_trace=dict(version=VERSION,consumer='EntityMemoryState.active_at → bounded lexical applicability → official answer context',
            process_id=os.getpid(),
            entity_id=snapshot.state.identity.instance_id,entity_state_id=snapshot.state.entity_state_id,entity_version=snapshot.state.state_version,
            query_sha256=digest(question),context_sha256=digest(context),context_characters=self.context_char_budget-remaining,
            consumed=consumed,status='SOURCE_BACKED_REPORTED_CONTEXT' if context else 'UNKNOWN_NO_APPLICABLE_ACTIVE_MEMORY',
            epistemic_promotion=False,world_verification=False,provider_calls=0,wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
            storage_bytes=self._bytes(),source_pins=self._sources())
        return context

    def mark_inactive(self,memory_id,*,operation='REVOKE'):
        require(not self.read_only_loaded and operation in ('REVOKE','MARK_EXPIRED','MARK_STALE','MARK_CONTRADICTED'),'MEMORY_LIFECYCLE_OPERATION')
        snapshot=self._verify();target=next((r for r in snapshot.state.memory.active_records if r.memory_id==memory_id),None)
        require(target is not None,'MEMORY_ACTIVE_TARGET_REQUIRED')
        runtime=LocalEntityRuntime(store=self.store,runtime_session_id='research-history-lifecycle')
        op=MemoryEventOperation(operation);ingress=runtime.submit_memory_transition(operation=op,subject=target.subject,
            content_summary='Historical memory withdrawn from active answer context: '+operation,ingress_key=digest([operation,memory_id]),
            revokes_memory_id=memory_id if op is MemoryEventOperation.REVOKE else None,
            supersedes_memory_id=memory_id if op is not MemoryEventOperation.REVOKE else None)
        step=runtime.process_one();require(step is not None and step.ingress.ingress_id==ingress.ingress_id,'MEMORY_LIFECYCLE_COMMIT_UNCERTAIN')
        return dict(receipt_id=step.receipt.receipt_id,entity_state_id=step.receipt.state_after_id)

    def save(self,path):
        snapshot=self._verify();target=self._inside(path)
        # A genuine SQLite backup, not a JSON simulated-store substitute.
        source=sqlite3.connect(self.store.path.as_uri()+'?mode=ro',uri=True)
        pages=source.execute('PRAGMA page_count').fetchone()[0];page_size=source.execute('PRAGMA page_size').fetchone()[0]
        if self._bytes()+pages*page_size+8192>self.storage_byte_budget:
            source.close();raise ValueError('MEMORY_SNAPSHOT_STORAGE_BUDGET')
        target.mkdir(parents=True,exist_ok=False)
        dest=sqlite3.connect(target/'entity.sqlite3')
        try:source.backup(dest)
        finally:dest.close();source.close()
        _write(target/'checkpoint.json',dict(version=VERSION,database_sha256=_sha(target/'entity.sqlite3'),
            entity_state_id=snapshot.state.entity_state_id,entity_version=snapshot.state.state_version,config=self.config))
        return dict(status='SAVED_REAL_ENTITY_SQLITE',database_sha256=_sha(target/'entity.sqlite3'),entity_state_id=snapshot.state.entity_state_id)
    def load(self,path):
        target=self._inside(path);saved=_read(target/'checkpoint.json')
        require(saved['version']==VERSION and saved['config']==self.config and saved['database_sha256']==_sha(target/'entity.sqlite3'),'MEMORY_COLD_CHECKPOINT_PIN')
        previous,previous_mode=self.store,self.read_only_loaded
        try:
            self.store=EntityStore.for_testing(target/'entity.sqlite3');self.read_only_loaded=True;snapshot=self._verify()
            require(snapshot.state.entity_state_id==saved['entity_state_id'] and snapshot.state.state_version==saved['entity_version'],'MEMORY_COLD_STATE_ANCESTRY')
        except BaseException:
            self.store,self.read_only_loaded=previous,previous_mode;raise
        return dict(status='COLD_REAL_ENTITY_RESTORED_QUERY_ONLY',entity_state_id=snapshot.state.entity_state_id,entity_version=snapshot.state.state_version)
