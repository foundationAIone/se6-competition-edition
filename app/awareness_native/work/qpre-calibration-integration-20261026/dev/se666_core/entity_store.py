"""Durable, local-only persistence for the SE6 three-loop entity.

This module is deliberately separate from the pure reducers in
``entity_state``, ``entity_events``, and ``three_loop_entity``.  It grants no
authority and performs no network or external action.  Its only production
effect is an atomic write to one SQLite database below an operating-system
trusted current-user state root.

Tests must opt in through :meth:`EntityStore.for_testing` with an explicit
path.  Read-only auditing is absence-safe: auditing a missing store creates
neither a directory nor a database.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import re
import sqlite3
import threading
from contextvars import ContextVar, copy_context
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .canonical_contracts import canonical_sha256
from .dashboard_read_timing import emit_audit_completion, is_polling_read, read_count, read_span, timing_active
from .embodiment_lifecycle import LifecycleState
from .entity_activation import (
    EntityActivationEvidenceBundle,
    EntityActivationRecord,
    activation_basis_references,
    build_first_local_live_entity_state,
    evaluate_entity_activation,
)
from .entity_events import (
    AuthorityStatus,
    EntityEvent,
    EntityEventDraft,
    EventEndpoint,
    EventSourceKind,
    EventType,
    LifecyclePayload,
    LifecycleSignal,
    LoopName,
    ObservationProvenance,
    PersistencePolicy,
    SensitivityClassification,
    create_entity_event,
)
from .entity_state import (
    ControllerStatus,
    EmergencyStopState,
    EntityOperatingMode,
    LifecycleView,
    OperationalConnectionState,
    SE6EntityState,
    SharedMetabolismSnapshot,
    create_entity_state,
)
from .epistemic_status import EpistemicStatus
from .production_state_paths import trusted_local_state_root
from .three_loop_entity import CommunicationIntent, CoordinatorStepResult

ENTITY_STORE_SCHEMA_VERSION = 1
ENTITY_STORE_POLICY_VERSION = "se6-durable-entity-store-v1"
ENTITY_STORE_RELATIVE_PATH = Path("SE6Triad") / "entity" / "se6triad_entity.sqlite3"
_ZERO_HASH = "0" * 64
_HASH_PATTERN = r"^[0-9a-f]{64}$"
_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$"
_INGRESS_ID_PATTERN = r"^entity_ingress_[0-9a-f]{64}$"
_OUTBOX_ID_PATTERN = r"^entity_outbox_[0-9a-f]{64}$"
_OUTBOX_DELIVERY_ID_PATTERN = r"^entity_outbox_delivery_[0-9a-f]{64}$"
_RECEIPT_ID_PATTERN = r"^entity_commit_receipt_[0-9a-f]{64}$"
_CHECKPOINT_ID_PATTERN = r"^entity_checkpoint_[0-9a-f]{64}$"
_SECRET_LIKE = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*\b", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_ -]?key|password|passwd|private[_ -]?key|"
        r"access[_ -]?token|refresh[_ -]?token)\s*[:=]",
        re.IGNORECASE,
    ),
)


def default_entity_database_path() -> Path:
    """Return the one production entity-store path.

    No environment variable controls this path.  The trusted-root helper uses
    the Windows Known Folder API (or the current user's platform state root).
    """

    path = (trusted_local_state_root() / ENTITY_STORE_RELATIVE_PATH).resolve(
        strict=False
    )
    repository = Path(__file__).resolve(strict=False).parents[1]
    if path == repository or repository in path.parents:
        raise EntityStoreError("PRODUCTION_PATH_INSIDE_REPOSITORY")
    return path


class EntityStoreError(RuntimeError):
    """A stable, non-secret store failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class EntityIngressRecord(BaseModel):
    """An append-only queued ingress; consumption is recorded separately."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-entity-ingress-v1"] = "se6-entity-ingress-v1"
    ingress_id: StrictStr = Field(pattern=_INGRESS_ID_PATTERN)
    queue_sequence: StrictInt = Field(ge=1)
    ingress_key: StrictStr = Field(min_length=1, max_length=512)
    draft_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    draft: EntityEventDraft
    enqueued_at_utc: datetime

    @field_validator("enqueued_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "enqueued_at_utc")

    @field_validator("ingress_key")
    @classmethod
    def key_is_non_secret(cls, value: str) -> str:
        _reject_secret_like(value)
        return value

    @model_validator(mode="after")
    def hashes_are_canonical(self) -> EntityIngressRecord:
        if self.draft_hash != canonical_sha256(self.draft):
            raise ValueError("draft_hash mismatch")
        expected = canonical_sha256(self.material_fields())
        if self.ingress_id != f"entity_ingress_{expected}":
            raise ValueError("ingress_id must derive from ingress material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"ingress_id", "draft"})


class EntityOutboxRecord(BaseModel):
    """A durable communication intent; persistence does not deliver it."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-entity-outbox-v1"] = "se6-entity-outbox-v1"
    outbox_id: StrictStr = Field(pattern=_OUTBOX_ID_PATTERN)
    outbox_sequence: StrictInt = Field(ge=1)
    result_id: StrictStr = Field(pattern=r"^coordinator_result_[0-9a-f]{64}$")
    entity_state_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    intent_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    intent: CommunicationIntent
    created_at_utc: datetime

    @field_validator("created_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "created_at_utc")

    @model_validator(mode="after")
    def hashes_are_canonical(self) -> EntityOutboxRecord:
        if self.intent_hash != canonical_sha256(self.intent):
            raise ValueError("intent_hash mismatch")
        expected = canonical_sha256(self.material_fields())
        if self.outbox_id != f"entity_outbox_{expected}":
            raise ValueError("outbox_id must derive from outbox material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"outbox_id", "intent"})


class EntityOutboxDeliveryRecord(BaseModel):
    """Append-only evidence that a separate caller delivered an outbox item.

    Creating this record does not itself send or display the communication.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-entity-outbox-delivery-v1"] = (
        "se6-entity-outbox-delivery-v1"
    )
    delivery_id: StrictStr = Field(pattern=_OUTBOX_DELIVERY_ID_PATTERN)
    delivery_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    delivery_sequence: StrictInt = Field(ge=1)
    outbox_id: StrictStr = Field(pattern=_OUTBOX_ID_PATTERN)
    delivery_reference: StrictStr = Field(
        min_length=1, max_length=512, pattern=_REFERENCE_PATTERN
    )
    delivered_at_utc: datetime
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("delivered_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "delivered_at_utc")

    @field_validator("delivery_reference")
    @classmethod
    def reference_is_non_secret(cls, value: str) -> str:
        _reject_secret_like(value)
        return value

    @model_validator(mode="after")
    def delivery_is_canonical(self) -> EntityOutboxDeliveryRecord:
        expected = canonical_sha256(self.material_fields())
        if self.delivery_hash != expected:
            raise ValueError("delivery_hash mismatch")
        if self.delivery_id != f"entity_outbox_delivery_{expected}":
            raise ValueError("delivery_id must derive from delivery material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(
            mode="python", exclude={"delivery_id", "delivery_hash"}
        )


class EntityCommitReceipt(BaseModel):
    """Content-addressed evidence for one committed canonical head."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-entity-commit-receipt-v1"] = (
        "se6-entity-commit-receipt-v1"
    )
    receipt_id: StrictStr = Field(pattern=_RECEIPT_ID_PATTERN)
    receipt_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    commit_sequence: StrictInt = Field(ge=1)
    commit_kind: Literal[
        "GENESIS", "STEP", "ACTIVATION", "RUNTIME_DETACH", "RUNTIME_REBIND"
    ]
    runtime_session_id: StrictStr = Field(
        min_length=1, max_length=512, pattern=_REFERENCE_PATTERN
    )
    state_before_id: StrictStr | None = Field(
        default=None, pattern=r"^entity_state_[0-9a-f]{64}$"
    )
    state_after_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    state_after_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    state_after_version: StrictInt = Field(ge=0)
    first_event_sequence: StrictInt | None = Field(default=None, ge=1)
    last_event_sequence: StrictInt | None = Field(default=None, ge=1)
    event_count: StrictInt = Field(ge=0)
    processed_ingress_id: StrictStr | None = Field(
        default=None, pattern=_INGRESS_ID_PATTERN
    )
    coordinator_result_id: StrictStr | None = Field(
        default=None, pattern=r"^coordinator_result_[0-9a-f]{64}$"
    )
    queued_ingress_ids: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    outbox_ids: tuple[StrictStr, ...] = Field(default=(), max_length=16)
    previous_receipt_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    committed_at_utc: datetime

    @field_validator("committed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "committed_at_utc")

    @model_validator(mode="after")
    def receipt_is_consistent_and_canonical(self) -> EntityCommitReceipt:
        if self.commit_kind == "GENESIS":
            if any(
                value is not None
                for value in (
                    self.state_before_id,
                    self.first_event_sequence,
                    self.last_event_sequence,
                    self.processed_ingress_id,
                    self.coordinator_result_id,
                )
            ):
                raise ValueError("genesis receipt cannot bind step material")
            if self.event_count or self.queued_ingress_ids or self.outbox_ids:
                raise ValueError("genesis receipt must be empty")
            if self.state_after_version != 0 or self.previous_receipt_hash != _ZERO_HASH:
                raise ValueError("genesis receipt must establish version zero")
        elif self.commit_kind == "STEP":
            required = (
                self.state_before_id,
                self.first_event_sequence,
                self.last_event_sequence,
                self.processed_ingress_id,
                self.coordinator_result_id,
            )
            if any(value is None for value in required) or self.event_count < 1:
                raise ValueError("step receipt requires complete step bindings")
            assert self.first_event_sequence is not None
            assert self.last_event_sequence is not None
            if self.last_event_sequence - self.first_event_sequence + 1 != self.event_count:
                raise ValueError("receipt event range is not contiguous")
        else:
            if (
                self.state_before_id is None
                or self.first_event_sequence is None
                or self.last_event_sequence is None
                or self.event_count != 1
                or self.first_event_sequence != self.last_event_sequence
            ):
                raise ValueError("verified control transition requires one lifecycle event")
            if (
                self.processed_ingress_id is not None
                or self.coordinator_result_id is not None
                or self.queued_ingress_ids
                or self.outbox_ids
            ):
                raise ValueError("verified control transition cannot claim reducer projections")
        expected = canonical_sha256(self.material_fields())
        if self.receipt_hash != expected:
            raise ValueError("receipt_hash mismatch")
        if self.receipt_id != f"entity_commit_receipt_{expected}":
            raise ValueError("receipt_id must derive from receipt material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(
            mode="python", exclude={"receipt_id", "receipt_hash"}
        )


class EntityCheckpointRecord(BaseModel):
    """Append-only binding of a receipt to all durable chain heads."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-entity-checkpoint-v1"] = (
        "se6-entity-checkpoint-v1"
    )
    checkpoint_id: StrictStr = Field(pattern=_CHECKPOINT_ID_PATTERN)
    checkpoint_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    checkpoint_sequence: StrictInt = Field(ge=1)
    entity_state_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    state_version: StrictInt = Field(ge=0)
    state_chain_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    event_head_id: StrictStr | None = Field(
        default=None, pattern=r"^entity_event_[0-9a-f]{64}$"
    )
    event_sequence: StrictInt = Field(ge=0)
    event_chain_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    receipt_id: StrictStr = Field(pattern=_RECEIPT_ID_PATTERN)
    receipt_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    created_at_utc: datetime

    @field_validator("created_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "created_at_utc")

    @model_validator(mode="after")
    def checkpoint_is_canonical(self) -> EntityCheckpointRecord:
        if (self.event_sequence == 0) != (self.event_head_id is None):
            raise ValueError("checkpoint event head and sequence disagree")
        expected = canonical_sha256(self.material_fields())
        if self.checkpoint_hash != expected:
            raise ValueError("checkpoint_hash mismatch")
        if self.checkpoint_id != f"entity_checkpoint_{expected}":
            raise ValueError("checkpoint_id must derive from checkpoint material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(
            mode="python", exclude={"checkpoint_id", "checkpoint_hash"}
        )


class EntityStoreIntegrityResult(BaseModel):
    """Non-secret result of an absence-safe, read-only full audit."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: Literal["ABSENT", "VALID", "INVALID", "PENDING"]
    present: StrictBool
    valid: StrictBool
    reason_codes: tuple[StrictStr, ...] = ()
    state_count: StrictInt = Field(ge=0)
    event_count: StrictInt = Field(ge=0)
    ingress_count: StrictInt = Field(ge=0)
    pending_ingress_count: StrictInt = Field(ge=0)
    coordinator_result_count: StrictInt = Field(ge=0)
    receipt_count: StrictInt = Field(ge=0)
    outbox_count: StrictInt = Field(ge=0)
    undelivered_outbox_count: StrictInt = Field(ge=0)
    checkpoint_count: StrictInt = Field(ge=0)
    activation_count: StrictInt = Field(default=0, ge=0)
    head_state_id: StrictStr | None = None
    head_state_version: StrictInt | None = Field(default=None, ge=0)
    head_event_id: StrictStr | None = None
    head_event_sequence: StrictInt = Field(default=0, ge=0)


class EntityRestartSnapshot(BaseModel):
    """Validated material needed to reconstruct the coordinator after restart."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    state: SE6EntityState
    historical_events: tuple[EntityEvent, ...]
    pending_ingress: tuple[EntityIngressRecord, ...]
    undelivered_outbox: tuple[EntityOutboxRecord, ...]
    latest_receipt: EntityCommitReceipt
    latest_checkpoint: EntityCheckpointRecord
    activation_record: EntityActivationRecord | None = None
    activation_evidence: EntityActivationEvidenceBundle | None = None
    activation_receipt: EntityCommitReceipt | None = None

    @model_validator(mode="after")
    def activation_material_is_complete(self) -> EntityRestartSnapshot:
        supplied = (
            self.activation_record is not None,
            self.activation_evidence is not None,
            self.activation_receipt is not None,
        )
        if any(supplied) and not all(supplied):
            raise ValueError("activation reconstruction material must be complete")
        if (
            self.activation_receipt is not None
            and self.activation_receipt.commit_kind != "ACTIVATION"
        ):
            raise ValueError("activation receipt kind mismatch")
        return self


class EntityStateReceiptLineage(BaseModel):
    """Fully audited state and commit ancestry for evidence adapters."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    states: tuple[SE6EntityState, ...] = Field(min_length=1)
    receipts: tuple[EntityCommitReceipt, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def lineage_heads_match(self) -> EntityStateReceiptLineage:
        if (
            len(self.states) != len(self.receipts)
            or self.receipts[-1].state_after_id != self.states[-1].entity_state_id
            or self.receipts[-1].state_after_hash != self.states[-1].state_hash
        ):
            raise ValueError("Entity state and receipt lineage mismatch")
        return self


class _AuditSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    states: tuple[SE6EntityState, ...]
    events: tuple[EntityEvent, ...]
    ingresses: tuple[EntityIngressRecord, ...]
    pending_ingress_ids: tuple[StrictStr, ...]
    results: tuple[CoordinatorStepResult, ...]
    receipts: tuple[EntityCommitReceipt, ...]
    outbox: tuple[EntityOutboxRecord, ...]
    outbox_deliveries: tuple[EntityOutboxDeliveryRecord, ...]
    undelivered_outbox_ids: tuple[StrictStr, ...]
    checkpoints: tuple[EntityCheckpointRecord, ...]
    state_chain_hashes: tuple[StrictStr, ...]
    event_chain_hashes: tuple[StrictStr, ...]
    activation_record: EntityActivationRecord | None = None
    activation_evidence: EntityActivationEvidenceBundle | None = None
    verified_extension: bool = False


FaultInjector = Callable[[str], None]

_AUDIT_PROOF_VERSION = "se6-entity-full-sqlite-image-proof-v3"
# A warm renewal may join one already-required verification, never reuse an
# invalidated image. Cold reads and work exceeding this bound remain PENDING.
_WARM_POLL_VERIFICATION_WAIT_SECONDS = 2.0


@dataclass(frozen=True)
class _AuditedStateRow:
    fields: tuple[object, ...]
    state: SE6EntityState
    chain_hash: str
    size: int


class _StateRowValidationCache:
    """Bounded process-local memo of successful, byte-exact row validation.

    This never certifies a database image. Every audit still checks its schema,
    current rows, bindings, chains, foreign keys and head. Changed rows miss.
    """

    def __init__(self, *, max_bytes: int = 64 * 1024 * 1024) -> None:
        self.max_bytes = max_bytes
        self.size = 0
        self.rows: OrderedDict[tuple[object, ...], _AuditedStateRow] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, fields: tuple[object, ...]) -> _AuditedStateRow | None:
        with self.lock:
            return self.rows.get(fields)

    def retain(self, rows: Sequence[_AuditedStateRow]) -> None:
        with self.lock:
            for row in rows:
                if row.size > self.max_bytes:
                    continue
                previous = self.rows.pop(row.fields, None)
                if previous is not None:
                    self.size -= previous.size
                self.rows[row.fields] = row
                self.size += row.size
                while self.size > self.max_bytes:
                    _, removed = self.rows.popitem(last=False)
                    self.size -= removed.size


_state_row_audit: ContextVar[
    tuple[_StateRowValidationCache, list[_AuditedStateRow]] | None
] = ContextVar("se6_state_row_audit", default=None)


@dataclass(frozen=True)
class _VerifiedAuditSnapshot:
    """Process-local proof of a full SQLite read-transaction image, never authority.

    The digest covers ALL pages (historical rows, schema, triggers, indexes,
    queues and heads), not just a state version or filesystem timestamp.
    Only one successful immutable audit is retained per EntityStore instance.
    Runtime authority and presentation observations are always derived afresh.
    """
    subject: tuple[str, int, str, str]
    store_path: Path
    verified_at_utc: datetime
    snapshot: _AuditSnapshot
    inspection: tuple[
        EntityStoreIntegrityResult, EntityRestartSnapshot, EntityStateReceiptLineage
    ]


_AUDIT_TABLE_ORDER = {
    "entity_ingress": "queue_sequence", "entity_events": "event_sequence",
    "entity_states": "state_version", "entity_coordinator_results": "result_sequence",
    "entity_commit_receipts": "commit_sequence", "entity_activation_commits": "activation_sequence",
    "entity_ingress_consumptions": "consumption_sequence", "entity_outbox": "outbox_sequence",
    "entity_outbox_deliveries": "delivery_sequence", "entity_checkpoints": "checkpoint_sequence",
}


@dataclass(frozen=True)
class _VerifiedPrefix:
    proof: _VerifiedAuditSnapshot
    schema: tuple[tuple[object, ...], ...]
    # Only counts and digests are retained, never a second copy of row payloads.
    tables: tuple[tuple[str, int, bytes], ...]


_extension_base: ContextVar[_AuditSnapshot | None] = ContextVar("se6_verified_extension", default=None)
_audit_row_image: ContextVar[dict[str, list[sqlite3.Row]] | None] = ContextVar("se6_audit_row_image", default=None)


def _audit_rows(connection: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    rows = _audit_row_image.get()
    if rows is not None and table in rows:
        return rows[table]
    # Identifiers come only from this module's fixed table map.
    result = connection.execute(f"SELECT * FROM {table} ORDER BY {_AUDIT_TABLE_ORDER[table]}").fetchall()
    if rows is not None:
        rows[table] = result
    return result


def _row_digest(rows: Sequence[sqlite3.Row]) -> bytes:
    digest = hashlib.sha256()
    for row in rows:
        # A process-local, type-preserving byte encoding, NOT canonical Entity
        # serialization. Nothing is unpickled or persisted. Canonical validators
        # still run on every new/unverified record.
        encoded = pickle.dumps(tuple(row), protocol=5)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.digest()


def _schema_image(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    return tuple(tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,rootpage,sql FROM sqlite_schema ORDER BY type,name"))


def _capture_prefix(connection: sqlite3.Connection, proof: _VerifiedAuditSnapshot) -> _VerifiedPrefix:
    tables = []
    for table in _AUDIT_TABLE_ORDER:
        rows = _audit_rows(connection, table)
        tables.append((table, len(rows), _row_digest(rows)))
    return _VerifiedPrefix(proof, _schema_image(connection), tuple(tables))


def _audit_incremental(connection: sqlite3.Connection, prefix: _VerifiedPrefix) -> _AuditSnapshot:
    """Prove the exact old rows unchanged before validating their new suffixes.

    This still reads historical bytes to detect arbitrary external mutation.
    It does not parse, canonicalize, rehash canonical models or rerun their
    semantic validators. It grants no authority and changes no durable schema.
    """
    for table, count, digest in prefix.tables:
        rows = _audit_rows(connection, table)
        if len(rows) < count or _row_digest(rows[:count]) != digest:
            raise EntityStoreError("VERIFIED_HISTORY_PREFIX_CHANGED")
    proof = prefix.proof
    state = proof.snapshot.states[-1]
    receipt = proof.snapshot.receipts[-1]
    integrity, restart, lineage = proof.inspection
    state_row = _audit_rows(connection, "entity_states")[len(proof.snapshot.states) - 1]
    if (restart.state is not state or restart.latest_receipt is not receipt
            or lineage.states[-1] is not state or lineage.receipts[-1] is not receipt
            or integrity.head_state_id != state.entity_state_id
            or state_row["entity_state_id"] != state.entity_state_id
            or state_row["state_hash"] != state.state_hash
            or state_row["identity_state_id"] != state.identity.identity_state_id
            or state_row["instance_id"] != state.identity.instance_id
            or receipt.state_after_id != state.entity_state_id):
        raise EntityStoreError("VERIFIED_PREFIX_BINDING_MISMATCH")
    token = _extension_base.set(prefix.proof.snapshot)
    try:
        with read_span("entity_delta_audit"):
            read_count("incremental_audits")
            return _audit_connection_impl(connection)
    finally:
        _extension_base.reset(token)


def _audit_subject(connection: sqlite3.Connection) -> tuple[str, int, str, str]:
    with read_span("audit_subject_digest"):
        connection.execute("SELECT rootpage FROM sqlite_schema LIMIT 1").fetchone()
        try:
            image = connection.serialize()
        except MemoryError as exc:
            raise EntityStoreError("INTEGRITY_AUDIT_MEMORY_EXHAUSTED") from exc
        return (_AUDIT_PROOF_VERSION, ENTITY_STORE_SCHEMA_VERSION,
                ENTITY_STORE_POLICY_VERSION, hashlib.sha256(image).hexdigest())


class EntityStore:
    """One canonical SQLite head for one continuous SE6 entity identity."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        _test_only: bool = False,
        _fault_injector: FaultInjector | None = None,
    ) -> None:
        if path is not None and not _test_only:
            raise ValueError("explicit entity database paths are test-only")
        if _test_only and path is None:
            raise ValueError("test entity store requires an explicit path")
        if _fault_injector is not None and not _test_only:
            raise ValueError("entity store fault injection is test-only")
        self.path = (
            Path(path).expanduser().resolve(strict=False)
            if path is not None
            else default_entity_database_path()
        )
        self.test_only = _test_only
        self._fault_injector = _fault_injector
        self._verified_audit: _VerifiedAuditSnapshot | None = None
        self._verified_prefix: _VerifiedPrefix | None = None
        self._audit_condition = threading.Condition()
        self._audit_in_flight = False
        self._audit_failure: tuple[tuple[str, int, str, str], str] | None = None
        self._state_row_validation = _StateRowValidationCache()
        if _test_only:
            production = default_entity_database_path()
            if (
                self.path == production
                or self.path == production.parent
                or production.parent in self.path.parents
            ):
                raise ValueError("test entity store cannot alias production state")
        repository = Path(__file__).resolve(strict=False).parents[1]
        if self.path == repository or repository in self.path.parents:
            raise ValueError("entity database must remain outside the repository")

    @classmethod
    def for_testing(
        cls,
        path: Path,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> EntityStore:
        return cls(path, _test_only=True, _fault_injector=fault_injector)

    @property
    def database_path(self) -> Path:
        return self.path

    @property
    def is_test_store(self) -> bool:
        return self.test_only

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            uri = f"{self.path.as_uri()}?mode=ro"
            connection = sqlite3.connect(uri, timeout=5, isolation_level=None, uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(self.path), timeout=5, isolation_level=None
            )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            if not read_only:
                connection.execute("PRAGMA synchronous=FULL")
            return connection
        except Exception:
            connection.close()
            raise

    def initialize_schema(self) -> None:
        """Create the schema without creating any entity state."""

        connection = self._connect()
        try:
            connection.executescript(_SCHEMA_SQL)
            row = connection.execute(
                "SELECT schema_version, policy_version FROM entity_store_schema "
                "WHERE singleton=1"
            ).fetchone()
            if row is None or tuple(row) != (
                ENTITY_STORE_SCHEMA_VERSION,
                ENTITY_STORE_POLICY_VERSION,
            ):
                raise EntityStoreError("SCHEMA_VERSION_MISMATCH")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.DatabaseError:
                pass
            raise
        finally:
            connection.close()

    def commit_genesis(
        self,
        *,
        state: SE6EntityState,
        runtime_session_id: str,
        committed_at_utc: datetime,
    ) -> EntityCommitReceipt:
        """Atomically establish the only genesis state and canonical head."""

        committed_at = _utc(committed_at_utc, "committed_at_utc")
        _validate_reference(runtime_session_id, "runtime_session_id")
        if (
            state.state_version != 0
            or state.previous_entity_state_id is not None
            or state.event_sequence != 0
            or state.event_head_id is not None
        ):
            raise EntityStoreError("GENESIS_STATE_INVALID")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM entity_head").fetchone() is not None:
                raise EntityStoreError("GENESIS_ALREADY_EXISTS")
            if connection.execute("SELECT 1 FROM entity_states").fetchone() is not None:
                raise EntityStoreError("ORPHANED_STATE_WITHOUT_HEAD")
            state_chain_hash = _state_chain_hash(state, _ZERO_HASH)
            _insert_state(
                connection,
                state,
                previous_state_chain_hash=_ZERO_HASH,
                state_chain_hash=state_chain_hash,
                committed_at_utc=committed_at,
            )
            self._fault("after_state_insert")
            receipt = _make_receipt(
                commit_sequence=1,
                commit_kind="GENESIS",
                runtime_session_id=runtime_session_id,
                state_before_id=None,
                state_after=state,
                events=(),
                processed_ingress_id=None,
                coordinator_result_id=None,
                queued_ingress_ids=(),
                outbox_ids=(),
                previous_receipt_hash=_ZERO_HASH,
                committed_at_utc=committed_at,
            )
            _insert_receipt(connection, receipt)
            checkpoint = _make_checkpoint(
                checkpoint_sequence=1,
                state=state,
                state_chain_hash=state_chain_hash,
                event_chain_hash=_ZERO_HASH,
                receipt=receipt,
                created_at_utc=committed_at,
            )
            _insert_checkpoint(connection, checkpoint)
            connection.execute(
                """
                INSERT INTO entity_head(
                    singleton, entity_state_id, state_version, state_chain_hash,
                    event_head_id, event_sequence, event_chain_hash,
                    receipt_id, receipt_hash, commit_sequence, checkpoint_id
                ) VALUES(1,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    state.entity_state_id,
                    state.state_version,
                    state_chain_hash,
                    None,
                    0,
                    _ZERO_HASH,
                    receipt.receipt_id,
                    receipt.receipt_hash,
                    1,
                    checkpoint.checkpoint_id,
                ),
            )
            self._fault("before_commit")
            connection.execute("COMMIT")
            return receipt
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def enqueue(
        self,
        *,
        draft: EntityEventDraft,
        ingress_key: str,
        enqueued_at_utc: datetime,
        final_admission: Callable[..., datetime] | None = None,
    ) -> EntityIngressRecord:
        """Append one ingress, rejecting key reuse and content replay."""

        at = _utc(enqueued_at_utc, "enqueued_at_utc")
        if draft.event_type is EventType.INTERACTIVE_PROOF_CONTROL:
            raise EntityStoreError("INTERACTIVE_PROOF_AUTHORITY_REQUIRED")
        if draft.event_type is EventType.LOCAL_EVENT_BUDGET_RENEWAL:
            raise EntityStoreError("LOCAL_EVENT_BUDGET_AUTHORITY_REQUIRED")
        _validate_reference(ingress_key, "ingress_key")
        if ingress_key.startswith("derived:"):
            raise EntityStoreError("INGRESS_KEY_RESERVED")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            audited = self._audit_current_connection(connection)
            # Same BEGIN IMMEDIATE snapshot as insertion. No Entity reads from
            # the callback: they would reopen the transaction being authorized.
            if final_admission is not None:
                at = _utc(final_admission(
                    state=audited.states[-1], receipt=audited.receipts[-1],
                    pending_count=len(audited.pending_ingress_ids),
                    activation_record=audited.activation_record,
                ), "final_admission_time")
            record = _insert_ingress(connection, draft, ingress_key, at)
            self._fault("after_ingress_insert")
            connection.execute("COMMIT")
            return record
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def commit_activation(
        self,
        *,
        expected_state_id: str,
        expected_state_version: int,
        runtime_session_id: str,
        activation_record: EntityActivationRecord,
        activation_evidence: EntityActivationEvidenceBundle,
        lifecycle: LifecycleView,
        shared_metabolism: SharedMetabolismSnapshot,
        occurred_at_utc: datetime,
        committed_at_utc: datetime,
    ) -> EntityCommitReceipt:
        """CAS the first LOCAL_LIVE state from an exact VERIFIED record.

        Evaluation remains pure and effect-free.  This separate commit is the
        durable bridge required by the activation record and never fabricates
        a coordinator result, ingress, approval, or external effect.
        """

        occurred_at = _utc(occurred_at_utc, "occurred_at_utc")
        committed_at = _utc(committed_at_utc, "committed_at_utc")
        if committed_at < occurred_at:
            raise EntityStoreError("ACTIVATION_TIME_INVALID")
        _validate_reference(runtime_session_id, "runtime_session_id")
        if runtime_session_id != activation_evidence.runtime_evidence.runtime_session_id:
            raise EntityStoreError("ACTIVATION_RUNTIME_BINDING_MISMATCH")
        if evaluate_entity_activation(activation_evidence) != activation_record:
            raise EntityStoreError("ACTIVATION_RECORD_EVIDENCE_MISMATCH")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            audit = self._audit_current_connection(connection)
            head = connection.execute(
                "SELECT * FROM entity_head WHERE singleton=1"
            ).fetchone()
            if head is None:
                raise EntityStoreError("STORE_HAS_NO_GENESIS")
            if (
                head["entity_state_id"] != expected_state_id
                or head["state_version"] != expected_state_version
            ):
                raise EntityStoreError("STALE_ENTITY_HEAD")
            state_before = audit.states[-1]
            if state_before.operating_mode is not EntityOperatingMode.SHADOW:
                raise EntityStoreError("ACTIVATION_REQUIRES_SHADOW_HEAD")
            references = activation_basis_references(
                activation_record, activation_evidence
            )
            draft = EntityEventDraft(
                event_type=EventType.LIFECYCLE,
                occurred_at_utc=occurred_at,
                originating_loop=LoopName.COORDINATOR,
                source=EventEndpoint(
                    kind=EventSourceKind.SYSTEM,
                    identifier="LOCAL_ENTITY_ACTIVATION_COMMITTER",
                ),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                relation="activates_verified_local_entity",
                provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
                epistemic_status=EpistemicStatus.VERIFIED,
                authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id=activation_record.activation_record_id,
                causal_id=state_before.event_head_id,
                parent_event_id=state_before.event_head_id,
                sensitivity=SensitivityClassification.INTERNAL,
                persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=LifecyclePayload(
                    signal=LifecycleSignal.STATE_REPORTED,
                    prior_state=EntityOperatingMode.SHADOW.value,
                    projected_state=EntityOperatingMode.LOCAL_LIVE.value,
                    reason=(
                        "The exact VERIFIED activation record passed every "
                        "local entity go-live evidence gate."
                    ),
                    controller_authoritative=lifecycle.controller_authoritative,
                    evidence_references=references,
                ),
            )
            event = create_entity_event(
                sequence=state_before.event_sequence + 1, draft=draft
            )
            state_after = build_first_local_live_entity_state(
                state_before,
                activation_record=activation_record,
                activation_evidence=activation_evidence,
                expected_state_version=expected_state_version,
                event_head_id=event.event_id,
                event_sequence=event.sequence,
                updated_at_utc=occurred_at,
                lifecycle=lifecycle,
                shared_metabolism=shared_metabolism,
            )
            _validate_activation_state_continuity(state_before, state_after)

            event_chain_hash = _event_chain_hash(
                event, head["event_chain_hash"]
            )
            connection.execute(
                """
                INSERT INTO entity_events(
                    event_sequence,event_id,parent_event_id,event_json,
                    content_hash,previous_event_chain_hash,event_chain_hash,
                    occurred_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    event.sequence,
                    event.event_id,
                    event.parent_event_id,
                    _model_json(event),
                    canonical_sha256(event),
                    head["event_chain_hash"],
                    event_chain_hash,
                    _time_text(event.occurred_at_utc),
                ),
            )
            self._fault("after_event_insert")
            state_chain_hash = _state_chain_hash(
                state_after, head["state_chain_hash"]
            )
            _insert_state(
                connection,
                state_after,
                previous_state_chain_hash=head["state_chain_hash"],
                state_chain_hash=state_chain_hash,
                committed_at_utc=committed_at,
            )
            self._fault("after_state_insert")
            receipt = _make_receipt(
                commit_sequence=head["commit_sequence"] + 1,
                commit_kind="ACTIVATION",
                runtime_session_id=runtime_session_id,
                state_before_id=state_before.entity_state_id,
                state_after=state_after,
                events=(event,),
                processed_ingress_id=None,
                coordinator_result_id=None,
                queued_ingress_ids=(),
                outbox_ids=(),
                previous_receipt_hash=head["receipt_hash"],
                committed_at_utc=committed_at,
            )
            _insert_receipt(connection, receipt)
            connection.execute(
                """
                INSERT INTO entity_activation_commits(
                    activation_sequence,activation_record_id,
                    activation_record_hash,evidence_bundle_id,
                    evidence_bundle_hash,record_json,evidence_json,
                    record_content_hash,evidence_content_hash,state_before_id,
                    state_after_id,receipt_id,committed_at_utc
                ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    activation_record.activation_record_id,
                    activation_record.activation_record_hash,
                    activation_evidence.evidence_bundle_id,
                    activation_evidence.evidence_bundle_hash,
                    _model_json(activation_record),
                    _model_json(activation_evidence),
                    canonical_sha256(activation_record),
                    canonical_sha256(activation_evidence),
                    state_before.entity_state_id,
                    state_after.entity_state_id,
                    receipt.receipt_id,
                    _time_text(committed_at),
                ),
            )
            checkpoint = _make_checkpoint(
                checkpoint_sequence=receipt.commit_sequence,
                state=state_after,
                state_chain_hash=state_chain_hash,
                event_chain_hash=event_chain_hash,
                receipt=receipt,
                created_at_utc=committed_at,
            )
            _insert_checkpoint(connection, checkpoint)
            self._fault("before_head_cas")
            cursor = connection.execute(
                """
                UPDATE entity_head SET
                    entity_state_id=?, state_version=?, state_chain_hash=?,
                    event_head_id=?, event_sequence=?, event_chain_hash=?,
                    receipt_id=?, receipt_hash=?, commit_sequence=?, checkpoint_id=?
                WHERE singleton=1 AND entity_state_id=? AND state_version=?
                """,
                (
                    state_after.entity_state_id,
                    state_after.state_version,
                    state_chain_hash,
                    state_after.event_head_id,
                    state_after.event_sequence,
                    event_chain_hash,
                    receipt.receipt_id,
                    receipt.receipt_hash,
                    receipt.commit_sequence,
                    checkpoint.checkpoint_id,
                    expected_state_id,
                    expected_state_version,
                ),
            )
            if cursor.rowcount != 1:
                raise EntityStoreError("STALE_ENTITY_HEAD")
            self._fault("before_commit")
            connection.execute("COMMIT")
            return receipt
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def commit_runtime_detach(
        self,
        *,
        expected_state_id: str,
        expected_state_version: int,
        expected_runtime_session_id: str,
        lifecycle: LifecycleView,
        verified_runtime_receipt_references: Sequence[str],
        occurred_at_utc: datetime,
        committed_at_utc: datetime,
    ) -> EntityCommitReceipt:
        """Durably detach LOCAL_LIVE identity from a verified stopped runtime.

        The caller must supply terminal runtime receipts; this store neither
        stops a controller nor infers that one disappeared.  The transition
        preserves activation, identity, authority, metabolism, and network
        isolation while recording the exact fail-closed lifecycle posture.
        """

        occurred_at = _utc(occurred_at_utc, "occurred_at_utc")
        committed_at = _utc(committed_at_utc, "committed_at_utc")
        if committed_at < occurred_at:
            raise EntityStoreError("RUNTIME_DETACH_TIME_INVALID")
        _validate_reference(
            expected_runtime_session_id, "expected_runtime_session_id"
        )
        references = tuple(verified_runtime_receipt_references)
        if (
            len(references) < 2
            or len(references) > 32
            or len(set(references)) != len(references)
        ):
            raise EntityStoreError("RUNTIME_DETACH_EVIDENCE_INVALID")
        for reference in references:
            _validate_reference(reference, "verified_runtime_receipt_reference")
        _validate_detach_lifecycle(lifecycle, references, occurred_at)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            audit = self._audit_current_connection(connection)
            head = connection.execute(
                "SELECT * FROM entity_head WHERE singleton=1"
            ).fetchone()
            if head is None:
                raise EntityStoreError("STORE_HAS_NO_GENESIS")
            if (
                head["entity_state_id"] != expected_state_id
                or head["state_version"] != expected_state_version
            ):
                raise EntityStoreError("STALE_ENTITY_HEAD")
            previous_receipt = audit.receipts[-1]
            if previous_receipt.runtime_session_id != expected_runtime_session_id:
                raise EntityStoreError("CURRENT_RUNTIME_BINDING_MISMATCH")
            state_before = audit.states[-1]
            if state_before.operating_mode is not EntityOperatingMode.LOCAL_LIVE:
                raise EntityStoreError("RUNTIME_DETACH_REQUIRES_LOCAL_LIVE")
            if not _lifecycle_is_present_capable(state_before.lifecycle):
                raise EntityStoreError("RUNTIME_DETACH_REQUIRES_ACTIVE_RUNTIME")

            emergency_stop = (
                lifecycle.emergency_stop is EmergencyStopState.TRIGGERED
            )
            draft = EntityEventDraft(
                event_type=EventType.STOP if emergency_stop else EventType.PAUSE,
                occurred_at_utc=occurred_at,
                originating_loop=LoopName.COORDINATOR,
                source=EventEndpoint(
                    kind=EventSourceKind.SYSTEM,
                    identifier="LOCAL_RUNTIME_DETACH_COMMITTER",
                ),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                relation="binds_verified_runtime_detach",
                provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
                epistemic_status=EpistemicStatus.VERIFIED,
                authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id=f"runtime-detach:{expected_runtime_session_id}",
                causal_id=state_before.event_head_id,
                parent_event_id=state_before.event_head_id,
                sensitivity=SensitivityClassification.INTERNAL,
                persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=LifecyclePayload(
                    signal=(
                        LifecycleSignal.STOP
                        if emergency_stop
                        else LifecycleSignal.PAUSE
                    ),
                    prior_state=state_before.lifecycle.durable_state.value,
                    projected_state=lifecycle.durable_state.value,
                    reason=(
                        "Verified emergency-stop receipts stopped local entity "
                        "processing while preserving its durable identity."
                        if emergency_stop
                        else "Verified terminal runtime receipts detach the durable "
                        "entity identity from process-local controller authority."
                    ),
                    controller_authoritative=False,
                    evidence_references=references,
                ),
            )
            event = create_entity_event(
                sequence=state_before.event_sequence + 1, draft=draft
            )
            material = {
                name: getattr(state_before, name)
                for name in state_before.__class__.model_fields
                if name not in {"entity_state_id", "state_hash"}
            }
            material.update(
                {
                    "previous_entity_state_id": state_before.entity_state_id,
                    "state_version": state_before.state_version + 1,
                    "lifecycle": lifecycle,
                    "event_head_id": event.event_id,
                    "event_sequence": event.sequence,
                    "updated_at_utc": occurred_at,
                }
            )
            state_after = create_entity_state(**material)
            _validate_detach_state_continuity(state_before, state_after)

            event_chain_hash = _event_chain_hash(event, head["event_chain_hash"])
            connection.execute(
                """
                INSERT INTO entity_events(
                    event_sequence,event_id,parent_event_id,event_json,
                    content_hash,previous_event_chain_hash,event_chain_hash,
                    occurred_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    event.sequence,
                    event.event_id,
                    event.parent_event_id,
                    _model_json(event),
                    canonical_sha256(event),
                    head["event_chain_hash"],
                    event_chain_hash,
                    _time_text(event.occurred_at_utc),
                ),
            )
            self._fault("after_event_insert")
            state_chain_hash = _state_chain_hash(
                state_after, head["state_chain_hash"]
            )
            _insert_state(
                connection,
                state_after,
                previous_state_chain_hash=head["state_chain_hash"],
                state_chain_hash=state_chain_hash,
                committed_at_utc=committed_at,
            )
            self._fault("after_state_insert")
            receipt = _make_receipt(
                commit_sequence=head["commit_sequence"] + 1,
                commit_kind="RUNTIME_DETACH",
                runtime_session_id=expected_runtime_session_id,
                state_before_id=state_before.entity_state_id,
                state_after=state_after,
                events=(event,),
                processed_ingress_id=None,
                coordinator_result_id=None,
                queued_ingress_ids=(),
                outbox_ids=(),
                previous_receipt_hash=head["receipt_hash"],
                committed_at_utc=committed_at,
            )
            _insert_receipt(connection, receipt)
            checkpoint = _make_checkpoint(
                checkpoint_sequence=receipt.commit_sequence,
                state=state_after,
                state_chain_hash=state_chain_hash,
                event_chain_hash=event_chain_hash,
                receipt=receipt,
                created_at_utc=committed_at,
            )
            _insert_checkpoint(connection, checkpoint)
            self._fault("before_head_cas")
            cursor = connection.execute(
                """
                UPDATE entity_head SET
                    entity_state_id=?, state_version=?, state_chain_hash=?,
                    event_head_id=?, event_sequence=?, event_chain_hash=?,
                    receipt_id=?, receipt_hash=?, commit_sequence=?, checkpoint_id=?
                WHERE singleton=1 AND entity_state_id=? AND state_version=?
                """,
                (
                    state_after.entity_state_id,
                    state_after.state_version,
                    state_chain_hash,
                    state_after.event_head_id,
                    state_after.event_sequence,
                    event_chain_hash,
                    receipt.receipt_id,
                    receipt.receipt_hash,
                    receipt.commit_sequence,
                    checkpoint.checkpoint_id,
                    expected_state_id,
                    expected_state_version,
                ),
            )
            if cursor.rowcount != 1:
                raise EntityStoreError("STALE_ENTITY_HEAD")
            self._fault("before_commit")
            connection.execute("COMMIT")
            return receipt
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def commit_runtime_rebind(
        self,
        *,
        expected_state_id: str,
        expected_state_version: int,
        expected_previous_runtime_session_id: str,
        runtime_session_id: str,
        lifecycle: LifecycleView,
        verified_runtime_receipt_references: Sequence[str],
        occurred_at_utc: datetime,
        committed_at_utc: datetime,
    ) -> EntityCommitReceipt:
        """Bind an existing LOCAL_LIVE entity to a verified successor runtime.

        This method does not discover, authenticate, or infer controller
        authority.  Its caller must independently validate the supplied
        runtime receipts.  The store requires and binds that evidence, then
        performs one narrow lifecycle-only CAS transition.
        """

        occurred_at = _utc(occurred_at_utc, "occurred_at_utc")
        committed_at = _utc(committed_at_utc, "committed_at_utc")
        if committed_at < occurred_at:
            raise EntityStoreError("RUNTIME_REBIND_TIME_INVALID")
        _validate_reference(
            expected_previous_runtime_session_id,
            "expected_previous_runtime_session_id",
        )
        _validate_reference(runtime_session_id, "runtime_session_id")
        if runtime_session_id == expected_previous_runtime_session_id:
            raise EntityStoreError("RUNTIME_SESSION_NOT_ADVANCING")
        references = tuple(verified_runtime_receipt_references)
        if len(references) < 2 or len(references) > 32 or len(set(references)) != len(references):
            raise EntityStoreError("RUNTIME_REBIND_EVIDENCE_INVALID")
        for reference in references:
            _validate_reference(reference, "verified_runtime_receipt_reference")
        _validate_rebind_lifecycle(lifecycle, references, occurred_at)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            audit = self._audit_current_connection(connection)
            head = connection.execute(
                "SELECT * FROM entity_head WHERE singleton=1"
            ).fetchone()
            if head is None:
                raise EntityStoreError("STORE_HAS_NO_GENESIS")
            if (
                head["entity_state_id"] != expected_state_id
                or head["state_version"] != expected_state_version
            ):
                raise EntityStoreError("STALE_ENTITY_HEAD")
            previous_receipt = audit.receipts[-1]
            if (
                previous_receipt.runtime_session_id
                != expected_previous_runtime_session_id
            ):
                raise EntityStoreError("PREVIOUS_RUNTIME_BINDING_MISMATCH")
            state_before = audit.states[-1]
            if state_before.operating_mode is not EntityOperatingMode.LOCAL_LIVE:
                raise EntityStoreError("RUNTIME_REBIND_REQUIRES_LOCAL_LIVE")

            draft = EntityEventDraft(
                event_type=EventType.RECOVERY,
                occurred_at_utc=occurred_at,
                originating_loop=LoopName.COORDINATOR,
                source=EventEndpoint(
                    kind=EventSourceKind.SYSTEM,
                    identifier="LOCAL_RUNTIME_RECONCILER",
                ),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                relation="binds_verified_successor_runtime",
                provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
                epistemic_status=EpistemicStatus.VERIFIED,
                authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id=f"runtime-rebind:{runtime_session_id}",
                causal_id=state_before.event_head_id,
                parent_event_id=state_before.event_head_id,
                sensitivity=SensitivityClassification.INTERNAL,
                persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=LifecyclePayload(
                    signal=LifecycleSignal.RECOVERED,
                    prior_state=state_before.lifecycle.durable_state.value,
                    projected_state=lifecycle.durable_state.value,
                    reason=(
                        "Verified successor runtime receipts establish fresh "
                        "process-local controller authority."
                    ),
                    controller_authoritative=True,
                    evidence_references=references,
                ),
            )
            event = create_entity_event(
                sequence=state_before.event_sequence + 1, draft=draft
            )
            material = {
                name: getattr(state_before, name)
                for name in state_before.__class__.model_fields
                if name not in {"entity_state_id", "state_hash"}
            }
            material.update(
                {
                    "previous_entity_state_id": state_before.entity_state_id,
                    "state_version": state_before.state_version + 1,
                    "lifecycle": lifecycle,
                    "event_head_id": event.event_id,
                    "event_sequence": event.sequence,
                    "updated_at_utc": occurred_at,
                }
            )
            state_after = create_entity_state(**material)
            _validate_rebind_state_continuity(state_before, state_after)

            event_chain_hash = _event_chain_hash(
                event, head["event_chain_hash"]
            )
            connection.execute(
                """
                INSERT INTO entity_events(
                    event_sequence,event_id,parent_event_id,event_json,
                    content_hash,previous_event_chain_hash,event_chain_hash,
                    occurred_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    event.sequence,
                    event.event_id,
                    event.parent_event_id,
                    _model_json(event),
                    canonical_sha256(event),
                    head["event_chain_hash"],
                    event_chain_hash,
                    _time_text(event.occurred_at_utc),
                ),
            )
            self._fault("after_event_insert")
            state_chain_hash = _state_chain_hash(
                state_after, head["state_chain_hash"]
            )
            _insert_state(
                connection,
                state_after,
                previous_state_chain_hash=head["state_chain_hash"],
                state_chain_hash=state_chain_hash,
                committed_at_utc=committed_at,
            )
            self._fault("after_state_insert")
            receipt = _make_receipt(
                commit_sequence=head["commit_sequence"] + 1,
                commit_kind="RUNTIME_REBIND",
                runtime_session_id=runtime_session_id,
                state_before_id=state_before.entity_state_id,
                state_after=state_after,
                events=(event,),
                processed_ingress_id=None,
                coordinator_result_id=None,
                queued_ingress_ids=(),
                outbox_ids=(),
                previous_receipt_hash=head["receipt_hash"],
                committed_at_utc=committed_at,
            )
            _insert_receipt(connection, receipt)
            checkpoint = _make_checkpoint(
                checkpoint_sequence=receipt.commit_sequence,
                state=state_after,
                state_chain_hash=state_chain_hash,
                event_chain_hash=event_chain_hash,
                receipt=receipt,
                created_at_utc=committed_at,
            )
            _insert_checkpoint(connection, checkpoint)
            self._fault("before_head_cas")
            cursor = connection.execute(
                """
                UPDATE entity_head SET
                    entity_state_id=?, state_version=?, state_chain_hash=?,
                    event_head_id=?, event_sequence=?, event_chain_hash=?,
                    receipt_id=?, receipt_hash=?, commit_sequence=?, checkpoint_id=?
                WHERE singleton=1 AND entity_state_id=? AND state_version=?
                """,
                (
                    state_after.entity_state_id,
                    state_after.state_version,
                    state_chain_hash,
                    state_after.event_head_id,
                    state_after.event_sequence,
                    event_chain_hash,
                    receipt.receipt_id,
                    receipt.receipt_hash,
                    receipt.commit_sequence,
                    checkpoint.checkpoint_id,
                    expected_state_id,
                    expected_state_version,
                ),
            )
            if cursor.rowcount != 1:
                raise EntityStoreError("STALE_ENTITY_HEAD")
            self._fault("before_commit")
            connection.execute("COMMIT")
            return receipt
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def commit_step(
        self,
        *,
        expected_state_id: str,
        expected_state_version: int,
        ingress_id: str | None,
        state_after: SE6EntityState | None,
        events: Sequence[EntityEvent],
        result: CoordinatorStepResult | None,
        runtime_session_id: str,
        committed_at_utc: datetime,
        queued_drafts: Sequence[EntityEventDraft] = (),
        _renewal_draft: EntityEventDraft | None = None,
        _renewal_authority_check: Callable[[], None] | None = None,
        _proof_draft: EntityEventDraft | None = None,
        _proof_authority_check: Callable[[], None] | None = None,
    ) -> EntityCommitReceipt:
        """Atomically CAS one reducer step and every durable side projection."""

        committed_at = _utc(committed_at_utc, "committed_at_utc")
        _validate_reference(runtime_session_id, "runtime_session_id")
        if expected_state_version < 0:
            raise EntityStoreError("EXPECTED_STATE_VERSION_INVALID")
        event_delta = tuple(events)
        queued_delta = tuple(queued_drafts)
        if any(item.event_type is EventType.INTERACTIVE_PROOF_CONTROL for item in event_delta):
            raise EntityStoreError("INTERACTIVE_PROOF_AUTHORITY_REQUIRED")
        if any(item.event_type is EventType.INTERACTIVE_PROOF_CONTROL for item in queued_delta):
            raise EntityStoreError("INTERACTIVE_PROOF_AUTHORITY_REQUIRED")
        if any(item.event_type is EventType.LOCAL_EVENT_BUDGET_RENEWAL for item in queued_delta):
            raise EntityStoreError("LOCAL_EVENT_BUDGET_AUTHORITY_REQUIRED")
        if not event_delta and _renewal_draft is None and _proof_draft is None:
            raise EntityStoreError("STEP_EVENT_DELTA_EMPTY")
        if (_renewal_draft is None) != (_renewal_authority_check is None):
            raise EntityStoreError("LOCAL_EVENT_BUDGET_AUTHORITY_REQUIRED")
        if ((_proof_draft is None) != (_proof_authority_check is None)
                or _proof_draft is not None and _renewal_draft is not None):
            raise EntityStoreError("INTERACTIVE_PROOF_AUTHORITY_REQUIRED")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            audit = self._audit_current_connection(connection)
            head = connection.execute("SELECT * FROM entity_head WHERE singleton=1").fetchone()
            if head is None:
                raise EntityStoreError("STORE_HAS_NO_GENESIS")
            if (
                head["entity_state_id"] != expected_state_id
                or head["state_version"] != expected_state_version
            ):
                raise EntityStoreError("STALE_ENTITY_HEAD")
            state_before = audit.states[-1]
            if _proof_draft is not None:
                from .interactive_entity_proof import build_step
                if ingress_id is not None or event_delta or result is not None or state_after is not None or queued_delta:
                    raise EntityStoreError("INTERACTIVE_PROOF_SCOPE_INVALID")
                # Errors roll back all ledger/queue work. The runtime can record
                # an attributable FAIL in a separate authorized control commit.
                event_delta, state_after, result = build_step(state_before, _proof_draft, audit.events, audit.states)
                assert _proof_authority_check is not None
                _proof_authority_check()
                ingress = _insert_ingress(connection, _proof_draft,
                    "interactive-proof:" + canonical_sha256(_proof_draft), committed_at)
            elif _renewal_draft is not None:
                from .entity_event_budget import build_renewal_step
                from .entity_events import LocalEventBudgetRenewalPayload
                if ingress_id is not None or event_delta or result is not None or state_after is not None or queued_delta:
                    raise EntityStoreError("LOCAL_EVENT_BUDGET_SCOPE_INVALID")
                try:
                    event, state_after, result = build_renewal_step(state_before, _renewal_draft, audit.events)
                except ValueError as exc:
                    raise EntityStoreError(str(exc)) from exc
                event_delta = (event,)
                assert _renewal_authority_check is not None
                _renewal_authority_check()  # Fresh owner/runtime check after the audit, before any write.
                assert isinstance(_renewal_draft.payload, LocalEventBudgetRenewalPayload)
                ingress = _insert_ingress(connection, _renewal_draft,
                    "local-event-budget:" + _renewal_draft.payload.request_id, committed_at)
            else:
                if ingress_id is None or state_after is None or result is None:
                    raise EntityStoreError("STEP_MATERIAL_REQUIRED")
                ingress = _load_ingress_for_commit(connection, ingress_id)
                if ingress.draft.event_type is EventType.INTERACTIVE_PROOF_CONTROL:
                    raise EntityStoreError("INTERACTIVE_PROOF_AUTHORITY_REQUIRED")
                if ingress.draft.event_type is EventType.LOCAL_EVENT_BUDGET_RENEWAL:
                    raise EntityStoreError("LOCAL_EVENT_BUDGET_AUTHORITY_REQUIRED")
                pending_ids = set(audit.pending_ingress_ids)
                pending_head = min(
                    (item for item in audit.ingresses if item.ingress_id in pending_ids),
                    key=lambda item: item.queue_sequence,
                    default=None,
                )
                if pending_head is None:
                    raise EntityStoreError("INGRESS_FIFO_HEAD_MISSING")
                if ingress.ingress_id != pending_head.ingress_id:
                    raise EntityStoreError("EARLIER_INGRESS_PENDING")
            assert state_after is not None and result is not None
            _validate_step_contract(
                state_before=state_before,
                state_after=state_after,
                ingress=ingress,
                events=event_delta,
                result=result,
            )

            previous_event_chain_hash = head["event_chain_hash"]
            event_chain_hash = previous_event_chain_hash
            for event in event_delta:
                next_chain_hash = _event_chain_hash(event, event_chain_hash)
                connection.execute(
                    """
                    INSERT INTO entity_events(
                        event_sequence,event_id,parent_event_id,event_json,
                        content_hash,previous_event_chain_hash,event_chain_hash,
                        occurred_at_utc
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        event.sequence,
                        event.event_id,
                        event.parent_event_id,
                        _model_json(event),
                        canonical_sha256(event),
                        event_chain_hash,
                        next_chain_hash,
                        _time_text(event.occurred_at_utc),
                    ),
                )
                event_chain_hash = next_chain_hash
            self._fault("after_event_insert")

            state_chain_hash = _state_chain_hash(state_after, head["state_chain_hash"])
            _insert_state(
                connection,
                state_after,
                previous_state_chain_hash=head["state_chain_hash"],
                state_chain_hash=state_chain_hash,
                committed_at_utc=committed_at,
            )
            self._fault("after_state_insert")
            connection.execute(
                """
                INSERT INTO entity_coordinator_results(
                    result_sequence,result_id,state_before_id,state_after_id,
                    processed_event_id,result_json,content_hash,processed_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    connection.execute(
                        "SELECT COALESCE(MAX(result_sequence),0)+1 "
                        "FROM entity_coordinator_results"
                    ).fetchone()[0],
                    result.result_id,
                    result.state_before_id,
                    result.state_after_id,
                    result.processed_event_id,
                    _model_json(result),
                    canonical_sha256(result),
                    _time_text(result.processed_at_utc),
                ),
            )
            self._fault("after_result_insert")

            queued_records = []
            for index, draft in enumerate(queued_delta):
                draft_hash = canonical_sha256(draft)
                key = f"derived:{result.result_id}:{index}:{draft_hash}"
                queued_records.append(
                    _insert_ingress(connection, draft, key, committed_at)
                )
            outbox_records = []
            for intent in result.communication_intents:
                outbox_records.append(
                    _insert_outbox(
                        connection,
                        intent=intent,
                        result_id=result.result_id,
                        entity_state_id=state_after.entity_state_id,
                        created_at_utc=committed_at,
                    )
                )
            self._fault("after_projections_insert")

            receipt = _make_receipt(
                commit_sequence=head["commit_sequence"] + 1,
                commit_kind="STEP",
                runtime_session_id=runtime_session_id,
                state_before_id=state_before.entity_state_id,
                state_after=state_after,
                events=event_delta,
                processed_ingress_id=ingress.ingress_id,
                coordinator_result_id=result.result_id,
                queued_ingress_ids=tuple(item.ingress_id for item in queued_records),
                outbox_ids=tuple(item.outbox_id for item in outbox_records),
                previous_receipt_hash=head["receipt_hash"],
                committed_at_utc=committed_at,
            )
            _insert_receipt(connection, receipt)
            connection.execute(
                """
                INSERT INTO entity_ingress_consumptions(
                    ingress_id,processed_event_id,result_id,receipt_id,consumed_at_utc
                ) VALUES(?,?,?,?,?)
                """,
                (
                    ingress.ingress_id,
                    event_delta[0].event_id,
                    result.result_id,
                    receipt.receipt_id,
                    _time_text(committed_at),
                ),
            )
            checkpoint = _make_checkpoint(
                checkpoint_sequence=receipt.commit_sequence,
                state=state_after,
                state_chain_hash=state_chain_hash,
                event_chain_hash=event_chain_hash,
                receipt=receipt,
                created_at_utc=committed_at,
            )
            _insert_checkpoint(connection, checkpoint)
            self._fault("before_head_cas")
            cursor = connection.execute(
                """
                UPDATE entity_head SET
                    entity_state_id=?, state_version=?, state_chain_hash=?,
                    event_head_id=?, event_sequence=?, event_chain_hash=?,
                    receipt_id=?, receipt_hash=?, commit_sequence=?, checkpoint_id=?
                WHERE singleton=1 AND entity_state_id=? AND state_version=?
                """,
                (
                    state_after.entity_state_id,
                    state_after.state_version,
                    state_chain_hash,
                    state_after.event_head_id,
                    state_after.event_sequence,
                    event_chain_hash,
                    receipt.receipt_id,
                    receipt.receipt_hash,
                    receipt.commit_sequence,
                    checkpoint.checkpoint_id,
                    expected_state_id,
                    expected_state_version,
                ),
            )
            if cursor.rowcount != 1:
                raise EntityStoreError("STALE_ENTITY_HEAD")
            self._fault("before_commit")
            connection.execute("COMMIT")
            return receipt
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def commit_local_event_budget_renewal(
        self, *, expected_state_id: str, expected_state_version: int,
        runtime_session_id: str, draft: EntityEventDraft,
        committed_at_utc: datetime, final_authority_check: Callable[[], None],
    ) -> EntityCommitReceipt:
        """Append one exact authenticated control step atomically with its grant.

        No ordinary ingress is popped or reordered. The host owns authentication;
        normal enqueue/processing cannot invoke this renewal path.
        """
        if not callable(final_authority_check):
            raise EntityStoreError("LOCAL_EVENT_BUDGET_AUTHORITY_REQUIRED")
        return self.commit_step(expected_state_id=expected_state_id,
            expected_state_version=expected_state_version, ingress_id=None,
            state_after=None, events=(), result=None, runtime_session_id=runtime_session_id,
            committed_at_utc=committed_at_utc, _renewal_draft=draft,
            _renewal_authority_check=final_authority_check)

    def pending_ingress(self, *, limit: int = 256) -> tuple[EntityIngressRecord, ...]:
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        if not self.path.is_file():
            return ()
        connection = self._connect(read_only=True)
        try:
            audit = self._audit_current_connection(connection)
            pending = set(audit.pending_ingress_ids)
            return tuple(item for item in audit.ingresses if item.ingress_id in pending)[:limit]
        finally:
            connection.close()

    def acknowledge_outbox(
        self,
        *,
        outbox_id: str,
        delivery_reference: str,
        delivered_at_utc: datetime,
    ) -> EntityOutboxDeliveryRecord:
        """Record, but do not perform, one successful local delivery."""

        delivered_at = _utc(delivered_at_utc, "delivered_at_utc")
        if re.fullmatch(_OUTBOX_ID_PATTERN, outbox_id) is None:
            raise ValueError("outbox_id is not canonical")
        _validate_reference(delivery_reference, "delivery_reference")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._audit_current_connection(connection)
            if connection.execute(
                "SELECT 1 FROM entity_outbox WHERE outbox_id=?", (outbox_id,)
            ).fetchone() is None:
                raise EntityStoreError("OUTBOX_NOT_FOUND")
            existing_row = connection.execute(
                "SELECT * FROM entity_outbox_deliveries WHERE outbox_id=?",
                (outbox_id,),
            ).fetchone()
            if existing_row is not None:
                existing = _outbox_delivery_from_row(existing_row)
                if existing.delivery_reference == delivery_reference:
                    # A caller can safely retry the same confirmation after an
                    # ambiguous response.  Preserve the first backend-observed
                    # timestamp and return the original immutable record.
                    connection.execute("COMMIT")
                    return existing
                raise EntityStoreError("OUTBOX_DELIVERY_BINDING_MISMATCH")
            if connection.execute(
                "SELECT 1 FROM entity_outbox_deliveries "
                "WHERE delivery_reference=?",
                (delivery_reference,),
            ).fetchone() is not None:
                raise EntityStoreError("OUTBOX_DELIVERY_REFERENCE_REUSED")
            sequence = connection.execute(
                "SELECT COALESCE(MAX(delivery_sequence),0)+1 "
                "FROM entity_outbox_deliveries"
            ).fetchone()[0]
            material = {
                "schema_version": "se6-entity-outbox-delivery-v1",
                "delivery_sequence": sequence,
                "outbox_id": outbox_id,
                "delivery_reference": delivery_reference,
                "delivered_at_utc": delivered_at,
                "authority_effect": "NONE",
            }
            digest = canonical_sha256(material)
            record = EntityOutboxDeliveryRecord(
                delivery_id=f"entity_outbox_delivery_{digest}",
                delivery_hash=digest,
                **material,
            )
            connection.execute(
                """
                INSERT INTO entity_outbox_deliveries(
                    delivery_sequence,delivery_id,delivery_hash,outbox_id,
                    delivery_reference,delivery_json,delivered_at_utc
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    record.delivery_sequence,
                    record.delivery_id,
                    record.delivery_hash,
                    record.outbox_id,
                    record.delivery_reference,
                    _model_json(record),
                    _time_text(record.delivered_at_utc),
                ),
            )
            self._fault("after_outbox_delivery_insert")
            connection.execute("COMMIT")
            return record
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def record_outbox_delivery(
        self,
        *,
        outbox_id: str,
        delivery_reference: str,
        delivered_at_utc: datetime,
    ) -> EntityOutboxDeliveryRecord:
        """Backward-compatible spelling for :meth:`acknowledge_outbox`."""

        return self.acknowledge_outbox(
            outbox_id=outbox_id,
            delivery_reference=delivery_reference,
            delivered_at_utc=delivered_at_utc,
        )

    def audit_read_only(self, *, full: bool = False) -> EntityStoreIntegrityResult:
        """Validate every chain and binding without creating or changing state."""

        if not self.path.is_file():
            return EntityStoreIntegrityResult(
                status="ABSENT",
                present=False,
                valid=False,
                reason_codes=("STORE_ABSENT",),
                state_count=0,
                event_count=0,
                ingress_count=0,
                pending_ingress_count=0,
                coordinator_result_count=0,
                receipt_count=0,
                outbox_count=0,
                undelivered_outbox_count=0,
                checkpoint_count=0,
            )
        if full:
            connection = self._connect(read_only=True)
            try:
                connection.execute("BEGIN")
                # Explicit audit: no image proof, prefix reuse or row memo.
                return self._validated_inspection(_audit_connection(connection))[0]
            except EntityStoreError as exc:
                return _invalid_integrity(exc.code)
            except (ValueError, TypeError, sqlite3.DatabaseError):
                return _invalid_integrity("INTEGRITY_VALIDATION_FAILED")
            finally:
                connection.close()
        return self.inspect_read_only()[0]

    def reconstruct(self) -> EntityRestartSnapshot:
        """Return only fully audited state suitable for coordinator reconstruction."""

        if not self.path.is_file():
            raise EntityStoreError("STORE_ABSENT")
        audit, snapshot, _ = self.inspect_read_only()
        if not audit.valid or snapshot is None:
            raise EntityStoreError(audit.reason_codes[0] if audit.reason_codes else "INTEGRITY_VALIDATION_FAILED")
        return snapshot

    def verified_mirror_read_only(self, *, cognition_store=None, as_of_utc=None):
        """Compose the self-model inside one fully audited read transaction.

        No caller-supplied state, claims, VERIFIED labels or live process flags
        enter this source boundary. This never initializes or mutates a store.
        """
        from .entity_mirror import _project_verified_mirror
        if not self.path.is_file():
            raise EntityStoreError("STORE_ABSENT")
        connection = self._connect(read_only=True)
        try:
            connection.execute("BEGIN")
            proof = self._verified_snapshot(connection)
            return _project_verified_mirror(self, proof, cognition_store, as_of_utc)
        except (ValueError, TypeError) as exc:
            raise EntityStoreError("MIRROR_SOURCE_MISMATCH") from exc
        finally:
            connection.close()

    def inspect_read_only(
        self,
    ) -> tuple[
        EntityStoreIntegrityResult,
        EntityRestartSnapshot | None,
        EntityStateReceiptLineage | None,
    ]:
        """Return integrity, restart state, and lineage from one full audit."""

        if not self.path.is_file():
            return self.audit_read_only(), None, None
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect(read_only=True)
            # Pin one SQLite transaction. A proof for an earlier head cannot
            # certify newly committed rows, even when the Entity ID is unchanged.
            connection.execute("BEGIN")
            return self._verified_snapshot(connection).inspection
        except EntityStoreError as exc:
            if exc.code == "INTEGRITY_VERIFICATION_PENDING":
                pending = _invalid_integrity(exc.code).model_copy(update={"status": "PENDING"})
                return pending, None, None
            return _invalid_integrity(exc.code), None, None
        except (
            IndexError,
            KeyError,
            json.JSONDecodeError,
            sqlite3.DatabaseError,
            ValueError,
            TypeError,
        ):
            return _invalid_integrity("INTEGRITY_VALIDATION_FAILED"), None, None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _validated_inspection(snapshot: _AuditSnapshot) -> tuple[
        EntityStoreIntegrityResult, EntityRestartSnapshot, EntityStateReceiptLineage
    ]:
        # Cold/full verification independently validates aggregate projections.
        # A proven extension reuses already-validated immutable models and runs
        # the aggregate contracts without revalidating every historical object.
        state = snapshot.states[-1]
        pending = set(snapshot.pending_ingress_ids)
        undelivered = set(snapshot.undelivered_outbox_ids)
        integrity = EntityStoreIntegrityResult(
            status="VALID", present=True, valid=True, reason_codes=(),
            state_count=len(snapshot.states), event_count=len(snapshot.events),
            ingress_count=len(snapshot.ingresses),
            pending_ingress_count=len(snapshot.pending_ingress_ids),
            coordinator_result_count=len(snapshot.results),
            receipt_count=len(snapshot.receipts), outbox_count=len(snapshot.outbox),
            undelivered_outbox_count=len(snapshot.undelivered_outbox_ids),
            checkpoint_count=len(snapshot.checkpoints),
            activation_count=1 if snapshot.activation_record is not None else 0,
            head_state_id=state.entity_state_id, head_state_version=state.state_version,
            head_event_id=state.event_head_id, head_event_sequence=state.event_sequence,
        )
        restart_fields: dict[str, Any] = dict(
            state=state, historical_events=snapshot.events,
            pending_ingress=tuple(item for item in snapshot.ingresses if item.ingress_id in pending),
            undelivered_outbox=tuple(item for item in snapshot.outbox if item.outbox_id in undelivered),
            latest_receipt=snapshot.receipts[-1], latest_checkpoint=snapshot.checkpoints[-1],
            activation_record=snapshot.activation_record,
            activation_evidence=snapshot.activation_evidence,
            activation_receipt=next((item for item in snapshot.receipts if item.commit_kind == "ACTIVATION"), None),
        )
        if snapshot.verified_extension:
            # Every supplied model was either verified in the unchanged prefix
            # or fully validated as a new row above. Avoid recursively running
            # historical model validators a second time; retain both aggregate
            # contracts explicitly. These private projections accept no caller
            # data and are published only with the current image proof.
            restart = EntityRestartSnapshot.model_construct(**restart_fields)
            cast(Callable[[], object], restart.activation_material_is_complete)()
            lineage = EntityStateReceiptLineage.model_construct(states=snapshot.states, receipts=snapshot.receipts)
            cast(Callable[[], object], lineage.lineage_heads_match)()
        else:
            restart = EntityRestartSnapshot(**restart_fields)
            lineage = EntityStateReceiptLineage(states=snapshot.states, receipts=snapshot.receipts)
        return integrity, restart, lineage

    def _verified_snapshot(self, connection: sqlite3.Connection) -> _VerifiedAuditSnapshot:
        polling = is_polling_read()
        deadline = monotonic() + _WARM_POLL_VERIFICATION_WAIT_SECONDS
        while True:
            subject = _audit_subject(connection)
            with self._audit_condition:
                proof = self._verified_audit
                if proof is not None and proof.subject == subject and self._proof_head_matches(connection, proof):
                    read_count("verified_reuses")
                    return proof
                if proof is not None:
                    self._verified_audit = None
                    read_count("invalidations")
                if self._audit_failure is not None and self._audit_failure[0] == subject:
                    raise EntityStoreError(self._audit_failure[1])
                if self._audit_in_flight:
                    remaining = max(0.0, deadline - monotonic()) if polling else None
                    if polling and (self._verified_prefix is None or remaining == 0):
                        read_count("integrity_pending")
                        raise EntityStoreError("INTEGRITY_VERIFICATION_PENDING")
                    # Release both the SQLite read transaction and Condition
                    # while waiting. Never recurse with the outer lock held:
                    # a newer subject may require another expensive audit.
                    connection.execute("ROLLBACK")
                    completed = self._audit_condition.wait_for(
                        lambda: not self._audit_in_flight, timeout=remaining)
                    connection.execute("BEGIN")
                    if not completed:
                        read_count("integrity_pending")
                        raise EntityStoreError("INTEGRITY_VERIFICATION_PENDING")
                    # Re-read the transaction image and its proof binding. A
                    # completed audit of an older subject certifies nothing.
                    continue
                self._audit_in_flight = True
                if polling:
                    context = copy_context()
                    worker = threading.Thread(target=lambda: context.run(self._verify_in_background),
                        name="se6-entity-integrity-verification", daemon=True)
                    try:
                        worker.start()
                    except BaseException:
                        self._audit_in_flight = False
                        self._audit_condition.notify_all()
                        raise
                    if self._verified_prefix is not None and monotonic() < deadline:
                        # Join the single flight above, releasing the metadata
                        # lock and SQLite read transaction while it completes.
                        continue
                    read_count("integrity_pending")
                    raise EntityStoreError("INTEGRITY_VERIFICATION_PENDING")
            return self._finish_verification(connection, subject)

    def _finish_verification(self, connection: sqlite3.Connection,
                             subject: tuple[str, int, str, str]) -> _VerifiedAuditSnapshot:
        rows_token = _audit_row_image.set({})
        try:
            snapshot = self._audit_current_connection(connection)
            inspection = self._validated_inspection(snapshot)
            proof = _VerifiedAuditSnapshot(subject, self.path, datetime.now(UTC), snapshot, inspection)
            prefix = _capture_prefix(connection, proof)
            # Prefix digests consume the already-audited raw rows. Release only
            # that temporary image before allocating SQLite's full byte image;
            # validated models and every integrity predicate remain unchanged.
            # Neither proof nor prefix is published until the exact final image
            # comparison succeeds in this same transaction.
            rows = _audit_row_image.get()
            if rows is not None:
                rows.clear()
            if subject != _audit_subject(connection):
                raise EntityStoreError("AUDIT_SUBJECT_CHANGED_DURING_VERIFICATION")
            with self._audit_condition:
                self._verified_audit = proof
                self._verified_prefix = prefix
                self._audit_failure = None
            return proof
        except Exception as exc:
            code = exc.code if isinstance(exc, EntityStoreError) else "INTEGRITY_VALIDATION_FAILED"
            with self._audit_condition:
                self._verified_audit = None
                self._verified_prefix = None
                # A negative result is not a verified proof. A changed image
                # always invalidates it and is eligible for fresh verification.
                self._audit_failure = (
                    (subject, code) if isinstance(exc, EntityStoreError)
                    and code != "INTEGRITY_AUDIT_MEMORY_EXHAUSTED" else None
                )
            raise
        finally:
            _audit_row_image.reset(rows_token)
            with self._audit_condition:
                self._audit_in_flight = False
                self._audit_condition.notify_all()

    def _audit_current_connection(self, connection: sqlite3.Connection) -> _AuditSnapshot:
        # Keep the caller's write transaction intact: never wait for a background
        # reader or release BEGIN IMMEDIATE to obtain a cached proof.
        if not connection.in_transaction:
            connection.execute("BEGIN")
        with self._audit_condition:
            proof = self._verified_audit
            prefix = self._verified_prefix
        if (proof is not None and proof.subject == _audit_subject(connection)
                and self._proof_head_matches(connection, proof)):
            read_count("verified_reuses")
            return proof.snapshot
        if (prefix is not None and prefix.proof.store_path == self.path
                and prefix.proof.subject[:3] == (_AUDIT_PROOF_VERSION, ENTITY_STORE_SCHEMA_VERSION, ENTITY_STORE_POLICY_VERSION)
                and prefix.schema == _schema_image(connection)):
            # Prefix bytes bind all old rows, including queues/consumptions and
            # side projections. The normal audit below validates every new row,
            # cross-reference, chain extension and current head.
            token = _audit_row_image.set({}) if _audit_row_image.get() is None else None
            try:
                try:
                    return _audit_incremental(connection, prefix)
                except EntityStoreError as exc:
                    if exc.code != "VERIFIED_PREFIX_BINDING_MISMATCH":
                        raise
                    # An untrustworthy in-process checkpoint cannot certify
                    # anything. Independently re-audit the actual stored rows.
                    with self._audit_condition:
                        self._verified_prefix = None
            finally:
                if token is not None:
                    _audit_row_image.reset(token)
        rows: list[_AuditedStateRow] = []
        token = _state_row_audit.set((self._state_row_validation, rows))
        try:
            snapshot = _audit_connection(connection)
        finally:
            _state_row_audit.reset(token)
        # Failed audits publish neither row-validation memo nor image proof.
        self._state_row_validation.retain(rows)
        return snapshot

    def _verify_in_background(self) -> None:
        connection = None
        handed_off = False
        verified = False
        try:
            connection = self._connect(read_only=True)
            connection.execute("BEGIN")
            subject = _audit_subject(connection)
            handed_off = True
            self._finish_verification(connection, subject)
            verified = True
        except BaseException:
            # No exception text or data. Failure never publishes a verified
            # result. Interrupted verification can be retried normally.
            if not handed_off:
                with self._audit_condition:
                    self._audit_in_flight = False
                    self._audit_condition.notify_all()
        finally:
            if connection is not None:
                connection.close()
            emit_audit_completion(verified=verified)

    def _proof_head_matches(self, connection: sqlite3.Connection, proof: _VerifiedAuditSnapshot) -> bool:
        # Defense against accidentally associating a correct digest with the
        # wrong immutable result. The full-image hash, not this head alone,
        # establishes historical integrity. No caller supplies these proofs.
        state = proof.snapshot.states[-1]
        receipt = proof.snapshot.receipts[-1]
        integrity, restart, lineage = proof.inspection
        if (
            restart.state is not state
            or restart.latest_receipt is not receipt
            or lineage.states[-1] is not state
            or lineage.receipts[-1] is not receipt
            or integrity.head_state_id != state.entity_state_id
            or integrity.head_state_version != state.state_version
        ):
            return False
        row = connection.execute(
            "SELECT s.instance_id,s.identity_state_id,s.entity_state_id,s.state_hash,"
            "h.receipt_id,h.receipt_hash FROM entity_head h JOIN entity_states s "
            "ON s.entity_state_id=h.entity_state_id WHERE h.singleton=1"
        ).fetchone()
        return proof.store_path == self.path and row is not None and tuple(row) == (
            state.identity.instance_id, state.identity.identity_state_id,
            state.entity_state_id, state.state_hash, receipt.receipt_id, receipt.receipt_hash)

    def ingress_evidence_read_only(self, ingress_key: str) -> dict:
        """One audited read transaction for exact ingress/crash reconciliation.

        No schema initialization, table writes, runtime attachment or processing.
        The caller must independently compare the returned immutable draft.
        """
        if not isinstance(ingress_key, str) or not 1 <= len(ingress_key) <= 512:
            raise ValueError("ingress key must be bounded text")
        if not self.path.is_file():
            raise EntityStoreError("STORE_ABSENT")
        connection = self._connect(read_only=True)
        try:
            connection.execute("BEGIN")
            proof = self._verified_snapshot(connection)
            snapshot = proof.snapshot
            ingress = next((row for row in snapshot.ingresses if row.ingress_key == ingress_key), None)
            receipt = next((row for row in snapshot.receipts
                            if ingress is not None and row.processed_ingress_id == ingress.ingress_id), None)
            states = {row.entity_state_id: row for row in snapshot.states}
            events = tuple(row for row in snapshot.events
                           if receipt is not None and receipt.first_event_sequence <= row.sequence <= receipt.last_event_sequence)
            return {"ingress": ingress, "receipt": receipt, "events": events,
                    "state_before": states.get(receipt.state_before_id) if receipt else None,
                    "state_after": states.get(receipt.state_after_id) if receipt else None,
                    "current_state": snapshot.states[-1],
                    "historical_events": snapshot.events,
                    "state_lineage": snapshot.states, "receipts": snapshot.receipts}
        finally:
            connection.close()

    def state_receipt_lineage_read_only(self) -> EntityStateReceiptLineage:
        """Return state and receipt ancestry only after a complete store audit."""

        if not self.path.is_file():
            raise EntityStoreError("STORE_ABSENT")
        audit, _, lineage = self.inspect_read_only()
        if not audit.valid or lineage is None:
            raise EntityStoreError(audit.reason_codes[0] if audit.reason_codes else "INTEGRITY_VALIDATION_FAILED")
        return lineage

    def authority_head_read_only(
        self,
    ) -> tuple[SE6EntityState, EntityCommitReceipt]:
        """Validate only the content-addressed canonical head and its receipt.

        Callers must establish full-store integrity before exposing an action
        for review. This bounded read is the fail-closed freshness check used
        immediately before an already-reviewed exact action.
        """

        if not self.path.is_file():
            raise EntityStoreError("STORE_ABSENT")
        connection = self._connect(read_only=True)
        try:
            schema = connection.execute(
                "SELECT schema_version,policy_version FROM entity_store_schema "
                "WHERE singleton=1"
            ).fetchone()
            if schema is None or tuple(schema) != (
                ENTITY_STORE_SCHEMA_VERSION,
                ENTITY_STORE_POLICY_VERSION,
            ):
                raise EntityStoreError("SCHEMA_VERSION_MISMATCH")
            triggers = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                ).fetchall()
            }
            if not _REQUIRED_TRIGGERS.issubset(triggers):
                raise EntityStoreError("APPEND_ONLY_TRIGGER_MISSING")
            head = connection.execute(
                "SELECT * FROM entity_head WHERE singleton=1"
            ).fetchone()
            if head is None:
                raise EntityStoreError("STORE_HAS_NO_GENESIS")
            state_row = connection.execute(
                "SELECT * FROM entity_states WHERE entity_state_id=?",
                (head["entity_state_id"],),
            ).fetchone()
            receipt_row = connection.execute(
                "SELECT * FROM entity_commit_receipts WHERE receipt_id=?",
                (head["receipt_id"],),
            ).fetchone()
            if state_row is None or receipt_row is None:
                raise EntityStoreError("CANONICAL_HEAD_BINDING_MISMATCH")
            state = _typed_json(
                SE6EntityState, state_row["state_json"], "STATE_JSON_INVALID"
            )
            receipt = _typed_json(
                EntityCommitReceipt,
                receipt_row["receipt_json"],
                "RECEIPT_JSON_INVALID",
            )
            state_bindings = (
                _model_json(state) == state_row["state_json"],
                state.entity_state_id == state_row["entity_state_id"],
                state.state_version == state_row["state_version"],
                state.previous_entity_state_id
                == state_row["previous_entity_state_id"],
                state.event_sequence == state_row["event_sequence"],
                state.event_head_id == state_row["event_head_id"],
                state.identity.identity_state_id
                == state_row["identity_state_id"],
                state.identity.identity_state_hash
                == state_row["identity_state_hash"],
                state.identity.instance_id == state_row["instance_id"],
                state.state_hash == state_row["state_hash"],
                canonical_sha256(state) == state_row["content_hash"],
            )
            receipt_bindings = (
                _model_json(receipt) == receipt_row["receipt_json"],
                receipt.receipt_id == receipt_row["receipt_id"],
                receipt.receipt_hash == receipt_row["receipt_hash"],
                receipt.commit_sequence == receipt_row["commit_sequence"],
                receipt.commit_kind == receipt_row["commit_kind"],
                receipt.runtime_session_id == receipt_row["runtime_session_id"],
                receipt.state_before_id == receipt_row["state_before_id"],
                receipt.state_after_id == state.entity_state_id,
                receipt.state_after_hash == state.state_hash,
                receipt.state_after_version == state.state_version,
                receipt.previous_receipt_hash
                == receipt_row["previous_receipt_hash"],
            )
            head_bindings = (
                head["state_version"] == state.state_version,
                head["event_head_id"] == state.event_head_id,
                head["event_sequence"] == state.event_sequence,
                head["receipt_hash"] == receipt.receipt_hash,
                head["commit_sequence"] == receipt.commit_sequence,
            )
            if not all((*state_bindings, *receipt_bindings, *head_bindings)):
                raise EntityStoreError("CANONICAL_HEAD_BINDING_MISMATCH")
            return state, receipt
        except EntityStoreError:
            raise
        except (KeyError, TypeError, ValueError, sqlite3.DatabaseError) as exc:
            raise EntityStoreError("CANONICAL_HEAD_BINDING_MISMATCH") from exc
        finally:
            connection.close()

    def _fault(self, stage: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage)


def _validate_activation_state_continuity(
    state_before: SE6EntityState, state_after: SE6EntityState
) -> None:
    allowed_changes = {
        "schema_version",
        "entity_state_id",
        "state_hash",
        "previous_entity_state_id",
        "state_version",
        "lifecycle",
        "shared_metabolism",
        "continuation",
        "loop_states",
        "event_head_id",
        "event_sequence",
        "updated_at_utc",
        "operating_mode",
        "activation_basis_references",
        "shadow_mode",
        "production_authoritative",
    }
    for field_name in state_before.__class__.model_fields:
        if field_name in allowed_changes:
            continue
        if getattr(state_before, field_name) != getattr(state_after, field_name):
            raise EntityStoreError("ACTIVATION_SCOPE_VIOLATION")
    if (
        state_before.operating_mode is not EntityOperatingMode.SHADOW
        or state_after.operating_mode is not EntityOperatingMode.LOCAL_LIVE
        or state_after.previous_entity_state_id != state_before.entity_state_id
        or state_after.state_version != state_before.state_version + 1
        or state_after.event_sequence != state_before.event_sequence + 1
    ):
        raise EntityStoreError("ACTIVATION_LINEAGE_INVALID")
    if state_after.identity != state_before.identity:
        raise EntityStoreError("IDENTITY_CONTINUITY_VIOLATION")
    if state_after.environment_access != state_before.environment_access:
        raise EntityStoreError("ACTIVATION_NETWORK_CHANGE_PROHIBITED")
    if (
        state_after.shared_metabolism.pending_approval
        or state_after.shared_metabolism.transaction_id is not None
    ):
        raise EntityStoreError("ACTIVATION_METABOLISM_NOT_QUIESCENT")


def _validate_rebind_lifecycle(
    lifecycle: LifecycleView,
    references: tuple[str, ...],
    occurred_at_utc: datetime,
) -> None:
    if (
        lifecycle.durable_state is not LifecycleState.OBSERVING
        or lifecycle.operational_state is not OperationalConnectionState.CONNECTED
        or lifecycle.controller_status is not ControllerStatus.ACTIVE
        or not lifecycle.controller_authoritative
        or lifecycle.emergency_stop is not EmergencyStopState.ARMED
    ):
        raise EntityStoreError("RUNTIME_REBIND_LIFECYCLE_INVALID")
    if lifecycle.observed_at_utc != occurred_at_utc:
        raise EntityStoreError("RUNTIME_REBIND_OBSERVATION_TIME_MISMATCH")
    if lifecycle.evidence_references != references:
        raise EntityStoreError("RUNTIME_REBIND_EVIDENCE_BINDING_MISMATCH")


def _lifecycle_is_present_capable(lifecycle: LifecycleView) -> bool:
    return (
        lifecycle.durable_state is LifecycleState.OBSERVING
        and lifecycle.operational_state is OperationalConnectionState.CONNECTED
        and lifecycle.controller_status is ControllerStatus.ACTIVE
        and lifecycle.controller_authoritative
        and lifecycle.emergency_stop is EmergencyStopState.ARMED
    )


def _validate_detach_lifecycle(
    lifecycle: LifecycleView,
    references: tuple[str, ...],
    occurred_at_utc: datetime,
) -> None:
    common = (
        lifecycle.operational_state
        is OperationalConnectionState.DISCONNECTED_SAFE
        and lifecycle.controller_status
        in {ControllerStatus.ABSENT, ControllerStatus.RECOVERY_REQUIRED}
        and not lifecycle.controller_authoritative
    )
    ordinary = (
        lifecycle.durable_state is LifecycleState.PAUSED
        and lifecycle.emergency_stop is EmergencyStopState.ARMED
    )
    emergency = (
        lifecycle.durable_state is LifecycleState.STOPPED
        and lifecycle.emergency_stop is EmergencyStopState.TRIGGERED
    )
    if not common or not (ordinary or emergency):
        raise EntityStoreError("RUNTIME_DETACH_LIFECYCLE_INVALID")
    if lifecycle.observed_at_utc != occurred_at_utc:
        raise EntityStoreError("RUNTIME_DETACH_OBSERVATION_TIME_MISMATCH")
    if lifecycle.evidence_references != references:
        raise EntityStoreError("RUNTIME_DETACH_EVIDENCE_BINDING_MISMATCH")


def _validate_detach_state_continuity(
    state_before: SE6EntityState, state_after: SE6EntityState
) -> None:
    allowed_changes = {
        "entity_state_id",
        "state_hash",
        "previous_entity_state_id",
        "state_version",
        "lifecycle",
        "event_head_id",
        "event_sequence",
        "updated_at_utc",
    }
    for field_name in state_before.__class__.model_fields:
        if field_name in allowed_changes:
            continue
        if getattr(state_before, field_name) != getattr(state_after, field_name):
            raise EntityStoreError("RUNTIME_DETACH_SCOPE_VIOLATION")
    if (
        state_after.previous_entity_state_id != state_before.entity_state_id
        or state_after.state_version != state_before.state_version + 1
        or state_after.event_sequence != state_before.event_sequence + 1
    ):
        raise EntityStoreError("RUNTIME_DETACH_LINEAGE_INVALID")
    if state_after.identity != state_before.identity:
        raise EntityStoreError("IDENTITY_CONTINUITY_VIOLATION")
    if state_after.operating_mode is not EntityOperatingMode.LOCAL_LIVE:
        raise EntityStoreError("RUNTIME_DETACH_MODE_CHANGE_PROHIBITED")
    if state_after.activation_basis_references != state_before.activation_basis_references:
        raise EntityStoreError("RUNTIME_DETACH_ACTIVATION_CHANGE_PROHIBITED")
    if state_after.shared_metabolism != state_before.shared_metabolism:
        raise EntityStoreError("RUNTIME_DETACH_METABOLISM_CHANGE_PROHIBITED")
    if state_after.environment_access != state_before.environment_access:
        raise EntityStoreError("RUNTIME_DETACH_NETWORK_CHANGE_PROHIBITED")


def _validate_rebind_state_continuity(
    state_before: SE6EntityState, state_after: SE6EntityState
) -> None:
    allowed_changes = {
        "entity_state_id",
        "state_hash",
        "previous_entity_state_id",
        "state_version",
        "lifecycle",
        "event_head_id",
        "event_sequence",
        "updated_at_utc",
    }
    for field_name in state_before.__class__.model_fields:
        if field_name in allowed_changes:
            continue
        if getattr(state_before, field_name) != getattr(state_after, field_name):
            raise EntityStoreError("RUNTIME_REBIND_SCOPE_VIOLATION")
    if (
        state_after.previous_entity_state_id != state_before.entity_state_id
        or state_after.state_version != state_before.state_version + 1
        or state_after.event_sequence != state_before.event_sequence + 1
    ):
        raise EntityStoreError("RUNTIME_REBIND_LINEAGE_INVALID")
    if state_after.identity != state_before.identity:
        raise EntityStoreError("IDENTITY_CONTINUITY_VIOLATION")
    if state_after.shared_metabolism != state_before.shared_metabolism:
        raise EntityStoreError("RUNTIME_REBIND_METABOLISM_CHANGE_PROHIBITED")
    if state_after.environment_access != state_before.environment_access:
        raise EntityStoreError("RUNTIME_REBIND_NETWORK_CHANGE_PROHIBITED")


def _validate_step_contract(
    *,
    state_before: SE6EntityState,
    state_after: SE6EntityState,
    ingress: EntityIngressRecord,
    events: tuple[EntityEvent, ...],
    result: CoordinatorStepResult,
) -> None:
    if (ingress.draft.event_type not in {EventType.LOCAL_EVENT_BUDGET_RENEWAL, EventType.INTERACTIVE_PROOF_CONTROL}
            and state_after.resources.events_processed != state_before.resources.events_processed + 1):
        raise EntityStoreError("LOCAL_EVENT_BUDGET_UNAUTHORIZED_CHANGE")
    if ingress.draft.event_type is not EventType.LOCAL_EVENT_BUDGET_RENEWAL:
        if state_after.resources.event_budget != state_before.resources.event_budget:
            raise EntityStoreError("LOCAL_EVENT_BUDGET_UNAUTHORIZED_CHANGE")
    if state_after.previous_entity_state_id != state_before.entity_state_id:
        raise EntityStoreError("STATE_PREDECESSOR_MISMATCH")
    if state_after.state_version != state_before.state_version + 1:
        raise EntityStoreError("STATE_VERSION_NOT_CONTIGUOUS")
    if state_after.identity != state_before.identity:
        raise EntityStoreError("IDENTITY_CONTINUITY_VIOLATION")
    if (
        state_after.authority.owner_identity_reference
        != state_before.authority.owner_identity_reference
    ):
        raise EntityStoreError("OWNER_CONTINUITY_VIOLATION")
    expected_first = create_entity_event(
        sequence=state_before.event_sequence + 1, draft=ingress.draft
    )
    if events[0] != expected_first:
        raise EntityStoreError("INGRESS_EVENT_BINDING_MISMATCH")
    known_ids = set()
    for expected_sequence, event in enumerate(
        events, start=state_before.event_sequence + 1
    ):
        if event.sequence != expected_sequence:
            raise EntityStoreError("EVENT_SEQUENCE_NOT_CONTIGUOUS")
        if event.event_id in known_ids:
            raise EntityStoreError("DUPLICATE_EVENT_IN_DELTA")
        known_ids.add(event.event_id)
    if state_after.event_sequence != events[-1].sequence:
        raise EntityStoreError("STATE_EVENT_SEQUENCE_MISMATCH")
    if state_after.event_head_id != events[-1].event_id:
        raise EntityStoreError("STATE_EVENT_HEAD_MISMATCH")
    expected_ids = (result.processed_event_id, *result.emitted_event_ids)
    if tuple(event.event_id for event in events) != expected_ids:
        raise EntityStoreError("RESULT_EVENT_BINDING_MISMATCH")
    if (
        result.state_before_id != state_before.entity_state_id
        or result.state_after_id != state_after.entity_state_id
    ):
        raise EntityStoreError("RESULT_STATE_BINDING_MISMATCH")


def _insert_ingress(
    connection: sqlite3.Connection,
    draft: EntityEventDraft,
    ingress_key: str,
    enqueued_at_utc: datetime,
) -> EntityIngressRecord:
    draft_hash = canonical_sha256(draft)
    existing = connection.execute(
        "SELECT ingress_key,draft_hash FROM entity_ingress "
        "WHERE ingress_key=? OR draft_hash=?",
        (ingress_key, draft_hash),
    ).fetchall()
    if existing:
        if any(
            row["ingress_key"] == ingress_key and row["draft_hash"] != draft_hash
            for row in existing
        ):
            raise EntityStoreError("INGRESS_KEY_BINDING_MISMATCH")
        raise EntityStoreError("INGRESS_REPLAY_REJECTED")
    sequence = connection.execute(
        "SELECT COALESCE(MAX(queue_sequence),0)+1 FROM entity_ingress"
    ).fetchone()[0]
    material = {
        "schema_version": "se6-entity-ingress-v1",
        "queue_sequence": sequence,
        "ingress_key": ingress_key,
        "draft_hash": draft_hash,
        "enqueued_at_utc": enqueued_at_utc,
    }
    digest = canonical_sha256(material)
    record = EntityIngressRecord(
        ingress_id=f"entity_ingress_{digest}", draft=draft, **material
    )
    connection.execute(
        """
        INSERT INTO entity_ingress(
            queue_sequence,ingress_id,ingress_key,draft_json,draft_hash,enqueued_at_utc
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            record.queue_sequence,
            record.ingress_id,
            record.ingress_key,
            _model_json(record.draft),
            record.draft_hash,
            _time_text(record.enqueued_at_utc),
        ),
    )
    return record


def _insert_outbox(
    connection: sqlite3.Connection,
    *,
    intent: CommunicationIntent,
    result_id: str,
    entity_state_id: str,
    created_at_utc: datetime,
) -> EntityOutboxRecord:
    sequence = connection.execute(
        "SELECT COALESCE(MAX(outbox_sequence),0)+1 FROM entity_outbox"
    ).fetchone()[0]
    material = {
        "schema_version": "se6-entity-outbox-v1",
        "outbox_sequence": sequence,
        "result_id": result_id,
        "entity_state_id": entity_state_id,
        "intent_hash": canonical_sha256(intent),
        "created_at_utc": created_at_utc,
    }
    digest = canonical_sha256(material)
    record = EntityOutboxRecord(
        outbox_id=f"entity_outbox_{digest}", intent=intent, **material
    )
    connection.execute(
        """
        INSERT INTO entity_outbox(
            outbox_sequence,outbox_id,result_id,entity_state_id,intent_json,
            intent_hash,created_at_utc
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            record.outbox_sequence,
            record.outbox_id,
            record.result_id,
            record.entity_state_id,
            _model_json(record.intent),
            record.intent_hash,
            _time_text(record.created_at_utc),
        ),
    )
    return record


def _insert_state(
    connection: sqlite3.Connection,
    state: SE6EntityState,
    *,
    previous_state_chain_hash: str,
    state_chain_hash: str,
    committed_at_utc: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO entity_states(
            state_version,entity_state_id,previous_entity_state_id,event_sequence,
            event_head_id,identity_state_id,identity_state_hash,instance_id,
            constitution_version,constitution_hash,owner_identity_reference,
            identity_lineage_json,state_json,state_hash,content_hash,
            previous_state_chain_hash,state_chain_hash,committed_at_utc
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            state.state_version,
            state.entity_state_id,
            state.previous_entity_state_id,
            state.event_sequence,
            state.event_head_id,
            state.identity.identity_state_id,
            state.identity.identity_state_hash,
            state.identity.instance_id,
            state.identity.constitution_version,
            state.identity.constitution_hash,
            state.identity.owner_identity_reference,
            _plain_json(state.identity.identity_lineage),
            _model_json(state),
            state.state_hash,
            canonical_sha256(state),
            previous_state_chain_hash,
            state_chain_hash,
            _time_text(committed_at_utc),
        ),
    )


def _make_receipt(
    *,
    commit_sequence: int,
    commit_kind: Literal[
        "GENESIS", "STEP", "ACTIVATION", "RUNTIME_DETACH", "RUNTIME_REBIND"
    ],
    runtime_session_id: str,
    state_before_id: str | None,
    state_after: SE6EntityState,
    events: tuple[EntityEvent, ...],
    processed_ingress_id: str | None,
    coordinator_result_id: str | None,
    queued_ingress_ids: tuple[str, ...],
    outbox_ids: tuple[str, ...],
    previous_receipt_hash: str,
    committed_at_utc: datetime,
) -> EntityCommitReceipt:
    material = {
        "schema_version": "se6-entity-commit-receipt-v1",
        "commit_sequence": commit_sequence,
        "commit_kind": commit_kind,
        "runtime_session_id": runtime_session_id,
        "state_before_id": state_before_id,
        "state_after_id": state_after.entity_state_id,
        "state_after_hash": state_after.state_hash,
        "state_after_version": state_after.state_version,
        "first_event_sequence": events[0].sequence if events else None,
        "last_event_sequence": events[-1].sequence if events else None,
        "event_count": len(events),
        "processed_ingress_id": processed_ingress_id,
        "coordinator_result_id": coordinator_result_id,
        "queued_ingress_ids": queued_ingress_ids,
        "outbox_ids": outbox_ids,
        "previous_receipt_hash": previous_receipt_hash,
        "committed_at_utc": committed_at_utc,
    }
    digest = canonical_sha256(material)
    return EntityCommitReceipt(
        receipt_id=f"entity_commit_receipt_{digest}",
        receipt_hash=digest,
        **material,
    )


def _insert_receipt(
    connection: sqlite3.Connection, receipt: EntityCommitReceipt
) -> None:
    connection.execute(
        """
        INSERT INTO entity_commit_receipts(
            commit_sequence,receipt_id,receipt_hash,commit_kind,runtime_session_id,
            state_before_id,state_after_id,processed_ingress_id,coordinator_result_id,
            previous_receipt_hash,receipt_json,committed_at_utc
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            receipt.commit_sequence,
            receipt.receipt_id,
            receipt.receipt_hash,
            receipt.commit_kind,
            receipt.runtime_session_id,
            receipt.state_before_id,
            receipt.state_after_id,
            receipt.processed_ingress_id,
            receipt.coordinator_result_id,
            receipt.previous_receipt_hash,
            _model_json(receipt),
            _time_text(receipt.committed_at_utc),
        ),
    )


def _make_checkpoint(
    *,
    checkpoint_sequence: int,
    state: SE6EntityState,
    state_chain_hash: str,
    event_chain_hash: str,
    receipt: EntityCommitReceipt,
    created_at_utc: datetime,
) -> EntityCheckpointRecord:
    material = {
        "schema_version": "se6-entity-checkpoint-v1",
        "checkpoint_sequence": checkpoint_sequence,
        "entity_state_id": state.entity_state_id,
        "state_version": state.state_version,
        "state_chain_hash": state_chain_hash,
        "event_head_id": state.event_head_id,
        "event_sequence": state.event_sequence,
        "event_chain_hash": event_chain_hash,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "created_at_utc": created_at_utc,
    }
    digest = canonical_sha256(material)
    return EntityCheckpointRecord(
        checkpoint_id=f"entity_checkpoint_{digest}",
        checkpoint_hash=digest,
        **material,
    )


def _insert_checkpoint(
    connection: sqlite3.Connection, checkpoint: EntityCheckpointRecord
) -> None:
    connection.execute(
        """
        INSERT INTO entity_checkpoints(
            checkpoint_sequence,checkpoint_id,checkpoint_hash,entity_state_id,
            state_version,state_chain_hash,event_head_id,event_sequence,
            event_chain_hash,receipt_id,receipt_hash,checkpoint_json,created_at_utc
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            checkpoint.checkpoint_sequence,
            checkpoint.checkpoint_id,
            checkpoint.checkpoint_hash,
            checkpoint.entity_state_id,
            checkpoint.state_version,
            checkpoint.state_chain_hash,
            checkpoint.event_head_id,
            checkpoint.event_sequence,
            checkpoint.event_chain_hash,
            checkpoint.receipt_id,
            checkpoint.receipt_hash,
            _model_json(checkpoint),
            _time_text(checkpoint.created_at_utc),
        ),
    )


def _load_ingress_for_commit(
    connection: sqlite3.Connection, ingress_id: str
) -> EntityIngressRecord:
    row = connection.execute(
        "SELECT * FROM entity_ingress WHERE ingress_id=?", (ingress_id,)
    ).fetchone()
    if row is None:
        raise EntityStoreError("INGRESS_NOT_FOUND")
    if connection.execute(
        "SELECT 1 FROM entity_ingress_consumptions WHERE ingress_id=?", (ingress_id,)
    ).fetchone() is not None:
        raise EntityStoreError("INGRESS_REPLAY_REJECTED")
    return _ingress_from_row(row)


def _audit_connection(connection: sqlite3.Connection) -> _AuditSnapshot:
    with read_span("entity_full_audit") as timing:
        read_count("full_audits")
        digest = hashlib.sha256(connection.serialize()).hexdigest() if timing_active() else None
        result = _audit_connection_impl(connection)
        timing.update(state_count=len(result.states), head_version=result.states[-1].state_version)
        if digest is not None and digest == hashlib.sha256(connection.serialize()).hexdigest():
            timing["subject_sha256"] = digest
        return result


def _audit_connection_impl(connection: sqlite3.Connection) -> _AuditSnapshot:
    base = _extension_base.get()
    schema = connection.execute(
        "SELECT schema_version,policy_version FROM entity_store_schema WHERE singleton=1"
    ).fetchone()
    if schema is None or tuple(schema) != (
        ENTITY_STORE_SCHEMA_VERSION,
        ENTITY_STORE_POLICY_VERSION,
    ):
        raise EntityStoreError("SCHEMA_VERSION_MISMATCH")
    integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity is None or integrity[0] != "ok":
        raise EntityStoreError("SQLITE_INTEGRITY_FAILED")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise EntityStoreError("FOREIGN_KEY_INTEGRITY_FAILED")
    actual_triggers = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    missing = _REQUIRED_TRIGGERS - actual_triggers
    if missing:
        raise EntityStoreError("APPEND_ONLY_TRIGGER_MISSING")

    ingress_rows = _audit_rows(connection, "entity_ingress")
    prior_ingresses = base.ingresses if base else ()
    ingresses = (*prior_ingresses, *(_ingress_from_row(row) for row in ingress_rows[len(prior_ingresses):]))
    for expected, record in enumerate(ingresses, start=1):
        if record.queue_sequence != expected:
            raise EntityStoreError("INGRESS_SEQUENCE_NOT_CONTIGUOUS")

    event_rows = _audit_rows(connection, "entity_events")
    events = list(base.events) if base else []
    event_chain_hashes = list(base.event_chain_hashes) if base else []
    previous_chain = event_chain_hashes[-1] if event_chain_hashes else _ZERO_HASH
    known_event_ids = {event.event_id for event in events}
    for expected_sequence, row in enumerate(event_rows[len(events):], start=len(events) + 1):
        event = _typed_json(EntityEvent, row["event_json"], "EVENT_JSON_INVALID")
        if _model_json(event) != row["event_json"]:
            raise EntityStoreError("EVENT_JSON_NOT_CANONICAL")
        if event.sequence != expected_sequence or row["event_sequence"] != expected_sequence:
            raise EntityStoreError("EVENT_SEQUENCE_NOT_CONTIGUOUS")
        if row["event_id"] != event.event_id or row["content_hash"] != canonical_sha256(event):
            raise EntityStoreError("EVENT_CONTENT_HASH_MISMATCH")
        if row["parent_event_id"] != event.parent_event_id:
            raise EntityStoreError("EVENT_PARENT_BINDING_MISMATCH")
        if event.parent_event_id is not None and event.parent_event_id not in known_event_ids:
            raise EntityStoreError("EVENT_PARENT_NOT_PRIOR")
        expected_chain = _event_chain_hash(event, previous_chain)
        if (
            row["previous_event_chain_hash"] != previous_chain
            or row["event_chain_hash"] != expected_chain
        ):
            raise EntityStoreError("EVENT_CHAIN_HASH_MISMATCH")
        if row["occurred_at_utc"] != _time_text(event.occurred_at_utc):
            raise EntityStoreError("EVENT_TIME_BINDING_MISMATCH")
        known_event_ids.add(event.event_id)
        events.append(event)
        event_chain_hashes.append(expected_chain)
        previous_chain = expected_chain

    state_rows = _audit_rows(connection, "entity_states")
    states = list(base.states) if base else []
    state_chain_hashes = list(base.state_chain_hashes) if base else []
    previous_state_chain = state_chain_hashes[-1] if state_chain_hashes else _ZERO_HASH
    prior_state: SE6EntityState | None = states[-1] if states else None
    genesis_identity = states[0].identity if states else None
    row_validation = _state_row_audit.get()
    for expected_version, row in enumerate(state_rows[len(states):], start=len(states)):
        fields = tuple(row)
        reused = row_validation[0].get(fields) if row_validation is not None else None
        # Also reject accidental in-process mutation of a previously validated
        # model. The aggregate constructors below still run its invariants.
        if reused is not None and _model_json(reused.state) != row["state_json"]:
            reused = None
        state = (reused.state if reused is not None else
                 _typed_json(SE6EntityState, row["state_json"], "STATE_JSON_INVALID"))
        if _model_json(state) != row["state_json"]:
            raise EntityStoreError("STATE_JSON_NOT_CANONICAL")
        if state.state_version != expected_version or row["state_version"] != expected_version:
            raise EntityStoreError("STATE_VERSION_NOT_CONTIGUOUS")
        if row["entity_state_id"] != state.entity_state_id:
            raise EntityStoreError("STATE_ID_BINDING_MISMATCH")
        if (row["state_hash"] != state.state_hash
                or reused is None and row["content_hash"] != canonical_sha256(state)):
            raise EntityStoreError("STATE_CONTENT_HASH_MISMATCH")
        duplicate_bindings = (
            row["previous_entity_state_id"] == state.previous_entity_state_id,
            row["event_sequence"] == state.event_sequence,
            row["event_head_id"] == state.event_head_id,
            row["identity_state_id"] == state.identity.identity_state_id,
            row["identity_state_hash"] == state.identity.identity_state_hash,
            row["instance_id"] == state.identity.instance_id,
            row["constitution_version"] == state.identity.constitution_version,
            row["constitution_hash"] == state.identity.constitution_hash,
            row["owner_identity_reference"] == state.identity.owner_identity_reference,
            row["identity_lineage_json"] == _plain_json(state.identity.identity_lineage),
        )
        if not all(duplicate_bindings):
            raise EntityStoreError("STATE_CONTINUITY_BINDING_MISMATCH")
        if prior_state is None:
            if state.previous_entity_state_id is not None or state.event_sequence != 0:
                raise EntityStoreError("GENESIS_STATE_INVALID")
            genesis_identity = state.identity
        else:
            if state.previous_entity_state_id != prior_state.entity_state_id:
                raise EntityStoreError("STATE_PREDECESSOR_MISMATCH")
            if state.event_sequence <= prior_state.event_sequence:
                raise EntityStoreError("STATE_EVENT_SEQUENCE_NOT_ADVANCING")
            if state.identity != genesis_identity:
                raise EntityStoreError("IDENTITY_CONTINUITY_VIOLATION")
        if state.event_sequence > len(events):
            raise EntityStoreError("STATE_REFERENCES_MISSING_EVENT")
        expected_event_head = (
            None if state.event_sequence == 0 else events[state.event_sequence - 1].event_id
        )
        if state.event_head_id != expected_event_head:
            raise EntityStoreError("STATE_EVENT_HEAD_MISMATCH")
        expected_state_chain = (reused.chain_hash if reused is not None else
                                _state_chain_hash(state, previous_state_chain))
        if (
            row["previous_state_chain_hash"] != previous_state_chain
            or row["state_chain_hash"] != expected_state_chain
        ):
            raise EntityStoreError("STATE_CHAIN_HASH_MISMATCH")
        states.append(state)
        state_chain_hashes.append(expected_state_chain)
        previous_state_chain = expected_state_chain
        prior_state = state
        if row_validation is not None:
            row_validation[1].append(reused or _AuditedStateRow(
                fields, state, expected_state_chain,
                sum(len(value.encode("utf-8")) if isinstance(value, str) else 32
                    for value in fields),
            ))
    if not states:
        raise EntityStoreError("STORE_HAS_NO_GENESIS")

    result_rows = _audit_rows(connection, "entity_coordinator_results")
    results = list(base.results) if base else []
    state_index_by_id = {
        state.entity_state_id: index for index, state in enumerate(states)
    }
    for expected_sequence, row in enumerate(result_rows[len(results):], start=len(results) + 1):
        result = _typed_json(
            CoordinatorStepResult, row["result_json"], "RESULT_JSON_INVALID"
        )
        if _model_json(result) != row["result_json"]:
            raise EntityStoreError("RESULT_JSON_NOT_CANONICAL")
        if row["result_sequence"] != expected_sequence:
            raise EntityStoreError("RESULT_SEQUENCE_NOT_CONTIGUOUS")
        if (
            row["result_id"] != result.result_id
            or row["content_hash"] != canonical_sha256(result)
            or row["state_before_id"] != result.state_before_id
            or row["state_after_id"] != result.state_after_id
            or row["processed_event_id"] != result.processed_event_id
            or row["processed_at_utc"] != _time_text(result.processed_at_utc)
        ):
            raise EntityStoreError("RESULT_CONTENT_BINDING_MISMATCH")
        before_index = state_index_by_id.get(result.state_before_id)
        after_index = state_index_by_id.get(result.state_after_id)
        if (
            before_index is None
            or after_index is None
            or after_index != before_index + 1
        ):
            raise EntityStoreError("RESULT_STATE_LINEAGE_MISMATCH")
        before = states[before_index]
        after = states[after_index]
        event_delta = events[before.event_sequence : after.event_sequence]
        if (
            result.state_before_id != before.entity_state_id
            or result.state_after_id != after.entity_state_id
            or tuple(item.event_id for item in event_delta)
            != (result.processed_event_id, *result.emitted_event_ids)
        ):
            raise EntityStoreError("RESULT_LINEAGE_BINDING_MISMATCH")
        results.append(result)
    receipt_rows = _audit_rows(connection, "entity_commit_receipts")
    if len(receipt_rows) != len(states):
        raise EntityStoreError("RECEIPT_STATE_COUNT_MISMATCH")
    receipts = list(base.receipts) if base else []
    previous_receipt_hash = receipts[-1].receipt_hash if receipts else _ZERO_HASH
    for expected_sequence, row in enumerate(receipt_rows[len(receipts):], start=len(receipts) + 1):
        receipt = _typed_json(
            EntityCommitReceipt, row["receipt_json"], "RECEIPT_JSON_INVALID"
        )
        if _model_json(receipt) != row["receipt_json"]:
            raise EntityStoreError("RECEIPT_JSON_NOT_CANONICAL")
        if (
            row["commit_sequence"] != expected_sequence
            or receipt.commit_sequence != expected_sequence
        ):
            raise EntityStoreError("RECEIPT_SEQUENCE_NOT_CONTIGUOUS")
        bindings = (
            row["receipt_id"] == receipt.receipt_id,
            row["receipt_hash"] == receipt.receipt_hash,
            row["commit_kind"] == receipt.commit_kind,
            row["runtime_session_id"] == receipt.runtime_session_id,
            row["state_before_id"] == receipt.state_before_id,
            row["state_after_id"] == receipt.state_after_id,
            row["processed_ingress_id"] == receipt.processed_ingress_id,
            row["coordinator_result_id"] == receipt.coordinator_result_id,
            row["previous_receipt_hash"] == receipt.previous_receipt_hash,
            row["committed_at_utc"] == _time_text(receipt.committed_at_utc),
        )
        if not all(bindings) or receipt.previous_receipt_hash != previous_receipt_hash:
            raise EntityStoreError("RECEIPT_CHAIN_BINDING_MISMATCH")
        state = states[expected_sequence - 1]
        if (
            receipt.state_after_id != state.entity_state_id
            or receipt.state_after_hash != state.state_hash
            or receipt.state_after_version != state.state_version
            or state_rows[expected_sequence - 1]["committed_at_utc"]
            != _time_text(receipt.committed_at_utc)
        ):
            raise EntityStoreError("RECEIPT_STATE_BINDING_MISMATCH")
        if expected_sequence == 1:
            if receipt.commit_kind != "GENESIS":
                raise EntityStoreError("GENESIS_RECEIPT_MISSING")
        elif receipt.commit_kind == "STEP":
            result = next(
                (
                    item
                    for item in results
                    if item.result_id == receipt.coordinator_result_id
                ),
                None,
            )
            if result is None:
                raise EntityStoreError("RECEIPT_RESULT_MISSING")
            before = states[expected_sequence - 2]
            if (
                receipt.state_before_id != before.entity_state_id
                or receipt.coordinator_result_id != result.result_id
                or receipt.first_event_sequence != before.event_sequence + 1
                or receipt.last_event_sequence != state.event_sequence
                or receipt.event_count
                != state.event_sequence - before.event_sequence
            ):
                raise EntityStoreError("RECEIPT_STEP_BINDING_MISMATCH")
            event = events[before.event_sequence]
            if any(e.event_type is EventType.INTERACTIVE_PROOF_CONTROL
                   for e in events[before.event_sequence + 1:state.event_sequence]):
                raise EntityStoreError("INTERACTIVE_PROOF_NESTED_CONTROL_INVALID")
            if event.event_type is EventType.LOCAL_EVENT_BUDGET_RENEWAL:
                from .entity_event_budget import build_renewal_step
                event_material = {name: getattr(event, name) for name in EntityEventDraft.model_fields}
                try:
                    _, expected_state, expected_result = build_renewal_step(before,
                        EntityEventDraft(**event_material), events[:before.event_sequence])
                except ValueError as exc:
                    raise EntityStoreError("LOCAL_EVENT_BUDGET_AUDIT_INVALID") from exc
                if state != expected_state or result != expected_result:
                    raise EntityStoreError("LOCAL_EVENT_BUDGET_TRANSITION_MISMATCH")
            elif event.event_type is EventType.INTERACTIVE_PROOF_CONTROL:
                from .interactive_entity_proof import build_step
                event_material = {name: getattr(event, name) for name in EntityEventDraft.model_fields}
                try:
                    expected_events, expected_state, expected_result = build_step(before,
                        EntityEventDraft(**event_material), events[:before.event_sequence], states[:expected_sequence - 1])
                except ValueError as exc:
                    raise EntityStoreError("INTERACTIVE_PROOF_AUDIT_INVALID") from exc
                if (state != expected_state or result != expected_result
                        or tuple(events[before.event_sequence:state.event_sequence]) != tuple(expected_events)):
                    raise EntityStoreError("INTERACTIVE_PROOF_TRANSITION_MISMATCH")
            elif (state.resources.event_budget != before.resources.event_budget
                  or state.resources.events_processed != before.resources.events_processed + 1):
                raise EntityStoreError("LOCAL_EVENT_BUDGET_UNAUTHORIZED_CHANGE")
        elif receipt.commit_kind == "ACTIVATION":
            before = states[expected_sequence - 2]
            event = events[before.event_sequence]
            if (
                receipt.state_before_id != before.entity_state_id
                or receipt.first_event_sequence != before.event_sequence + 1
                or receipt.last_event_sequence != state.event_sequence
                or state.event_sequence != before.event_sequence + 1
                or event.event_id != state.event_head_id
                or event.event_type is not EventType.LIFECYCLE
                or not isinstance(event.payload, LifecyclePayload)
                or event.payload.signal is not LifecycleSignal.STATE_REPORTED
                or event.payload.evidence_references
                != state.activation_basis_references
                or event.occurred_at_utc != state.updated_at_utc
            ):
                raise EntityStoreError("ACTIVATION_RECEIPT_INVALID")
            _validate_activation_state_continuity(before, state)
        elif receipt.commit_kind == "RUNTIME_DETACH":
            before = states[expected_sequence - 2]
            event = events[before.event_sequence]
            emergency_detach = (
                state.lifecycle.emergency_stop is EmergencyStopState.TRIGGERED
            )
            if (
                receipt.state_before_id != before.entity_state_id
                or receipt.first_event_sequence != before.event_sequence + 1
                or receipt.last_event_sequence != state.event_sequence
                or state.event_sequence != before.event_sequence + 1
                or event.event_id != state.event_head_id
                or event.event_type
                is not (EventType.STOP if emergency_detach else EventType.PAUSE)
                or not isinstance(event.payload, LifecyclePayload)
                or event.payload.signal
                is not (
                    LifecycleSignal.STOP
                    if emergency_detach
                    else LifecycleSignal.PAUSE
                )
                or event.payload.controller_authoritative
                or event.payload.evidence_references
                != state.lifecycle.evidence_references
                or event.occurred_at_utc != state.updated_at_utc
                or receipt.runtime_session_id
                != receipts[-1].runtime_session_id
            ):
                raise EntityStoreError("RUNTIME_DETACH_RECEIPT_INVALID")
            if not _lifecycle_is_present_capable(before.lifecycle):
                raise EntityStoreError("RUNTIME_DETACH_PREDECESSOR_INVALID")
            _validate_detach_lifecycle(
                state.lifecycle,
                tuple(event.payload.evidence_references),
                event.occurred_at_utc,
            )
            _validate_detach_state_continuity(before, state)
        elif receipt.commit_kind == "RUNTIME_REBIND":
            before = states[expected_sequence - 2]
            event = events[before.event_sequence]
            if (
                receipt.state_before_id != before.entity_state_id
                or receipt.first_event_sequence != before.event_sequence + 1
                or receipt.last_event_sequence != state.event_sequence
                or state.event_sequence != before.event_sequence + 1
                or event.event_id != state.event_head_id
                or event.event_type is not EventType.RECOVERY
                or not isinstance(event.payload, LifecyclePayload)
                or event.payload.signal is not LifecycleSignal.RECOVERED
                or event.payload.evidence_references
                != state.lifecycle.evidence_references
                or event.occurred_at_utc != state.updated_at_utc
                or receipt.runtime_session_id
                == receipts[-1].runtime_session_id
            ):
                raise EntityStoreError("RUNTIME_REBIND_RECEIPT_INVALID")
            _validate_rebind_lifecycle(
                state.lifecycle,
                tuple(event.payload.evidence_references),
                event.occurred_at_utc,
            )
            _validate_rebind_state_continuity(before, state)
        else:
            raise EntityStoreError("RECEIPT_KIND_INVALID")
        receipts.append(receipt)
        previous_receipt_hash = receipt.receipt_hash
    step_result_ids = tuple(
        receipt.coordinator_result_id
        for receipt in receipts
        if receipt.commit_kind == "STEP"
    )
    if step_result_ids != tuple(result.result_id for result in results):
        raise EntityStoreError("RESULT_RECEIPT_COUNT_MISMATCH")
    activation_rows = _audit_rows(connection, "entity_activation_commits")
    activation_receipts = tuple(
        receipt for receipt in receipts if receipt.commit_kind == "ACTIVATION"
    )
    if len(activation_rows) != len(activation_receipts) or len(activation_rows) > 1:
        raise EntityStoreError("ACTIVATION_COMMIT_COUNT_MISMATCH")
    durable_activation_record = base.activation_record if base else None
    durable_activation_evidence = base.activation_evidence if base else None
    if activation_rows and durable_activation_record is None:
        row = activation_rows[0]
        record = _typed_json(
            EntityActivationRecord,
            row["record_json"],
            "ACTIVATION_RECORD_JSON_INVALID",
        )
        evidence = _typed_json(
            EntityActivationEvidenceBundle,
            row["evidence_json"],
            "ACTIVATION_EVIDENCE_JSON_INVALID",
        )
        if (
            _model_json(record) != row["record_json"]
            or _model_json(evidence) != row["evidence_json"]
        ):
            raise EntityStoreError("ACTIVATION_JSON_NOT_CANONICAL")
        receipt = activation_receipts[0]
        before_index = state_index_by_id.get(row["state_before_id"])
        after_index = state_index_by_id.get(row["state_after_id"])
        if before_index is None or after_index is None:
            raise EntityStoreError("ACTIVATION_COMMIT_BINDING_MISMATCH")
        bindings = (
            row["activation_sequence"] == 1,
            row["activation_record_id"] == record.activation_record_id,
            row["activation_record_hash"] == record.activation_record_hash,
            row["evidence_bundle_id"] == evidence.evidence_bundle_id,
            row["evidence_bundle_hash"] == evidence.evidence_bundle_hash,
            row["record_content_hash"] == canonical_sha256(record),
            row["evidence_content_hash"] == canonical_sha256(evidence),
            row["receipt_id"] == receipt.receipt_id,
            row["committed_at_utc"] == _time_text(receipt.committed_at_utc),
            receipt.runtime_session_id
            == evidence.runtime_evidence.runtime_session_id,
        )
        if not all(bindings) or after_index != before_index + 1:
            raise EntityStoreError("ACTIVATION_COMMIT_BINDING_MISMATCH")
        if evaluate_entity_activation(evidence) != record:
            raise EntityStoreError("ACTIVATION_RECORD_EVIDENCE_MISMATCH")
        assert before_index is not None
        assert after_index is not None
        before = states[before_index]
        after = states[after_index]
        event = events[before.event_sequence]
        if (
            receipt.state_before_id != before.entity_state_id
            or receipt.state_after_id != after.entity_state_id
            or event.event_id != after.event_head_id
            or not isinstance(event.payload, LifecyclePayload)
            or event.payload.evidence_references
            != activation_basis_references(record, evidence)
        ):
            raise EntityStoreError("ACTIVATION_EVENT_BINDING_MISMATCH")
        try:
            expected_after = build_first_local_live_entity_state(
                before,
                activation_record=record,
                activation_evidence=evidence,
                expected_state_version=before.state_version,
                event_head_id=event.event_id,
                event_sequence=event.sequence,
                updated_at_utc=event.occurred_at_utc,
                lifecycle=after.lifecycle,
                shared_metabolism=after.shared_metabolism,
                continuation=after.continuation,
            )
        except (TypeError, ValueError) as exc:
            raise EntityStoreError("ACTIVATION_RECONSTRUCTION_FAILED") from exc
        if expected_after != after:
            raise EntityStoreError("ACTIVATION_STATE_RECONSTRUCTION_MISMATCH")
        durable_activation_record = record
        durable_activation_evidence = evidence
    consumption_rows = _audit_rows(connection, "entity_ingress_consumptions")
    consumed_ids = {item.ingress_id for item in base.ingresses}.difference(base.pending_ingress_ids) if base else set()
    prior_consumption_count = len(consumed_ids)
    if len(consumption_rows) != len(results):
        raise EntityStoreError("INGRESS_CONSUMPTION_COUNT_MISMATCH")
    ingress_by_id = {item.ingress_id: item for item in ingresses}
    result_by_id = {item.result_id: item for item in results}
    receipt_by_id = {item.receipt_id: item for item in receipts}
    for index, row in enumerate(consumption_rows[prior_consumption_count:], start=prior_consumption_count):
        if row["consumption_sequence"] != index + 1:
            raise EntityStoreError("INGRESS_CONSUMPTION_SEQUENCE_INVALID")
        result = result_by_id.get(row["result_id"])
        receipt = receipt_by_id.get(row["receipt_id"])
        if result is None or receipt is None or receipt.commit_kind != "STEP":
            raise EntityStoreError("INGRESS_CONSUMPTION_ORPHANED")
        before_index = state_index_by_id.get(result.state_before_id)
        if before_index is None:
            raise EntityStoreError("INGRESS_CONSUMPTION_ORPHANED")
        before = states[before_index]
        ingress = ingress_by_id.get(row["ingress_id"])
        if ingress is None:
            raise EntityStoreError("INGRESS_CONSUMPTION_ORPHANED")
        if (
            row["processed_event_id"] != result.processed_event_id
            or row["result_id"] != result.result_id
            or row["receipt_id"] != receipt.receipt_id
            or receipt.processed_ingress_id != ingress.ingress_id
            or receipt.coordinator_result_id != result.result_id
            or row["consumed_at_utc"] != _time_text(receipt.committed_at_utc)
        ):
            raise EntityStoreError("INGRESS_CONSUMPTION_BINDING_MISMATCH")
        expected_event = create_entity_event(
            sequence=before.event_sequence + 1, draft=ingress.draft
        )
        if events[before.event_sequence] != expected_event:
            raise EntityStoreError("INGRESS_EVENT_BINDING_MISMATCH")
        consumed_ids.add(ingress.ingress_id)

    outbox_rows = _audit_rows(connection, "entity_outbox")
    outbox = list(base.outbox) if base else []
    for expected_sequence, row in enumerate(outbox_rows[len(outbox):], start=len(outbox) + 1):
        record = _outbox_from_row(row)
        if record.outbox_sequence != expected_sequence:
            raise EntityStoreError("OUTBOX_SEQUENCE_NOT_CONTIGUOUS")
        outbox.append(record)
    expected_outbox = [
        (result.result_id, result.state_after_id, intent)
        for result in results
        for intent in result.communication_intents
    ]
    if len(outbox) != len(expected_outbox):
        raise EntityStoreError("OUTBOX_RESULT_COUNT_MISMATCH")
    for record, expected in zip(outbox, expected_outbox):
        if (
            record.result_id != expected[0]
            or record.entity_state_id != expected[1]
            or record.intent != expected[2]
        ):
            raise EntityStoreError("OUTBOX_RESULT_BINDING_MISMATCH")

    for receipt in receipts[len(base.receipts) if base else 0:]:
        if receipt.commit_kind != "STEP":
            continue
        result = result_by_id.get(receipt.coordinator_result_id or "")
        if result is None:
            raise EntityStoreError("RECEIPT_RESULT_MISSING")
        queued_for_result = tuple(
            item
            for item in ingresses
            if item.ingress_key.startswith(f"derived:{result.result_id}:")
        )
        outbox_for_result = tuple(
            item for item in outbox if item.result_id == result.result_id
        )
        if (
            receipt.queued_ingress_ids
            != tuple(item.ingress_id for item in queued_for_result)
            or receipt.outbox_ids
            != tuple(item.outbox_id for item in outbox_for_result)
        ):
            raise EntityStoreError("RECEIPT_PROJECTION_BINDING_MISMATCH")
        for position, item in enumerate(queued_for_result):
            expected_key = (
                f"derived:{result.result_id}:{position}:{item.draft_hash}"
            )
            if (
                item.ingress_key != expected_key
                or item.enqueued_at_utc != receipt.committed_at_utc
            ):
                raise EntityStoreError("DERIVED_INGRESS_BINDING_MISMATCH")
        if any(
            item.created_at_utc != receipt.committed_at_utc
            for item in outbox_for_result
        ):
            raise EntityStoreError("OUTBOX_RECEIPT_TIME_MISMATCH")

    if base:
        # A new ingress cannot be grafted onto an already-committed result.
        # The complete audit's receipt loop checks this for all history; the
        # delta path must also cover additions that target that old prefix.
        new_derived_ids = {identity for receipt in receipts[len(base.receipts):]
                           for identity in receipt.queued_ingress_ids}
        for ingress in ingresses[len(base.ingresses):]:
            if ingress.ingress_key.startswith("derived:") and ingress.ingress_id not in new_derived_ids:
                raise EntityStoreError("RECEIPT_PROJECTION_BINDING_MISMATCH")

    delivery_rows = _audit_rows(connection, "entity_outbox_deliveries")
    deliveries = list(base.outbox_deliveries) if base else []
    known_outbox_ids = {item.outbox_id for item in outbox}
    for expected_sequence, row in enumerate(delivery_rows[len(deliveries):], start=len(deliveries) + 1):
        delivery = _outbox_delivery_from_row(row)
        if delivery.delivery_sequence != expected_sequence:
            raise EntityStoreError("OUTBOX_DELIVERY_SEQUENCE_NOT_CONTIGUOUS")
        if delivery.outbox_id not in known_outbox_ids:
            raise EntityStoreError("OUTBOX_DELIVERY_ORPHANED")
        deliveries.append(delivery)
    delivered_ids = {item.outbox_id for item in deliveries}

    checkpoint_rows = _audit_rows(connection, "entity_checkpoints")
    if len(checkpoint_rows) != len(states):
        raise EntityStoreError("CHECKPOINT_STATE_COUNT_MISMATCH")
    checkpoints = list(base.checkpoints) if base else []
    for index, row in enumerate(checkpoint_rows[len(checkpoints):], start=len(checkpoints)):
        checkpoint = _typed_json(
            EntityCheckpointRecord, row["checkpoint_json"], "CHECKPOINT_JSON_INVALID"
        )
        if _model_json(checkpoint) != row["checkpoint_json"]:
            raise EntityStoreError("CHECKPOINT_JSON_NOT_CANONICAL")
        state = states[index]
        receipt = receipts[index]
        event_chain = (
            _ZERO_HASH
            if state.event_sequence == 0
            else event_chain_hashes[state.event_sequence - 1]
        )
        bindings = (
            checkpoint.checkpoint_sequence == index + 1,
            row["checkpoint_sequence"] == index + 1,
            row["checkpoint_id"] == checkpoint.checkpoint_id,
            row["checkpoint_hash"] == checkpoint.checkpoint_hash,
            row["entity_state_id"] == checkpoint.entity_state_id,
            row["state_version"] == checkpoint.state_version,
            row["state_chain_hash"] == checkpoint.state_chain_hash,
            row["event_head_id"] == checkpoint.event_head_id,
            row["event_sequence"] == checkpoint.event_sequence,
            row["event_chain_hash"] == checkpoint.event_chain_hash,
            row["receipt_id"] == checkpoint.receipt_id,
            row["receipt_hash"] == checkpoint.receipt_hash,
            row["created_at_utc"] == _time_text(checkpoint.created_at_utc),
            checkpoint.entity_state_id == state.entity_state_id,
            checkpoint.state_version == state.state_version,
            checkpoint.state_chain_hash == state_chain_hashes[index],
            checkpoint.event_head_id == state.event_head_id,
            checkpoint.event_sequence == state.event_sequence,
            checkpoint.event_chain_hash == event_chain,
            checkpoint.receipt_id == receipt.receipt_id,
            checkpoint.receipt_hash == receipt.receipt_hash,
        )
        if not all(bindings):
            raise EntityStoreError("CHECKPOINT_BINDING_MISMATCH")
        checkpoints.append(checkpoint)
    head_rows = connection.execute("SELECT * FROM entity_head").fetchall()
    if len(head_rows) != 1:
        raise EntityStoreError("CANONICAL_HEAD_COUNT_INVALID")
    head = head_rows[0]
    latest_state = states[-1]
    latest_receipt = receipts[-1]
    latest_checkpoint = checkpoints[-1]
    latest_event_chain = _ZERO_HASH if not events else event_chain_hashes[-1]
    head_bindings = (
        head["singleton"] == 1,
        head["entity_state_id"] == latest_state.entity_state_id,
        head["state_version"] == latest_state.state_version,
        head["state_chain_hash"] == state_chain_hashes[-1],
        head["event_head_id"] == latest_state.event_head_id,
        head["event_sequence"] == latest_state.event_sequence == len(events),
        head["event_chain_hash"] == latest_event_chain,
        head["receipt_id"] == latest_receipt.receipt_id,
        head["receipt_hash"] == latest_receipt.receipt_hash,
        head["commit_sequence"] == latest_receipt.commit_sequence,
        head["checkpoint_id"] == latest_checkpoint.checkpoint_id,
    )
    if not all(head_bindings):
        raise EntityStoreError("CANONICAL_HEAD_BINDING_MISMATCH")

    # New rows were constructed through their strict validators; old rows were
    # checked byte-for-byte against the verified prefix. All aggregate bindings
    # above run before this private container is created. Cold/full audits keep
    # the independent recursive construction as a separate assurance boundary.
    snapshot_factory = _AuditSnapshot.model_construct if base else _AuditSnapshot
    return snapshot_factory(
        verified_extension=base is not None,
        states=tuple(states),
        events=tuple(events),
        ingresses=ingresses,
        pending_ingress_ids=tuple(
            item.ingress_id for item in ingresses if item.ingress_id not in consumed_ids
        ),
        results=tuple(results),
        receipts=tuple(receipts),
        outbox=tuple(outbox),
        outbox_deliveries=tuple(deliveries),
        undelivered_outbox_ids=tuple(
            item.outbox_id for item in outbox if item.outbox_id not in delivered_ids
        ),
        checkpoints=tuple(checkpoints),
        state_chain_hashes=tuple(state_chain_hashes),
        event_chain_hashes=tuple(event_chain_hashes),
        activation_record=durable_activation_record,
        activation_evidence=durable_activation_evidence,
    )


def _require_valid_existing_store(connection: sqlite3.Connection) -> None:
    _audit_connection(connection)


def _ingress_from_row(row: sqlite3.Row) -> EntityIngressRecord:
    draft = _typed_json(EntityEventDraft, row["draft_json"], "INGRESS_JSON_INVALID")
    if _model_json(draft) != row["draft_json"]:
        raise EntityStoreError("INGRESS_JSON_NOT_CANONICAL")
    parsed_time = _parse_time(row["enqueued_at_utc"])
    if row["enqueued_at_utc"] != _time_text(parsed_time):
        raise EntityStoreError("INGRESS_TIME_NOT_CANONICAL")
    record = EntityIngressRecord(
        ingress_id=row["ingress_id"],
        queue_sequence=row["queue_sequence"],
        ingress_key=row["ingress_key"],
        draft_hash=row["draft_hash"],
        draft=draft,
        enqueued_at_utc=parsed_time,
    )
    return record


def _outbox_from_row(row: sqlite3.Row) -> EntityOutboxRecord:
    intent = _typed_json(
        CommunicationIntent, row["intent_json"], "OUTBOX_JSON_INVALID"
    )
    if _model_json(intent) != row["intent_json"]:
        raise EntityStoreError("OUTBOX_JSON_NOT_CANONICAL")
    parsed_time = _parse_time(row["created_at_utc"])
    if row["created_at_utc"] != _time_text(parsed_time):
        raise EntityStoreError("OUTBOX_TIME_NOT_CANONICAL")
    return EntityOutboxRecord(
        outbox_id=row["outbox_id"],
        outbox_sequence=row["outbox_sequence"],
        result_id=row["result_id"],
        entity_state_id=row["entity_state_id"],
        intent_hash=row["intent_hash"],
        intent=intent,
        created_at_utc=parsed_time,
    )


def _outbox_delivery_from_row(
    row: sqlite3.Row,
) -> EntityOutboxDeliveryRecord:
    record = _typed_json(
        EntityOutboxDeliveryRecord,
        row["delivery_json"],
        "OUTBOX_DELIVERY_JSON_INVALID",
    )
    if _model_json(record) != row["delivery_json"]:
        raise EntityStoreError("OUTBOX_DELIVERY_JSON_NOT_CANONICAL")
    bindings = (
        row["delivery_sequence"] == record.delivery_sequence,
        row["delivery_id"] == record.delivery_id,
        row["delivery_hash"] == record.delivery_hash,
        row["outbox_id"] == record.outbox_id,
        row["delivery_reference"] == record.delivery_reference,
        row["delivered_at_utc"] == _time_text(record.delivered_at_utc),
    )
    if not all(bindings):
        raise EntityStoreError("OUTBOX_DELIVERY_CONTENT_BINDING_MISMATCH")
    return record


def _event_chain_hash(event: EntityEvent, previous_hash: str) -> str:
    return canonical_sha256(
        {
            "chain_type": "se6-entity-event-chain-v1",
            "sequence": event.sequence,
            "event_id": event.event_id,
            "content_hash": canonical_sha256(event),
            "previous_hash": previous_hash,
        }
    )


def _state_chain_hash(state: SE6EntityState, previous_hash: str) -> str:
    return canonical_sha256(
        {
            "chain_type": "se6-entity-state-chain-v1",
            "state_version": state.state_version,
            "entity_state_id": state.entity_state_id,
            "state_hash": state.state_hash,
            "content_hash": canonical_sha256(state),
            "event_head_id": state.event_head_id,
            "event_sequence": state.event_sequence,
            "previous_hash": previous_hash,
        }
    )


def _model_json(model: BaseModel) -> str:
    return json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _plain_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _typed_json(model_type, payload: str, error_code: str):
    try:
        return model_type.model_validate_json(payload)
    except (ValueError, TypeError) as exc:
        raise EntityStoreError(error_code) from exc


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (AttributeError, ValueError) as exc:
        raise EntityStoreError("TIMESTAMP_INVALID") from exc
    return _utc(parsed, "timestamp")


def _validate_reference(value: str, field_name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(_REFERENCE_PATTERN, value) is None:
        raise ValueError(f"{field_name} is not a safe opaque reference")
    _reject_secret_like(value)


def _reject_secret_like(value: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET_LIKE):
        raise ValueError("secret-like material is prohibited in entity persistence")


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.DatabaseError:
        pass


def _invalid_integrity(code: str) -> EntityStoreIntegrityResult:
    return EntityStoreIntegrityResult(
        status="INVALID",
        present=True,
        valid=False,
        reason_codes=(code,),
        state_count=0,
        event_count=0,
        ingress_count=0,
        pending_ingress_count=0,
        coordinator_result_count=0,
        receipt_count=0,
        outbox_count=0,
        undelivered_outbox_count=0,
        checkpoint_count=0,
    )


_APPEND_ONLY_TABLES = (
    "entity_ingress",
    "entity_events",
    "entity_states",
    "entity_coordinator_results",
    "entity_commit_receipts",
    "entity_ingress_consumptions",
    "entity_outbox",
    "entity_outbox_deliveries",
    "entity_checkpoints",
    "entity_activation_commits",
)
_REQUIRED_TRIGGERS = {
    *(f"{table}_no_update" for table in _APPEND_ONLY_TABLES),
    *(f"{table}_no_delete" for table in _APPEND_ONLY_TABLES),
    "entity_head_no_delete",
    "entity_head_contiguous_update",
}
_APPEND_ONLY_TRIGGER_SQL = "".join(
    (
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_update "
        f"BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'{table} is "
        "append-only'); END; "
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete "
        f"BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'{table} is "
        "append-only'); END;"
    )
    for table in _APPEND_ONLY_TABLES
)


_SCHEMA_SQL = f"""
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS entity_store_schema (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    schema_version INTEGER NOT NULL CHECK(schema_version={ENTITY_STORE_SCHEMA_VERSION}),
    policy_version TEXT NOT NULL CHECK(policy_version='{ENTITY_STORE_POLICY_VERSION}')
);
INSERT OR IGNORE INTO entity_store_schema(singleton,schema_version,policy_version)
VALUES(1,{ENTITY_STORE_SCHEMA_VERSION},'{ENTITY_STORE_POLICY_VERSION}');

CREATE TABLE IF NOT EXISTS entity_ingress (
    queue_sequence INTEGER PRIMARY KEY,
    ingress_id TEXT NOT NULL UNIQUE,
    ingress_key TEXT NOT NULL UNIQUE,
    draft_json TEXT NOT NULL,
    draft_hash TEXT NOT NULL UNIQUE,
    enqueued_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_events (
    event_sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    parent_event_id TEXT REFERENCES entity_events(event_id),
    event_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    previous_event_chain_hash TEXT NOT NULL,
    event_chain_hash TEXT NOT NULL UNIQUE,
    occurred_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_states (
    state_version INTEGER PRIMARY KEY,
    entity_state_id TEXT NOT NULL UNIQUE,
    previous_entity_state_id TEXT REFERENCES entity_states(entity_state_id),
    event_sequence INTEGER NOT NULL,
    event_head_id TEXT REFERENCES entity_events(event_id),
    identity_state_id TEXT NOT NULL,
    identity_state_hash TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    constitution_version TEXT NOT NULL,
    constitution_hash TEXT NOT NULL,
    owner_identity_reference TEXT NOT NULL,
    identity_lineage_json TEXT NOT NULL,
    state_json TEXT NOT NULL,
    state_hash TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL UNIQUE,
    previous_state_chain_hash TEXT NOT NULL,
    state_chain_hash TEXT NOT NULL UNIQUE,
    committed_at_utc TEXT NOT NULL,
    UNIQUE(event_sequence)
);
CREATE TABLE IF NOT EXISTS entity_coordinator_results (
    result_sequence INTEGER PRIMARY KEY,
    result_id TEXT NOT NULL UNIQUE,
    state_before_id TEXT NOT NULL REFERENCES entity_states(entity_state_id),
    state_after_id TEXT NOT NULL UNIQUE REFERENCES entity_states(entity_state_id),
    processed_event_id TEXT NOT NULL UNIQUE REFERENCES entity_events(event_id),
    result_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    processed_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_commit_receipts (
    commit_sequence INTEGER PRIMARY KEY,
    receipt_id TEXT NOT NULL UNIQUE,
    receipt_hash TEXT NOT NULL UNIQUE,
    commit_kind TEXT NOT NULL CHECK(
        commit_kind IN (
            'GENESIS','STEP','ACTIVATION','RUNTIME_DETACH','RUNTIME_REBIND'
        )
    ),
    runtime_session_id TEXT NOT NULL,
    state_before_id TEXT REFERENCES entity_states(entity_state_id),
    state_after_id TEXT NOT NULL UNIQUE REFERENCES entity_states(entity_state_id),
    processed_ingress_id TEXT REFERENCES entity_ingress(ingress_id),
    coordinator_result_id TEXT UNIQUE REFERENCES entity_coordinator_results(result_id),
    previous_receipt_hash TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    committed_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_ingress_consumptions (
    consumption_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    ingress_id TEXT NOT NULL UNIQUE REFERENCES entity_ingress(ingress_id),
    processed_event_id TEXT NOT NULL UNIQUE REFERENCES entity_events(event_id),
    result_id TEXT NOT NULL UNIQUE REFERENCES entity_coordinator_results(result_id),
    receipt_id TEXT NOT NULL UNIQUE REFERENCES entity_commit_receipts(receipt_id),
    consumed_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_outbox (
    outbox_sequence INTEGER PRIMARY KEY,
    outbox_id TEXT NOT NULL UNIQUE,
    result_id TEXT NOT NULL REFERENCES entity_coordinator_results(result_id),
    entity_state_id TEXT NOT NULL REFERENCES entity_states(entity_state_id),
    intent_json TEXT NOT NULL,
    intent_hash TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_outbox_deliveries (
    delivery_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id TEXT NOT NULL UNIQUE,
    delivery_hash TEXT NOT NULL UNIQUE,
    outbox_id TEXT NOT NULL UNIQUE REFERENCES entity_outbox(outbox_id),
    delivery_reference TEXT NOT NULL UNIQUE,
    delivery_json TEXT NOT NULL,
    delivered_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_checkpoints (
    checkpoint_sequence INTEGER PRIMARY KEY,
    checkpoint_id TEXT NOT NULL UNIQUE,
    checkpoint_hash TEXT NOT NULL UNIQUE,
    entity_state_id TEXT NOT NULL UNIQUE REFERENCES entity_states(entity_state_id),
    state_version INTEGER NOT NULL UNIQUE,
    state_chain_hash TEXT NOT NULL,
    event_head_id TEXT REFERENCES entity_events(event_id),
    event_sequence INTEGER NOT NULL,
    event_chain_hash TEXT NOT NULL,
    receipt_id TEXT NOT NULL UNIQUE REFERENCES entity_commit_receipts(receipt_id),
    receipt_hash TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_activation_commits (
    activation_sequence INTEGER PRIMARY KEY CHECK(activation_sequence=1),
    activation_record_id TEXT NOT NULL UNIQUE,
    activation_record_hash TEXT NOT NULL UNIQUE,
    evidence_bundle_id TEXT NOT NULL UNIQUE,
    evidence_bundle_hash TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    record_content_hash TEXT NOT NULL UNIQUE,
    evidence_content_hash TEXT NOT NULL UNIQUE,
    state_before_id TEXT NOT NULL UNIQUE REFERENCES entity_states(entity_state_id),
    state_after_id TEXT NOT NULL UNIQUE REFERENCES entity_states(entity_state_id),
    receipt_id TEXT NOT NULL UNIQUE REFERENCES entity_commit_receipts(receipt_id),
    committed_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_head (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    entity_state_id TEXT NOT NULL UNIQUE REFERENCES entity_states(entity_state_id),
    state_version INTEGER NOT NULL,
    state_chain_hash TEXT NOT NULL,
    event_head_id TEXT REFERENCES entity_events(event_id),
    event_sequence INTEGER NOT NULL,
    event_chain_hash TEXT NOT NULL,
    receipt_id TEXT NOT NULL UNIQUE REFERENCES entity_commit_receipts(receipt_id),
    receipt_hash TEXT NOT NULL,
    commit_sequence INTEGER NOT NULL,
    checkpoint_id TEXT NOT NULL UNIQUE REFERENCES entity_checkpoints(checkpoint_id)
);

{_APPEND_ONLY_TRIGGER_SQL}
CREATE TRIGGER IF NOT EXISTS entity_head_no_delete
BEFORE DELETE ON entity_head BEGIN SELECT RAISE(ABORT,'entity head cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS entity_head_contiguous_update
BEFORE UPDATE ON entity_head
WHEN NEW.singleton != OLD.singleton
  OR NEW.state_version != OLD.state_version + 1
  OR NEW.event_sequence <= OLD.event_sequence
  OR NEW.commit_sequence != OLD.commit_sequence + 1
BEGIN SELECT RAISE(ABORT,'entity head CAS transition is not contiguous'); END;
COMMIT;
"""


__all__ = [
    "ENTITY_STORE_POLICY_VERSION",
    "ENTITY_STORE_SCHEMA_VERSION",
    "EntityCheckpointRecord",
    "EntityCommitReceipt",
    "EntityIngressRecord",
    "EntityOutboxDeliveryRecord",
    "EntityOutboxRecord",
    "EntityRestartSnapshot",
    "EntityStateReceiptLineage",
    "EntityStore",
    "EntityStoreError",
    "EntityStoreIntegrityResult",
    "default_entity_database_path",
]
