"""Local entry point. No network, model-provider or production-runtime command."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


def install_runtime_fence(write_root=None, allow_children=False):
    """Defense in depth for the trusted local executable, not an OS sandbox."""
    root = Path(write_root).resolve() if write_root is not None else None
    sys.dont_write_bytecode = True

    def inside(path):
        if root is not None and isinstance(path, (str, bytes, os.PathLike)):
            resolved = Path(os.fsdecode(path)).resolve()
            if not resolved.is_relative_to(root):
                raise PermissionError("WRITE_OUTSIDE_REFERENCE_STORE")

    def fence(event, args):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"):
            raise PermissionError("NETWORK_NOT_AVAILABLE_IN_REFERENCE_DEVELOPMENT")
        if not allow_children and event in ("subprocess.Popen", "os.system", "os.posix_spawn"):
            raise PermissionError("CHILD_EXECUTION_NOT_AVAILABLE_IN_REFERENCE_ENGINE")
        if event == "open" and args:
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            if writing:
                inside(args[0])
        elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate") and args:
            inside(args[0])
        elif event in ("os.rename", "os.link", "os.symlink"):
            inside(args[0])
            inside(args[1])
    sys.addaudithook(fence)


def main():
    parser = argparse.ArgumentParser(description="SE6 persistent reference development extension")
    commands = parser.add_subparsers(dest="command", required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--store", type=Path, required=True)
    apply.add_argument("--authority", type=Path, required=True)
    apply.add_argument("--authority-sha", required=True)
    apply.add_argument("--request", type=Path, required=True)
    view = commands.add_parser("inspect")
    view.add_argument("--store", type=Path, required=True)
    view.add_argument("--expected-head", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    install_runtime_fence(args.store if args.command in ("apply", "inspect") else None,
                          allow_children=args.command == "demo")
    wall, cpu = time.perf_counter(), time.process_time()
    from se6_reference.codec import read_json
    if args.command == "apply":
        from se6_reference.storage import apply_request
        result = apply_request(args.store, args.authority, args.authority_sha, read_json(args.request))
    elif args.command == "inspect":
        from se6_reference.storage import inspect
        result = inspect(args.store, expected_head=args.expected_head)
    else:
        from se6_reference.demo import run_demo
        result = run_demo(args.out)
    result["invocation_measurements"] = {
        "wall_seconds": time.perf_counter() - wall,
        "current_process_cpu_seconds": time.process_time() - cpu,
        "scope": "Current process only; child process totals reported separately when available",
        "provider_calls": 0, "network_calls": 0,
        "billing_cost": None, "energy": None,
    }
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "FAILED_CLOSED", "error_type": type(error).__name__,
                          "error": str(error), "canonical_acceptance": "NOT_EVALUATED"}), file=sys.stderr)
        raise SystemExit(1)
