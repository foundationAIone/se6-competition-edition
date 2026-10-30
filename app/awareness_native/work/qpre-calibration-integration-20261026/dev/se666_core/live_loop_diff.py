"""Deterministic, bounded, non-executing diffs for LIVE LOOP candidates.

The module produces display text only.  It never opens a workspace, executes a
candidate, accesses production state, or contacts a network.  A truncated or
redacted artifact is explicitly non-authorizing so unseen content can never be
treated as an approved executable tail.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from .canonical_contracts import canonical_sha256

DIFF_SCHEMA_VERSION = "se6-live-loop-sanitized-diff-v1"
MAX_SOURCE_BYTES = 64_000
MAX_DISPLAY_BYTES = 16_384
MAX_DISPLAY_LINES = 400
TRUNCATION_MARKER = (
    "@@ SE6 DIFF TRUNCATED: NON-AUTHORIZING PREVIEW; OMITTED CONTENT EXISTS @@\n"
)
REDACTED_CHANGE_MARKER = (
    "@@ SE6 DIFF REDACTED: NON-AUTHORIZING CHANGE; EXACT CONTENT WITHHELD @@\n"
)
TEXT_CONTENT_RENDERING_CONTRACT = "BACKEND_RAW_TEXT_BROWSER_TEXTCONTENT_ONLY"

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_CANDIDATE_PATTERN = r"^candidate_[0-9a-f]{64}$"
_SAFE_TARGET = re.compile(r"^[A-Za-z0-9._/-]{1,260}$")
_CONTROL_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
            re.IGNORECASE,
        ),
    ),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    (
        "BEARER_TOKEN",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    ),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "STRIPE_SECRET",
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b"),
    ),
    (
        "JWT",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    (
        "CREDENTIAL_URI",
        re.compile(
            r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@",
            re.IGNORECASE,
        ),
    ),
)

_PRIVATE_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bfile:///(?:[^\s\"'<>]+)"),
    re.compile(r"(?i)(?<![A-Za-z0-9_])[A-Z]:\\[^\s\"'<>]+"),
    re.compile(r"(?<!\\)\\\\[^\\\s]+\\[^\s\"'<>]+"),
    re.compile(
        r"(?<![A-Za-z0-9_.:/<\\-])/"
        r"(?:[A-Za-z0-9._~+-]+/)*[A-Za-z0-9._~+-]+"
    ),
)

_SENSITIVE_LINE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ENVIRONMENT_REFERENCE",
        re.compile(
            r"(?i)(?:\bos\.(?:environ|getenv)\b|\bgetenv\s*\(|"
            r"\$\{?[A-Z_][A-Z0-9_]*\}?|%[A-Z_][A-Z0-9_]*%|\benv:)",
        ),
    ),
    (
        "OWNER_OR_CREDENTIAL_CONTEXT",
        re.compile(
            r"(?i)\b(?:owner(?:_id)?|password|passwd|credential|secret|"
            r"api[_-]?key|access[_-]?token|refresh[_-]?token|session[_-]?token|"
            r"csrf[_-]?token)\b"
        ),
    ),
)


class DiffPolicyError(RuntimeError):
    """Stable refusal with no candidate or secret content in its message."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_target(target: str) -> str:
    if not isinstance(target, str):
        raise DiffPolicyError("DIFF_TARGET_INVALID")
    if "\\" in target:
        raise DiffPolicyError("DIFF_TARGET_NOT_WORKSPACE_RELATIVE")
    normalized = target
    parts = normalized.split("/")
    if (
        not _SAFE_TARGET.fullmatch(normalized)
        or normalized.startswith(("/", "//"))
        or ":" in normalized
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise DiffPolicyError("DIFF_TARGET_NOT_WORKSPACE_RELATIVE")
    return normalized


def _decode_source(payload: bytes, *, side: str) -> str:
    if not isinstance(payload, bytes):
        raise TypeError(f"{side} source must be bytes")
    if len(payload) > MAX_SOURCE_BYTES:
        raise DiffPolicyError("DIFF_SOURCE_BYTE_LIMIT")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DiffPolicyError("DIFF_BINARY_OR_ENCODING_REJECTED") from exc
    if _CONTROL_TEXT.search(text):
        raise DiffPolicyError("DIFF_BINARY_OR_CONTROL_TEXT_REJECTED")
    if "\r" in text:
        raise DiffPolicyError("DIFF_NONCANONICAL_LINE_ENDING")
    return text


def _sanitize_source(
    text: str,
    *,
    secret_policy: Literal["reject", "redact"],
) -> tuple[str, set[str]]:
    sanitized = text
    categories: set[str] = set()
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(sanitized) is None:
            continue
        if secret_policy == "reject":
            raise DiffPolicyError("DIFF_SECRET_PATTERN_REJECTED")
        sanitized = pattern.sub(f"<SE6_SECRET_REDACTED:{name}>", sanitized)
        categories.add(f"SECRET_{name}")
    for pattern in _PRIVATE_PATH_PATTERNS:
        if pattern.search(sanitized) is not None:
            sanitized = pattern.sub("<SE6_PRIVATE_PATH_REDACTED>", sanitized)
            categories.add("PRIVATE_PATH")
    rendered_lines: list[str] = []
    for line in sanitized.splitlines(keepends=True):
        matched = next(
            (name for name, pattern in _SENSITIVE_LINE_PATTERNS if pattern.search(line)),
            None,
        )
        if matched is None:
            rendered_lines.append(line)
            continue
        if secret_policy == "reject":
            raise DiffPolicyError("DIFF_SENSITIVE_CONTEXT_REJECTED")
        newline = "\n" if line.endswith("\n") else ""
        rendered_lines.append(f"<SE6_SENSITIVE_LINE_REDACTED:{matched}>{newline}")
        categories.add(f"SENSITIVE_{matched}")
    sanitized = "".join(rendered_lines)
    return sanitized, categories


def _canonical_diff(before: str, after: str, target: str) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    generated = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{target}",
        tofile=f"b/{target}",
        n=3,
        lineterm="\n",
    )
    lines: list[str] = []
    for line in generated:
        if line.endswith("\n"):
            lines.append(line)
        else:
            lines.append(line + "\n")
            lines.append("\\ No newline at end of file\n")
    return "".join(lines)


def _bounded_preview(full_diff: str) -> tuple[str, bool, int, int]:
    payload = full_diff.encode("utf-8")
    lines = full_diff.splitlines(keepends=True)
    if len(lines) <= MAX_DISPLAY_LINES and len(payload) <= MAX_DISPLAY_BYTES:
        return full_diff, False, 0, 0

    marker_bytes = len(TRUNCATION_MARKER.encode("utf-8"))
    selected: list[str] = []
    selected_bytes = 0
    for line in lines:
        encoded = line.encode("utf-8")
        if len(selected) >= MAX_DISPLAY_LINES - 1:
            break
        if selected_bytes + len(encoded) + marker_bytes > MAX_DISPLAY_BYTES:
            break
        selected.append(line)
        selected_bytes += len(encoded)
    preview = "".join(selected) + TRUNCATION_MARKER
    return (
        preview,
        True,
        len(lines) - len(selected),
        len(payload) - selected_bytes,
    )


def candidate_diff_binding_hash(
    *,
    candidate_id: str,
    target: str,
    canonical_target_hash: str,
    before_sha256: str,
    after_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "candidate_id": candidate_id,
            "target": target,
            "canonical_target_hash": canonical_target_hash,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
        }
    )


class SanitizedCandidateDiff(BaseModel):
    """Strict display artifact; it is never executable content itself."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: StrictStr = Field(pattern=r"^se6-live-loop-sanitized-diff-v1$")
    candidate_id: StrictStr = Field(pattern=_CANDIDATE_PATTERN)
    target: StrictStr = Field(min_length=1, max_length=260)
    before_filename: StrictStr = Field(min_length=3, max_length=263)
    after_filename: StrictStr = Field(min_length=3, max_length=263)
    before_sha256: StrictStr = Field(pattern=_HASH_PATTERN)
    after_sha256: StrictStr = Field(pattern=_HASH_PATTERN)
    canonical_target_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    candidate_binding_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    full_diff_sha256: StrictStr = Field(pattern=_HASH_PATTERN)
    displayed_diff_sha256: StrictStr = Field(pattern=_HASH_PATTERN)
    canonical_diff_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    diff_text: StrictStr = Field(min_length=1)
    full_line_count: StrictInt = Field(ge=1)
    full_byte_count: StrictInt = Field(ge=1)
    displayed_line_count: StrictInt = Field(ge=1, le=MAX_DISPLAY_LINES)
    displayed_byte_count: StrictInt = Field(ge=1, le=MAX_DISPLAY_BYTES)
    truncated: StrictBool
    omitted_line_count: StrictInt = Field(ge=0)
    omitted_byte_count: StrictInt = Field(ge=0)
    redacted: StrictBool
    redaction_categories: tuple[StrictStr, ...] = ()
    secret_policy: Literal["reject", "redact"]
    authorization_complete: StrictBool
    non_authorizing_reason_codes: tuple[StrictStr, ...] = ()
    rendering_contract: StrictStr = Field(
        pattern=r"^BACKEND_RAW_TEXT_BROWSER_TEXTCONTENT_ONLY$"
    )

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"canonical_diff_hash"})

    @model_validator(mode="after")
    def verify_material(self) -> SanitizedCandidateDiff:
        target = _normalize_target(self.target)
        if target != self.target:
            raise ValueError("diff target is not canonical")
        if self.before_filename != f"a/{target}" or self.after_filename != f"b/{target}":
            raise ValueError("diff filenames must remain workspace-relative")
        expected_target_hash = canonical_sha256({"target": target})
        if self.canonical_target_hash != expected_target_hash:
            raise ValueError("canonical target hash mismatch")
        expected_binding = candidate_diff_binding_hash(
            candidate_id=self.candidate_id,
            target=target,
            canonical_target_hash=self.canonical_target_hash,
            before_sha256=self.before_sha256,
            after_sha256=self.after_sha256,
        )
        if self.candidate_binding_hash != expected_binding:
            raise ValueError("candidate diff binding mismatch")
        encoded = self.diff_text.encode("utf-8")
        if self.displayed_byte_count != len(encoded):
            raise ValueError("displayed diff byte count mismatch")
        if self.displayed_line_count != len(self.diff_text.splitlines()):
            raise ValueError("displayed diff line count mismatch")
        if self.displayed_diff_sha256 != _sha256(encoded):
            raise ValueError("displayed diff hash mismatch")
        expected_reasons = tuple(
            reason
            for condition, reason in (
                (self.redacted, "DIFF_REDACTED"),
                (self.truncated, "DIFF_TRUNCATED"),
            )
            if condition
        )
        if self.non_authorizing_reason_codes != expected_reasons:
            raise ValueError("non-authorizing reason codes mismatch")
        if self.authorization_complete != (not self.redacted and not self.truncated):
            raise ValueError("diff authorization completeness mismatch")
        if self.redacted != bool(self.redaction_categories):
            raise ValueError("diff redaction metadata mismatch")
        if tuple(sorted(set(self.redaction_categories))) != self.redaction_categories:
            raise ValueError("redaction categories must be sorted and unique")
        if self.truncated:
            if TRUNCATION_MARKER not in self.diff_text:
                raise ValueError("truncated diff lacks explicit marker")
            if self.omitted_line_count <= 0 or self.omitted_byte_count <= 0:
                raise ValueError("truncated diff lacks omission counts")
        else:
            if self.omitted_line_count != 0 or self.omitted_byte_count != 0:
                raise ValueError("complete diff cannot report omitted content")
            if self.full_line_count != self.displayed_line_count:
                raise ValueError("complete diff line counts differ")
            if self.full_byte_count != self.displayed_byte_count:
                raise ValueError("complete diff byte counts differ")
            if self.full_diff_sha256 != self.displayed_diff_sha256:
                raise ValueError("complete diff hashes differ")
        if self.rendering_contract != TEXT_CONTENT_RENDERING_CONTRACT:
            raise ValueError("unsafe browser rendering contract")
        for _name, pattern in _SECRET_PATTERNS:
            if pattern.search(self.diff_text) is not None:
                raise ValueError("secret-like value remains in displayed diff")
        for _name, pattern in _SENSITIVE_LINE_PATTERNS:
            if pattern.search(self.diff_text) is not None:
                raise ValueError("sensitive context remains in displayed diff")
        for pattern in _PRIVATE_PATH_PATTERNS:
            if pattern.search(self.diff_text) is not None:
                raise ValueError("private path remains in displayed diff")
        if self.canonical_diff_hash != canonical_sha256(self.material_fields()):
            raise ValueError("canonical diff hash mismatch")
        return self


def build_sanitized_candidate_diff(
    *,
    candidate_id: str,
    target: str,
    before: bytes,
    after: bytes,
    secret_policy: Literal["reject", "redact"] = "reject",
) -> SanitizedCandidateDiff:
    """Build a deterministic unified diff without performing any file access."""

    if secret_policy not in {"reject", "redact"}:
        raise DiffPolicyError("DIFF_SECRET_POLICY_INVALID")
    if not isinstance(candidate_id, str) or re.fullmatch(_CANDIDATE_PATTERN, candidate_id) is None:
        raise DiffPolicyError("DIFF_CANDIDATE_ID_INVALID")
    normalized_target = _normalize_target(target)
    before_text = _decode_source(before, side="before")
    after_text = _decode_source(after, side="after")
    if before == after:
        raise DiffPolicyError("DIFF_HAS_NO_CHANGE")

    safe_before, before_categories = _sanitize_source(
        before_text, secret_policy=secret_policy
    )
    safe_after, after_categories = _sanitize_source(
        after_text, secret_policy=secret_policy
    )
    categories = tuple(sorted(before_categories | after_categories))
    full_diff = _canonical_diff(safe_before, safe_after, normalized_target)
    if not full_diff:
        full_diff = (
            f"--- a/{normalized_target}\n"
            f"+++ b/{normalized_target}\n"
            f"{REDACTED_CHANGE_MARKER}"
        )
        categories = tuple(sorted(set(categories) | {"EXACT_CHANGE_WITHHELD"}))
    preview, truncated, omitted_lines, omitted_bytes = _bounded_preview(full_diff)
    full_payload = full_diff.encode("utf-8")
    display_payload = preview.encode("utf-8")
    target_hash = canonical_sha256({"target": normalized_target})
    before_hash = _sha256(before)
    after_hash = _sha256(after)
    material: dict[str, object] = {
        "schema_version": DIFF_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "target": normalized_target,
        "before_filename": f"a/{normalized_target}",
        "after_filename": f"b/{normalized_target}",
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "canonical_target_hash": target_hash,
        "candidate_binding_hash": candidate_diff_binding_hash(
            candidate_id=candidate_id,
            target=normalized_target,
            canonical_target_hash=target_hash,
            before_sha256=before_hash,
            after_sha256=after_hash,
        ),
        "full_diff_sha256": _sha256(full_payload),
        "displayed_diff_sha256": _sha256(display_payload),
        "diff_text": preview,
        "full_line_count": len(full_diff.splitlines()),
        "full_byte_count": len(full_payload),
        "displayed_line_count": len(preview.splitlines()),
        "displayed_byte_count": len(display_payload),
        "truncated": truncated,
        "omitted_line_count": omitted_lines,
        "omitted_byte_count": omitted_bytes,
        "redacted": bool(categories),
        "redaction_categories": categories,
        "secret_policy": secret_policy,
        "authorization_complete": not categories and not truncated,
        "non_authorizing_reason_codes": tuple(
            reason
            for condition, reason in (
                (bool(categories), "DIFF_REDACTED"),
                (truncated, "DIFF_TRUNCATED"),
            )
            if condition
        ),
        "rendering_contract": TEXT_CONTENT_RENDERING_CONTRACT,
    }
    return SanitizedCandidateDiff.model_validate(
        {"canonical_diff_hash": canonical_sha256(material), **material}
    )


def revalidate_sanitized_candidate_diff(
    artifact: SanitizedCandidateDiff,
    *,
    candidate_id: str,
    target: str,
    before: bytes,
    after: bytes,
    require_authorization_complete: bool = True,
) -> SanitizedCandidateDiff:
    """Rebuild from exact bytes and reject tampering, hiding, or stale binding."""

    try:
        validated = SanitizedCandidateDiff.model_validate(
            artifact.model_dump(mode="python")
        )
    except Exception as exc:
        raise DiffPolicyError("DIFF_ARTIFACT_INVALID") from exc
    rebuilt = build_sanitized_candidate_diff(
        candidate_id=candidate_id,
        target=target,
        before=before,
        after=after,
        secret_policy=validated.secret_policy,
    )
    if rebuilt != validated:
        raise DiffPolicyError("DIFF_REVALIDATION_MISMATCH")
    if require_authorization_complete and not rebuilt.authorization_complete:
        raise DiffPolicyError("DIFF_PREVIEW_NOT_AUTHORIZABLE")
    return rebuilt


__all__ = [
    "DIFF_SCHEMA_VERSION",
    "MAX_DISPLAY_BYTES",
    "MAX_DISPLAY_LINES",
    "MAX_SOURCE_BYTES",
    "REDACTED_CHANGE_MARKER",
    "TEXT_CONTENT_RENDERING_CONTRACT",
    "TRUNCATION_MARKER",
    "DiffPolicyError",
    "SanitizedCandidateDiff",
    "build_sanitized_candidate_diff",
    "candidate_diff_binding_hash",
    "revalidate_sanitized_candidate_diff",
]
