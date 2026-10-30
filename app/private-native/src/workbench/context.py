"""Model-context policy only; the full local kernel audit is never rewritten."""
from __future__ import annotations
from copy import deepcopy

from .native_core import model_context, parse_observation

POLICIES = ("audit_v3", "compact_v1", "math_end_to_end_v1", "math_mechanism_controlled_v1", "math_compact_end_to_end_v1")
DEFAULT_POLICY = "audit_v3"


def policy_for(settings):
    # Missing means the actual pre-3.1.1 behavior, not the new compact behavior.
    value = settings.get("context_policy", DEFAULT_POLICY)
    if value not in POLICIES:
        raise ValueError("Unknown context policy; no fallback or task migration.")
    return value


def compact_context(summary, problem):
    """Select current relation state and one actual latest transition.

    All literal user messages and lane answers are retained by the host's
    history builder. This function removes repeated audit/state narratives,
    not conversation text, local receipts, evidence or persisted state.
    """
    observation = parse_observation(problem)["observation"]
    state = summary["state_after"]
    key = (observation["subject"].casefold(), observation["predicate"].casefold())
    relations = [r for r in state["relations"]
                 if (r["subject"].casefold(), r["predicate"].casefold()) == key]
    # Retain complete relation values, source labels and epistemic class.
    # A refused proposal is represented by its boundary/outcome, not assimilated.
    outcome_keys = ("observation_id", "boundary", "verification", "conflict",
                    "local_action_executed", "observed_consequence", "assimilation",
                    "relation_assimilated", "checkpoint_roundtrip", "persistence")
    compact = {
        "schema": "se6-compact-structured-context-v1",
        "context_policy": "compact_v1",
        "entrypoint": summary["entrypoint"],
        "kernel_sha256": summary["kernel_sha256"],
        "scope": summary["scope"],
        "round_id": summary["round_id"],
        "state": {"identity": state["identity"], "version": state["version"],
                  "relations": relations},
        "relation_scope": {"subject": observation["subject"], "predicate": observation["predicate"],
                           "selection": "Current observation key only; a partial projection, not absence of other retained state."},
        "latest_transition": {k: summary[k] for k in outcome_keys},
        "provenance": {k: summary[k] for k in
                       ("state_before_hash", "state_after_hash", "receipt_hash",
                        "previous_receipt_hash", "verification_scope")},
        "world_truth_verified": summary["world_truth_verified"],
        "reference_contents_fetched": summary["reference_contents_fetched"],
    }
    return model_context(deepcopy(compact))
