"""Opt-in finite-history Native probability adapter, never execution authority.

Persistent material lives in the existing Native export/renewal, not a new
Entity schema. The host authenticates effect evidence and the atomic renewal.
Only one-step finite consensus candidates are supported. Model hypotheses,
predictions and raw caller flags cannot certify outcomes.
"""
from copy import deepcopy
import json

from . import qpre_calibration_v1 as cal
from .observation_grounding import digest, require, beliefs, raw_id
from .symbolic_realization import _evaluation

VERSION = 'se6-native-calibrated-one-step-development-v1'
OUTCOMES = ('GOAL', 'NO_GOAL', 'OTHER')


def scope_for(value, history, binding, actions, frame):
    """Stable semantic context; exclude moving state/head/cost from class keys."""
    return dict(version=VERSION, entity=binding['entity_id'],source=binding['source'],
        epoch=binding['epoch'],model_semantics=digest(value['proposal']),frame=digest(frame),
        beliefs=sorted([digest(model),state] for model,state in beliefs(value['proposal'],history)),
        actions={a['id']:digest(a['payload']) for a in actions})


def keys(scope):
    return {action:'native-action-'+digest(dict(scope=scope,action=action,payload=payload))
            for action,payload in sorted(scope['actions'].items())}


def initial(scope):
    return dict(version=VERSION,scope=deepcopy(scope),
        snapshot=cal.initial_calibration({key:OUTCOMES for key in keys(scope).values()}).model_dump(mode='json'))


def snapshot(state):
    require(state['version']==VERSION,'NATIVE_CALIBRATION_VERSION')
    value=cal.CalibrationSnapshot.model_validate_json(json.dumps(state['snapshot']))
    require({a.action_key:a.outcome_catalog for a in value.actions}=={key:OUTCOMES for key in keys(state['scope']).values()},
            'NATIVE_CALIBRATION_ACTION_CLASSES')
    return value


def probability_render(render, lookup, policy, binding, state):
    require(state['scope']['entity']==binding['entity_id'] and state['scope']['source']==binding['source'] and
        state['scope']['epoch']==binding['epoch'] and state['scope']['frame']==digest(policy['frame']),
        'NATIVE_CALIBRATION_SOURCE_SCOPE')
    require(all(len(lookup[c.candidate_id]['continuation'])==1 for c in render.possibility_field.candidates),
            'NATIVE_CALIBRATION_ONE_STEP_ONLY')
    saved=snapshot(state);action_keys=keys(state['scope'])
    distributions=[cal.posterior_distribution(saved,candidate_id=c.candidate_id,
        action_key=action_keys[lookup[c.candidate_id]['continuation'][0]]) for c in render.possibility_field.candidates]
    wrapped=cal.build_probability_render(render,model_version=saved.model_version,
        calibration_state_hash=saved.snapshot_id.removeprefix('calibration_'),distributions=distributions)
    return wrapped


def render_and_rank(render, candidates, lookup, policy, binding, state, *, rendered=None):
    expected=probability_render(render,lookup,policy,binding,state)
    require(rendered is None or rendered==expected,'NATIVE_PROBABILITY_RENDER_CHANGED')
    wrapped=rendered or expected
    scores=[]
    for candidate in candidates:
        distribution=next(d for d in wrapped.distributions if d.candidate_id==candidate.candidate_id)
        p=next(o.point_bp for o in distribution.outcomes if o.outcome_id=='GOAL')
        penalty=_evaluation(candidate,benefit=0,uncertainty=policy['uncertainty_units']).net_score
        scores.append(dict(candidate_id=candidate.candidate_id,
            score_numerator=policy['goal_value_units']*p+10000*penalty,denominator=10000))
    ordered=sorted(scores,key=lambda r:(-r['score_numerator'],r['candidate_id']))
    chosen=ordered[0]['candidate_id'] if ordered and ordered[0]['score_numerator']>0 else None
    material=dict(version=VERSION,render=wrapped.model_dump(mode='json'),
        calibration_state=deepcopy(state),binding=deepcopy(binding),scores=scores,
        candidate_actions={c.candidate_id:lookup[c.candidate_id]['continuation'][0] for c in render.possibility_field.candidates},
        selected_candidate_id=chosen,authority_effect='NONE',actual=False)
    material['material_sha256']=digest(material)
    return chosen,material


def validate_pending(state,pending):
    material=pending['prepared']['learned']['selection']['probability_learning']
    require(material['material_sha256']==digest({k:v for k,v in material.items() if k!='material_sha256'}),
            'NATIVE_PROBABILITY_MATERIAL_CHANGED')
    require(material['version']==VERSION and material['authority_effect']=='NONE' and material['actual'] is False,
            'NATIVE_PROBABILITY_NOT_AUTHORITY')
    require(material['calibration_state']==state and material['binding']==pending['prepared']['binding'],
            'NATIVE_CALIBRATION_STALE_OR_BINDING')
    wrapped=cal.QPREProbabilityRender.model_validate_json(json.dumps(material['render']))
    saved=snapshot(state)
    require(wrapped.calibration_state_hash==saved.snapshot_id.removeprefix('calibration_') and
        wrapped.base_render.possibility_field.source_state_hash==pending['prepared']['binding']['entity_state'] and
        wrapped.base_render.possibility_field.model_dump(mode='json')==pending['prepared']['learned']['selection']['possibility_field'],'NATIVE_PROBABILITY_STATE_FRAME')
    require(wrapped.distributions==tuple(cal.posterior_distribution(saved,candidate_id=d.candidate_id,action_key=d.action_key)
        for d in wrapped.distributions),'NATIVE_PROBABILITY_POSTERIOR')
    for base in wrapped.base_render.possibility_field.candidates:
        word=json.loads(next(f.possible_value for f in base.realization.candidate_state if f.name=='continuation'))
        require(len(word)==1 and material['candidate_actions'][base.candidate_id]==word[0],
                'NATIVE_PROBABILITY_ACTION_ATTRIBUTION')
        distribution=next(d for d in wrapped.distributions if d.candidate_id==base.candidate_id)
        require(distribution.action_key==keys(state['scope'])[word[0]],
                'NATIVE_PROBABILITY_KEY_ATTRIBUTION')
    candidate=material['selected_candidate_id']
    action=pending['action']
    require(material['candidate_actions'][candidate]==action['id'] and
        state['scope']['actions'][action['id']]==digest(action['payload']) and
        pending['prepared']['learned']['actions']==[action['id']],'NATIVE_PROBABILITY_SELECTED_ACTION')
    return wrapped


def feedback(state,pending,witness,*,verified_effect):
    require(verified_effect is True,'NATIVE_CALIBRATION_INDEPENDENT_EFFECT_REQUIRED')
    render=validate_pending(state,pending)
    prediction=pending['prepared']['learned']['prediction']['outcomes'][0]
    observed_raw=raw_id(witness['raw'])
    outcome=('GOAL' if witness['goal'] else 'NO_GOAL') if prediction[0]==observed_raw else 'UNMODELED_RAW'
    readback=cal.OutcomeReadback(render_id=render.render_id,
        candidate_id=pending['prepared']['learned']['selection']['probability_learning']['selected_candidate_id'],
        actual_outcome_id=outcome,witness_reference='witness-'+digest(witness),
        receipt_reference='effect-'+digest(dict(entity=witness['entity_id'],source=witness['source'],
            epoch=witness['epoch'],attempt=witness['attempt_id'])))
    update=cal.update_from_verified_readback(snapshot(state),render,readback,
        verifier=lambda value: verified_effect is True and value==readback)
    after=dict(state,snapshot=update.next_state.model_dump(mode='json'))
    record=dict(version=VERSION,before=deepcopy(state),after=after,pending=deepcopy(pending),
        witness=deepcopy(witness),readback=readback.model_dump(mode='json'),feedback=update.model_dump(mode='json'))
    record['record_sha256']=digest(record)
    return after,record


def verify_history(state,events,verifier):
    """Restore requires independent host evidence, not just a self-hashed log."""
    if not events:
        require(state is None or state==initial(state['scope']),'NATIVE_CALIBRATION_UNWITNESSED_COUNTS')
        return
    require(callable(verifier),'NATIVE_LEARNING_RESTORE_VERIFIER_REQUIRED')
    current=initial(events[0]['before']['scope'])
    for event in events:
        require(event['record_sha256']==digest({k:v for k,v in event.items() if k!='record_sha256'}) and
            event['before']==current,'NATIVE_CALIBRATION_HISTORY_CHAIN')
        require(verifier(deepcopy(event)) is True,'NATIVE_CALIBRATION_RESTORE_AUTHORITY')
        current,recomputed=feedback(current,event['pending'],event['witness'],verified_effect=True)
        require(recomputed==event,'NATIVE_CALIBRATION_REPLAY')
    require(current==state,'NATIVE_CALIBRATION_HEAD')
