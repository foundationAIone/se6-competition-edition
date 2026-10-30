"""Deterministic, effect-free integration of the Symbolic Equation V6 organs.

This module is a SHADOW proof harness, not a production runtime.  It composes
the frame, Universal Mapper, QPRE, Merkabah and existing pure Master Boundary
contracts around one deterministic fixture.  Its "environment" and
"verification" are explicitly fixture-scoped values: no adapter, process,
network, file, database, model, credential, approval or production authority is
used.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

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
from .epistemic_status import EpistemicStatus
from .master_boundary import evaluate_boundary
from .merkabah_traversal import (
    MerkabahTraversal,
    TraversalReference,
    TraversalReferenceKind,
    build_traversal_center,
    build_traversal_terminal,
    build_verified_consequence_assimilation,
    traverse_merkabah,
)
from .qpre import (
    CandidateStateField,
    QPRECandidate,
    QPRERender,
    Reversibility,
    StructuredUncertainty,
    TransformationStep,
    build_candidate_realization,
    build_possibility_field,
    build_predicted_consequence,
    build_qpre_candidate,
    render_qpre,
)
from .realization_frame import (
    RealizationFrame,
    RealizationState,
    advance_realization_state,
    create_realization_frame,
    create_realization_state,
    create_source_observation,
)
from .universal_mapper import (
    InversionKind,
    NodeKind,
    PeriodicGrounding,
    RelationKind,
    UniversalMap,
    create_flower_center,
    create_inversion_assessment,
    create_mapper_hyperedge,
    create_mapper_node,
    create_mapper_relation,
    create_periodic_dimension,
    create_periodic_terminal,
    create_perspective_view,
    create_reality_object,
    create_scale,
    create_universal_map,
    extract_common_denominator,
    recenter_flower,
)

SHADOW_REALIZATION_SCHEMA_VERSION = "se6-symbolic-realization-v6-shadow-1"
_HASH_PATTERN = r"^[0-9a-f]{64}$"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"


class _ShadowProof(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    def material_fields(self) -> dict[str, Any]:
        """Return the exact material bound by a concrete shadow proof ID."""

        raise NotImplementedError


class CandidateEvaluation(_ShadowProof):
    evaluation_id: StrictStr
    candidate_id: StrictStr
    benefit_units: StrictInt = Field(ge=0)
    cost_units: StrictInt = Field(ge=0)
    risk_units: StrictInt = Field(ge=0)
    irreversibility_units: StrictInt = Field(ge=0)
    uncertainty_units: StrictInt = Field(ge=0)
    net_score: StrictInt
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_evaluation(self) -> CandidateEvaluation:
        expected_score = (
            self.benefit_units
            - self.cost_units
            - self.risk_units
            - self.irreversibility_units
            - self.uncertainty_units
        )
        if self.net_score != expected_score:
            raise ValueError("candidate net score does not match fixed arithmetic")
        if self.evaluation_id != _content_id("shadow_evaluation", self.material_fields()):
            raise ValueError("evaluation_id must derive from evaluation material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"evaluation_id"})


class ShadowSelection(_ShadowProof):
    selection_id: StrictStr
    possibility_field_id: StrictStr
    evaluations: tuple[CandidateEvaluation, ...] = Field(min_length=2, max_length=64)
    selected_candidate_id: StrictStr
    arithmetic: Literal[
        "benefit-cost-risk-irreversibility-uncertainty"
    ] = "benefit-cost-risk-irreversibility-uncertainty"
    tie_break: Literal[
        "irreversibility,risk,cost,candidate_id"
    ] = "irreversibility,risk,cost,candidate_id"
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_selection(self) -> ShadowSelection:
        candidate_ids = tuple(item.candidate_id for item in self.evaluations)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("selection evaluations must be unique")
        maximum = max(item.net_score for item in self.evaluations)
        tied = [item for item in self.evaluations if item.net_score == maximum]
        expected = min(
            tied,
            key=lambda item: (
                item.irreversibility_units,
                item.risk_units,
                item.cost_units,
                item.candidate_id,
            ),
        ).candidate_id
        if self.selected_candidate_id != expected:
            raise ValueError("selected candidate violates deterministic ranking")
        if self.selection_id != _content_id("shadow_selection", self.material_fields()):
            raise ValueError("selection_id must derive from selection material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"selection_id"})


class ShadowBoundarySnapshot(_ShadowProof):
    boundary_id: StrictStr
    decision: Literal["allow"] = "allow"
    reasons: tuple[StrictStr, ...] = Field(min_length=1)
    simulation_scope: Literal["DETERMINISTIC_SHADOW_FIXTURE"] = (
        "DETERMINISTIC_SHADOW_FIXTURE"
    )
    real_authority_granted: Literal[False] = False
    production_effect_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_boundary(self) -> ShadowBoundarySnapshot:
        if self.boundary_id != _content_id("shadow_boundary", self.material_fields()):
            raise ValueError("boundary_id must derive from boundary material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"boundary_id"})


class ShadowExpression(_ShadowProof):
    expression_id: StrictStr
    candidate_id: StrictStr
    boundary_id: StrictStr
    expected_value: StrictStr = Field(min_length=1, max_length=1_024)
    mode: Literal["SIMULATED_EXPRESSION"] = "SIMULATED_EXPRESSION"
    real_authority_granted: Literal[False] = False
    production_effect: Literal[False] = False
    io_performed: Literal[False] = False
    network_performed: Literal[False] = False
    model_called: Literal[False] = False

    @model_validator(mode="after")
    def validate_expression(self) -> ShadowExpression:
        if self.expression_id != _content_id("shadow_expression", self.material_fields()):
            raise ValueError("expression_id must derive from expression material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"expression_id"})


class ShadowConsequence(_ShadowProof):
    consequence_id: StrictStr
    expression_id: StrictStr
    observed_value: StrictStr = Field(min_length=1, max_length=1_024)
    environment: Literal["DETERMINISTIC_SHADOW_FIXTURE"] = (
        "DETERMINISTIC_SHADOW_FIXTURE"
    )
    epistemic_scope: Literal["SIMULATED_OBSERVATION"] = "SIMULATED_OBSERVATION"
    production_actuality: Literal[False] = False
    io_performed: Literal[False] = False
    network_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_consequence(self) -> ShadowConsequence:
        if self.consequence_id != _content_id("shadow_consequence", self.material_fields()):
            raise ValueError("consequence_id must derive from consequence material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"consequence_id"})


class ShadowVerification(_ShadowProof):
    verification_id: StrictStr
    consequence_id: StrictStr
    expected_value: StrictStr
    observed_value: StrictStr
    method: Literal["EXACT_FIXTURE_MATCH"] = "EXACT_FIXTURE_MATCH"
    passed: StrictBool
    verification_scope: Literal["DETERMINISTIC_SHADOW_FIXTURE"] = (
        "DETERMINISTIC_SHADOW_FIXTURE"
    )
    production_verified: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_verification(self) -> ShadowVerification:
        if self.passed != (self.expected_value == self.observed_value):
            raise ValueError("verification result must match exact fixture comparison")
        if self.verification_id != _content_id("shadow_verification", self.material_fields()):
            raise ValueError("verification_id must derive from verification material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"verification_id"})


class ShadowAssimilation(_ShadowProof):
    assimilation_id: StrictStr
    verification_id: StrictStr
    consequence_id: StrictStr
    eligible: Literal[True] = True
    scope: Literal["SHADOW_STATE_ONLY"] = "SHADOW_STATE_ONLY"
    durable: Literal[False] = False
    production_state_mutated: Literal[False] = False
    production_identity_advanced: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_assimilation(self) -> ShadowAssimilation:
        if self.assimilation_id != _content_id("shadow_assimilation", self.material_fields()):
            raise ValueError("assimilation_id must derive from assimilation material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"assimilation_id"})


class SymbolicRealizationTrace(_ShadowProof):
    schema_version: Literal["se6-symbolic-realization-v6-shadow-1"] = (
        SHADOW_REALIZATION_SCHEMA_VERSION
    )
    trace_id: StrictStr
    identity_state_id_before: StrictStr = Field(pattern=_ID_PATTERN)
    identity_state_id_after: StrictStr = Field(pattern=_ID_PATTERN)
    x0: RealizationState
    theta0: RealizationFrame
    map0: UniversalMap
    qpre: QPRERender
    selection: ShadowSelection
    selected_candidate: QPRECandidate
    outward_traversal: MerkabahTraversal
    boundary: ShadowBoundarySnapshot
    expression: ShadowExpression
    consequence: ShadowConsequence
    verification: ShadowVerification
    assimilation: ShadowAssimilation
    x1: RealizationState
    theta1: RealizationFrame
    returned_traversal: MerkabahTraversal
    map1: UniversalMap
    shadow_only: Literal[True] = True
    production_authoritative: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"
    io_performed: Literal[False] = False
    network_performed: Literal[False] = False
    model_called: Literal[False] = False

    @model_validator(mode="after")
    def validate_complete_causal_trace(self) -> SymbolicRealizationTrace:
        if self.identity_state_id_after != self.identity_state_id_before:
            raise ValueError("shadow realization cannot advance production identity")
        if self.theta0.x != self.x0:
            raise ValueError("Theta0 must bind exact X0")
        if self.qpre.source_state_hash != self.x0.x_hash:
            raise ValueError("QPRE must bind X0")
        if self.qpre.frame_hash != self.theta0.theta_hash:
            raise ValueError("QPRE must bind Theta0")
        candidates = self.qpre.possibility_field.candidates
        if len(candidates) < 2:
            raise ValueError("complete trace requires multiple possibilities")
        if self.selection.possibility_field_id != self.qpre.possibility_field.possibility_field_id:
            raise ValueError("selection must bind the exact possibility field")
        if {item.candidate_id for item in self.selection.evaluations} != {
            item.candidate_id for item in candidates
        }:
            raise ValueError("selection must evaluate every QPRE candidate exactly once")
        if self.selected_candidate not in candidates:
            raise ValueError("selected candidate must come from QPRE")
        if self.selection.selected_candidate_id != self.selected_candidate.candidate_id:
            raise ValueError("selection and selected candidate disagree")
        if self.selected_candidate.actual or self.selected_candidate.verified:
            raise ValueError("selected possibility cannot become actuality before consequence")
        if self.outward_traversal.state_changed:
            raise ValueError("outward possibility traversal cannot change center")
        if self.outward_traversal.source_center.state_hash != self.x0.x_hash:
            raise ValueError("outward traversal must begin from X0")
        if self.outward_traversal.source_center.frame_hash != self.theta0.theta_hash:
            raise ValueError("outward traversal must begin from Theta0")
        traversal_refs = {
            (item.kind.value, item.reference_id)
            for item in self.outward_traversal.terminal.references
        }
        if ("MAPPED", f"map:{self.map0.map_id}") not in traversal_refs:
            raise ValueError("outward traversal must bind the exact initial map")
        if ("QPRE", f"qpre:{self.selected_candidate.candidate_id}") not in traversal_refs:
            raise ValueError("outward traversal must bind the selected possibility")
        if self.expression.candidate_id != self.selected_candidate.candidate_id:
            raise ValueError("expression must bind selected candidate")
        if self.expression.boundary_id != self.boundary.boundary_id:
            raise ValueError("expression must bind boundary result")
        if self.consequence.expression_id != self.expression.expression_id:
            raise ValueError("consequence must bind expression")
        if self.verification.consequence_id != self.consequence.consequence_id:
            raise ValueError("verification must bind consequence")
        if not self.verification.passed:
            raise ValueError("assimilation trace requires passed fixture verification")
        if self.assimilation.verification_id != self.verification.verification_id:
            raise ValueError("assimilation must bind verification")
        if self.assimilation.consequence_id != self.consequence.consequence_id:
            raise ValueError("assimilation must bind consequence")
        if self.x1.previous_x_id != self.x0.x_id:
            raise ValueError("X1 must lineage-link to X0")
        if self.x1.source_observations[: len(self.x0.source_observations)] != self.x0.source_observations:
            raise ValueError("X1 must preserve X0 observations")
        if self.theta1 != self.theta0:
            raise ValueError("this fixture must preserve Theta without an expansion claim")
        if not self.returned_traversal.state_changed:
            raise ValueError("verified shadow assimilation must return a new center")
        if self.returned_traversal.returned_center.state_hash != self.x1.x_hash:
            raise ValueError("returned center must bind X1")
        if self.returned_traversal.returned_center.frame_hash != self.theta1.theta_hash:
            raise ValueError("returned center must bind Theta1")
        if self.map1.map_id == self.map0.map_id:
            raise ValueError("next recursive map must reflect the returned consequence")
        new_binding = self.x1.source_observations[-1].binding
        if not any(
            new_binding in node.source_observation_bindings
            for node in self.map1.vertices
        ):
            raise ValueError("next recursive map must bind the assimilated observation")
        if self.trace_id != _content_id("symbolic_realization_trace", self.material_fields()):
            raise ValueError("trace_id must derive from complete trace material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"trace_id"})


def _content_id(prefix: str, material: Any) -> str:
    return f"{prefix}_{canonical_sha256(material)}"


def _build(model_type: type[_ShadowProof], id_field: str, prefix: str, material: dict[str, Any]) -> Any:
    draft = model_type.model_construct(**{id_field: f"{prefix}_draft", **material})
    normalized = draft.material_fields()
    return model_type(**{id_field: _content_id(prefix, normalized), **normalized})


def _evaluation(candidate: QPRECandidate, *, benefit: int, uncertainty: int) -> CandidateEvaluation:
    reversibility_units = {
        Reversibility.REVERSIBLE: 0,
        Reversibility.PARTIALLY_REVERSIBLE: 1,
        Reversibility.UNKNOWN: 2,
        Reversibility.IRREVERSIBLE: 3,
    }[candidate.realization.reversibility]
    material = {
        "candidate_id": candidate.candidate_id,
        "benefit_units": benefit,
        "cost_units": candidate.realization.cost_units,
        "risk_units": candidate.realization.risk_score,
        "irreversibility_units": reversibility_units,
        "uncertainty_units": uncertainty,
        "net_score": benefit
        - candidate.realization.cost_units
        - candidate.realization.risk_score
        - reversibility_units
        - uncertainty,
        "shadow_only": True,
        "authority_effect": "NONE",
    }
    return _build(CandidateEvaluation, "evaluation_id", "shadow_evaluation", material)


def _selection(field_id: str, evaluations: Sequence[CandidateEvaluation]) -> ShadowSelection:
    maximum = max(item.net_score for item in evaluations)
    tied = [item for item in evaluations if item.net_score == maximum]
    selected = min(
        tied,
        key=lambda item: (
            item.irreversibility_units,
            item.risk_units,
            item.cost_units,
            item.candidate_id,
        ),
    )
    material = {
        "possibility_field_id": field_id,
        "evaluations": tuple(evaluations),
        "selected_candidate_id": selected.candidate_id,
        "arithmetic": "benefit-cost-risk-irreversibility-uncertainty",
        "tie_break": "irreversibility,risk,cost,candidate_id",
        "shadow_only": True,
        "authority_effect": "NONE",
    }
    return _build(ShadowSelection, "selection_id", "shadow_selection", material)


def run_deterministic_shadow_realization(
    *,
    identity_state_id: str,
    observation_summary: str = "A deterministic fixture reports one bounded change.",
) -> SymbolicRealizationTrace:
    """Run one complete V6 realization in a closed deterministic fixture.

    The result is content addressed but ephemeral.  "ALLOW" below means only
    that the pure compatibility boundary found no prohibited content; every
    expression and consequence is still explicitly simulated and carries no
    production authority.
    """

    observation = create_source_observation(
        source_reference="fixture:symbolic-equation-v6",
        summary=observation_summary,
        epistemic_status=EpistemicStatus.REPORTED,
    )
    x0 = create_realization_state(
        state_summary="Initial shadow state before simulated consequence.",
        source_observations=(observation,),
    )
    theta0 = create_realization_frame(
        x0,
        frame_name="situated-source-frame",
        dimensions=("source", "relation", "epistemic-status"),
        representation_rules=("preserve source provenance",),
    )

    reality = create_reality_object(
        label="source event",
        description="One provenance-linked source reality object.",
        source_observations=(observation,),
    )
    candidate_node = create_mapper_node(
        kind=NodeKind.TERMINAL,
        label="candidate-change",
        description="A symbolic terminal representing bounded change.",
        epistemic_status=EpistemicStatus.SYMBOLIC,
    )
    rest_node = create_mapper_node(
        kind=NodeKind.TERMINAL,
        label="candidate-rest",
        description="A symbolic terminal representing no change.",
        epistemic_status=EpistemicStatus.SYMBOLIC,
    )
    relation = create_mapper_relation(
        kind=RelationKind.RELATES_TO,
        label="source event relates to possible terminals",
        source_nodes=(reality,),
        target_nodes=(candidate_node, rest_node),
        epistemic_status=EpistemicStatus.SYMBOLIC,
    )
    edge = create_mapper_hyperedge(relation)
    periodic = create_periodic_dimension(
        name="possibility-mode",
        property_name="symbolic candidate differentiation",
        terminals=(
            create_periodic_terminal(
                candidate_node,
                label="bounded-change-symbol",
                grounding=PeriodicGrounding.SYMBOLIC,
                epistemic_status=EpistemicStatus.SYMBOLIC,
            ),
            create_periodic_terminal(
                rest_node,
                label="rest-symbol",
                grounding=PeriodicGrounding.SYMBOLIC,
                epistemic_status=EpistemicStatus.SYMBOLIC,
            ),
        ),
    )
    views = tuple(
        create_perspective_view(
            reality,
            perspective_key=key,
            representation=representation,
        )
        for key, representation in (
            ("SE6", "The event in relation to the current bounded SE6 state."),
            ("ProgrammerOne", "The event as an owner-visible proposed change."),
            ("developer", "The event as a deterministic implementation case."),
            ("regulator", "The event as a provenance and authority distinction."),
        )
    )
    invariant = extract_common_denominator(reality, views)
    flower0 = create_flower_center(reality, terminals=(candidate_node, rest_node))
    inversion = create_inversion_assessment(
        reality,
        kind=InversionKind.NO_VALID_INVERSE,
        domain="general event semantics",
        reason="No domain rule justifies a literal inverse of the source event.",
        epistemic_status=EpistemicStatus.DETERMINISTIC,
    )
    scale = create_scale(name="fixture-event", level=0)
    map0 = create_universal_map(
        vertices=(reality, candidate_node, rest_node),
        hyperedges=(edge,),
        relations=(relation,),
        dimensions=(periodic,),
        scales=(scale,),
        perspectives=views,
        flower_lineage=(flower0,),
        invariants=(invariant,),
        inversions=(inversion,),
    )

    map_ref = f"map:{map0.map_id}"
    expected_value = "bounded shadow consequence observed"
    change_prediction = build_predicted_consequence(
        summary=expected_value,
        provenance_references=(map_ref,),
    )
    rest_prediction = build_predicted_consequence(
        summary="no simulated state change",
        provenance_references=(map_ref,),
    )

    def candidate(value: str, prediction: Any, *, cost: int, risk: int) -> QPRECandidate:
        realization = build_candidate_realization(
            source_state_hash=x0.x_hash,
            frame_hash=theta0.theta_hash,
            candidate_state=(CandidateStateField(name="fixture_state", possible_value=value),),
            transformations=(
                TransformationStep(
                    operation="shadow_fixture_transition",
                    input_reference=map_ref,
                    possible_output=value,
                ),
            ),
            predicted_consequences=(prediction,),
            reversibility=Reversibility.REVERSIBLE,
            cost_units=cost,
            risk_score=risk,
            provenance_references=(map_ref,),
        )
        uncertainty = StructuredUncertainty(
            known=("The source state, frame and mapper hashes are fixed.",),
            unknown=("No consequence exists before the fixture expression.",),
            assumptions=("The closed deterministic fixture remains unchanged.",),
            sensitivity_factors=("A changed fixture invalidates this render.",),
        )
        return build_qpre_candidate(
            source_state_hash=x0.x_hash,
            frame_hash=theta0.theta_hash,
            assumptions=uncertainty.assumptions,
            uncertainty=uncertainty,
            realization=realization,
            provenance_references=(map_ref,),
        )

    change_candidate = candidate("bounded-change", change_prediction, cost=1, risk=1)
    rest_candidate = candidate("rest", rest_prediction, cost=0, risk=0)
    field = build_possibility_field(
        source_state_hash=x0.x_hash,
        frame_hash=theta0.theta_hash,
        candidates=(change_candidate, rest_candidate),
    )
    qpre = render_qpre(field)
    selection = _selection(
        field.possibility_field_id,
        (
            _evaluation(change_candidate, benefit=12, uncertainty=1),
            _evaluation(rest_candidate, benefit=2, uncertainty=0),
        ),
    )
    selected = next(
        item for item in field.candidates if item.candidate_id == selection.selected_candidate_id
    )

    center0 = build_traversal_center(state_hash=x0.x_hash, frame_hash=theta0.theta_hash)
    terminal = build_traversal_terminal(
        source_center_id=center0.center_id,
        references=(
            TraversalReference(kind=TraversalReferenceKind.MAPPED, reference_id=map_ref),
            TraversalReference(
                kind=TraversalReferenceKind.QPRE,
                reference_id=f"qpre:{selected.candidate_id}",
            ),
        ),
        summary="Selected mapped possibility; no actuality is implied.",
    )
    outward = traverse_merkabah(center=center0, terminal=terminal)

    raw_boundary = evaluate_boundary(
        "Run one closed deterministic shadow fixture with no network, file, process, or production effect."
    )
    if raw_boundary.decision != "allow":
        raise ValueError("deterministic shadow fixture did not pass the pure boundary")
    boundary = _build(
        ShadowBoundarySnapshot,
        "boundary_id",
        "shadow_boundary",
        {
            "decision": "allow",
            "reasons": tuple(raw_boundary.reasons),
            "simulation_scope": "DETERMINISTIC_SHADOW_FIXTURE",
            "real_authority_granted": False,
            "production_effect_allowed": False,
        },
    )
    expression = _build(
        ShadowExpression,
        "expression_id",
        "shadow_expression",
        {
            "candidate_id": selected.candidate_id,
            "boundary_id": boundary.boundary_id,
            "expected_value": expected_value,
            "mode": "SIMULATED_EXPRESSION",
            "real_authority_granted": False,
            "production_effect": False,
            "io_performed": False,
            "network_performed": False,
            "model_called": False,
        },
    )
    consequence = _build(
        ShadowConsequence,
        "consequence_id",
        "shadow_consequence",
        {
            "expression_id": expression.expression_id,
            "observed_value": expected_value,
            "environment": "DETERMINISTIC_SHADOW_FIXTURE",
            "epistemic_scope": "SIMULATED_OBSERVATION",
            "production_actuality": False,
            "io_performed": False,
            "network_performed": False,
        },
    )
    verification = _build(
        ShadowVerification,
        "verification_id",
        "shadow_verification",
        {
            "consequence_id": consequence.consequence_id,
            "expected_value": expression.expected_value,
            "observed_value": consequence.observed_value,
            "method": "EXACT_FIXTURE_MATCH",
            "passed": expression.expected_value == consequence.observed_value,
            "verification_scope": "DETERMINISTIC_SHADOW_FIXTURE",
            "production_verified": False,
            "authority_effect": "NONE",
        },
    )
    assimilation = _build(
        ShadowAssimilation,
        "assimilation_id",
        "shadow_assimilation",
        {
            "verification_id": verification.verification_id,
            "consequence_id": consequence.consequence_id,
            "eligible": True,
            "scope": "SHADOW_STATE_ONLY",
            "durable": False,
            "production_state_mutated": False,
            "production_identity_advanced": False,
            "authority_effect": "NONE",
        },
    )

    consequence_observation = create_source_observation(
        source_reference="shadow_fixture:consequence",
        summary=consequence.observed_value,
        epistemic_status=EpistemicStatus.VERIFIED,
        evidence_references=(f"shadow:{verification.verification_id}",),
    )
    x1 = advance_realization_state(
        x0,
        state_summary="Next shadow state after fixture-scoped verified consequence.",
        additional_observations=(consequence_observation,),
    )
    theta1 = theta0
    verified_reference = build_verified_consequence_assimilation(
        source_center_id=center0.center_id,
        consequence_reference=f"shadow:{consequence.consequence_id}",
        verification_reference=f"shadow:{verification.verification_id}",
        assimilation_reference=f"shadow:{assimilation.assimilation_id}",
        next_state_hash=x1.x_hash,
        next_frame_hash=theta1.theta_hash,
    )
    returned = traverse_merkabah(
        center=center0,
        terminal=terminal,
        verified_assimilation=verified_reference,
    )

    consequence_reality = create_reality_object(
        label="fixture consequence",
        description="The fixture-scoped consequence linked to exact verification.",
        source_observations=(consequence_observation,),
    )
    consequence_relation = create_mapper_relation(
        kind=RelationKind.RELATES_TO,
        label="selected terminal relates to verified fixture consequence",
        source_nodes=(candidate_node,),
        target_nodes=(consequence_reality,),
        epistemic_status=EpistemicStatus.VERIFIED,
        source_observations=(consequence_observation,),
    )
    consequence_edge = create_mapper_hyperedge(consequence_relation)
    consequence_dimension = create_periodic_dimension(
        name="fixture-consequence-grounding",
        property_name="symbolic representation of fixture-scoped verification",
        terminals=(
            create_periodic_terminal(
                consequence_reality,
                label="fixture-verified-symbolic-consequence",
                grounding=PeriodicGrounding.SYMBOLIC,
                epistemic_status=EpistemicStatus.SYMBOLIC,
            ),
        ),
    )
    flower1 = recenter_flower(
        flower0,
        candidate_node,
        terminals=(reality, consequence_reality),
    )
    map1 = create_universal_map(
        vertices=(reality, candidate_node, rest_node, consequence_reality),
        hyperedges=(edge, consequence_edge),
        relations=(relation, consequence_relation),
        dimensions=(periodic, consequence_dimension),
        scales=(scale,),
        perspectives=views,
        flower_lineage=(flower0, flower1),
        invariants=(invariant,),
        inversions=(inversion,),
    )

    material = {
        "schema_version": SHADOW_REALIZATION_SCHEMA_VERSION,
        "identity_state_id_before": identity_state_id,
        "identity_state_id_after": identity_state_id,
        "x0": x0,
        "theta0": theta0,
        "map0": map0,
        "qpre": qpre,
        "selection": selection,
        "selected_candidate": selected,
        "outward_traversal": outward,
        "boundary": boundary,
        "expression": expression,
        "consequence": consequence,
        "verification": verification,
        "assimilation": assimilation,
        "x1": x1,
        "theta1": theta1,
        "returned_traversal": returned,
        "map1": map1,
        "shadow_only": True,
        "production_authoritative": False,
        "authority_effect": "NONE",
        "io_performed": False,
        "network_performed": False,
        "model_called": False,
    }
    return _build(
        SymbolicRealizationTrace,
        "trace_id",
        "symbolic_realization_trace",
        material,
    )


__all__ = [
    "SHADOW_REALIZATION_SCHEMA_VERSION",
    "CandidateEvaluation",
    "ShadowAssimilation",
    "ShadowBoundarySnapshot",
    "ShadowConsequence",
    "ShadowExpression",
    "ShadowSelection",
    "ShadowVerification",
    "SymbolicRealizationTrace",
    "run_deterministic_shadow_realization",
]
