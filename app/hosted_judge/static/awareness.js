'use strict';
(() => {
  const byId = id => document.getElementById(id);
  if (!byId('configuration-awareness')) return;
  const make = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = typeof text === 'object' ? JSON.stringify(text, null, 2) : String(text);
    return node;
  };
  const value = item => item === null || item === undefined ? 'UNKNOWN — not measured or not supplied' : typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item);
  const STORAGE_KEY = 'se6-awareness-request-v1';
  const SCENARIO = 'dependency-self-v1';
  const ID = /^[0-9a-f]{32}$/;
  const TERMINAL = new Set(['COMPLETE', 'FAILED_CLOSED', 'INTERRUPTED']);
  const WAIT_MS = 180000;
  let judge = {ready: false, busy: false, pending: false};
  let working = false, unresolved = false, attempt = null, evidenceLoading = false, restoredAttempt = false, retired = false;

  function status(text, state = 'UNKNOWN') {
    byId('awareness-status').textContent = text;
    byId('awareness-status').dataset.status = state;
  }
  function controls() {
    byId('awareness-run').disabled = !judge.ready || judge.busy || judge.pending || working || !!attempt;
    byId('awareness-check').hidden = !attempt || retired;
    byId('awareness-check').disabled = !judge.ready || working || retired;
    byId('awareness-evidence-load').disabled = !judge.ready || evidenceLoading;
    byId('configuration-awareness').setAttribute('aria-busy', String(working));
  }
  function announce() {
    document.dispatchEvent(new CustomEvent('se6:awareness-busy', {detail: {busy: working || unresolved}}));
    controls();
  }
  function remember() {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(attempt)); } catch (_) {
      // The visible request ID still supports read-only reconciliation. Never
      // create another execution because browser storage is unavailable.
    }
  }
  function showRetired() {
    byId('awareness-mode').textContent = 'PREVIOUS ISOLATED SESSION · RETIRED';
    byId('awareness-export').hidden = true;
    byId('awareness-export').removeAttribute('href');
    byId('awareness-export').removeAttribute('download');
    status(`Request ${attempt.request_id} belongs to the previous isolated judge session, retired at ${attempt.retired_at_utc || 'UNKNOWN'}. Displayed evidence is preserved; export and reconciliation are unavailable under the replacement session. No execution was retried.`, 'RETIRED');
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', ...options, signal: controller.signal});
      let data;
      try { data = await response.json(); } catch (_) { throw new Error('The backend response was not valid JSON. The operation outcome is UNKNOWN.'); }
      if (!response.ok) throw new Error(data.error || data.reason || `HTTP ${response.status}; no execution was retried.`);
      return data;
    } finally { clearTimeout(timeout); }
  }
  function details(label, data) {
    const node = make('details');
    node.append(make('summary', label), make('pre', value(data)));
    return node;
  }
  function facts(items) {
    const list = make('dl');
    list.className = 'awareness-facts';
    for (const [label, content] of items) {
      const pair = make('div');
      pair.append(make('dt', label), make('dd', value(content)));
      list.append(pair);
    }
    return list;
  }
  function arm(label, data, conventional) {
    const box = make('article');
    box.className = `awareness-arm ${conventional ? 'awareness-conventional' : ''}`;
    const verification = data?.verification === 'INDEPENDENTLY_VERIFIED' ? 'INDEPENDENTLY VERIFIED' : value(data?.verification);
    box.append(make('h4', label), facts([
      ['Chosen action', data?.action], ['Actual goal', data?.goal],
      ['Independent consequence check', verification], ['Retention / cold continuation', data?.retention],
      ['Entity version', data?.entity_version], ['Native receipt', data?.native_receipt],
      ['Retained relationships', data?.retained_relationship_ids],
      ['Invalidated relationships', data?.invalidated_relationship_ids]
    ]));
    box.append(details('Exact action, evidence and local work', data));
    return box;
  }
  function render(result) {
    if (!attempt || result?.request_id !== attempt.request_id || result.scenario !== SCENARIO || result.mode !== 'LIVE_DISPOSABLE_DEVELOPMENT' || !['RUNNING', ...TERMINAL].includes(result.status)) {
      throw new Error('Saved result identity, execution mode or status did not match. Outcome UNKNOWN; no resubmission.');
    }
    byId('awareness-mode').textContent = restoredAttempt ? 'SAVED LOCAL REQUEST · NOT A NEW EXECUTION' : 'THIS SESSION · LOCAL DISPOSABLE RUN';
    byId('awareness-mode').dataset.mode = 'LIVE_DISPOSABLE_DEVELOPMENT';
    byId('awareness-result').hidden = false;
    const phases = Array.isArray(result.phases) ? result.phases : [];
    const summary = byId('awareness-summary');
    const heading = result.status === 'COMPLETE' ? 'Local comparison finished' : result.status === 'RUNNING' ? 'Local comparison in progress' : 'Execution stopped without a success claim';
    summary.replaceChildren(make('h3', heading), make('p', `Request ${attempt.request_id} · ${result.status}`));
    if (phases.length) {
      const verified = key => phases.filter(p => p.arms?.[key]?.goal === true && p.arms?.[key]?.verification === 'INDEPENDENTLY_VERIFIED').length;
      summary.append(make('p', `Independently verified goals: SE6 ${verified('se6')}/${phases.length}; conventional control ${verified('conventional')}/${phases.length}.`));
    }
    summary.append(make('p', result.comparative_result === 'NOT_ESTABLISHED' ? 'MEASURED ADVANTAGE: NOT ESTABLISHED. Ties and additional SE6 work remain part of the evidence.' : `Comparative result: ${value(result.comparative_result)}. This bounded development run is not a general-intelligence or full-equation claim.`));
    const phaseBox = byId('awareness-phases');
    phaseBox.replaceChildren();
    for (const phase of phases.slice(0, 8)) {
      const section = make('section');
      section.className = 'awareness-phase';
      section.append(make('h3', `Phase ${value(phase.phase)} · ${value(phase.label)}`), facts([
        ['Observed dependency relationship', phase.relationship], ['SELF / working-root context', phase.context]
      ]));
      const columns = make('div');
      columns.className = 'awareness-columns';
      columns.append(arm('SE6 · retained relational route', phase.arms?.se6, false), arm('Conventional resolver · matched control', phase.arms?.conventional, true));
      section.append(columns);
      phaseBox.append(section);
    }
    const resource = result.resources || {};
    byId('awareness-provenance').replaceChildren(facts([
      ['Provider calls', resource.provider_calls], ['External network calls', resource.network_calls],
      ['Worker CPU seconds', resource.worker_cpu_seconds], ['Worker wall seconds', resource.worker_wall_seconds],
      ['Peak traced Python bytes', resource.peak_traced_python_bytes], ['Child CPU seconds', resource.child_cpu_seconds],
      ['Monetary cost', resource.monetary_cost]
    ]), details('Executed source hashes', result.source_hashes), details('Complete saved result', result));
    byId('awareness-export').href = '/api/awareness/export/' + attempt.request_id;
    byId('awareness-export').setAttribute('download', `se6-awareness-${attempt.request_id}.json`);
    byId('awareness-export').hidden = false;
    return result;
  }
  async function waitForResult(initial) {
    let result = render(initial);
    const started = Date.now();
    while (result.status === 'RUNNING') {
      status(`RUNNING · ${attempt.request_id}. Reading saved status only; no execution or model call is being resubmitted.`, 'RUNNING');
      if (Date.now() - started >= WAIT_MS) throw new Error('The bounded status wait ended. Outcome UNKNOWN; use CHECK SAVED RESULT. No new execution is permitted from this page.');
      await new Promise(resolve => setTimeout(resolve, 1000));
      result = render(await request('/api/awareness/result/' + attempt.request_id));
    }
    unresolved = false;
    status(`${result.status} · ${attempt.request_id}. Saved evidence is available. No automatic retry occurred.`, result.status);
    byId('awareness-run').textContent = 'COMPARISON SAVED · NO REPEAT';
  }
  byId('awareness-run').addEventListener('click', async () => {
    if (byId('awareness-run').disabled || attempt) return;
    working = true;
    announce();
    try {
      // Reuse the existing authenticated judge session only after the main
      // application completed initialization. This never renews paid authority.
      const session = await request('/api/session');
      if (typeof session.csrf_token !== 'string' || !session.csrf_token) throw new Error('Authenticated judge CSRF binding is unavailable. Nothing was dispatched.');
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      attempt = {request_id: [...bytes].map(b => b.toString(16).padStart(2, '0')).join(''), scenario: SCENARIO};
      remember();
      unresolved = true;
      announce();
      status(`Submitting one bounded local comparison · ${attempt.request_id}. Provider budget: zero.`, 'RUNNING');
      const result = await request('/api/awareness/run', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Judge-CSRF': session.csrf_token}, body: JSON.stringify(attempt)});
      await waitForResult(result);
    } catch (error) {
      status(`${attempt ? 'OUTCOME UNKNOWN. ' : 'NOT DISPATCHED. '}${error.name === 'AbortError' ? 'Request timed out.' : error.message}${attempt ? ` Request ${attempt.request_id}. Read saved status only; do not resubmit.` : ''}`, 'UNKNOWN');
    } finally {
      working = false;
      announce();
    }
  });
  byId('awareness-check').addEventListener('click', async () => {
    if (!attempt || working || !judge.ready || retired) return;
    working = true;
    announce();
    try { await waitForResult(await request('/api/awareness/result/' + attempt.request_id)); }
    catch (error) { status(`${error.name === 'AbortError' ? 'Read timed out.' : error.message} Outcome UNKNOWN; no operation was retried. Request ${attempt.request_id}.`, 'UNKNOWN'); }
    finally { working = false; announce(); }
  });
  byId('awareness-evidence-load').addEventListener('click', async () => {
    if (!judge.ready || evidenceLoading) return;
    evidenceLoading = true;
    controls();
    try {
      const payload = await request('/api/awareness/evidence');
      const recorded = payload.awareness || payload;
      const model = payload.model_integration;
      if (recorded.status !== 'RECORDED_VERIFIED' || recorded.mode !== 'FROZEN_HISTORICAL_EVIDENCE') throw new Error('The frozen record was not verified by the evidence reader.');
      const result = recorded.result || {};
      const box = byId('awareness-evidence');
      box.replaceChildren(make('h3', 'FROZEN HISTORICAL EVIDENCE · not a current execution'), facts([
        ['Retained SE6', `${value(result.retained)} / ${value(result.total_per_arm)}`],
        ['Narrow memory ablation', `${value(result.memory_ablated)} / ${value(result.total_per_arm)}`],
        ['Conventional resolver', `${value(result.conventional)} / ${value(result.total_per_arm)}`],
        ['Comparative result', result.comparative_result], ['Original archive SHA-256', recorded.archive_sha256]
      ]), make('p', 'The preserved awareness result is a tie. It does not establish a measured SE6 advantage.'), details('Frozen scope, limitations and provenance', recorded));
      if (model) {
        const estimate = typeof model.combined_tariff_estimate_usd === 'number' && Number.isFinite(model.combined_tariff_estimate_usd) && model.combined_tariff_estimate_usd >= 0 ? '$' + String(model.combined_tariff_estimate_usd) : 'UNKNOWN';
        box.append(make('h3', 'Recorded NVIDIA/Nebius integration · two historical calls'),
          make('p', `Combined tariff ESTIMATE: ${estimate}. Actual invoice: UNKNOWN. Its SE6 context included the answer, so this is integration evidence and does not establish independent reasoning superiority. No new provider request is made by this viewer.`),
          details('Actual recorded model verification', model));
      } else box.append(make('p', 'Recorded model-integration evidence was not supplied. No new model execution or cost is claimed.'));
      byId('awareness-evidence-status').textContent = 'RECORDED_VERIFIED · authentic frozen evidence reader · no new execution';
    } catch (error) { byId('awareness-evidence-status').textContent = 'Evidence unavailable or UNKNOWN: ' + error.message; }
    finally { evidenceLoading = false; controls(); }
  });
  document.addEventListener('se6:judge-state', event => {
    judge = {ready: event.detail?.ready === true, busy: event.detail?.busy === true, pending: event.detail?.pending === true};
    controls();
  });
  document.addEventListener('se6:judge-reset', () => {
    if (!attempt) return;
    retired = true;
    unresolved = false;
    attempt.retired = true;
    attempt.retired_at_utc = new Date().toISOString();
    remember();
    showRetired();
    announce();
  });
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    if (saved && ID.test(saved.request_id) && saved.scenario === SCENARIO) {
      attempt = {request_id: saved.request_id, scenario: SCENARIO};
      restoredAttempt = true;
      retired = saved.retired === true;
      unresolved = !retired;
      if (retired) {
        attempt.retired = true;
        attempt.retired_at_utc = typeof saved.retired_at_utc === 'string' ? saved.retired_at_utc : 'UNKNOWN';
        showRetired();
      } else status(`Saved request ${attempt.request_id} found. Outcome UNKNOWN until read-only reconciliation; no new execution will be submitted.`, 'UNKNOWN');
    }
  } catch (_) { /* Storage availability is not execution authority. */ }
  controls();
  document.dispatchEvent(new Event('se6:judge-state-request'));
  announce();
})();
