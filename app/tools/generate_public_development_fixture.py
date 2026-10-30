"""Generate fresh, non-sensitive synthetic DEVELOPMENT evidence in TEMP.

Uses the existing bounded native worker and core. Never reads the old private
fixture. No inference, production enrollment, credentials or public rights grant.
"""
import argparse,hashlib,json,os,re,sys,time
from pathlib import Path
MAX_FIXTURE_BYTES=1024*1024
KEYS={'checkpoint','journal','out','raw_answer','selection','summary'}
def encode(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
def sha(v):return hashlib.sha256(v).hexdigest()
def require(v,code):
    if not v:raise ValueError(code)
def public_question(seed=17):
    require(type(seed) is int and 0<=seed<=999,'DEVELOPMENT_SEED_BOUND')
    # Intentionally small witness-bearing arithmetic, unrelated to heldout tasks.
    second=3+seed%3;difference=2+seed%4
    return f'Given equations:\nE1: p+q+r={second+difference}\nE2: r+s={second}\nDerive the relation between p,q,s.'
def strip_provider_authority():
    for k in list(os.environ):
        if k.startswith(('NEBIUS','OPENAI')):del os.environ[k]
    for k in ('SE6_PRODUCTION_ENROLLMENT','SE6_PRODUCTION_EMBODIMENT','SE6_OWNER_AUTH','SE6_ONLINE_OBSERVATION','SE6_AVATAR_RESEARCH','SE6_AVATAR_PROTOTYPE'):
        os.environ[k]='off'
    sys.dont_write_bytecode=True

def projection(result):
    require(result['public']['provider_calls']==0 and result['public']['production_connected'] is False,'DEVELOPMENT_AUTHORITY_BOUND')
    require(result['public']['local_verification']['status']=='LOCAL_CERTIFICATES_REPLAYED','DEVELOPMENT_ACTUAL_NATIVE_PROOF_REQUIRED')
    out=result['attestation']['raw_execution_out'];checkpoint=result['checkpoint']['auto_checkpoint']
    require(len(out['nodes'])==1 and out['nodes'][0]['status']=='COMPLETE' and out['nodes'][0]['route']=='LINEAR_DERIVATION','DEVELOPMENT_NATIVE_ROUTE_REQUIRED')
    shown=out['nodes'][0]['result'];journal=json.loads(checkpoint['math']['journal']);last=journal['receipts'][-1]
    require(last['observation']['kind']=='MATH_DERIVE' and shown['head']==last['receipt_hash'],'DEVELOPMENT_HEAD_BINDING')
    # Original source hash function, not a new mathematical solver or proof.
    from src.workbench.canonical_core_vendor.se_core.kernel import _hash
    selection={'route':out['nodes'][0]['route'],'math':{'proof_candidate':{'pivot':last['observation']['isolate_variable']}},'limitations':shown['limitations']}
    summary={'receipts':out['receipts'],'context':json.dumps({'head':shown['head'],'state_hash':_hash(journal['state']),'scope':shown['scope']},ensure_ascii=False),'checkpoint_hash':checkpoint['checkpoint_hash'],'local_seconds':shown['local_seconds']}
    fixture={'checkpoint':checkpoint,'journal':journal,'out':out,'raw_answer':result['attestation']['raw_answer'],'selection':selection,'summary':summary}
    require(set(fixture)==KEYS and len(encode(fixture))<=MAX_FIXTURE_BYTES,'DEVELOPMENT_FIXTURE_BOUND')
    def inspect(v):
        if type(v) is dict:
            for key,item in v.items():
                require(key.lower() not in ('api_key','authorization','csrf_token','cookie','password','access_token'),'DEVELOPMENT_SECRET_FIELD')
                inspect(item)
        elif type(v) in (list,tuple):
            for item in v:inspect(item)
        elif type(v) is str:
            require(not re.search(r'[A-Za-z]:[\\/]|/(?:Users|home|app|tmp)/|Bearer\s',v),'DEVELOPMENT_PRIVATE_PATH_OR_AUTH')
    inspect(fixture)
    return fixture

def generate(source,output,seed=17):
    source=Path(source).resolve();output=Path(output).resolve()
    require(not output.is_relative_to(source),'TEMP_OUTPUT_MUST_BE_OUTSIDE_SOURCE')
    require(not output.exists() and not output.with_suffix('.provenance.json').exists(),'DEVELOPMENT_OUTPUT_ALREADY_EXISTS_NO_RETRY')
    require(not any(p.is_symlink() or p.is_junction() for p in (output,*output.parents)),'DEVELOPMENT_OUTPUT_LINK')
    strip_provider_authority()
    sys.path[:0]=[str(source),str(source/'private-native')]
    from hosted_judge.service import disposable_native
    bundle=source/'private-native';manifest=bundle/'hosted-test-manifest.json';pin=sha(manifest.read_bytes())
    q=public_question(seed);task=sha(('synthetic-development-task:'+str(seed)).encode())[:32];rid=sha(('synthetic-development-round:'+str(seed)).encode())[:32]
    started=time.perf_counter()
    # One fresh real execution, no earlier checkpoint/effects and no retry.
    result=disposable_native((bundle,manifest,pin,q,None,task,rid,None),deadline=20)
    fixture=projection(result);raw=encode(fixture);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    provenance={'schema':'se6-public-development-fixture-provenance-v1','origin':'FRESH_REAL_NATIVE_SYNTHETIC_DEVELOPMENT_NOT_BENCHMARK','question':q,'public_seed':seed,'recipe_sha256':sha(Path(__file__).read_bytes()),'native_manifest_sha256':pin,'whole_host_manifest_sha256':sha((source/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json').read_bytes()),'fixture_sha256':sha(raw),'fixture_bytes':len(raw),'native_operations':result['operations'],'native_receipts':len(fixture['out']['receipts']),'provider_calls':0,'production_connected':False,'native_deadline_seconds':20,'wall_seconds':time.perf_counter()-started,'source_redistribution_rights':'PENDING_NOT_GRANTED_BY_GENERATION','scope':'Conditional synthetic public premises; actual local receipts. Typed deserialization in later formatter tests is not a new independent replay.'}
    with output.with_suffix('.provenance.json').open('xb') as f:f.write(encode(provenance));f.flush();os.fsync(f.fileno())
    return provenance

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=17);a=p.parse_args()
    row=generate(a.source,a.output,a.seed)
    print(json.dumps({k:row[k] for k in ('origin','fixture_bytes','native_operations','native_receipts','provider_calls','native_deadline_seconds')}))
if __name__=='__main__':main()
