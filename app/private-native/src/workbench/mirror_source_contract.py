"""Read-only source-contract subset extracted by the offline fixture builder.
No store, projection producer or authority service is vendored here.
Original entity_mirror.py SHA256: fc1c022f72482f469fa7be7ca3976f7a7bcc51712ed0887c85847962b95a5907
"""
from __future__ import annotations
import json
from enum import Enum
from pydantic import BaseModel, ConfigDict, StrictStr, model_validator

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

def _value_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)

class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

class SelfModelFact(_Frozen):
    key: StrictStr
    value_json: StrictStr
    status: EpistemicStatus
    evidence_references: tuple[StrictStr, ...] = ()
    scope: StrictStr

    @model_validator(mode="after")
    def qualified_fact(self):
        if _value_json(json.loads(self.value_json)) != self.value_json:
            raise ValueError("mirror values must use canonical JSON")
        if self.status is EpistemicStatus.VERIFIED and not self.evidence_references:
            raise ValueError("verified mirror material requires canonical evidence")
        if self.status is EpistemicStatus.UNKNOWN and self.value_json != "null":
            raise ValueError("unknown self-model information cannot invent a value")
        return self
