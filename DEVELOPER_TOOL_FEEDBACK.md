# Developer-tool feedback grounded in captured use

Private submission text; owner review required before posting.

Nebius Token Factory made it possible to use NVIDIA `nvidia/nemotron-3-super-120b-a12b` in an auditable tool/controller workflow with explicit model identity, bounded requests, raw responses, finish reasons and token accounting. In the completed 32-call developer pilot, the model inspected unresolved project evidence and proposed bounded configuration edits. The original evaluated outcomes were preserved, including premature finish claims in both conditions.

The most useful improvement would be an unambiguous per-deployment contract for reasoning controls, structured output and token budgeting. NVIDIA serving documentation does not by itself establish which optional controls a specific Nebius deployment accepts. In the later retrieval-answer batch, one response exhausted the 2,048-token output cap: 1,412 reasoning tokens were reported and the final answer was truncated. Raising a cap blindly would not resolve the underlying contract uncertainty. The project now distinguishes complete final answers, item-level incompletion and ambiguous global failures, saves all response bodies, and separates independently approved grading from reader execution.

Request IDs, model/version provenance, finish reasons and usage are valuable. An invoice-reconcilable per-request cost reference and clear cache/reasoning billing fields would improve exact budget and incident accounting. Published-tariff estimates are disclosed as estimates, not billed amounts. Missing usage is reserved conservatively rather than interpreted as free.

Agent outputs benefit from explicit completion semantics: a `finish` message is a claim, not proof of success. The SE6 application checks a fresh source/root/goal-bound command result before accepting completion. This is application engineering, not a criticism that all model claims fail.

Our small synthetic developer pilot tied on task success and SE6 was slower. Fresh retrieval also tied the BM25 baseline. These results motivate inspectability and honest controls; they do not justify comparative superiority or a broad model-quality conclusion.

