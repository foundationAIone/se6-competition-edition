"""Source-pinned DEVELOPMENT method report and existing retrieval capability.

This report is independently recomputed aggregate evidence from exposed cases,
not held-out labels, owner authority, a verified World effect, or per-case rules.
The read contract is frozen source data; the actor cannot supply its own pin.
"""
from pathlib import Path
from fractions import Fraction
import hashlib,json
from .sessions_format import VERSION,canonicalbytes
from .format import require

LEGACY='legacy-token-overlap-v1'
BM25='official-flat-bm25-v1'
ROOT=Path(__file__).resolve().parent
SCOPE='CLEANED_S_COMPLETE_ALL_ROLE_SESSIONS_RECALL_AT_5_DEVELOPMENT_ONLY'

def source_files():
    return (Path(__file__),ROOT/'selection_read_contract.json',ROOT/'development_method_report.json',
        ROOT.parent/'research_controls/official_bm25_s.py')

def read_admitted_development_report():
    contract_path=ROOT/'selection_read_contract.json'
    require(not contract_path.is_symlink(),'METHOD_CONTRACT_LINK')
    contract=json.loads(contract_path.read_bytes())
    require(set(contract)=={'schema','report_file','report_sha256','scope'} and contract['schema']=='se6-development-method-read-contract-v1'
        and contract['report_file']=='development_method_report.json'
        and contract['scope']=='PROVISIONAL_REPORTED_NON_AUTHORIZING_TEXT_SESSION_METHOD_PREFERENCE','METHOD_READ_CONTRACT')
    path=ROOT/contract['report_file'];require(not path.is_symlink(),'METHOD_REPORT_LINK');raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==contract['report_sha256'],'METHOD_REPORT_PIN_MISMATCH')
    report=json.loads(raw)
    require(report.get('schema')=='se6-development-retrieval-method-report-v1' and report.get('scope')==SCOPE
        and report.get('representation_version')==VERSION and report.get('epistemic_status')=='REPORTED'
        and report.get('memory_status')=='PROVISIONAL' and report.get('authority_effect')=='NONE','METHOD_REPORT_SCOPE')
    require(report.get('allowed_methods')==[LEGACY,BM25],'METHOD_REPORT_ALLOWED_CAPABILITIES')
    for name in ('old_result_sha256','old_capture_sha256','old_source_manifest_sha256'):
        require(type(report.get(name)) is str and len(report[name])==64 and all(c in '0123456789abcdef' for c in report[name]),'METHOD_REPORT_SOURCE_PINS')
    aggregate=report['aggregate'];require(type(aggregate.get('cases')) is int and aggregate['cases']>0,'METHOD_REPORT_CASES')
    def fraction(name):
        value=aggregate[name];require(set(value)=={'numerator','denominator'} and type(value['numerator']) is int
            and type(value['denominator']) is int and value['denominator']>0 and 0<=value['numerator']<=value['denominator'],'METHOD_REPORT_METRIC')
        return Fraction(value['numerator'],value['denominator'])
    preferred=BM25 if fraction('bm25_recall_at_5')>fraction('legacy_recall_at_5') else LEGACY
    require(report.get('recommended_method')==preferred,'METHOD_REPORT_RECOMMENDATION')
    return report

def admitted_report_pin():
    # A source data pin, not caller-supplied authorization or secret trust key.
    read_admitted_development_report()
    return json.loads((ROOT/'selection_read_contract.json').read_bytes())['report_sha256']

def policy_material(report):
    return dict(schema='se6-retained-development-method-policy-v1',report_sha256=admitted_report_pin(),
        representation_version=VERSION,method=report['recommended_method'],scope=SCOPE,
        old_result_sha256=report['old_result_sha256'],old_capture_sha256=report['old_capture_sha256'],
        old_source_manifest_sha256=report['old_source_manifest_sha256'],authority_effect='NONE')

def bm25_candidates(question,corpus):
    """Call the SAME existing baseline capability; never copy saved outputs."""
    from research_controls.official_bm25_s import rank
    indices,scores=rank(question,corpus)
    return [(int(index),float(scores[int(index)])) for index in indices]
