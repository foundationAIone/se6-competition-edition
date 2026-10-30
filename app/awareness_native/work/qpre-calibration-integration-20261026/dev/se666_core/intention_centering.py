"""Deterministic intention centering for the SE6Triad kernel."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CenteredIntention(BaseModel):
    real_objective: str
    stated_intention: str
    identity_context: str = "not asserted"
    desires: list[str] = Field(default_factory=list)
    fears_or_constraints: list[str] = Field(default_factory=list)
    memory_context_available: bool = False
    true_question: str


def center_intention(
    task: str,
    *,
    current_state: dict[str, Any] | None = None,
) -> CenteredIntention:
    """Center an input without inventing hidden motives or identity.

    This stage preserves the stated objective and identifies only explicit
    constraint cues. Deeper motives remain questions for the user, not facts.
    """
    if not isinstance(task, str):
        raise TypeError("task must be str")
    if current_state is not None and not isinstance(current_state, dict):
        raise TypeError("current_state must be a dict or None")

    text = " ".join(task.strip().split())
    objective = text or "Clarify the intended state change."
    lower = text.lower()
    constraints = [
        cue for cue in (
            "do not", "don't", "never", "without", "only", "must", "should",
            "approval", "permission", "private", "safe", "lawful",
        )
        if cue in lower
    ]

    return CenteredIntention(
        real_objective=objective,
        stated_intention=text,
        desires=[objective] if text else [],
        fears_or_constraints=constraints,
        memory_context_available=bool(current_state),
        true_question=f"What authorized state change would satisfy: {objective}",
    )


__all__ = ["CenteredIntention", "center_intention"]
