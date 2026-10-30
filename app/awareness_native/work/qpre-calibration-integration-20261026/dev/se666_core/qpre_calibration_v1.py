"""Opt-in probabilistic QPRE development V1; never grants World authority.

This module wraps the unchanged deterministic QPRE render with a NEW, fully
content-addressed versioned render. Probabilities are explicitly from a
Dirichlet-multinomial estimator trained only on readbacks that a separate
host verifier accepts. A caller-supplied hash does not independently verify
reality. No production selector, approval, Entity memory or API uses this V1.

All probabilities use exact integer basis points (10000 = 1). Intervals are
conservative *approximate* two-posterior-standard-deviation uncertainty bands,
NOT empirically certified calibration or coverage guarantees. No quantum
interference, hardware, or physical-quantum claims are made here.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from math import sqrt
import re
import json

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from .canonical_contracts import canonical_sha256
from .qpre import QPRERender, QPREEpistemicClass

VERSION = 'se6-qpre-probability-shadow-v1'
MODEL_VERSION = 'se6-dirichlet-multinomial-fixed-v1'
REF_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$')
HASH_RE = re.compile(r'^[0-9a-f]{64}$')
TOTAL = 10000


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _ref(value: str) -> None:
    _require(type(value) is str and REF_RE.fullmatch(value) is not None,
             'CALIBRATION_SAFE_REFERENCE_REQUIRED')


def _content_id(prefix: str, data: object) -> str:
    return prefix+'_'+canonical_sha256(data)


class DistributionSemantics(str, Enum):
    EXHAUSTIVE = 'EXHAUSTIVE'
    OPEN_WORLD = 'OPEN_WORLD'
    OVERLAPPING = 'OVERLAPPING'


class ProbabilityBasis(str, Enum):
    EMPIRICAL_MODEL = 'EMPIRICAL_MODEL'
    DECLARED_MODEL = 'DECLARED_MODEL'
    UNCALIBRATED = 'UNCALIBRATED'


class OutcomeProbability(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    outcome_id: StrictStr
    point_bp: StrictInt | None = Field(default=None, ge=0, le=TOTAL)
    lower_bp: StrictInt = Field(ge=0, le=TOTAL)
    upper_bp: StrictInt = Field(ge=0, le=TOTAL)
    basis: ProbabilityBasis
    model_reference: StrictStr
    epistemic_class: QPREEpistemicClass = QPREEpistemicClass.PREDICTION
    actual: bool = False
    verified: bool = False
    authority: bool = False
    memory_eligible: bool = False

    @model_validator(mode='after')
    def valid(self):
        _ref(self.outcome_id)
        _ref(self.model_reference)
        _require(self.epistemic_class is QPREEpistemicClass.PREDICTION and
                 not (self.actual or self.verified or self.authority or self.memory_eligible),
                 'CALIBRATION_PREDICTION_CANNOT_BE_ACTUAL')
        if self.basis is ProbabilityBasis.UNCALIBRATED:
            _require(self.point_bp is None and self.lower_bp==0 and self.upper_bp==TOTAL,
                     'CALIBRATION_UNCALIBRATED_MUST_BE_VACUOUS')
        else:
            _require(self.point_bp is not None and
                     self.lower_bp <= self.point_bp <= self.upper_bp,
                     'CALIBRATION_PROBABILITY_INTERVAL')
        return self


class ConditionalDistribution(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    candidate_id: StrictStr
    action_key: StrictStr
    semantics: DistributionSemantics
    outcomes: tuple[OutcomeProbability, ...] = Field(min_length=1, max_length=64)
    residual_bp: StrictInt | str | None = None

    @model_validator(mode='after')
    def valid(self):
        _ref(self.candidate_id)
        _ref(self.action_key)
        names=[x.outcome_id for x in self.outcomes]
        _require(len(names)==len(set(names)), 'CALIBRATION_DUPLICATE_OUTCOMES')
        points=[x.point_bp for x in self.outcomes]
        if self.semantics is DistributionSemantics.OVERLAPPING:
            _require(self.residual_bp == 'UNKNOWN', 'CALIBRATION_OVERLAPPING_RESIDUAL_UNKNOWN')
        else:
            _require(all(p is not None for p in points),
                     'CALIBRATION_UNCALIBRATED_DISTRIBUTION_CANNOT_NORMALIZE')
            summed=sum(points)
            if self.semantics is DistributionSemantics.EXHAUSTIVE:
                _require(summed==TOTAL and self.residual_bp is None,
                         'CALIBRATION_EXHAUSTIVE_TOTAL')
            else:
                _require(type(self.residual_bp) is int and 0 < self.residual_bp <= TOTAL and
                         summed+self.residual_bp==TOTAL,
                         'CALIBRATION_OPEN_WORLD_RESIDUAL')
        return self


class QPREProbabilityRender(BaseModel):
    """New render identity includes immutable base render AND probability material."""
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    schema_version: str = VERSION
    render_id: StrictStr
    base_render: QPRERender
    model_version: StrictStr
    calibration_state_hash: StrictStr
    distributions: tuple[ConditionalDistribution, ...] = Field(min_length=1, max_length=64)
    epistemic_class: QPREEpistemicClass = QPREEpistemicClass.POSSIBILITY
    actual: bool = False
    verified: bool = False
    authority: bool = False
    memory_eligible: bool = False

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode='python',exclude={'render_id'})

    @model_validator(mode='after')
    def valid(self):
        _require(self.schema_version==VERSION, 'CALIBRATION_RENDER_VERSION')
        _ref(self.model_version)
        _require(HASH_RE.fullmatch(self.calibration_state_hash) is not None,
                 'CALIBRATION_STATE_HASH')
        _require(self.epistemic_class is QPREEpistemicClass.POSSIBILITY and
                 not (self.actual or self.verified or self.authority or self.memory_eligible),
                 'CALIBRATION_RENDER_NOT_ACTUAL')
        expected={c.candidate_id for c in self.base_render.possibility_field.candidates}
        ids=[x.candidate_id for x in self.distributions]
        _require(len(ids)==len(set(ids)) and set(ids)==expected,
                 'CALIBRATION_QPRE_CANDIDATE_COVERAGE')
        _require(self.render_id==_content_id('qpre_probability_render',self.material_fields()),
                 'CALIBRATION_RENDER_HASH_MISMATCH')
        return self


def build_probability_render(base_render: QPRERender, *,
        model_version: str, calibration_state_hash: str,
        distributions: Sequence[ConditionalDistribution]) -> QPREProbabilityRender:
    _require(type(base_render) is QPRERender, 'CALIBRATION_QPRE_BASE_REQUIRED')
    QPRERender.model_validate_json(base_render.model_dump_json())
    material=dict(schema_version=VERSION,base_render=base_render,
                  model_version=model_version,calibration_state_hash=calibration_state_hash,
                  distributions=tuple(distributions),
                  epistemic_class=QPREEpistemicClass.POSSIBILITY,
                  actual=False,verified=False,authority=False,memory_eligible=False)
    draft=QPREProbabilityRender.model_construct(render_id='draft',**material)
    normalized=draft.material_fields()
    return QPREProbabilityRender.model_validate_json(json.dumps(dict(
        render_id=_content_id('qpre_probability_render',normalized),**normalized),
        default=lambda x:x.model_dump(mode='json') if isinstance(x,BaseModel) else x.value))


class CalibratedAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    action_key: StrictStr
    outcome_catalog: tuple[StrictStr, ...] = Field(min_length=2, max_length=64)
    counts: tuple[StrictInt, ...]

    @model_validator(mode='after')
    def valid(self):
        _ref(self.action_key)
        _require(len(self.outcome_catalog)==len(self.counts) and
                 len(self.outcome_catalog)==len(set(self.outcome_catalog)),
                 'CALIBRATION_COUNT_CATALOG')
        for outcome in self.outcome_catalog:
            _ref(outcome)
        _require(all(type(c) is int and c>=0 for c in self.counts),
                 'CALIBRATION_NONNEGATIVE_COUNTS')
        return self


class CalibrationSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    snapshot_id: StrictStr
    model_version: StrictStr = MODEL_VERSION
    alpha: StrictInt = Field(default=1, ge=1, le=1000)
    actions: tuple[CalibratedAction, ...] = Field(min_length=1, max_length=64)
    consumed_receipts: tuple[StrictStr, ...] = ()
    evidence_hashes: tuple[StrictStr, ...] = ()

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode='python',exclude={'snapshot_id'})

    @model_validator(mode='after')
    def valid(self):
        _require(self.model_version==MODEL_VERSION, 'CALIBRATION_MODEL_VERSION')
        keys=[action.action_key for action in self.actions]
        _require(len(keys)==len(set(keys)), 'CALIBRATION_DUPLICATE_ACTIONS')
        _require(len(set(self.consumed_receipts))==len(self.consumed_receipts),
                 'CALIBRATION_DUPLICATE_RECEIPTS')
        _require(len(self.evidence_hashes)==len(self.consumed_receipts) and
                 all(HASH_RE.fullmatch(h) for h in self.evidence_hashes),
                 'CALIBRATION_RECEIPT_EVIDENCE_ALIGNMENT')
        for receipt in self.consumed_receipts:
            _ref(receipt)
        _require(self.snapshot_id==_content_id('calibration',self.material_fields()),
                 'CALIBRATION_SNAPSHOT_HASH_MISMATCH')
        return self


def _snapshot(*, actions: Sequence[CalibratedAction], alpha: int,
              receipts: Sequence[str] = (), evidence_hashes: Sequence[str] = ()) -> CalibrationSnapshot:
    material=dict(model_version=MODEL_VERSION,alpha=alpha,actions=tuple(actions),
                  consumed_receipts=tuple(receipts),evidence_hashes=tuple(evidence_hashes))
    draft=CalibrationSnapshot.model_construct(snapshot_id='draft',**material)
    fields=draft.material_fields()
    return CalibrationSnapshot.model_validate(dict(snapshot_id=_content_id('calibration',fields),**fields))


def initial_calibration(catalogs: Mapping[str, Sequence[str]], *, alpha: int=1):
    _require(type(alpha) is int and 1<=alpha<=1000, 'CALIBRATION_ALPHA')
    _require(0<len(catalogs)<=64, 'CALIBRATION_ACTION_CATALOG')
    actions=[CalibratedAction(action_key=key,outcome_catalog=tuple(catalog),
                              counts=tuple(0 for _ in catalog))
             for key,catalog in sorted(catalogs.items())]
    return _snapshot(actions=actions,alpha=alpha)


def _quantize(weights: Sequence[int]) -> tuple[int,...]:
    """Largest-remainder deterministic exact 10000-bp normalization."""
    denominator=sum(weights)
    _require(denominator>0, 'CALIBRATION_EMPTY_POSTERIOR')
    exact=[divmod(w*TOTAL,denominator) for w in weights]
    values=[q for q,r in exact]
    remaining=TOTAL-sum(values)
    ranked=sorted(range(len(weights)),key=lambda i:(-exact[i][1],i))
    for i in ranked[:remaining]:
        values[i]+=1
    # Finite basis points can round a positive open-world residual to zero.
    # Reserve the smallest representable mass for every positive modeled class.
    # This quantization convention is disclosed; it is not probability proof.
    for i,weight in enumerate(weights):
        if weight>0 and values[i]==0:
            donor=max(range(len(weights)),key=lambda j:(values[j],-j))
            _require(values[donor]>1,'CALIBRATION_FINITE_PRECISION')
            values[donor]-=1
            values[i]+=1
    _require(sum(values)==TOTAL,'CALIBRATION_NORMALIZATION')
    return tuple(values)


def posterior_distribution(state: CalibrationSnapshot, *, action_key: str,
        candidate_id: str, semantics: DistributionSemantics=DistributionSemantics.OPEN_WORLD):
    """Dirichlet posterior predictive over a stable action/outcome catalog.

    OPEN_WORLD requires last catalog entry OTHER (all unlisted outcomes), and
    emits that posterior's probability as explicit residual mass.
    """
    action=next((a for a in state.actions if a.action_key==action_key),None)
    CalibrationSnapshot.model_validate_json(state.model_dump_json())
    _require(action is not None,'CALIBRATION_ACTION_NOT_REGISTERED')
    _require(semantics in (DistributionSemantics.OPEN_WORLD,DistributionSemantics.EXHAUSTIVE),
             'CALIBRATION_LEARNER_MODE_UNSUPPORTED')
    if semantics is DistributionSemantics.OPEN_WORLD:
        _require(action.outcome_catalog[-1]=='OTHER','CALIBRATION_OPEN_WORLD_REQUIRES_OTHER')
    weights=[state.alpha+c for c in action.counts]
    total=sum(weights)
    points=_quantize(weights)
    outcomes=[]
    size=len(weights)-(1 if semantics is DistributionSemantics.OPEN_WORLD else 0)
    for i in range(size):
        mean=weights[i]/total
        variance=mean*(1-mean)/(total+1)
        # Approximately two posterior sigma, not a certified coverage interval.
        half=2*sqrt(variance)
        lower=max(0,min(points[i],int((mean-half)*TOTAL)))
        upper=min(TOTAL,max(points[i],int((mean+half)*TOTAL+0.999999)))
        outcomes.append(OutcomeProbability(outcome_id=action.outcome_catalog[i],
                        point_bp=points[i],lower_bp=lower,upper_bp=upper,
                        basis=ProbabilityBasis.EMPIRICAL_MODEL,
                        model_reference='calibration:'+state.snapshot_id))
    return ConditionalDistribution(candidate_id=candidate_id,action_key=action_key,
           semantics=semantics,outcomes=tuple(outcomes),
           residual_bp=(points[-1] if semantics is DistributionSemantics.OPEN_WORLD else None))


class OutcomeReadback(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    render_id: StrictStr
    candidate_id: StrictStr
    actual_outcome_id: StrictStr
    witness_reference: StrictStr
    receipt_reference: StrictStr

    @model_validator(mode='after')
    def valid(self):
        for value in (self.render_id,self.candidate_id,self.actual_outcome_id,
                      self.witness_reference,self.receipt_reference):
            _ref(value)
        return self


class CalibrationFeedback(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    next_state: CalibrationSnapshot
    escaped_field: bool
    counted_as: StrictStr | None
    receipt_reference: StrictStr
    evidence_hash: StrictStr
    # This record is *not* an Entity verified-memory event.
    production_assimilated: bool = False


def update_from_verified_readback(state: CalibrationSnapshot,
        render: QPREProbabilityRender, observed: OutcomeReadback, *,
        verifier: Callable[[OutcomeReadback], bool]) -> CalibrationFeedback:
    """Only accept a host-authenticated readback for the exact rendered action.

    The caller must supply a genuinely independent verifier. A test verifier
    is only test evidence. No local field, hash or bool self-certifies truth.
    """
    _require(type(state) is CalibrationSnapshot and
             type(render) is QPREProbabilityRender and
             type(observed) is OutcomeReadback,
             'CALIBRATION_STRICT_INPUTS')
    _require(callable(verifier) and verifier(observed) is True,
             'CALIBRATION_INDEPENDENT_WITNESS_REQUIRED')
    CalibrationSnapshot.model_validate_json(state.model_dump_json())
    QPREProbabilityRender.model_validate_json(render.model_dump_json())
    OutcomeReadback.model_validate_json(observed.model_dump_json())
    _require(render.calibration_state_hash==state.snapshot_id.removeprefix('calibration_') and
             render.model_version==state.model_version and
             observed.render_id==render.render_id,
             'CALIBRATION_STALE_RENDER_OR_MODEL')
    _require(observed.receipt_reference not in state.consumed_receipts,
             'CALIBRATION_DUPLICATE_RECEIPT')
    forecast=next((d for d in render.distributions if d.candidate_id==observed.candidate_id),None)
    _require(forecast is not None,'CALIBRATION_EXECUTED_CANDIDATE_REQUIRED')
    action=next(a for a in state.actions if a.action_key==forecast.action_key)
    projected={p.outcome_id for p in forecast.outcomes}
    escaped=observed.actual_outcome_id not in projected
    counted=observed.actual_outcome_id
    if escaped and forecast.semantics is DistributionSemantics.OPEN_WORLD:
        counted='OTHER'
    if counted not in action.outcome_catalog:
        counted=None  # retain receipt evidence; do not launder into prediction
    updated=[]
    for entry in state.actions:
        if entry.action_key!=action.action_key or counted is None:
            updated.append(entry)
        else:
            counts=list(entry.counts)
            counts[entry.outcome_catalog.index(counted)]+=1
            updated.append(entry.model_copy(update={'counts':tuple(counts)}))
    evidence_hash=canonical_sha256(dict(calibration_before=state.snapshot_id,
        exact_render=render.render_id,readback=observed.model_dump(mode='json'),
        escaped_field=escaped,counted_as=counted))
    next_state=_snapshot(actions=updated,alpha=state.alpha,
                         receipts=(*state.consumed_receipts,observed.receipt_reference),
                         evidence_hashes=(*state.evidence_hashes,evidence_hash))
    return CalibrationFeedback(next_state=next_state,escaped_field=escaped,
                               counted_as=counted,receipt_reference=observed.receipt_reference,
                               evidence_hash=evidence_hash)


__all__=['VERSION','MODEL_VERSION','DistributionSemantics','ProbabilityBasis',
         'OutcomeProbability','ConditionalDistribution','QPREProbabilityRender',
         'build_probability_render','CalibrationSnapshot','initial_calibration',
         'posterior_distribution','OutcomeReadback','CalibrationFeedback',
         'update_from_verified_readback']
