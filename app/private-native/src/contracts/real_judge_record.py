"""Immutable unpaired real-evidence record, distinct from synthetic comparisons."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from src.contracts.public_se6_bridge import PublicSE6BridgeEnvelope, canonical_hash


@dataclass(frozen=True)
class RealEvidenceJudgeRecord:
    # JSON text makes the source projection immutable, including nested fields.
    export_json: str
    bridge: PublicSE6BridgeEnvelope
    record_hash: str = ""

    def payload(self) -> dict:
        export = json.loads(self.export_json)
        return {
            "schema_version": "se6-real-evidence-judge-record-v1",
            "evidence_origin": "REAL_SE6",
            "synthetic_fixture": False,
            "source_export_schema": export["schema_version"],
            "export_sha256": export["export_sha256"],
            "baseline_sha256": export["baseline_sha256"],
            "entity": export["entity"],
            "evidence": export["evidence"],
            "public_contract": export["public_contract"],
            "public_review": {
                "scope": "PUBLIC_IMPORT_DISPOSITION_NOT_SOURCE_DECISION",
                "source_boundary_decision": None,
                "source_transition_status": None,
                "authority_mapping": {
                    "scope": "SOURCE_EXPORT_PUBLIC_CONTRACT_ONLY",
                    "source_field": "public_contract.execution_authority",
                    "runtime_action_authorization": None,
                },
                "bridge": asdict(self.bridge),
            },
            "model_alone": None,
            "paired_model_comparison": "PENDING",
            "paired_model_result": "NOT_YET_AVAILABLE",
            "overall_verdict": None,
        }

    def verify_hash(self) -> bool:
        return self.bridge.verify_hash() and self.record_hash == canonical_hash(self.payload())
