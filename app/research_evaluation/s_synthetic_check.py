"""One new-route synthetic development check; not an external case/score."""
from pathlib import Path
import argparse,json
from .s_public import sanitize_case
from .s_batch import write,file_sha,run_batch

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    sessions=[[dict(role='user',content='Keep this unrelated note.',has_answer=False),
        dict(role='assistant',content='An unrelated archive record.')] for _ in range(5)]
    good=[dict(role='user',content='I need a receipt location.',has_answer=False),
        dict(role='assistant',content='Marmalade receipts are kept in the amber cabinet.',HAS_ANSWER=True)]
    sessions += [good,good]
    raw=dict(question_id='SYNTHETIC_ONLY',question_type='single-session-assistant',answer='amber cabinet',
        question='Where are marmalade receipts kept?',question_date='2026-10-29',
        haystack_sessions=sessions,haystack_dates=['2025-01-01']*6+['2025-02-01'],
        haystack_session_ids=[str(i) for i in range(5)]+['answer_good','answer_good'],answer_session_ids=['answer_good'])
    public,private=sanitize_case(raw,dataset_sha256='a'*64,dataset_revision='SYNTHETIC_NO_DATASET')
    write(out/'public.json',public);write(out/'private.json',private)
    manifest=dict(cases=[dict(case_id='synthetic-route',partition='development',public_path=str(out/'public.json'),
        private_path=str(out/'private.json'),public_sha256=file_sha(out/'public.json'),private_sha256=file_sha(out/'private.json'))])
    write(out/'manifest.json',manifest)
    report=run_batch(out/'manifest.json',out/'actual','development',development_unfrozen=True)
    if any(v['failures'] or v['recall_at_5']!=1 for v in report['results']['arms'].values()):
        raise ValueError('SYNTHETIC_ROUTE_CONTRACT_FAILED')
    print(json.dumps(dict(status='SYNTHETIC_NEW_S_ROUTE_VERIFIED',external_cases=0,provider_calls=0)))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args();run(args.out)
