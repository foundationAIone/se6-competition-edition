"""Merkabah v-next SHADOW traversal contracts.

This module records a deterministic C -> T -> C' traversal over mapping or
QPRE references.  It does not replace :mod:`se666_core.merkabah_rotation` and
has no mechanism for executing, verifying, assimilating, or authorizing work.
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
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from se666_core.canonical_contracts import canonical_sha256

MERKABAH_TRAVERSAL_SCHEMA_VERSION = "se6-merkabah-traversal-shadow-v-next-1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def _content_id(prefix: str, material: object) -> str:
    return f"{prefix}_{canonical_sha256(material)}"


class TraversalReferenceKind(str, Enum):
    MAPPED = "MAPPED"
    QPRE = "QPRE"


class TraversalEpistemicClass(str, Enum):
    POSSIBILITY = "POSSIBILITY"
    VERIFIED = "VERIFIED"


class TraversalReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: TraversalReferenceKind
    reference_id: StrictStr = Field(min_length=1, max_length=256)

    @field_validator("reference_id")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not _REF_RE.fullmatch(value):
            raise ValueError("reference_id must be a safe reference")
        return value


class TraversalCenter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-merkabah-traversal-shadow-v-next-1"] = (
        MERKABAH_TRAVERSAL_SCHEMA_VERSION
    )
    center_id: StrictStr
    state_hash: StrictStr
    frame_hash: StrictStr
    predecessor_center_id: StrictStr | None = None

    @field_validator("state_hash", "frame_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("predecessor_center_id")
    @classmethod
    def validate_predecessor(cls, value: str | None) -> str | None:
        if value is not None and not _REF_RE.fullmatch(value):
            raise ValueError("predecessor_center_id must be a safe reference")
        return value

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"center_id"})

    @model_validator(mode="after")
    def validate_content_id(self) -> TraversalCenter:
        if self.center_id != _content_id("merkabah_center", self.material_fields()):
            raise ValueError("center_id must match canonical content")
        return self


def build_traversal_center(
    *,
    state_hash: str,
    frame_hash: str,
    predecessor_center_id: str | None = None,
) -> TraversalCenter:
    material = {
        "schema_version": MERKABAH_TRAVERSAL_SCHEMA_VERSION,
        "state_hash": state_hash,
        "frame_hash": frame_hash,
        "predecessor_center_id": predecessor_center_id,
    }
    draft = TraversalCenter.model_construct(center_id="merkabah_center_draft", **material)
    normalized = draft.material_fields()
    return TraversalCenter.model_validate(
        {"center_id": _content_id("merkabah_center", normalized), **normalized}
    )


class TraversalTerminal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-merkabah-traversal-shadow-v-next-1"] = (
        MERKABAH_TRAVERSAL_SCHEMA_VERSION
    )
    terminal_id: StrictStr
    source_center_id: StrictStr
    references: tuple[TraversalReference, ...] = Field(min_length=1, max_length=64)
    summary: StrictStr = Field(min_length=1, max_length=1024)
    epistemic_class: Literal[TraversalEpistemicClass.POSSIBILITY] = (
        TraversalEpistemicClass.POSSIBILITY
    )
    actual: Literal[False] = False
    verified: Literal[False] = False
    authority: Literal[False] = False
    memory_eligible: Literal[False] = False

    @field_validator("source_center_id")
    @classmethod
    def validate_source_reference(cls, value: str) -> str:
        if not _REF_RE.fullmatch(value):
            raise ValueError("source_center_id must be a safe reference")
        return value

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError("summary must be non-empty and trimmed")
        return value

    @field_validator("references")
    @classmethod
    def validate_references(
        cls, values: tuple[TraversalReference, ...]
    ) -> tuple[TraversalReference, ...]:
        identities = tuple((value.kind.value, value.reference_id) for value in values)
        if len(identities) != len(set(identities)):
            raise ValueError("terminal references must be unique")
        return values

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"terminal_id"})

    @model_validator(mode="after")
    def validate_content_id(self) -> TraversalTerminal:
        if self.terminal_id != _content_id("merkabah_terminal", self.material_fields()):
            raise ValueError("terminal_id must match canonical content")
        return self


def build_traversal_terminal(
    *,
    source_center_id: str,
    references: Sequence[TraversalReference],
    summary: str,
) -> TraversalTerminal:
    material = {
        "schema_version": MERKABAH_TRAVERSAL_SCHEMA_VERSION,
        "source_center_id": source_center_id,
        "references": tuple(references),
        "summary": summary,
        "epistemic_class": TraversalEpistemicClass.POSSIBILITY,
        "actual": False,
        "verified": False,
        "authority": False,
        "memory_eligible": False,
    }
    draft = TraversalTerminal.model_construct(
        terminal_id="merkabah_terminal_draft", **material
    )
    normalized = draft.material_fields()
    return TraversalTerminal.model_validate(
        {"terminal_id": _content_id("merkabah_terminal", normalized), **normalized}
    )


class VerifiedConsequenceAssimilation(BaseModel):
    """A reference to independent verification already performed elsewhere.

    The record carries evidence references; this SHADOW module never performs
    verification or assimilation itself.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-merkabah-traversal-shadow-v-next-1"] = (
        MERKABAH_TRAVERSAL_SCHEMA_VERSION
    )
    evidence_id: StrictStr
    source_center_id: StrictStr
    consequence_reference: StrictStr
    verification_reference: StrictStr
    assimilation_reference: StrictStr
    next_state_hash: StrictStr
    next_frame_hash: StrictStr
    consequence_status: Literal[TraversalEpistemicClass.VERIFIED] = (
        TraversalEpistemicClass.VERIFIED
    )
    assimilation_status: Literal[TraversalEpistemicClass.VERIFIED] = (
        TraversalEpistemicClass.VERIFIED
    )
    independently_verified: Literal[True] = True

    @field_validator(
        "source_center_id",
        "consequence_reference",
        "verification_reference",
        "assimilation_reference",
    )
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not _REF_RE.fullmatch(value):
            raise ValueError("evidence references must be safe references")
        return value

    @field_validator("next_state_hash", "next_frame_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("hash must be a lowercase SHA-256 digest")
        return value

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"evidence_id"})

    @model_validator(mode="after")
    def validate_content_id(self) -> VerifiedConsequenceAssimilation:
        expected = _content_id("merkabah_verified_assimilation", self.material_fields())
        if self.evidence_id != expected:
            raise ValueError("evidence_id must match canonical content")
        return self


def build_verified_consequence_assimilation(
    *,
    source_center_id: str,
    consequence_reference: str,
    verification_reference: str,
    assimilation_reference: str,
    next_state_hash: str,
    next_frame_hash: str,
) -> VerifiedConsequenceAssimilation:
    material = {
        "schema_version": MERKABAH_TRAVERSAL_SCHEMA_VERSION,
        "source_center_id": source_center_id,
        "consequence_reference": consequence_reference,
        "verification_reference": verification_reference,
        "assimilation_reference": assimilation_reference,
        "next_state_hash": next_state_hash,
        "next_frame_hash": next_frame_hash,
        "consequence_status": TraversalEpistemicClass.VERIFIED,
        "assimilation_status": TraversalEpistemicClass.VERIFIED,
        "independently_verified": True,
    }
    draft = VerifiedConsequenceAssimilation.model_construct(
        evidence_id="merkabah_verified_assimilation_draft", **material
    )
    normalized = draft.material_fields()
    return VerifiedConsequenceAssimilation.model_validate(
        {
            "evidence_id": _content_id(
                "merkabah_verified_assimilation", normalized
            ),
            **normalized,
        }
    )


class MerkabahTraversal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-merkabah-traversal-shadow-v-next-1"] = (
        MERKABAH_TRAVERSAL_SCHEMA_VERSION
    )
    traversal_id: StrictStr
    path: Literal["C->T->C'"] = "C->T->C'"
    source_center: TraversalCenter
    terminal: TraversalTerminal
    returned_center: TraversalCenter
    verified_assimilation: VerifiedConsequenceAssimilation | None = None
    outward_epistemic_class: Literal[TraversalEpistemicClass.POSSIBILITY] = (
        TraversalEpistemicClass.POSSIBILITY
    )
    state_changed: StrictBool
    proposal_only: Literal[True] = True
    authority: Literal[False] = False
    io_performed: Literal[False] = False
    network_performed: Literal[False] = False
    model_called: Literal[False] = False

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"traversal_id"})

    @model_validator(mode="after")
    def validate_contract(self) -> MerkabahTraversal:
        if self.terminal.source_center_id != self.source_center.center_id:
            raise ValueError("terminal must be bound to source center")

        changed = self.returned_center != self.source_center
        if self.state_changed != changed:
            raise ValueError("state_changed must describe the returned center")

        evidence = self.verified_assimilation
        if evidence is None:
            if changed:
                raise ValueError("C' must equal C without verified assimilation")
        else:
            if evidence.source_center_id != self.source_center.center_id:
                raise ValueError("verified assimilation must bind to source center")
            if self.returned_center.state_hash != evidence.next_state_hash:
                raise ValueError("returned center state is not verified next state")
            if self.returned_center.frame_hash != evidence.next_frame_hash:
                raise ValueError("returned center frame is not verified next frame")
            if changed and (
                self.returned_center.predecessor_center_id != self.source_center.center_id
            ):
                raise ValueError("changed C' must lineage-link to C")

        if self.traversal_id != _content_id("merkabah_traversal", self.material_fields()):
            raise ValueError("traversal_id must match canonical content")
        return self


def traverse_merkabah(
    *,
    center: TraversalCenter,
    terminal: TraversalTerminal,
    verified_assimilation: VerifiedConsequenceAssimilation | None = None,
) -> MerkabahTraversal:
    returned_center = center
    if verified_assimilation is not None and (
        verified_assimilation.next_state_hash != center.state_hash
        or verified_assimilation.next_frame_hash != center.frame_hash
    ):
        returned_center = build_traversal_center(
            state_hash=verified_assimilation.next_state_hash,
            frame_hash=verified_assimilation.next_frame_hash,
            predecessor_center_id=center.center_id,
        )

    material = {
        "schema_version": MERKABAH_TRAVERSAL_SCHEMA_VERSION,
        "path": "C->T->C'",
        "source_center": center,
        "terminal": terminal,
        "returned_center": returned_center,
        "verified_assimilation": verified_assimilation,
        "outward_epistemic_class": TraversalEpistemicClass.POSSIBILITY,
        "state_changed": returned_center != center,
        "proposal_only": True,
        "authority": False,
        "io_performed": False,
        "network_performed": False,
        "model_called": False,
    }
    draft = MerkabahTraversal.model_construct(
        traversal_id="merkabah_traversal_draft", **material
    )
    normalized = draft.material_fields()
    return MerkabahTraversal.model_validate(
        {"traversal_id": _content_id("merkabah_traversal", normalized), **normalized}
    )


__all__ = [
    "MERKABAH_TRAVERSAL_SCHEMA_VERSION",
    "MerkabahTraversal",
    "TraversalCenter",
    "TraversalEpistemicClass",
    "TraversalReference",
    "TraversalReferenceKind",
    "TraversalTerminal",
    "VerifiedConsequenceAssimilation",
    "build_traversal_center",
    "build_traversal_terminal",
    "build_verified_consequence_assimilation",
    "traverse_merkabah",
]
