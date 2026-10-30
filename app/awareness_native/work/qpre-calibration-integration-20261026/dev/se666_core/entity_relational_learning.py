"""Bounded relational learning through the existing Entity event/memory path.

No store, transport, model invocation, or authority is created here. Original
provider records remain immutable in cognition storage; Entity memory retains
their exact IDs/hashes and a separately scoped verification of source assertions.
Owner assertions remain USER_SUPPLIED, including after correction.
"""
from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime

from .canonical_contracts import ExecutionStatus, canonical_sha256
from .entity_cognition import EvidenceSourceKind, create_evidence_reference
from .entity_events import (
    AuthorityStatus, EntityEventDraft, EventEndpoint, EventSourceKind, EventType,
    InteractionPayload, LoopName, MemoryEventOperation, MemoryPayload,
    ObservationPayload, ObservationProvenance, PersistencePolicy,
    SensitivityClassification, VerificationPayload, VerificationResult,
)
from .epistemic_status import EpistemicStatus
from .entity_state import MemoryStatus

OWNER_RELATION = "owner_supplied_property"
PROVIDER_RELATION = "retained_provider_hypothesis"
_ID = r"cognition_memory_[0-9a-f]{64}"
_FACT = re.compile(
    r"^(?P<prefix>For this test,|Fact:|Correction:)\s*"
    r"(?P<subject>[\w][\w .-]{0,79})['’]s\s+"
    r"(?P<property>[\w][\w -]{0,79})\s+is\s+"
    r"(?P<value>[^\n\r.!?]{1,160})\.?$", re.IGNORECASE,
)
_QUERY = re.compile(
    r"^What is (?P<subject>[\w][\w .-]{0,79})['’]s "
    r"(?P<property>[\w][\w -]{0,79})(?:, and how do you know)?\?$",
    re.IGNORECASE,
)
_DIGITAL_QUERY = re.compile(
    r"^Assess retained digital basis for path-sha256 ([0-9a-f]{64}) "
    r"at content-sha256 ([0-9a-f]{64})\.$"
)


def digital_basis_query(path_sha256: str, content_sha256: str) -> str:
    """Request revision applicability, never assert that a requested hash is true."""
    text = f"Assess retained digital basis for path-sha256 {path_sha256} at content-sha256 {content_sha256}."
    if _DIGITAL_QUERY.fullmatch(text) is None:
        raise ValueError("DIGITAL_BASIS_HASH_REQUIRED")
    return text


def _digital_observation(event) -> dict | None:
    payload = event.payload
    if (not isinstance(payload, ObservationPayload)
            or event.event_type is not EventType.OBSERVATION
            or event.relation != "observes_local_state"
            or event.source.kind is not EventSourceKind.SYSTEM
            or event.source.identifier != "LOCAL_STATE_ADAPTER"
            or event.provenance is not ObservationProvenance.SYSTEM_OBSERVED
            or event.epistemic_status is not EpistemicStatus.MEASURED
            or payload.provenance is not ObservationProvenance.SYSTEM_OBSERVED
            or payload.relation != "measured_file_content_digest"
            or not payload.current_claim
            or payload.observed_at_utc > event.occurred_at_utc):
        return None
    location = re.fullmatch(r"local-file-path-sha256:([0-9a-f]{64})", payload.world_node)
    measured = re.fullmatch(r"Measured local file bytes=([0-9]+); content_sha256=([0-9a-f]{64}); structural_kind=(utf8-text|json|binary); no assertion about file meaning or external World truth\.", payload.value_summary)
    prefixes = ("digital-receipt-sha256", "local-file-sha256", "universal-map-sha256",
                "shadow-x-sha256", "shadow-theta-sha256", "local-observation-id")
    if location is None or measured is None or len(payload.evidence_references) != 6:
        return None
    values = {}
    for prefix, reference in zip(prefixes, payload.evidence_references):
        pattern = prefix + r":(" + ("source_observation_" if prefix == "local-observation-id" else "") + r"[0-9a-f]{64})"
        match = re.fullmatch(pattern, reference)
        if match is None:
            return None
        values[prefix] = match[1]
    if (int(measured[1]) > 1_048_576 or measured[2] != values["local-file-sha256"]
            or event.correlation_id != "digital-file-observation:" + values["digital-receipt-sha256"]):
        return None
    return dict(kind="measured_digital_basis", path_sha256=location[1],
                content_sha256=measured[2], byte_count=int(measured[1]),
                structural_kind=measured[3], observation_event_id=event.event_id,
                observed_at_utc=payload.observed_at_utc.isoformat(), bindings=values)


def digital_basis_decision(event, state) -> tuple[str, tuple[str, ...]] | None:
    """Select evidence applicability from retained measured state, with no effect."""
    if (event.event_type is not EventType.USER_MESSAGE
            or event.source.kind is not EventSourceKind.PROGRAMMERONE
            or not isinstance(event.payload, InteractionPayload)):
        return None
    request = _DIGITAL_QUERY.fullmatch(event.payload.text.strip())
    if request is None:
        return None
    path_hash, requested_hash = request.groups()
    world_node = "local-file-path-sha256:" + path_hash
    relation = next((r for r in state.environment.relations if r.world_node == world_node
        and r.relation == "measured_file_content_digest" and r.current and r.superseded_by is None), None)
    memory = next((m for m in reversed(state.memory.active_at(event.occurred_at_utc))
        if m.subject == world_node and m.epistemic_status is EpistemicStatus.MEASURED
        and m.status is MemoryStatus.PROVISIONAL
        and m.recorded_at_utc <= event.occurred_at_utc and _content(m).get("kind") == "measured_digital_basis"), None)
    decision, reason, refs = "REMEASUREMENT_REQUIRED", "NO_CURRENT_RETAINED_MEASURED_BASIS", ()
    if memory is not None:
        data = _content(memory)
        refs = memory.source_event_ids[:8]
        retained_proof = next((m for m in state.memory.active_at(event.occurred_at_utc)
            if m.status is MemoryStatus.VERIFIED and m.epistemic_status is EpistemicStatus.VERIFIED
            and m.recorded_at_utc <= event.occurred_at_utc
            and m.subject in {"verification:" + source for source in memory.source_event_ids}
            and m.evidence_references == (memory.memory_id, *memory.evidence_references)
            and m.content_summary.startswith("Verified retention of measured digital basis from "
                                            + str(data.get("observation_event_id")) + ",")), None)
        if (relation is None or relation.epistemic_status is not EpistemicStatus.MEASURED
                or relation.observed_at_utc > event.occurred_at_utc
                or relation.source_event_id != data.get("observation_event_id")
                or relation.evidence_references != memory.evidence_references
                or relation.source_event_id not in memory.source_event_ids
                or data.get("path_sha256") != path_hash
                or "local-file-sha256:" + str(data.get("content_sha256")) not in memory.evidence_references
                or data.get("observed_at_utc") != relation.observed_at_utc.isoformat()
                or f"content_sha256={data.get('content_sha256')};" not in relation.value_summary):
            reason = "RETAINED_BASIS_NOT_CURRENT_IN_RELATIONAL_STATE"
        elif retained_proof is None:
            reason = "RETENTION_VERIFICATION_NOT_CURRENT"
        elif data.get("content_sha256") != requested_hash:
            reason = "REQUESTED_REVISION_DIFFERS_FROM_RETAINED_MEASUREMENT"
        else:
            decision, reason = "REUSE_MEASURED_BASIS", "REQUESTED_REVISION_MATCHES_CURRENT_RETAINED_MEASUREMENT"
            refs = tuple(dict.fromkeys((*refs, *retained_proof.source_event_ids)))[:8]
    result = dict(kind="digital_basis_applicability_decision_v1", decision=decision,
        reason=reason, requested_path_sha256=path_hash, requested_content_sha256=requested_hash,
        state_used=state.entity_state_id, state_version=state.state_version,
        memory_id=memory.memory_id if memory is not None else None,
        relation_id=relation.relation_id if relation is not None else None,
        authority_effect="NONE", scope="Applicability to requested file revision only; no current-file, equation-meaning or independent World-truth claim.")
    return _json(result), refs


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def review_command(text: str) -> str | None:
    match = re.fullmatch(rf"Review retained candidate ({_ID})\.?", text.strip())
    return match[1] if match else None


def parse_fact(text: str) -> dict | None:
    match = _FACT.fullmatch(text.strip())
    if match is None:
        return None
    return {"kind": "owner_fact", "subject": match["subject"].strip(),
            "property": match["property"].strip(), "value": match["value"].strip(),
            "provenance": "OWNER_SUPPLIED_CORRECTION" if match["prefix"].lower() == "correction:" else "OWNER_SUPPLIED"}


def fact_subject(fact: dict) -> str:
    return "owner-fact:" + canonical_sha256(
        (fact["subject"].casefold(), fact["property"].casefold()))


def _content(record) -> dict:
    try:
        data = json.loads(record.content_summary)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def observation_summary(payload) -> str:
    if payload.relation == OWNER_RELATION:
        data = json.loads(payload.value_summary)
        return f"{data['subject']}'s {data['property']} is {data['value']} ({data['provenance']})."
    if payload.relation == PROVIDER_RELATION:
        data = json.loads(payload.value_summary)
        return f"Retained model hypothesis {data['candidate_id']}; {len(data['claim_reviews'])} scoped source checks."
    value = payload.value_summary
    if len(value) <= 500:
        return value
    # ObservationPayload retains up to 2,000 characters; the derived Awareness
    # display has a separate 500-character bound. Never truncate source evidence.
    prefix = "Preview; full observation retained: "
    return prefix + value[:499 - len(prefix)] + "…"


def observation_value(payload) -> str:
    # Attribution changes are retained in history but are not value contradictions.
    if payload.relation == OWNER_RELATION:
        return json.loads(payload.value_summary)["value"]
    return payload.value_summary


def owner_fact(event) -> dict | None:
    if (event.event_type is not EventType.USER_MESSAGE
            or event.source.kind is not EventSourceKind.PROGRAMMERONE
            or event.provenance is not ObservationProvenance.USER_REPORTED
            or not isinstance(event.payload, InteractionPayload)):
        return None
    return parse_fact(event.payload.text)


def _derived(cause, *, event_type, loop, relation, payload, provenance, epistemic):
    return EntityEventDraft(
        event_type=event_type, occurred_at_utc=cause.occurred_at_utc,
        originating_loop=loop,
        source=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
        target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
        relation=relation, provenance=provenance, epistemic_status=epistemic,
        authority_status=AuthorityStatus.NOT_REQUIRED, correlation_id=cause.correlation_id,
        causal_id=cause.event_id, parent_event_id=cause.event_id,
        sensitivity=cause.sensitivity, persistence_policy=PersistencePolicy.DURABLE_AUDIT,
        payload=payload,
    )


def owner_observation(event, state) -> EntityEventDraft | None:
    fact = owner_fact(event)
    if fact is None:
        return None
    prior = next((m for m in state.memory.active_at(event.occurred_at_utc)
                  if m.subject == fact_subject(fact)), None)
    # A differing assertion must explicitly identify itself as a correction.
    if (fact["provenance"] == "OWNER_SUPPLIED_CORRECTION" and prior is None
            or prior is not None and fact["provenance"] != "OWNER_SUPPLIED_CORRECTION"
            and _content(prior).get("value") != fact["value"]):
        return None
    fact["owner_event_id"] = event.event_id
    return _derived(event, event_type=EventType.OBSERVATION, loop=LoopName.PRESENCE,
        relation=OWNER_RELATION,
        provenance=ObservationProvenance.USER_REPORTED, epistemic=EpistemicStatus.USER_SUPPLIED,
        payload=ObservationPayload(world_node=fact_subject(fact), relation=OWNER_RELATION,
            value_summary=_json(fact), provenance=ObservationProvenance.USER_REPORTED,
            observed_at_utc=event.occurred_at_utc, evidence_references=(event.event_id,),
            confidence_basis_points=0))


def memory_from_observation(
    event,
    state,
    history,
    *,
    allow_reassertion: bool = False,
) -> EntityEventDraft | None:
    payload = event.payload
    if not isinstance(payload, ObservationPayload):
        return None
    digital = _digital_observation(event)
    if digital is not None:
        if any(m.subject == payload.world_node and _content(m) == digital
               for m in state.memory.active_at(event.occurred_at_utc)):
            return None
        return _derived(event, event_type=EventType.MEMORY_CANDIDATE,
            loop=LoopName.AWARENESS, relation="retains_relational_learning",
            provenance=ObservationProvenance.SYSTEM_OBSERVED, epistemic=EpistemicStatus.MEASURED,
            payload=MemoryPayload(operation=MemoryEventOperation.CANDIDATE,
                subject=payload.world_node, content_summary=_json(digital),
                source_event_ids=(event.event_id,), evidence_references=payload.evidence_references))
    if event.relation not in {OWNER_RELATION, PROVIDER_RELATION}:
        return None
    data = json.loads(payload.value_summary)
    prior = None
    if event.relation == OWNER_RELATION:
        original = next((e for e in history if e.event_id == data.get("owner_event_id")), None)
        fact = owner_fact(original) if original is not None else None
        if (original is None or fact is None or any(data.get(k) != v for k, v in fact.items())
                or payload.world_node != fact_subject(fact)
                or event.provenance is not ObservationProvenance.USER_REPORTED
                or payload.evidence_references != (original.event_id,)):
            return None
        prior = next((m for m in state.memory.active_at(event.occurred_at_utc)
                      if m.subject == payload.world_node), None)
        same_reassertion = (
            prior is not None and _content(prior).get("value") == fact["value"]
        )
        if same_reassertion and not allow_reassertion:
            return None
        if (
            not (allow_reassertion and same_reassertion)
            and (prior is not None)
            != (fact["provenance"] == "OWNER_SUPPLIED_CORRECTION")
        ):
            return None
        provenance, epistemic = ObservationProvenance.USER_REPORTED, EpistemicStatus.USER_SUPPLIED
    else:
        if (event.source.kind is not EventSourceKind.COMPONENT
                or event.source.identifier != "retained-provider-review"
                or event.provenance is not ObservationProvenance.MODEL_INFERRED):
            return None
        provenance, epistemic = ObservationProvenance.MODEL_INFERRED, EpistemicStatus.MODEL_PROPOSED
    return _derived(event, event_type=EventType.MEMORY_CONSOLIDATION if prior else EventType.MEMORY_CANDIDATE,
        loop=LoopName.AWARENESS, relation="retains_relational_learning",
        provenance=provenance, epistemic=epistemic,
        payload=MemoryPayload(operation=MemoryEventOperation.SUPERSEDE if prior else MemoryEventOperation.CANDIDATE,
            subject=payload.world_node, content_summary=payload.value_summary,
            source_event_ids=tuple(dict.fromkeys((event.event_id, *(
                (data["owner_event_id"],) if event.relation == OWNER_RELATION else ())))),
            evidence_references=payload.evidence_references,
            supersedes_memory_id=prior.memory_id if prior else None))


def retention_verification(
    event,
    before,
    after,
    history,
    *,
    allow_reassertion: bool = False,
    verified_at_utc: datetime | None = None,
) -> EntityEventDraft | None:
    """Verify the committed representation against its attributable source event.

    This proves retention and a bounded source comparison, never the physical
    truth of an owner assertion or a model's interpretation.
    """
    if not isinstance(event.payload, MemoryPayload) or event.relation != "retains_relational_learning":
        return None
    observation = next((e for e in history if e.event_id == event.parent_event_id), None)
    if observation is None:
        return None
    expected = memory_from_observation(
        observation,
        before,
        history,
        allow_reassertion=allow_reassertion,
    )
    if expected is None or expected.payload != event.payload:
        return None
    retained = next((m for m in after.records if event.event_id in m.source_event_ids
                     and m.content_summary == event.payload.content_summary), None)
    if retained is None:
        return None
    data = _content(retained)
    if data["kind"] == "measured_digital_basis":
        summary = (f"Verified retention of measured digital basis from {data['observation_event_id']}, "
                   f"content digest {data['content_sha256']}, with exact source-event and six-reference ancestry. "
                   "The retained observation remains MEASURED/PROVISIONAL; this verifies retention only, "
                   "not current file contents, equation meaning or independent World truth.")
    elif data["kind"] == "owner_fact":
        summary = (f"Verified retention of {data['provenance']} assertion: {data['subject']}'s "
                   f"{data['property']} is {data['value']}. The assertion remains USER_SUPPLIED; "
                   "its physical truth was not independently verified.")
    else:
        results = "; ".join(f"relationship {r['index']}: {r['result']}" for r in data["claim_reviews"])
        summary = (f"Verified canonical retention of candidate {data['candidate_id']}. "
                   f"Source assertion checks: {results or 'no relationship claims'}. "
                   "Verification scope: saved document assertions only. The original candidate remains HYPOTHESIS; "
                   "node interpretations, alternatives and physical identity remain unverified.")
    proof = _derived(event, event_type=EventType.VERIFICATION, loop=LoopName.BECOMING,
        relation="verifies_relational_retention",
        provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED, epistemic=EpistemicStatus.VERIFIED,
        payload=VerificationPayload(subject_event_id=event.event_id, result=VerificationResult.PASSED,
            independently_verified=True, evidence_references=(retained.memory_id, *retained.evidence_references),
            summary=summary))
    if verified_at_utc is None:
        return proof  # Preserve historical/default pure-reducer semantics.
    if (verified_at_utc.tzinfo is None or verified_at_utc.utcoffset() is None
            or verified_at_utc < event.occurred_at_utc):
        raise ValueError("RETENTION_VERIFICATION_TIME_INVALID")
    # The observation's time/provenance is unchanged. Only the new retention
    # attestation gets its trusted evaluation time; its existing 24-hour TTL
    # and all decision freshness checks still apply.
    return proof.model_copy(update={"occurred_at_utc": verified_at_utc})


def learning_response(event, state) -> tuple[str, tuple[str, ...]] | None:
    if not isinstance(event.payload, InteractionPayload) or event.event_type is not EventType.USER_MESSAGE:
        return None
    digital = digital_basis_decision(event, state)
    if digital is not None:
        return digital
    if review_command(event.payload.text) is not None:
        return ("Review of the retained candidate was requested. Retention and source verification "
                "must complete before a later retrieval can confirm assimilation.", ())
    fact = owner_fact(event)
    if fact is not None:
        if owner_observation(event, state) is None:
            return ("The assertion was not applied. A correction requires an existing current assertion; "
                    "changing an existing value requires an explicit Correction: message.", ())
        return ("Your owner-supplied assertion is queued for relational retention with its provenance. "
                "It is not independently verified world truth.", ())
    query = _QUERY.fullmatch(event.payload.text.strip())
    if query:
        subject = fact_subject(query.groupdict())
        current = next((m for m in state.memory.active_at(event.occurred_at_utc) if m.subject == subject), None)
        if current is None:
            return ("I have no current retained owner assertion for that subject and property.", ())
        data = _content(current)
        text = (f"{data['subject']}'s {data['property']} is {data['value']} (CURRENT). "
                f"Provenance: {data['provenance']}; owner event {data['owner_event_id']}; "
                f"recorded {current.recorded_at_utc.isoformat()}. This is owner-supplied information.")
        prior_id = current.supersedes_memory_id
        prior = next((m for m in state.memory.records if m.memory_id == prior_id), None)
        if prior is not None:
            old = _content(prior)
            text += (f" Previous value {old.get('value')} is SUPERSEDED and preserved as {prior.memory_id}. "
                     f"The owner supplied the correction; {current.memory_id} supersedes {prior.memory_id}.")
        return text, current.source_event_ids[:8]
    match = re.fullmatch(rf"What do you retain about candidate ({_ID})\?", event.payload.text.strip())
    if match:
        current = next((m for m in state.memory.active_at(event.occurred_at_utc)
                        if m.subject == "provider-candidate:" + match[1]), None)
        if current is None:
            return "That candidate has not entered my retained Entity memory.", ()
        data = _content(current)
        verification = next((m for m in state.memory.active_at(event.occurred_at_utc)
                             if m.subject == "verification:" + current.source_event_ids[0]), None)
        text = (f"Candidate {data['candidate_id']} is retained as HYPOTHESIS with MODEL_OUTPUT provenance, "
                f"original hash {data['candidate_hash']}. "
                + "; ".join(f"{r['subject']} {r['predicate']} {r['object']}: {r['result']} "
                            f"within {data['scope']}" for r in data["claim_reviews"])
                + ". Physical identity and other inferred claims remain uncertain. "
                + (f"Retention/source verification: {verification.memory_id}." if verification
                   else "Retention/source verification is pending."))
        return text, current.source_event_ids[:8]
    return None


def source_assertion_result(left: str, predicate: str, right: str, sources, now: datetime) -> str:
    """An exact document assertion check; no general semantic/world verifier."""
    outcomes = set()
    for source in sources:
        if source.valid_until_utc is not None and now >= source.valid_until_utc:
            continue
        if predicate == "SAME_REFERENT":
            for a, b in ((left, right), (right, left)):
                if source.original == f"{a} denotes {b} in this synthetic glossary.":
                    outcomes.add("SUPPORTED_SOURCE_ASSERTION")
                if source.original == f"{a} does not denote {b} in this synthetic glossary.":
                    outcomes.add("CONTRADICTED_BY_SOURCE")
    return ("CONFLICTING_SOURCE_ASSERTIONS" if len(outcomes) > 1 else
            next(iter(outcomes)) if outcomes else "UNSUPPORTED_HYPOTHESIS")


def retained_provider_verification(*, candidate_record, receipt_record, bundle, state, history, now: datetime) -> VerificationPayload:
    """Prove only exact relationships in the server-owned synthetic glossary.

    Validate model/receipt provenance, but neither is semantic support. Support
    must equal the independently held, fixed local input and pass deterministic
    source comparison. No browser-supplied source, result or trust bit is used.
    """
    from .openai_responses_executor import _package
    from .relational_response import RelationalCandidate

    draft = retained_provider_draft(candidate_record=candidate_record,
        receipt_record=receipt_record, bundle=bundle, state=state, now=now)
    if not isinstance(draft.payload, ObservationPayload):
        raise ValueError("VERIFICATION_CANDIDATE_NOT_RETAINED")
    saved = json.loads(bundle.transaction.arguments["body"]["input"].rsplit("\nSynthetic input:\n", 1)[1])
    trusted = _package()  # Pure local data; no credentials, preparation or model call.
    data = json.loads(draft.payload.value_summary)
    if (saved["scope"] != trusted["scope"]
            or saved["source_observations"] != trusted["source_observations"]
            or any(s["reference"]["source_kind"] != "SYSTEM_OBSERVATION"
                   for s in saved["source_observations"])
            or not data["claim_reviews"]
            or any(r["result"] != "SUPPORTED_SOURCE_ASSERTION" for r in data["claim_reviews"])):
        raise ValueError("VERIFICATION_INDEPENDENT_SUPPORT_MISSING")
    subject = next((e for e in history if e.correlation_id == candidate_record.memory_id
                    and e.relation == PROVIDER_RELATION and e.payload == draft.payload
                    and e.source == draft.source and e.provenance == draft.provenance), None)
    if subject is None:
        raise ValueError("VERIFICATION_CANDIDATE_NOT_RETAINED")
    claims = "; ".join(f"{r['subject']} {r['predicate']} {r['object']}" for r in data["claim_reviews"])
    candidate = RelationalCandidate.model_validate_json(candidate_record.content_summary)
    source_evidence = tuple(dict.fromkeys((
        candidate_record.memory_id,
        receipt_record.memory_id,
        *candidate.evidence_references,
        *(ref for relation in candidate.relationships for ref in relation.source_references),
    )))
    if not source_evidence:
        raise ValueError("VERIFICATION_INDEPENDENT_SUPPORT_MISSING")
    summary = (f"Verified synthetic glossary relationship within track-b-synthetic ONLY: {claims}. "
               "The original model candidate remains HYPOTHESIS. This proves no physical or real-world identity.")
    return VerificationPayload(subject_event_id=subject.event_id,
        result=VerificationResult.PASSED, independently_verified=True,
        evidence_references=source_evidence, summary=summary)


def retained_provider_draft(*, candidate_record, receipt_record, bundle, state, now: datetime):
    """Validate existing records and compare exact saved source assertions.

    Expired *call authority* is deliberately not renewed: this consumes already
    retained evidence, makes no provider call and grants no new capability.
    """
    from .approval_contracts import ApprovalStatus
    from .entity_cognition import DurableMemoryRecord, EvidenceSourceKind, MemoryStatus
    from .relational_response import RelationalCandidate, SourceObservation, validate_candidate

    def require(condition):
        if not condition:
            raise ValueError("RETAINED_PROVIDER_EVIDENCE_INVALID")

    candidate_record = DurableMemoryRecord.model_validate_json(candidate_record.model_dump_json())
    receipt_record = DurableMemoryRecord.model_validate_json(receipt_record.model_dump_json())
    tx, approval = bundle.transaction, bundle.approval
    require(candidate_record.entity_id == receipt_record.entity_id == tx.actor_identity == state.identity.instance_id)
    require(candidate_record.identity_state_id == receipt_record.identity_state_id == state.identity.identity_state_id)
    require(tx.arguments["identity_state_id"] == state.identity.identity_state_id)
    require(candidate_record.status is MemoryStatus.HYPOTHESIS)
    require(candidate_record.recorded_at_utc <= receipt_record.recorded_at_utc <= now)
    require(approval.approval_status is ApprovalStatus.CONSUMED and approval.current_uses == approval.maximum_uses == 1)
    require(candidate_record.subject == "relational:track-b:" + approval.approval_id)
    require(receipt_record.subject == "provider-receipt:" + approval.approval_id)
    raw_candidate = json.loads(candidate_record.content_summary)
    digest = canonical_sha256(raw_candidate)
    require(any(p.source_kind is EvidenceSourceKind.MODEL_OUTPUT and p.source_id == approval.approval_id
                and p.content_hash == digest for p in candidate_record.provenance))
    receipt = json.loads(receipt_record.content_summary)
    require(any(p.source_kind is EvidenceSourceKind.EXECUTION_RECEIPT and p.source_id == approval.approval_id
                and p.content_hash == canonical_sha256(receipt) for p in receipt_record.provenance))
    diagnostic = receipt["provider_diagnostics"]
    require(receipt["status"] == ExecutionStatus.SUCCEEDED.value and diagnostic["http_status"] == 200
            and diagnostic["candidate_status"] == "RETAINED" and diagnostic["candidate_hash"] == digest)
    body = tx.arguments["body"]
    require(hashlib.sha256(_json(body).encode("utf-8")).hexdigest()
            == tx.content_hash == tx.arguments["body_hash"] == diagnostic["request_hash"])
    require(receipt["transaction_hash"] == tx.material_transaction_hash)
    package = json.loads(body["input"].rsplit("\nSynthetic input:\n", 1)[1])
    require(package["scope"] == "track-b-synthetic" and not package["retained_context"])
    candidate = RelationalCandidate.model_validate_json(candidate_record.content_summary)
    validate_candidate(candidate, package)
    sources = {}
    for entry in package["source_observations"]:
        source = SourceObservation.model_validate_json(_json({k: v for k, v in entry.items() if k != "current"}))
        source.check(source.reference.entity_id, package["scope"], now)
        sources[source.reference.evidence_id] = source
    representations = {r.key: r for r in candidate.representations}
    nodes = {n.key: representations[n.representation_keys[0]].original for n in candidate.candidate_entities}
    reviews = []
    for index, relation in enumerate(candidate.relationships):
        left, right = nodes[relation.subject], nodes[relation.object]
        result = source_assertion_result(left, relation.predicate, right,
            (sources[ref] for ref in relation.source_references), now)
        reviews.append({"index": index, "subject": left, "predicate": relation.predicate,
                        "object": right, "result": result})
    data = {"kind": "provider_candidate", "candidate_id": candidate_record.memory_id,
            "candidate_hash": digest, "receipt_id": receipt_record.memory_id,
            "original_recorded_at": candidate_record.recorded_at_utc.isoformat(),
            "confidence_basis_points": candidate_record.confidence_basis_points,
            "classification": "HYPOTHESIS", "provenance": "MODEL_OUTPUT",
            "scope": package["scope"], "claim_reviews": reviews}
    content = _json(data)
    require(len(content) <= 2000)
    references = tuple(dict.fromkeys((
        candidate_record.memory_id,
        receipt_record.memory_id,
        *candidate.evidence_references,
        *(ref for r in candidate.relationships for ref in r.source_references),
    )))
    require(len(references) <= 30)
    return EntityEventDraft(
        event_type=EventType.OBSERVATION, occurred_at_utc=now, originating_loop=LoopName.EXTERNAL,
        source=EventEndpoint(kind=EventSourceKind.COMPONENT, identifier="retained-provider-review"),
        target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
        relation=PROVIDER_RELATION, provenance=ObservationProvenance.MODEL_INFERRED,
        epistemic_status=EpistemicStatus.MODEL_PROPOSED, authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id=candidate_record.memory_id, sensitivity=SensitivityClassification.INTERNAL,
        persistence_policy=PersistencePolicy.DURABLE_AUDIT,
        payload=ObservationPayload(world_node="provider-candidate:" + candidate_record.memory_id,
            relation=PROVIDER_RELATION, value_summary=content,
            provenance=ObservationProvenance.MODEL_INFERRED, observed_at_utc=now,
            evidence_references=references, confidence_basis_points=candidate_record.confidence_basis_points))
