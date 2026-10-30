# Installation and reproducible release verification

Use the README's clean-directory Windows instructions. All five runtime dependencies and all six test dependencies are version-pinned; the supplied Windows CPython 3.14 wheel pack and lock file additionally pin every wheel SHA-256. No dependency reads a private research module. Essential Native source is included and separately hash-admitted by `native-manifest.json` before worker imports.

Run the focused clean-start acceptance with:

```text
python -B tools/release_acceptance.py --evidence ../acceptance-new
```

The evidence directory must not already exist. This starts only its own loopback child, verifies the actual page/assets, runs the business problem, stops that child, starts a fresh process using the same disposable store, verifies retained session state, applies the correction, checks artifact/receipt ancestry, and shuts down. It never accesses production or invokes a provider. Private evidence contains session/state details; do not publish it. Use the separately prepared sanitized summary.

The existing `tools/verify_offline.py` remains available for maintainers. Do not rerun its full historical 560-test suite merely to repackage unchanged runtime code. Historical accepted source99 Linux results: 95 focused and 560 full, four actual HTTP jobs, eight artifacts. This candidate's source-bound clean start and necessary regressions are reported separately.

For a local browser demo use `tools/run_dashboard.py --port 0 --store ../runtime`. The store must remain outside source. Stop only the owned local process with Ctrl+C; do not use production ports 8766/8777. Model calls are off by default even when credentials exist.

Hosted setup remains the existing nonroot Docker/Render configuration with exact HTTPS PUBLIC_ORIGIN, private persistent disk, origin/CSRF guards and anonymous inference disabled. A local passing test is not public HTTPS acceptance. Account, host, budget, exact publication manifest and separately approved deployment are still required.
