"""Bounded DEVELOPMENT dependency operator, not owner-adopted equation semantics.

Domain: one public affine CLI, 2..8 manifest profiles, integer config values.
Codomain: conditional one-action predictions and derived parameters. Observers
provide bytes/context only; this operator resolves entry->profile->config and
solves gain*limit+offset=public_goal using exact integers. World truth requires
the separate dispatcher and independent subprocess witness.
"""
from copy import deepcopy
from fractions import Fraction
from pathlib import PurePosixPath,Path
import hashlib,json
from .observation_grounding import digest,require,raw_id

VERSION='se6-native-dependency-relation-development-v1'

def is_certificate(value):return isinstance(value,dict) and value.get('version')==VERSION
def pin():return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def certificate(observation,history,binding,*,memory=None):
    value=dict(version=VERSION,proposal=dict(version=VERSION,source=binding['source'],epoch=binding['epoch'],
        contract_sha256=pin(),limits={'max_plan_depth':1}),observation=deepcopy(observation),
        history=deepcopy(history),binding=deepcopy(binding),memory=deepcopy(memory))
    return {**value,'certificate_sha256':digest(value)}

def validate(value,authority):
    require(is_certificate(value) and set(value)=={'version','proposal','observation','history','binding','memory','certificate_sha256'},'DEPENDENCY_CERTIFICATE_SHAPE')
    require(value['certificate_sha256']==digest({k:v for k,v in value.items() if k!='certificate_sha256'}),'DEPENDENCY_CERTIFICATE_SEAL')
    require(value['proposal']==dict(version=VERSION,source=value['binding']['source'],epoch=value['binding']['epoch'],
        contract_sha256=pin(),limits={'max_plan_depth':1}),'DEPENDENCY_OPERATOR_SOURCE_DOMAIN')
    port=getattr(authority,'authenticate_dependency_certificate',None)
    require(callable(port) and port(deepcopy(value)) is True,'DEPENDENCY_INDEPENDENT_SOURCE_REQUIRED')
    return dict(passed=True,readback_sha256=digest(value['observation']),
        scope='AUTHENTIC_LOCAL_BYTES_AND_PUBLIC_CONDITIONAL_CONTRACT_NOT_WORLD_EFFECT')

def relation_index(observation):
    m=observation['manifest'];schema=observation['schema']
    require(set(m)=={'entry','profiles'} and 2<=len(m['profiles'])<=8 and m['entry'] in m['profiles'],'DEPENDENCY_MANIFEST_DOMAIN')
    require(schema['version']==VERSION and type(schema['goal']) is int and
        schema['setting_bounds']==[0,100] and schema['operation']=='gain*limit+offset','DEPENDENCY_PUBLIC_SCHEMA')
    require(observation['context']['cwd']==observation['context']['observed_root'] and
        observation['context']['entity_id'],'DEPENDENCY_SELF_ROOT_BINDING')
    index={}
    for name,row in m['profiles'].items():
        require(set(row)=={'config','gain','offset'} and type(row['gain']) is int and 1<=row['gain']<=16
            and type(row['offset']) is int and abs(row['offset'])<=100,'DEPENDENCY_AFFINE_DOMAIN')
        path=PurePosixPath(row['config'])
        require(not path.is_absolute() and '..' not in path.parts and len(path.parts)==1 and path.suffix=='.json'
            and row['config'] in observation['configs'],'DEPENDENCY_CONFIGURATION_SCOPE')
        require(set(observation['configs'][row['config']])=={'limit'} and
            type(observation['configs'][row['config']]['limit']) is int,'DEPENDENCY_CONFIG_DOMAIN')
        index[name]=dict(row,edge_id=digest({'profile':name,'definition':row}),definition_sha256=digest(row))
    return index

def prepare(value,history,binding,admitted,authority):
    verified=validate(value,authority)
    require(binding==value['binding'] and history==value['history'],'DEPENDENCY_STATE_HISTORY_FRAME_BINDING')
    require(history and history[-1]['source']==binding['source'] and history[-1]['epoch']==binding['epoch'],'DEPENDENCY_CURRENT_EPOCH')
    require(admitted and len({a['id'] for a in admitted})==len(admitted) and all(set(a)=={'id','payload','cost'} and
        type(a['cost']) is int and a['cost']>=0 for a in admitted),'ADMITTED_ACTION_DEFINITIONS')
    obs=value['observation']
    require(set(obs)=={'manifest','schema','configs','context','failure','file_hashes'},'DEPENDENCY_ALLOWED_RAW_INPUTS')
    require(set(obs['schema'])=={'version','goal','setting_bounds','operation'},'DEPENDENCY_NO_ANSWER_INPUT')
    require(obs['context']['entity_id']==binding['entity_id'] and obs['context']['situated_frame_hash'] and
        obs['file_hashes']['workload.py']==binding['epoch'],'DEPENDENCY_ENTITY_FRAME_EPOCH')
    index=relation_index(obs);memory=value['memory'];reused=[]
    # Reuse only source-revalidated edges, never an earlier decision or patch.
    if memory is not None:
        previous=relation_index(memory['observation'])
        if memory['observation']['context']['observed_root']==obs['context']['observed_root']:
            for name,row in list(index.items()):
                if name in previous and previous[name]['definition_sha256']==row['definition_sha256']:
                    index[name]=deepcopy(previous[name]);reused.append(row['edge_id'])
    active=index[obs['manifest']['entry']];goal=obs['schema']['goal'];predictions=[]
    for action in sorted(admitted,key=lambda a:(a['cost'],a['id'])):
        p=action['payload'];require(set(p)=={'op','path','field'} and p['op']=='SET_INTEGER' and p['field']=='limit'
            and p['path'] in obs['configs'],'DEPENDENCY_ADMITTED_PRIMITIVE')
        rows=[r for r in index.values() if r['config']==p['path']]
        require(len(rows)==1,'DEPENDENCY_UNAMBIGUOUS_CONFIG_RELATION')
        row=rows[0];needed=Fraction(goal-row['offset'],row['gain'])
        applicable=needed.denominator==1 and 0<=needed<=100
        success=applicable and row['config']==active['config']
        output=goal if success else obs['failure']['output']
        predictions.append(dict(status='KNOWN',continuation=[action['id']],outcomes=[[raw_id([output]),bool(success)]],
            derived_values={action['id']:int(needed)} if applicable else {},
            dependency_edge=row['edge_id'],active_edge=active['edge_id'],
            self_root_sha256=digest(obs['context']['cwd']),reused_edge_ids=sorted(reused),
            epistemic_scope='CONDITIONAL_PUBLIC_AFFINE_CONTRACT'))
    return dict(status='MAPPED_CANDIDATE_PREDICTIONS',domain=VERSION,predictions=predictions,
        certificate_sha256=value['certificate_sha256'],verification=verified,binding=deepcopy(binding),
        history_sha256=digest(history),history=deepcopy(history),definitions_sha256=digest(admitted),
        operating_context=deepcopy(obs['context']),relation_index=index,
        semantics='Source-bound bounded dependency relation; exact conditional integer consequence',authority_effect='NONE')

def instantiate(action,prediction):
    require(prediction['continuation']==[action['id']] and action['id'] in prediction['derived_values'],'DEPENDENCY_DERIVED_PARAMETERS_REQUIRED')
    value=prediction['derived_values'][action['id']]
    require(type(value) is int and 0<=value<=100,'DEPENDENCY_DERIVED_VALUE_DOMAIN')
    return {**deepcopy(action),'payload':{**deepcopy(action['payload']),'value':value}}

def augment(graph,prepared,canonical):
    mapper=canonical.mapper;E=canonical.E
    nodes=list(mapper.UniversalMap.model_validate_json(json.dumps(graph)).vertices);relations=list(mapper.UniversalMap.model_validate_json(json.dumps(graph)).relations)
    source=canonical.frames.create_source_observation(source_reference='dependency:'+prepared['certificate_sha256'],
        summary='Independent local manifest bytes; bounded development relation, not action authority.',epistemic_status=E.REPORTED,
        evidence_references=(prepared['verification']['readback_sha256'],))
    for name,row in sorted(prepared['relation_index'].items()):
        node=mapper.create_mapper_node(kind=mapper.NodeKind.THING,label='dependency:'+name,
            description=json.dumps(row,sort_keys=True),epistemic_status=E.INFERRED,source_observations=(source,))
        relations.append(mapper.create_mapper_relation(kind=mapper.RelationKind.RELATES_TO,label='profile-config-dependency',
            source_nodes=(nodes[0],),target_nodes=(node,),epistemic_status=E.INFERRED,source_observations=(source,)))
        nodes.append(node)
    return mapper.create_universal_map(vertices=nodes,relations=relations).model_dump(mode='json')
