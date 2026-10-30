"""Append-only persistence for the cognition layer of one durable Entity.

This sidecar does not create an Entity.  Every initialization, append, and
read verifies the canonical :class:`EntityStore`, binds to its stable
``instance_id`` and IdentityState ancestry, and records the exact Entity state
head observed for each new record.  The separate schema avoids silently
migrating the already activated EntityStore contract.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

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
from .entity_cognition import (
    DurableAttentionRecord,
    DurableMemoryRecord,
    DurableObjectiveRecord,
)
from .entity_events import LoopName
from .entity_state import EntityOperatingMode, SE6EntityState
from .entity_store import (
    EntityRestartSnapshot,
    EntityStateReceiptLineage,
    EntityStore,
)
from .production_state_paths import trusted_local_state_root

COGNITION_STORE_SCHEMA_VERSION = 1
COGNITION_STORE_POLICY_VERSION = "se6-entity-cognition-store-v1"
COGNITION_STORE_RELATIVE_PATH = (
    Path("SE6Triad") / "entity" / "se6triad_cognition.sqlite3"
)

_ZERO_HASH = "0" * 64
_HASH = r"^[0-9a-f]{64}$"
_ENTITY_ID = r"^instance_[0-9a-f]{64}$"
_IDENTITY_ID = r"^identity_[0-9a-f]{64}$"
_ENTITY_STATE_ID = r"^entity_state_[0-9a-f]{64}$"
_LOOP_ID = r"^se6_loop_[0-9a-f]{64}$"


class CognitionStoreError(RuntimeError):
    """Stable, non-secret refusal from the cognition persistence boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _StoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CognitionStorePolicy(_StoreModel):
    schema_version: Literal["se6-entity-cognition-store-policy-v1"] = (
        "se6-entity-cognition-store-policy-v1"
    )
    maximum_records: StrictInt = Field(default=100_000, ge=1, le=1_000_000)
    maximum_active_attention: StrictInt = Field(default=64, ge=1, le=256)
    network_authority: Literal["NONE"] = "NONE"
    external_requests: Literal["BLOCKED"] = "BLOCKED"
    model_calls_allowed: Literal[False] = False
    shell_allowed: Literal[False] = False
    subprocess_allowed: Literal[False] = False


class CognitionEntityBindingRecord(_StoreModel):
    schema_version: Literal["se6-cognition-entity-binding-v1"] = (
        "se6-cognition-entity-binding-v1"
    )
    binding_id: StrictStr = Field(pattern=r"^cognition_binding_[0-9a-f]{64}$")
    binding_hash: StrictStr = Field(pattern=_HASH)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    root_identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    root_identity_state_hash: StrictStr = Field(pattern=_HASH)
    root_entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    root_entity_state_hash: StrictStr = Field(pattern=_HASH)
    root_runtime_session_id: StrictStr = Field(min_length=1, max_length=512)
    presence_loop_id: StrictStr = Field(pattern=_LOOP_ID)
    awareness_loop_id: StrictStr = Field(pattern=_LOOP_ID)
    becoming_loop_id: StrictStr = Field(pattern=_LOOP_ID)
    created_at_utc: datetime
    network_authority: Literal["NONE"] = "NONE"
    external_requests: Literal["BLOCKED"] = "BLOCKED"
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("created_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "created_at_utc")

    @model_validator(mode="after")
    def binding_is_canonical(self) -> CognitionEntityBindingRecord:
        expected_loops = _loop_ids(self.entity_id)
        if self.loop_ids != expected_loops:
            raise ValueError("cognition binding loop identities mismatch")
        expected = canonical_sha256(self.material_fields())
        if self.binding_hash != expected:
            raise ValueError("cognition binding hash mismatch")
        if self.binding_id != f"cognition_binding_{expected}":
            raise ValueError("cognition binding ID mismatch")
        return self

    @property
    def loop_ids(self) -> tuple[str, str, str]:
        return (
            self.presence_loop_id,
            self.awareness_loop_id,
            self.becoming_loop_id,
        )

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"binding_id", "binding_hash"}
        )


class CognitionEntityBinding(_StoreModel):
    binding: CognitionEntityBindingRecord
    current_identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    current_identity_state_hash: StrictStr = Field(pattern=_HASH)
    current_entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    current_entity_state_hash: StrictStr = Field(pattern=_HASH)
    current_entity_state_version: StrictInt = Field(ge=0)

    @property
    def entity_id(self) -> str:
        return self.binding.entity_id

    @property
    def loop_ids(self) -> tuple[str, str, str]:
        return self.binding.loop_ids


class CognitionStoreAudit(_StoreModel):
    schema_version: Literal["se6-entity-cognition-store-audit-v1"] = (
        "se6-entity-cognition-store-audit-v1"
    )
    status: Literal["ABSENT", "VALID", "INVALID"]
    present: StrictBool
    valid: StrictBool
    entity_id: StrictStr | None = None
    identity_state_id: StrictStr | None = None
    current_entity_state_id: StrictStr | None = None
    binding_id: StrictStr | None = None
    record_count: StrictInt = Field(ge=0)
    memory_record_count: StrictInt = Field(ge=0)
    objective_record_count: StrictInt = Field(ge=0)
    attention_record_count: StrictInt = Field(ge=0)
    trigger_record_count: StrictInt = Field(default=0, ge=0)
    cycle_record_count: StrictInt = Field(default=0, ge=0)
    controlled_observation_proposal_count: StrictInt = Field(default=0, ge=0)
    capability_grant_count: StrictInt = Field(default=0, ge=0)
    audit_record_count: StrictInt = Field(default=0, ge=0)
    retrieval_observation_count: StrictInt = Field(default=0, ge=0)
    online_execution_count: StrictInt = Field(default=0, ge=0)
    record_chain_head: StrictStr | None = Field(default=None, pattern=_HASH)
    network_authority: Literal["NONE"] = "NONE"
    external_requests: Literal["BLOCKED"] = "BLOCKED"
    reason_codes: tuple[StrictStr, ...] = ()


def default_cognition_database_path() -> Path:
    path = (
        trusted_local_state_root() / COGNITION_STORE_RELATIVE_PATH
    ).resolve(strict=False)
    repository = Path(__file__).resolve(strict=False).parents[1]
    if path == repository or repository in path.parents:
        raise CognitionStoreError("COGNITION_PATH_INSIDE_REPOSITORY")
    return path


class EntityCognitionStore:
    """One append-only cognition ledger bound to one canonical EntityStore."""

    def __init__(
        self,
        *,
        entity_store: EntityStore,
        path: Path | None = None,
        policy: CognitionStorePolicy | None = None,
        _test_only: bool = False,
    ) -> None:
        if not isinstance(entity_store, EntityStore):
            raise TypeError("entity_store must be EntityStore")
        if path is not None and not _test_only:
            raise ValueError("explicit cognition database paths are test-only")
        if _test_only and path is None:
            raise ValueError("test cognition store requires an explicit path")
        if _test_only != entity_store.is_test_store:
            raise ValueError("cognition and Entity stores must share test mode")
        self.entity_store = entity_store
        self.path = (
            Path(path).expanduser().resolve(strict=False)
            if path is not None
            else default_cognition_database_path()
        )
        self.policy = policy or CognitionStorePolicy()
        self.test_only = _test_only
        # One immutable proof, never a cached dashboard/state projection. Every
        # reuse rechecks the full database image and verified Entity lineage.
        self._verified_cognition_audit: tuple[
            tuple[str, str, bytes], CognitionStoreAudit
        ] | None = None
        repository = Path(__file__).resolve(strict=False).parents[1]
        if self.path == repository or repository in self.path.parents:
            raise ValueError("cognition database must remain outside the repository")
        if self.path == self.entity_store.path:
            raise ValueError("cognition sidecar cannot alias the EntityStore")
        if _test_only:
            production = default_cognition_database_path()
            if self.path == production or production.parent in self.path.parents:
                raise ValueError("test cognition store cannot alias production state")

    @classmethod
    def for_testing(
        cls,
        path: Path,
        *,
        entity_store: EntityStore,
        policy: CognitionStorePolicy | None = None,
    ) -> EntityCognitionStore:
        return cls(
            entity_store=entity_store,
            path=path,
            policy=policy,
            _test_only=True,
        )

    def initialize(self, *, created_at_utc: datetime) -> CognitionEntityBinding:
        """Create or verify this sidecar without changing the EntityStore."""

        snapshot = self._entity_snapshot()
        at = _utc(created_at_utc, "created_at_utc")
        connection = self._connect()
        try:
            connection.executescript(_SCHEMA_SQL)
            row = connection.execute(
                "SELECT schema_version,policy_version FROM cognition_store_schema "
                "WHERE singleton=1"
            ).fetchone()
            if row is None or tuple(row) != (
                COGNITION_STORE_SCHEMA_VERSION,
                COGNITION_STORE_POLICY_VERSION,
            ):
                raise CognitionStoreError("COGNITION_SCHEMA_VERSION_MISMATCH")
            existing = connection.execute(
                "SELECT binding_json FROM cognition_entity_binding WHERE singleton=1"
            ).fetchone()
            if existing is None:
                binding = _create_binding(
                    snapshot.state,
                    snapshot.latest_receipt.runtime_session_id,
                    at,
                )
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO cognition_entity_binding(" 
                    "singleton,binding_id,binding_hash,binding_json) VALUES(1,?,?,?)",
                    (
                        binding.binding_id,
                        binding.binding_hash,
                        _model_json(binding),
                    ),
                )
                connection.execute("COMMIT")
            else:
                binding = _binding_from_json(existing["binding_json"])
            self._validate_binding_against_state(binding, snapshot.state)
            return _project_binding(binding, snapshot.state)
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def presentation_binding(
        self,
        *,
        audited_state: SE6EntityState,
    ) -> CognitionEntityBinding:
        """Project the immutable cognition binding for an already-audited Entity.

        SE6_PRESENTATION_BINDING_FROM_AUDITED_STATE_R1

        This is a dashboard/presentation read only. It grants no authority,
        performs no mutation and makes no claim about cognition record history.
        The caller must already possess the Entity state from the successful
        Entity integrity projection in the same dashboard request.

        The normal binding() method retains its existing full cognition-audit
        semantics for operational and consequential callers.
        """
        if not isinstance(audited_state, SE6EntityState):
            raise TypeError(
                "audited_state must be a SE6EntityState"
            )

        # Canonical defensive copy. Never trust a mutable caller projection.
        state = SE6EntityState.model_validate_json(
            audited_state.model_dump_json()
        )

        connection = self._connect(
            read_only=True
        )

        try:
            # Pin one read-only SQLite image. No writer reservation.
            connection.execute("BEGIN")

            schema = connection.execute(
                "SELECT schema_version,policy_version "
                "FROM cognition_store_schema WHERE singleton=1"
            ).fetchone()

            if (
                schema is None
                or tuple(schema)
                != (
                    COGNITION_STORE_SCHEMA_VERSION,
                    COGNITION_STORE_POLICY_VERSION,
                )
            ):
                raise CognitionStoreError(
                    "COGNITION_SCHEMA_VERSION_MISMATCH"
                )

            # The immutable binding contract must still be physically enforced.
            trigger_rows = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='trigger'"
            ).fetchall()

            trigger_names = {
                str(row["name"])
                for row in trigger_rows
            }

            if not _REQUIRED_TRIGGERS.issubset(
                trigger_names
            ):
                raise CognitionStoreError(
                    "COGNITION_TRIGGER_SET_INVALID"
                )

            count_row = connection.execute(
                "SELECT COUNT(*) AS n "
                "FROM cognition_entity_binding"
            ).fetchone()

            if (
                count_row is None
                or int(count_row["n"]) != 1
            ):
                raise CognitionStoreError(
                    "COGNITION_BINDING_CARDINALITY_INVALID"
                )

            row = connection.execute(
                "SELECT binding_json "
                "FROM cognition_entity_binding "
                "WHERE singleton=1"
            ).fetchone()

            if row is None:
                raise CognitionStoreError(
                    "COGNITION_BINDING_MISSING"
                )

            # _binding_from_json performs canonical model/hash validation.
            binding = _binding_from_json(
                row["binding_json"]
            )

            # Bind the persisted immutable cognition root to the exact Entity
            # state that was already integrity-verified in this same response.
            self._validate_binding_against_state(
                binding,
                state,
            )

            return _project_binding(
                binding,
                state,
            )

        except sqlite3.DatabaseError as exc:
            raise CognitionStoreError(
                "COGNITION_STORE_INVALID"
            ) from exc

        finally:
            connection.close()


    def binding(
        self,
        *,
        audited_state: SE6EntityState | None = None,
        presentation_only: bool = False,
    ) -> CognitionEntityBinding:
        # SE6_PRESENTATION_ONLY_BINDING_ROUTE_R2
        # Keep binding() as the stable presentation interception point.
        # Default callers retain the complete cognition audit below.
        if presentation_only:
            if audited_state is None:
                raise CognitionStoreError(
                    "COGNITION_PRESENTATION_STATE_REQUIRED"
                )
            return self.presentation_binding(
                audited_state=audited_state
            )

        audit = self.audit_read_only()
        if not audit.valid:
            raise CognitionStoreError(
                audit.reason_codes[0] if audit.reason_codes else "COGNITION_STORE_INVALID"
            )
        state = (
            self._entity_snapshot().state if audited_state is None
            else SE6EntityState.model_validate_json(audited_state.model_dump_json())
        )
        connection = self._connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT binding_json FROM cognition_entity_binding WHERE singleton=1"
            ).fetchone()
            if row is None:
                raise CognitionStoreError("COGNITION_BINDING_MISSING")
            binding = _binding_from_json(row["binding_json"])
            self._validate_binding_against_state(binding, state)
            return _project_binding(binding, state)
        finally:
            connection.close()

    def append_memory(self, record: DurableMemoryRecord) -> DurableMemoryRecord:
        state = self._require_record_binding(record)
        prior = self.memory_records()
        latest = next(
            (item for item in reversed(prior) if item.subject == record.subject),
            None,
        )
        expected_previous = latest.memory_id if latest is not None else None
        if record.previous_memory_id != expected_previous:
            raise CognitionStoreError("MEMORY_ANCESTRY_MISMATCH")
        self._append_record(
            record_type="MEMORY",
            record_id=record.memory_id,
            record=record,
            recorded_at_utc=record.recorded_at_utc,
            state=state,
        )
        return record

    def memory_records(self) -> tuple[DurableMemoryRecord, ...]:
        return self._typed_records("MEMORY", DurableMemoryRecord)

    def active_memory(self) -> tuple[DurableMemoryRecord, ...]:
        latest: dict[str, DurableMemoryRecord] = {}
        for record in self.memory_records():
            latest[record.subject] = record
        return tuple(item for item in latest.values() if item.active)

    def append_objective(
        self, record: DurableObjectiveRecord
    ) -> DurableObjectiveRecord:
        state = self._require_record_binding(record)
        records = self.objective_records()
        revisions = tuple(
            item for item in records if item.objective_id == record.objective_id
        )
        latest = revisions[-1] if revisions else None
        if latest is None:
            if record.revision != 1 or record.previous_objective_record_id is not None:
                raise CognitionStoreError("OBJECTIVE_ANCESTRY_MISMATCH")
        elif (
            record.revision != latest.revision + 1
            or record.previous_objective_record_id != latest.objective_record_id
            or record.created_at_utc != latest.created_at_utc
        ):
            raise CognitionStoreError("OBJECTIVE_ANCESTRY_MISMATCH")
        if record.derived:
            parent = next(
                (
                    item
                    for item in reversed(records)
                    if item.objective_id == record.parent_objective_id
                ),
                None,
            )
            if parent is None:
                raise CognitionStoreError("OBJECTIVE_PARENT_NOT_FOUND")
            if (
                record.governing_authority_reference
                != parent.governing_authority_reference
                or not set(record.authority_scope).issubset(parent.authority_scope)
                or not set(record.required_capabilities).issubset(
                    parent.required_capabilities
                )
            ):
                raise CognitionStoreError("OBJECTIVE_AUTHORITY_ESCALATION")
        self._append_record(
            record_type="OBJECTIVE",
            record_id=record.objective_record_id,
            record=record,
            recorded_at_utc=record.updated_at_utc,
            state=state,
        )
        return record

    def objective_records(self) -> tuple[DurableObjectiveRecord, ...]:
        return self._typed_records("OBJECTIVE", DurableObjectiveRecord)

    def current_objectives(self) -> tuple[DurableObjectiveRecord, ...]:
        latest: dict[str, DurableObjectiveRecord] = {}
        for record in self.objective_records():
            latest[record.objective_id] = record
        return tuple(latest.values())

    def append_attention(
        self, record: DurableAttentionRecord
    ) -> DurableAttentionRecord:
        state = self._require_record_binding(record)
        active = list(self.active_attention(at_utc=record.recorded_at_utc))
        if record.supersedes_attention_id is not None:
            active = [
                item
                for item in active
                if item.attention_id != record.supersedes_attention_id
            ]
        if record.current and len(active) >= self.policy.maximum_active_attention:
            raise CognitionStoreError("ATTENTION_BOUND_EXCEEDED")
        self._append_record(
            record_type="ATTENTION",
            record_id=record.attention_id,
            record=record,
            recorded_at_utc=record.recorded_at_utc,
            state=state,
        )
        return record

    def attention_records(self) -> tuple[DurableAttentionRecord, ...]:
        return self._typed_records("ATTENTION", DurableAttentionRecord)

    def active_attention(
        self, *, at_utc: datetime
    ) -> tuple[DurableAttentionRecord, ...]:
        instant = _utc(at_utc, "at_utc")
        latest: dict[str, DurableAttentionRecord] = {}
        superseded: set[str] = set()
        for record in self.attention_records():
            latest[record.subject] = record
            if record.supersedes_attention_id is not None:
                superseded.add(record.supersedes_attention_id)
        active = tuple(
            record
            for record in latest.values()
            if record.current
            and record.attention_id not in superseded
            and (record.expires_at_utc is None or record.expires_at_utc >= instant)
        )
        return tuple(
            sorted(
                active,
                key=lambda item: (-item.score, item.recorded_at_utc, item.attention_id),
            )
        )

    def append_raw_record(
        self,
        *,
        record_type: str,
        record_id: str,
        record: BaseModel,
        recorded_at_utc: datetime,
        dedupe_key: str | None = None,
    ) -> None:
        """Internal shared ledger API for scheduler and gateway contracts."""

        _validate_payload(record_type, record.model_dump(mode="json"))
        state = self._require_record_binding(record)
        self._append_record(
            record_type=record_type,
            record_id=record_id,
            record=record,
            recorded_at_utc=recorded_at_utc,
            state=state,
            dedupe_key=dedupe_key,
        )

    def append_raw_records(
        self,
        records: Sequence[
            tuple[str, str, BaseModel, datetime, str | None]
        ],
        *,
        accepted_ancestor_entity_state_id: str | None = None,
    ) -> None:
        """Append one ordered evidence bundle in a single ledger transaction."""

        if not records:
            raise ValueError("records must not be empty")
        if accepted_ancestor_entity_state_id is not None:
            anchored_grants = tuple(
                record
                for record_type, _record_id, record, _at, _dedupe in records
                if record_type == "CAPABILITY_GRANT"
                and record.model_dump(mode="python").get("entity_state_id")
                == accepted_ancestor_entity_state_id
            )
            if len(anchored_grants) != 1:
                raise CognitionStoreError(
                    "COGNITION_ANCESTOR_GRANT_BUNDLE_INVALID"
                )
        prepared = []
        state = self._entity_snapshot().state
        lineage = (
            self.entity_store.state_receipt_lineage_read_only()
            if accepted_ancestor_entity_state_id is not None
            else None
        )
        for record_type, record_id, record, recorded_at_utc, dedupe_key in records:
            payload = record.model_dump(mode="json")
            _validate_payload(record_type, payload)
            current = self._require_record_binding(
                record,
                record_type=record_type,
                accepted_ancestor_entity_state_id=(
                    accepted_ancestor_entity_state_id
                    if record_type == "CAPABILITY_GRANT"
                    else None
                ),
                state=state,
                lineage=lineage,
            )
            if current.entity_state_id != state.entity_state_id:
                raise CognitionStoreError("COGNITION_BUNDLE_STATE_MISMATCH")
            prepared.append(
                (
                    record_type,
                    record_id,
                    payload,
                    _utc(recorded_at_utc, "recorded_at_utc"),
                    dedupe_key,
                )
            )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._audit_ledger_connection(connection)
            for record_type, record_id, payload, at, dedupe_key in prepared:
                self._append_record_connection(
                    connection,
                    record_type=record_type,
                    record_id=record_id,
                    payload=payload,
                    recorded_at_utc=at,
                    state=state,
                    dedupe_key=dedupe_key,
                )
            connection.execute("COMMIT")
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def append_capability_evaluation(
        self,
        *,
        grant_id: str,
        requested_at_utc: datetime,
        requested_bytes: int,
        requested_elapsed_ms: int,
        maximum_requests: int | None,
        maximum_bytes: int | None,
        maximum_elapsed_ms: int | None,
        rate_limit_requests: int | None,
        rate_window_seconds: int | None,
        base_reason_codes: Sequence[str],
        record_factory: Callable[
            [tuple[str, ...], SE6EntityState], tuple[BaseModel, BaseModel]
        ],
    ) -> tuple[BaseModel, BaseModel]:
        """Atomically reserve capability budget and append its decision audit."""

        if not callable(record_factory):
            raise TypeError("record_factory must be callable")
        at = _utc(requested_at_utc, "requested_at_utc")
        state = self._entity_snapshot().state
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._audit_ledger_connection(connection)
            rows = connection.execute(
                "SELECT record_type,payload_json FROM cognition_records "
                "WHERE record_type IN ('CAPABILITY_AUDIT','CAPABILITY_REVOCATION') "
                "ORDER BY record_sequence"
            ).fetchall()
            audits = [
                json.loads(row["payload_json"])
                for row in rows
                if row["record_type"] == "CAPABILITY_AUDIT"
            ]
            revocations = [
                json.loads(row["payload_json"])
                for row in rows
                if row["record_type"] == "CAPABILITY_REVOCATION"
            ]
            reasons = list(base_reason_codes)
            if any(
                item.get("grant_id") == grant_id
                and isinstance(item.get("revoked_at_utc"), str)
                and _parse_time(item["revoked_at_utc"]) <= at
                for item in revocations
            ):
                reasons.append("CAPABILITY_GRANT_REVOKED")
            evaluations = tuple(
                item
                for item in audits
                if item.get("operation") == "REQUEST_EVALUATED"
                and item.get("grant_id") == grant_id
            )
            if any(
                isinstance(item.get("recorded_at_utc"), str)
                and _parse_time(item["recorded_at_utc"]) > at
                for item in evaluations
            ):
                reasons.append("CAPABILITY_REQUEST_TIME_NON_MONOTONIC")
            prior = tuple(
                item
                for item in evaluations
                if isinstance(item.get("recorded_at_utc"), str)
                and _parse_time(item["recorded_at_utc"]) <= at
            )
            successful = tuple(item for item in prior if item.get("allowed") is True)
            request_budget_exceeded = (
                maximum_requests is not None
                and len(successful) >= maximum_requests
            )
            byte_budget_exceeded = maximum_bytes is not None and (
                sum(int(item.get("requested_bytes", 0)) for item in successful)
                + requested_bytes
                > maximum_bytes
            )
            elapsed_budget_exceeded = maximum_elapsed_ms is not None and (
                sum(
                    int(item.get("requested_elapsed_ms", 0))
                    for item in successful
                )
                + requested_elapsed_ms
                > maximum_elapsed_ms
            )
            if (
                request_budget_exceeded
                or byte_budget_exceeded
                or elapsed_budget_exceeded
            ):
                reasons.append("CAPABILITY_REQUEST_BUDGET_EXCEEDED")
            if rate_limit_requests is not None and rate_window_seconds is not None:
                window_start = at.timestamp() - rate_window_seconds
                attempts = tuple(
                    item
                    for item in prior
                    if _parse_time(item["recorded_at_utc"]).timestamp()
                    >= window_start
                )
                if len(attempts) >= rate_limit_requests:
                    reasons.append("CAPABILITY_RATE_LIMIT_EXCEEDED")
            normalized_reasons = tuple(dict.fromkeys(reasons))
            decision, audit = record_factory(normalized_reasons, state)
            decision_payload = decision.model_dump(mode="json")
            audit_payload = audit.model_dump(mode="json")
            if (
                audit_payload.get("decision_id")
                != decision_payload.get("decision_id")
                or audit_payload.get("reason_codes")
                != decision_payload.get("reason_codes")
                or audit_payload.get("allowed") != decision_payload.get("allowed")
                or audit_payload.get("entity_state_id") != state.entity_state_id
            ):
                raise CognitionStoreError("CAPABILITY_DECISION_AUDIT_MISMATCH")
            _validate_payload("CAPABILITY_AUDIT", audit_payload)
            self._append_record_connection(
                connection,
                record_type="CAPABILITY_AUDIT",
                record_id=str(audit_payload.get("audit_id")),
                payload=audit_payload,
                recorded_at_utc=at,
                state=state,
                dedupe_key=None,
            )
            connection.execute("COMMIT")
            return decision, audit
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def authority_binding_read_only(
        self, state: SE6EntityState
    ) -> CognitionEntityBinding:
        """Validate the immutable binding and current ledger tail in bounded time."""

        connection = self._connect(read_only=True)
        try:
            binding = self._bounded_authority_binding_connection(
                connection, state
            )
            return _project_binding(binding, state)
        finally:
            connection.close()

    def exact_capability_unused_read_only(
        self,
        *,
        grant_id: str,
        request_id: str,
    ) -> bool:
        """Return whether an exact prospective capability has no durable use."""

        connection = self._connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT record_type,payload_json FROM cognition_records "
                "WHERE record_id IN (?,?) OR ("
                "record_type IN ('CAPABILITY_REVOCATION','CAPABILITY_AUDIT') "
                "AND json_extract(payload_json,'$.grant_id')=?)",
                (grant_id, request_id, grant_id),
            ).fetchall()
            return not rows
        except sqlite3.DatabaseError as exc:
            raise CognitionStoreError("COGNITION_CAPABILITY_STATE_INVALID") from exc
        finally:
            connection.close()

    def append_prevalidated_capability_consumption(
        self,
        *,
        grant: BaseModel,
        grant_audit: BaseModel,
        request_audit: BaseModel,
        state: SE6EntityState,
        expected_binding_id: str,
    ) -> None:
        """Atomically append one pre-audited exact grant and its sole use.

        The caller must have completed a full eligibility audit before review
        and a bounded authority-head check immediately before this operation.
        """

        records = (
            ("CAPABILITY_GRANT", grant),
            ("CAPABILITY_AUDIT", grant_audit),
            ("CAPABILITY_AUDIT", request_audit),
        )
        prepared: list[tuple[str, str, dict[str, Any], datetime]] = []
        for record_type, record in records:
            payload = record.model_dump(mode="json")
            _validate_payload(record_type, payload)
            record_id = str(payload[_id_field(record_type)])
            recorded_at = (
                getattr(record, "issued_at_utc")
                if record_type == "CAPABILITY_GRANT"
                else getattr(record, "recorded_at_utc")
            )
            prepared.append(
                (
                    record_type,
                    record_id,
                    payload,
                    _utc(recorded_at, "recorded_at_utc"),
                )
            )
        grant_payload = prepared[0][2]
        request_audit_payload = prepared[2][2]
        grant_id = str(grant_payload["grant_id"])
        request_id = str(request_audit_payload["request_id"])
        if (
            grant_payload.get("entity_id") != state.identity.instance_id
            or grant_payload.get("identity_state_id")
            != state.identity.identity_state_id
            or request_audit_payload.get("grant_id") != grant_id
            or request_audit_payload.get("allowed") is not True
        ):
            raise CognitionStoreError("COGNITION_CAPABILITY_BINDING_MISMATCH")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            binding = self._bounded_authority_binding_connection(
                connection, state
            )
            if binding.binding_id != expected_binding_id:
                raise CognitionStoreError("COGNITION_BINDING_MISMATCH")
            conflicts = connection.execute(
                "SELECT 1 FROM cognition_records WHERE record_id IN (?,?,?) "
                "OR (record_type IN ('CAPABILITY_REVOCATION','CAPABILITY_AUDIT') "
                "AND json_extract(payload_json,'$.grant_id')=?) LIMIT 1",
                (
                    prepared[0][1],
                    prepared[1][1],
                    prepared[2][1],
                    grant_id,
                ),
            ).fetchone()
            if conflicts is not None:
                raise CognitionStoreError("CAPABILITY_CONSUMPTION_REPLAY_REJECTED")
            for record_type, record_id, payload, at in prepared:
                self._append_record_connection(
                    connection,
                    record_type=record_type,
                    record_id=record_id,
                    payload=payload,
                    recorded_at_utc=at,
                    state=state,
                    dedupe_key=None,
                )
            connection.execute("COMMIT")
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def _bounded_authority_binding_connection(
        self,
        connection: sqlite3.Connection,
        state: SE6EntityState,
    ) -> CognitionEntityBindingRecord:
        schema = connection.execute(
            "SELECT schema_version,policy_version FROM cognition_store_schema "
            "WHERE singleton=1"
        ).fetchone()
        if schema is None or tuple(schema) != (
            COGNITION_STORE_SCHEMA_VERSION,
            COGNITION_STORE_POLICY_VERSION,
        ):
            raise CognitionStoreError("COGNITION_SCHEMA_VERSION_MISMATCH")
        triggers = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        if not _REQUIRED_TRIGGERS.issubset(triggers):
            raise CognitionStoreError("COGNITION_APPEND_ONLY_TRIGGER_MISSING")
        row = connection.execute(
            "SELECT binding_id,binding_hash,binding_json "
            "FROM cognition_entity_binding WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise CognitionStoreError("COGNITION_BINDING_MISSING")
        binding = _binding_from_json(row["binding_json"])
        if (
            binding.binding_id != row["binding_id"]
            or binding.binding_hash != row["binding_hash"]
            or _model_json(binding) != row["binding_json"]
        ):
            raise CognitionStoreError("COGNITION_BINDING_COLUMN_MISMATCH")
        self._validate_binding_against_state(binding, state)
        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM cognition_records"
            ).fetchone()[0]
        )
        tail = connection.execute(
            "SELECT * FROM cognition_records ORDER BY record_sequence DESC LIMIT 1"
        ).fetchone()
        if (tail is None) != (count == 0):
            raise CognitionStoreError("COGNITION_LEDGER_TAIL_INVALID")
        if tail is not None:
            payload = json.loads(tail["payload_json"])
            material = _row_material(
                sequence=tail["record_sequence"],
                record_type=tail["record_type"],
                record_id=tail["record_id"],
                dedupe_key=tail["dedupe_key"],
                payload_hash=tail["payload_hash"],
                previous_record_hash=tail["previous_record_hash"],
                recorded_at_utc=tail["recorded_at_utc"],
            )
            previous = (
                None
                if tail["record_sequence"] == 1
                else connection.execute(
                    "SELECT record_hash FROM cognition_records "
                    "WHERE record_sequence=?",
                    (tail["record_sequence"] - 1,),
                ).fetchone()
            )
            expected_previous = (
                _ZERO_HASH if previous is None else previous["record_hash"]
            )
            if (
                tail["record_sequence"] != count
                or canonical_sha256(payload) != tail["payload_hash"]
                or canonical_sha256(material) != tail["record_hash"]
                or tail["previous_record_hash"] != expected_previous
            ):
                raise CognitionStoreError("COGNITION_LEDGER_TAIL_INVALID")
        return binding

    def try_append_scheduler_lease(
        self,
        lease: BaseModel,
        *,
        recorded_at_utc: datetime,
    ) -> bool:
        """Atomically acquire one trigger lease across runtime processes."""

        state = self._require_record_binding(lease)
        payload = lease.model_dump(mode="json")
        trigger_id = payload.get("trigger_id")
        acquired_at = payload.get("acquired_at_utc")
        recovered_from = payload.get("recovered_from_lease_id")
        if not isinstance(trigger_id, str) or not isinstance(acquired_at, str):
            raise CognitionStoreError("SCHEDULER_LEASE_INVALID")
        acquired = _parse_time(acquired_at)
        at = _utc(recorded_at_utc, "recorded_at_utc")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._audit_ledger_connection(connection)
            rows = connection.execute(
                "SELECT record_type,payload_json FROM cognition_records "
                "WHERE record_type IN ('SCHEDULER_LEASE','SCHEDULER_CYCLE') "
                "ORDER BY record_sequence"
            ).fetchall()
            leases = [
                json.loads(row["payload_json"])
                for row in rows
                if row["record_type"] == "SCHEDULER_LEASE"
            ]
            cycles = [
                json.loads(row["payload_json"])
                for row in rows
                if row["record_type"] == "SCHEDULER_CYCLE"
            ]
            if any(
                item.get("trigger_id") == trigger_id
                and item.get("status") != "DEFERRED"
                for item in cycles
            ):
                connection.execute("COMMIT")
                return False
            cycle_lease_ids = {
                item.get("lease_id")
                for item in cycles
                if isinstance(item.get("lease_id"), str)
            }
            # A single Entity reducer head permits one outstanding lease,
            # including when contenders selected different priority classes.
            latest_by_trigger = {item.get("trigger_id"): item for item in leases}
            if any(item.get("lease_id") not in cycle_lease_ids
                   and _parse_time(item["expires_at_utc"]) > acquired
                   for item in latest_by_trigger.values()):
                connection.execute("COMMIT")
                return False
            prior = next(
                (
                    item
                    for item in reversed(leases)
                    if item.get("trigger_id") == trigger_id
                ),
                None,
            )
            expected_recovery = None
            if prior is not None and prior.get("lease_id") not in cycle_lease_ids:
                expires_at = prior.get("expires_at_utc")
                if not isinstance(expires_at, str):
                    raise CognitionStoreError("SCHEDULER_LEASE_INVALID")
                if _parse_time(expires_at) > acquired:
                    connection.execute("COMMIT")
                    return False
                expected_recovery = prior.get("lease_id")
            if recovered_from != expected_recovery:
                connection.execute("COMMIT")
                return False
            self._append_record_connection(
                connection,
                record_type="SCHEDULER_LEASE",
                record_id=str(payload.get("lease_id")),
                payload=payload,
                recorded_at_utc=at,
                state=state,
                dedupe_key=None,
            )
            connection.execute("COMMIT")
            return True
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def raw_records(self, record_type: str) -> tuple[dict[str, Any], ...]:
        _binding, records = self.read_raw_snapshot((record_type,))
        return records[record_type]

    def verified_mirror_read_only(self, *, as_of_utc=None):
        """Cognition sees the same Entity through its canonical evidence owner."""
        return self.entity_store.verified_mirror_read_only(
            cognition_store=self, as_of_utc=as_of_utc)

    def _read_mirror_snapshot_from_proof(self, entity_proof):
        """Bind mirror records to one pinned, fully audited cognition image.

        The Entity owner supplies its private pinned audit proof. A separate
        full audit is usable only when its exact image/Entity/receipt subject
        matches this still-open read transaction; summary counts are not proof.
        """
        _, snapshot, lineage = entity_proof.inspection
        connection = self._connect(read_only=True)
        try:
            connection.execute("BEGIN")
            connection.execute("SELECT rootpage FROM sqlite_schema LIMIT 1").fetchone()
            image = hashlib.sha256(connection.serialize()).digest()
            expected = (snapshot.state.state_hash, snapshot.latest_receipt.receipt_hash, image)
            audit = self.audit_read_only(full=True)
            verified = self._verified_cognition_audit
            if not audit.valid or verified is None or verified[0] != expected or not verified[1].valid:
                raise CognitionStoreError("MIRROR_COGNITION_IMAGE_MISMATCH")
            row = connection.execute("SELECT binding_json FROM cognition_entity_binding WHERE singleton=1").fetchone()
            if row is None:
                raise CognitionStoreError("COGNITION_BINDING_MISSING")
            binding = _binding_from_json(row["binding_json"])
            self._validate_binding_against_state(binding, snapshot.state)
            records = {kind: [] for kind in ("MEMORY", "OBJECTIVE", "ATTENTION")}
            for row in connection.execute("SELECT record_type,payload_json FROM cognition_records ORDER BY record_sequence"):
                if row["record_type"] in records:
                    value = json.loads(row["payload_json"])
                    _validate_payload(row["record_type"], value)
                    records[row["record_type"]].append(value)
            return _project_binding(binding, snapshot.state), {
                key: tuple(value) for key, value in records.items()}
        finally:
            connection.close()

    def read_raw_snapshot(
        self, record_types: Sequence[str]
    ) -> tuple[CognitionEntityBinding, dict[str, tuple[dict[str, Any], ...]]]:
        """Return one validated binding and one coherent set of typed records."""

        requested = tuple(dict.fromkeys(record_types))
        if not requested or any(
            item not in {"MEMORY", "OBJECTIVE", "ATTENTION", *_EXTENSION_RECORD_TYPES}
            for item in requested
        ):
            raise CognitionStoreError("COGNITION_RECORD_TYPE_UNSUPPORTED")
        audit = self.audit_read_only()
        if not audit.valid:
            raise CognitionStoreError(
                audit.reason_codes[0] if audit.reason_codes else "COGNITION_STORE_INVALID"
            )
        snapshot = self._entity_snapshot()
        connection = self._connect(read_only=True)
        try:
            binding_row = connection.execute(
                "SELECT binding_json FROM cognition_entity_binding WHERE singleton=1"
            ).fetchone()
            if binding_row is None:
                raise CognitionStoreError("COGNITION_BINDING_MISSING")
            binding = _binding_from_json(binding_row["binding_json"])
            self._validate_binding_against_state(binding, snapshot.state)
            placeholders = ",".join("?" for _ in requested)
            rows = connection.execute(
                "SELECT record_type,payload_json FROM cognition_records "
                f"WHERE record_type IN ({placeholders}) ORDER BY record_sequence",
                requested,
            ).fetchall()
            records = {item: [] for item in requested}
            for row in rows:
                payload = json.loads(row["payload_json"])
                _validate_payload(row["record_type"], payload)
                records[row["record_type"]].append(payload)
            return (
                _project_binding(binding, snapshot.state),
                {key: tuple(value) for key, value in records.items()},
            )
        finally:
            connection.close()

    def audit_read_only(self, *, full: bool = False) -> CognitionStoreAudit:
        if not self.path.is_file():
            self._verified_cognition_audit = None
            return _absent_audit()
        connection: sqlite3.Connection | None = None
        try:
            entity_audit, snapshot, lineage = self.entity_store.inspect_read_only()
            if not entity_audit.valid or snapshot is None or lineage is None:
                raise CognitionStoreError("ENTITY_STORE_NOT_VALID")
            state_ids = {item.entity_state_id for item in lineage.states}
            identity_ids = set(snapshot.state.identity.identity_lineage)
            connection = self._connect(read_only=True)
            # Establish one SQLite read snapshot for the digest AND all audit
            # queries. Concurrent commits cannot change the bytes underneath a
            # successful proof; later readers must compare their own snapshot.
            connection.execute("BEGIN")
            schema = connection.execute(
                "SELECT schema_version,policy_version FROM cognition_store_schema "
                "WHERE singleton=1"
            ).fetchone()
            if schema is None or tuple(schema) != (
                COGNITION_STORE_SCHEMA_VERSION,
                COGNITION_STORE_POLICY_VERSION,
            ):
                raise CognitionStoreError("COGNITION_SCHEMA_VERSION_MISMATCH")
            subject = (
                snapshot.state.state_hash,
                snapshot.latest_receipt.receipt_hash,
                hashlib.sha256(connection.serialize()).digest(),
            )
            verified = self._verified_cognition_audit
            if not full and verified is not None and verified[0] == subject:
                return verified[1]
            triggers = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
            }
            if not _REQUIRED_TRIGGERS.issubset(triggers):
                raise CognitionStoreError("COGNITION_APPEND_ONLY_TRIGGER_MISSING")
            binding_row = connection.execute(
                "SELECT binding_id,binding_hash,binding_json "
                "FROM cognition_entity_binding WHERE singleton=1"
            ).fetchone()
            if binding_row is None:
                raise CognitionStoreError("COGNITION_BINDING_MISSING")
            binding = _binding_from_json(binding_row["binding_json"])
            if (
                binding.binding_id != binding_row["binding_id"]
                or binding.binding_hash != binding_row["binding_hash"]
            ):
                raise CognitionStoreError("COGNITION_BINDING_COLUMN_MISMATCH")
            self._validate_binding_against_state(binding, snapshot.state)
            if binding.root_runtime_session_id not in {
                item.runtime_session_id for item in lineage.receipts
            }:
                raise CognitionStoreError("COGNITION_RUNTIME_ANCESTRY_MISMATCH")
            rows = connection.execute(
                "SELECT * FROM cognition_records ORDER BY record_sequence"
            ).fetchall()
            counts: dict[str, int] = {}
            source_triggers: dict[str, dict[str, Any]] = {}
            source_cycles: dict[str, dict[str, Any]] = {}
            source_objectives: dict[str, dict[str, Any]] = {}
            source_attention: dict[str, dict[str, Any]] = {}
            latest_proposals: dict[str, dict[str, Any]] = {}
            previous = _ZERO_HASH
            for expected_sequence, row in enumerate(rows, start=1):
                if row["record_sequence"] != expected_sequence:
                    raise CognitionStoreError("COGNITION_SEQUENCE_INVALID")
                if row["previous_record_hash"] != previous:
                    raise CognitionStoreError("COGNITION_CHAIN_PREDECESSOR_INVALID")
                payload = json.loads(row["payload_json"])
                if row["payload_json"] != _json(payload):
                    raise CognitionStoreError("COGNITION_JSON_NOT_CANONICAL")
                if canonical_sha256(payload) != row["payload_hash"]:
                    raise CognitionStoreError("COGNITION_PAYLOAD_HASH_INVALID")
                if payload.get("entity_id") != binding.entity_id:
                    raise CognitionStoreError("COGNITION_RECORD_ENTITY_MISMATCH")
                if (
                    payload.get("identity_state_id") is not None
                    and payload["identity_state_id"] not in identity_ids
                ):
                    raise CognitionStoreError("COGNITION_RECORD_IDENTITY_MISMATCH")
                if (
                    payload.get("entity_state_id") is not None
                    and payload["entity_state_id"] not in state_ids
                ):
                    raise CognitionStoreError("COGNITION_RECORD_STATE_MISMATCH")
                _validate_payload(row["record_type"], payload)
                material = _row_material(
                    sequence=row["record_sequence"],
                    record_type=row["record_type"],
                    record_id=row["record_id"],
                    dedupe_key=row["dedupe_key"],
                    payload_hash=row["payload_hash"],
                    previous_record_hash=row["previous_record_hash"],
                    recorded_at_utc=row["recorded_at_utc"],
                )
                if canonical_sha256(material) != row["record_hash"]:
                    raise CognitionStoreError("COGNITION_RECORD_HASH_INVALID")
                if payload.get(_id_field(row["record_type"])) != row["record_id"]:
                    raise CognitionStoreError("COGNITION_RECORD_ID_MISMATCH")
                if row["record_type"] == "CONTROLLED_OBSERVATION_PROPOSAL":
                    _validate_controlled_observation_proposal_link(
                        payload,
                        dedupe_key=row["dedupe_key"],
                        binding=binding,
                        source_triggers=source_triggers,
                        source_cycles=source_cycles,
                        source_objectives=source_objectives,
                        source_attention=source_attention,
                        latest_proposals=latest_proposals,
                    )
                if row["record_type"] == "SCHEDULER_TRIGGER":
                    source_triggers[str(payload["trigger_id"])] = payload
                elif row["record_type"] == "SCHEDULER_CYCLE":
                    source_cycles[str(payload["cycle_id"])] = payload
                elif row["record_type"] == "OBJECTIVE":
                    source_objectives[str(payload["objective_record_id"])] = payload
                elif row["record_type"] == "ATTENTION":
                    source_attention[str(payload["attention_id"])] = payload
                elif row["record_type"] == "CONTROLLED_OBSERVATION_PROPOSAL":
                    latest_proposals[str(payload["schedule_id"])] = payload
                previous = row["record_hash"]
                counts[row["record_type"]] = counts.get(row["record_type"], 0) + 1
            audit = CognitionStoreAudit(
                status="VALID",
                present=True,
                valid=True,
                entity_id=binding.entity_id,
                identity_state_id=snapshot.state.identity.identity_state_id,
                current_entity_state_id=snapshot.state.entity_state_id,
                binding_id=binding.binding_id,
                record_count=len(rows),
                memory_record_count=counts.get("MEMORY", 0),
                objective_record_count=counts.get("OBJECTIVE", 0),
                attention_record_count=counts.get("ATTENTION", 0),
                trigger_record_count=counts.get("SCHEDULER_TRIGGER", 0),
                cycle_record_count=counts.get("SCHEDULER_CYCLE", 0),
                controlled_observation_proposal_count=counts.get(
                    "CONTROLLED_OBSERVATION_PROPOSAL", 0
                ),
                capability_grant_count=counts.get("CAPABILITY_GRANT", 0),
                audit_record_count=counts.get("CAPABILITY_AUDIT", 0),
                retrieval_observation_count=counts.get(
                    "RETRIEVAL_OBSERVATION", 0
                ),
                online_execution_count=counts.get("ONLINE_EXECUTION", 0),
                record_chain_head=previous if rows else None,
                reason_codes=(),
            )
            self._verified_cognition_audit = (subject, audit)
            return audit
        except CognitionStoreError as exc:
            self._verified_cognition_audit = None
            return _invalid_audit(exc.code)
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            sqlite3.DatabaseError,
        ):
            self._verified_cognition_audit = None
            return _invalid_audit("COGNITION_INTEGRITY_VALIDATION_FAILED")
        finally:
            if connection is not None:
                connection.close()

    def _typed_records(
        self, record_type: str, model: type[BaseModel]
    ) -> tuple[Any, ...]:
        return tuple(
            model.model_validate_json(_json(item))
            for item in self.raw_records(record_type)
        )

    def _require_record_binding(
        self,
        record: BaseModel,
        *,
        record_type: str | None = None,
        accepted_ancestor_entity_state_id: str | None = None,
        state: SE6EntityState | None = None,
        lineage: EntityStateReceiptLineage | None = None,
    ) -> SE6EntityState:
        current_state = state or self._entity_snapshot().state
        values = record.model_dump(mode="python")
        if values.get("entity_id") != current_state.identity.instance_id:
            raise CognitionStoreError("COGNITION_RECORD_ENTITY_MISMATCH")
        if values.get("identity_state_id") not in {
            None,
            current_state.identity.identity_state_id,
        }:
            raise CognitionStoreError("COGNITION_RECORD_IDENTITY_MISMATCH")
        record_state_id = values.get("entity_state_id")
        if record_state_id not in {None, current_state.entity_state_id}:
            if not (
                record_type == "CAPABILITY_GRANT"
                and accepted_ancestor_entity_state_id == record_state_id
            ):
                raise CognitionStoreError("COGNITION_RECORD_STATE_MISMATCH")
            verified_lineage = (
                lineage or self.entity_store.state_receipt_lineage_read_only()
            )
            anchors = tuple(
                item
                for item in verified_lineage.states
                if item.entity_state_id == record_state_id
            )
            if (
                len(anchors) != 1
                or verified_lineage.states[-1].entity_state_id
                != current_state.entity_state_id
                or anchors[0].identity.instance_id
                != current_state.identity.instance_id
                or anchors[0].identity.identity_state_id
                != current_state.identity.identity_state_id
            ):
                raise CognitionStoreError(
                    "COGNITION_RECORD_ANCESTOR_BINDING_MISMATCH"
                )
        return current_state

    def _append_record(
        self,
        *,
        record_type: str,
        record_id: str,
        record: BaseModel,
        recorded_at_utc: datetime,
        state: SE6EntityState,
        dedupe_key: str | None = None,
    ) -> None:
        at = _utc(recorded_at_utc, "recorded_at_utc")
        payload = record.model_dump(mode="json")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._audit_ledger_connection(connection)
            self._append_record_connection(
                connection,
                record_type=record_type,
                record_id=record_id,
                payload=payload,
                recorded_at_utc=at,
                state=state,
                dedupe_key=dedupe_key,
            )
            connection.execute("COMMIT")
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def _append_record_connection(
        self,
        connection: sqlite3.Connection,
        *,
        record_type: str,
        record_id: str,
        payload: dict[str, Any],
        recorded_at_utc: datetime,
        state: SE6EntityState,
        dedupe_key: str | None,
    ) -> None:
        if record_type == "CONTROLLED_OBSERVATION_PROPOSAL":
            binding_row = connection.execute(
                "SELECT binding_json FROM cognition_entity_binding WHERE singleton=1"
            ).fetchone()
            if binding_row is None:
                raise CognitionStoreError("COGNITION_BINDING_MISSING")
            context_rows = connection.execute(
                "SELECT record_type,payload_json FROM cognition_records "
                "WHERE record_type IN "
                "('SCHEDULER_TRIGGER','SCHEDULER_CYCLE','OBJECTIVE','ATTENTION',"
                "'CONTROLLED_OBSERVATION_PROPOSAL') "
                "ORDER BY record_sequence"
            ).fetchall()
            source_triggers: dict[str, dict[str, Any]] = {}
            source_cycles: dict[str, dict[str, Any]] = {}
            source_objectives: dict[str, dict[str, Any]] = {}
            source_attention: dict[str, dict[str, Any]] = {}
            latest_proposals: dict[str, dict[str, Any]] = {}
            for row in context_rows:
                context_payload = json.loads(row["payload_json"])
                if row["record_type"] == "SCHEDULER_TRIGGER":
                    source_triggers[
                        str(context_payload["trigger_id"])
                    ] = context_payload
                elif row["record_type"] == "SCHEDULER_CYCLE":
                    source_cycles[str(context_payload["cycle_id"])] = context_payload
                elif row["record_type"] == "OBJECTIVE":
                    source_objectives[
                        str(context_payload["objective_record_id"])
                    ] = context_payload
                elif row["record_type"] == "ATTENTION":
                    source_attention[
                        str(context_payload["attention_id"])
                    ] = context_payload
                else:
                    latest_proposals[
                        str(context_payload["schedule_id"])
                    ] = context_payload
            _validate_controlled_observation_proposal_link(
                payload,
                dedupe_key=dedupe_key,
                binding=_binding_from_json(binding_row["binding_json"]),
                source_triggers=source_triggers,
                source_cycles=source_cycles,
                source_objectives=source_objectives,
                source_attention=source_attention,
                latest_proposals=latest_proposals,
            )
        payload_hash = canonical_sha256(payload)
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM cognition_records"
        ).fetchone()["count"]
        if count >= self.policy.maximum_records:
            raise CognitionStoreError("COGNITION_RECORD_BOUND_EXCEEDED")
        last = connection.execute(
            "SELECT record_sequence,record_hash FROM cognition_records "
            "ORDER BY record_sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if last is None else last["record_sequence"] + 1
        previous = _ZERO_HASH if last is None else last["record_hash"]
        material = _row_material(
            sequence=sequence,
            record_type=record_type,
            record_id=record_id,
            dedupe_key=dedupe_key,
            payload_hash=payload_hash,
            previous_record_hash=previous,
            recorded_at_utc=_time_text(recorded_at_utc),
        )
        record_hash = canonical_sha256(material)
        try:
            connection.execute(
                "INSERT INTO cognition_records(" 
                "record_sequence,record_type,record_id,dedupe_key,payload_json," 
                "payload_hash,previous_record_hash,record_hash,recorded_at_utc," 
                "entity_state_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    sequence,
                    record_type,
                    record_id,
                    dedupe_key,
                    _json(payload),
                    payload_hash,
                    previous,
                    record_hash,
                    _time_text(recorded_at_utc),
                    state.entity_state_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            code = (
                "COGNITION_DEDUPE_REJECTED"
                if dedupe_key is not None
                else "COGNITION_RECORD_REPLAY_REJECTED"
            )
            raise CognitionStoreError(code) from exc

    def _audit_ledger_connection(self, connection: sqlite3.Connection) -> None:
        schema = connection.execute(
            "SELECT schema_version,policy_version FROM cognition_store_schema "
            "WHERE singleton=1"
        ).fetchone()
        if schema is None or tuple(schema) != (
            COGNITION_STORE_SCHEMA_VERSION,
            COGNITION_STORE_POLICY_VERSION,
        ):
            raise CognitionStoreError("COGNITION_SCHEMA_VERSION_MISMATCH")
        binding_row = connection.execute(
            "SELECT binding_json FROM cognition_entity_binding WHERE singleton=1"
        ).fetchone()
        if binding_row is None:
            raise CognitionStoreError("COGNITION_BINDING_MISSING")
        binding = _binding_from_json(binding_row["binding_json"])
        rows = connection.execute(
            "SELECT * FROM cognition_records ORDER BY record_sequence"
        ).fetchall()
        source_triggers: dict[str, dict[str, Any]] = {}
        source_cycles: dict[str, dict[str, Any]] = {}
        source_objectives: dict[str, dict[str, Any]] = {}
        source_attention: dict[str, dict[str, Any]] = {}
        latest_proposals: dict[str, dict[str, Any]] = {}
        previous = _ZERO_HASH
        for expected_sequence, row in enumerate(rows, start=1):
            payload = json.loads(row["payload_json"])
            if (
                row["record_sequence"] != expected_sequence
                or row["previous_record_hash"] != previous
                or canonical_sha256(payload) != row["payload_hash"]
            ):
                raise CognitionStoreError("COGNITION_LEDGER_INVALID")
            material = _row_material(
                sequence=row["record_sequence"],
                record_type=row["record_type"],
                record_id=row["record_id"],
                dedupe_key=row["dedupe_key"],
                payload_hash=row["payload_hash"],
                previous_record_hash=row["previous_record_hash"],
                recorded_at_utc=row["recorded_at_utc"],
            )
            if canonical_sha256(material) != row["record_hash"]:
                raise CognitionStoreError("COGNITION_LEDGER_INVALID")
            if row["record_type"] in {
                "SCHEDULER_CYCLE",
                "CONTROLLED_OBSERVATION_PROPOSAL",
            }:
                _validate_payload(row["record_type"], payload)
                if payload.get(_id_field(row["record_type"])) != row["record_id"]:
                    raise CognitionStoreError("COGNITION_LEDGER_INVALID")
            if row["record_type"] == "CONTROLLED_OBSERVATION_PROPOSAL":
                _validate_controlled_observation_proposal_link(
                    payload,
                    dedupe_key=row["dedupe_key"],
                    binding=binding,
                    source_triggers=source_triggers,
                    source_cycles=source_cycles,
                    source_objectives=source_objectives,
                    source_attention=source_attention,
                    latest_proposals=latest_proposals,
                )
            if row["record_type"] == "SCHEDULER_TRIGGER":
                source_triggers[str(payload["trigger_id"])] = payload
            elif row["record_type"] == "SCHEDULER_CYCLE":
                source_cycles[str(payload["cycle_id"])] = payload
            elif row["record_type"] == "OBJECTIVE":
                source_objectives[str(payload["objective_record_id"])] = payload
            elif row["record_type"] == "ATTENTION":
                source_attention[str(payload["attention_id"])] = payload
            elif row["record_type"] == "CONTROLLED_OBSERVATION_PROPOSAL":
                latest_proposals[str(payload["schedule_id"])] = payload
            previous = row["record_hash"]

    def _entity_snapshot(self) -> EntityRestartSnapshot:
        audit, snapshot, _lineage = self.entity_store.inspect_read_only()
        if not audit.valid or snapshot is None:
            raise CognitionStoreError("ENTITY_STORE_NOT_VALID")
        state = snapshot.state
        if state.operating_mode is not EntityOperatingMode.LOCAL_LIVE:
            raise CognitionStoreError("ENTITY_NOT_LOCAL_LIVE")
        if (
            state.environment_access.online_observation_enabled
            or state.environment_access.network_authority != "NONE"
            or state.environment_access.external_requests != "BLOCKED"
        ):
            raise CognitionStoreError("ENTITY_NETWORK_BOUNDARY_NOT_CLOSED")
        return snapshot

    @staticmethod
    def _validate_binding_against_state(
        binding: CognitionEntityBindingRecord, state: SE6EntityState
    ) -> None:
        if binding.entity_id != state.identity.instance_id:
            raise CognitionStoreError("COGNITION_ENTITY_BINDING_MISMATCH")
        if binding.root_identity_state_id not in state.identity.identity_lineage:
            raise CognitionStoreError("COGNITION_IDENTITY_ANCESTRY_MISMATCH")
        if binding.loop_ids != _loop_ids(state.identity.instance_id):
            raise CognitionStoreError("COGNITION_LOOP_BINDING_MISMATCH")

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro",
                timeout=5,
                isolation_level=None,
                uri=True,
            )
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(self.path), timeout=5, isolation_level=None
            )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        if not read_only:
            connection.execute("PRAGMA synchronous=FULL")
        return connection


def _create_binding(
    state: SE6EntityState,
    runtime_session_id: str,
    created_at_utc: datetime,
) -> CognitionEntityBindingRecord:
    presence, awareness, becoming = _loop_ids(state.identity.instance_id)
    material = {
        "schema_version": "se6-cognition-entity-binding-v1",
        "entity_id": state.identity.instance_id,
        "root_identity_state_id": state.identity.identity_state_id,
        "root_identity_state_hash": state.identity.identity_state_hash,
        "root_entity_state_id": state.entity_state_id,
        "root_entity_state_hash": state.state_hash,
        "root_runtime_session_id": runtime_session_id,
        "presence_loop_id": presence,
        "awareness_loop_id": awareness,
        "becoming_loop_id": becoming,
        "created_at_utc": _utc(created_at_utc, "created_at_utc"),
        "network_authority": "NONE",
        "external_requests": "BLOCKED",
        "authority_effect": "NONE",
    }
    digest = canonical_sha256(material)
    return CognitionEntityBindingRecord(
        binding_id=f"cognition_binding_{digest}",
        binding_hash=digest,
        **material,
    )


def _project_binding(
    binding: CognitionEntityBindingRecord, state: SE6EntityState
) -> CognitionEntityBinding:
    return CognitionEntityBinding(
        binding=binding,
        current_identity_state_id=state.identity.identity_state_id,
        current_identity_state_hash=state.identity.identity_state_hash,
        current_entity_state_id=state.entity_state_id,
        current_entity_state_hash=state.state_hash,
        current_entity_state_version=state.state_version,
    )


def _binding_from_json(value: str) -> CognitionEntityBindingRecord:
    try:
        return CognitionEntityBindingRecord.model_validate_json(value)
    except (ValueError, TypeError) as exc:
        raise CognitionStoreError("COGNITION_BINDING_INVALID") from exc


def _loop_ids(entity_id: str) -> tuple[str, str, str]:
    return tuple(
        f"se6_loop_{canonical_sha256({'entity_id': entity_id, 'loop': loop.value})}"
        for loop in (LoopName.PRESENCE, LoopName.AWARENESS, LoopName.BECOMING)
    )  # type: ignore[return-value]


def _validate_controlled_observation_proposal_link(
    payload: dict[str, Any],
    *,
    dedupe_key: str | None,
    binding: CognitionEntityBindingRecord,
    source_triggers: dict[str, dict[str, Any]],
    source_cycles: dict[str, dict[str, Any]],
    source_objectives: dict[str, dict[str, Any]],
    source_attention: dict[str, dict[str, Any]],
    latest_proposals: dict[str, dict[str, Any]],
) -> None:
    """Bind one proposal to its exact prior cognition-cycle evidence."""

    if dedupe_key != payload.get("deduplication_key"):
        raise CognitionStoreError("COGNITION_PROPOSAL_DEDUPE_MISMATCH")
    proposal_loops = (
        payload.get("presence_loop_id"),
        payload.get("awareness_loop_id"),
        payload.get("becoming_loop_id"),
    )
    if proposal_loops != binding.loop_ids:
        raise CognitionStoreError("COGNITION_PROPOSAL_LOOP_BINDING_MISMATCH")
    source_cycle_id = payload.get("source_cognition_cycle_id")
    source_cycle = (
        source_cycles.get(source_cycle_id)
        if isinstance(source_cycle_id, str)
        else None
    )
    if source_cycle is None:
        raise CognitionStoreError("COGNITION_PROPOSAL_SOURCE_CYCLE_MISSING")
    exact_bindings = (
        payload.get("entity_id") == source_cycle.get("entity_id"),
        payload.get("identity_state_id")
        == source_cycle.get("identity_state_id"),
        payload.get("entity_state_id") == source_cycle.get("entity_state_id"),
        payload.get("runtime_id") == source_cycle.get("runtime_session_id"),
        payload.get("source_trigger_id") == source_cycle.get("trigger_id"),
    )
    if not all(exact_bindings):
        raise CognitionStoreError("COGNITION_PROPOSAL_SOURCE_CYCLE_MISMATCH")

    source_trigger_id = payload.get("source_trigger_id")
    source_trigger = (
        source_triggers.get(source_trigger_id)
        if isinstance(source_trigger_id, str)
        else None
    )
    if source_trigger is None:
        raise CognitionStoreError("COGNITION_PROPOSAL_SOURCE_TRIGGER_MISSING")
    proposal_at = _parse_time(str(payload["created_at_utc"]))
    trigger_bindings = (
        source_trigger.get("trigger_id") == source_cycle.get("trigger_id"),
        source_trigger.get("entity_id") == payload.get("entity_id"),
        source_trigger.get("identity_state_id")
        == payload.get("identity_state_id"),
        source_trigger.get("entity_state_id") == payload.get("entity_state_id"),
        source_trigger.get("trigger_kind") == "LOCAL_TIMER",
        source_trigger.get("source") == "LOCAL_TIMER",
        source_trigger.get("subject_reference") == payload.get("schedule_id"),
        source_trigger.get("payload_hash")
        == payload.get("schedule_record_hash"),
    )
    if not all(trigger_bindings):
        raise CognitionStoreError("COGNITION_PROPOSAL_SOURCE_TRIGGER_MISMATCH")
    if (
        _parse_time(str(source_trigger["observed_at_utc"])) > proposal_at
        or _parse_time(str(source_trigger["created_at_utc"])) > proposal_at
        or _parse_time(str(source_cycle["recorded_at_utc"])) > proposal_at
    ):
        raise CognitionStoreError("COGNITION_PROPOSAL_SOURCE_TIME_INVALID")

    objective_reference = payload.get("objective_reference")
    objective = (
        source_objectives.get(objective_reference)
        if isinstance(objective_reference, str)
        else None
    )
    attention_reference = payload.get("attention_reference")
    attention = (
        source_attention.get(attention_reference)
        if isinstance(attention_reference, str)
        else None
    )
    if objective is None:
        raise CognitionStoreError("COGNITION_PROPOSAL_OBJECTIVE_MISSING")
    if attention is None:
        raise CognitionStoreError("COGNITION_PROPOSAL_ATTENTION_MISSING")
    context_bindings = (
        payload.get("entity_id") == objective.get("entity_id"),
        payload.get("identity_state_id") == objective.get("identity_state_id"),
        payload.get("entity_state_id") == objective.get("entity_state_id"),
        payload.get("entity_id") == attention.get("entity_id"),
        payload.get("identity_state_id") == attention.get("identity_state_id"),
        payload.get("entity_state_id") == attention.get("entity_state_id"),
        objective.get("objective_id") in attention.get("objective_ids", ()),
        payload.get("target_scope_reference") == attention.get("subject"),
        payload.get("information_need")
        == objective.get("completion_condition"),
        payload.get("target_scope_reference")
        in objective.get("authority_scope", ()),
        payload.get("requested_capability")
        in objective.get("required_capabilities", ()),
        objective.get("status") == "ACTIVE",
    )
    if not all(context_bindings):
        raise CognitionStoreError("COGNITION_PROPOSAL_CONTEXT_MISMATCH")
    objective_created = _parse_time(str(objective["created_at_utc"]))
    objective_updated = _parse_time(str(objective["updated_at_utc"]))
    attention_recorded = _parse_time(str(attention["recorded_at_utc"]))
    attention_expires_raw = attention.get("expires_at_utc")
    if (
        objective_created > proposal_at
        or objective_updated > proposal_at
        or attention_recorded > proposal_at
        or attention.get("current") is not True
        or (
            isinstance(attention_expires_raw, str)
            and _parse_time(attention_expires_raw) < proposal_at
        )
    ):
        raise CognitionStoreError("COGNITION_PROPOSAL_CONTEXT_TIME_INVALID")
    current_objective = max(
        (
            item
            for item in source_objectives.values()
            if item.get("objective_id") == objective.get("objective_id")
        ),
        key=lambda item: (
            int(item.get("revision", 0)),
            str(item.get("updated_at_utc", "")),
            str(item.get("objective_record_id", "")),
        ),
        default=None,
    )
    current_attention = next(
        (
            item
            for item in reversed(tuple(source_attention.values()))
            if item.get("subject") == attention.get("subject")
        ),
        None,
    )
    attention_superseded = any(
        item.get("supersedes_attention_id") == attention_reference
        for item in source_attention.values()
    )
    if (
        current_objective is None
        or current_objective.get("objective_record_id") != objective_reference
        or current_objective.get("status") != "ACTIVE"
        or current_attention is None
        or current_attention.get("attention_id") != attention_reference
        or attention_superseded
    ):
        raise CognitionStoreError("COGNITION_PROPOSAL_CONTEXT_NOT_CURRENT")

    schedule_id = payload.get("schedule_id")
    prior = (
        latest_proposals.get(schedule_id)
        if isinstance(schedule_id, str)
        else None
    )
    expected_previous = None if prior is None else prior.get("proposal_id")
    if payload.get("previous_proposal_reference") != expected_previous:
        raise CognitionStoreError("COGNITION_PROPOSAL_ANCESTRY_MISMATCH")


def _validate_payload(record_type: str, payload: dict[str, Any]) -> None:
    from .controlled_observation_schedule import ControlledObservationProposalV1
    from .entity_capability_gateway import (
        CapabilityAuditRecord,
        CapabilityGrantRecord,
        CapabilityRevocationRecord,
    )
    from .entity_cognition_scheduler import (
        CognitionCycleRecord,
        CognitionLeaseRecord,
        CognitionTriggerRecord,
    )
    from .entity_online_observation import (
        OnlineObservationExecutionRecord,
        OnlineObservationExecutionRecordV2,
        OnlineObservationRecord,
    )

    models: dict[str, type[BaseModel]] = {
        "MEMORY": DurableMemoryRecord,
        "OBJECTIVE": DurableObjectiveRecord,
        "ATTENTION": DurableAttentionRecord,
        "SCHEDULER_TRIGGER": CognitionTriggerRecord,
        "SCHEDULER_LEASE": CognitionLeaseRecord,
        "SCHEDULER_CYCLE": CognitionCycleRecord,
        "CONTROLLED_OBSERVATION_PROPOSAL": ControlledObservationProposalV1,
        "CAPABILITY_GRANT": CapabilityGrantRecord,
        "CAPABILITY_REVOCATION": CapabilityRevocationRecord,
        "CAPABILITY_AUDIT": CapabilityAuditRecord,
        "RETRIEVAL_OBSERVATION": OnlineObservationRecord,
    }
    if record_type == "ONLINE_EXECUTION":
        model = (
            OnlineObservationExecutionRecordV2
            if payload.get("schema_version") == "se6-online-execution-v2"
            else OnlineObservationExecutionRecord
            if payload.get("schema_version") == "se6-online-execution-v1"
            else None
        )
    else:
        model = models.get(record_type)
    if model is None:
        raise CognitionStoreError("COGNITION_RECORD_TYPE_UNSUPPORTED")
    try:
        model.model_validate_json(_json(payload))
    except (TypeError, ValueError) as exc:
        raise CognitionStoreError("COGNITION_RECORD_PAYLOAD_INVALID") from exc


def _id_field(record_type: str) -> str:
    fields = {
        "MEMORY": "memory_id",
        "OBJECTIVE": "objective_record_id",
        "ATTENTION": "attention_id",
        "SCHEDULER_TRIGGER": "trigger_id",
        "SCHEDULER_LEASE": "lease_id",
        "SCHEDULER_CYCLE": "cycle_id",
        "CONTROLLED_OBSERVATION_PROPOSAL": "proposal_id",
        "CAPABILITY_GRANT": "grant_id",
        "CAPABILITY_REVOCATION": "revocation_id",
        "CAPABILITY_AUDIT": "audit_id",
        "RETRIEVAL_OBSERVATION": "observation_id",
        "ONLINE_EXECUTION": "execution_id",
    }
    try:
        return fields[record_type]
    except KeyError as exc:
        raise CognitionStoreError("COGNITION_RECORD_TYPE_UNSUPPORTED") from exc


_EXTENSION_RECORD_TYPES = frozenset(
    {
        "SCHEDULER_TRIGGER",
        "SCHEDULER_LEASE",
        "SCHEDULER_CYCLE",
        "CONTROLLED_OBSERVATION_PROPOSAL",
        "CAPABILITY_GRANT",
        "CAPABILITY_REVOCATION",
        "CAPABILITY_AUDIT",
        "RETRIEVAL_OBSERVATION",
        "ONLINE_EXECUTION",
    }
)


def _row_material(
    *,
    sequence: int,
    record_type: str,
    record_id: str,
    dedupe_key: str | None,
    payload_hash: str,
    previous_record_hash: str,
    recorded_at_utc: str,
) -> dict[str, Any]:
    return {
        "record_sequence": sequence,
        "record_type": record_type,
        "record_id": record_id,
        "dedupe_key": dedupe_key,
        "payload_hash": payload_hash,
        "previous_record_hash": previous_record_hash,
        "recorded_at_utc": recorded_at_utc,
    }


def _model_json(model: BaseModel) -> str:
    return _json(model.model_dump(mode="json"))


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _time_text(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed, "stored timestamp")


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.DatabaseError:
        pass


def _absent_audit() -> CognitionStoreAudit:
    return CognitionStoreAudit(
        status="ABSENT",
        present=False,
        valid=False,
        record_count=0,
        memory_record_count=0,
        objective_record_count=0,
        attention_record_count=0,
        reason_codes=("COGNITION_STORE_ABSENT",),
    )


def _invalid_audit(code: str) -> CognitionStoreAudit:
    return CognitionStoreAudit(
        status="INVALID",
        present=True,
        valid=False,
        record_count=0,
        memory_record_count=0,
        objective_record_count=0,
        attention_record_count=0,
        reason_codes=(code,),
    )


_REQUIRED_TRIGGERS = frozenset(
    {
        "cognition_binding_no_update",
        "cognition_binding_no_delete",
        "cognition_records_no_update",
        "cognition_records_no_delete",
    }
)

_SCHEMA_SQL = f"""
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS cognition_store_schema (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    schema_version INTEGER NOT NULL CHECK(schema_version={COGNITION_STORE_SCHEMA_VERSION}),
    policy_version TEXT NOT NULL
);
INSERT OR IGNORE INTO cognition_store_schema(singleton,schema_version,policy_version)
VALUES(1,{COGNITION_STORE_SCHEMA_VERSION},'{COGNITION_STORE_POLICY_VERSION}');
CREATE TABLE IF NOT EXISTS cognition_entity_binding (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    binding_id TEXT NOT NULL UNIQUE,
    binding_hash TEXT NOT NULL,
    binding_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cognition_records (
    record_sequence INTEGER PRIMARY KEY CHECK(record_sequence>=1),
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL UNIQUE,
    dedupe_key TEXT UNIQUE,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    previous_record_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    recorded_at_utc TEXT NOT NULL,
    entity_state_id TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS cognition_binding_no_update
BEFORE UPDATE ON cognition_entity_binding BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER IF NOT EXISTS cognition_binding_no_delete
BEFORE DELETE ON cognition_entity_binding BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER IF NOT EXISTS cognition_records_no_update
BEFORE UPDATE ON cognition_records BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER IF NOT EXISTS cognition_records_no_delete
BEFORE DELETE ON cognition_records BEGIN SELECT RAISE(ABORT,'append-only'); END;
COMMIT;
"""


__all__ = [
    "COGNITION_STORE_POLICY_VERSION",
    "COGNITION_STORE_SCHEMA_VERSION",
    "CognitionEntityBinding",
    "CognitionEntityBindingRecord",
    "CognitionStoreAudit",
    "CognitionStoreError",
    "CognitionStorePolicy",
    "EntityCognitionStore",
    "default_cognition_database_path",
]
