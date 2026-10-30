"""Trusted metadata-only grouping/split. Gold is never an input to selection."""
from copy import deepcopy
from .protocol import VERSION,digest,require

FIELDS={'question_id','question_type','source_histories','environment_ids','modality_eligible','raw_data_sha256'}

def prepare_manifests(metadata,*,seed='se6-memory-pilot-20261028-v1',development_questions=4,
                      evaluation_questions=12,min_eval_clusters=3,max_per_cluster=4):
    require(type(metadata) is list and all(type(r) is dict and set(r)==FIELDS for r in metadata),'TRUSTED_METADATA_SCHEMA_NO_GOLD')
    require(len({r['question_id'] for r in metadata})==len(metadata),'QUESTION_ID_UNIQUE')
    require(all(type(r['modality_eligible']) is bool and r['source_histories']
        and all(type(v) is str and v for v in r['source_histories']+r['environment_ids']) for r in metadata),'HISTORY_IDENTITY_REQUIRED')
    # Group ALL metadata before eligibility/selection, so an excluded connector
    # cannot accidentally split two overlapping histories across dev/eval.
    parent=list(range(len(metadata)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def join(i,j):
        a,b=find(i),find(j)
        if a!=b:parent[b]=a
    keys={}
    for i,r in enumerate(metadata):
        for key in [('history',x) for x in r['source_histories']]+[('environment',x) for x in r['environment_ids']]:
            if key in keys:join(i,keys[key])
            else:keys[key]=i
    groups={}
    for i,r in enumerate(metadata):groups.setdefault(find(i),[]).append(r)
    components=[]
    for rows in groups.values():
        component=digest(dict(histories=sorted({v for r in rows for v in r['source_histories']}),
            environments=sorted({v for r in rows for v in r['environment_ids']})))
        eligible=[r for r in rows if r['modality_eligible']]
        if eligible:components.append((component,sorted(eligible,key=lambda r:digest([seed,r['question_id']]))))
    components.sort(key=lambda row:digest([seed,row[0]]))
    dev=[];evaluation=[];dev_groups=[];eval_groups=[]
    for group,rows in components:
        if len(dev)<development_questions:
            chosen=rows[:min(max_per_cluster,development_questions-len(dev))];dev.extend(chosen);dev_groups.append(group)
        elif len(evaluation)<evaluation_questions:
            chosen=rows[:min(max_per_cluster,evaluation_questions-len(evaluation))];evaluation.extend(chosen);eval_groups.append(group)
    blockers=[]
    if len(dev)<development_questions:blockers.append('INSUFFICIENT_DISJOINT_DEVELOPMENT_QUESTIONS')
    if len(evaluation)<evaluation_questions:blockers.append('INSUFFICIENT_DISJOINT_EVALUATION_QUESTIONS')
    if len(eval_groups)<min_eval_clusters:blockers.append('INSUFFICIENT_INDEPENDENT_EVALUATION_CLUSTERS')
    out=dict(schema=VERSION+'-trusted-manifests',status='PREPARED' if not blockers else 'BLOCKED',seed=seed,
        development={'questions':deepcopy(dev),'clusters':dev_groups},evaluation={'questions':deepcopy(evaluation),'clusters':eval_groups},
        blockers=blockers,independence_unit='OVERLAPPING_HISTORY_ENVIRONMENT_COMPONENT',
        source_metadata_sha256=digest(metadata),gold_inspected_for_selection=False,
        contestant_export='NONE: question IDs/types, source-group identities and selection internals remain trusted evaluator data.')
    return {**out,'manifest_sha256':digest(out)}
