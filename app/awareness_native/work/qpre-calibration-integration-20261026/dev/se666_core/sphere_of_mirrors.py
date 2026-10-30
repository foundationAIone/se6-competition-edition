"""Sphere of Mirrors reflection.

Reflects a task through eight mirror facets.
"""

from __future__ import annotations

from pydantic import BaseModel

MIRROR_KEYS = (
    "truth",
    "user_intent",
    "safety",
    "law_consent",
    "privacy",
    "project",
    "future",
    "repair",
)


class MirrorReflection(BaseModel):
    truth: str
    user_intent: str
    safety: str
    law_consent: str
    privacy: str
    project: str
    future: str
    repair: str

    def as_dict(self) -> dict[str, str]:
        return self.model_dump()


def reflect_task(task: str) -> MirrorReflection:
    """Produce structured reflections across the eight mirrors."""
    t = task.strip() or "(empty task)"
    short = (t[:120] + "…") if len(t) > 120 else t

    return MirrorReflection(
        truth=f"What is literally being asked: {short}",
        user_intent=f"Probable underlying goal behind: {short}",
        safety=(
            "Identify any path within this task that could cause harm to "
            "self, others, systems, or data."
        ),
        law_consent=(
            "Confirm the task is lawful and that all affected parties "
            "have consented or that consent is not required."
        ),
        privacy=(
            "Confirm no private, secret, or personal data is exposed, "
            "leaked, or processed without basis."
        ),
        project=(
            "Locate this task within the active project: which components, "
            "files, or workflows it touches."
        ),
        future=(
            "Project the consequences forward: short-term outcome, "
            "medium-term effect, long-term coherence."
        ),
        repair=(
            "Define the rollback / repair path if the action turns out "
            "to be wrong, partial, or misunderstood."
        ),
    )
