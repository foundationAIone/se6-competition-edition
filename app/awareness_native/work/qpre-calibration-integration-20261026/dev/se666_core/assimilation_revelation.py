"""Assimilation / Revelation calculation (V2 Step 5).

Principle:
    R(x) + U(x) + M(x, T_t) + ΔT(x) = A_revelation(x, t)

Where:
    R(x)       — recognition: shared structure between before/after, with
                 type/value similarity on shared keys (not just key overlap).
    U(x)       — understanding: presence + meaningfulness of the expected
                 post-pipeline fields (``decision``, ``primary_element``,
                 ``next_action``).
    M(x, T_t)  — memory link: continuity with the prior audit summary
                 when one is supplied, else degraded internal overlap.
    ΔT(x)      — temporal delta: how much *value* shifted between states,
                 weighted by structural growth.
    A_rev      — total revelation / assimilation score (0..1).

Pure, deterministic, no I/O, no network.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Result model (V2 — backward compatible)
# ---------------------------------------------------------------------------


class AssimilationResult(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    # V1 surface (preserved):
    components: dict[str, float] = Field(default_factory=dict)
    explanation: str = ""
    # V2 top-level component fields (new):
    recognition: float = 0.0
    understanding: float = 0.0
    memory_link: float = 0.0
    delta: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_EXPECTED_POST_FIELDS = ("decision", "primary_element", "next_action")
_KNOWN_DECISIONS = {
    "allow", "pause", "refuse", "needs_human_approval",
}
_TRIVIAL_NEXT_ACTIONS = {"", "noop", "none"}


def _safe_dict(state: Any) -> dict[str, Any]:
    if state is None:
        return {}
    if isinstance(state, dict):
        return state
    if hasattr(state, "model_dump"):
        try:
            return state.model_dump()
        except (AttributeError, TypeError, ValueError):
            return {"value": state}
    return {"value": state}


def _is_meaningful_value(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) > 0
    return True


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> set:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _clamp(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _value_similarity(a: Any, b: Any) -> float:
    """Crude 0..1 similarity for two arbitrary values."""
    if a == b:
        return 1.0
    if type(a) is not type(b):
        return 0.0
    if isinstance(a, str):
        ta, tb = _tokens(a), _tokens(b)
        if not ta and not tb:
            return 1.0
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)
    if isinstance(a, bool) or isinstance(b, bool):
        return 1.0 if a == b else 0.0
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        denom = max(abs(a), abs(b), 1.0)
        return max(0.0, 1.0 - abs(a - b) / denom)
    if isinstance(a, (list, tuple)):
        sa, sb = set(map(repr, a)), set(map(repr, b))
        if not sa and not sb:
            return 1.0
        if not (sa | sb):
            return 0.0
        return len(sa & sb) / len(sa | sb)
    if isinstance(a, dict):
        ka, kb = set(a.keys()), set(b.keys())
        if not (ka | kb):
            return 1.0
        shared = ka & kb
        if not shared:
            return 0.0
        per_key = [_value_similarity(a[k], b[k]) for k in shared]
        return (len(shared) / len(ka | kb)) * (sum(per_key) / len(per_key))
    return 0.0


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------


def _recognition(before: dict[str, Any], after: dict[str, Any]) -> float:
    """Shared keys + per-key value similarity, normalized to 0..1."""
    bkeys = set(before.keys())
    akeys = set(after.keys())
    if not akeys:
        return 0.0
    shared = bkeys & akeys
    if not shared:
        return 0.0
    sims = [_value_similarity(before[k], after[k]) for k in shared]
    avg_sim = sum(sims) / len(sims)
    coverage = len(shared) / len(akeys)
    return _clamp(coverage * (0.5 + 0.5 * avg_sim))


def _understanding(after: dict[str, Any]) -> float:
    """Fraction of expected post-pipeline fields present and meaningful."""
    if not after:
        return 0.0
    score = 0.0
    for field in _EXPECTED_POST_FIELDS:
        v = after.get(field)
        if not _is_meaningful_value(v):
            continue
        if field == "next_action":
            sval = str(v).strip().lower()
            if sval in _TRIVIAL_NEXT_ACTIONS:
                score += 0.4
            else:
                score += 1.0
        elif field == "decision":
            sval = str(v).strip().lower()
            if sval in _KNOWN_DECISIONS:
                score += 1.0
            else:
                score += 0.5
        else:
            score += 1.0
    return _clamp(score / len(_EXPECTED_POST_FIELDS))


def _memory_link(
    before: dict[str, Any],
    after: dict[str, Any],
    prior_audit_summary: dict[str, Any] | None,
    task_text: str | None,
) -> float:
    """Continuity with prior audit when available, else degraded overlap."""
    if isinstance(prior_audit_summary, dict) and prior_audit_summary:
        score = 0.0
        weight = 0.0

        prior_decision = str(prior_audit_summary.get("decision", "") or "")
        cur_decision = str(after.get("decision", "") or "")
        if prior_decision or cur_decision:
            weight += 1.0
            if prior_decision and cur_decision:
                score += 1.0 if prior_decision == cur_decision else 0.3

        prior_elem = str(prior_audit_summary.get("primary_element", "") or "")
        cur_elem = str(after.get("primary_element", "") or "")
        if prior_elem or cur_elem:
            weight += 1.0
            if prior_elem and cur_elem:
                score += 1.0 if prior_elem == cur_elem else 0.2

        prior_task = (
            str(prior_audit_summary.get("task_preview", "") or "")
            or str(prior_audit_summary.get("task", "") or "")
        )
        cur_task = (
            str(task_text or "")
            or str(after.get("task", "") or "")
            or str(before.get("task", "") or "")
        )
        if prior_task or cur_task:
            weight += 1.0
            score += _value_similarity(prior_task, cur_task)

        prior_score = prior_audit_summary.get("assimilation_score")
        try:
            ps = float(prior_score) if prior_score is not None else None
        except (TypeError, ValueError):
            ps = None
        if ps is not None:
            weight += 0.5
            score += 0.5 * ps

        if weight == 0:
            return 0.5
        return _clamp(score / weight)

    # No prior summary: degraded internal overlap, capped at 0.5 so the
    # presence of real prior context can meaningfully *raise* this score.
    bkeys = set(before.keys())
    akeys = set(after.keys())
    union = bkeys | akeys
    if not union:
        return 0.0
    overlap = len(bkeys & akeys) / len(union)
    return _clamp(0.5 * overlap)


def _delta(before: dict[str, Any], after: dict[str, Any]) -> float:
    """Meaningful before/after changes — value-aware, not just key churn."""
    bkeys = set(before.keys())
    akeys = set(after.keys())
    union = bkeys | akeys
    if not union:
        return 0.0

    new_meaningful = sum(
        1 for k in (akeys - bkeys) if _is_meaningful_value(after.get(k))
    )
    shared_changed = 0.0
    for k in bkeys & akeys:
        sim = _value_similarity(before.get(k), after.get(k))
        if sim < 0.999:
            shared_changed += 1.0 - sim
    removed = len(bkeys - akeys)

    raw = (new_meaningful + shared_changed + 0.5 * removed) / len(union)
    if raw <= 0.0:
        return 0.0
    if raw >= 1.0:
        return 1.0
    # Triangular shape with a plateau favouring moderate-to-strong change.
    if raw < 0.4:
        return _clamp(raw / 0.4 * 0.85)
    if raw <= 0.8:
        return _clamp(0.85 + 0.15 * ((raw - 0.4) / 0.4))
    return _clamp(1.0 - (raw - 0.8) / 0.2 * 0.2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_assimilation(
    before_state: Any,
    after_state: Any,
    *,
    prior_audit_summary: dict[str, Any] | None = None,
    task_text: str | None = None,
) -> AssimilationResult:
    """Estimate assimilation between two states (V2).

    Backward compatible: callers passing only ``before_state`` and
    ``after_state`` still work. The two new keyword-only parameters
    refine the *memory_link* signal:

    * ``prior_audit_summary`` — a dict shaped like
      :class:`~se666_core.project_memory.LastRun` /
      :class:`~se666_core.project_memory.TaskSummary` (``decision``,
      ``primary_element``, ``assimilation_score``, ``task_preview``).
    * ``task_text`` — the raw current task string, used to compare
      against the prior task preview.

    Pure, deterministic, no I/O.
    """
    before = _safe_dict(before_state)
    after = _safe_dict(after_state)

    recognition = _recognition(before, after)
    understanding = _understanding(after)
    memory_link = _memory_link(before, after, prior_audit_summary, task_text)
    delta = _delta(before, after)

    score = _clamp(
        0.25 * recognition
        + 0.30 * understanding
        + 0.20 * memory_link
        + 0.25 * delta
    )

    parts = [
        f"recognition={recognition:.2f}",
        f"understanding={understanding:.2f}",
        (
            f"memory_link={memory_link:.2f} (prior-audit-aware)"
            if prior_audit_summary
            else f"memory_link={memory_link:.2f} (no prior context)"
        ),
        f"delta={delta:.2f}",
    ]
    explanation = (
        "Assimilation blends recognition, understanding, memory link, "
        "and delta. " + ", ".join(parts) + "."
    )

    return AssimilationResult(
        score=round(score, 4),
        components={
            "recognition": round(recognition, 4),
            "understanding": round(understanding, 4),
            "memory_link": round(memory_link, 4),
            "delta": round(delta, 4),
        },
        recognition=round(recognition, 4),
        understanding=round(understanding, 4),
        memory_link=round(memory_link, 4),
        delta=round(delta, 4),
        explanation=explanation,
    )


__all__ = ["AssimilationResult", "calculate_assimilation"]
