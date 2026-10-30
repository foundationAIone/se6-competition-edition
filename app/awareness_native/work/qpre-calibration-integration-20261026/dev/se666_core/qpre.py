"""Deterministic SHADOW contracts for possibility rendering.

QPRE values are proposals only.  This module deliberately has no adapters,
storage, clocks, randomness, network access, model calls, or authority hooks.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from se666_core.canonical_contracts import canonical_sha256

QPRE_SCHEMA_VERSION = "se6-qpre-shadow-v-next-1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def _content_id(prefix: str, material: object) -> str:
    return f"{prefix}_{canonical_sha256(material)}"


def _nonblank(value: str) -> str:
    if value != value.strip() or not value:
        raise ValueError("value must be non-empty and surrounding-whitespace-free")
    return value


def _unique(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


class QPREEpistemicClass(str, Enum):
    POSSIBILITY = "POSSIBILITY"
    PREDICTION = "PREDICTION"


class ConfidenceBasis(str, Enum):
    DETERMINISTIC_ENUMERATION = "DETERMINISTIC_ENUMERATION"
    EMPIRICAL_CALIBRATION = "EMPIRICAL_CALIBRATION"
    DECLARED_MODEL_ESTIMATE = "DECLARED_MODEL_ESTIMATE"


class Reversibility(str, Enum):
    REVERSIBLE = "REVERSIBLE"
    PARTIALLY_REVERSIBLE = "PARTIALLY_REVERSIBLE"
    IRREVERSIBLE = "IRREVERSIBLE"
    UNKNOWN = "UNKNOWN"


class StructuredUncertainty(BaseModel):
    """Uncertainty without an implied numeric confidence.

    Numeric confidence is optional and accepted only with both a named basis
    and a traceable basis reference.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    known: tuple[StrictStr, ...] = ()
    unknown: tuple[StrictStr, ...] = ()
    assumptions: tuple[StrictStr, ...] = ()
    sensitivity_factors: tuple[StrictStr, ...] = ()
    confidence: StrictFloat | None = Field(default=None, ge=0.0, le=1.0)
    confidence_basis: ConfidenceBasis | None = None
    confidence_basis_reference: StrictStr | None = Field(
        default=None, min_length=1, max_length=256
    )

    @field_validator("known", "unknown", "assumptions", "sensitivity_factors")
    @classmethod
    def validate_statements(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _nonblank(value)
            if len(value) > 512:
                raise ValueError("uncertainty statement exceeds 512 characters")
        return _unique(values, "uncertainty statements")

    @field_validator("confidence_basis_reference")
    @classmethod
    def validate_basis_reference(cls, value: str | None) -> str | None:
        if value is not None and not _REF_RE.fullmatch(value):
            raise ValueError("confidence_basis_reference must be a safe reference")
        return value

    @model_validator(mode="after")
    def require_complete_confidence_basis(self) -> StructuredUncertainty:
        supplied = (
            self.confidence is not None,
            self.confidence_basis is not None,
            self.confidence_basis_reference is not None,
        )
        if any(supplied) and not all(supplied):
            raise ValueError(
                "confidence requires confidence_basis and confidence_basis_reference"
            )
        return self


class CandidateStateField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: StrictStr = Field(min_length=1, max_length=128)
    possible_value: StrictStr = Field(min_length=1, max_length=1024)
    epistemic_class: Literal[QPREEpistemicClass.POSSIBILITY] = (
        QPREEpistemicClass.POSSIBILITY
    )

    @field_validator("name", "possible_value")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _nonblank(value)


class TransformationStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    operation: StrictStr = Field(min_length=1, max_length=256)
    input_reference: StrictStr = Field(min_length=1, max_length=256)
    possible_output: StrictStr = Field(min_length=1, max_length=1024)
    epistemic_class: Literal[QPREEpistemicClass.POSSIBILITY] = (
        QPREEpistemicClass.POSSIBILITY
    )

    @field_validator("operation", "possible_output")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _nonblank(value)

    @field_validator("input_reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not _REF_RE.fullmatch(value):
            raise ValueError("input_reference must be a safe reference")
        return value


class PredictedConsequence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    prediction_id: StrictStr
    summary: StrictStr = Field(min_length=1, max_length=1024)
    provenance_references: tuple[StrictStr, ...] = Field(min_length=1)
    epistemic_class: Literal[QPREEpistemicClass.PREDICTION] = (
        QPREEpistemicClass.PREDICTION
    )
    actual: Literal[False] = False
    verified: Literal[False] = False
    authority: Literal[False] = False
    memory_eligible: Literal[False] = False

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return _nonblank(value)

    @field_validator("provenance_references")
    @classmethod
    def validate_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not _REF_RE.fullmatch(value):
                raise ValueError("provenance references must be safe references")
        return _unique(values, "provenance_references")

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"prediction_id"})

    @model_validator(mode="after")
    def validate_content_id(self) -> PredictedConsequence:
        if self.prediction_id != _content_id("qpre_prediction", self.material_fields()):
            raise ValueError("prediction_id must match canonical content")
        return self


def build_predicted_consequence(
    *, summary: str, provenance_references: Sequence[str]
) -> PredictedConsequence:
    material = {
        "summary": summary,
        "provenance_references": tuple(provenance_references),
        "epistemic_class": QPREEpistemicClass.PREDICTION,
        "actual": False,
        "verified": False,
        "authority": False,
        "memory_eligible": False,
    }
    draft = PredictedConsequence.model_construct(
        prediction_id="qpre_prediction_draft", **material
    )
    normalized = draft.material_fields()
    return PredictedConsequence.model_validate(
        {
            "prediction_id": _content_id("qpre_prediction", normalized),
            **normalized,
        }
    )


class CandidateRealization(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    realization_id: StrictStr
    source_state_hash: StrictStr
    frame_hash: StrictStr
    candidate_state: tuple[CandidateStateField, ...] = Field(min_length=1)
    transformations: tuple[TransformationStep, ...] = Field(min_length=1)
    predicted_consequences: tuple[PredictedConsequence, ...] = Field(min_length=1)
    reversibility: Reversibility
    cost_units: StrictInt = Field(ge=0)
    risk_score: StrictInt = Field(ge=0, le=100)
    provenance_references: tuple[StrictStr, ...] = Field(min_length=1)
    epistemic_class: Literal[QPREEpistemicClass.POSSIBILITY] = (
        QPREEpistemicClass.POSSIBILITY
    )
    actual: Literal[False] = False
    verified: Literal[False] = False
    authority: Literal[False] = False
    memory_eligible: Literal[False] = False

    @field_validator("source_state_hash", "frame_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("candidate_state")
    @classmethod
    def validate_state_names(
        cls, values: tuple[CandidateStateField, ...]
    ) -> tuple[CandidateStateField, ...]:
        if len({value.name for value in values}) != len(values):
            raise ValueError("candidate_state names must be unique")
        return values

    @field_validator("predicted_consequences")
    @classmethod
    def validate_predictions(
        cls, values: tuple[PredictedConsequence, ...]
    ) -> tuple[PredictedConsequence, ...]:
        ids = tuple(value.prediction_id for value in values)
        _unique(ids, "predicted consequence IDs")
        return values

    @field_validator("provenance_references")
    @classmethod
    def validate_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not _REF_RE.fullmatch(value):
                raise ValueError("provenance references must be safe references")
        return _unique(values, "provenance_references")

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"realization_id"})

    @model_validator(mode="after")
    def validate_content_id(self) -> CandidateRealization:
        if self.realization_id != _content_id("qpre_realization", self.material_fields()):
            raise ValueError("realization_id must match canonical content")
        return self


def build_candidate_realization(
    *,
    source_state_hash: str,
    frame_hash: str,
    candidate_state: Sequence[CandidateStateField],
    transformations: Sequence[TransformationStep],
    predicted_consequences: Sequence[PredictedConsequence],
    reversibility: Reversibility,
    cost_units: int,
    risk_score: int,
    provenance_references: Sequence[str],
) -> CandidateRealization:
    material = {
        "source_state_hash": source_state_hash,
        "frame_hash": frame_hash,
        "candidate_state": tuple(candidate_state),
        "transformations": tuple(transformations),
        "predicted_consequences": tuple(predicted_consequences),
        "reversibility": reversibility,
        "cost_units": cost_units,
        "risk_score": risk_score,
        "provenance_references": tuple(provenance_references),
        "epistemic_class": QPREEpistemicClass.POSSIBILITY,
        "actual": False,
        "verified": False,
        "authority": False,
        "memory_eligible": False,
    }
    draft = CandidateRealization.model_construct(
        realization_id="qpre_realization_draft", **material
    )
    normalized = draft.material_fields()
    return CandidateRealization.model_validate(
        {
            "realization_id": _content_id("qpre_realization", normalized),
            **normalized,
        }
    )


class QPRECandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-qpre-shadow-v-next-1"] = QPRE_SCHEMA_VERSION
    candidate_id: StrictStr
    source_state_hash: StrictStr
    frame_hash: StrictStr
    assumptions: tuple[StrictStr, ...] = ()
    uncertainty: StructuredUncertainty
    realization: CandidateRealization
    provenance_references: tuple[StrictStr, ...] = Field(min_length=1)
    epistemic_class: Literal[QPREEpistemicClass.POSSIBILITY] = (
        QPREEpistemicClass.POSSIBILITY
    )
    actual: Literal[False] = False
    verified: Literal[False] = False
    authority: Literal[False] = False
    memory_eligible: Literal[False] = False

    @field_validator("source_state_hash", "frame_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _nonblank(value)
        return _unique(values, "assumptions")

    @field_validator("provenance_references")
    @classmethod
    def validate_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not _REF_RE.fullmatch(value):
                raise ValueError("provenance references must be safe references")
        return _unique(values, "provenance_references")

    @model_validator(mode="after")
    def validate_contract(self) -> QPRECandidate:
        if self.assumptions != self.uncertainty.assumptions:
            raise ValueError("candidate assumptions must equal uncertainty assumptions")
        if self.realization.source_state_hash != self.source_state_hash:
            raise ValueError("realization source_state_hash does not match candidate")
        if self.realization.frame_hash != self.frame_hash:
            raise ValueError("realization frame_hash does not match candidate")
        if self.candidate_id != _content_id("qpre_candidate", self.material_fields()):
            raise ValueError("candidate_id must match canonical content")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"candidate_id"})


def build_qpre_candidate(
    *,
    source_state_hash: str,
    frame_hash: str,
    assumptions: Sequence[str],
    uncertainty: StructuredUncertainty,
    realization: CandidateRealization,
    provenance_references: Sequence[str],
) -> QPRECandidate:
    material = {
        "schema_version": QPRE_SCHEMA_VERSION,
        "source_state_hash": source_state_hash,
        "frame_hash": frame_hash,
        "assumptions": tuple(assumptions),
        "uncertainty": uncertainty,
        "realization": realization,
        "provenance_references": tuple(provenance_references),
        "epistemic_class": QPREEpistemicClass.POSSIBILITY,
        "actual": False,
        "verified": False,
        "authority": False,
        "memory_eligible": False,
    }
    draft = QPRECandidate.model_construct(candidate_id="qpre_candidate_draft", **material)
    normalized = draft.material_fields()
    return QPRECandidate.model_validate(
        {
            "candidate_id": _content_id("qpre_candidate", normalized),
            **normalized,
        }
    )


class PossibilityField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-qpre-shadow-v-next-1"] = QPRE_SCHEMA_VERSION
    possibility_field_id: StrictStr
    source_state_hash: StrictStr
    frame_hash: StrictStr
    candidates: tuple[QPRECandidate, ...] = Field(min_length=1, max_length=64)
    epistemic_class: Literal[QPREEpistemicClass.POSSIBILITY] = (
        QPREEpistemicClass.POSSIBILITY
    )
    actual: Literal[False] = False
    verified: Literal[False] = False
    authority: Literal[False] = False
    memory_eligible: Literal[False] = False

    @field_validator("source_state_hash", "frame_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("hash must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> PossibilityField:
        ids = tuple(candidate.candidate_id for candidate in self.candidates)
        _unique(ids, "candidate IDs")
        for candidate in self.candidates:
            if candidate.source_state_hash != self.source_state_hash:
                raise ValueError("candidate source_state_hash does not match field")
            if candidate.frame_hash != self.frame_hash:
                raise ValueError("candidate frame_hash does not match field")
        expected = _content_id("qpre_field", self.material_fields())
        if self.possibility_field_id != expected:
            raise ValueError("possibility_field_id must match canonical content")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"possibility_field_id"})


def build_possibility_field(
    *, source_state_hash: str, frame_hash: str, candidates: Sequence[QPRECandidate]
) -> PossibilityField:
    material = {
        "schema_version": QPRE_SCHEMA_VERSION,
        "source_state_hash": source_state_hash,
        "frame_hash": frame_hash,
        "candidates": tuple(candidates),
        "epistemic_class": QPREEpistemicClass.POSSIBILITY,
        "actual": False,
        "verified": False,
        "authority": False,
        "memory_eligible": False,
    }
    draft = PossibilityField.model_construct(
        possibility_field_id="qpre_field_draft", **material
    )
    normalized = draft.material_fields()
    return PossibilityField.model_validate(
        {
            "possibility_field_id": _content_id("qpre_field", normalized),
            **normalized,
        }
    )


class QPRERender(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-qpre-shadow-v-next-1"] = QPRE_SCHEMA_VERSION
    render_id: StrictStr
    source_state_hash: StrictStr
    frame_hash: StrictStr
    possibility_field: PossibilityField
    renderer: Literal["DETERMINISTIC_SHADOW"] = "DETERMINISTIC_SHADOW"
    epistemic_class: Literal[QPREEpistemicClass.POSSIBILITY] = (
        QPREEpistemicClass.POSSIBILITY
    )
    actual: Literal[False] = False
    verified: Literal[False] = False
    authority: Literal[False] = False
    memory_eligible: Literal[False] = False
    io_performed: Literal[False] = False
    network_performed: Literal[False] = False
    model_called: Literal[False] = False
    state_mutated: Literal[False] = False

    @field_validator("source_state_hash", "frame_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("hash must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> QPRERender:
        if self.possibility_field.source_state_hash != self.source_state_hash:
            raise ValueError("render source_state_hash does not match field")
        if self.possibility_field.frame_hash != self.frame_hash:
            raise ValueError("render frame_hash does not match field")
        if self.render_id != _content_id("qpre_render", self.material_fields()):
            raise ValueError("render_id must match canonical content")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"render_id"})


def render_qpre(possibility_field: PossibilityField) -> QPRERender:
    material = {
        "schema_version": QPRE_SCHEMA_VERSION,
        "source_state_hash": possibility_field.source_state_hash,
        "frame_hash": possibility_field.frame_hash,
        "possibility_field": possibility_field,
        "renderer": "DETERMINISTIC_SHADOW",
        "epistemic_class": QPREEpistemicClass.POSSIBILITY,
        "actual": False,
        "verified": False,
        "authority": False,
        "memory_eligible": False,
        "io_performed": False,
        "network_performed": False,
        "model_called": False,
        "state_mutated": False,
    }
    draft = QPRERender.model_construct(render_id="qpre_render_draft", **material)
    normalized = draft.material_fields()
    return QPRERender.model_validate(
        {"render_id": _content_id("qpre_render", normalized), **normalized}
    )


__all__ = [
    "QPRE_SCHEMA_VERSION",
    "CandidateRealization",
    "CandidateStateField",
    "ConfidenceBasis",
    "PossibilityField",
    "PredictedConsequence",
    "QPRECandidate",
    "QPREEpistemicClass",
    "QPRERender",
    "Reversibility",
    "StructuredUncertainty",
    "TransformationStep",
    "build_candidate_realization",
    "build_possibility_field",
    "build_predicted_consequence",
    "build_qpre_candidate",
    "render_qpre",
]
