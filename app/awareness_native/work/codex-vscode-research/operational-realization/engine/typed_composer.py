"""Finite HOST-provisioned type-path composition, not arbitrary code planning."""
from copy import deepcopy
import hashlib,json,heapq
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def require(v,s):
 if not v:raise ValueError(s)

class TypedComposer:
    def __init__(self,catalog):
        require(isinstance(catalog,list) and 1<=len(catalog)<=8,'CATALOG_BOUND')
        self.catalog=deepcopy(catalog);self.cache={};self.configurations=0;self.history=[]
        self.source_fingerprint=digest(self.catalog)
        require(len({n['id'] for n in catalog})==len(catalog),'DUPLICATE_NODE')
        for n in catalog:
            require(set(n)=={'id','inputs','outputs','permissions','evidence','current_epoch','cost','source_id','verifier'},'NODE_SCHEMA')
            require(type(n['cost']) is int and 0<=n['cost']<=1000,'COST_BOUND')
            require(n['id']!='fixed_math_fixture' and n['verifier'] and n['source_id'],'SOURCE_VERIFIER')
            require(all(isinstance(n[k],list) and len(set(n[k]))==len(n[k]) for k in ('inputs','outputs','permissions','evidence')),'TAG_SET')
            require(type(n['current_epoch']) is bool and all(isinstance(t,str) and 0<len(t)<=128 for k in ('inputs','outputs','permissions','evidence') for t in n[k]),'TAG_TYPES')
    def plan(self,goal,available,context,*,reconfigure=True):
        require(isinstance(goal,list) and bool(goal) and len(goal)<=8,'GOAL_TYPES')
        require(set(context)=={'permissions','evidence','epoch','evidence_epoch','source_fingerprint','authority_scope'},'CONTEXT_SCHEMA')
        require(type(reconfigure) is bool,'RECONFIGURE_BOOL')
        require(context['source_fingerprint']==self.source_fingerprint,'CURRENT_SOURCE_FINGERPRINT')
        require(type(context['epoch']) is int and type(context['evidence_epoch']) is int and context['epoch']>=0 and context['evidence_epoch']>=0,'CURRENT_EPOCH')
        key=digest({'goal':sorted(goal),'available':sorted(available),'context':context,'catalog':self.catalog})
        if key in self.cache:
            cached=self.cache[key]
            for path in cached['plans']:
                tags=set(available);seen=set();cost=0
                require(len(path)<=6,'CACHED_PATH_BOUND')
                for ident in path:
                    n=next((n for n in self.catalog if n['id']==ident),None)
                    require(n is not None and ident not in seen and set(n['inputs'])<=tags and set(n['permissions'])<=set(context['permissions']) and set(n['evidence'])<=set(context['evidence']) and (not n['current_epoch'] or context['epoch']==context['evidence_epoch']),'CACHED_PATH_CURRENT_VALIDITY')
                    tags.update(n['outputs']);seen.add(ident);cost+=n['cost']
                require(set(goal)<=tags and cost==cached['minimum_declared_cost'],'CACHED_GOAL_BINDING')
            return {**deepcopy(cached),'cache':'EXACT_CURRENT_VALIDITY_HIT'}
        if not reconfigure and self.cache:return {'status':'RECONFIGURATION_DISABLED_INCOMPATIBLE_CONTEXT','plans':[],'cache':'PRESERVED_OTHER_SCOPES'}
        require(self.configurations<20,'CONFIGURATION_CAP')
        self.configurations+=1
        eligible=[n for n in self.catalog if set(n['permissions'])<=set(context['permissions']) and set(n['evidence'])<=set(context['evidence']) and (not n['current_epoch'] or context['epoch']==context['evidence_epoch'])]
        queue=[(0,(),frozenset(available))];solutions=[];best=None;expanded=0
        while queue:
            cost,path,tags=heapq.heappop(queue);expanded+=1
            require(expanded<=10000,'SEARCH_BOUND')
            if best is not None and cost>best:break
            if set(goal)<=tags:best=cost;solutions.append(list(path));continue
            if len(path)>=6:continue
            for n in eligible:
                if n['id'] in path or not set(n['inputs'])<=tags or set(n['outputs'])<=tags:continue
                heapq.heappush(queue,(cost+n['cost'],path+(n['id'],),tags|frozenset(n['outputs'])))
        out={'status':'VIABLE_PATHS' if solutions else 'INSUFFICIENT_TYPES_EVIDENCE_OR_AUTHORITY','plans':solutions,'minimum_declared_cost':best,'configuration':self.configurations,'context_sha256':digest(context),'goal':deepcopy(goal),'available':sorted(available),'scope':'Declared resource ordering, not measured utility; runtime admission/verifier mandatory','cache':'NEW_CONFIGURATION'}
        self.cache[key]=deepcopy(out);self.history.append({'key':key,'status':out['status'],'plans':solutions});return out
    def export(self):
        data={'catalog':self.catalog,'cache':self.cache,'configurations':self.configurations,'history':self.history};return {**deepcopy(data),'seal':digest(data)}
    @classmethod
    def restore(cls,record):
        require(record['seal']==digest({k:v for k,v in record.items() if k!='seal'}),'COMPOSER_STATE_SEAL')
        obj=cls(record['catalog']);obj.cache=deepcopy(record['cache']);obj.configurations=record['configurations'];obj.history=deepcopy(record['history']);require(type(obj.configurations) is int and 0<=obj.configurations<=20,'CONFIGURATION_CAP');return obj

def inspect_viable_plans(plan_result,mode):
    """Actual source-bound mapper/field/navigation plus QPRE generated by preflight."""
    require(mode in ('ordinary','field'),'MODE')
    from experimental.operator_bridge import select_observation_requests
    require(plan_result['status']=='VIABLE_PATHS' and 1<=len(plan_result['plans'])<=12,'PATH_INSPECTION_BOUND')
    requests=[{'id':f'p{i:02d}','inputs':{'typed_path':json.dumps(p,separators=(',',':')),'goal':json.dumps(plan_result['goal']),'context':plan_result['context_sha256']},'history':[]} for i,p in enumerate(plan_result['plans'])]
    result=select_observation_requests(requests,[r['id'] for r in requests],mode=mode)
    chosen=result['selected_request'];require(chosen is not None,'NO_PATH_SELECTION')
    return {'selected_path':plan_result['plans'][int(chosen['id'][1:])],'actual_operators':result,'scope':'Original typed preflight/QPRE/field/nav over HOST-declared viable paths; no World or native solver execution yet'}
