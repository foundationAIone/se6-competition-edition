"""Execute supplied Core and representation code without changing their semantics.

The source modules remain unchanged and their shadow/authority flags remain true
to the supplied contracts. An outer lineage binds successive X/Theta pairs;
Theta EXPANSION itself continues to preserve exactly the same X.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .codec import byte_hash, digest, encode, read_bytes, read_json, require

ROOT = Path(__file__).resolve().parents[1]


def check_sources():
    pins = read_json(ROOT / "SOURCE_PINS.json")
    for relative, expected in pins["files"].items():
        path = ROOT / relative
        require(byte_hash(read_bytes(path)) == expected,
                "SUPPLIED_CANONICAL_SOURCE_CHANGED:" + relative)
    runtime_files = ["se6_reference/" + name for name in
                     ("__init__.py", "codec.py", "canonical.py", "engine.py", "geometry.py", "storage.py")]
    runtime_files += ["run_reference.py", "vendor/se666_core/__init__.py"]
    implementation = {name: byte_hash(read_bytes(ROOT / name)) for name in runtime_files}
    result = digest({"upstream": pins, "extension_runtime": implementation})
    if "SOURCE_ID" in globals():
        require(result == SOURCE_ID, "REFERENCE_IMPLEMENTATION_CHANGED_DURING_PROCESS")
    return result


def _package(name, directory):
    if name in sys.modules:
        require(Path(sys.modules[name].__file__).resolve() ==
                (directory / "__init__.py").resolve(), "MODULE_NAMESPACE_COLLISION")
        return
    spec = importlib.util.spec_from_file_location(
        name, directory / "__init__.py", submodule_search_locations=[str(directory)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


SOURCE_ID = check_sources()
_package("_se6_reference_core", ROOT / "vendor" / "se_core")
_package("_se6_reference_contracts", ROOT / "vendor" / "se666_core")
core = importlib.import_module("_se6_reference_core.kernel")
frames = importlib.import_module("_se6_reference_contracts.realization_frame")
mapper = importlib.import_module("_se6_reference_contracts.universal_mapper")
E = importlib.import_module("_se6_reference_contracts.epistemic_status").EpistemicStatus
_REPLAY = ContextVar("se6_reference_recorded_replay", default=None)


@contextmanager
def replay_receipts(records):
    """Replay recorded consequences without invoking the live Native executor."""
    queue = list(records)
    token = _REPLAY.set(queue)
    try:
        yield
        require(not queue, "UNCONSUMED_REPLAY_NATIVE_RECEIPTS")
    finally:
        _REPLAY.reset(token)


def restore_core(state):
    engine = core.SE.restore(state["core_journal"], expected_head=state["core_head"])
    require(engine.state.identity == state["native_identity"], "NATIVE_ENTITY_BINDING")
    require(engine.state.actions_used == state["native_actions_used"], "NATIVE_COUNT_BINDING")
    return engine


def native(state, observation, permissions):
    engine = restore_core(state)
    context = {
        "identity": state["native_identity"], "authorized": True,
        "permissions": list(permissions), "integrity_valid": True,
        "evidence_valid": True, "max_actions": state["native_limit"],
        "risk": 0, "max_risk": 0, "sensitive": False,
        "human_approval_for": None,
    }
    queue = _REPLAY.get()
    if queue is None:
        _, receipt = engine.transition(engine.state, observation, context)
    else:
        require(queue, "MISSING_REPLAY_NATIVE_RECEIPT")
        saved_receipt = queue.pop(0)
        require(saved_receipt["observation"] == json.loads(encode(asdict(observation))) and
                saved_receipt["authority"] == encode(context).decode(), "REPLAY_NATIVE_REQUEST_BINDING")
        journal = json.loads(engine.dumps())
        journal["receipts"].append(saved_receipt)
        journal["state"] = saved_receipt["state_after"]
        # The public original-source restore replays and compares the recorded
        # transition using its saved consequence, never _local_action().
        engine = core.SE.restore(encode(journal).decode(), expected_head=saved_receipt["receipt_hash"])
        receipt = engine.receipts[-1]
    require(receipt.boundary.outcome == "ALLOW" and receipt.verification.passed,
            "NATIVE_TRANSITION_NOT_VERIFIED")
    state["core_journal"] = engine.dumps()
    state["core_head"] = receipt.receipt_hash
    state["native_actions_used"] = engine.state.actions_used
    return receipt


def retain(state, object_id, point, refs, *, correction):
    observation = core.SEObservation(
        kind="ASSERT", subject=object_id, predicate="position.base-metres",
        value=encode({"point": point, "space": state["space_id"]}).decode(),
        source="local-reference-observer", evidence_refs=tuple(refs),
        correction=correction)
    return native(state, observation, ("RETAIN_ASSERTION",))


def recall(state, object_id, refs):
    observation = core.SEObservation(
        kind="RECALL", subject=object_id, predicate="position.base-metres",
        source="local-reference-observer", evidence_refs=tuple(refs))
    receipt = native(state, observation, ("RECALL",))
    returned = json.loads(receipt.observed_consequence.result)
    require(returned["value"] is not None, "NATIVE_REFERENCE_UNKNOWN")
    value = json.loads(returned["value"])
    require(value["space"] == state["space_id"], "NATIVE_REFERENCE_SPACE")
    return value["point"], receipt.receipt_hash


def _source(reference, summary, refs):
    return frames.create_source_observation(
        source_reference=reference, summary=summary,
        epistemic_status=E.REPORTED, evidence_references=tuple(refs))


def projection(previous, state, request, grant_sha, source_refs):
    """Build actual canonical state/frame/map objects from the retained state."""
    old_x = (frames.RealizationState.model_validate_json(encode(previous["x"]))
             if previous else None)
    old_theta = (frames.RealizationFrame.model_validate_json(encode(previous["theta"]))
                 if previous else None)
    if request["op"] == "expand":
        theta = frames.expand_realization_frame(
            old_theta, frame_name="Persistent Entity reference",
            added_dimensions=request["dimensions"])
        x = old_x
        source = None
    else:
        summary = {
            "entity_id": state["entity_id"], "identity_state_id": state["identity_state_id"],
            "task": state["active_task"], "core_head": state["core_head"],
            "claims_sha256": digest({key: {k: v for k, v in value.items() if k != "observation"}
                                     for key, value in state["claims"].items()}),
            "pending_sha256": digest(state["pending"]),
            "actions_reserved": state["actions_reserved"],
            "native_actions_used": state["native_actions_used"],
            "scope": "Declared affine length reference; reported local file observations",
        }
        source = _source("grant:" + grant_sha,
                         encode({"operation": request["op"], "request_sha256": digest(request),
                                 "entity_id": state["entity_id"],
                                 "source_refs": source_refs}).decode(),
                         ["grant:" + grant_sha, *source_refs])
        if old_x is None:
            x = frames.create_realization_state(
                state_summary=encode(summary).decode(), source_observations=(source,))
        else:
            x = frames.advance_realization_state(
                old_x, state_summary=encode(summary).decode(), additional_observations=(source,))
        dimensions = old_theta.dimensions if old_theta else (
            "entity", "task", "world-object", "length", "source", "authority")
        theta = frames.create_realization_frame(
            x, frame_name="Persistent Entity reference", dimensions=dimensions,
            representation_rules=(
                "Exact rational base-metre coordinates bind Native retained assertions",
                "Declared affine frames; no inferred units, physical measurement or world truth",
                "Outer lineage binds Theta transport across changed X",
            ))
    state["x"] = x.model_dump(mode="json")
    state["theta"] = theta.model_dump(mode="json")
    state["frame_link"] = {
        "operation": "SAME_X_EXPANSION" if request["op"] == "expand" else "STATE_ADVANCE",
        "previous_x_hash": old_x.x_hash if old_x else None,
        "previous_theta_hash": old_theta.theta_hash if old_theta else None,
        "x_hash": x.x_hash, "theta_hash": theta.theta_hash,
        "entity_id": state["entity_id"],
    }
    if request["op"] == "expand":
        require(x == old_theta.x and theta.x == old_theta.x, "EXPANSION_CHANGED_X")
    else:
        # New source bindings are preserved separately from declared truth status.
        for object_id in state.pop("_new_claim_sources", []):
            state["claims"][object_id]["observation"] = source.model_dump(mode="json")
    state["mapping"] = _mapping(state, x).model_dump(mode="json")


def _mapping(state, x):
    anchor = x.source_observations[0]
    center = mapper.create_mapper_node(
        kind=mapper.NodeKind.CENTER, label="self:" + state["entity_id"],
        description="Stable declared Entity anchor, independent of task and interface",
        epistemic_status=E.REPORTED, source_observations=(anchor,))
    vertices = [center]
    relations = []
    measurements = []
    as_of = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=state["clock"])
    # Ticks are a disclosed logical clock anchored to 2000-01-01 for this model.
    from fractions import Fraction
    for object_id, claim in sorted(state["claims"].items()):
        observation = frames.SourceObservation.model_validate_json(encode(claim["observation"]))
        node = center if object_id == "self" else mapper.create_mapper_node(
            kind=mapper.NodeKind.THING, label=object_id,
            description="Stable world-object reference within " + state["space_id"],
            epistemic_status=E.REPORTED, source_observations=(anchor,))
        if object_id != "self":
            vertices.append(node)
            relations.append(mapper.create_mapper_relation(
                kind=mapper.RelationKind.RELATES_TO,
                label="self-to-object spatial reference; status=" + claim["status"],
                source_nodes=(center,), target_nodes=(node,),
                epistemic_status=E.REPORTED, source_observations=(observation,)))
        if claim["status"] == "CURRENT":
            for index, component in enumerate(claim["point"]):
                measurements.append(mapper.MappingMeasurement(
                    node=node.reference, quantity="position.axis." + str(index),
                    grounding=mapper.PeriodicGrounding.SYMBOLIC,
                    meaning="Reported affine coordinate; exact rational value retained in Native",
                    value=float(Fraction(component)), unit="metre",
                    reference_frame=state["space_id"],
                    observed_at_utc=datetime(2000, 1, 1, tzinfo=timezone.utc) +
                        timedelta(seconds=claim["observed_tick"]),
                    source_observation_bindings=(observation.binding,),
                    uncertainty="Declared local data only; floating projection never used for arithmetic"))
    graph = mapper.create_universal_map(vertices=vertices, relations=relations)
    return mapper.create_bounded_mapping(
        entity_id=state["entity_id"], identity_state_id=state["identity_state_id"],
        entity_state_id="entity_state_" + digest({"x": x.x_hash, "entity": state["entity_id"]}),
        as_of_utc=as_of, graph=graph,
        boundaries=tuple(mapper.NodeBoundary(
            node=node.reference, scope="Declared object identifier in " + state["space_id"])
            for node in vertices),
        measurements=tuple(measurements), source_observations=x.source_observations,
        uncertainty="Finite declared affine reference. No production identity, physical field or inferred semantics.")


def verify_projection(state):
    x = frames.RealizationState.model_validate_json(encode(state["x"]))
    theta = frames.RealizationFrame.model_validate_json(encode(state["theta"]))
    mapping = mapper.BoundedMapping.model_validate_json(encode(state["mapping"]))
    require(theta.x == x and mapping.entity_id == state["entity_id"], "CANONICAL_FRAME_BINDING")
    require(_mapping(state, x) == mapping, "CANONICAL_MAPPING_RECOMPUTATION")
    return mapping
