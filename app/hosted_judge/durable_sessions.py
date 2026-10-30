"""Private bounded session snapshots; cookie secrets never enter public evidence."""
from copy import deepcopy
import hashlib,json,os,re,secrets,time
from pathlib import Path
from . import realization_loop as loop

MAX_STORED_SESSIONS=128
MAX_SNAPSHOT=6*1024*1024

class DurableSessions:
    def __init__(self,root,manifest_sha256):
        self.root=loop.root_path(root);self.manifest_sha256=manifest_sha256
        self.root.mkdir(parents=True,exist_ok=True)
        loop.root_path(self.root)

    def path(self,token):
        if not isinstance(token,str) or re.fullmatch('[0-9a-f]{64}',token) is None:raise ValueError('DURABLE_COOKIE_SHAPE')
        return self.root/(hashlib.sha256(token.encode()).hexdigest()+'.json')

    def save(self,token,session,clock,*,terminal=False):
        path=self.path(token)
        loop.root_path(path)
        if not path.exists() and len(list(self.root.glob('*.json')))>=MAX_STORED_SESSIONS:
            raise ValueError('DURABLE_PRIVATE_STORE_CAP')
        material={'schema':'se6-private-session-v11','manifest_sha256':self.manifest_sha256,
            'task_id':session.task_id,'csrf':session.csrf,'expires_unix':time.time()+max(0,session.expires-clock()),
            'checkpoint':session.checkpoint,'field_checkpoint':session.field_checkpoint,
            'realization_state':session.realization_state,'rounds':session.rounds,'actions':session.actions,
            'typed_task_state':getattr(session,'typed_task_state',None),
            'attempts':session.attempts,'requests':session.requests,'public_questions':session.public_questions,
            'failure_info':session.failure_info,'busy':False if terminal else session.busy,'queued_id':None if terminal else session.queued_id,
            'request_ages_seconds':[max(0,clock()-t) for t in session.request_times if 0<=clock()-t<60]}
        raw=loop.encode(loop.seal(material))
        if len(raw)>MAX_SNAPSHOT:raise ValueError('DURABLE_SNAPSHOT_BOUND')
        temporary=self.root/(path.stem+'.'+secrets.token_hex(8)+'.tmp')
        loop.exclusive(temporary,raw)
        # Atomic replacement only within the verified private directory.
        os.replace(temporary,path)

    def restore(self,token,clock):
        path=self.path(token);loop.root_path(path)
        if not path.is_file():return None
        if path.stat().st_size>MAX_SNAPSHOT:raise ValueError('DURABLE_SNAPSHOT_BOUND')
        record=loop.checked(json.loads(path.read_bytes()))
        if record['schema']!='se6-private-session-v11' or record['manifest_sha256']!=self.manifest_sha256:
            raise ValueError('DURABLE_SOURCE_IDENTITY')
        remaining=record['expires_unix']-time.time()
        if not 0<remaining<=601:return None
        if not re.fullmatch('[0-9a-f]{32}',record['task_id']) or not re.fullmatch('[0-9a-f]{64}',record['csrf']):
            raise ValueError('DURABLE_SESSION_IDENTITY')
        if any(type(record[k]) is not int or record[k]<0 or record[k]>maximum for k,maximum in [('rounds',4),('actions',20),('attempts',8)]):
            raise ValueError('DURABLE_ALLOWANCE')
        # An interrupted job is unresolved; GET cannot dispatch it again.
        if record['busy'] or record['queued_id'] is not None:
            raise ValueError('DURABLE_UNCERTAIN_JOB_NO_RETRY')
        ages=record['request_ages_seconds']
        if not isinstance(ages,list) or len(ages)>8 or any(type(a) not in (int,float) or not 0<=a<60 for a in ages):raise ValueError('DURABLE_REQUEST_RATE')
        from .service import Session
        return Session(record['csrf'],clock()+remaining,record['task_id'],
            checkpoint=deepcopy(record['checkpoint']),field_checkpoint=deepcopy(record['field_checkpoint']),
            realization_state=deepcopy(record['realization_state']),rounds=record['rounds'],actions=record['actions'],
            attempts=record['attempts'],requests=deepcopy(record['requests']),public_questions=list(record['public_questions']),
            failure_info=deepcopy(record['failure_info']),request_times=[clock()-a for a in ages],
            typed_task_state=deepcopy(record.get('typed_task_state')))
