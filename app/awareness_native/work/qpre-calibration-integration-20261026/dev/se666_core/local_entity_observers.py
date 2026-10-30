"""Bounded local-only observation adapters for SE6 entity operation.

The adapters read caller-authorized local metadata and construct typed events.
They do not write files, open sockets, call models, execute tools, or grant
authority.  Repository observations store only relative paths and metadata
hashes; file contents are never copied into entity memory.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

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
from .entity_events import (
    AuthorityStatus,
    EntityEventDraft,
    EventEndpoint,
    EventSourceKind,
    EventType,
    LoopName,
    ObservationPayload,
    ObservationProvenance,
    PersistencePolicy,
    SensitivityClassification,
)
from .epistemic_status import EpistemicStatus

LOCAL_OBSERVER_SCHEMA_VERSION = "se6-local-observer-v1"
_DEFAULT_EXCLUDED = (
    ".git",
    ".runtime",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "local_backups",
)
_DEFAULT_SUFFIXES = (
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
)


class RepositoryObservationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-local-observer-v1"] = LOCAL_OBSERVER_SCHEMA_VERSION
    allowed_suffixes: tuple[StrictStr, ...] = _DEFAULT_SUFFIXES
    excluded_parts: tuple[StrictStr, ...] = _DEFAULT_EXCLUDED
    max_files: StrictInt = Field(default=4_096, ge=1, le=20_000)
    max_changed_paths: StrictInt = Field(default=64, ge=1, le=256)
    follow_reparse_points: Literal[False] = False
    read_contents: Literal[False] = False
    network_allowed: Literal[False] = False


class RepositoryFileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    relative_path: StrictStr = Field(min_length=1, max_length=512)
    size_bytes: StrictInt = Field(ge=0)
    modified_time_ns: StrictInt = Field(ge=0)
    metadata_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def metadata_is_bound(self) -> RepositoryFileMetadata:
        expected = canonical_sha256(
            {
                "relative_path": self.relative_path,
                "size_bytes": self.size_bytes,
                "modified_time_ns": self.modified_time_ns,
            }
        )
        if self.metadata_hash != expected:
            raise ValueError("repository metadata hash mismatch")
        return self


class RepositoryObservationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-local-observer-v1"] = LOCAL_OBSERVER_SCHEMA_VERSION
    snapshot_id: StrictStr = Field(pattern=r"^repo_snapshot_[0-9a-f]{64}$")
    root_reference: Literal["SE6_REPOSITORY"] = "SE6_REPOSITORY"
    observed_at_utc: datetime
    entries: tuple[RepositoryFileMetadata, ...] = Field(max_length=20_000)
    entry_count: StrictInt = Field(ge=0, le=20_000)
    tree_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    truncated: StrictBool = False
    network_used: Literal[False] = False
    content_captured: Literal[False] = False

    @field_validator("observed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def snapshot_is_canonical(self) -> RepositoryObservationSnapshot:
        if self.entry_count != len(self.entries):
            raise ValueError("repository entry count mismatch")
        if tuple(sorted(item.relative_path for item in self.entries)) != tuple(
            item.relative_path for item in self.entries
        ):
            raise ValueError("repository entries must be sorted")
        tree_hash = canonical_sha256(tuple(item.model_dump(mode="python") for item in self.entries))
        if self.tree_hash != tree_hash:
            raise ValueError("repository tree hash mismatch")
        expected = canonical_sha256(self.material_fields())
        if self.snapshot_id != f"repo_snapshot_{expected}":
            raise ValueError("repository snapshot ID mismatch")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"snapshot_id"})


class RepositoryChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    previous_snapshot_id: StrictStr = Field(pattern=r"^repo_snapshot_[0-9a-f]{64}$")
    current_snapshot_id: StrictStr = Field(pattern=r"^repo_snapshot_[0-9a-f]{64}$")
    added_paths: tuple[StrictStr, ...] = Field(default=(), max_length=256)
    changed_paths: tuple[StrictStr, ...] = Field(default=(), max_length=256)
    removed_paths: tuple[StrictStr, ...] = Field(default=(), max_length=256)
    changed_count: StrictInt = Field(ge=1)
    paths_truncated: StrictBool = False


def scan_repository(
    root: Path,
    *,
    observed_at_utc: datetime,
    policy: RepositoryObservationPolicy | None = None,
) -> RepositoryObservationSnapshot:
    """Read one bounded, non-recursive-effect repository metadata snapshot."""

    resolved = Path(root).resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        raise ValueError("repository observation root must be a real directory")
    active = policy or RepositoryObservationPolicy()
    entries = []
    truncated = False
    for path in _bounded_files(resolved, active):
        if len(entries) >= active.max_files:
            truncated = True
            break
        stat_result = path.stat(follow_symlinks=False)
        relative = path.relative_to(resolved).as_posix()
        material = {
            "relative_path": relative,
            "size_bytes": int(stat_result.st_size),
            "modified_time_ns": int(stat_result.st_mtime_ns),
        }
        entries.append(
            RepositoryFileMetadata(
                **material, metadata_hash=canonical_sha256(material)
            )
        )
    ordered = tuple(sorted(entries, key=lambda item: item.relative_path))
    tree_hash = canonical_sha256(tuple(item.model_dump(mode="python") for item in ordered))
    material = {
        "schema_version": LOCAL_OBSERVER_SCHEMA_VERSION,
        "root_reference": "SE6_REPOSITORY",
        "observed_at_utc": _utc(observed_at_utc),
        "entries": ordered,
        "entry_count": len(ordered),
        "tree_hash": tree_hash,
        "truncated": truncated,
        "network_used": False,
        "content_captured": False,
    }
    draft = RepositoryObservationSnapshot.model_construct(
        snapshot_id=f"repo_snapshot_{'0' * 64}", **material
    )
    normalized = draft.material_fields()
    return RepositoryObservationSnapshot.model_validate(
        {
            "snapshot_id": f"repo_snapshot_{canonical_sha256(normalized)}",
            **normalized,
        }
    )


def compare_repository_snapshots(
    previous: RepositoryObservationSnapshot,
    current: RepositoryObservationSnapshot,
    *,
    max_paths: int = 64,
) -> RepositoryChange | None:
    if previous.tree_hash == current.tree_hash:
        return None
    if max_paths < 1 or max_paths > 256:
        raise ValueError("max_paths must be between 1 and 256")
    before = {item.relative_path: item.metadata_hash for item in previous.entries}
    after = {item.relative_path: item.metadata_hash for item in current.entries}
    added_all = tuple(sorted(set(after) - set(before)))
    removed_all = tuple(sorted(set(before) - set(after)))
    changed_all = tuple(
        sorted(path for path in set(before) & set(after) if before[path] != after[path])
    )
    total = len(added_all) + len(removed_all) + len(changed_all)
    return RepositoryChange(
        previous_snapshot_id=previous.snapshot_id,
        current_snapshot_id=current.snapshot_id,
        added_paths=added_all[:max_paths],
        changed_paths=changed_all[:max_paths],
        removed_paths=removed_all[:max_paths],
        changed_count=total,
        paths_truncated=total > max_paths,
    )


def repository_change_event(
    change: RepositoryChange,
    *,
    occurred_at_utc: datetime,
    correlation_id: str,
) -> EntityEventDraft:
    examples = (*change.added_paths, *change.changed_paths, *change.removed_paths)[:8]
    suffix = f" Representative paths: {', '.join(examples)}." if examples else ""
    return EntityEventDraft(
        event_type=EventType.ENVIRONMENT_CHANGE,
        occurred_at_utc=_utc(occurred_at_utc),
        originating_loop=LoopName.EXTERNAL,
        source=EventEndpoint(kind=EventSourceKind.SYSTEM, identifier="LOCAL_REPOSITORY_OBSERVER"),
        target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
        relation="repository_state_changed_outside_last_entity_snapshot",
        provenance=ObservationProvenance.SYSTEM_OBSERVED,
        epistemic_status=EpistemicStatus.MEASURED,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id=correlation_id,
        causal_id=None,
        parent_event_id=None,
        sensitivity=SensitivityClassification.INTERNAL,
        persistence_policy=PersistencePolicy.DURABLE_AUDIT,
        payload=ObservationPayload(
            world_node="SE6_REPOSITORY",
            relation="metadata_tree_hash",
            value_summary=(
                f"Repository metadata changed across {change.changed_count} path(s)."
                f"{suffix} No repair or external action was performed."
            ),
            provenance=ObservationProvenance.SYSTEM_OBSERVED,
            observed_at_utc=_utc(occurred_at_utc),
            evidence_references=(
                change.previous_snapshot_id,
                change.current_snapshot_id,
            ),
            current_claim=True,
            confidence_basis_points=10_000,
        ),
    )


def repository_snapshot_event(
    snapshot: RepositoryObservationSnapshot,
    *,
    correlation_id: str,
) -> EntityEventDraft:
    """Record one measured current tree without claiming a prior-state diff."""

    truncation = " The bounded scan was truncated." if snapshot.truncated else ""
    return EntityEventDraft(
        event_type=EventType.OBSERVATION,
        occurred_at_utc=snapshot.observed_at_utc,
        originating_loop=LoopName.EXTERNAL,
        source=EventEndpoint(
            kind=EventSourceKind.SYSTEM, identifier="LOCAL_REPOSITORY_OBSERVER"
        ),
        target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
        relation="observes_current_repository_metadata",
        provenance=ObservationProvenance.SYSTEM_OBSERVED,
        epistemic_status=EpistemicStatus.MEASURED,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id=correlation_id,
        causal_id=None,
        parent_event_id=None,
        sensitivity=SensitivityClassification.INTERNAL,
        persistence_policy=PersistencePolicy.DURABLE_AUDIT,
        payload=ObservationPayload(
            world_node="SE6_REPOSITORY",
            relation="metadata_tree_hash",
            value_summary=(
                f"Measured {snapshot.entry_count} bounded repository path(s) at "
                f"tree hash {snapshot.tree_hash}.{truncation} No file content was "
                "captured and no repair or external action was performed."
            ),
            provenance=ObservationProvenance.SYSTEM_OBSERVED,
            observed_at_utc=snapshot.observed_at_utc,
            evidence_references=(
                snapshot.snapshot_id,
                f"repo_tree_{snapshot.tree_hash}",
            ),
            current_claim=True,
            confidence_basis_points=10_000,
        ),
    )


def local_state_observation_event(
    *,
    world_node: str,
    relation: str,
    value_summary: str,
    evidence_references: tuple[str, ...],
    occurred_at_utc: datetime,
    correlation_id: str,
    independently_verified: bool,
) -> EntityEventDraft:
    """Convert a trusted local adapter projection into an epistemically exact event."""

    provenance = (
        ObservationProvenance.INDEPENDENTLY_VERIFIED
        if independently_verified
        else ObservationProvenance.SYSTEM_OBSERVED
    )
    epistemic = EpistemicStatus.VERIFIED if independently_verified else EpistemicStatus.MEASURED
    return EntityEventDraft(
        event_type=EventType.OBSERVATION,
        occurred_at_utc=_utc(occurred_at_utc),
        originating_loop=LoopName.EXTERNAL,
        source=EventEndpoint(kind=EventSourceKind.SYSTEM, identifier="LOCAL_STATE_ADAPTER"),
        target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
        relation="observes_local_state",
        provenance=provenance,
        epistemic_status=epistemic,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id=correlation_id,
        causal_id=None,
        parent_event_id=None,
        sensitivity=SensitivityClassification.INTERNAL,
        persistence_policy=PersistencePolicy.DURABLE_AUDIT,
        payload=ObservationPayload(
            world_node=world_node,
            relation=relation,
            value_summary=value_summary,
            provenance=provenance,
            observed_at_utc=_utc(occurred_at_utc),
            evidence_references=evidence_references,
            current_claim=True,
            confidence_basis_points=10_000,
        ),
    )


def _bounded_files(root: Path, policy: RepositoryObservationPolicy) -> Iterable[Path]:
    suffixes = {item.casefold() for item in policy.allowed_suffixes}
    excluded = set(policy.excluded_parts)
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        names[:] = sorted(
            name
            for name in names
            if name not in excluded and not (base / name).is_symlink()
        )
        for name in sorted(files):
            path = base / name
            if path.is_symlink() or path.suffix.casefold() not in suffixes:
                continue
            yield path


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "LOCAL_OBSERVER_SCHEMA_VERSION",
    "RepositoryChange",
    "RepositoryFileMetadata",
    "RepositoryObservationPolicy",
    "RepositoryObservationSnapshot",
    "compare_repository_snapshots",
    "local_state_observation_event",
    "repository_change_event",
    "repository_snapshot_event",
    "scan_repository",
]
