# Frozen benchmark methodology

One ordinary problem is shared between assisted and independent lanes. The assisted
lane receives verified SE6 consequences; the baseline receives no SE6 output. Both
use Nebius-served NVIDIA Nemotron-3-Super with matched per-call completion limits and
the same public problem/format requirements. Each correction lane receives its own
previous answer, never the other lane's. Answer keys and scoring rules were excluded
from generation context; independent scoring followed capture and freezing.

Three successor pairs used six captured calls, maximum 1,024 completion tokens per
call, 6,144 total completion tokens, 49,152 combined original input bytes and a
$0.50 tariff cap, with no retries. Captures report 1,349 completion tokens and
28,902 input bytes, within the declared limits. They contain 8,510 prompt tokens
and 9,859 total tokens. The replay makes zero provider calls.

| Case | SE6 | Baseline | Scoped result |
|---|---:|---:|---|
| Earlier linear attempt | Unassessable | 0/3 | No winner |
| Successor initial linear | 3/3 | 3/3 | Tie |
| Successor corrected linear | 3/3 | 3/3 | Tie; both invalidated old proof references |
| Successor mixed business | 16/16 | 3/16 | SE6 advantage on this case |

The linear rubric checks the derived relation, proof shape/validity and premise
discipline. On correction it verifies that superseded references are invalidated
without retaining stale steps. The mixed rubric checks seven original and seven
corrected numeric/view fields plus investigate-spending=true and world-facts-verified=false.
Recommendation prose is unscored. Corrected materials were $271 against a $260 budget;
the independent answer's quantity allocations did not satisfy the stated hours.

These are narrow examples. Sixteen correlated checks are not sixteen trials. Both
mixed versions were present in one question. There is no general superiority,
intrinsic reasoning or longitudinal-memory claim. SE6 receives extra native work
and a larger context, so equality of total compute is not claimed.

Successor tariff estimates use the frozen $0.30/million input and $0.90/million
output rates: assisted $0.0025557, baseline $0.0012114, total $0.0037671. Assisted
prompt tokens were 6,668 versus 1,842; cost was about 2.11 times baseline. Actual
invoice cost is unknown. Three transport times totaled 6.409247 seconds assisted
and 6.821507 seconds baseline; native preparation took 11.488487 seconds, with
additional preflight and scoring work. Transport measurements do not establish
an end-to-end speed advantage. The earlier campaign estimate was $0.0008922.

The public sanitized captures and standard-library scorer reproduce arithmetic,
score shapes, own-lane history checks, usage and tariff calculations. Original IDs,
times, approvals, native journals and sensitive metadata are removed. Therefore this
public projection cannot authenticate original raw wire bytes, paid authorization,
private source execution or pre-capture answer-key isolation. Those checks were
performed privately against preserved originals; they are not claimed as a public
exact historical replay. Local provider captures are not provider-signed account logs.
