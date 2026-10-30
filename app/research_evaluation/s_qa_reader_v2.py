"""Non-authorizing concise reader profile and item policy; no new reader batch.

The old source/profile remains unchanged. No unverified vendor reasoning keys
are emitted. This profile is prepared/tested, not demonstrated by new inference.
"""
import hashlib,json
from .s_qa import reader_messages
from .s_qa_gateway import model_parts

CONCISE_SYSTEM='''Answer the specific question directly from the supplied historical conversations and dates.
Give the final answer in at most 120 words. Use up to three brief bullets only if needed.
Avoid introductions, tables, repeated context or lengthy recipes. Do not describe your reasoning.
If the evidence is insufficient, say so concisely. The word limit is an instruction,
not a guaranteed provider control. No tools or external information are available.'''

def prepare_reader_v2(public,retrieval):
    messages,trace=reader_messages(public,retrieval)
    messages[0]={'role':'system','content':CONCISE_SYSTEM}
    settings,router=model_parts('reader')
    wire=router.payload_bytes(settings,{'input':messages})
    if len(wire)>24576:raise ValueError('READER_V2_WIRE_CAP')
    return dict(messages=messages,wire_sha256=hashlib.sha256(wire).hexdigest(),wire_bytes=len(wire),
        trace=trace,model=settings.model,temperature=0,max_total_completion_tokens=2048,
        reasoning_control='UNKNOWN_ON_EXACT_NEBIUS_ENDPOINT; no enable_thinking/reasoning_budget/NIM extension emitted',
        final_token_reservation='UNKNOWN_NOT_GUARANTEED',provider_calls=0,authorizing=False,
        proposal='NONE: only saved-output grader recovery is recommended in this mission.')
