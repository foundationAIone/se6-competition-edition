"""Pure lifecycle and launch-mode contracts for bounded embodiment."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator


class LaunchMode(str, Enum):
    OFFLINE_DRY_RUN = "OFFLINE_DRY_RUN"
    LOCAL_SUPERVISED = "LOCAL_SUPERVISED"
    ONLINE_OBSERVE_ONLY = "ONLINE_OBSERVE_ONLY"
    ONLINE_BOUNDED_ACTION = "ONLINE_BOUNDED_ACTION"
    STOPPED = "STOPPED"


class LifecycleState(str, Enum):
    DORMANT = "DORMANT"
    GERMINATING = "GERMINATING"
    ROOTING = "ROOTING"
    OBSERVING = "OBSERVING"
    DELIBERATING = "DELIBERATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    ASSIMILATING = "ASSIMILATING"
    GROWING = "GROWING"
    PAUSED = "PAUSED"
    REPAIRING = "REPAIRING"
    ROLLING_BACK = "ROLLING_BACK"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED_SAFE = "FAILED_SAFE"


_LEGAL: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.DORMANT: frozenset({LifecycleState.GERMINATING, LifecycleState.STOPPED}),
    LifecycleState.GERMINATING: frozenset({LifecycleState.ROOTING, LifecycleState.REPAIRING}),
    LifecycleState.ROOTING: frozenset({LifecycleState.OBSERVING, LifecycleState.REPAIRING}),
    LifecycleState.OBSERVING: frozenset({LifecycleState.DELIBERATING, LifecycleState.STOPPING}),
    LifecycleState.DELIBERATING: frozenset({
        LifecycleState.AWAITING_APPROVAL, LifecycleState.ACTING,
        LifecycleState.REPAIRING, LifecycleState.STOPPED,
    }),
    LifecycleState.AWAITING_APPROVAL: frozenset({
        LifecycleState.ACTING, LifecycleState.PAUSED, LifecycleState.STOPPING,
    }),
    LifecycleState.ACTING: frozenset({LifecycleState.VERIFYING}),
    LifecycleState.VERIFYING: frozenset({
        LifecycleState.ASSIMILATING, LifecycleState.REPAIRING,
        LifecycleState.ROLLING_BACK,
    }),
    LifecycleState.ASSIMILATING: frozenset({LifecycleState.OBSERVING, LifecycleState.GROWING}),
    LifecycleState.GROWING: frozenset({
        LifecycleState.VERIFYING, LifecycleState.OBSERVING,
        LifecycleState.ROLLING_BACK,
    }),
    LifecycleState.PAUSED: frozenset({
        LifecycleState.OBSERVING, LifecycleState.DELIBERATING,
        LifecycleState.REPAIRING, LifecycleState.STOPPING, LifecycleState.STOPPED,
    }),
    LifecycleState.REPAIRING: frozenset({
        LifecycleState.OBSERVING, LifecycleState.ROLLING_BACK,
        LifecycleState.PAUSED,
    }),
    LifecycleState.ROLLING_BACK: frozenset({
        LifecycleState.OBSERVING, LifecycleState.PAUSED, LifecycleState.FAILED_SAFE,
    }),
    LifecycleState.STOPPING: frozenset({LifecycleState.STOPPED, LifecycleState.FAILED_SAFE}),
    LifecycleState.STOPPED: frozenset(),
    LifecycleState.FAILED_SAFE: frozenset({LifecycleState.STOPPING, LifecycleState.STOPPED}),
}

_UNIVERSAL_FAIL_CLOSED = frozenset({
    LifecycleState.PAUSED, LifecycleState.FAILED_SAFE, LifecycleState.STOPPING,
})


class LifecycleTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    from_state: LifecycleState
    to_state: LifecycleState
    reason: StrictStr
    proposed_at_utc: datetime
    capability_grants: tuple[StrictStr, ...] = ()
    applied: bool = False

    @field_validator("proposed_at_utc")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transition timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def transition_is_legal_and_non_authorizing(self) -> LifecycleTransition:
        if not is_legal_transition(self.from_state, self.to_state):
            raise ValueError(f"illegal lifecycle transition: {self.from_state.value}->{self.to_state.value}")
        if self.capability_grants:
            raise ValueError("lifecycle state cannot grant capability")
        if self.applied:
            raise ValueError("Phase 2C lifecycle transitions are proposals only")
        return self


def is_legal_transition(from_state: LifecycleState, to_state: LifecycleState) -> bool:
    if from_state is to_state:
        return False
    return to_state in _LEGAL[from_state] or to_state in _UNIVERSAL_FAIL_CLOSED


def propose_transition(
    from_state: LifecycleState,
    to_state: LifecycleState,
    *,
    reason: str,
    proposed_at: datetime,
) -> LifecycleTransition:
    return LifecycleTransition(
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        proposed_at_utc=proposed_at,
    )


def propose_emergency_stop(
    current_state: LifecycleState,
    *,
    proposed_at: datetime,
) -> tuple[LifecycleTransition, LifecycleTransition]:
    return (
        propose_transition(
            current_state, LifecycleState.STOPPING,
            reason="Emergency stop requested; prevent new capability invocation.",
            proposed_at=proposed_at,
        ),
        propose_transition(
            LifecycleState.STOPPING, LifecycleState.STOPPED,
            reason="Complete bounded emergency stop.",
            proposed_at=proposed_at,
        ),
    )


__all__ = [
    "LaunchMode", "LifecycleState", "LifecycleTransition", "is_legal_transition",
    "propose_emergency_stop", "propose_transition",
]
