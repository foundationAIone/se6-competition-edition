"""Hash-pinned sanitized held-out observations; read-only, no scorer/keys/calls."""
import hashlib,json,re
from pathlib import Path

def load_benchmark(path,pin):
    if path is None and pin is None:return {'schema':'se6-v11-benchmark-view-v1','status':'NOT_CONFIGURED','tasks':[],'provider_calls':0}
    if path is None or not isinstance(pin,str) or not re.fullmatch('[0-9a-f]{64}',pin):raise ValueError('Pinned benchmark view required')
    raw=Path(path).read_bytes()
    if len(raw)>2*1024*1024 or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Benchmark view byte pin')
    value=json.loads(raw)
    if not isinstance(value,dict) or value.get('schema')!='se6-v11-benchmark-view-v1':raise ValueError('Benchmark view schema')
    allowed={'schema','status','scope','tasks','aggregate','comparisons','source','pilot','v2','provider_calls','controls','coverage','limitations','live_pilot'}
    if set(value)-allowed:raise ValueError('Private or unknown benchmark fields')
    if value.get('provider_calls')!=0:raise ValueError('Offline observations cannot claim fresh model inference')
    tasks=value.get('tasks')
    if not isinstance(tasks,list) or len(tasks)!=30 or len({r.get('id') for r in tasks})!=30:raise ValueError('Exact 30 task denominator required')
    for r in tasks:
        if set(r)-{'id','category','phases','public_questions','conditions','scope'}:raise ValueError('Task public fields')
        if not isinstance(r.get('conditions'),dict) or set(r['conditions'])!={'A','B','C','D'}:raise ValueError('Four condition observations required')
        for condition,record in r['conditions'].items():
            if record.get('model_status')!='NOT_EXECUTED':raise ValueError('Offline software results are not model answers')
    if 'live_pilot' in value:
        pilot=value['live_pilot']
        if not isinstance(pilot,dict) or pilot.get('schema')!='se6-v11-frozen-live-pilot-view-v1' or pilot.get('mode')!='FROZEN_LIVE_CAPTURE_OFFLINE_REPLAY':raise ValueError('Frozen pilot identity')
        if pilot.get('status')!='UNASSESSABLE_NO_OVERALL_WINNER' or pilot.get('overall_winner') is not None:raise ValueError('Frozen unassessable pilot cannot claim winner')
        if type(pilot.get('provider_calls_in_frozen_campaign')) is not int or pilot['provider_calls_in_frozen_campaign']!=16 or type(pilot.get('fresh_provider_calls_on_view')) is not int or pilot['fresh_provider_calls_on_view']!=0:raise ValueError('Frozen viewing never dispatches calls')
        rows=pilot.get('rows');ids=set();groups={}
        if not isinstance(rows,list) or len(rows)!=16:raise ValueError('All16actual responses required')
        for row in rows:
            key=(row.get('task_id'),row.get('phase_id'),row.get('condition'))
            if key in ids or key[2] not in ('A','B','C','D') or not isinstance(row.get('actual_answer_text'),str) or len(row['actual_answer_text'].encode())>16384:raise ValueError('Pilot response identity/size')
            if row.get('official_status') not in ('PASS','UNASSESSABLE') or row.get('actual_billing_usd') is not None:raise ValueError('Frozengrade/billing scope')
            ids.add(key);groups.setdefault(key[:2],set()).add(key[2])
        if len(groups)!=4 or len({key[0] for key in ids})!=3 or any(g!=set('ABCD') for g in groups.values()):raise ValueError('Three tasks/four balanced phases')
    # Public file must not contain original owner records, absolute local metadata or secrets.
    # Inspect DECODED strings. JSON-escaped labels such as "premises:\n" are
    # ordinary newlines, not a Windows drive ending in "s:\\".
    def strings(v):
        if isinstance(v,str):yield v
        elif isinstance(v,dict):
            for key,item in v.items():yield key;yield from strings(item)
        elif isinstance(v,list):
            for item in v:yield from strings(item)
    pattern=r'(?:[A-Za-z]:\\|C:/Users/|Bearer\s+[A-Za-z0-9]|sk-[A-Za-z0-9]{12}|startup-private|APPROVED_ALLOWANCE_PRIVATE)'
    if any(re.search(pattern,text) for text in strings(value)):raise ValueError('Sensitive local metadata refused')
    return value

class BenchmarkTaskRunner:
    """Repeat one fixed PUBLIC task with existing tools, zero provider authority.

    Separate repeat evidence cannot replace the first frozen held-out result.
    The service shares its bounded native-worker slots and session admission.
    """
    def __init__(self,path,pin,bundle,manifest,native_pin,store,semaphore):
        import threading
        from .benchmark_controls import valid
        raw=Path(path).read_bytes()
        if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Frozen public task pin')
        suite=json.loads(raw);self.tasks={t['id']:t for t in suite['tasks']}
        if len(self.tasks)!=30:raise ValueError('Complete public task set')
        for task in self.tasks.values():valid(task,'C')
        self.bundle,self.manifest,self.pin=str(bundle),str(manifest),native_pin
        self.root=Path(store).resolve();self.semaphore=semaphore
        if self.root.is_relative_to(Path(bundle).parent.resolve()):raise ValueError('Private repeats outside source')
        if any(p.is_symlink() for p in [self.root,*self.root.parents]):raise ValueError('Linked repeat store')
        self.jobs={};self.lock=threading.RLock()

    def submit(self,session_id,value):
        from copy import deepcopy
        import threading
        if not isinstance(value,dict) or set(value)!={'request_id','task_id','condition'}:raise ValueError('Fixed task, condition and request required')
        request=value['request_id'];task=value['task_id'];condition=value['condition']
        if not isinstance(request,str) or not re.fullmatch('[0-9a-f]{32}',request):raise ValueError('Request identity')
        if task not in self.tasks or condition not in ('B','C','D'):raise ValueError('Known native task/condition only')
        key=(session_id,request)
        with self.lock:
            if key in self.jobs:
                old,result=self.jobs[key]
                if old!=value:raise ValueError('Request reused with other task')
                return deepcopy(result)
            if not self.semaphore.acquire(blocking=False):raise ValueError('Native slots busy; no job dispatched')
            self.jobs[key]=(deepcopy(value),{'status':'RUNNING','request_id':request,'provider_calls':0,'model_status':'NOT_EXECUTED'})
            worker=threading.Thread(target=self._run,args=(key,deepcopy(value)),daemon=True);worker.start()
            return deepcopy(self.jobs[key][1])

    def _run(self,key,value):
        from .benchmark_controls import run_condition,encode
        from .realization_loop import exclusive
        try:
            root=self.root/key[0]/value['request_id']
            result=run_condition(self.tasks[value['task_id']],value['condition'],root,self.bundle,self.manifest,self.pin)
            phases=[]
            for phase in result['phase_records']:
                public=phase.get('public') or {};canonical=public.get('canonical') or {}
                phases.append({'id':phase['id'],'status':phase['status'],'conditional_tool_answer':phase.get('response'),
                    'native_operations':phase.get('native_operations'),'checkpoint_sha256':phase.get('checkpoint_sha256'),
                    'operator_evidence':{k:canonical[k] for k in ('independent_checkpoint_replay','toroidal_realization','flower_context','operator_trace') if k in canonical},
                    'recursive_realization':public.get('realization_loop'),'resources':phase.get('resources'),
                    'artifact_hashes':[a['effect_sha256'] for a in phase.get('artifact_records',[])],
                    'error_code':phase.get('error_code')})
            output={'status':result['status'],'request_id':value['request_id'],'task_id':value['task_id'],
                'condition':value['condition'],'mode':'NEW_OFFLINE_NATIVE_REPEAT_NOT_HELDOUT_MODEL_INFERENCE',
                'model_status':'NOT_EXECUTED','provider_calls':0,'first_frozen_results_preserved':True,
                'independent_score':'NOT_EVALUATED_HERE','phases':phases,'resources':result['resources'],
                'scope':'Actual native/software repeat on already exposed frozen tasks; no new model answer, superiority claim or overwritten result'}
            exclusive(root/'public-repeat.json',encode(output))
        except Exception:
            output={'status':'FAILED_CLOSED','request_id':value['request_id'],'provider_calls':0,
                'model_status':'NOT_EXECUTED','retry_allowed':False,'error':'Offline native repeat failed; private outcome retained'}
        finally:self.semaphore.release()
        with self.lock:self.jobs[key]=(value,output)

    def get(self,session_id,request):
        from copy import deepcopy
        with self.lock:
            row=self.jobs.get((session_id,request))
            if row is None:raise ValueError('No queued repeat; polling never dispatches')
            return deepcopy(row[1])
