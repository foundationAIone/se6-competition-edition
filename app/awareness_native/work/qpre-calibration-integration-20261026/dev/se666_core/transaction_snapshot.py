"""Immutable, independently verifiable snapshots of canonical transactions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBytes,
    StrictStr,
    field_validator,
)

from .canonical_contracts import ActionTransaction, canonical_json


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot_id(arguments_hash: str, material_hash: str) -> str:
    payload = f"se6-transaction-snapshot-v1:{arguments_hash}:{material_hash}".encode("ascii")
    return f"snap_{_sha256(payload)}"


class SnapshotIntegrityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    valid: bool
    errors: tuple[StrictStr, ...] = ()
    recalculated_arguments_hash: StrictStr
    recalculated_material_hash: StrictStr
    recalculated_snapshot_id: StrictStr


class TransactionSnapshot(BaseModel):
    """Frozen bytes captured before any decision or execution fields change."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    snapshot_id: StrictStr = Field(pattern=r"^snap_[0-9a-f]{64}$")
    transaction_id: StrictStr = Field(pattern=r"^txn_[0-9a-f]{64}$")
    schema_version: StrictStr
    canonicalization_version: StrictStr
    hash_algorithm: StrictStr = Field(pattern=r"^sha256$")
    canonical_arguments_bytes: StrictBytes
    material_transaction_bytes: StrictBytes
    canonical_arguments_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    material_transaction_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_created_at_utc: datetime
    policy_version: StrictStr
    content_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    patch_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("snapshot_created_at_utc")
    @classmethod
    def created_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("snapshot_created_at_utc must be timezone-aware")
        return value.astimezone(UTC)

    def verify_integrity(self) -> SnapshotIntegrityResult:
        arguments_hash = _sha256(self.canonical_arguments_bytes)
        material_hash = _sha256(self.material_transaction_bytes)
        snapshot_id = _snapshot_id(arguments_hash, material_hash)
        errors = []
        if arguments_hash != self.canonical_arguments_hash:
            errors.append("canonical_arguments_hash_mismatch")
        if material_hash != self.material_transaction_hash:
            errors.append("material_transaction_hash_mismatch")
        if snapshot_id != self.snapshot_id:
            errors.append("snapshot_id_mismatch")
        if self.transaction_id != f"txn_{material_hash}":
            errors.append("transaction_id_mismatch")
        try:
            arguments_node = json.loads(self.canonical_arguments_bytes.decode("utf-8"))
            material_node = json.loads(self.material_transaction_bytes.decode("utf-8"))
            if json.dumps(arguments_node, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8") != self.canonical_arguments_bytes:
                errors.append("canonical_arguments_bytes_not_canonical")
            if json.dumps(material_node, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8") != self.material_transaction_bytes:
                errors.append("material_transaction_bytes_not_canonical")
            material_values = material_node["value"]

            def scalar(name: str):
                node = material_values[name]
                return None if node.get("$type") == "null" else node.get("value")

            metadata_checks = {
                "schema_version": (self.schema_version, scalar("schema_version")),
                "canonicalization_version": (self.canonicalization_version, scalar("canonicalization_version")),
                "hash_algorithm": (self.hash_algorithm, scalar("hash_algorithm")),
                "canonical_arguments_hash": (self.canonical_arguments_hash, scalar("canonical_arguments_hash")),
                "policy_version": (self.policy_version, scalar("policy_version")),
                "content_hash": (self.content_hash, scalar("content_hash")),
                "patch_hash": (self.patch_hash, scalar("patch_hash")),
            }
            errors.extend(
                f"snapshot_metadata_mismatch:{name}"
                for name, (stored, encoded) in metadata_checks.items()
                if stored != encoded
            )
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            errors.append("snapshot_bytes_invalid")
        return SnapshotIntegrityResult(
            valid=not errors,
            errors=tuple(errors),
            recalculated_arguments_hash=arguments_hash,
            recalculated_material_hash=material_hash,
            recalculated_snapshot_id=snapshot_id,
        )


def create_transaction_snapshot(
    transaction: ActionTransaction,
    *,
    created_at: datetime | None = None,
) -> TransactionSnapshot:
    """Copy canonical bytes from a transaction without performing any effect."""
    if not isinstance(transaction, ActionTransaction):
        raise TypeError("transaction must be an ActionTransaction")
    arguments_bytes = canonical_json(transaction.arguments).encode("utf-8")
    material_bytes = canonical_json(transaction.material_fields()).encode("utf-8")
    arguments_hash = _sha256(arguments_bytes)
    material_hash = _sha256(material_bytes)
    if arguments_hash != transaction.canonical_arguments_hash:
        raise ValueError("transaction canonical arguments hash is inconsistent")
    if material_hash != transaction.material_transaction_hash:
        raise ValueError("transaction material hash is inconsistent")
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    snapshot = TransactionSnapshot(
        snapshot_id=_snapshot_id(arguments_hash, material_hash),
        transaction_id=f"txn_{material_hash}",
        schema_version=transaction.schema_version,
        canonicalization_version=transaction.canonicalization_version,
        hash_algorithm=transaction.hash_algorithm,
        canonical_arguments_bytes=bytes(arguments_bytes),
        material_transaction_bytes=bytes(material_bytes),
        canonical_arguments_hash=arguments_hash,
        material_transaction_hash=material_hash,
        snapshot_created_at_utc=timestamp.astimezone(UTC),
        policy_version=transaction.policy_version,
        content_hash=transaction.content_hash,
        patch_hash=transaction.patch_hash,
    )
    if not snapshot.verify_integrity().valid:
        raise ValueError("new transaction snapshot failed integrity verification")
    return snapshot


__all__ = ["SnapshotIntegrityResult", "TransactionSnapshot", "create_transaction_snapshot"]
