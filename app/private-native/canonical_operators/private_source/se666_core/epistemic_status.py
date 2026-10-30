"""Explicit epistemic provenance for canonical SE6 contracts.

These types describe where a value came from.  They do not establish that the
value is true and do not perform verification or any external action.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EpistemicStatus(str, Enum):
    """Provenance and lifecycle class; never an authority grant."""

    USER_SUPPLIED = "user_supplied"
    MODEL_PROPOSED = "model_proposed"
    DETERMINISTIC = "deterministic"
    MEASURED = "measured"
    OBSERVED = "observed"
    REPORTED = "reported"
    VERIFIED = "verified"
    SYMBOLIC = "symbolic"
    UNKNOWN = "unknown"
    INFERRED = "inferred"
    ASSUMED = "assumed"
    MODELLED = "modelled"
    PREDICTED = "predicted"
    DERIVED = "derived"
    MAPPED = "mapped"
    CONTRADICTED = "contradicted"
    STALE = "stale"
    EXPIRED = "expired"
    REVOKED = "revoked"


class EpistemicValue[T](BaseModel):
    """A value paired with explicit provenance and uncertainty."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: EpistemicStatus
    value: T | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_references: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()

    @model_validator(mode="after")
    def enforce_unknown_semantics(self) -> EpistemicValue[T]:
        if self.status is EpistemicStatus.UNKNOWN:
            if self.value is not None:
                raise ValueError("UNKNOWN epistemic values must not contain a value")
            if self.confidence != 0.0:
                raise ValueError("UNKNOWN epistemic values must have zero confidence")
        if self.status is EpistemicStatus.VERIFIED and not self.evidence_references:
            raise ValueError("VERIFIED epistemic values require evidence references")
        return self


class UncertaintyRecord(BaseModel):
    """Contract-level uncertainty; it is descriptive, not an authority grant."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: EpistemicStatus
    confidence: float = Field(ge=0.0, le=1.0)
    known: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    inferences: tuple[str, ...] = ()
    symbolic: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()


__all__ = ["EpistemicStatus", "EpistemicValue", "UncertaintyRecord"]
