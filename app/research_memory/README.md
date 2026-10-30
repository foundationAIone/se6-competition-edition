# Reported historical text adapter

This development adapter uses the real `EntityStore`, `LocalEntityRuntime`,
`MemoryPayload.CANDIDATE`, `DevelopmentalAssimilationLoop`, and
`EntityMemoryState.active_at` contracts. It does not create a separate facts or
retrieval database. The sole retained knowledge is the actual Entity memory.

Insertion commits attributed text through the existing Becoming path as
`PROVISIONAL / REPORTED`, with `EXTERNAL_RETRIEVED` source events and exact
trajectory/chunk hashes. It never creates a `VerificationPayload`, Native World
witness, verified capability, owner approval, or production activation.

`Memory(root=..., context_char_budget=..., storage_byte_budget=...)` exposes:

- `insert(trajectory)`: typed text-only historical admission, idempotent by full
  source hash. Changed bytes under one source ID need an explicit lifecycle
  decision. Partial admission is unanswerable and is not automatically replayed.
- `query(question, query_image=None)`: a new, explicitly bounded lexical reader
  of the actual active Entity projection, returning official text-context items.
  The trace binds each consumed memory ID, source event, content hash, current
  Entity head, and final answer-context hash. Empty applicable evidence remains
  UNKNOWN. This is not a general Native semantic QA operator.
- `save(own_root / snapshot)`: a genuine SQLite backup plus a pinned checkpoint.
- `load(own_root / snapshot)`: actual audited Entity recovery in query-only mode.
  A snapshot older than the current root head cannot resurrect revoked memory.
- `mark_inactive(...)`: development-only use of existing revoke/stale/expiry
  transitions. Append-only historical bytes remain; the active answer context
  changes, and unrelated valid history remains usable.

The official wrapper is `official.register_with_official(actual_memory_module)`.
It uses the supplied official base and its registration/save/load hooks. That
registration has **not been executed** here: importing the unmodified official
module in the isolated environment currently requires missing `httpx`, followed
potentially by other backend dependencies. No substitute base is claimed.

`python -B -m research_memory.worker` accepts one host-constrained JSON request
with `root`, explicit budgets and operation `insert`, `query`, `save`, or `load`.
Query may include `path` to load a checkpoint before returning `context` and
`trace`. No evaluator question ID/type/gold is accepted by this interface.

## Scope and capacity

The supported source is an explicitly declared text-only development trajectory:
`id`, `goal`, `start_url`, `outcome`, `states`, optionally `domain` and
`environment`. Each state preserves typed URL/action/text or accessibility-tree
fields, optional step/thought fields, and an absent/empty screenshot. Nonempty
screenshots and image queries are refused; arbitrary `content`/metadata objects
are not flattened. No image is dropped or fetched.

Bounds are 512 KiB per source, 384 adapter records **across all histories**, and
512 initial event units. The existing core memory contract has a separate 2,048
record maximum. A 100-history official haystack is not established to fit.
Source-preserving JSON segments are split into at most 1,600-character chunks;
the exact chunks are shared with the control. The caller explicitly sets equal
context/storage limits for both arms. Storage checks stop on breach after an
atomic Entity commit, so a single-commit overshoot is possible and is not a
strict filesystem quota. SQLite checkpoint capacity is checked before copying.

The official first inspected development record is 1,344,890 bytes and contains
101 screenshot-bearing states. It is not admitted by this adapter. Text-only
sufficiency for actual LongMemEval-V2 questions is unestablished, so the real
benchmark remains blocked. The passing synthetic development tests are neither
an official score nor evidence of live-model reasoning or comparative advantage.

The global experiment source manifest must cover the full imported core and
environment. The adapter's five direct core pins are an extra local continuity
check, not a complete transitive source attestation.
