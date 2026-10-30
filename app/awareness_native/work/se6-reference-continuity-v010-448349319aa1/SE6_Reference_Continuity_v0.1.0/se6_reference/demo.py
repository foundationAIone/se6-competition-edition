"""Three-task local file-world demonstration of persistent SE6 reference.

The host owns the files, grants, action menu and coordinate bindings.  The
engine must choose from that menu using its persisted reference.  Every engine
operation runs in a fresh process.  The host executes the selected local file
move without using the engine's predicted result, then offers immutable
before/after files for engine verification.

This is a local development demonstration.  Its generated grants and chronology
are not independent production admission, a private challenge, or Alpha proof.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import sys
import time
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PERMISSIONS = {
    "create": ["CREATE_REFERENCE"],
    "attach": ["ATTACH_TASK"],
    "observe": ["READ_SOURCES", "RETAIN_ASSERTION"],
    "plan": ["RECALL", "PLAN_LOCAL_MOVE"],
    "renew": ["READ_SOURCES", "VERIFY_LOCAL_EFFECT", "RETAIN_ASSERTION"],
    "expand": ["EXPAND_FRAME"],
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_canonical(value) + b"\n")


def _q(value: Fraction | str | int) -> str:
    value = Fraction(value)
    return str(value.numerator) if value.denominator == 1 else str(value)


def _point(values: list[Any]) -> list[str]:
    return [_q(value) for value in values]


def _pointer_get(document: Any, pointer: str) -> Any:
    """Host-owned JSON pointer reader, separate from the engine mapper."""
    cursor = document
    for raw in pointer.split("/")[1:]:
        key = raw.replace("~1", "/").replace("~0", "~")
        cursor = cursor[int(key)] if isinstance(cursor, list) else cursor[key]
    return cursor


def _pointer_set(document: Any, pointer: str, value: Any) -> None:
    parts = [x.replace("~1", "/").replace("~0", "~")
             for x in pointer.split("/")[1:]]
    cursor = document
    for key in parts[:-1]:
        cursor = cursor[int(key)] if isinstance(cursor, list) else cursor[key]
    key = parts[-1]
    if isinstance(cursor, list):
        cursor[int(key)] = value
    else:
        cursor[key] = value


def _host_to_base(local: list[str], frame: dict[str, Any]) -> list[str]:
    values = [Fraction(v) for v in local]
    return _point([
        Fraction(origin) + sum(Fraction(a) * b for a, b in zip(row, values))
        for row, origin in zip(frame["matrix"], frame["origin"])
    ])


def _host_from_base(base: list[str], frame: dict[str, Any]) -> list[str]:
    """Explicit two-dimensional inverse used only by the demonstration host."""
    a, b = map(Fraction, frame["matrix"][0])
    c, d = map(Fraction, frame["matrix"][1])
    x, y = (Fraction(v) - Fraction(o)
            for v, o in zip(base, frame["origin"]))
    determinant = a * d - b * c
    return _point([(d * x - b * y) / determinant,
                   (-c * x + a * y) / determinant])


class _ProcessHost:
    """A local test host issuing a separate pinned grant per engine request."""

    def __init__(self, output: Path, entity_id: str) -> None:
        self.output = output
        self.store = output / "entity_store"
        self.entity_id = entity_id
        self.head: str | None = None
        self.sequence = 0
        self.tick = 0
        self.task: str | None = None
        self.sources: dict[str, dict[str, str]] = {}
        self.state: dict[str, Any] | None = None
        self.operations: list[dict[str, Any]] = []

    def source(self, token: str, payload: Any) -> Path:
        path = self.output / "sources" / (token + ".json")
        _write_new(path, payload)
        self.sources[token] = {
            "path": path.relative_to(self.output).as_posix(),
            "sha256": _file_hash(path),
        }
        return path

    def apply(self, request: dict[str, Any], *, actions: list[str] | None = None
              ) -> dict[str, Any]:
        self.tick += 1
        if request["op"] == "attach":
            task = request["task_id"]
        else:
            task = self.task
        if request["op"] == "create":
            task = None
        source_tokens = [request[key] for key in (
            "source_token", "before_source_token", "effect_source_token"
        ) if key in request]
        grant = {
            "schema": "se6-reference-grant-v1",
            "scope": "LOCAL_DEVELOPMENT_ONLY",
            "entity_id": self.entity_id,
            "sequence": self.sequence,
            "expected_head": self.head,
            "request_sha256": _digest(request),
            "operation": request["op"],
            "task_id": task,
            "permissions": PERMISSIONS[request["op"]],
            "now_tick": self.tick,
            "max_age_ticks": 100,
            "allowed_actions": actions or [],
            "task_action_limit": 1,
            "max_action_cost": "10",
            "sources": {token: self.sources[token] for token in source_tokens},
        }
        stem = f"{self.sequence:06d}-{request['op']}"
        grant_path = self.output / (stem + ".grant.json")
        request_path = self.output / "requests" / (stem + ".request.json")
        _write_new(grant_path, grant)
        _write_new(request_path, request)
        command = [
            sys.executable, str(PACKAGE_ROOT / "run_reference.py"), "apply",
            "--store", str(self.store),
            "--authority", str(grant_path),
            "--authority-sha", _file_hash(grant_path),
            "--request", str(request_path),
        ]
        started = time.perf_counter()
        completed = subprocess.run(
            command, cwd=PACKAGE_ROOT, capture_output=True, text=True,
            encoding="utf-8", timeout=30, check=False,
        )
        elapsed = time.perf_counter() - started
        if completed.returncode != 0:
            raise RuntimeError(
                f"Fresh-process operation {stem} failed: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Operation {stem} did not return JSON") from exc
        self.head = response["event_head"]
        self.state = response["state"]
        if self.state["entity_id"] != self.entity_id:
            raise AssertionError("Entity identity changed across a fresh process")
        self.operations.append({
            "sequence": self.sequence,
            "operation": request["op"],
            "task_id": task,
            "event_head": self.head,
            "native_identity": self.state["native_identity"],
            "native_actions_used": self.state["native_actions_used"],
            "actions_reserved": self.state["actions_reserved"],
            "x_hash": self.state["x"]["x_hash"],
            "theta_hash": self.state["theta"]["theta_hash"],
            "wall_seconds": elapsed,
            "process_cpu_seconds": response["invocation_measurements"]["current_process_cpu_seconds"],
            "fresh_process": True,
        })
        self.sequence += 1
        self.task = task
        return response


def _bindings(self_pointers: list[str], target_pointers: list[str] | None = None
              ) -> dict[str, Any]:
    bindings = [{"object_id": "self", "coordinates": self_pointers}]
    if target_pointers is not None:
        bindings.append({"object_id": "retained_destination",
                         "coordinates": target_pointers})
    return {"bindings": bindings}


def _source_document(label: str, local_self: list[str], *,
                     target: list[str] | None = None,
                     names: tuple[str, str, str] | None = None
                     ) -> tuple[dict[str, Any], list[str], list[str] | None]:
    if label == "A":
        payload = {"dispatch": {"cart": {"channels": local_self},
                                "dock": {"channels": target}},
                   "opaque_context": "delivery interface A"}
        return payload, ["/dispatch/cart/channels/0", "/dispatch/cart/channels/1"], [
            "/dispatch/dock/channels/0", "/dispatch/dock/channels/1"]
    if label == "B":
        payload = {"instrument": [{"samples": {"u": local_self[0],
                                                "v": local_self[1]}}],
                   "opaque_context": "maintenance interface B"}
        return payload, ["/instrument/0/samples/u", "/instrument/0/samples/v"], None
    if names is None:
        raise ValueError("Third interface needs its post-freeze schema names")
    root_name, first, second = names
    payload = {root_name: {"reading": {first: local_self[0], second: local_self[1]}},
               "opaque_context": "inspection interface C; host-declared schema"}
    return payload, [f"/{root_name}/reading/{first}",
                     f"/{root_name}/reading/{second}"], None


def run_demo(output: Path) -> dict[str, Any]:
    """Run and save one fresh local demonstration; never touches production."""
    started = time.perf_counter()
    parent_cpu_started = time.process_time()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Demo output directory must be empty; choose a fresh path")

    frozen_sources = {
        path.relative_to(PACKAGE_ROOT).as_posix(): _file_hash(path)
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts
    }
    if (PACKAGE_ROOT / "SOURCE_PINS.json").is_file():
        frozen_sources["SOURCE_PINS.json"] = _file_hash(PACKAGE_ROOT / "SOURCE_PINS.json")
    freeze_path = output / "CODE_FREEZE.json"
    _write_new(freeze_path, {
        "schema": "se6-local-demo-code-freeze-v1",
        "files": frozen_sources,
        "scope": "LOCAL_DEVELOPMENT_ONLY",
        "chronology": "Host-recorded; not independent canonical admission",
    })

    host = _ProcessHost(output, "instance_" + secrets.token_hex(32))
    created = host.apply({"op": "create", "dimension": 2,
                          "native_limit": 20, "action_limit": 4})
    native_identity = created["state"]["native_identity"]
    base_position = ["0", "0"]
    destination = ["4", "0"]
    frames = [
        {"id": "frame-a", "dimension": "length", "unit": "m",
         "matrix": [["1", "0"], ["0", "1"]], "origin": ["0", "0"]},
        {"id": "frame-b", "dimension": "length", "unit": "cm",
         "matrix": [["0", "-1/100"], ["1/100", "0"]], "origin": ["10", "2"]},
        {"id": "frame-c", "dimension": "length", "unit": "mm",
         "matrix": [["-1/1000", "0"], ["0", "-1/1000"]], "origin": ["6", "3"]},
    ]
    action_menus = [
        [{"id": "east", "delta": ["1", "0"], "cost": "1"},
         {"id": "hold", "delta": ["0", "0"], "cost": "0"},
         {"id": "west", "delta": ["-1", "0"], "cost": "1"}],
        [{"id": "forward", "delta": ["0", "-100"], "cost": "1"},
         {"id": "hold", "delta": ["0", "0"], "cost": "0"},
         {"id": "backward", "delta": ["0", "100"], "cost": "1"}],
        [{"id": "arrive", "delta": ["-2000", "0"], "cost": "2"},
         {"id": "hold", "delta": ["0", "0"], "cost": "0"},
         {"id": "retreat", "delta": ["2000", "0"], "cost": "2"}],
    ]
    roles = ["delivery", "maintenance", "inspection"]
    task_results: list[dict[str, Any]] = []
    target_claim_id: str | None = None
    target_source_sha256: str | None = None
    for index, (label, frame, actions, role) in enumerate(
            zip("ABC", frames, action_menus, roles)):
        task_id = f"task-{label.lower()}-{role}"
        host.apply({"op": "attach", "task_id": task_id,
                    "interface_id": f"interface-{label.lower()}", "role": role, "frame": frame})
        names = None
        if label == "C":
            # Generated only now, after the frozen source manifest was written.
            names = tuple("field_" + secrets.token_hex(6) for _ in range(3))
            _write_new(output / "THIRD_SCHEMA_RELEASE.json", {
                "schema": "se6-local-schema-release-v1",
                "code_freeze_sha256": _file_hash(freeze_path),
                "after_event_head": host.head,
                "field_names": list(names),
                "interpretation": "Host-declared coordinate bindings; not autonomous semantic discovery",
            })
        payload, self_pointers, target_pointers = _source_document(
            label, _host_from_base(base_position, frame),
            target=_host_from_base(destination, frame) if index == 0 else None,
            names=names,
        )
        before_token = f"{label.lower()}-before"
        before_path = host.source(before_token, payload)
        schema = _bindings(self_pointers, target_pointers)
        revisions = {}
        for binding in schema["bindings"]:
            object_id = binding["object_id"]
            old = host.state["claims"].get(object_id) if host.state else None
            revisions[object_id] = {
                "version": old["version"] + 1 if old else 1,
                "supersedes": old["claim_id"] if old else None,
            }
        observed = host.apply({
            "op": "observe", "source_token": before_token,
            "schema": schema, "frame": frame,
            "observed_tick": host.tick + 1, "revisions": revisions,
        })
        if index == 0:
            target_claim_id = observed["state"]["claims"]["retained_destination"]["claim_id"]
            target_source_sha256 = observed["state"]["claims"]["retained_destination"]["source_sha256"]
        else:
            if {binding["object_id"] for binding in schema["bindings"]} != {"self"}:
                raise AssertionError("Later task resupplied a world-target observation")
            if _file_hash(before_path) == target_source_sha256:
                raise AssertionError("Later task reused the original target observation source")
        planned = host.apply({
            "op": "plan", "target_id": "retained_destination", "actions": actions,
            "tolerance_squared": "0",
        }, actions=[action["id"] for action in actions])
        selection = planned["result"]
        chosen = selection["chosen"]
        if selection["target_claim_id"] != target_claim_id:
            raise AssertionError("Later task did not use the original retained destination")
        if not planned["state"]["pending"]:
            raise AssertionError("Planning failed to retain the unverified consequence")

        # The world consumes the chosen ID and its own offered action menu.  It
        # does not assign the prediction to the after file.
        host_action = next(action for action in actions if action["id"] == chosen["id"])
        independently_read_before = json.loads(before_path.read_bytes())
        before_local = [_q(_pointer_get(independently_read_before, pointer))
                        for pointer in self_pointers]
        after_local = _point([Fraction(a) + Fraction(b)
                              for a, b in zip(before_local, host_action["delta"])])
        after_payload = deepcopy(independently_read_before)
        for pointer, value in zip(self_pointers, after_local):
            _pointer_set(after_payload, pointer, value)
        after_token = f"{label.lower()}-after"
        after_path = host.source(after_token, after_payload)
        effect_token = f"{label.lower()}-effect"
        effect_path = host.source(effect_token, {
            "schema": "se6-local-move-effect-v1",
            "entity_id": host.entity_id, "task_id": task_id,
            "transaction_id": selection["transaction_id"], "action_id": chosen["id"],
            "before_sha256": _file_hash(before_path), "after_sha256": _file_hash(after_path),
        })
        independently_read_after = json.loads(after_path.read_bytes())
        actual_base = _host_to_base([
            _q(_pointer_get(independently_read_after, pointer)) for pointer in self_pointers
        ], frame)
        if actual_base != _point(chosen["predicted_position"]):
            raise AssertionError("Independent file-world result disagrees with prediction")
        renewed = host.apply({
            "op": "renew", "transaction_id": selection["transaction_id"],
            "before_source_token": before_token, "source_token": after_token,
            "effect_source_token": effect_token, "schema": _bindings(self_pointers),
            "frame": frame, "observed_tick": host.tick + 1,
        }, actions=[action["id"] for action in actions])
        if renewed["state"]["pending"] is not None:
            raise AssertionError("Verified renewal left a pending consequence")
        if _point(renewed["state"]["claims"]["self"]["point"]) != actual_base:
            raise AssertionError("Renewed reference differs from read-back world state")
        task_grants = (json.loads(path.read_bytes())
                       for path in sorted(output.glob("*.grant.json")))
        task_source_hashes = sorted({
            source["sha256"] for grant in task_grants if grant["task_id"] == task_id
            for source in grant["sources"].values()
        })
        if index > 0 and target_source_sha256 in task_source_hashes:
            raise AssertionError("Later current-task grant resupplied the original target source")
        distance_squared = sum((Fraction(a) - Fraction(b)) ** 2
                               for a, b in zip(actual_base, destination))
        task_results.append({
            "task_id": task_id, "interface_id": f"interface-{label.lower()}", "role": role,
            "frame": frame, "action_id": chosen["id"],
            "before_base_m": base_position, "after_base_m": actual_base,
            "predicted_base_m": _point(chosen["predicted_position"]),
            "prediction_verified": True,
            "goal_distance_squared_m2": _q(distance_squared),
            "goal_reached": distance_squared == 0,
            "target_coordinates_supplied_in_this_task": index == 0,
            "observed_object_ids_in_this_task": [binding["object_id"] for binding in schema["bindings"]],
            "current_task_source_sha256s": task_source_hashes,
            "current_task_sources_exclude_original_target_source": target_source_sha256 not in task_source_hashes,
            "target_claim_id_consumed": selection["target_claim_id"],
            "self_claim_id_consumed": selection["self_claim_id"],
            "transaction_id": selection["transaction_id"],
            "before_file_sha256": _file_hash(before_path),
            "after_file_sha256": _file_hash(after_path),
            "effect_file_sha256": _file_hash(effect_path),
            "renewal_event_head": renewed["event_head"],
            "native_actions_used": renewed["state"]["native_actions_used"],
            "actions_reserved": renewed["state"]["actions_reserved"],
        })
        base_position = actual_base

    before_expansion = deepcopy(host.state)
    expanded = host.apply({"op": "expand", "dimensions": ["task_role", "source_freshness"]})
    final = expanded["state"]
    if final["x"] != before_expansion["x"]:
        raise AssertionError("Interpretive expansion changed X")
    if final["theta"]["theta_hash"] == before_expansion["theta"]["theta_hash"]:
        raise AssertionError("Interpretive expansion failed to change Theta")
    if any(item["native_identity"] != native_identity for item in host.operations):
        raise AssertionError("Native identity was not retained across tasks")
    if base_position != destination:
        raise AssertionError("Final file-world position does not reach the retained destination")
    for relative, digest in frozen_sources.items():
        if _file_hash(PACKAGE_ROOT / relative) != digest:
            raise AssertionError("Source changed during the demonstration")

    report = {
        "schema": "se6-reference-demo-result-v1",
        "scope": "LOCAL_DEVELOPMENT_VERIFIED",
        "canonical_acceptance": "NOT_EVALUATED",
        "alpha_score_delta_claimed": False,
        "entity_id": host.entity_id, "native_identity": native_identity,
        "task_count": len(task_results), "tasks": task_results,
        "fresh_engine_processes": len(host.operations),
        "actual_local_file_moves": len(task_results),
        "verified_local_renewals": len(task_results),
        "native_actions_used": final["native_actions_used"],
        "actions_reserved": final["actions_reserved"],
        "final_position_m": base_position,
        "original_target_claim_id": target_claim_id,
        "original_target_source_sha256": target_source_sha256,
        "target_retained_without_resupply_in_later_tasks": True,
        "same_x_theta_expansion": {
            "verified": True, "x_hash": final["x"]["x_hash"],
            "before_theta_hash": before_expansion["theta"]["theta_hash"],
            "after_theta_hash": final["theta"]["theta_hash"],
        },
        "final_event_head": host.head,
        "code_freeze_sha256": _file_hash(freeze_path),
        "operations": host.operations,
        "resources": {
            "wall_seconds": time.perf_counter() - started,
            "host_cpu_seconds": time.process_time() - parent_cpu_started,
            "engine_child_cpu_seconds": sum(item["process_cpu_seconds"] for item in host.operations),
            "engine_child_cpu_measurement": "Sum of child internal process CPU timers; startup and teardown outside each timer excluded",
            "runtime_provider_calls": 0,
            "runtime_network_requests": 0,
            "model_usage_to_create_package": "NOT_MEASURED_HERE",
            "action_cost_units": "Synthetic local move penalty; not currency or model usage",
        },
        "limitations": [
            "Host-owned files and host-issued development grants; no physical or production action.",
            "Third-task keys are generated after code freeze, but host supplies their coordinate meaning.",
            "One retained two-dimensional destination across three declared interfaces; not general awareness.",
            "Only the third task reaches the final destination; earlier moves verify predicted intermediate consequences.",
            "No outside-grammar discovery, independent canonical admission, or Alpha PASS is established.",
            "Native counts are runtime resource counts, not ChatGPT or Codex account-usage measurements.",
        ],
    }
    _write_new(output / "DEMO_RESULT.json", report)
    lines = [
        "SE6 REFERENCE CONTINUITY — LOCAL DEVELOPMENT DEMONSTRATION",
        "Scope: LOCAL_DEVELOPMENT_VERIFIED",
        "Canonical acceptance: NOT_EVALUATED; no Alpha score change claimed.",
        "",
        f"Entity: {host.entity_id}",
        f"Fresh engine processes: {len(host.operations)}",
        f"Task interfaces: {len(task_results)}",
        f"Actual owned-file moves / verified renewals: {len(task_results)} / {len(task_results)}",
        f"Native actions used: {final['native_actions_used']}",
        f"Action reservations used: {final['actions_reserved']}",
        "",
    ]
    for task in task_results:
        lines.append(
            f"{task['task_id']}: {task['action_id']}; "
            f"base {task['before_base_m']} -> {task['after_base_m']}; "
            f"prediction verified; squared goal distance {task['goal_distance_squared_m2']}; "
            f"goal reached = {task['goal_reached']}."
        )
    lines += [
        "",
        "The original destination claim affected task B and task C without target coordinates being resupplied.",
        "Entity and Native identity survived every fresh process and all three roles/interfaces.",
        "The final interpretive expansion changed Theta while preserving exactly the same X.",
        f"Elapsed wall time: {report['resources']['wall_seconds']:.6f} seconds.",
        f"Engine-child CPU time: {report['resources']['engine_child_cpu_seconds']:.6f} seconds; startup/teardown outside child timers excluded.",
        "Host CPU is reported separately. Account/model usage for creating this package was not measured.",
        "",
        "Limits:",
        *["- " + item for item in report["limitations"]],
        "",
    ]
    with (output / "DEMO_REPORT.txt").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run_demo(arguments.output), indent=2, ensure_ascii=False))
