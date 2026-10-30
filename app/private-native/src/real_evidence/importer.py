"""Local-file import only. Never accepts the private before/after capture."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.contracts.public_se6_bridge import canonical_json
from src.judge_mode.engine import (
    build_real_evidence_record,
    render_real_evidence_markdown,
)
from src.real_evidence.competition_export import (
    RealExportError,
    decode_json,
    scan_public_boundary,
    validate_competition_export,
)

RECEIPT_FIELDS = {
    "schema_version", "evidence_origin", "synthetic_fixture", "captured_at_utc",
    "export_sha256", "baseline_sha256", "export_hash_verified", "authoritative_state_unchanged",
    "event_budget_unchanged", "public_boundary_scan", "secrets_exported", "read_only",
    "authority_effect", "execution_authority", "network_authority", "raw_private_payload_included",
    "paired_model_comparison", "verification_basis",
}


def read_public_json(path: Path):
    if path.stat().st_size > 131072:
        raise RealExportError("public artifact size limit exceeded")
    return decode_json(path.read_text(encoding="utf-8-sig"))


def validate_capture_receipt(receipt: dict, export: dict) -> None:
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise RealExportError("public receipt fields do not match allowlist")
    expected = {
        "schema_version": "se6-real-export-receipt-v1", "evidence_origin": "REAL_SE6",
        "synthetic_fixture": False, "export_sha256": export["export_sha256"],
        "baseline_sha256": export["baseline_sha256"], "export_hash_verified": True,
        "authoritative_state_unchanged": True, "event_budget_unchanged": True,
        "public_boundary_scan": "PASS", "secrets_exported": 0, "read_only": True,
        "authority_effect": "NONE", "execution_authority": False, "network_authority": "NONE",
        "raw_private_payload_included": False, "paired_model_comparison": "PENDING",
        "verification_basis": "OWNER_CONFIRMED_CAPTURE_AND_LOCAL_DIGEST_CHECK",
    }
    for key, value in expected.items():
        if type(receipt[key]) is not type(value) or receipt[key] != value:
            raise RealExportError("public receipt assertion mismatch")
    timestamp = receipt["captured_at_utc"]
    if not isinstance(timestamp, str):
        raise RealExportError("capture timestamp required")
    scan_public_boundary(timestamp)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RealExportError("invalid capture timestamp") from exc
    if parsed.tzinfo is None:
        raise RealExportError("capture timestamp must have timezone")


def verify_judge_artifact(raw: dict) -> bool:
    """Rebuild both derived hashes from the public source fields."""
    try:
        export = {
            "schema_version": raw["source_export_schema"],
            "baseline_sha256": raw["baseline_sha256"], "export_sha256": raw["export_sha256"],
            "entity": raw["entity"], "evidence": raw["evidence"], "public_contract": raw["public_contract"],
        }
        record = build_real_evidence_record(export)
        # Compare JSON values: dataclass tuples become lists on a disk roundtrip.
        expected = {**record.payload(), "record_hash": record.record_hash}
        return canonical_json(raw) == canonical_json(expected) and record.verify_hash()
    except (KeyError, TypeError, ValueError):
        return False


def import_real_export(export_path: Path, receipt_path: Path, output: Path) -> dict:
    export = validate_competition_export(read_public_json(export_path))
    receipt = read_public_json(receipt_path)
    validate_capture_receipt(receipt, export)
    record = build_real_evidence_record(export)
    raw = {**record.payload(), "record_hash": record.record_hash}
    if not verify_judge_artifact(raw):
        raise RealExportError("derived record verification failed")
    rendered = render_real_evidence_markdown(record)
    # Refuse overwrite, including a repeated import of the same source.
    output.mkdir(parents=True, exist_ok=False)
    with (output / "judge-record.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(raw, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    with (output / "judge-record.md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    return raw
