"""Functional boundary and continuity checks for the local reference engine.

The tests issue real separately hashed local development grant files.  They do
not create production authorization, novelty certificates or Alpha acceptance.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from se6_reference.codec import ReferenceError
from se6_reference import canonical
from se6_reference.engine import reduce
from se6_reference.storage import FileWitness, apply_request, inspect as inspect_reference


FRAME = {"id": "test-frame", "dimension": "length", "unit": "m",
         "matrix": [["1", "0"], ["0", "1"]], "origin": ["0", "0"]}
FULL_SCHEMA = {"bindings": [
    {"object_id": "self", "coordinates": ["/payload/self/0", "/payload/self/1"]},
    {"object_id": "goal", "coordinates": ["/payload/destination/0", "/payload/destination/1"]},
]}
SELF_SCHEMA = {"bindings": [FULL_SCHEMA["bindings"][0]]}
GOAL_SCHEMA = {"bindings": [FULL_SCHEMA["bindings"][1]]}
ACTIONS = [{"id": "east", "delta": ["1", "0"], "cost": "1"},
           {"id": "hold", "delta": ["0", "0"], "cost": "0"},
           {"id": "west", "delta": ["-1", "0"], "cost": "1"}]
PERMISSIONS = {
    "create": ["CREATE_REFERENCE"], "attach": ["ATTACH_TASK"],
    "observe": ["READ_SOURCES", "RETAIN_ASSERTION"],
    "plan": ["RECALL", "PLAN_LOCAL_MOVE"],
    "renew": ["READ_SOURCES", "VERIFY_LOCAL_EFFECT", "RETAIN_ASSERTION"],
    "expand": ["EXPAND_FRAME"],
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


class Harness:
    def __init__(self, root):
        self.root = Path(root)
        self.host = self.root / "host"
        self.host.mkdir(parents=True)
        self.store = self.root / "store"
        self.entity_id = "instance_" + "a" * 64
        self.sequence = 0
        self.serial = 0
        self.head = None
        self.state = None
        self.task_id = None
        self.tick = 0
        self.sources = {}

    def source(self, token, payload):
        path = self.host / "sources" / (token + ".json")
        write(path, payload)
        self.sources[token] = {"path": path.relative_to(self.host).as_posix(),
                               "sha256": file_hash(path)}
        return path

    def prepare(self, request, **changes):
        request = deepcopy(request)
        op = request["op"]
        task_id = request["task_id"] if op == "attach" else self.task_id
        tokens = [request[key] for key in ("source_token", "before_source_token",
                                          "effect_source_token") if key in request]
        grant = {
            "schema": "se6-reference-grant-v1", "scope": "LOCAL_DEVELOPMENT_ONLY",
            "entity_id": self.entity_id, "sequence": self.sequence,
            "expected_head": self.head, "request_sha256": digest(request),
            "operation": op, "task_id": None if op == "create" else task_id,
            "permissions": PERMISSIONS[op], "now_tick": self.tick + 1,
            "max_age_ticks": 100, "allowed_actions": [a["id"] for a in ACTIONS],
            "task_action_limit": 1, "max_action_cost": "2",
            "sources": {token: self.sources[token] for token in tokens},
        }
        grant.update(changes)
        grant_file = self.host / f"grant-{self.serial:06d}.json"
        self.serial += 1
        write(grant_file, grant)
        return grant_file, file_hash(grant_file), request, grant

    def invoke(self, prepared):
        grant_file, grant_sha, request, grant = prepared
        response = apply_request(self.store, grant_file, grant_sha, request)
        self.head = response["event_head"]
        self.state = response["state"]
        self.sequence += 1
        self.tick = grant["now_tick"]
        self.task_id = grant["task_id"]
        return response

    def call(self, request, **changes):
        return self.invoke(self.prepare(request, **changes))

    def create(self, *, action_limit=4, native_limit=20):
        return self.call({"op": "create", "dimension": 2,
                          "native_limit": native_limit, "action_limit": action_limit})

    def attach(self, task="task-a", **changes):
        return self.call({"op": "attach", "task_id": task,
                          "interface_id": "interface-" + task, "role": "test-role",
                          "frame": FRAME}, **changes)

    def initialize(self, *, action_limit=4, native_limit=20):
        self.create(action_limit=action_limit, native_limit=native_limit)
        self.attach()
        self.source("before", {"payload": {"self": ["0", "0"],
                                            "destination": ["4", "0"]}})
        return self.call({
            "op": "observe", "source_token": "before", "schema": FULL_SCHEMA,
            "frame": FRAME, "observed_tick": self.tick + 1,
            "revisions": {"self": {"version": 1, "supersedes": None},
                          "goal": {"version": 1, "supersedes": None}},
        })

    def plan_request(self):
        return {"op": "plan", "target_id": "goal", "actions": deepcopy(ACTIONS),
                "tolerance_squared": "0"}

    def plan(self, **changes):
        return self.call(self.plan_request(), **changes)

    def renewal_request(self, *, after="1", wrong_transaction=False):
        pending = self.state["pending"]
        self.source("after", {"payload": {"self": [after, "0"]}})
        self.source("effect", {
            "schema": "se6-local-move-effect-v1", "entity_id": self.entity_id,
            "task_id": self.task_id,
            "transaction_id": "move:" + "0" * 64 if wrong_transaction
                              else pending["transaction_id"],
            "action_id": pending["chosen"]["id"],
            "before_sha256": self.sources["before"]["sha256"],
            "after_sha256": self.sources["after"]["sha256"],
        })
        return {
            "op": "renew", "transaction_id": pending["transaction_id"],
            "before_source_token": "before", "source_token": "after",
            "effect_source_token": "effect", "schema": SELF_SCHEMA,
            "frame": FRAME, "observed_tick": self.tick + 1,
        }


class ReferenceContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="se6-reference-test-")
        self.h = Harness(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def assert_rejected(self, callback):
        head = self.h.head
        with self.assertRaises(ReferenceError):
            callback()
        self.assertEqual(self.h.head, head)
        if head is not None:
            self.assertEqual(json.loads((self.h.store / "CURRENT.json").read_bytes())["head"], head)

    def test_actual_native_recall_and_file_renewal_retain_reference(self):
        self.h.initialize()
        goal_id = self.h.state["claims"]["goal"]["claim_id"]
        native_identity = self.h.state["native_identity"]
        planned = self.h.plan()
        self.assertEqual(planned["result"]["chosen"]["id"], "east")
        self.assertEqual(planned["result"]["target_claim_id"], goal_id)
        self.assertEqual(len(planned["result"]["native_recall_receipts"]), 2)
        self.assertIsNotNone(planned["state"]["pending"])
        renewed = self.h.call(self.h.renewal_request())
        self.assertTrue(renewed["result"]["actual_local_bytes_verified"])
        self.assertFalse(renewed["result"]["physical_world_truth_verified"])
        self.assertFalse(renewed["result"]["goal_reached"])
        self.assertEqual(renewed["state"]["claims"]["self"]["point"], ["1", "0"])
        self.assertIsNone(renewed["state"]["pending"])
        attached = self.h.attach("task-b")
        self.assertEqual(attached["state"]["claims"]["goal"]["claim_id"], goal_id)
        self.assertEqual(attached["state"]["native_identity"], native_identity)
        self.assertEqual(attached["state"]["native_actions_used"], 5)
        self.assertEqual(attached["state"]["actions_reserved"], 1)

    def test_stale_reference_is_ineligible(self):
        self.h.initialize()
        self.assert_rejected(lambda: self.h.plan(now_tick=200, max_age_ticks=10))

    def test_same_version_disagreement_conflicts_and_blocks_action(self):
        self.h.initialize()
        self.h.source("disagreement", {"payload": {"destination": ["-4", "0"]}})
        conflict = self.h.call({
            "op": "observe", "source_token": "disagreement", "schema": GOAL_SCHEMA,
            "frame": FRAME, "observed_tick": self.h.tick + 1,
            "revisions": {"goal": {"version": 1, "supersedes": None}},
        })
        self.assertEqual(conflict["state"]["claims"]["goal"]["status"], "CONFLICT")
        self.assert_rejected(self.h.plan)

    def test_explicit_new_version_correction_changes_selected_direction(self):
        baseline = Harness(Path(self.temp.name) / "baseline")
        baseline.initialize()
        baseline_plan = baseline.plan()
        self.h.initialize()
        old_id = self.h.state["claims"]["goal"]["claim_id"]
        self.h.source("correction", {"payload": {"destination": ["-4", "0"]}})
        self.h.call({
            "op": "observe", "source_token": "correction", "schema": GOAL_SCHEMA,
            "frame": FRAME, "observed_tick": self.h.tick + 1,
            "revisions": {"goal": {"version": 2, "supersedes": old_id}},
        })
        planned = self.h.plan()
        self.assertEqual(baseline_plan["result"]["chosen"]["id"], "east")
        self.assertEqual(baseline.plan_request()["actions"], self.h.plan_request()["actions"])
        self.assertEqual(planned["result"]["chosen"]["id"], "west")
        self.assertNotEqual(planned["result"]["target_claim_id"], old_id)
        self.assertTrue(any(claim["claim_id"] == old_id
                            for claim in planned["state"]["claim_history"]))

    def test_missing_retained_target_blocks_same_action_menu(self):
        self.h.create()
        self.h.attach()
        self.h.source("self-only", {"payload": {"self": ["0", "0"]}})
        self.h.call({
            "op": "observe", "source_token": "self-only", "schema": SELF_SCHEMA,
            "frame": FRAME, "observed_tick": self.h.tick + 1,
            "revisions": {"self": {"version": 1, "supersedes": None}},
        })
        self.assertNotIn("goal", self.h.state["claims"])
        self.assert_rejected(self.h.plan)
        self.assertEqual(self.h.state["actions_reserved"], 0)

    def test_correction_must_be_newer_than_all_conflicting_evidence(self):
        self.h.initialize()
        conflict_tick = self.h.tick + 10
        self.h.source("later-conflict", {"payload": {"destination": ["-4", "0"]}})
        self.h.call({
            "op": "observe", "source_token": "later-conflict", "schema": GOAL_SCHEMA,
            "frame": FRAME, "observed_tick": conflict_tick,
            "revisions": {"goal": {"version": 1, "supersedes": None}},
        }, now_tick=conflict_tick)
        conflict_id = self.h.state["claims"]["goal"]["claim_id"]
        self.h.source("stale-correction", {"payload": {"destination": ["6", "0"]}})
        self.assert_rejected(lambda: self.h.call({
            "op": "observe", "source_token": "stale-correction", "schema": GOAL_SCHEMA,
            "frame": FRAME, "observed_tick": conflict_tick - 1,
            "revisions": {"goal": {"version": 2, "supersedes": conflict_id}},
        }))

    def test_cross_entity_grant_cannot_attach(self):
        self.h.create()
        self.assert_rejected(lambda: self.h.attach(entity_id="instance_" + "b" * 64))

    def test_stale_external_head_cannot_continue(self):
        created = self.h.create()
        self.h.attach()
        self.assert_rejected(lambda: self.h.attach("task-b", expected_head=created["event_head"]))

    def test_missing_current_permission_cannot_inherit_prior_authority(self):
        self.h.initialize()
        self.assert_rejected(lambda: self.h.plan(permissions=["RECALL"]))
        self.assertEqual(self.h.state["actions_reserved"], 0)

    def test_no_currently_allowed_action_cannot_reserve(self):
        self.h.initialize()
        self.assert_rejected(lambda: self.h.plan(allowed_actions=[]))
        self.assertEqual(self.h.state["actions_reserved"], 0)

    def test_grant_mutation_is_rejected_against_external_hash(self):
        self.h.create()
        prepared = self.h.prepare({"op": "attach", "task_id": "task-a",
                                   "interface_id": "interface-a", "role": "test-role",
                                   "frame": FRAME})
        changed = deepcopy(prepared[3])
        changed["permissions"] = []
        write(prepared[0], changed)
        self.assert_rejected(lambda: self.h.invoke(prepared))

    def test_pending_consequence_blocks_task_handoff_and_new_plan(self):
        self.h.initialize()
        self.h.plan()
        transaction = self.h.state["pending"]["transaction_id"]
        self.assert_rejected(lambda: self.h.attach("task-b"))
        self.assert_rejected(self.h.plan)
        self.assertEqual(self.h.state["pending"]["transaction_id"], transaction)
        self.assertEqual(self.h.state["active_task"]["id"], "task-a")

    def test_renewal_requires_current_verify_permission(self):
        self.h.initialize()
        self.h.plan()
        request = self.h.renewal_request()
        self.assert_rejected(lambda: self.h.call(request,
            permissions=["READ_SOURCES", "RETAIN_ASSERTION"]))
        self.assertIsNotNone(self.h.state["pending"])

    def test_tampered_checkpoint_is_rejected(self):
        self.h.create()
        event_path = self.h.store / "events" / "000000.json"
        event = json.loads(event_path.read_bytes())
        event["state"]["native_actions_used"] = 19
        write(event_path, event)
        self.assert_rejected(self.h.attach)

    def test_resealed_forged_state_is_rejected_by_replay(self):
        self.h.create()
        event_path = self.h.store / "events" / "000000.json"
        event = json.loads(event_path.read_bytes())
        event["state"]["actions_reserved"] = 0
        event["state"]["action_limit"] = 20
        event["seal"] = digest({key: value for key, value in event.items() if key != "seal"})
        write(event_path, event)
        write(self.h.store / "CURRENT.json", {"sequence": 0, "head": event["seal"]})
        # Even adopting a replaced checkpoint's new hash must not substitute for
        # deterministic replay of its original pinned request and grant.
        with self.assertRaises(ReferenceError):
            self.h.attach(expected_head=event["seal"])

    def test_mutated_historical_source_invalidates_restore(self):
        self.h.initialize()
        source_path = self.h.host / self.h.sources["before"]["path"]
        write(source_path, {"payload": {"self": ["90", "0"],
                                       "destination": ["4", "0"]}})
        self.assert_rejected(self.h.plan)

    def test_effect_bytes_changed_after_grant_are_rejected(self):
        self.h.initialize()
        self.h.plan()
        prepared = self.h.prepare(self.h.renewal_request())
        effect_path = self.h.host / self.h.sources["effect"]["path"]
        changed = json.loads(effect_path.read_bytes())
        changed["action_id"] = "west"
        write(effect_path, changed)
        self.assert_rejected(lambda: self.h.invoke(prepared))
        self.assertIsNotNone(self.h.state["pending"])

    def test_hashed_but_wrong_transaction_effect_is_rejected(self):
        self.h.initialize()
        self.h.plan()
        self.assert_rejected(lambda: self.h.call(self.h.renewal_request(wrong_transaction=True)))

    def test_hashed_but_incorrect_world_movement_is_rejected(self):
        self.h.initialize()
        self.h.plan()
        self.assert_rejected(lambda: self.h.call(self.h.renewal_request(after="2")))
        self.assertEqual(self.h.state["claims"]["self"]["point"], ["0", "0"])

    def test_global_action_budget_is_not_reset_by_new_task(self):
        self.h.initialize(action_limit=1)
        self.h.plan()
        self.h.call(self.h.renewal_request())
        self.h.attach("task-b")
        self.assertEqual(self.h.state["actions_reserved"], 1)
        self.assert_rejected(self.h.plan)

    def test_same_task_reattachment_does_not_reset_task_allowance(self):
        self.h.initialize()
        self.h.plan()
        self.h.call(self.h.renewal_request())
        self.h.attach("task-a")
        self.assertEqual(self.h.state["task_actions"]["task-a"], 1)
        self.assert_rejected(self.h.plan)

    def test_global_native_budget_is_not_reset_by_new_task(self):
        self.h.initialize(native_limit=5)
        self.h.plan()
        self.h.call(self.h.renewal_request())
        self.h.attach("task-b")
        self.assertEqual(self.h.state["native_actions_used"], 5)
        self.assert_rejected(self.h.plan)

    def test_plan_reserves_native_capacity_for_mandatory_renewal(self):
        self.h.initialize(native_limit=4)
        # Two Native assertions are already consumed.  Two recalls would fit,
        # but the required post-effect retain would not; no move may be planned.
        self.assertEqual(self.h.state["native_actions_used"], 2)
        self.assert_rejected(self.h.plan)
        self.assertIsNone(self.h.state["pending"])
        self.assertEqual(self.h.state["actions_reserved"], 0)

    def test_isolated_plan_reserves_last_transition_for_renewal(self):
        """Counter-boundary unit check; this copied state is not a journal receipt."""
        self.h.initialize()
        previous = deepcopy(self.h.state)
        previous["generation"] = 62
        grant_file, grant_sha, request, grant = self.h.prepare(self.h.plan_request())
        witness = FileWitness(grant_file, grant, self.h.store)
        with patch.object(canonical.core, "_local_action",
                          side_effect=AssertionError("Executor must not run at an exhausted boundary")) as executor:
            with self.assertRaises(ReferenceError):
                reduce(previous, request, grant, grant_sha, witness)
            executor.assert_not_called()
        self.assertIsNone(previous["pending"])
        self.assertEqual(previous["actions_reserved"], 0)

    def test_isolated_plan_reserves_claim_history_slot_for_renewal(self):
        """Exercise the bounded container directly without generating 62 fake events."""
        self.h.initialize()
        previous = deepcopy(self.h.state)
        sample = deepcopy(previous["claim_history"][0])
        previous["claim_history"].extend(deepcopy(sample)
                                         for _ in range(64 - len(previous["claim_history"])))
        grant_file, grant_sha, request, grant = self.h.prepare(self.h.plan_request())
        witness = FileWitness(grant_file, grant, self.h.store)
        with patch.object(canonical.core, "_local_action",
                          side_effect=AssertionError("Executor must not run without renewal capacity")) as executor:
            with self.assertRaises(ReferenceError):
                reduce(previous, request, grant, grant_sha, witness)
            executor.assert_not_called()
        self.assertIsNone(previous["pending"])
        self.assertEqual(previous["native_actions_used"], 2)

    def test_journal_inspection_never_reexecutes_recorded_native_actions(self):
        self.h.initialize()
        self.h.plan()
        self.h.call(self.h.renewal_request())
        expected_state = deepcopy(self.h.state)
        current_bytes = (self.h.store / "CURRENT.json").read_bytes()
        with patch.object(canonical.core, "_local_action",
                          side_effect=AssertionError("Inspection must replay recorded consequences only")) as executor:
            inspected = inspect_reference(self.h.store, expected_head=self.h.head)
            executor.assert_not_called()
        self.assertEqual(inspected["event_head"], self.h.head)
        self.assertEqual(inspected["state"], expected_state)
        self.assertEqual(inspected["state"]["native_actions_used"], 5)
        self.assertEqual((self.h.store / "CURRENT.json").read_bytes(), current_bytes)

    def test_x_lineage_and_same_x_theta_expansion(self):
        created = self.h.create()["state"]
        attached = self.h.attach()["state"]
        self.assertEqual(attached["x"]["previous_x_hash"], created["x"]["x_hash"])
        self.assertEqual(attached["frame_link"]["previous_theta_hash"],
                         created["theta"]["theta_hash"])
        before = deepcopy(attached)
        expanded = self.h.call({"op": "expand", "dimensions": ["role-specific-reference"]})["state"]
        self.assertEqual(expanded["x"], before["x"])
        self.assertNotEqual(expanded["theta"]["theta_hash"], before["theta"]["theta_hash"])
        self.assertEqual(expanded["frame_link"]["operation"], "SAME_X_EXPANSION")
        self.assertEqual(expanded["frame_link"]["previous_theta_hash"],
                         before["theta"]["theta_hash"])
        self.assertEqual(expanded["entity_id"], before["entity_id"])
        self.assertEqual(expanded["native_actions_used"], before["native_actions_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
