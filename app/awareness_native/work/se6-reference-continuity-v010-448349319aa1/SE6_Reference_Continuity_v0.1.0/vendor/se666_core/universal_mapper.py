"""Pure, finite, content-addressed Universal Mapper shadow contracts.

The canonical graph projection is ``G = (V, E, R, D, S, P)``:

``V`` vertices, ``E`` typed hyperedges, ``R`` relations, ``D`` periodic
dimensions/terminals, ``S`` scales, and ``P`` perspective views. Recursive
Flower recentering, provenance invariants, and explicit inversion assessments
are hash-bound derived records over that finite graph.

These contracts do not infer physical facts, manufacture inverses, execute an
action, call a model, access a network, read or write files, persist state,
grant authority, or mutate production.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)

from .canonical_contracts import canonical_sha256
from .epistemic_status import EpistemicStatus
from .realization_frame import ObservationBinding, SourceObservation

MAPPER_SCHEMA_VERSION = "se6-universal-mapper-v1-shadow"
_HASH_PATTERN = r"^[0-9a-f]{64}$"
_NODE_ID_PATTERN = r"^mapper_node_[0-9a-f]{64}$"
_RELATION_ID_PATTERN = r"^mapper_relation_[0-9a-f]{64}$"
_EDGE_ID_PATTERN = r"^mapper_edge_[0-9a-f]{64}$"
_TERMINAL_ID_PATTERN = r"^periodic_terminal_[0-9a-f]{64}$"
_DIMENSION_ID_PATTERN = r"^periodic_dimension_[0-9a-f]{64}$"
_SCALE_ID_PATTERN = r"^mapper_scale_[0-9a-f]{64}$"
_PERSPECTIVE_ID_PATTERN = r"^perspective_[0-9a-f]{64}$"
_INVARIANT_ID_PATTERN = r"^perspective_invariant_[0-9a-f]{64}$"
_INVERSION_ID_PATTERN = r"^inversion_[0-9a-f]{64}$"
_FLOWER_ID_PATTERN = r"^flower_center_[0-9a-f]{64}$"
_MAP_ID_PATTERN = r"^universal_map_[0-9a-f]{64}$"


class NodeKind(str, Enum):
    THING = "THING"
    EVENT = "EVENT"
    STATE = "STATE"
    CENTER = "CENTER"
    TERMINAL = "TERMINAL"
    REALITY_OBJECT = "REALITY_OBJECT"
    SYNTHESIS = "SYNTHESIS"


class RelationKind(str, Enum):
    RELATES_TO = "RELATES_TO"
    CONTAINS = "CONTAINS"
    DEPENDS_ON = "DEPENDS_ON"
    TERMINAL_OF = "TERMINAL_OF"
    RECENTERED_FROM = "RECENTERED_FROM"
    PERSPECTIVE_OF = "PERSPECTIVE_OF"
    CONTRADICTS = "CONTRADICTS"
    INVARIANT_OF = "INVARIANT_OF"
    SYNTHESIZES = "SYNTHESIZES"
    INTERSECTS = "INTERSECTS"
    OVERLAPS = "OVERLAPS"
    DISTINCT_FROM = "DISTINCT_FROM"


class PeriodicGrounding(str, Enum):
    SYMBOLIC = "SYMBOLIC"
    PHYSICAL_OBSERVATION = "PHYSICAL_OBSERVATION"


class InversionKind(str, Enum):
    DUAL = "DUAL"
    COMPLEMENT = "COMPLEMENT"
    RECIPROCAL = "RECIPROCAL"
    REVERSE = "REVERSE"
    MIRROR = "MIRROR"
    NO_VALID_INVERSE = "NO_VALID_INVERSE"
    UNKNOWN = "UNKNOWN"


class _ShadowContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class NodeReference(_ShadowContract):
    node_id: StrictStr = Field(pattern=_NODE_ID_PATTERN)
    node_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def id_and_hash_match(self) -> NodeReference:
        if self.node_id != f"mapper_node_{self.node_hash}":
            raise ValueError("node reference id/hash mismatch")
        return self


class RelationReference(_ShadowContract):
    relation_id: StrictStr = Field(pattern=_RELATION_ID_PATTERN)
    relation_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def id_and_hash_match(self) -> RelationReference:
        if self.relation_id != f"mapper_relation_{self.relation_hash}":
            raise ValueError("relation reference id/hash mismatch")
        return self


class PerspectiveReference(_ShadowContract):
    perspective_id: StrictStr = Field(pattern=_PERSPECTIVE_ID_PATTERN)
    perspective_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def id_and_hash_match(self) -> PerspectiveReference:
        if self.perspective_id != f"perspective_{self.perspective_hash}":
            raise ValueError("perspective reference id/hash mismatch")
        return self


class MapperNode(_ShadowContract):
    node_id: StrictStr = Field(pattern=_NODE_ID_PATTERN)
    node_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    kind: NodeKind
    label: StrictStr = Field(min_length=1, max_length=256)
    description: StrictStr = Field(min_length=1, max_length=4_000)
    epistemic_status: EpistemicStatus
    source_observation_bindings: tuple[ObservationBinding, ...] = Field(
        default=(), max_length=256
    )
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def node_is_content_addressed(self) -> MapperNode:
        _unique_bindings(self.source_observation_bindings, "node observations")
        if self.kind is NodeKind.REALITY_OBJECT and not self.source_observation_bindings:
            raise ValueError("reality object requires source observation bindings")
        if self.epistemic_status in {
            EpistemicStatus.MEASURED,
            EpistemicStatus.VERIFIED,
        } and not self.source_observation_bindings:
            raise ValueError("measured or verified node requires source observations")
        _validate_hash_bound(self, "node_id", "node_hash", "mapper_node_")
        return self

    @property
    def reference(self) -> NodeReference:
        return NodeReference(node_id=self.node_id, node_hash=self.node_hash)

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"node_id", "node_hash"})


class MapperRelation(_ShadowContract):
    relation_id: StrictStr = Field(pattern=_RELATION_ID_PATTERN)
    relation_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    kind: RelationKind
    label: StrictStr = Field(min_length=1, max_length=256)
    source_nodes: tuple[NodeReference, ...] = Field(min_length=1, max_length=64)
    target_nodes: tuple[NodeReference, ...] = Field(min_length=1, max_length=64)
    epistemic_status: EpistemicStatus
    source_observation_bindings: tuple[ObservationBinding, ...] = Field(
        default=(), max_length=256
    )
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def relation_is_content_addressed(self) -> MapperRelation:
        _unique_refs(self.source_nodes, "source nodes")
        _unique_refs(self.target_nodes, "target nodes")
        _unique_bindings(self.source_observation_bindings, "relation observations")
        if self.epistemic_status in {
            EpistemicStatus.MEASURED,
            EpistemicStatus.VERIFIED,
        } and not self.source_observation_bindings:
            raise ValueError("measured or verified relation requires observations")
        _validate_hash_bound(
            self, "relation_id", "relation_hash", "mapper_relation_"
        )
        return self

    @property
    def reference(self) -> RelationReference:
        return RelationReference(
            relation_id=self.relation_id, relation_hash=self.relation_hash
        )

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"relation_id", "relation_hash"}
        )


class MapperHyperedge(_ShadowContract):
    edge_id: StrictStr = Field(pattern=_EDGE_ID_PATTERN)
    edge_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    relation: RelationReference
    endpoint_nodes: tuple[NodeReference, ...] = Field(min_length=2, max_length=128)
    directed: bool
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def edge_is_content_addressed(self) -> MapperHyperedge:
        _unique_refs(self.endpoint_nodes, "hyperedge endpoints")
        _validate_hash_bound(self, "edge_id", "edge_hash", "mapper_edge_")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"edge_id", "edge_hash"})


class PeriodicTerminal(_ShadowContract):
    """One typed terminal in a general dimensional classifier."""

    terminal_id: StrictStr = Field(pattern=_TERMINAL_ID_PATTERN)
    terminal_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    node: NodeReference
    label: StrictStr = Field(min_length=1, max_length=256)
    grounding: PeriodicGrounding
    epistemic_status: EpistemicStatus
    source_observation_bindings: tuple[ObservationBinding, ...] = Field(
        default=(), max_length=256
    )
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def terminal_separates_symbolic_and_physical(self) -> PeriodicTerminal:
        _unique_bindings(self.source_observation_bindings, "terminal observations")
        if self.grounding is PeriodicGrounding.SYMBOLIC:
            if self.epistemic_status is not EpistemicStatus.SYMBOLIC:
                raise ValueError("symbolic terminal requires SYMBOLIC epistemic status")
            if self.source_observation_bindings:
                raise ValueError("symbolic terminal cannot claim physical observations")
        else:
            if self.epistemic_status not in {
                EpistemicStatus.MEASURED,
                EpistemicStatus.VERIFIED,
            }:
                raise ValueError(
                    "physical-observation terminal requires MEASURED or VERIFIED status"
                )
            if not self.source_observation_bindings:
                raise ValueError("physical-observation terminal requires observations")
        _validate_hash_bound(
            self, "terminal_id", "terminal_hash", "periodic_terminal_"
        )
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"terminal_id", "terminal_hash"}
        )


class PeriodicDimension(_ShadowContract):
    dimension_id: StrictStr = Field(pattern=_DIMENSION_ID_PATTERN)
    dimension_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    name: StrictStr = Field(min_length=1, max_length=256)
    property_name: StrictStr = Field(min_length=1, max_length=256)
    terminals: tuple[PeriodicTerminal, ...] = Field(min_length=1, max_length=256)
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def dimension_is_content_addressed(self) -> PeriodicDimension:
        ids = tuple(item.terminal_id for item in self.terminals)
        if len(ids) != len(set(ids)):
            raise ValueError("periodic terminals must be unique")
        _validate_hash_bound(
            self, "dimension_id", "dimension_hash", "periodic_dimension_"
        )
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"dimension_id", "dimension_hash"}
        )


class ScaleDescriptor(_ShadowContract):
    scale_id: StrictStr = Field(pattern=_SCALE_ID_PATTERN)
    scale_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    name: StrictStr = Field(min_length=1, max_length=256)
    level: StrictInt = Field(ge=0, le=1_000)
    parent_scale_id: StrictStr | None = Field(default=None, pattern=_SCALE_ID_PATTERN)
    parent_scale_hash: StrictStr | None = Field(default=None, pattern=_HASH_PATTERN)
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def scale_is_content_addressed(self) -> ScaleDescriptor:
        if (self.parent_scale_id is None) != (self.parent_scale_hash is None):
            raise ValueError("parent scale id and hash must appear together")
        if self.parent_scale_id is not None:
            if self.parent_scale_id != f"mapper_scale_{self.parent_scale_hash}":
                raise ValueError("parent scale id/hash mismatch")
            if self.parent_scale_id == self.scale_id:
                raise ValueError("scale cannot be its own parent")
        _validate_hash_bound(self, "scale_id", "scale_hash", "mapper_scale_")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"scale_id", "scale_hash"})


class PerspectiveView(_ShadowContract):
    """A general ``M(X|p)`` view linked to one source reality object."""

    perspective_id: StrictStr = Field(pattern=_PERSPECTIVE_ID_PATTERN)
    perspective_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    transformation: Literal["M(X|p)"] = "M(X|p)"
    source_reality_object: NodeReference
    perspective_key: StrictStr = Field(min_length=1, max_length=256)
    representation: StrictStr = Field(min_length=1, max_length=4_000)
    epistemic_status: EpistemicStatus
    source_observation_bindings: tuple[ObservationBinding, ...] = Field(
        min_length=1, max_length=256
    )
    is_source_reality: Literal[False] = False
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def perspective_is_not_reality(self) -> PerspectiveView:
        _unique_bindings(self.source_observation_bindings, "perspective observations")
        if self.epistemic_status in {
            EpistemicStatus.MEASURED,
            EpistemicStatus.VERIFIED,
        }:
            raise ValueError("a perspective representation is not measured or verified reality")
        _validate_hash_bound(
            self, "perspective_id", "perspective_hash", "perspective_"
        )
        return self

    @property
    def reference(self) -> PerspectiveReference:
        return PerspectiveReference(
            perspective_id=self.perspective_id,
            perspective_hash=self.perspective_hash,
        )

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"perspective_id", "perspective_hash"}
        )


class PerspectiveInvariant(_ShadowContract):
    """The exact source-reality provenance shared by multiple perspectives."""

    invariant_id: StrictStr = Field(pattern=_INVARIANT_ID_PATTERN)
    invariant_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    invariant_kind: Literal["SOURCE_REALITY_COMMON_DENOMINATOR"] = (
        "SOURCE_REALITY_COMMON_DENOMINATOR"
    )
    source_reality_object: NodeReference
    perspectives: tuple[PerspectiveReference, ...] = Field(
        min_length=2, max_length=256
    )
    common_observation_bindings: tuple[ObservationBinding, ...] = Field(
        min_length=1, max_length=256
    )
    description: StrictStr = Field(min_length=1, max_length=1_000)
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def invariant_is_content_addressed(self) -> PerspectiveInvariant:
        ids = tuple(item.perspective_id for item in self.perspectives)
        if len(ids) != len(set(ids)):
            raise ValueError("invariant perspectives must be unique")
        _unique_bindings(
            self.common_observation_bindings, "invariant observations"
        )
        _validate_hash_bound(
            self, "invariant_id", "invariant_hash", "perspective_invariant_"
        )
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"invariant_id", "invariant_hash"}
        )


class InversionAssessment(_ShadowContract):
    """An explicit domain assessment; it never invents an inverse."""

    inversion_id: StrictStr = Field(pattern=_INVERSION_ID_PATTERN)
    inversion_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    source_node: NodeReference
    kind: InversionKind
    inverse_node: NodeReference | None = None
    domain: StrictStr = Field(min_length=1, max_length=256)
    reason: StrictStr = Field(min_length=1, max_length=1_000)
    epistemic_status: EpistemicStatus
    evidence_observation_bindings: tuple[ObservationBinding, ...] = Field(
        default=(), max_length=256
    )
    inferred_automatically: Literal[False] = False
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def inverse_presence_matches_classification(self) -> InversionAssessment:
        _unique_bindings(
            self.evidence_observation_bindings, "inversion observations"
        )
        no_result = self.kind in {
            InversionKind.NO_VALID_INVERSE,
            InversionKind.UNKNOWN,
        }
        if no_result and self.inverse_node is not None:
            raise ValueError("NO_VALID_INVERSE or UNKNOWN cannot carry an inverse node")
        if not no_result and self.inverse_node is None:
            raise ValueError("a valid inversion classification requires an explicit inverse node")
        if self.epistemic_status in {
            EpistemicStatus.MEASURED,
            EpistemicStatus.VERIFIED,
        } and not self.evidence_observation_bindings:
            raise ValueError("measured or verified inversion requires observations")
        _validate_hash_bound(
            self, "inversion_id", "inversion_hash", "inversion_"
        )
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"inversion_id", "inversion_hash"}
        )


class FlowerCenter(_ShadowContract):
    """One recursive Flower projection where any terminal may be a center."""

    flower_id: StrictStr = Field(pattern=_FLOWER_ID_PATTERN)
    flower_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    center: NodeReference
    terminals: tuple[NodeReference, ...] = Field(min_length=1, max_length=256)
    depth: StrictInt = Field(default=0, ge=0, le=1_000)
    previous_flower_id: StrictStr | None = Field(
        default=None, pattern=_FLOWER_ID_PATTERN
    )
    previous_flower_hash: StrictStr | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    recentered_from_terminal: NodeReference | None = None
    shadow_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def flower_is_recursive_and_content_addressed(self) -> FlowerCenter:
        _unique_refs(self.terminals, "Flower terminals")
        if self.center.node_id in {item.node_id for item in self.terminals}:
            raise ValueError("current Flower center cannot also be its terminal")
        predecessor_pair = (self.previous_flower_id, self.previous_flower_hash)
        if (predecessor_pair[0] is None) != (predecessor_pair[1] is None):
            raise ValueError("previous Flower id and hash must appear together")
        if self.depth == 0:
            if self.previous_flower_id is not None or self.recentered_from_terminal is not None:
                raise ValueError("genesis Flower cannot have recenter lineage")
        else:
            if self.previous_flower_id is None or self.recentered_from_terminal is None:
                raise ValueError("recursive Flower requires predecessor and terminal lineage")
            if self.previous_flower_id != f"flower_center_{self.previous_flower_hash}":
                raise ValueError("previous Flower id/hash mismatch")
            if self.center != self.recentered_from_terminal:
                raise ValueError("selected terminal must become the exact next center")
        if self.previous_flower_id == self.flower_id:
            raise ValueError("Flower cannot reference itself as predecessor")
        _validate_hash_bound(
            self, "flower_id", "flower_hash", "flower_center_"
        )
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"flower_id", "flower_hash"})


class UniversalMap(_ShadowContract):
    """One finite typed hypergraph plus content-addressed derived analyses."""

    schema_version: Literal["se6-universal-mapper-v1-shadow"] = (
        MAPPER_SCHEMA_VERSION
    )
    map_id: StrictStr = Field(pattern=_MAP_ID_PATTERN)
    map_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    vertices: tuple[MapperNode, ...] = Field(min_length=1, max_length=1_024)
    hyperedges: tuple[MapperHyperedge, ...] = Field(default=(), max_length=2_048)
    relations: tuple[MapperRelation, ...] = Field(default=(), max_length=2_048)
    dimensions: tuple[PeriodicDimension, ...] = Field(default=(), max_length=256)
    scales: tuple[ScaleDescriptor, ...] = Field(default=(), max_length=128)
    perspectives: tuple[PerspectiveView, ...] = Field(default=(), max_length=256)
    flower_lineage: tuple[FlowerCenter, ...] = Field(default=(), max_length=512)
    invariants: tuple[PerspectiveInvariant, ...] = Field(default=(), max_length=256)
    inversions: tuple[InversionAssessment, ...] = Field(default=(), max_length=512)
    finite: Literal[True] = True
    shadow_only: Literal[True] = True
    production_authoritative: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def graph_is_finite_referentially_closed_and_content_addressed(
        self,
    ) -> UniversalMap:
        _unique_ids(self.vertices, "node_id", "vertices")
        _unique_ids(self.relations, "relation_id", "relations")
        _unique_ids(self.hyperedges, "edge_id", "hyperedges")
        _unique_ids(self.dimensions, "dimension_id", "dimensions")
        _unique_ids(self.scales, "scale_id", "scales")
        _unique_ids(self.perspectives, "perspective_id", "perspectives")
        _unique_ids(self.flower_lineage, "flower_id", "Flower lineage")
        _unique_ids(self.invariants, "invariant_id", "invariants")
        _unique_ids(self.inversions, "inversion_id", "inversions")

        nodes = {item.node_id: item for item in self.vertices}
        relations = {item.relation_id: item for item in self.relations}
        perspectives = {
            item.perspective_id: item for item in self.perspectives
        }
        flowers = {item.flower_id: item for item in self.flower_lineage}
        scales = {item.scale_id: item for item in self.scales}

        for relation in self.relations:
            for ref in relation.source_nodes + relation.target_nodes:
                _require_node(ref, nodes)

        for edge in self.hyperedges:
            for ref in edge.endpoint_nodes:
                _require_node(ref, nodes)
            relation = relations.get(edge.relation.relation_id)
            if relation is None or relation.relation_hash != edge.relation.relation_hash:
                raise ValueError("hyperedge references an absent or mismatched relation")
            required = {
                item.node_id for item in relation.source_nodes + relation.target_nodes
            }
            endpoints = {item.node_id for item in edge.endpoint_nodes}
            if not required.issubset(endpoints):
                raise ValueError("hyperedge omits a relation endpoint")

        for dimension in self.dimensions:
            for terminal in dimension.terminals:
                _require_node(terminal.node, nodes)

        for scale in self.scales:
            if scale.parent_scale_id is not None:
                parent = scales.get(scale.parent_scale_id)
                if parent is None or parent.scale_hash != scale.parent_scale_hash:
                    raise ValueError("scale references an absent or mismatched parent")
                if parent.level >= scale.level:
                    raise ValueError("child scale level must exceed parent level")

        for perspective in self.perspectives:
            reality = _require_node(perspective.source_reality_object, nodes)
            if reality.kind is not NodeKind.REALITY_OBJECT:
                raise ValueError("perspective source must be a REALITY_OBJECT node")
            if perspective.source_observation_bindings != reality.source_observation_bindings:
                raise ValueError("perspective must preserve exact source reality bindings")

        for flower in self.flower_lineage:
            _require_node(flower.center, nodes)
            for terminal in flower.terminals:
                _require_node(terminal, nodes)
            if flower.recentered_from_terminal is not None:
                _require_node(flower.recentered_from_terminal, nodes)
            if flower.previous_flower_id is not None:
                parent = flowers.get(flower.previous_flower_id)
                if parent is None or parent.flower_hash != flower.previous_flower_hash:
                    raise ValueError("Flower references an absent or mismatched predecessor")
                if flower.depth != parent.depth + 1:
                    raise ValueError("Flower depth must advance exactly once")
                if flower.center not in parent.terminals:
                    raise ValueError("recursive Flower center was not a parent terminal")

        for invariant in self.invariants:
            reality = _require_node(invariant.source_reality_object, nodes)
            if reality.kind is not NodeKind.REALITY_OBJECT:
                raise ValueError("invariant source must be a REALITY_OBJECT node")
            if invariant.common_observation_bindings != reality.source_observation_bindings:
                raise ValueError("invariant must preserve source reality bindings")
            for ref in invariant.perspectives:
                view = perspectives.get(ref.perspective_id)
                if view is None or view.perspective_hash != ref.perspective_hash:
                    raise ValueError("invariant references an absent perspective")
                if view.source_reality_object != invariant.source_reality_object:
                    raise ValueError("invariant perspectives do not share one reality")

        for inversion in self.inversions:
            _require_node(inversion.source_node, nodes)
            if inversion.inverse_node is not None:
                _require_node(inversion.inverse_node, nodes)

        _validate_hash_bound(self, "map_id", "map_hash", "universal_map_")
        return self

    @property
    def graph_tuple(self) -> tuple[
        tuple[MapperNode, ...],
        tuple[MapperHyperedge, ...],
        tuple[MapperRelation, ...],
        tuple[PeriodicDimension, ...],
        tuple[ScaleDescriptor, ...],
        tuple[PerspectiveView, ...],
    ]:
        """Return the exact ``(V, E, R, D, S, P)`` projection."""

        return (
            self.vertices,
            self.hyperedges,
            self.relations,
            self.dimensions,
            self.scales,
            self.perspectives,
        )

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"map_id", "map_hash"})


class NodeBoundary(_ShadowContract):
    """Declared membership rule for a locus; never an inferred physical mask.

    Parent/child nesting uses the existing graph's explicit CONTAINS relation.
    Inside means satisfying ``scope``; outside means not satisfying it. The rule
    itself is the boundary, including when geometry is unavailable.
    """

    node: NodeReference
    scope: StrictStr = Field(min_length=1, max_length=1_000)
    parent: NodeReference | None = None

    @model_validator(mode="after")
    def nonempty_scope(self) -> NodeBoundary:
        if not self.scope.strip():
            raise ValueError("boundary requires a declared membership scope")
        return self


class MappingMeasurement(_ShadowContract):
    """Typed observation/analogue with explicit units, frame and uncertainty."""

    node: NodeReference
    quantity: StrictStr = Field(min_length=1, max_length=128)
    grounding: PeriodicGrounding
    meaning: StrictStr = Field(min_length=1, max_length=1_000)
    value: float = Field(allow_inf_nan=False)
    unit: StrictStr = Field(min_length=1, max_length=128)
    reference_frame: StrictStr = Field(min_length=1, max_length=256)
    observed_at_utc: datetime
    source_observation_bindings: tuple[ObservationBinding, ...] = Field(min_length=1, max_length=64)
    uncertainty: StrictStr = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def explicit_measurement_context(self) -> MappingMeasurement:
        if self.observed_at_utc.utcoffset() is None:
            raise ValueError("measurement timestamp must be timezone-aware")
        if any(not value.strip() for value in (
            self.quantity, self.meaning, self.unit, self.reference_frame, self.uncertainty
        )):
            raise ValueError("measurement semantics and uncertainty must be explicit")
        _unique_bindings(self.source_observation_bindings, "measurement observations")
        return self


class BoundedMapping(_ShadowContract):
    """Entity-bound annotations over an existing UniversalMap, not another graph.

    COUNT/SYMBOLIZE/BOUND/RELATE/INTERPRET are finite representation operations.
    Flower recentering transforms the view only. VERIFY/ASSIMILATE/NEXT STATE
    remain the existing consequence-gated runtime path; this record grants
    neither truth nor external authority and performs no persistence.
    """

    schema_version: Literal["se6-bounded-mapping-v1-shadow"] = "se6-bounded-mapping-v1-shadow"
    mapping_id: StrictStr = Field(pattern=r"^bounded_mapping_[0-9a-f]{64}$")
    mapping_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    entity_id: StrictStr = Field(pattern=r"^instance_[0-9a-f]{64}$")
    identity_state_id: StrictStr = Field(pattern=r"^identity_[0-9a-f]{64}$")
    entity_state_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    as_of_utc: datetime
    graph: UniversalMap
    boundaries: tuple[NodeBoundary, ...] = Field(min_length=1, max_length=1_024)
    measurements: tuple[MappingMeasurement, ...] = Field(default=(), max_length=1_024)
    source_observations: tuple[SourceObservation, ...] = Field(min_length=1, max_length=256)
    uncertainty: StrictStr = Field(min_length=1, max_length=2_000)
    shadow_only: Literal[True] = True
    production_authoritative: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def boundaries_and_evidence_are_closed(self) -> BoundedMapping:
        if self.as_of_utc.utcoffset() is None or not self.uncertainty.strip():
            raise ValueError("mapping requires explicit time and uncertainty")
        nodes = {node.node_id: node for node in self.graph.vertices}
        scopes = {item.node.node_id: item for item in self.boundaries}
        if len(scopes) != len(self.boundaries) or set(scopes) != set(nodes):
            raise ValueError("every node must have exactly one declared boundary")
        sources = {item.observation_id: item for item in self.source_observations}
        if len(sources) != len(self.source_observations):
            raise ValueError("mapping observations must be unique")

        def resolve(bindings):
            if not bindings:
                raise ValueError("bounded mapping material requires source provenance")
            result = []
            for binding in bindings:
                source = sources.get(binding.observation_id)
                if source is None or source.binding != binding:
                    raise ValueError("mapping references unknown or mismatched evidence")
                result.append(source)
            return result

        for item in (*self.graph.vertices, *self.graph.relations, *self.graph.perspectives):
            observations = resolve(item.source_observation_bindings)
            if item.epistemic_status is EpistemicStatus.VERIFIED and any(
                source.epistemic_status is not EpistemicStatus.VERIFIED for source in observations
            ):
                raise ValueError("mapping cannot promote source claims to VERIFIED")
            if item.epistemic_status is EpistemicStatus.MEASURED and any(
                source.epistemic_status not in {EpistemicStatus.MEASURED, EpistemicStatus.VERIFIED}
                for source in observations
            ):
                raise ValueError("mapping cannot promote symbolic claims to MEASURED")
        for boundary in self.boundaries:
            _require_node(boundary.node, nodes)
            if boundary.parent is not None:
                _require_node(boundary.parent, nodes)
                if not any(relation.kind is RelationKind.CONTAINS
                           and relation.source_nodes == (boundary.parent,)
                           and boundary.node in relation.target_nodes for relation in self.graph.relations):
                    raise ValueError("nested boundary requires an explicit CONTAINS relation")
            seen = {boundary.node.node_id}
            ancestor = boundary.parent
            while ancestor is not None:
                if ancestor.node_id in seen:
                    raise ValueError("boundary containment cannot be cyclic")
                seen.add(ancestor.node_id)
                ancestor = scopes[ancestor.node_id].parent
        for measurement in self.measurements:
            _require_node(measurement.node, nodes)
            observations = resolve(measurement.source_observation_bindings)
            if measurement.observed_at_utc > self.as_of_utc:
                raise ValueError("measurement cannot postdate mapping context")
            if measurement.grounding is PeriodicGrounding.PHYSICAL_OBSERVATION and any(
                source.epistemic_status not in {EpistemicStatus.MEASURED, EpistemicStatus.VERIFIED}
                for source in observations
            ):
                raise ValueError("physical measurement requires measured source evidence")
        _validate_hash_bound(self, "mapping_id", "mapping_hash", "bounded_mapping_")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"mapping_id", "mapping_hash"})

    def recenter(self, terminal: NodeReference, *, terminals: Sequence[NodeReference] = ()) -> BoundedMapping:
        """Recenter an existing Flower without changing Entity, sources or truth."""
        if not self.graph.flower_lineage:
            raise ValueError("recentring requires an existing Flower center")
        nodes = {node.node_id: node for node in self.graph.vertices}
        flower = recenter_flower(self.graph.flower_lineage[-1],
            terminal=_require_node(terminal, nodes),
            terminals=tuple(_require_node(ref, nodes) for ref in terminals))
        fields = {name: getattr(self.graph, name) for name in (
            "vertices", "hyperedges", "relations", "dimensions", "scales",
            "perspectives", "flower_lineage", "invariants", "inversions"
        )}
        fields["flower_lineage"] = (*self.graph.flower_lineage, flower)
        material = {name: getattr(self, name) for name in type(self).model_fields
                    if name not in {"mapping_id", "mapping_hash"}}
        material["graph"] = create_universal_map(**fields)
        return _build_hash_bound(BoundedMapping, "mapping_id", "mapping_hash", "bounded_mapping_", material)


def create_bounded_mapping(**context: Any) -> BoundedMapping:
    """Bind a graph to declared scopes; existing v1 graph/node hashes are intact."""
    # Strict final validation rejects extra authority or unbound graph fields.
    allowed = set(BoundedMapping.model_fields) - {"mapping_id", "mapping_hash"}
    if set(context) - allowed:
        raise ValueError("unknown bounded mapping fields")
    return _build_hash_bound(BoundedMapping, "mapping_id", "mapping_hash", "bounded_mapping_", context)


def create_mapper_node(
    *,
    kind: NodeKind,
    label: str,
    description: str,
    epistemic_status: EpistemicStatus,
    source_observations: Sequence[SourceObservation] = (),
) -> MapperNode:
    return _build_hash_bound(
        MapperNode,
        "node_id",
        "node_hash",
        "mapper_node_",
        {
            "kind": kind,
            "label": label,
            "description": description,
            "epistemic_status": epistemic_status,
            "source_observation_bindings": _bindings(source_observations),
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_reality_object(
    *,
    label: str,
    description: str,
    source_observations: Sequence[SourceObservation],
) -> MapperNode:
    """Create one reality object without promoting its observations to truth."""

    return create_mapper_node(
        kind=NodeKind.REALITY_OBJECT,
        label=label,
        description=description,
        epistemic_status=EpistemicStatus.DETERMINISTIC,
        source_observations=source_observations,
    )


def create_mapper_relation(
    *,
    kind: RelationKind,
    label: str,
    source_nodes: Sequence[MapperNode],
    target_nodes: Sequence[MapperNode],
    epistemic_status: EpistemicStatus,
    source_observations: Sequence[SourceObservation] = (),
) -> MapperRelation:
    return _build_hash_bound(
        MapperRelation,
        "relation_id",
        "relation_hash",
        "mapper_relation_",
        {
            "kind": kind,
            "label": label,
            "source_nodes": tuple(item.reference for item in source_nodes),
            "target_nodes": tuple(item.reference for item in target_nodes),
            "epistemic_status": epistemic_status,
            "source_observation_bindings": _bindings(source_observations),
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_mapper_hyperedge(
    relation: MapperRelation,
    *,
    additional_endpoint_nodes: Sequence[MapperNode] = (),
    directed: bool = True,
) -> MapperHyperedge:
    endpoints = list(relation.source_nodes + relation.target_nodes)
    known = {item.node_id for item in endpoints}
    for node in additional_endpoint_nodes:
        if node.node_id not in known:
            endpoints.append(node.reference)
            known.add(node.node_id)
    return _build_hash_bound(
        MapperHyperedge,
        "edge_id",
        "edge_hash",
        "mapper_edge_",
        {
            "relation": relation.reference,
            "endpoint_nodes": tuple(endpoints),
            "directed": directed,
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_periodic_terminal(
    node: MapperNode,
    *,
    label: str,
    grounding: PeriodicGrounding,
    epistemic_status: EpistemicStatus,
    source_observations: Sequence[SourceObservation] = (),
) -> PeriodicTerminal:
    return _build_hash_bound(
        PeriodicTerminal,
        "terminal_id",
        "terminal_hash",
        "periodic_terminal_",
        {
            "node": node.reference,
            "label": label,
            "grounding": grounding,
            "epistemic_status": epistemic_status,
            "source_observation_bindings": _bindings(source_observations),
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_periodic_dimension(
    *,
    name: str,
    property_name: str,
    terminals: Sequence[PeriodicTerminal],
) -> PeriodicDimension:
    return _build_hash_bound(
        PeriodicDimension,
        "dimension_id",
        "dimension_hash",
        "periodic_dimension_",
        {
            "name": name,
            "property_name": property_name,
            "terminals": tuple(terminals),
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_scale(
    *,
    name: str,
    level: int,
    parent: ScaleDescriptor | None = None,
) -> ScaleDescriptor:
    return _build_hash_bound(
        ScaleDescriptor,
        "scale_id",
        "scale_hash",
        "mapper_scale_",
        {
            "name": name,
            "level": level,
            "parent_scale_id": parent.scale_id if parent is not None else None,
            "parent_scale_hash": parent.scale_hash if parent is not None else None,
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_perspective_view(
    source_reality_object: MapperNode,
    *,
    perspective_key: str,
    representation: str,
    epistemic_status: EpistemicStatus = EpistemicStatus.INFERRED,
) -> PerspectiveView:
    if source_reality_object.kind is not NodeKind.REALITY_OBJECT:
        raise ValueError("perspective source must be a REALITY_OBJECT node")
    return _build_hash_bound(
        PerspectiveView,
        "perspective_id",
        "perspective_hash",
        "perspective_",
        {
            "transformation": "M(X|p)",
            "source_reality_object": source_reality_object.reference,
            "perspective_key": perspective_key,
            "representation": representation,
            "epistemic_status": epistemic_status,
            "source_observation_bindings": (
                source_reality_object.source_observation_bindings
            ),
            "is_source_reality": False,
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def extract_common_denominator(
    source_reality_object: MapperNode,
    perspectives: Sequence[PerspectiveView],
    *,
    description: str = "All views preserve one source reality and its exact observation provenance.",
) -> PerspectiveInvariant:
    """Extract the provenance invariant shared by at least two views.

    This deliberately does not claim that free-text interpretations share a
    semantic truth. The mechanically justified common denominator is the one
    source reality object and the exact immutable observations every view
    preserves.
    """

    views = tuple(perspectives)
    if source_reality_object.kind is not NodeKind.REALITY_OBJECT:
        raise ValueError("invariant source must be a REALITY_OBJECT node")
    if len(views) < 2:
        raise ValueError("common-denominator extraction requires two perspectives")
    for view in views:
        if view.source_reality_object != source_reality_object.reference:
            raise ValueError("perspectives must reference one source reality object")
        if view.source_observation_bindings != source_reality_object.source_observation_bindings:
            raise ValueError("perspective rewrote source observation bindings")
    return _build_hash_bound(
        PerspectiveInvariant,
        "invariant_id",
        "invariant_hash",
        "perspective_invariant_",
        {
            "invariant_kind": "SOURCE_REALITY_COMMON_DENOMINATOR",
            "source_reality_object": source_reality_object.reference,
            "perspectives": tuple(item.reference for item in views),
            "common_observation_bindings": (
                source_reality_object.source_observation_bindings
            ),
            "description": description,
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_inversion_assessment(
    source_node: MapperNode,
    *,
    kind: InversionKind,
    domain: str,
    reason: str,
    epistemic_status: EpistemicStatus,
    inverse_node: MapperNode | None = None,
    evidence_observations: Sequence[SourceObservation] = (),
) -> InversionAssessment:
    """Record an explicit inversion assessment without inferring an inverse."""

    return _build_hash_bound(
        InversionAssessment,
        "inversion_id",
        "inversion_hash",
        "inversion_",
        {
            "source_node": source_node.reference,
            "kind": kind,
            "inverse_node": inverse_node.reference if inverse_node is not None else None,
            "domain": domain,
            "reason": reason,
            "epistemic_status": epistemic_status,
            "evidence_observation_bindings": _bindings(evidence_observations),
            "inferred_automatically": False,
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_flower_center(
    center: MapperNode,
    *,
    terminals: Sequence[MapperNode],
) -> FlowerCenter:
    return _build_hash_bound(
        FlowerCenter,
        "flower_id",
        "flower_hash",
        "flower_center_",
        {
            "center": center.reference,
            "terminals": tuple(item.reference for item in terminals),
            "depth": 0,
            "previous_flower_id": None,
            "previous_flower_hash": None,
            "recentered_from_terminal": None,
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def recenter_flower(
    previous: FlowerCenter,
    terminal: MapperNode,
    *,
    terminals: Sequence[MapperNode],
) -> FlowerCenter:
    """Make one exact parent terminal the next recursive Flower center."""

    if terminal.reference not in previous.terminals:
        raise ValueError("only a terminal of the current Flower may become center")
    return _build_hash_bound(
        FlowerCenter,
        "flower_id",
        "flower_hash",
        "flower_center_",
        {
            "center": terminal.reference,
            "terminals": tuple(item.reference for item in terminals),
            "depth": previous.depth + 1,
            "previous_flower_id": previous.flower_id,
            "previous_flower_hash": previous.flower_hash,
            "recentered_from_terminal": terminal.reference,
            "shadow_only": True,
            "authority_effect": "NONE",
        },
    )


def create_universal_map(
    *,
    vertices: Sequence[MapperNode],
    hyperedges: Sequence[MapperHyperedge] = (),
    relations: Sequence[MapperRelation] = (),
    dimensions: Sequence[PeriodicDimension] = (),
    scales: Sequence[ScaleDescriptor] = (),
    perspectives: Sequence[PerspectiveView] = (),
    flower_lineage: Sequence[FlowerCenter] = (),
    invariants: Sequence[PerspectiveInvariant] = (),
    inversions: Sequence[InversionAssessment] = (),
) -> UniversalMap:
    """Construct one finite, referentially closed ``G=(V,E,R,D,S,P)``."""

    return _build_hash_bound(
        UniversalMap,
        "map_id",
        "map_hash",
        "universal_map_",
        {
            "schema_version": MAPPER_SCHEMA_VERSION,
            "vertices": tuple(vertices),
            "hyperedges": tuple(hyperedges),
            "relations": tuple(relations),
            "dimensions": tuple(dimensions),
            "scales": tuple(scales),
            "perspectives": tuple(perspectives),
            "flower_lineage": tuple(flower_lineage),
            "invariants": tuple(invariants),
            "inversions": tuple(inversions),
            "finite": True,
            "shadow_only": True,
            "production_authoritative": False,
            "authority_effect": "NONE",
        },
    )


def _bindings(observations: Sequence[SourceObservation]) -> tuple[ObservationBinding, ...]:
    return tuple(item.binding for item in observations)


def _build_hash_bound(
    model_type: type[_ShadowContract],
    id_field: str,
    hash_field: str,
    prefix: str,
    material: dict[str, Any],
) -> Any:
    draft = model_type.model_construct(
        **{id_field: f"{prefix}{'0' * 64}", hash_field: "0" * 64, **material}
    )
    normalized = draft.material_fields()  # type: ignore[attr-defined]
    digest = canonical_sha256(normalized)
    return model_type(**{id_field: f"{prefix}{digest}", hash_field: digest, **normalized})


def _validate_hash_bound(
    model: Any,
    id_field: str,
    hash_field: str,
    prefix: str,
) -> None:
    expected = canonical_sha256(model.material_fields())
    if getattr(model, hash_field) != expected:
        raise ValueError(f"{hash_field} must derive from contract material")
    if getattr(model, id_field) != f"{prefix}{expected}":
        raise ValueError(f"{id_field} must derive from contract material")


def _unique_bindings(bindings: Sequence[ObservationBinding], label: str) -> None:
    ids = tuple(item.observation_id for item in bindings)
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} must be unique")


def _unique_refs(refs: Sequence[NodeReference], label: str) -> None:
    ids = tuple(item.node_id for item in refs)
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} must be unique")


def _unique_ids(items: Sequence[Any], field: str, label: str) -> None:
    ids = tuple(getattr(item, field) for item in items)
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} must be unique")


def _require_node(
    ref: NodeReference,
    nodes: dict[str, MapperNode],
) -> MapperNode:
    node = nodes.get(ref.node_id)
    if node is None or node.node_hash != ref.node_hash:
        raise ValueError("graph contains an absent or mismatched node reference")
    return node


__all__ = [
    "MAPPER_SCHEMA_VERSION",
    "BoundedMapping",
    "FlowerCenter",
    "InversionAssessment",
    "InversionKind",
    "MapperHyperedge",
    "MapperNode",
    "MapperRelation",
    "MappingMeasurement",
    "NodeBoundary",
    "NodeKind",
    "NodeReference",
    "PeriodicDimension",
    "PeriodicGrounding",
    "PeriodicTerminal",
    "PerspectiveInvariant",
    "PerspectiveReference",
    "PerspectiveView",
    "RelationKind",
    "RelationReference",
    "ScaleDescriptor",
    "UniversalMap",
    "create_bounded_mapping",
    "create_flower_center",
    "create_inversion_assessment",
    "create_mapper_hyperedge",
    "create_mapper_node",
    "create_mapper_relation",
    "create_periodic_dimension",
    "create_periodic_terminal",
    "create_perspective_view",
    "create_reality_object",
    "create_scale",
    "create_universal_map",
    "extract_common_denominator",
    "recenter_flower",
]
