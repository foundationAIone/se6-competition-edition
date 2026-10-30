# SE6 Reference Continuity v0.1.0

## The implemented advancement

This package adds a persistent, bounded Entity reference that can retain a
world-object relationship in the original supplied SE Core, change task and
interface, convert a new declared coordinate frame, and consume the old Native
relationship when selecting a later action. A fresh process reconstructs the
same state from the journal before every operation. Actual local file effects
are read separately and checked before renewal.

The original operational `ResearchEntityBinding` is deliberately tied to one
`core_task_id`; its Native identity is `competition-task:<task>`. Its `typed_frame`
recreates a genesis X and Theta representation. This extension gives a new
development Entity its own stable `reference-entity:<entity>` Native identity
and attaches multiple task IDs to it. It carries canonical X ancestry and an
explicit host record linking successive X/Theta pairs.

This is complete runnable development code. It does not require an external
discovery proof to run. It does not modify the original binding or reinterpret
its already admitted receipts.

## Scope and acceptance

The targeted existing requirement is `presence-general-reference`:

> A coherent Entity center/frame and meaningful self-world relationships persist
> beyond task-specific finite schemas and per-sequence identity.

The new behavior addresses one concrete prerequisite of that requirement:
persistent spatial reference and causally used Native memory across different
tasks and declared schemas. It demonstrates a bounded family of length-coordinate
interfaces. It does not establish unrestricted general presence or an Alpha PASS.

The supplied immutable Alpha snapshot remains 75.833333%, 6/12 mandatory gates,
`NOT_VERIFIED`. This package never reads or writes the live Alpha scoreboard,
claims an admission, changes a weight, or submits a scored cohort.

| Area | Result this package can establish |
|---|---|
| Persistent Native reference | One Entity-owned journal survives distinct task identities and cold processes. |
| Meaningful frame conversion | Declared shifted, rotated and scaled coordinates map through exact rational arithmetic. |
| Causal retained use | Native RECALL returns target values consumed in action selection; a changed target changes the action. |
| Consequence and renewal | Independent local reads of actual before/after file bytes verify the selected move before retaining its successor. |
| Canonical representations | Actual supplied X, Theta and BoundedMapping constructors and validators are executed without source changes. |
| Unfamiliar semantic discovery | Not claimed; the host supplies the coordinate meaning and JSON pointers. |
| Outside-grammar discovery | Not implemented or claimed by this package. |
| Complete equation fidelity | Not claimed; the supplied contracts remain shadow-only and the optimizer is a bounded spatial policy. |
| Complete resource usefulness | Not claimed; there is no matched utility comparison or complete billing/energy/engineering accounting. |

## What the three-task run does

The development host creates real owned JSON files and publishes separately
pinned, immutable local grants. Each engine request runs in a new Python process.
The engine sees the declared schema and permitted actions; the host's local
world update is implemented independently of the engine's prediction code.

1. Task A uses a nested meter schema. It observes `self` at `[0,0]` and a
   destination at `[4,0]`, retains both through actual Native assertions, and
   selects a move to `[1,0]`.
2. Task B uses a different nested centimeter schema with a shifted, rotated
   coordinate frame. Its current grant supplies only the new self observation.
   The destination source is excluded. Native recall of the retained destination
   drives the next selected move to `[2,0]`.
3. Task C uses millimeters, a different origin/orientation, and field names
   generated after the runtime source files have been hashed. Their coordinate
   meanings are explicitly declared; they are not autonomously discovered.
   Again, the destination is not supplied. The chosen move reaches `[4,0]`.
4. Each actual local move is separately read, verified and renewed. The target's
   original claim ID remains unchanged. Only the final task reaches the final
   destination; squared remaining distances are 9, 4 and 0.
5. A final representation expansion changes Theta while preserving exactly the
   same X, as required by the existing canonical expansion function.

Expected complete demonstration: 3 distinct tasks and roles, 14 fresh engine
processes, 13 committed Native actions, 3 reserved local moves and 3 verified
local renewals. Native journal inspection replays recorded consequences and does
not invoke the live Native executor again.

## Mathematical connection

For a declared task frame k, the exact conversion is:

    p_base = M_k * p_local + origin_k
    delta_base = M_k * delta_local
    predicted_next_base = current_base + delta_base

The matrix includes the declared scale and axis transformation. It must be
nonsingular; dimensions are limited to one, two or three. Coordinate origin is
never added to a displacement vector. All decision arithmetic uses bounded
`Fraction` values. Floating-point fields in the existing mapper are explanatory
projections and never determine the selected action.

The finite action policy minimizes squared distance to the Native-recalled
target, then public action cost, then identifier. It does not claim to implement
every cost/risk/irreversibility term in the full Symbolic Equation.

The supplied canonical `advance_realization_state` preserves prior X observations.
The supplied `expand_realization_frame` preserves the exact same X. When X
changes, this package creates the frame for the new X and stores a separate
`frame_link` with exact old/new X and Theta hashes. It does not change the
upstream meaning of GENESIS or EXPANSION.

## Files

| File | Purpose |
|---|---|
| `se6_reference/engine.py` | Entity/task attachments, retained claims, Native-driven planning, consequence verification and renewal. |
| `se6_reference/storage.py` | Write-once event journal, separately pinned local grants, full replay, expected-head checks and unresolved-write blocking. |
| `se6_reference/canonical.py` | Source-bound loading, original Core execution/replay, and actual canonical state/frame/map projection. |
| `se6_reference/geometry.py` | Exact affine transformations and generic declared JSON-pointer observation binding. |
| `se6_reference/demo.py` | Separate local host, action executor, immutable source files, fresh child processes and evidence report. |
| `tests/` | Focused behavioral and failure regressions, including changed-target and missing-target interventions. |
| `vendor/` | Eight byte-for-byte supplied canonical source files plus one local empty package initializer. |
| `SOURCE_PINS.json` | Hashes of the eight unchanged supplied source files. |
| `PACKAGE_MANIFEST.json` | Hashes of the complete reviewed package payload. |
| `setup_and_run.py` | Dependency check, local verification, one demonstration and result ZIP. |
| `CANONICAL_HANDOFF.md` | Exact integration scope and acceptance obligations for the designated canonical writer. |

## Windows: one local command after download

Download the ZIP and accompanying `SE6_Run_Reference.cmd` into Downloads. Run:

```powershell
cmd /c "$env:USERPROFILE\Downloads\SE6_Run_Reference.cmd"
```

The launcher verifies the ZIP hash, extracts it into a new isolated directory
beneath the existing mission's `work` directory, and uses
`C:\Users\weare\se6triad\.venv\Scripts\python.exe` when present. It can otherwise
use `py -3.11` if Python 3.11 and Pydantic 2 are already installed.

No packages are downloaded. The package runs ordinary local Python and does not
start a VS Code agent or contact a model provider. Creation of this package in
ChatGPT still has usage; this package cannot measure or refund that usage.

Successful output ends with a path to `SE6_REFERENCE_RESULT.zip`. That ZIP contains
the exact local test output, three-task report, grants, raw file observations,
and event journal. Re-running the launcher after a completed run reports the
existing result instead of starting another demonstration. An interrupted or
failed attempt is preserved and is not automatically retried.

## Direct developer commands

Python 3.11 or later and Pydantic 2 are required by the supplied canonical source.
All other dependencies are from the standard library.

```text
python -m unittest discover -s tests -v
python run_reference.py demo --out <new-owned-output-directory>
python run_reference.py inspect --store <entity-store> --expected-head <host-pinned-head>
```

`apply` accepts a request file, a separate grant path/hash and an owned store.
The demonstration writes complete working examples for every operation. They
are local development grants and must never be relabeled as canonical admission.

## Trust, persistence and practical limits

- The development host is trusted to issue the current grant and its out-of-band
  checksum. Checksums authenticate bytes relative to that host; they are not
  signatures and cannot authenticate a malicious host.
- Source files are read through the grant allowlist, using actual bytes and
  rejecting path escape, symlinks and changed contents. Historical source files
  and grants must remain available for full cold replay.
- Each request binds Entity, task, operation, permissions, source pins, logical
  time and the exact predecessor head. Observation data never supplies authority.
- All Native and local-action limits belong to the persistent Entity. Reattaching
  a task does not reset its own allowance or the global counters. Planning
  reserves capacity for the mandatory renewal as well as its own recalls.
- Conflicting same-version observations block current use. A correction must bind
  the exact previous claim and postdate all retained conflicting evidence.
- A mismatching or missing consequence leaves the move pending. This version
  deliberately provides no automatic recovery, repeated dispatch or fabricated
  renewal for that situation; reconciliation is a future versioned operation.
- The maximums are 20 committed Native actions, 20 reserved local moves, 64
  reference events, 16 task attachments, 16 objects and 64 claim-history entries.
  Smaller limits can be set at reference creation. Work done during validation
  and replay still consumes computation and is included in measured process CPU.
- This is a trusted local executable with command-line network/child/write
  restrictions as defense in depth. It is not an OS sandbox for hostile code.
- Canonical representation flags remain `shadow_only=True`,
  `production_authoritative=False`, `authority_effect="NONE"`.
- No production IdentityState is migrated or activated. The original task-bound
  Native journals are not renamed or overwritten.
- The measured CPU and wall time are local runtime measurements. RAM, energy,
  provider billing, historical engineering cost, and ChatGPT/Codex usage are not
  fully measured. No efficiency advantage or credit-free development is claimed.

## Supplied source basis

The original inputs were the two owner-supplied exports:

- `SE6_Canonical_Boundary_9b71fe52ec0e45e4883597caf0607ee5.zip`
- `SE6_Runtime_Sources_e0fe80b1de2540ed920002b3040a3040.zip`

The specific gap is visible in the exported
`learner-integration/entity-continuity/entity_binding_v2.py`, in its task-bound
constructor, `typed_frame`, and `frame_transition`. The reused definitions are
in `se_core/kernel.py`, `se666_core/realization_frame.py` and
`se666_core/universal_mapper.py`. The frozen requirement and unchanged acceptance
state come from snapshot `alpha-progress-000003`, criteria and ledger supplied
in the boundary export.
