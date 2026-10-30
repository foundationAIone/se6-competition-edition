# Model-assisted developer workflow — current scope

The existing Competition page now has a **read-only paired-pilot viewer**. It cannot call a model, submit a repair, approve a budget or grant authority. It reads `/api/model-workflow/evidence` through the existing authenticated judge session and exports only the displayed safe record. The coordinator owns the source-bound runner and all action/provider gates.

Until an exact new budget is approved and a real batch runs, the required status is:

`MODEL_COMPARISON: BLOCKED_PENDING_EXACT_BUDGET`

No scored projects, proposals, aggregate scores or advantages are displayed before committed responses are released. Unknown measurements stay UNKNOWN. Prepared source hashes, settings and limits are metadata, not model execution evidence. HTTP or schema failures become UNKNOWN and never cause dispatch or an automatic retry.

The planned pilot uses three independently generated projects, each with an initial failure and a cold continuation after a predeclared dependency/root change. Six stages per arm are related within three project sequences. The same NVIDIA/Nebius model, ordinary tools and own verified notes are compared with the same model plus actual SE6. The illustrated story is the lowest numeric project identifier, chosen before outcomes; the viewer retains all three projects, ties, failures, refusals and incomplete stages.

The model's proposed interpretation, inspection or repair must be causally consumed. Its output is untrusted. Native finite validation, Boundary, dispatch, independent consequence evidence and retained state are separate stages. If deterministic SE6 computation already solves the task, count and label that system computation. No artificial requirement for a model call, answer-bearing assistance or named stage alone establishes the intended role.

The earlier 172-second video, source47cc release and two-call answer-bearing provider capture remain immutable history. They do not establish this new unresolved-task comparison. A new version-two video is pending actual approved execution; see VIDEO_STORYBOARD_V2.md. New provider allowance is zero until separately authorized.

Focused offline UI checks:

```text
node --check hosted_judge/static/model-workflow.js
node docs/model-workflow/test_viewer.cjs
```

The latter uses explicitly synthetic UI records, not a provider, Native execution, World effect or scored evaluation.
