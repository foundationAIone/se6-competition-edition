"""Bounded persistent reference operations over the unchanged supplied SE Core.

This host extension has one Entity reference and several distinct task
attachments. Explicitly declared observation layouts and affine frames are
supported. It does not discover semantic types or confer production authority.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import re

from . import canonical
from .codec import digest, encode, exact, identifier, require, uint
from .geometry import (add_vectors, distance_squared, observe_points, rational,
                       validate_frame, vector_to_base)

SCHEMA = "se6-persistent-reference-v1"
PERMISSIONS = {
    "create": {"CREATE_REFERENCE"},
    "attach": {"ATTACH_TASK"},
    "observe": {"READ_SOURCES", "RETAIN_ASSERTION"},
    "plan": {"RECALL", "PLAN_LOCAL_MOVE"},
    "renew": {"READ_SOURCES", "VERIFY_LOCAL_EFFECT", "RETAIN_ASSERTION"},
    "expand": {"EXPAND_FRAME"},
}


def _frame(state, frame):
    normalized = validate_frame(frame)
    require(len(normalized["origin"]) == state["dimension"], "REFERENCE_SPACE_DIMENSION")
    require(state["active_task"] is not None and
            normalized == state["active_task"]["frame"], "CURRENT_TASK_FRAME_REQUIRED")
    return normalized


def _native_room(state, count):
    require(state["native_actions_used"] + count <= state["native_limit"],
            "GLOBAL_NATIVE_BUDGET_EXHAUSTED")


def _current(state, object_id, grant):
    identifier(object_id)
    require(object_id in state["claims"], "REFERENCE_UNKNOWN:" + object_id)
    claim = state["claims"][object_id]
    require(claim["status"] == "CURRENT", "REFERENCE_CONFLICT:" + object_id)
    require(0 <= grant["now_tick"] - claim["observed_tick"] <= grant["max_age_ticks"],
            "REFERENCE_STALE:" + object_id)
    return claim


def _claim(state, object_id, point, observed_tick, version, supersedes,
           source_sha, task_id, refs, *, execute_native=True):
    require(len(state["claim_history"]) < 64, "CLAIM_HISTORY_BOUND")
    old = state["claims"].get(object_id)
    base = {"object_id": object_id, "point": point, "version": version,
            "observed_tick": observed_tick, "source_sha256": source_sha,
            "origin_task_id": task_id, "supersedes": supersedes,
            "status": "CURRENT", "conflicts": []}
    if old is not None:
        latest_tick = max([old["observed_tick"],
                           *(item["observed_tick"] for item in old["conflicts"])])
        require(observed_tick >= latest_tick, "OBSERVATION_TIME_ROLLBACK")
        if version == old["version"]:
            require(point != old["point"], "DUPLICATE_OBSERVATION_NO_ADVANCE")
            require(supersedes is None, "CONFLICT_CANNOT_SELF_AUTHORIZE_CORRECTION")
            base = {**deepcopy(old), "status": "CONFLICT"}
            base.pop("observation", None)
            base.pop("claim_id", None)
            base["conflicts"].append({"point": point, "observed_tick": observed_tick,
                                      "source_sha256": source_sha})
        else:
            require(version == old["version"] + 1 and supersedes == old["claim_id"],
                    "EXACT_PRIOR_CLAIM_CORRECTION_REQUIRED")
            require(observed_tick > latest_tick, "CORRECTION_MUST_BE_NEWER")
    else:
        require(version == 1 and supersedes is None, "CLAIM_GENESIS_VERSION")
    base["claim_id"] = digest(base)
    # Earlier source claims remain in claim_history and canonical X observations.
    state["claim_history"].append(deepcopy(base))
    state["claims"][object_id] = base
    state.setdefault("_new_claim_sources", []).append(object_id)
    if base["status"] == "CURRENT" and execute_native:
        receipt = canonical.retain(state, object_id, point, refs, correction=old is not None)
        return receipt.receipt_hash
    return None


def reduce(previous, request, grant, grant_sha, witness):
    """A deterministic transition; external movement is performed by the host.

    The independent local witness supplies bytes under an explicitly pinned
    development grant. Native action receipts here attest local Core behavior,
    not the truth of an external physical world.
    """
    require(type(request) is dict and request.get("op") in PERMISSIONS, "OPERATION")
    op = request["op"]
    require(grant["operation"] == op and PERMISSIONS[op] <= set(grant["permissions"]),
            "CURRENT_OPERATION_PERMISSION_REQUIRED")
    require(digest(request) == grant["request_sha256"], "EXACT_GRANTED_REQUEST_REQUIRED")
    require(re.fullmatch(r"instance_[0-9a-f]{64}", grant["entity_id"]) is not None,
            "ENTITY_IDENTIFIER")
    uint(grant["now_tick"])
    uint(grant["max_age_ticks"])
    uint(grant["task_action_limit"], 20)
    require(rational(grant["max_action_cost"]) >= 0, "NONNEGATIVE_ACTION_COST_LIMIT")
    result = {}
    if op == "create":
        exact(request, {"op", "dimension", "native_limit", "action_limit"}, "CREATE_SCHEMA")
        require(previous is None and grant["task_id"] is None, "REFERENCE_ALREADY_EXISTS")
        require(type(request["dimension"]) is int and 1 <= request["dimension"] <= 3,
                "DIMENSION_BOUND")
        require(type(request["native_limit"]) is int and 1 <= request["native_limit"] <= 20,
                "NATIVE_LIMIT_BOUND")
        require(type(request["action_limit"]) is int and 1 <= request["action_limit"] <= 20,
                "ACTION_LIMIT_BOUND")
        identity = grant["entity_id"]
        engine = canonical.core.SE(canonical.core.SEState("reference-entity:" + identity))
        state = {
            "schema": SCHEMA, "entity_id": identity,
            "identity_state_id": "identity_" + digest({"entity": identity, "grant": grant_sha}),
            "native_identity": engine.state.identity,
            "source_id": canonical.SOURCE_ID, "dimension": request["dimension"],
            "space_id": "space:" + digest({"entity": identity, "dimension": request["dimension"]}),
            "native_limit": request["native_limit"], "action_limit": request["action_limit"],
            "native_actions_used": 0, "actions_reserved": 0,
            "task_actions": {}, "task_history": [], "frames": {}, "active_task": None,
            "claims": {}, "claim_history": [], "pending": None,
            "core_journal": engine.dumps(), "core_head": None,
            "clock": grant["now_tick"], "generation": 0,
        }
        result = {"status": "REFERENCE_CREATED", "entity_id": identity}
    else:
        require(previous is not None, "REFERENCE_NOT_CREATED")
        require(previous["entity_id"] == grant["entity_id"], "CROSS_ENTITY_GRANT")
        require(previous["source_id"] == canonical.SOURCE_ID, "REFERENCE_SOURCE_VERSION")
        canonical.verify_projection(previous)
        canonical.restore_core(previous)
        require(grant["now_tick"] >= previous["clock"], "GLOBAL_CLOCK_ROLLBACK")
        require(previous["generation"] < 63, "REFERENCE_TRANSITION_LIMIT")
        require(previous["pending"] is None or op == "renew", "PENDING_CONSEQUENCE_BLOCKS_TRANSITION")
        state = deepcopy(previous)
        state["clock"] = grant["now_tick"]
        state["generation"] += 1
        if op != "attach":
            require(state["active_task"] is not None and
                    grant["task_id"] == state["active_task"]["id"], "CURRENT_TASK_AUTHORITY")
        if op == "attach":
            result = _attach(state, request, grant)
        elif op == "observe":
            result = _observe(state, request, grant, witness)
        elif op == "plan":
            result = _plan(state, request, grant, grant_sha)
        elif op == "renew":
            result = _renew(state, request, grant, witness)
        elif op == "expand":
            exact(request, {"op", "dimensions"}, "EXPAND_SCHEMA")
            require(type(request["dimensions"]) is list and 1 <= len(request["dimensions"]) <= 8,
                    "EXPANSION_BOUND")
            for dimension in request["dimensions"]:
                identifier(dimension)
            require(len(set(request["dimensions"])) == len(request["dimensions"]), "DUPLICATE_DIMENSION")
            require(all(d not in previous["theta"]["dimensions"] for d in request["dimensions"]),
                    "EXPANSION_REQUIRES_NEW_DIMENSION")
            result = {"status": "REPRESENTATION_EXPANDED", "x_unchanged": True}
    canonical.projection(previous, state, request, grant_sha, witness.used)
    canonical.verify_projection(state)
    return state, result


def _attach(state, request, grant):
    exact(request, {"op", "task_id", "interface_id", "role", "frame"}, "ATTACH_SCHEMA")
    for name in ("task_id", "interface_id", "role"):
        identifier(request[name])
    require(request["task_id"] == grant["task_id"], "TASK_ATTACHMENT_AUTHORITY")
    require(len(state["task_history"]) < 16, "TASK_ATTACHMENT_BOUND")
    frame = validate_frame(request["frame"])
    require(len(frame["origin"]) == state["dimension"], "REFERENCE_SPACE_DIMENSION")
    if frame["id"] in state["frames"]:
        require(state["frames"][frame["id"]] == frame, "FRAME_ID_CANNOT_CHANGE_MEANING")
    state["frames"][frame["id"]] = frame
    task = {"id": request["task_id"], "interface_id": request["interface_id"],
            "role": request["role"], "frame": frame}
    entry = {"task": task, "previous_task": deepcopy(state["active_task"]),
             "native_head_at_entry": state["core_head"],
             "claims_sha256_at_entry": digest(state["claims"]),
             "actions_reserved_at_entry": state["actions_reserved"]}
    state["task_history"].append(entry)
    state["task_actions"].setdefault(task["id"], 0)
    state["active_task"] = task
    return {"status": "TASK_ATTACHED", "task_id": task["id"],
            "native_identity": state["native_identity"],
            "retained_claim_ids": {k: v["claim_id"] for k, v in state["claims"].items()}}


def _observe(state, request, grant, witness):
    exact(request, {"op", "source_token", "schema", "frame", "observed_tick", "revisions"},
          "OBSERVE_SCHEMA")
    frame = _frame(state, request["frame"])
    tick = uint(request["observed_tick"])
    require(tick <= grant["now_tick"], "FUTURE_OBSERVATION")
    document, source_sha = witness.read(request["source_token"])
    points = observe_points(document, request["schema"], frame)
    require(set(points) == set(request["revisions"]), "EXACT_OBSERVATION_REVISIONS")
    require(len(set(state["claims"]) | set(points)) <= 16, "REFERENCE_OBJECT_BOUND")
    require(len(state["claim_history"]) + len(points) <= 64, "CLAIM_HISTORY_BOUND")
    _native_room(state, len(points))
    # Validate the whole observation batch before any live Native call. A bad
    # later row must not cause an unrecorded earlier execution in the same batch.
    trial = deepcopy(state)
    for object_id, point in sorted(points.items()):
        identifier(object_id)
        revision = request["revisions"][object_id]
        exact(revision, {"version", "supersedes"}, "REVISION_SCHEMA")
        uint(revision["version"], 64)
        _claim(trial, object_id, point, tick, revision["version"], revision["supersedes"],
               source_sha, state["active_task"]["id"], ["file:" + source_sha], execute_native=False)
    receipts = []
    for object_id, point in sorted(points.items()):
        revision = request["revisions"][object_id]
        receipt = _claim(state, object_id, point, tick, revision["version"],
                         revision["supersedes"], source_sha, state["active_task"]["id"],
                         ["file:" + source_sha])
        if receipt:
            receipts.append(receipt)
    return {"status": "OBSERVATIONS_RETAINED", "native_receipts": receipts,
            "claims": {k: state["claims"][k]["claim_id"] for k in points},
            "conflicts": [k for k in points if state["claims"][k]["status"] == "CONFLICT"]}


def _plan(state, request, grant, grant_sha):
    exact(request, {"op", "target_id", "actions", "tolerance_squared"}, "PLAN_SCHEMA")
    require(request["target_id"] != "self", "WORLD_TARGET_REQUIRED")
    target_claim = _current(state, request["target_id"], grant)
    self_claim = _current(state, "self", grant)
    tolerance = rational(request["tolerance_squared"])
    require(tolerance >= 0, "NONNEGATIVE_GOAL_TOLERANCE")
    require(type(request["actions"]) is list and 1 <= len(request["actions"]) <= 32,
            "ACTION_SET_BOUND")
    require(state["actions_reserved"] < state["action_limit"], "GLOBAL_ACTION_BUDGET_EXHAUSTED")
    task = state["active_task"]
    require(state["task_actions"][task["id"]] < grant["task_action_limit"],
            "CURRENT_TASK_ACTION_BUDGET_EXHAUSTED")
    require(state["generation"] < 63, "RESERVE_RENEWAL_TRANSITION")
    require(len(state["claim_history"]) < 64, "RESERVE_RENEWAL_CLAIM_HISTORY")
    # A selected move must leave room to retain its mandatory observed successor.
    # No other operation is allowed while it is pending, so this is a reservation
    # against the fixed global Native cap, not an unaccounted extra allowance.
    _native_room(state, 3)
    # The actual canonical map resolves the stable referents, while exact values
    # come from the original Native RECALL consequences, never task input values.
    # Previous projection was independently recomputed before this operation.
    # Its as-of clock remains the observed prior state's clock until renewal.
    mapping = canonical.mapper.BoundedMapping.model_validate_json(encode(state["mapping"]))
    labels = {node.label for node in mapping.graph.vertices}
    require(request["target_id"] in labels and "self:" + state["entity_id"] in labels,
            "CANONICAL_REFERENCE_NODES_REQUIRED")
    admitted = []
    seen = set()
    for action in request["actions"]:
        exact(action, {"id", "delta", "cost"}, "ACTION_SCHEMA")
        identifier(action["id"])
        require(action["id"] not in seen, "ACTION_ID_DUPLICATE")
        seen.add(action["id"])
        # A known but unauthorized candidate is ineligible, not newly authorized
        # because its expected effect would be useful.
        delta = vector_to_base(action["delta"], task["frame"])
        cost = rational(action["cost"])
        require(cost >= 0, "ACTION_COST_NONNEGATIVE")
        if action["id"] not in grant["allowed_actions"] or cost > rational(grant["max_action_cost"]):
            continue
        admitted.append({**deepcopy(action), "cost": str(cost), "delta_base": delta})
    require(admitted, "NO_CURRENT_AUTHORIZED_ACTION")
    refs = ["grant:" + grant_sha, "claim:" + self_claim["claim_id"],
            "claim:" + target_claim["claim_id"]]
    self_point, self_receipt = canonical.recall(state, "self", refs)
    target_point, target_receipt = canonical.recall(state, request["target_id"], refs)
    require(self_point == self_claim["point"] and target_point == target_claim["point"],
            "RETAINED_NATIVE_VALUE_BINDING")
    candidates = []
    for action in admitted:
        predicted = add_vectors(self_point, action["delta_base"])
        candidates.append({**action,
                           "predicted_position": predicted,
                           "distance_squared": str(distance_squared(predicted, target_point))})
    chosen = min(candidates, key=lambda row: (Fraction(row["distance_squared"]),
                                             Fraction(row["cost"]), row["id"]))
    material = {"entity_id": state["entity_id"], "task_id": task["id"],
                "authority_sha256": grant_sha, "chosen": chosen,
                "self_claim_id": self_claim["claim_id"], "target_claim_id": target_claim["claim_id"],
                "target_id": request["target_id"], "self_point": self_point,
                "target_point": target_point, "frame": deepcopy(task["frame"]),
                "source_frame_sha256": digest(state["theta"]),
                "mapping_sha256": mapping.mapping_hash,
                "native_recall_receipts": [self_receipt, target_receipt],
                "tolerance_squared": str(tolerance), "planned_at_tick": grant["now_tick"]}
    transaction_id = "move:" + digest(material)
    state["pending"] = {**material, "transaction_id": transaction_id}
    state["actions_reserved"] += 1
    state["task_actions"][task["id"]] += 1
    return {"status": "PENDING_LOCAL_CONSEQUENCE", "transaction_id": transaction_id,
            "chosen": deepcopy(chosen), "candidates": candidates,
            "self_claim_id": self_claim["claim_id"], "target_claim_id": target_claim["claim_id"],
            "native_recall_receipts": [self_receipt, target_receipt],
            "policy": "Exact target distance squared, then public cost and ID",
            "world_truth_verified": False}


def _renew(state, request, grant, witness):
    exact(request, {"op", "transaction_id", "before_source_token", "source_token",
                    "effect_source_token", "schema", "frame", "observed_tick"}, "RENEW_SCHEMA")
    pending = state["pending"]
    require(pending is not None and request["transaction_id"] == pending["transaction_id"],
            "PENDING_TRANSACTION_REQUIRED")
    frame = _frame(state, request["frame"])
    require(frame == pending["frame"], "PENDING_FRAME_BINDING")
    tick = uint(request["observed_tick"])
    require(state["claims"]["self"]["observed_tick"] < tick <= grant["now_tick"] and
            tick >= pending["planned_at_tick"], "EFFECT_OBSERVATION_CHRONOLOGY")
    before, before_sha = witness.read(request["before_source_token"])
    after, after_sha = witness.read(request["source_token"])
    effect, _ = witness.read(request["effect_source_token"])
    exact(effect, {"schema", "entity_id", "task_id", "transaction_id", "action_id",
                   "before_sha256", "after_sha256"}, "LOCAL_EFFECT_RECEIPT_SCHEMA")
    require(effect == {"schema": "se6-local-move-effect-v1", "entity_id": state["entity_id"],
                       "task_id": state["active_task"]["id"], "transaction_id": pending["transaction_id"],
                       "action_id": pending["chosen"]["id"], "before_sha256": before_sha,
                       "after_sha256": after_sha}, "INDEPENDENT_EFFECT_BYTES_BINDING")
    before_points = observe_points(before, request["schema"], frame)
    after_points = observe_points(after, request["schema"], frame)
    require(set(before_points) == {"self"} and set(after_points) == {"self"}, "SELF_ONLY_CONSEQUENCE")
    require(before_points["self"] == pending["self_point"], "ACTUAL_BEFORE_STATE_MISMATCH")
    require(after_points["self"] == pending["chosen"]["predicted_position"] and
            after_points["self"] == add_vectors(before_points["self"], pending["chosen"]["delta_base"]),
            "ACTUAL_CONSEQUENCE_MISMATCH")
    _native_room(state, 1)
    old = state["claims"]["self"]
    receipt = _claim(state, "self", after_points["self"], tick, old["version"] + 1,
                     old["claim_id"], after_sha, state["active_task"]["id"],
                     ["file:" + before_sha, "file:" + after_sha, "transaction:" + pending["transaction_id"]])
    distance = distance_squared(after_points["self"], pending["target_point"])
    result = {"status": "LOCAL_CONSEQUENCE_VERIFIED_AND_RENEWED",
              "transaction_id": pending["transaction_id"], "observed_position": after_points["self"],
              "distance_squared": str(distance), "goal_reached": distance <= rational(pending["tolerance_squared"]),
              "native_receipt": receipt, "actual_local_bytes_verified": True,
              "physical_world_truth_verified": False}
    state["pending"] = None
    return result
