"""Source Trust Registry (V2 Step 15 / Phase H).

A **manual**, **local-only**, **deterministic** registry of public
sources the operator wants to track *before* any internet fetching is
ever permitted. Nothing in this module fetches, crawls, scrapes,
browses, posts, or logs in. The URL is treated as an opaque label.

Files written (atomic):

* ``memory/sources/sources.jsonl`` — append-only index, one line per
  registered source (latest write wins on read).
* ``memory/sources/<source_id>.json`` — the full record.
* ``memory/sources/<source_id>.md`` — a printable summary.

Audit linkage (append-only) to ``memory/audit_log.jsonl``:

* ``source_added``
* ``source_reviewed``

Pure, deterministic, local. No network, no APIs, no shell, no
avatar/voice/trading, no self-update, no browser, no autonomy.

Public API:

* :func:`add_source`
* :func:`load_source`
* :func:`list_sources`
* :func:`review_source`
* :func:`make_source_id`
* :class:`SourceTrustRecord`
* :class:`SourceTrustReview`
* :class:`SourceTrustSummary`
* :class:`SourceTrustError`

There is no delete, truncate, clear, drop, remove, purge, wipe, or
overwrite API.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .audit_store import DEFAULT_AUDIT_PATH
from .project_memory import MEMORY_DIR, _resolve_under_memory  # type: ignore

SOURCES_DIR: Path = MEMORY_DIR / "sources"
SOURCES_INDEX_NAME = "sources.jsonl"

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Allowed trust tiers, ordered.
TRUST_TIERS: tuple[str, ...] = (
    "T0_BLOCKED",
    "T1_UNKNOWN",
    "T2_COMMUNITY",
    "T3_SECONDARY",
    "T4_PRIMARY",
    "T5_CANONICAL",
)

#: Allowed risk levels.
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high", "blocked")

#: Allowed source types.
SOURCE_TYPES: tuple[str, ...] = (
    "official_docs",
    "standards_body",
    "government",
    "research_paper",
    "open_source_repo",
    "company_docs",
    "news_analysis",
    "community_discussion",
    "social_media",
    "unknown",
)

#: Trust → risk default mapping.
_TRUST_TO_RISK = {
    "T0_BLOCKED": "blocked",
    "T1_UNKNOWN": "high",
    "T2_COMMUNITY": "medium",
    "T3_SECONDARY": "medium",
    "T4_PRIMARY": "low",
    "T5_CANONICAL": "low",
}

#: Schemes that are absolutely refused.
_FORBIDDEN_SCHEME_PREFIXES = (
    "file:",
    "ftp:",
    "javascript:",
    "data:",
    "chrome:",
    "powershell:",
    "cmd:",
    "ssh:",
    "smb:",
    "mailto:",
    "tel:",
    "vbscript:",
)

_ALLOWED_SCHEMES = ("http://", "https://")

_SECRET_MARKERS = (
    "token",
    "api_key",
    "api-key",
    "apikey",
    "private_key",
    "private-key",
    "privatekey",
    "password",
    "passwd",
    "secret",
    "credential",
)

_SOURCE_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_TAG_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")

_AUDIT_ADDED = "source_added"
_AUDIT_REVIEWED = "source_reviewed"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SourceTrustError(Exception):
    """Raised when a source registry operation cannot be performed."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SourceTrustReview(BaseModel):
    ts: str
    trust_tier: str
    risk_level: str
    note: str = ""
    by: str | None = None


class SourceTrustRecord(BaseModel):
    source_id: str
    created_ts: str
    updated_ts: str
    title: str
    url: str
    source_type: str
    trust_tier: str
    risk_level: str
    status: str = "registered"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    review_history: list[SourceTrustReview] = Field(default_factory=list)
    markdown: str = ""


class SourceTrustSummary(BaseModel):
    records: list[SourceTrustRecord] = Field(default_factory=list)
    count: int = 0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_text(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise SourceTrustError(f"{name} must be a string")
    if not value.strip():
        raise SourceTrustError(f"{name} must be non-empty")
    return value


def _validate_url(url: str) -> str:
    u = _ensure_text(url, name="url").strip()
    low = u.lower()
    for bad in _FORBIDDEN_SCHEME_PREFIXES:
        if low.startswith(bad):
            raise SourceTrustError(
                f"refusing url with forbidden scheme: {bad}"
            )
    if not (low.startswith(("http://", "https://"))):
        raise SourceTrustError(
            "url must start with http:// or https://"
        )
    if " " in u or "\t" in u or "\n" in u or "\r" in u:
        raise SourceTrustError("url must not contain whitespace")
    return u


def _validate_trust(tier: str) -> str:
    t = _ensure_text(tier, name="trust_tier").strip()
    if t not in TRUST_TIERS:
        raise SourceTrustError(
            f"trust_tier must be one of {TRUST_TIERS}, got {t!r}"
        )
    return t


def _validate_type(source_type: str | None) -> str:
    if source_type is None or source_type == "":
        return "unknown"
    if not isinstance(source_type, str):
        raise SourceTrustError("source_type must be a string")
    if source_type not in SOURCE_TYPES:
        raise SourceTrustError(
            f"source_type must be one of {SOURCE_TYPES}, got {source_type!r}"
        )
    return source_type


def _validate_tags(tags: Iterable[str] | None) -> list[str]:
    if tags is None:
        return []
    out: list[str] = []
    seen: set = set()
    for raw in tags:
        if not isinstance(raw, str):
            raise SourceTrustError("tag must be a string")
        t = raw.strip()
        if not t:
            continue
        if not _TAG_RE.match(t):
            raise SourceTrustError(
                f"tag {t!r} must match {_TAG_RE.pattern}"
            )
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _scan_secret_markers(*texts: str) -> None:
    for raw in texts:
        if not isinstance(raw, str) or not raw:
            continue
        low = raw.lower()
        for marker in _SECRET_MARKERS:
            if marker in low:
                raise SourceTrustError(
                    f"refusing input containing secret marker {marker!r}"
                )


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def _resolve_sources_dir(sources_dir: Path) -> Path:
    p = Path(sources_dir).resolve()
    if p.name != "sources":
        raise PermissionError(
            f"Sources directory must be named 'sources': {p}"
        )
    _resolve_under_memory(p / ".guard")
    return p


def _validate_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be a non-empty string")
    if (
        source_id.startswith(".")
        or "/" in source_id
        or "\\" in source_id
        or ".." in source_id
        or os.path.isabs(source_id)
        or not _SOURCE_ID_RE.match(source_id)
    ):
        raise ValueError(f"invalid source_id: {source_id!r}")


def _record_paths(source_id: str, sources_dir: Path) -> tuple[Path, Path]:
    _validate_source_id(source_id)
    base = _resolve_sources_dir(sources_dir)
    json_path = (base / f"{source_id}.json").resolve()
    md_path = (base / f"{source_id}.md").resolve()
    if json_path.parent != base or md_path.parent != base:
        raise PermissionError(f"source files must live directly under {base}")
    return json_path, md_path


def _index_path(sources_dir: Path) -> Path:
    base = _resolve_sources_dir(sources_dir)
    p = (base / SOURCES_INDEX_NAME).resolve()
    if p.parent != base:
        raise PermissionError(f"index must live directly under {base}")
    return p


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".source_trust.", suffix=".tmp", dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target)
    except (TypeError, ValueError):
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _append_jsonl(target: Path, payload: dict) -> None:
    p = _resolve_under_memory(Path(target))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Deterministic id
# ---------------------------------------------------------------------------


def make_source_id(title: str, url: str) -> str:
    """Deterministic 12-hex id from (normalized title, normalized url)."""
    t = _ensure_text(title, name="title").strip().lower()
    u = _validate_url(url).rstrip("/").lower()
    h = hashlib.sha256(f"src|{t}|{u}".encode()).hexdigest()
    return h[:12]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _render_markdown(rec: SourceTrustRecord) -> str:
    lines = [
        "# SE666 Source Trust Record",
        "",
        f"- **source_id:** `{rec.source_id}`",
        f"- **title:** {rec.title}",
        f"- **url:** {rec.url}",
        f"- **source_type:** `{rec.source_type}`",
        f"- **trust_tier:** `{rec.trust_tier}`",
        f"- **risk_level:** `{rec.risk_level}`",
        f"- **status:** `{rec.status}`",
        f"- **created_ts:** {rec.created_ts}",
        f"- **updated_ts:** {rec.updated_ts}",
    ]
    if rec.tags:
        lines.append(f"- **tags:** {', '.join(rec.tags)}")
    if rec.notes:
        lines.extend(["", "## Notes", "", rec.notes.strip()])
    if rec.review_history:
        lines.extend(["", "## Review history"])
        for r in rec.review_history:
            line = (
                f"- {r.ts} \u2014 `{r.trust_tier}` (risk `{r.risk_level}`)"
            )
            if r.by:
                line += f" by `{r.by}`"
            if r.note:
                line += f" \u2014 {r.note}"
            lines.append(line)
    lines.extend([
        "",
        "## Local-safe constraints",
        "- This record was registered manually.",
        "- The URL was **not** fetched; it is an opaque label only.",
        "- No internet access. No browser. No scraping. No login.",
    ])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


def _read_index(sources_dir: Path) -> list[dict]:
    """Return raw index rows (latest write wins, deduped by source_id)."""
    idx = _index_path(sources_dir)
    if not idx.exists():
        return []
    rows_by_id: dict = {}
    order: list[str] = []
    try:
        with idx.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                sid = obj.get("source_id")
                if not isinstance(sid, str):
                    continue
                if sid not in rows_by_id:
                    order.append(sid)
                rows_by_id[sid] = obj
    except OSError:
        return []
    return [rows_by_id[sid] for sid in order]


def _append_index(sources_dir: Path, rec: SourceTrustRecord) -> None:
    idx = _index_path(sources_dir)
    idx.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_id": rec.source_id,
        "title": rec.title,
        "url": rec.url,
        "source_type": rec.source_type,
        "trust_tier": rec.trust_tier,
        "risk_level": rec.risk_level,
        "status": rec.status,
        "tags": rec.tags,
        "created_ts": rec.created_ts,
        "updated_ts": rec.updated_ts,
    }
    with idx.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _save_record(rec: SourceTrustRecord, *, sources_dir: Path) -> None:
    json_path, md_path = _record_paths(rec.source_id, sources_dir)
    _atomic_write_text(json_path, rec.model_dump_json(indent=2))
    _atomic_write_text(md_path, rec.markdown)
    _append_index(sources_dir, rec)


def load_source(
    source_id: str,
    *,
    sources_dir: Path = SOURCES_DIR,
) -> SourceTrustRecord | None:
    """Read-only: load a saved record by id, or ``None``."""
    try:
        json_path, _md = _record_paths(source_id, sources_dir)
    except (ValueError, PermissionError):
        return None
    if not json_path.exists():
        return None
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return SourceTrustRecord(**raw)
    except (TypeError, ValueError):
        return None


def list_sources(
    *,
    sources_dir: Path = SOURCES_DIR,
    trust: str | None = None,
    source_type: str | None = None,
    tag: str | None = None,
) -> SourceTrustSummary:
    """Read-only: list saved records, optionally filtered.

    Filters are exact matches; ``tag`` matches if the tag appears in the
    record's tag list.
    """
    base = _resolve_sources_dir(sources_dir)
    if not base.exists():
        return SourceTrustSummary(records=[], count=0)

    filter_trust = _validate_trust(trust) if trust else None
    filter_type = _validate_type(source_type) if source_type else None
    filter_tag: str | None = None
    if tag is not None:
        if not isinstance(tag, str) or not _TAG_RE.match(tag.strip()):
            raise SourceTrustError(f"invalid tag filter: {tag!r}")
        filter_tag = tag.strip()

    records: list[SourceTrustRecord] = []
    seen: set = set()
    for row in _read_index(sources_dir):
        sid = row.get("source_id")
        if not isinstance(sid, str) or sid in seen:
            continue
        seen.add(sid)
        rec = load_source(sid, sources_dir=sources_dir)
        if rec is None:
            continue
        if filter_trust is not None and rec.trust_tier != filter_trust:
            continue
        if filter_type is not None and rec.source_type != filter_type:
            continue
        if filter_tag is not None and filter_tag not in rec.tags:
            continue
        records.append(rec)
    return SourceTrustSummary(records=records, count=len(records))


# ---------------------------------------------------------------------------
# Public: add
# ---------------------------------------------------------------------------


def add_source(
    *,
    title: str,
    url: str,
    trust_tier: str,
    source_type: str | None = None,
    note: str = "",
    tags: Iterable[str] | None = None,
    sources_dir: Path = SOURCES_DIR,
    audit_path: Path = DEFAULT_AUDIT_PATH,
) -> SourceTrustRecord:
    """Register a source. Idempotent: re-adding the same (title, url)
    pair updates trust/type/notes/tags in place but never duplicates."""
    title = _ensure_text(title, name="title").strip()
    url = _validate_url(url)
    tier = _validate_trust(trust_tier)
    stype = _validate_type(source_type)
    note = (note or "").strip()
    tags_list = _validate_tags(tags)
    _scan_secret_markers(title, url, note, *tags_list)

    if tier == "T5_CANONICAL" and not note:
        raise SourceTrustError(
            "T5_CANONICAL requires a non-empty review note"
        )

    sid = make_source_id(title, url)
    risk = _TRUST_TO_RISK[tier]
    now = _utc_now()

    existing = load_source(sid, sources_dir=sources_dir)
    if existing is not None:
        # Idempotent update: preserve created_ts and review history.
        rec = SourceTrustRecord(
            source_id=sid,
            created_ts=existing.created_ts,
            updated_ts=now,
            title=title,
            url=url,
            source_type=stype,
            trust_tier=tier,
            risk_level=risk,
            status=existing.status,
            tags=tags_list or existing.tags,
            notes=note or existing.notes,
            review_history=existing.review_history,
            markdown="",
        )
    else:
        rec = SourceTrustRecord(
            source_id=sid,
            created_ts=now,
            updated_ts=now,
            title=title,
            url=url,
            source_type=stype,
            trust_tier=tier,
            risk_level=risk,
            status="registered",
            tags=tags_list,
            notes=note,
            review_history=[],
            markdown="",
        )
    rec = rec.model_copy(update={"markdown": _render_markdown(rec)})
    _save_record(rec, sources_dir=sources_dir)

    _append_jsonl(audit_path, {
        "action": _AUDIT_ADDED,
        "ts": now,
        "source_id": rec.source_id,
        "trust_tier": rec.trust_tier,
        "risk_level": rec.risk_level,
        "source_type": rec.source_type,
        "title": rec.title,
        "url": rec.url,
    })
    return rec


# ---------------------------------------------------------------------------
# Public: review
# ---------------------------------------------------------------------------


def review_source(
    source_id: str,
    *,
    trust_tier: str,
    note: str,
    by: str | None = None,
    sources_dir: Path = SOURCES_DIR,
    audit_path: Path = DEFAULT_AUDIT_PATH,
) -> SourceTrustRecord:
    """Append a review event to a source. Updates trust + risk; preserves
    history. Refuses unknown ids and empty T5_CANONICAL notes."""
    tier = _validate_trust(trust_tier)
    note = _ensure_text(note, name="note").strip()
    if not note:
        raise SourceTrustError("review note must be non-empty")
    _scan_secret_markers(note, by or "")

    if tier == "T5_CANONICAL" and not note:
        raise SourceTrustError(
            "T5_CANONICAL requires a non-empty review note"
        )

    rec = load_source(source_id, sources_dir=sources_dir)
    if rec is None:
        raise SourceTrustError(f"No source with id '{source_id}'.")

    risk = _TRUST_TO_RISK[tier]
    now = _utc_now()
    review = SourceTrustReview(
        ts=now, trust_tier=tier, risk_level=risk, note=note, by=by,
    )
    new_history = list(rec.review_history) + [review]
    updated = SourceTrustRecord(
        source_id=rec.source_id,
        created_ts=rec.created_ts,
        updated_ts=now,
        title=rec.title,
        url=rec.url,
        source_type=rec.source_type,
        trust_tier=tier,
        risk_level=risk,
        status="reviewed",
        tags=rec.tags,
        notes=rec.notes,
        review_history=new_history,
        markdown="",
    )
    updated = updated.model_copy(update={"markdown": _render_markdown(updated)})
    _save_record(updated, sources_dir=sources_dir)

    _append_jsonl(audit_path, {
        "action": _AUDIT_REVIEWED,
        "ts": now,
        "source_id": updated.source_id,
        "trust_tier": updated.trust_tier,
        "risk_level": updated.risk_level,
        "note": review.note,
        "by": review.by,
    })
    return updated


__all__ = [
    "RISK_LEVELS",
    "SOURCES_DIR",
    "SOURCE_TYPES",
    "TRUST_TIERS",
    "SourceTrustError",
    "SourceTrustRecord",
    "SourceTrustReview",
    "SourceTrustSummary",
    "add_source",
    "list_sources",
    "load_source",
    "make_source_id",
    "review_source",
]
