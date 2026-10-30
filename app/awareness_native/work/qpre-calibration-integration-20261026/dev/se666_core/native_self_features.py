"""Finite operational self-specialization: bounded local scan capacity.

This pure typed mapping neither authenticates a sensor nor derives the owner's
numerical rho*R_self. Native must independently reread the actual source port
and current Entity, and bind its source/task frames before using the result.
Only a task explicitly requiring a complete policy-filtered metadata scan may
consume completeness as a narrowing constraint. Counts never become World
effect allowance, value, execution authority or geographic knowledge.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction

from .canonical_contracts import canonical_sha256
from .candidate_state_transition import tree
from .local_entity_observers import RepositoryObservationPolicy, RepositoryObservationSnapshot
from .observation_grounding import digest, require

VERSION = 'se6-native-finite-self-features-v1'
SPECIALIZATION = 'FINITE_REPOSITORY_METADATA_SCAN_CAPACITY_V1'
_COUNT_UNIT = dict(id='count:repository-metadata-entry', kind='COUNT',
    dimension=[['repository-metadata-entry',1]])
_RATIO_UNIT = dict(id='ratio:repository-scan-utilization', kind='MEASUREMENT', dimension=[])


def _wire(value):
    exact = Fraction(value)
    return [exact.numerator, exact.denominator]


def derive_repository_features(repository_snapshot, observation_policy, *, context):
    """Compute exact coordinates conditional on an independently verified read.

    entry_count is the admitted scanner's actual returned metadata count;
    entry_limit is its source policy cap. remaining_scan_slots is capacity
    minus recorded count, not unknown filesystem size or action permission.
    utilization is a dimensionless measurement ratio, not a probability.
    is_complete means untruncated under this exact metadata/filter policy.

    The source scanner detects a further allowed file before setting
    truncated; consequently an exact-limit, untruncated scan is complete.
    Completeness does not imply that file contents, excluded paths, all local
    sensors or the wider world are known. There is no invented time-to-live:
    observed_at is an as-of value; currentness requires an actual source read.
    """
    require(type(repository_snapshot) is RepositoryObservationSnapshot and
        type(observation_policy) is RepositoryObservationPolicy, 'SELF_FEATURE_ACTUAL_SCAN_TYPES')
    snapshot = RepositoryObservationSnapshot.model_validate(repository_snapshot.model_dump(mode='python'))
    policy = RepositoryObservationPolicy.model_validate(observation_policy.model_dump(mode='python'))
    require(type(context) is dict and context and all(type(key) is str for key in context),
        'SELF_FEATURE_CONTEXT_REQUIRED')
    tree(context)  # Bound and type-preserve the complete source/task frame context.
    count = snapshot.entry_count
    limit = policy.max_files
    require(count == len(snapshot.entries) and count <= limit, 'SELF_FEATURE_SCAN_CAPACITY')
    require(not snapshot.truncated or count == limit, 'SELF_FEATURE_TRUNCATION_SOURCE_LAW')
    complete = not snapshot.truncated
    policy_hash = canonical_sha256(policy.model_dump(mode='python'))
    material = dict(version=VERSION, specialization=SPECIALIZATION,
        scope='PURE_MATH_CONDITIONAL_ON_INDEPENDENT_CURRENT_SOURCE_VERIFICATION',
        source_verification='REQUIRED_UPSTREAM_NOT_ESTABLISHED_BY_THIS_FUNCTION',
        source_snapshot_id=snapshot.snapshot_id, source_tree_hash=snapshot.tree_hash,
        source_observation_policy_hash=policy_hash,
        observed_at_utc=snapshot.observed_at_utc.isoformat(), context=deepcopy(context), context_sha256=digest(context),
        entry_count=_wire(count), entry_limit=_wire(limit), remaining_scan_slots=_wire(limit-count),
        utilization=_wire(Fraction(count,limit)), is_complete=complete,
        constraint_result='COMPLETE_REPOSITORY_SCAN' if complete else 'INCOMPLETE_REPOSITORY_SCAN',
        units=dict(entry_count=deepcopy(_COUNT_UNIT), entry_limit=deepcopy(_COUNT_UNIT),
            remaining_scan_slots=deepcopy(_COUNT_UNIT), utilization=deepcopy(_RATIO_UNIT)),
        freshness='AS_OF_SOURCE_READ_NO_INVENTED_TTL',
        coverage='ONLY_ALLOWED_REPOSITORY_METADATA_UNDER_BOUND_FILTER_POLICY',
        unknown=['File contents, excluded paths, unobserved sensors and external world remain unknown.'],
        owner_equation=dict(status='UNRESOLVED',
            reason='No adopted state-coordinate lift, self-reference gain rho or operator combination law.',
            identification='FINITE_OPERATIONAL_SPECIALIZATION_ONLY_NOT_FULL_R_SELF'),
        authority_effect='NONE', world_execution_approval='NOT_GRANTED', world_truth=False,
        provenance=[snapshot.snapshot_id,'repository-policy:'+policy_hash])
    return {**material, 'features_sha256':digest(material)}


__all__ = ['VERSION','SPECIALIZATION','derive_repository_features']
