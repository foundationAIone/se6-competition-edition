"""A fail-closed, read-only adapter from audited EntityStore to a research frame.

This does NOT activate a runtime, equate Native and Entity state hashes, grant
research actions authority, or establish full-canonical/general-state coverage.
Only an audited store can *produce* a contemporaneous source projection; a
serialized projection is NOT a transferable authentication credential.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from .canonical_contracts import canonical_sha256
from .entity_state import SE6EntityState
from .entity_store import EntityCheckpointRecord, EntityCommitReceipt, EntityStore
from .epistemic_status import EpistemicStatus
from .realization_frame import (
    RealizationFrame, create_realization_frame, create_realization_state,
    create_source_observation,
)
from . import candidate_state_transition as typed

SCHEMA = "se6-audited-entity-to-research-frame-v1"
_RESEARCH_FRAME = "Audited persisted Entity state (read-only research frame)"
_DIMENSIONS = ("entity-identity", "entity-state-version", "event-sequence", "receipt-lineage")
_RULES = (
    "EntityStore audit verifies the persisted state and receipt lineage, not external World truth.",
    "Research Native state and Entity state are different schemas; hashes are never substituted.",
    "A frame is descriptive. It grants no execution, network, model, or owner authority.",
)


class BridgeSourceError(ValueError):
    """Stable failure: no Entity authority or effect accompanies this error."""


class EntityResearchFrame(BaseModel):
    """Complete typed persisted Entity record, plus an audited shadow frame.

    The UTF-8 JSON payload is a *lossless* complement for the EntityState Pydantic
    model. Its hash proves consistency, NOT who authored it. Every use requiring
    a current source must call ``recheck_current`` against the actual store.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal["se6-audited-entity-to-research-frame-v1"] = SCHEMA
    representation_seed: Literal["([{01*}])"] = "([{01*}])"
    representation_scope: Literal["TYPED_ENTITY_JSON_UTF8_NOT_UNIVERSAL_SEED"] = (
        "TYPED_ENTITY_JSON_UTF8_NOT_UNIVERSAL_SEED"
    )
    source_status: Literal["AUDITED_PERSISTED_RECORD_NOT_WORLD_TRUTH"] = (
        "AUDITED_PERSISTED_RECORD_NOT_WORLD_TRUTH"
    )
    identity_instance_id: StrictStr
    identity_state_id: StrictStr
    entity_state_id: StrictStr
    entity_state_hash: StrictStr
    entity_state_version: StrictInt = Field(ge=0)
    state_schema: StrictStr
    event_sequence: StrictInt = Field(ge=0)
    previous_entity_state_id: StrictStr | None
    receipt_id: StrictStr
    receipt_hash: StrictStr
    receipt_sequence: StrictInt = Field(ge=1)
    checkpoint_id: StrictStr
    checkpoint_hash: StrictStr
    state_lineage_count: StrictInt = Field(ge=1)
    receipt_lineage_count: StrictInt = Field(ge=1)
    state_json_b64: StrictStr
    state_json_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    store_locator_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    source_frame: RealizationFrame
    metadata_term: list
    authority_effect: Literal["NONE"] = "NONE"
    native_state_interchangeable: Literal[False] = False
    production_write_performed: Literal[False] = False
    source_commit_performed: Literal[False] = False
    projection_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def internally_consistent(self):
        if self.projection_hash != canonical_sha256(self.material_fields()):
            raise ValueError("BRIDGE_PROJECTION_HASH_MISMATCH")
        if self.entity_state_id != "entity_state_" + self.entity_state_hash:
            raise ValueError("BRIDGE_ENTITY_STATE_HASH_MISMATCH")
        try:
            raw = base64.b64decode(self.state_json_b64, validate=True)
            if base64.b64encode(raw).decode("ascii") != self.state_json_b64:
                raise ValueError("BRIDGE_PAYLOAD_ENCODING")
            if hashlib.sha256(raw).hexdigest() != self.state_json_sha256:
                raise ValueError("BRIDGE_PAYLOAD_HASH_MISMATCH")
            state = SE6EntityState.model_validate_json(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("BRIDGE_TYPED_STATE_RESTORE_FAILED") from exc
        if (state.entity_state_id != self.entity_state_id or
                state.state_hash != self.entity_state_hash or
                state.state_version != self.entity_state_version or
                state.schema_version != self.state_schema or
                state.identity.instance_id != self.identity_instance_id or
                state.identity.identity_state_id != self.identity_state_id or
                state.event_sequence != self.event_sequence or
                state.previous_entity_state_id != self.previous_entity_state_id):
            raise ValueError("BRIDGE_STATE_SCOPE_MISMATCH")
        material = {
            "schema": SCHEMA,
            "representation": self.representation_seed,
            "carrier": self.representation_scope,
            "entity": self.identity_instance_id,
            "state": self.entity_state_id,
            "state_hash": self.entity_state_hash,
            "payload_sha256": self.state_json_sha256,
            "receipt": self.receipt_id,
            "checkpoint": self.checkpoint_id,
            "store_locator": self.store_locator_sha256,
        }
        if typed.un_tree(self.metadata_term) != material:
            raise ValueError("BRIDGE_TYPED_TERM_MISMATCH")
        obs = self.source_frame.x.source_observations
        if (len(obs) != 1 or obs[0].source_reference != self.entity_state_id or
                obs[0].epistemic_status is not EpistemicStatus.OBSERVED or
                tuple(obs[0].evidence_references) != (
                    self.receipt_id, self.checkpoint_id, self.identity_state_id
                ) or
                self.source_frame.frame_name != _RESEARCH_FRAME or
                self.source_frame.dimensions != _DIMENSIONS or
                self.source_frame.representation_rules != _RULES or
                self.source_frame.x.state_summary != _summary(self)):
            raise ValueError("BRIDGE_FRAME_SCOPE_MISMATCH")
        return self

    def material_fields(self):
        return self.model_dump(mode="python", exclude={"projection_hash"})

    def restored_state(self) -> SE6EntityState:
        # Revalidation stops modified model copies even if fields were mutated.
        checked = self.__class__.model_validate_json(self.model_dump_json())
        return SE6EntityState.model_validate_json(base64.b64decode(checked.state_json_b64))


def _summary(p):
    return (f"Persisted Entity {p.identity_instance_id}: {p.entity_state_id}; "
            f"version {p.entity_state_version}; full typed payload {p.state_json_sha256}. "
            "This is not a Native-state hash or live World proof.")


def _read_audited(store: EntityStore):
    if type(store) is not EntityStore:
        raise BridgeSourceError("AUDITED_ENTITY_STORE_REQUIRED")
    integrity, restart, lineage = store.inspect_read_only()
    if not integrity.valid or restart is None or lineage is None:
        raise BridgeSourceError("AUDITED_ENTITY_HEAD_UNAVAILABLE:" + ",".join(integrity.reason_codes))
    state, receipt, checkpoint = restart.state, restart.latest_receipt, restart.latest_checkpoint
    if not isinstance(state, SE6EntityState) or not isinstance(receipt, EntityCommitReceipt) or not isinstance(checkpoint, EntityCheckpointRecord):
        raise BridgeSourceError("ENTITY_HEAD_TYPES")
    if (state.entity_state_id != integrity.head_state_id or
            state.state_version != integrity.head_state_version or
            state.event_sequence != integrity.head_event_sequence or
            receipt.state_after_id != state.entity_state_id or
            receipt.state_after_hash != state.state_hash or
            receipt.state_after_version != state.state_version or
            checkpoint.entity_state_id != state.entity_state_id or
            checkpoint.state_version != state.state_version or
            checkpoint.receipt_id != receipt.receipt_id or
            checkpoint.receipt_hash != receipt.receipt_hash or
            len(lineage.receipts) != integrity.receipt_count or
            len(lineage.states) != integrity.state_count or
            lineage.receipts[-1].receipt_id != receipt.receipt_id or
            lineage.states[-1].entity_state_id != state.entity_state_id or
            state.identity.identity_state_id != "identity_" + state.identity.identity_state_hash):
        raise BridgeSourceError("ENTITY_AUDITED_LINEAGE_SCOPE_MISMATCH")
    # Fail closed against inconsistent or forged in-memory model instances.
    SE6EntityState.model_validate_json(state.model_dump_json())
    EntityCommitReceipt.model_validate_json(receipt.model_dump_json())
    EntityCheckpointRecord.model_validate_json(checkpoint.model_dump_json())
    return integrity, state, receipt, checkpoint


def _store_locator(store: EntityStore) -> str:
    # A source fingerprint, not a signature, secret, or permission.  Avoid
    # exposing the user's private local state path in research projections.
    import os
    path = str(store.database_path.resolve())
    if os.name == "nt":
        path = path.casefold()
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def project_audited_entity(store: EntityStore) -> EntityResearchFrame:
    """Consume ONLY the existing store's audited, one-transaction snapshot."""
    integrity, state, receipt, checkpoint = _read_audited(store)
    raw = state.model_dump_json().encode("utf-8")
    payload_hash = hashlib.sha256(raw).hexdigest()
    source = create_source_observation(
        source_reference=state.entity_state_id,
        summary=("Audited persisted Entity state and receipt; no claim of present "
                 "runtime operation or external World truth."),
        epistemic_status=EpistemicStatus.OBSERVED,
        evidence_references=(receipt.receipt_id, checkpoint.checkpoint_id, state.identity.identity_state_id),
    )
    x = create_realization_state(
        state_summary=(f"Persisted Entity {state.identity.instance_id}: {state.entity_state_id}; "
                       f"version {state.state_version}; full typed payload {payload_hash}. "
                       "This is not a Native-state hash or live World proof."),
        source_observations=(source,),
    )
    frame = create_realization_frame(
        x, frame_name=_RESEARCH_FRAME, dimensions=_DIMENSIONS,
        representation_rules=_RULES,
    )
    material = {
        "schema": SCHEMA,
        "representation": "([{01*}])",
        "carrier": "TYPED_ENTITY_JSON_UTF8_NOT_UNIVERSAL_SEED",
        "entity": state.identity.instance_id,
        "state": state.entity_state_id,
        "state_hash": state.state_hash,
        "payload_sha256": payload_hash,
        "receipt": receipt.receipt_id,
        "checkpoint": checkpoint.checkpoint_id,
        "store_locator": _store_locator(store),
    }
    packet = dict(
        schema_version=SCHEMA,
        representation_seed="([{01*}])",
        representation_scope="TYPED_ENTITY_JSON_UTF8_NOT_UNIVERSAL_SEED",
        source_status="AUDITED_PERSISTED_RECORD_NOT_WORLD_TRUTH",
        identity_instance_id=state.identity.instance_id,
        identity_state_id=state.identity.identity_state_id,
        entity_state_id=state.entity_state_id,
        entity_state_hash=state.state_hash,
        entity_state_version=state.state_version,
        state_schema=state.schema_version,
        event_sequence=state.event_sequence,
        previous_entity_state_id=state.previous_entity_state_id,
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.receipt_hash,
        receipt_sequence=receipt.commit_sequence,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_hash=checkpoint.checkpoint_hash,
        state_lineage_count=integrity.state_count,
        receipt_lineage_count=integrity.receipt_count,
        state_json_b64=base64.b64encode(raw).decode("ascii"),
        state_json_sha256=payload_hash,
        store_locator_sha256=_store_locator(store),
        source_frame=frame,
        metadata_term=typed.tree(material),
        authority_effect="NONE",
        native_state_interchangeable=False,
        production_write_performed=False,
        source_commit_performed=False,
    )
    draft = EntityResearchFrame.model_construct(**packet, projection_hash="0" * 64)
    return EntityResearchFrame(**packet, projection_hash=canonical_sha256(draft.material_fields()))


def recheck_current(store: EntityStore, projection: EntityResearchFrame):
    """Re-audit on consumption; a saved projection is not persistent authority."""
    if not isinstance(projection, EntityResearchFrame):
        raise BridgeSourceError("BRIDGE_PROJECTION_REQUIRED")
    # Re-validate every value even if model_copy() bypassed validators.
    checked = EntityResearchFrame.model_validate_json(projection.model_dump_json())
    integrity, state, receipt, checkpoint = _read_audited(store)
    if (_store_locator(store) != checked.store_locator_sha256 or
            state.entity_state_id != checked.entity_state_id or
            state.state_hash != checked.entity_state_hash or
            state.state_version != checked.entity_state_version or
            receipt.receipt_id != checked.receipt_id or
            receipt.receipt_hash != checked.receipt_hash or
            checkpoint.checkpoint_id != checked.checkpoint_id or
            checkpoint.checkpoint_hash != checked.checkpoint_hash or
            integrity.state_count != checked.state_lineage_count or
            integrity.receipt_count != checked.receipt_lineage_count or
            state.model_dump_json().encode("utf-8") != base64.b64decode(checked.state_json_b64)):
        raise BridgeSourceError("BRIDGE_STALE_OR_FOREIGN_HEAD")
    # This proves a current persisted *record*. No action authority is created.
    return checked.source_frame


def compare_native_binding(projection: EntityResearchFrame, research_binding: dict) -> dict:
    """Expose the distinct domains; never silently substitute Entity for Native."""
    checked = EntityResearchFrame.model_validate_json(projection.model_dump_json())
    if type(research_binding) is not dict or research_binding.get("entity_id") != checked.identity_instance_id:
        raise BridgeSourceError("ENTITY_IDENTITY_DOMAIN_MISMATCH")
    native_hash = research_binding.get("entity_state")
    if not isinstance(native_hash, str) or len(native_hash) != 64:
        raise BridgeSourceError("NATIVE_STATE_REFERENCE_INVALID")
    return dict(
        status="DISTINCT_STATE_DOMAINS_REQUIRE_EXPLICIT_WITNESSED_TRANSITION",
        entity_state_id=checked.entity_state_id,
        native_state_hash=native_hash,
        research_identity=research_binding["entity_id"],
        can_execute=False, can_replace_native_state=False,
        authority_effect="NONE",
    )

__all__ = ["EntityResearchFrame", "BridgeSourceError", "project_audited_entity", "recheck_current", "compare_native_binding"]
