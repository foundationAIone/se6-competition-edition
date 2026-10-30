"""Local QA is reversible; PUBLIC deployment/upload requires separate approval."""
import argparse
import os
from pathlib import Path
import sys
sys.dont_write_bytecode=True
from .service import JudgeService,make_server
from .review import load_review
from .dynamic import load_dynamic
from .canonical import load_canonical,load_current_coverage,load_field_controls
from .replays import load_replays
from .pair_gateway import PairGateway
from .benchmark_view import load_benchmark,BenchmarkTaskRunner


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',default=os.environ.get('PUBLIC_ORIGIN'))
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8080')))
    parser.add_argument('--loopback-development',action='store_true',help='Local QA only: bind127.0.0.1, exact HTTPorigin, no Secure cookie')
    parser.add_argument('--native-bundle',type=Path)
    parser.add_argument('--native-manifest',type=Path)
    parser.add_argument('--native-manifest-sha256')
    parser.add_argument('--review',type=Path,default=os.environ.get('FROZEN_REVIEW_PATH'))
    parser.add_argument('--review-sha256',default=os.environ.get('FROZEN_REVIEW_SHA256'))
    parser.add_argument('--dynamic',type=Path,default=os.environ.get('FROZEN_DYNAMIC_PATH'))
    parser.add_argument('--dynamic-sha256',default=os.environ.get('FROZEN_DYNAMIC_SHA256'))
    parser.add_argument('--canonical',type=Path,default=os.environ.get('FROZEN_CANONICAL_PATH'))
    parser.add_argument('--canonical-sha256',default=os.environ.get('FROZEN_CANONICAL_SHA256'))
    parser.add_argument('--replays',type=Path,default=os.environ.get('FROZEN_REPLAYS_PATH'))
    parser.add_argument('--replays-sha256',default=os.environ.get('FROZEN_REPLAYS_SHA256'))
    parser.add_argument('--current-coverage',type=Path,default=os.environ.get('CURRENT_COVERAGE_PATH'))
    parser.add_argument('--current-coverage-sha256',default=os.environ.get('CURRENT_COVERAGE_SHA256'))
    parser.add_argument('--field-controls',type=Path,default=os.environ.get('FIELD_CONTROLS_PATH'))
    parser.add_argument('--field-controls-sha256',default=os.environ.get('FIELD_CONTROLS_SHA256'))
    parser.add_argument('--benchmark',type=Path,default=os.environ.get('FROZEN_BENCHMARK_PATH'))
    parser.add_argument('--benchmark-sha256',default=os.environ.get('FROZEN_BENCHMARK_SHA256'))
    parser.add_argument('--benchmark-tasks',type=Path)
    parser.add_argument('--benchmark-tasks-sha256')
    parser.add_argument('--pair-store',type=Path,default=Path(os.environ.get('SE6_PAIR_STORE','work/competition-pair-store')))
    parser.add_argument('--live-pair',action='store_true',help='Requires a new exact owner-approved pinned allowance. Never authorize via HTTP.')
    parser.add_argument('--pair-approval',type=Path)
    parser.add_argument('--pair-approval-sha256')
    parser.add_argument('--pair-simulation',action='store_true',help='Loopback offline acceptance only; explicit simulated responses, zero inference')
    args=parser.parse_args()
    if not args.origin and args.loopback_development:args.origin='http://127.0.0.1:'+str(args.port)
    if not args.origin:raise ValueError('Exact public HTTPS origin must be configured')
    if args.port in (8766,8777) or not (1024<=args.port<=65535 or (args.loopback_development and args.port==0)):raise ValueError('Hosted backend uses a separate unprivileged internal port')
    options=(args.native_bundle,args.native_manifest,args.native_manifest_sha256)
    if any(v is not None for v in options) and not all(v is not None for v in options):raise ValueError('Explicit reviewed Competition bundle, manifest and pin required together')
    if args.pair_simulation and (not args.loopback_development or args.live_pair):raise ValueError('Simulation requires isolated loopback and no live allowance')
    if any((args.live_pair,args.pair_simulation,args.pair_approval,args.pair_approval_sha256)) and not all(options):raise ValueError('Full reviewed native bundle required for paired execution')
    if (args.pair_approval or args.pair_approval_sha256) and not args.live_pair:raise ValueError('Allowance is accepted only with explicit live activation')
    gateway=PairGateway(args.native_bundle,args.pair_store,native_manifest=args.native_manifest,native_manifest_sha256=args.native_manifest_sha256,
        approval_path=args.pair_approval,approval_sha256=args.pair_approval_sha256,live_enabled=args.live_pair,simulated=args.pair_simulation) if all(options) else None
    service=JudgeService(*options,review=load_review(args.review,args.review_sha256),dynamic=load_dynamic(args.dynamic,args.dynamic_sha256),canonical=load_canonical(args.canonical,args.canonical_sha256),current_coverage=load_current_coverage(args.current_coverage,args.current_coverage_sha256),field_controls=load_field_controls(args.field_controls,args.field_controls_sha256),replays=load_replays(args.replays,args.replays_sha256),pair_gateway=gateway,asynchronous=True,realization_root=(args.pair_store/'recursive-realization' if all(options) and not args.pair_simulation else None))
    service.benchmark=load_benchmark(args.benchmark,args.benchmark_sha256)
    if args.benchmark_tasks or args.benchmark_tasks_sha256:
        if not all(options) or not args.benchmark_tasks or not args.benchmark_tasks_sha256:raise ValueError('Pinned tasks and actual native bundle required for offline repeats')
        service.benchmark_runner=BenchmarkTaskRunner(args.benchmark_tasks,args.benchmark_tasks_sha256,*options,args.pair_store/'benchmark-native-repeats',service.workers)
    server=make_server(service,args.origin,Path(__file__).with_name('static'),args.port,loopback_development=args.loopback_development)
    # Disable outgoing connections in parent too; accepted inbound sockets work.
    import socket
    def deny(*args,**kwargs):raise ValueError('Hosted public demo has no outbound network authority')
    socket.socket.connect=deny;socket.create_connection=deny;socket.getaddrinfo=deny
    socket.socket.connect_ex=deny;socket.socket.sendto=deny
    print('COMPETITION_RUN_BOTH_V11; '+('SIMULATED_TEST_ZERO_INFERENCE' if args.pair_simulation else 'EXACT_OWNER_ALLOWANCE_REQUIRED' if args.live_pair else 'DEFAULT_BLOCKED_ZERO_INFERENCE'),flush=True)
    print('JUDGE_URL='+server.public_origin,flush=True)
    try:server.serve_forever()
    finally:server.server_close()


if __name__=='__main__':main()
