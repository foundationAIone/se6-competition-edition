from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from typing import Any

BRIDGE_SCHEMA = "se6-public-bridge-v1"

EPISTEMIC_STATES = frozenset(
    {
        "MODEL_OUTPUT",
        "HYPOTHESIS",
        "OBSERVATION",
        "INDEPENDENT_EVIDENCE",
        "VERIFIED",
        "CONTRADICTED",
        "SUPERSEDED",
        "UNRESOLVED",
    }
)

BOUNDARY_DECISIONS = frozenset(
    {
        "ALLOW",
        "PAUSE",
        "REFUSE",
        "NEEDS_HUMAN_APPROVAL",
    }
)

EVIDENCE_CLASSES = frozenset(
    {
        "MODEL_OUTPUT",
        "OWNER_STATEMENT",
        "OBSERVATION",
        "INDEPENDENT_EVIDENCE",
        "EXECUTION_RECEIPT",
    }
)

TRANSITION_STATUSES = frozenset(
    {
        "NONE",
        "PROPOSED",
        "ACCEPTED",
        "REJECTED",
    }
)

SOURCE_NETWORK_AUTHORITY = frozenset(
    {
        "NONE",
        "SCOPED_APPROVAL",
    }
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_FORBIDDEN_TEXT = (
    "api_key",
    "api-key",
    "password",
    "passwd",
    "csrf",
    "cookie",
    "authorization:",
    "bearer ",
    "private key",
    "begin rsa private key",
    "begin openssh private key",
    "sk-",
    "c:\\users\\",
    "c:/users/",
    "/home/",
    "/users/",
)


class PublicBridgeError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_hash(value: Any) -> str:
    return sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PublicBridgeError(
            f"{field_name} must be nonempty text"
        )
    return value


def _require_sha256(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name).lower()

    if not _HEX64.fullmatch(text):
        raise PublicBridgeError(
            f"{field_name} must be lowercase SHA256"
        )

    return text


def _scan_public_value(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lower_key = str(key).lower()

            for marker in _FORBIDDEN_TEXT:
                if marker in lower_key:
                    raise PublicBridgeError(
                        f"private or secret-like field at {path}.{key}"
                    )

            _scan_public_value(
                item,
                f"{path}.{key}",
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_public_value(
                item,
                f"{path}[{index}]",
            )

    elif isinstance(value, str):
        lowered = value.lower()

        for marker in _FORBIDDEN_TEXT:
            if marker in lowered:
                raise PublicBridgeError(
                    f"private or secret-like content at {path}"
                )


@dataclass(frozen=True)
class BridgeEvidence:
    evidence_id: str
    evidence_class: str
    source_digest: str
    supports_claim: bool = False
    contradicts_claim: bool = False
    provenance_kind: str = "UNSPECIFIED"

    def __post_init__(self) -> None:
        if type(self.supports_claim) is not bool or type(self.contradicts_claim) is not bool:
            raise PublicBridgeError("evidence support and contradiction flags must be booleans")
        _require_text(
            self.evidence_id,
            "evidence_id",
        )

        if self.evidence_class not in EVIDENCE_CLASSES:
            raise PublicBridgeError(
                "invalid evidence_class"
            )

        _require_sha256(
            self.source_digest,
            "source_digest",
        )

        _require_text(
            self.provenance_kind,
            "provenance_kind",
        )

        if (
            self.supports_claim
            and self.contradicts_claim
        ):
            raise PublicBridgeError(
                "evidence cannot simultaneously support and contradict"
            )


@dataclass(frozen=True)
class PublicSE6BridgeEnvelope:
    schema_version: str
    case_id: str

    baseline_sha256: str
    source_record_sha256: str

    epistemic_state: str
    boundary_decision: str
    evidence: tuple[BridgeEvidence, ...]

    transition_status: str
    transition_digest: str | None = None

    verified_consequence_digest: str | None = None
    restart_reconstructed: bool | None = None

    # These two fields describe the SOURCE SE6 receipt.
    # They do not confer authority to Competition Edition.
    source_execution_authorized: bool | None = None
    source_action_executed: bool | None = None
    source_network_authority: str = "NONE"

    # These describe this PUBLIC bridge itself.
    public_read_only: bool = True
    public_authority_effect: str = "NONE"
    public_execution_authority: bool = False
    public_network_authority: str = "NONE"

    raw_private_payload_included: bool = False

    bridge_hash: str = field(default="")

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("bridge_hash", None)
        return value

    def verify_hash(self) -> bool:
        return (
            self.bridge_hash
            == canonical_hash(self.payload())
        )


_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "case_id",
        "baseline_sha256",
        "source_record_sha256",
        "epistemic_state",
        "boundary_decision",
        "evidence",
        "transition_status",
        "transition_digest",
        "verified_consequence_digest",
        "restart_reconstructed",
        "source_execution_authorized",
        "source_action_executed",
        "source_network_authority",
        "public_read_only",
        "public_authority_effect",
        "public_execution_authority",
        "public_network_authority",
        "raw_private_payload_included",
    }
)

_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "evidence_class",
        "source_digest",
        "supports_claim",
        "contradicts_claim",
        "provenance_kind",
    }
)


def parse_public_bridge(
    raw: dict[str, Any],
) -> PublicSE6BridgeEnvelope:

    if not isinstance(raw, dict):
        raise PublicBridgeError(
            "bridge export must be an object"
        )

    _scan_public_value(raw)

    extra = set(raw) - _TOP_LEVEL_FIELDS

    if extra:
        raise PublicBridgeError(
            "unknown bridge field: "
            + min(extra)
        )

    if raw.get("schema_version") != BRIDGE_SCHEMA:
        raise PublicBridgeError(
            "unsupported bridge schema"
        )

    case_id = _require_text(
        raw.get("case_id"),
        "case_id",
    )

    baseline_sha256 = _require_sha256(
        raw.get("baseline_sha256"),
        "baseline_sha256",
    )

    source_record_sha256 = _require_sha256(
        raw.get("source_record_sha256"),
        "source_record_sha256",
    )

    epistemic_state = _require_text(
        raw.get("epistemic_state"),
        "epistemic_state",
    )

    if epistemic_state not in EPISTEMIC_STATES:
        raise PublicBridgeError(
            "invalid epistemic_state"
        )

    boundary_decision = _require_text(
        raw.get("boundary_decision"),
        "boundary_decision",
    )

    if boundary_decision not in BOUNDARY_DECISIONS:
        raise PublicBridgeError(
            "invalid boundary_decision"
        )

    evidence_raw = raw.get("evidence")

    if not isinstance(evidence_raw, list):
        raise PublicBridgeError(
            "evidence must be a list"
        )

    evidence_items: list[BridgeEvidence] = []

    for item in evidence_raw:
        if not isinstance(item, dict):
            raise PublicBridgeError(
                "evidence entry must be an object"
            )

        extra_evidence = (
            set(item) - _EVIDENCE_FIELDS
        )

        if extra_evidence:
            raise PublicBridgeError(
                "unknown evidence field: "
                + min(extra_evidence)
            )

        evidence_items.append(
            BridgeEvidence(
                evidence_id=_require_text(
                    item.get("evidence_id"),
                    "evidence_id",
                ),
                evidence_class=_require_text(
                    item.get("evidence_class"),
                    "evidence_class",
                ),
                source_digest=_require_sha256(
                    item.get("source_digest"),
                    "source_digest",
                ),
                supports_claim=item.get("supports_claim", False),
                contradicts_claim=item.get("contradicts_claim", False),
                provenance_kind=_require_text(
                    item.get(
                        "provenance_kind",
                        "UNSPECIFIED",
                    ),
                    "provenance_kind",
                ),
            )
        )

    evidence = tuple(evidence_items)

    ids = [
        item.evidence_id
        for item in evidence
    ]

    if len(ids) != len(set(ids)):
        raise PublicBridgeError(
            "duplicate evidence_id"
        )

    transition_status = _require_text(
        raw.get("transition_status"),
        "transition_status",
    )

    if transition_status not in TRANSITION_STATUSES:
        raise PublicBridgeError(
            "invalid transition_status"
        )

    transition_digest = raw.get(
        "transition_digest"
    )

    if transition_digest is not None:
        transition_digest = _require_sha256(
            transition_digest,
            "transition_digest",
        )

    verified_digest = raw.get(
        "verified_consequence_digest"
    )

    if verified_digest is not None:
        verified_digest = _require_sha256(
            verified_digest,
            "verified_consequence_digest",
        )

    restart_reconstructed = raw.get(
        "restart_reconstructed"
    )

    if (
        restart_reconstructed is not None
        and not isinstance(
            restart_reconstructed,
            bool,
        )
    ):
        raise PublicBridgeError(
            "restart_reconstructed must be bool or null"
        )

    source_exec_auth = raw.get(
        "source_execution_authorized"
    )

    if (
        source_exec_auth is not None
        and not isinstance(
            source_exec_auth,
            bool,
        )
    ):
        raise PublicBridgeError(
            "source_execution_authorized must be bool or null"
        )

    source_executed = raw.get(
        "source_action_executed"
    )

    if (
        source_executed is not None
        and not isinstance(
            source_executed,
            bool,
        )
    ):
        raise PublicBridgeError(
            "source_action_executed must be bool or null"
        )

    source_network = _require_text(
        raw.get(
            "source_network_authority",
            "NONE",
        ),
        "source_network_authority",
    )

    if source_network not in SOURCE_NETWORK_AUTHORITY:
        raise PublicBridgeError(
            "invalid source_network_authority"
        )

    # PUBLIC competition layer is always inert.
    if raw.get("public_read_only") is not True:
        raise PublicBridgeError(
            "public bridge must be read_only"
        )

    if (
        raw.get("public_authority_effect")
        != "NONE"
    ):
        raise PublicBridgeError(
            "public authority_effect must be NONE"
        )

    if (
        raw.get("public_execution_authority")
        is not False
    ):
        raise PublicBridgeError(
            "public bridge cannot have execution authority"
        )

    if (
        raw.get("public_network_authority")
        != "NONE"
    ):
        raise PublicBridgeError(
            "public bridge cannot have network authority"
        )

    if (
        raw.get("raw_private_payload_included")
        is not False
    ):
        raise PublicBridgeError(
            "raw private payload is forbidden"
        )

    independent_support = any(
        item.evidence_class
        == "INDEPENDENT_EVIDENCE"
        and item.supports_claim
        for item in evidence
    )

    independent_contradiction = any(
        item.evidence_class
        == "INDEPENDENT_EVIDENCE"
        and item.contradicts_claim
        for item in evidence
    )

    if (
        epistemic_state == "VERIFIED"
        and not independent_support
    ):
        raise PublicBridgeError(
            "VERIFIED requires independent supporting evidence"
        )

    if (
        epistemic_state == "CONTRADICTED"
        and not independent_contradiction
    ):
        raise PublicBridgeError(
            "CONTRADICTED requires independent contradictory evidence"
        )

    if epistemic_state == "VERIFIED" and independent_contradiction:
        raise PublicBridgeError("contradicting independent evidence cannot be VERIFIED")

    if verified_digest is not None and epistemic_state != "VERIFIED":
        raise PublicBridgeError("verified consequence requires VERIFIED epistemic state")

    if (
        source_executed is True
        and source_exec_auth is not True
    ):
        raise PublicBridgeError(
            "executed source action requires recorded source authority"
        )

    if source_executed is True:
        has_execution_receipt = any(
            item.evidence_class
            == "EXECUTION_RECEIPT"
            for item in evidence
        )

        if not has_execution_receipt:
            raise PublicBridgeError(
                "executed source action requires execution receipt"
            )

    if (
        transition_status == "ACCEPTED"
        and transition_digest is None
    ):
        raise PublicBridgeError(
            "accepted transition requires transition_digest"
        )

    envelope = PublicSE6BridgeEnvelope(
        schema_version=BRIDGE_SCHEMA,
        case_id=case_id,
        baseline_sha256=baseline_sha256,
        source_record_sha256=source_record_sha256,
        epistemic_state=epistemic_state,
        boundary_decision=boundary_decision,
        evidence=evidence,
        transition_status=transition_status,
        transition_digest=transition_digest,
        verified_consequence_digest=verified_digest,
        restart_reconstructed=restart_reconstructed,
        source_execution_authorized=source_exec_auth,
        source_action_executed=source_executed,
        source_network_authority=source_network,
        public_read_only=True,
        public_authority_effect="NONE",
        public_execution_authority=False,
        public_network_authority="NONE",
        raw_private_payload_included=False,
        bridge_hash="",
    )

    return replace(
        envelope,
        bridge_hash=canonical_hash(
            envelope.payload()
        ),
    )
