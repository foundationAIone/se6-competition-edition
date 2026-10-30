from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.contracts.judge_record import (
    JudgeComparison,
    JudgeRecord,
    ModelAloneLane,
    PublicEvidence,
    SE6Lane,
    canonical_hash,
)


class JudgeModeError(ValueError):
    pass


def _nonempty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JudgeModeError(f"{field} must be nonempty text")
    return value


def build_record(raw: dict[str, Any]) -> JudgeRecord:
    if not isinstance(raw, dict):
        raise JudgeModeError("case must be an object")

    if raw.get("schema_version") != "se6-judge-input-v1":
        raise JudgeModeError("unsupported schema_version")

    case_id = _nonempty_text(raw.get("case_id"), "case_id")
    task = _nonempty_text(raw.get("task"), "task")

    model = raw.get("model")
    if not isinstance(model, dict):
        raise JudgeModeError("model object required")

    provider = _nonempty_text(model.get("provider"), "provider")
    model_id = _nonempty_text(model.get("model_id"), "model_id")
    model_output = _nonempty_text(model.get("output"), "model.output")

    evidence_raw = raw.get("evidence", [])
    if not isinstance(evidence_raw, list):
        raise JudgeModeError("evidence must be a list")

    evidence = tuple(
        PublicEvidence(
            evidence_id=_nonempty_text(
                item.get("evidence_id"),
                "evidence_id",
            ),
            evidence_class=_nonempty_text(
                item.get("evidence_class"),
                "evidence_class",
            ),
            supports_claim=item.get("supports_claim", False),
            contradicts_claim=item.get("contradicts_claim", False),
            provenance=item.get("provenance"),
        )
        for item in evidence_raw
        if isinstance(item, dict)
    )

    if len(evidence) != len(evidence_raw):
        raise JudgeModeError("every evidence item must be an object")

    evidence_by_id = {
        item.evidence_id: item
        for item in evidence
    }

    if len(evidence_by_id) != len(evidence):
        raise JudgeModeError("duplicate evidence_id")

    alone_raw = raw.get("model_alone")
    if not isinstance(alone_raw, dict):
        raise JudgeModeError("model_alone object required")

    model_alone = ModelAloneLane(
        retained_claim=alone_raw.get("retained_claim"),
        claimed_verification=alone_raw.get("claimed_verification", False),
        action=alone_raw.get("action"),
        result=alone_raw.get("result"),
    )

    se6_raw = raw.get("se6")
    if not isinstance(se6_raw, dict):
        raise JudgeModeError("se6 object required")

    refs_raw = se6_raw.get("evidence_refs", [])

    if not isinstance(refs_raw, list):
        raise JudgeModeError("se6.evidence_refs must be a list")

    refs = tuple(str(ref) for ref in refs_raw)

    if len(set(refs)) != len(refs):
        raise JudgeModeError("duplicate se6 evidence reference")

    unknown = [
        ref
        for ref in refs
        if ref not in evidence_by_id
    ]

    if unknown:
        raise JudgeModeError(
            "unknown SE6 evidence reference: " + unknown[0]
        )

    se6 = SE6Lane(
        epistemic_state=_nonempty_text(
            se6_raw.get("epistemic_state"),
            "se6.epistemic_state",
        ),
        boundary_decision=_nonempty_text(
            se6_raw.get("boundary_decision"),
            "se6.boundary_decision",
        ),
        evidence_refs=refs,
        execution_authority=se6_raw.get("execution_authority", False),
        verified_consequence=se6_raw.get(
            "verified_consequence"
        ),
        state_transition=se6_raw.get("state_transition"),
        restart_reconstructed=se6_raw.get(
            "restart_reconstructed"
        ),
    )

    selected = [
        evidence_by_id[ref]
        for ref in se6.evidence_refs
    ]

    independent_support = any(
        item.evidence_class == "INDEPENDENT_EVIDENCE"
        and item.supports_claim
        for item in selected
    )

    independent_contradiction = any(
        item.evidence_class == "INDEPENDENT_EVIDENCE"
        and item.contradicts_claim
        for item in selected
    )

    if (
        se6.epistemic_state == "VERIFIED"
        and not independent_support
    ):
        raise JudgeModeError(
            "VERIFIED requires cited independent supporting evidence"
        )

    if (
        se6.epistemic_state == "CONTRADICTED"
        and not independent_contradiction
    ):
        raise JudgeModeError(
            "CONTRADICTED requires cited independent contradiction"
        )

    if (
        independent_contradiction
        and se6.epistemic_state == "VERIFIED"
    ):
        raise JudgeModeError(
            "contradicting independent evidence cannot be VERIFIED"
        )

    comparison = JudgeComparison(
        same_model_output=True,
        retention_changed=(
            model_alone.retained_claim
            != se6.state_transition
        ),
        model_alone_claimed_verification=(
            model_alone.claimed_verification
        ),
        se6_epistemic_state=se6.epistemic_state,
        se6_boundary_decision=se6.boundary_decision,
        se6_restart_reconstructed=(
            se6.restart_reconstructed
        ),
        overall_verdict=None,
    )

    record = JudgeRecord(
        schema_version="se6-judge-record-v1",
        case_id=case_id,
        task=task,
        provider=provider,
        model_id=model_id,
        model_output=model_output,
        evidence=evidence,
        model_alone=model_alone,
        se6=se6,
        comparison=comparison,
        synthetic=raw.get("synthetic", False),
        record_hash="",
    )

    return replace(
        record,
        record_hash=canonical_hash(record.payload()),
    )


def render_markdown(record: JudgeRecord) -> str:
    if not record.verify_hash():
        raise JudgeModeError("judge record hash mismatch")
    lines = [
        f"# Judge Record: {record.case_id}",
        "",
        f"**Synthetic:** {str(record.synthetic).lower()}",
        "",
        "## Task",
        "",
        record.task,
        "",
        "## Shared model output",
        "",
        f"Provider: `{record.provider}`",
        "",
        f"Model: `{record.model_id}`",
        "",
        record.model_output,
        "",
        "## MODEL ALONE",
        "",
        f"- Retained claim: `{record.model_alone.retained_claim}`",
        (
            "- Claimed verification: "
            f"`{record.model_alone.claimed_verification}`"
        ),
        f"- Action: `{record.model_alone.action}`",
        f"- Result: `{record.model_alone.result}`",
        "",
        "## MODEL + SE6",
        "",
        f"- Epistemic state: `{record.se6.epistemic_state}`",
        f"- Boundary: `{record.se6.boundary_decision}`",
        (
            "- Execution authority: "
            f"`{record.se6.execution_authority}`"
        ),
        (
            "- Verified consequence: "
            f"`{record.se6.verified_consequence}`"
        ),
        f"- State transition: `{record.se6.state_transition}`",
        (
            "- Restart reconstructed: "
            f"`{record.se6.restart_reconstructed}`"
        ),
        "",
        "## Evidence",
        "",
    ]

    if record.evidence:
        for item in record.evidence:
            lines.append(
                "- "
                f"`{item.evidence_id}` "
                f"[{item.evidence_class}] "
                f"supports={item.supports_claim} "
                f"contradicts={item.contradicts_claim}"
            )
    else:
        lines.append("- None")

    lines += [
        "",
        "## Factual comparison",
        "",
        (
            "- Same model output supplied to comparison: "
            f"`{record.comparison.same_model_output}`"
        ),
        (
            "- Retained state differs: "
            f"`{record.comparison.retention_changed}`"
        ),
        (
            "- Model-alone claimed verification: "
            f"`{record.comparison.model_alone_claimed_verification}`"
        ),
        (
            "- SE6 epistemic state: "
            f"`{record.comparison.se6_epistemic_state}`"
        ),
        (
            "- SE6 boundary decision: "
            f"`{record.comparison.se6_boundary_decision}`"
        ),
        "",
        "## Overall verdict",
        "",
        "None. Judge Mode records evidence; it does not select a winner.",
        "",
        f"Record SHA256: `{record.record_hash}`",
        "",
    ]

    return "\n".join(lines)


def load_case(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def build_real_evidence_record(raw: dict[str, Any]):
    """Review an unpaired real snapshot without constructing a model lane."""
    from src.contracts.public_se6_bridge import canonical_json
    from src.contracts.real_judge_record import RealEvidenceJudgeRecord
    from src.real_evidence.competition_export import (
        to_public_bridge,
        validate_competition_export,
    )

    export = validate_competition_export(raw)
    record = RealEvidenceJudgeRecord(
        export_json=canonical_json(export),
        bridge=to_public_bridge(export),
    )
    return replace(record, record_hash=canonical_hash(record.payload()))


def render_real_evidence_markdown(record) -> str:
    if not record.verify_hash():
        raise JudgeModeError("real evidence record hash mismatch")
    value = record.payload()
    lines = [
        "# Judge Mode: first real SE6 evidence", "",
        "EVIDENCE_ORIGIN=REAL_SE6  ",
        "REAL_SE6_EVIDENCE=YES  ",
        "SYNTHETIC_FIXTURE=NO  ",
        "PAIRED_MODEL_RESULT=NOT_YET_AVAILABLE  ",
        "PAIRED_MODEL_COMPARISON=PENDING  ",
        "OVERALL_VERDICT=null", "",
        f"Export SHA256: `{value['export_sha256']}`  ",
        f"Historical baseline SHA256: `{value['baseline_sha256']}`", "",
        ("The supplied public export's digest is verified. This proves payload consistency; "
         "it is not independent verification of cognition, receipt availability, or a model comparison."), "",
        "## Source Entity projection", "", "| Field | Exported value |", "|---|---|",
    ]
    def display(item):
        return "UNAVAILABLE (null)" if item is None else json.dumps(item, ensure_ascii=False)

    lines += [f"| {key} | `{display(item)}` |" for key, item in value["entity"].items()]
    lines += ["", "## Source evidence projection", "", "| Field | Exported value |", "|---|---|"]
    lines += [f"| {key} | `{display(item)}` |" for key, item in value["evidence"].items()]
    lines += [
        "", "## Public boundary", "",
        "PUBLIC_EXECUTION_AUTHORITY=NONE  ",
        "PUBLIC_NETWORK_AUTHORITY=NONE  ",
        "PUBLIC_AUTHORITY_EFFECT=NONE  ",
        "RAW_PRIVATE_PAYLOAD=FALSE", "",
        "## Public review disposition", "",
        ("The existing v1 bridge validates the inert public review envelope. Its UNRESOLVED / "
         "PAUSE / NONE classifications mean judgment is withheld and no public transition is accepted. "
         "They are public adapter policy, not claims about a source SE6 boundary decision or transition. "
         "Those source classifications remain UNAVAILABLE (null). No standalone source-receipt bridge is emitted."), "",
        ("Authority mapping scope: SOURCE_EXPORT_PUBLIC_CONTRACT_ONLY. "
         "The bridge's source_execution_authorized=false maps only to the source export's "
         "public_contract.execution_authority=false. It conveys no execution authority. "
         "Runtime action authorization was not exported and remains UNAVAILABLE (null); "
         "source_action_executed also remains null."), "",
        ("Source readiness and Entity continuity do not fill null consequence-verification or receipt fields. "
         "The source restart flag is preserved without claiming reconstructed restart evidence."), "",
        "No MODEL ALONE result was supplied. Judge Mode records evidence; it does not select a winner.", "",
        f"Public review bridge SHA256: `{record.bridge.bridge_hash}`  ",
        f"Judge record SHA256: `{record.record_hash}`", "",
    ]
    return "\n".join(line.rstrip() for line in lines)
