"""Verify and run this isolated development package once on the local computer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parent


def digest_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or later is required; use the existing SE6 virtual environment.")
    try:
        import pydantic
    except ImportError as error:
        raise RuntimeError("Pydantic 2 is missing in this Python environment. No dependency was downloaded.") from error
    if not str(pydantic.__version__).startswith("2."):
        raise RuntimeError("Pydantic 2 is required by the supplied canonical SE6 source.")
    manifest = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        if not path.is_file() or path.is_symlink() or digest_file(path) != expected:
            raise RuntimeError("Package file does not match the reviewed bundle: " + relative)
    result_path = ROOT / "LOCAL_SETUP_RESULT.json"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") == "LOCAL_DEVELOPMENT_VERIFIED":
            print("Existing completed local run found. No second run was started.")
            print("RESULT: " + str(ROOT / "SE6_REFERENCE_RESULT.zip"))
            return 0
        raise RuntimeError("A previous local attempt did not complete. Its evidence is preserved; no automatic retry.")
    out = ROOT / "local-run"
    if out.exists():
        raise RuntimeError("An earlier local run is incomplete. Its evidence is preserved; no automatic retry.")
    # This marker is exclusive and retained even on interruption. It is local
    # bookkeeping and grants no authority to the existing production runtime.
    marker = ROOT / "LOCAL_RUN_STARTED.json"
    write_json(marker, {"schema": "se6-reference-local-run-start-v1", "pid": os.getpid(),
                        "python": sys.version, "started_unix_seconds": time.time(),
                        "package_manifest_sha256": digest_file(ROOT / "PACKAGE_MANIFEST.json")})
    status = {"schema": "se6-reference-local-setup-v1", "status": "LOCAL_VERIFICATION_FAILED",
              "canonical_acceptance": "NOT_EVALUATED", "production_changes": False,
              "source_manifest_sha256": digest_file(ROOT / "PACKAGE_MANIFEST.json"),
              "python": sys.version, "pydantic": pydantic.__version__}
    try:
        print("Checking the isolated reference runtime...")
        tests = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
        (ROOT / "LOCAL_TEST_OUTPUT.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
        status["test_exit_code"] = tests.returncode
        if tests.returncode:
            raise RuntimeError("Local tests failed. See LOCAL_TEST_OUTPUT.txt; no demonstration was executed.")
        print("Running three tasks through fresh SE6 reference processes...")
        demo = subprocess.run([sys.executable, "-B", str(ROOT / "run_reference.py"), "demo", "--out", str(out)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
        (ROOT / "LOCAL_DEMO_STDOUT.json").write_text(demo.stdout, encoding="utf-8")
        (ROOT / "LOCAL_DEMO_STDERR.txt").write_text(demo.stderr, encoding="utf-8")
        status["demo_exit_code"] = demo.returncode
        if demo.returncode:
            raise RuntimeError("Local demonstration failed; its evidence is preserved.")
        result = json.loads(demo.stdout)
        if not (result["scope"] == "LOCAL_DEVELOPMENT_VERIFIED" and result["verified_local_renewals"] == 3
                and result["target_retained_without_resupply_in_later_tasks"] is True
                and result["same_x_theta_expansion"]["verified"] is True):
            raise RuntimeError("The expected reference behavior was not verified.")
        status.update(status="LOCAL_DEVELOPMENT_VERIFIED", task_count=result["task_count"],
                      fresh_engine_processes=result["fresh_engine_processes"],
                      native_actions_used=result["native_actions_used"],
                      actual_local_file_moves=result["actual_local_file_moves"],
                      verified_local_renewals=result["verified_local_renewals"],
                      final_position_m=result["final_position_m"], final_event_head=result["final_event_head"])
    except BaseException as error:
        status["error_type"], status["error"] = type(error).__name__, str(error)
        write_json(result_path, status)
        raise
    write_json(result_path, status)
    archive_path = ROOT / "SE6_REFERENCE_RESULT.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob("*")):
            if path.is_file() and not path.is_symlink():
                archive.write(path, path.relative_to(ROOT))
        for name in ("LOCAL_SETUP_RESULT.json", "LOCAL_TEST_OUTPUT.txt", "LOCAL_DEMO_STDOUT.json",
                     "LOCAL_DEMO_STDERR.txt", "LOCAL_RUN_STARTED.json", "PACKAGE_MANIFEST.json", "SOURCE_PINS.json"):
            archive.write(ROOT / name, name)
    print("\nLOCAL DEVELOPMENT VERIFIED")
    print("3 tasks; 14 fresh engine processes; 13 committed Native actions; 3 verified local renewals.")
    print("Retained destination consumed across metre, centimetre and millimetre task frames.")
    print("Canonical Alpha acceptance: NOT EVALUATED. Existing production files were not changed.")
    print("\nAttach this result ZIP in ChatGPT:")
    print(archive_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("\nSTOP: " + str(error), file=sys.stderr)
        raise SystemExit(1)
