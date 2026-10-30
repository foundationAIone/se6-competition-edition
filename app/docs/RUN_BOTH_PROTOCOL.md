# V8 server-only matched-pair coordinator

Copy only `v8_run_both.py`, `v8_scoring.py` and the focused test file. Do not copy test-tmp directories, private allowances or runtime archives into a release. No import triggers inference. No live approval is supplied by this implementation.

## Interface

Instantiate `RunBothCoordinator(storage_root, approval_path=None, approval_sha256=None, live_enabled=False, credential_probe=None)` in the trusted server. The storage root must be private, durable, outside the packaged source tree, and inaccessible to HTTP clients. Load existing `src.workbench` dependencies from the reviewed private-native snapshot in a fresh owned process.

Call `status()` for the public safe configuration state. It reads neither credentials nor allowance. Call `prepare(question, native_context, public_history, own_histories)` server-side to generate the exact prospective packet before seeking approval; it uses no credential or provider. Approval must bind that packet, source contract and resolved claim store. Browser input cannot create an allowance.

Call `run(task_id, request_id, question, native_context, native_metrics, public_history)` with trusted 32-hex session/request IDs. Native context is only sanitized public answer and public proof scope, never checkpoints, raw task identities, internal prompts, private receipts or credentials. Metrics must use the module's numeric allowlist. The server supplies complete public question history; the coordinator supplies each lane's own durable assistant history. Browser-provided lane history is never an authority.

Return only `result['public']` over HTTP. `result['attestation']`, prepared packets, private allowance, raw archives and absolute runtime paths remain private. Map Blocked/Pending to generic public states without exception details. Serve asynchronous jobs and recovery via the lead-owned API. Run the pair in an owned child with a hard 75-second deadline; the urllib socket timeout alone does not impose a total deadline. A killed/incomplete reservation stays spent and unresolved; never retry, delete claims, refund reservations or steal stale locks.

## Explicit approval

The exact `se6-v8-one-pair-allowance-v1` schema is enforced in `allowance()`: one fresh permit/campaign, approved ONE_MATCHED_NEMOTRON_PAIR, an aware UTC expiry, one question hash, packet hash, exact fixed model/source contract, resolved LIVE claim-store hash, max_pairs=1, max_calls=2, max_output_tokens=1024, combined max_input_bytes=49152, exact dated tariff, and decimal dollar cap. Known exhausted campaign IDs are refused. The allowance file SHA is independently pinned in server configuration. Copying that allowance to another storage root fails its store binding. Trusted operator tampering/deleting the original claim store is outside this local integrity boundary; preserve claims and ACLs.

Settings are Nemotron `nvidia/nemotron-3-super-120b-a12b`, temperature 0, output limit 1024 per lane. Conservative tariff cap is $0.1591296 using two full 262144-token context bounds plus two 1024-token outputs; maximum allowed approval cap is $0.20. This is an existing dated official-source estimate, not an invoice. The quote is valid only on its verified UTC date, 2026-10-10, and fails closed after UTC rollover. Refreshing prices requires a new reviewed source/packet/approval, never silent renewal.

Both call reservations are permanently consumed before dispatch. A failed first response, missing/anomalous usage, model mismatch, timeout or exception stops the second call. Successful pairs freeze raw requests/responses and measurements before independent scoring. Credential probe failure precedes reservations and reveals no exception text. No retries are implemented.

## Fairness and scoring

Both lanes receive identical public contract, full public inputs and only their own prior assistant replies, with identical model settings and no tools. Only SE6 receives sanitized native context. This measures native-context assistance, not equal total computation. Native CPU/wall work and provider latency/cost are reported separately; local monetary cost and actual invoices may be unknown.

The independent stdlib scorer uses public equations/business facts and explicit public corrections, not native answer/parser/key imports. Derived public truth is archived before dispatch and withheld from providers. Exact rational certificates and supported business fields are scored separately. Unsupported prose, contradictory unannounced premises, malformed JSON/schema, or absent automatic truth are UNASSESSABLE. An arithmetic tie/winner is narrowly scoped; overall_winner is always null. Correction certificates are algebraic conditional evidence, not independent world verification.

Injected test transports must declare SIMULATED=True and use a separate namespace. Their public actual provider calls/cost are zero, hypothetical usage is clearly labelled, and simulated arithmetic winners are suppressed. They prove guard/serialization/scoring behavior, not provider readiness or model performance.

Replay reconstructs messages from public inputs and own histories, rechecks raw wire/response model, packet/source/store approval bindings, full archive hashes, derived truth, score, usage, cost and next history. File hashes prove captured local byte integrity, not authenticated remote origin or compiled in-memory execution. Source hashes are current disk observations; the trusted launcher must use the reviewed frozen snapshot and fresh process. The server-owned mutable history cache and claim store require private ACLs. No browser can choose these paths or mutate histories.

Durable private preflight/completion sidecars now cover compiled private src and separately observed hosted file hashes. They link exact frozen manifests without changing them. Retrieval sidecars are explicitly tagged CACHED_RETRIEVAL and never substitute for original dispatch provenance. HTTP session/native state is RAM-scoped; archive recovery does not imply browser-session recovery after restart. The candidate field and additional audit costs are included in native whole-worker wall/CPU and separately scoped in public output; they add no model tools or truth authority.
