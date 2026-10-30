"""Versioned modes; the Mirror reader is test-only and durable mode is reserved."""
from __future__ import annotations
from dataclasses import asdict, dataclass

CONTRACT_VERSION = "se6-competition-integration-modes-v2"


@dataclass(frozen=True)
class IntegrationMode:
    id: str
    integration: str
    context_policy: str | None
    enabled: bool
    state_source: str
    required_evidence: tuple[str, ...]


MODES = (
    IntegrationMode("LEGACY_STRUCTURED_CORE", "executable_se6", "audit_v3", True,
                    "ISOLATED_TASK_KERNEL", ("kernel_hash", "local_receipt", "task_checkpoint")),
    IntegrationMode("COMPACT_STRUCTURED_CORE", "executable_se6", "compact_v1", True,
                    "ISOLATED_TASK_KERNEL", ("kernel_hash", "local_receipt", "task_checkpoint")),
    IntegrationMode("VERIFIED_MIRROR", "verified_mirror", "compact_v1", True,
                    "PINNED_ISOLATED_TEST_ENTITY_EXPORT", ("audited_identity", "state_hash", "canonical_provenance",
                                      "read_only_snapshot", "epistemic_classes")),
    IntegrationMode("DURABLE_ENTITY_EXPERIMENTAL", "durable_entity_experimental", None, False,
                    "NOT_CONNECTED", ("isolated_durable_entity", "identity_lineage",
                                      "bounded_authority", "consequence_receipts")),
    IntegrationMode("NATIVE_MATHEMATICS_V1", "native_mathematics", "math_end_to_end_v1", True,
                    "ISOLATED_NATIVE_MATH_TASK_STATE", ("source_hashes", "public_problem_hash", "checked_deduction", "task_checkpoint")),
    IntegrationMode("NATIVE_MATHEMATICS_V1_MECHANISM_CONTROL", "native_mathematics", "math_mechanism_controlled_v1", True,
                    "ISOLATED_NATIVE_MATH_TASK_STATE_AND_STATELESS_SHARED_CHECKING", ("source_hashes", "checked_deduction", "task_checkpoint")),
    IntegrationMode("NATIVE_MATHEMATICS_COMPACT_BOUNDED_V1", "native_mathematics", "math_compact_end_to_end_v1", False,
                    "OFFLINE_PREPARED_PROVIDER_CONTROLS_UNVERIFIED", ("source_hashes", "checked_deduction", "verified_provider_reasoning_mapping")),
)


def require_mode(mode_id):
    mode = next((m for m in MODES if m.id == mode_id), None)
    if mode is None or not mode.enabled:
        raise ValueError("Integration mode NOT YET ENABLED; no source or fallback is connected.")
    return mode


def contract():
    return {"schema_version": CONTRACT_VERSION, "modes": [asdict(m) for m in MODES],
            "production_entity_connected": False,
            "adapter_interface": "src.workbench.integrations.ExecutableSE6Contract",
            "read_only_adapter_interface": "src.workbench.integrations.ReadOnlyStateContextContract",
            "future_modes_enablement": "Disabled modes require a separately verified adapter. Enabled Mirror reads pinned test fixtures only; no production access."}
