"""Strict public-only export validation and unresolved evidence review.

No transport, private implementation imports, state access or action dispatch.
The v1 bridge decision is a PUBLIC REVIEW disposition, never an invented
source-runtime boundary decision or cognition verdict.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from src.contracts.public_se6_bridge import (
    BRIDGE_SCHEMA,
    PublicSE6BridgeEnvelope,
    canonical_hash,
    canonical_json,
    parse_public_bridge,
)

EXPORT_SCHEMA = "se6-competition-export-v1"
TOP_FIELDS = frozenset({"schema_version", "baseline_sha256", "entity", "evidence",
                        "public_contract", "export_sha256"})
ENTITY_TEXT = frozenset({"entity_state_id", "identity_state_id", "runtime_session_id",
                         "status", "continuity", "store_integrity", "authority_effect",
                         "network_authority", "external_requests"})
ENTITY_FIELDS = ENTITY_TEXT | {"entity_state_hash", "state_version", "supervisor_active"}
EVIDENCE_HASHES = frozenset({"state_hash", "evidence_hash", "final_receipt_hash",
    "recovery_receipt_hash", "identity_state_before_hash", "identity_state_after_hash"})
EVIDENCE_TEXT = frozenset({"verification_status", "predecessor_runtime_session_id",
                          "successor_runtime_session_id"})
EVIDENCE_FIELDS = EVIDENCE_HASHES | EVIDENCE_TEXT | {"ready", "restart"}
PUBLIC_CONTRACT = {"read_only": True, "authority_effect": "NONE", "execution_authority": False,
                   "network_authority": "NONE", "raw_private_payload_included": False}
FORBIDDEN = ("password", "passwd", "csrf", "cookie", "authorization", "bearer", "api_key",
             "api-key", "secret", "private_key", "private key", "owner_session", "session_token",
             "credential", "c:\\users\\", "c:/users/", ".runtime\\", ".runtime/", ".sqlite",
             "/home/", "/users/", "-----begin")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class RealExportError(ValueError):
    pass


def scan_public_boundary(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            scan_public_boundary(key)
            scan_public_boundary(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            scan_public_boundary(item)
    elif isinstance(value, str) and any(word in value.casefold() for word in FORBIDDEN):
        # Do not echo rejected content, which could itself contain sensitive data.
        raise RealExportError("prohibited public content")


def _exact_fields(value: Any, fields: frozenset | set, name: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise RealExportError(name + " fields do not match public allowlist")


def _hash(value: Any, name: str, *, nullable=False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise RealExportError(name + " must be lowercase SHA256")


def _text(value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 256):
        raise RealExportError("projection text must be bounded text or null")


def validate_competition_export(raw: Any, *, expected_sha256: str | None = None) -> dict:
    """Accept only the sanitized envelope, never a capture wrapper."""
    _exact_fields(raw, TOP_FIELDS, "export")
    scan_public_boundary(raw)
    if raw["schema_version"] != EXPORT_SCHEMA:
        raise RealExportError("unsupported export schema")
    _hash(raw["export_sha256"], "export_sha256")
    _hash(raw["baseline_sha256"], "baseline_sha256")
    if expected_sha256 is not None and raw["export_sha256"] != expected_sha256:
        raise RealExportError("unexpected source export hash")
    _exact_fields(raw["public_contract"], set(PUBLIC_CONTRACT), "public contract")
    for key, expected in PUBLIC_CONTRACT.items():
        actual = raw["public_contract"][key]
        if type(actual) is not type(expected) or actual != expected:
            raise RealExportError("public contract must be inert")
    entity, evidence = raw["entity"], raw["evidence"]
    _exact_fields(entity, ENTITY_FIELDS, "entity")
    _exact_fields(evidence, EVIDENCE_FIELDS, "evidence")
    for key in ENTITY_TEXT:
        _text(entity[key])
    for key in EVIDENCE_TEXT:
        _text(evidence[key])
    _hash(entity["entity_state_hash"], "entity_state_hash", nullable=True)
    for key in EVIDENCE_HASHES:
        _hash(evidence[key], key, nullable=True)
    if entity["state_version"] is not None and (type(entity["state_version"]) is not int or entity["state_version"] < 0):
        raise RealExportError("state_version must be nonnegative integer or null")
    for value in (entity["supervisor_active"], evidence["ready"], evidence["restart"]):
        if type(value) is not bool:
            raise RealExportError("projection flags must be booleans")
    if (entity["authority_effect"], entity["network_authority"], entity["external_requests"]) != ("NONE", "NONE", "BLOCKED"):
        raise RealExportError("source projection exceeds the offline import scope")
    actual = canonical_hash({key: value for key, value in raw.items() if key != "export_sha256"})
    if actual != raw["export_sha256"]:
        raise RealExportError("export hash mismatch")
    return json.loads(canonical_json(raw))


def to_public_bridge(raw: Any) -> PublicSE6BridgeEnvelope:
    """Review the snapshot as unresolved; no claim about source decisions.

    PAUSE withholds public judgment; NONE records that this import accepts no
    state transition. Both are adapter dispositions. Source boundary/transition
    and consequence verification remain unavailable in the Judge record.
    """
    export = validate_competition_export(raw)
    return parse_public_bridge({
        "schema_version": BRIDGE_SCHEMA,
        "case_id": "real-export-review-" + export["export_sha256"],
        "baseline_sha256": export["baseline_sha256"],
        "source_record_sha256": export["export_sha256"],
        "epistemic_state": "UNRESOLVED",
        "boundary_decision": "PAUSE",
        "transition_status": "NONE",
        "transition_digest": None,
        "verified_consequence_digest": None,
        "restart_reconstructed": None,
        # Authority conveyed by the source EXPORT, not an absent action receipt.
        # The enclosing Judge record hash-binds this import-specific scope.
        "source_execution_authorized": export["public_contract"]["execution_authority"],
        "source_action_executed": None,
        "source_network_authority": "NONE",
        "public_read_only": True,
        "public_authority_effect": "NONE",
        "public_execution_authority": False,
        "public_network_authority": "NONE",
        "raw_private_payload_included": False,
        "evidence": [{"evidence_id": "public-export-" + export["export_sha256"],
            "evidence_class": "OBSERVATION", "source_digest": export["export_sha256"],
            "supports_claim": False, "contradicts_claim": False,
            "provenance_kind": "OWNER_SUPPLIED_REAL_SE6_CAPTURE"}],
    })


def decode_json(text: str) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RealExportError("duplicate JSON field")
            result[key] = value
        return result

    def invalid_number(_value):
        raise RealExportError("non-finite JSON number")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise RealExportError("non-finite JSON number")
        return parsed

    return json.loads(
        text, object_pairs_hook=unique, parse_constant=invalid_number,
        parse_float=finite_float,
    )
