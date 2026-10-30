"""Prepare/validate by default. Fresh exact approval is required for --live.

No retries, fallback providers, hidden oracles or credential logging. This is
the same Competition Edition provider stack, not another engine/application.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hosted_judge.native_adapter import validate_bundle
from hosted_judge.benchmark_campaign import PilotCoordinator,validate_packet,verify_complete_source

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--packet-sha256',required=True)
    parser.add_argument('--store',type=Path,required=True)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--approval-sha256')
    args=parser.parse_args()
    if (args.approval or args.approval_sha256) and not args.live:raise ValueError('Approval is accepted only by explicit live invocation')
    if args.live and not(args.approval and args.approval_sha256):raise ValueError('Exact new owner approval required')
    raw=args.packet.read_bytes()
    if len(raw)>524288 or hashlib.sha256(raw).hexdigest()!=args.packet_sha256:raise ValueError('Packet byte pin mismatch')
    packet=json.loads(raw)
    native_pin=hashlib.sha256((ROOT/'native-manifest.json').read_bytes()).hexdigest()
    verify_complete_source(ROOT);validate_bundle(ROOT/'private-native',ROOT/'native-manifest.json',native_pin)
    sys.path.insert(0,str(ROOT/'private-native'))
    validate_packet(packet,ROOT)
    if not args.live:
        print(json.dumps({'status':'PREPARED_NOT_AUTHORIZED','campaign':packet['campaign'],
            'packet_sha256':packet['packet_sha256'],'maximum_calls':16,'provider_calls':0,
            'credentials_consulted':False,'model_answers':'NOT_EXECUTED','retries':0}))
        return
    coordinator=PilotCoordinator(args.store,ROOT,approval_path=args.approval,
        approval_sha256=args.approval_sha256,live_enabled=True)
    result=coordinator.run(packet)
    print(json.dumps({k:result[k] for k in ('status','mode','provider_calls','captured_complete_responses','reserved_calls','failure','winner','actual_billing_usd','wall_seconds')}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'FAILED_CLOSED','error_type':type(error).__name__,
            'retry_allowed':False,'scope':'Inspect private receipts; no invented free-call count or winner'}))
        raise SystemExit(1)
