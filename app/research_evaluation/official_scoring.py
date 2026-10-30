"""Trusted evaluator-only bridge to pinned official deterministic/rubric code.

Never mount this module or official evaluator source in a contestant namespace.
No official provider client/transport is invoked: its ten-retry policy is not
the custom pilot's no-retry policy. Offline prompt checks are not judge validation.
"""
from pathlib import Path
import hashlib,importlib.util

DETERMINISTIC={'norm_phrase_set_match','norm_phrase_set_match_ordered','mc_choice_match','mc_choice_set_match'}
def require(ok,code):
    if not ok:raise ValueError(code)

class OfficialScoring:
    def __init__(self,path,expected_sha256):
        self.path=Path(path).resolve(strict=True)
        raw=self.path.read_bytes()
        require(len(raw)<=128*1024 and hashlib.sha256(raw).hexdigest()==expected_sha256,'OFFICIAL_EVALUATOR_SOURCE_PIN')
        spec=importlib.util.spec_from_file_location('_lmev2_pinned_trusted_metrics',self.path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.module=module;self.source_sha256=expected_sha256
    def deterministic(self,spec,prediction,reference):
        require(type(spec) is str and self.module.eval_name(spec) in DETERMINISTIC,'UNSUPPORTED_OR_MODEL_JUDGED_EVALUATOR')
        return self.module.score_to_bool(self.module.eval_from_spec(spec,prediction,reference))
    def judge_messages(self,kind,*,question,reference,response):
        require(kind in {'abstention','gotchas'},'OFFICIAL_JUDGE_RUBRIC_KIND')
        require(all(type(x) is str for x in (question,reference,response)),'JUDGE_TEXT_FIELDS')
        builder=getattr(self.module,'_build_'+kind+'_judge_messages')
        return builder(question_text=question,reference_answer=reference,model_full_response=response,
            model_final_answer=self.module.extract_boxed_answer(response))
    def parse_judge(self,response):
        return self.module._parse_llm_binary_judgement(response)
