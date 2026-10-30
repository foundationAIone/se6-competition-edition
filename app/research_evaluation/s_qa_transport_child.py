"""One already-claimed, freshly admitted provider request; no standalone permit.

Credentials arrive through the process environment, never command arguments or
evidence. The coordinator enforces the absolute 30-second helper deadline.
"""
from pathlib import Path
import argparse,json,os
from .s_qa_gateway import MemoryQAGateway,model_parts
from hosted_judge.v8_run_both import read,exclusive,require
from .measurement import Meter

def run(args):
    meter=Meter()
    gateway=MemoryQAGateway(args.store,spec_path=args.spec,spec_sha256=args.spec_pin,
        approval_path=args.approval,approval_sha256=args.approval_pin,live_enabled=True)
    spec,approval=gateway.admit()
    prepared=gateway.prepare_cell(args.kind,args.case_id,args.arm)
    directory=gateway.path('calls',args.case_id+'-'+args.kind+'-'+args.arm)
    require(not gateway.path('STOP.json').exists() and directory.is_dir(),'Claimed active memory QA request required')
    intent=read(directory/'intent.json')
    require(intent['spec_sha256']==args.spec_pin and intent['kind']==args.kind and intent['wire_sha256']==prepared['wire_sha256']
        and read(directory/'prepared.json')==prepared,'Transport helper intent does not match admitted packet')
    require(read(gateway.path('batch-claim.json'))==dict(permit_id=approval['permit_id'],spec_sha256=args.spec_pin),
        'Transport helper has no exact admitted batch claim')
    exclusive(directory/'transport-child-claim.json',dict(pid=os.getpid(),spec_sha256=args.spec_pin,wire_sha256=prepared['wire_sha256']))
    gateway._approval()  # final expiry/identity binding immediately before wire
    settings,router=model_parts(args.kind)
    require(router.credential_status(settings),'NEBIUS_CREDENTIAL_MISSING_NO_CALL')
    try:response=router.NebiusTransport(settings).request({'input':prepared['messages']},directory,25)
    except Exception as error:
        exclusive(directory/'transport-failure.json',dict(error_type=type(error).__name__,
            usage=getattr(error,'usage',None),text=getattr(error,'text',''),model=getattr(error,'returned_model',None),
            retry_allowed=False))
        raise
    measured=meter.read();measured['provider_calls']=1
    measured['scope']='Owned transport-helper process: source/authentication/request/parsing CPU and peak RSS. Parent/engineering/other descendants excluded.'
    response['transport_child_resources']=measured
    exclusive(directory/'transport-response.json',response)
    return dict(status='ONE_PROVIDER_RESPONSE_CAPTURED_UNVERIFIED',pid=os.getpid())
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['store','spec','approval']:parser.add_argument('--'+name,type=Path,required=True)
    for name in ['spec-pin','approval-pin','kind','case-id','arm']:parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args)))
    except Exception as error:
        print(json.dumps(dict(status='FAILED_OR_UNCERTAIN_NO_RETRY',error_type=type(error).__name__)))
        raise SystemExit(2)
