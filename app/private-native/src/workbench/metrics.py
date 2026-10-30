"""Read-only execution measurements; missing provider usage remains unknown."""
from __future__ import annotations
import math

SCHEMA = "se6-comparison-execution-metrics-v1"


def _sum_known(values):
    return sum(values) if all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values) else None


def _tokens(agent, names):
    usage = agent.get("usage")
    if not isinstance(usage, dict):
        return None
    for name in names:
        value = usage.get(name)
        if type(value) is int and value >= 0:
            return value
    return None


def lane_metrics(rounds, lane):
    agents = [a for r in rounds for a in r["lanes"][lane]["agents"]]
    attempts = [int(a["provider_request_attempted"]) if type(a.get("provider_request_attempted")) is bool
                else None for a in agents]
    sizes = [a.get("input_bytes_reserved") for a in agents]
    latency = [a.get("elapsed_seconds") for a in agents]
    def reasoning_tokens(agent):
        usage = agent.get("usage")
        details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
        value = details.get("reasoning_tokens") if isinstance(details, dict) else None
        completion = _tokens(agent, ("output_tokens", "completion_tokens"))
        return value if type(value) is int and value >= 0 and (completion is None or value <= completion) else None
    return {
        "prompt_tokens": _sum_known([_tokens(a, ("input_tokens", "prompt_tokens")) for a in agents]),
        "completion_tokens": _sum_known([_tokens(a, ("output_tokens", "completion_tokens")) for a in agents]),
        "reasoning_tokens": _sum_known([reasoning_tokens(a) for a in agents]),
        "total_tokens": _sum_known([_tokens(a, ("total_tokens",)) for a in agents]),
        "serialized_input_bytes": _sum_known(sizes),
        "model_calls": _sum_known(attempts),
        "latency_seconds": _sum_known(latency),
        "model_request_elapsed_seconds": _sum_known([a.get("model_request_elapsed_seconds") for a in agents]),
        "local_se_transition_count": sum(bool(r.get("core_receipt")) for r in rounds) if lane == "se6" else 0,
        "local_se_latency_seconds": _sum_known([r.get("local_se_elapsed_seconds") for r in rounds
                                               if r.get("core_receipt")]) if lane == "se6" else 0,
        "local_mirror_projection_count":sum(bool(r.get("mirror_projection")) for r in rounds) if lane=="se6" else 0,
        "local_mirror_generation_seconds":_sum_known([r.get("mirror_generation_seconds") for r in rounds
                                                     if r.get("mirror_projection")]) if lane=="se6" else 0,
        "auto_local_operations": sum(r.get("auto_execution", {}).get("local_operations", 0) for r in rounds) if lane == "se6" else 0,
        "auto_local_seconds": _sum_known([r["auto_execution"]["local_seconds"] for r in rounds if r.get("auto_execution")]) if lane == "se6" else 0,
        "auto_context_bytes": sum(r.get("auto_execution", {}).get("context_bytes", 0) for r in rounds) if lane == "se6" else 0,
        "local_math_operations": sum(r.get("math_projection", {}).get("local_operations", 0) for r in rounds) if lane == "se6" else 0,
        "local_math_processing_seconds": _sum_known([_sum_known([r.get("math_generation_seconds"),
            r.get("math_context_preparation_seconds", {}).get("se6")]) for r in rounds if r.get("math_projection")]) if lane == "se6" else 0,
        "stateless_shared_checking_seconds": _sum_known([_sum_known([r.get("math_control_seconds"),
            r.get("math_context_preparation_seconds", {}).get("baseline")]) for r in rounds if r.get("math_control_context")]) if lane == "baseline" else 0,
        "math_context_preparation_seconds": _sum_known([r.get("math_context_preparation_seconds", {}).get(lane)
            for r in rounds if r.get("math_projection")]),
    }


def execution_metrics(task):
    return {"schema_version": SCHEMA,
            "lanes": {lane: lane_metrics(task["rounds"], lane) for lane in ("se6", "baseline")},
            "scope": {"tokens": "Provider-returned usage only; null means unavailable.",
                      "model_calls": "Host request attempts, not proof of remote completion or billing; historical unrecorded attempts are null.",
                      "serialized_input_bytes": "Measured prepared payload bytes; not tokens or proof of send.",
                      "latency": "Worker elapsed time including scheduling; not provider-only latency.",
                      "local_se_transitions": "Committed local receipts; model responses are unverified.",
                      "local_mirror_latency":"Pinned fixture validation/context projection time; not live loops or a rebuild of the original test stores."},
            "fixture_evaluation_preparation":[{"case":r["mirror_projection"]["fixture_case"],
                "step":r["mirror_projection"]["fixture_step"],"evaluation":r["mirror_projection"]["evaluation"]}
                for r in task["rounds"] if r.get("mirror_projection")],
            "auto_scores": [r.get("auto_evaluation") for r in task["rounds"]] if task["settings"]["integration"] == "auto" else None,
            "quality_scores": ([r.get("math_evaluation") for r in task["rounds"]]
                if task["settings"].get("core_revision") == "canonical-realization-v1" and task["settings"]["integration"] == "native_mathematics" else None), "winner": None}
