'use strict';
(() => {
  const byId = id => document.getElementById(id);
  if (!byId('agent-realization')) return;
  const ENDPOINT = '/api/agent-realization/evidence';
  let ready = false, loading = false;
  const node = (tag, value) => {
    const item = document.createElement(tag);
    if (value !== undefined) item.textContent = value === null ? 'UNKNOWN — not measured' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
    return item;
  };
  function line(parent, label, value) {
    const row = node('p'); row.append(node('strong', `${label}: `), node('span', value)); parent.append(row);
  }
  function detail(parent, label, value) {
    const item = node('details'); item.append(node('summary', label), node('pre', value)); parent.append(item);
  }
  function controls() {
    byId('agent-realization-read').disabled = !ready || loading;
    byId('agent-realization').setAttribute('aria-busy', String(loading));
  }
  function clear() {
    for (const id of ['agent-realization-summary', 'agent-realization-conditions', 'agent-realization-provenance']) byId(id).replaceChildren();
  }
  function render(value) {
    if (value?.schema !== 'se6-agent-realization-development-view-v1' || value.status !== 'VERIFIED_DEVELOPMENT_CONNECTION' ||
      value.record_kind !== 'ACTUAL_DISPOSABLE_DEVELOPMENT_NO_MODEL' || value.provider_calls !== 0 ||
      value.production_connected !== false || value.alpha_changed !== false || !Array.isArray(value.conditions) || value.conditions.length !== 2) {
      throw new Error('Unsupported development evidence scope');
    }
    clear();
    byId('agent-realization-status').textContent = 'VERIFIED DEVELOPMENT CONNECTION · SAVED RECORD · READ ONLY';
    const summary = byId('agent-realization-summary'), provenance = byId('agent-realization-provenance');
    line(summary, 'Record', value.record_kind);
    line(summary, 'New provider calls / production connection / Alpha change', '0 / NONE / NONE');
    line(summary, 'Scope', 'Two conditions of the same Native implementation, two phases each. This is a bounded mechanism demonstration, not a new model benchmark or general agent nursery.');
    detail(summary, 'Shared completion repair — equally available to the conventional arm', value.completion_repair);
    for (const condition of value.conditions) {
      if (!['retained-bridge', 'bridge-disabled'].includes(condition.name) || !Array.isArray(condition.phases) || condition.phases.length !== 2) throw new Error('Invalid Native development condition');
      const phases = [...condition.phases].sort((a, b) => a.phase - b.phase), card = node('article');
      card.className = 'model-workflow-project';
      card.append(node('h3', condition.name === 'retained-bridge' ? 'Verified applicability bridge enabled' : 'Applicability bridge disabled · same Native implementation'));
      line(card, 'Actual configured and grounded candidate counts', phases.map(p => p.candidate_count).join(' → '));
      const table = node('table'); table.className = 'benchmark-table';
      const head = node('thead'), heading = node('tr');
      for (const label of ['Phase', 'Process PID', 'Goal / public target', 'Effects', 'Candidates', 'Verified memory used', 'Cold restore', 'Entity version']) heading.append(node('th', label));
      head.append(heading); table.append(head); const body = node('tbody');
      for (const phase of phases) {
        const row = node('tr');
        for (const item of [phase.phase, phase.pid, `${phase.goal ? 'PASS' : 'NOT VERIFIED'} / ${phase.public_goal}`, phase.actual_effects,
          phase.candidate_count, phase.memory_consumed ? 'YES' : 'NO', phase.cold_restored ? 'YES' : 'NO', phase.entity_version]) row.append(node('td', item));
        body.append(row);
        detail(card, `Phase ${phase.phase}: actual configuration, witness, receipt and measured local costs`, {
          agent_implementation: phase.agent_implementation, configuration_mode: phase.configuration_mode,
          capability_status: phase.capability_status, configured_candidates: phase.configured_candidates,
          verified_memory_id: phase.verified_memory_id, entity_receipt_id: phase.entity_receipt_id,
          native_receipt_hash: phase.native_receipt_hash, witness_sha256: phase.witness_sha256,
          retained_state_sha256: phase.retained_state_sha256, worker_wall_seconds: phase.worker_wall_seconds,
          worker_cpu_seconds: phase.worker_cpu_seconds, peak_traced_python_bytes: phase.peak_traced_python_bytes,
          total_child_cpu: 'UNKNOWN unless supplied in the independently reviewed record'
        });
      }
      table.append(body); const scroll = node('div'); scroll.className = 'benchmark-scroll'; scroll.append(table);
      card.insertBefore(scroll, card.querySelector('details')); byId('agent-realization-conditions').append(card);
    }
    line(provenance, 'Executing source manifest SHA-256', value.source_manifest_sha256);
    line(provenance, 'Raw result SHA-256', value.raw_result_sha256);
    line(provenance, 'Independent review SHA-256', value.independent_review_sha256);
    detail(provenance, 'Scope, unknown costs and remaining canonical dependencies', value.limitations);
  }
  async function read() {
    if (!ready || loading) return;
    loading = true; clear(); controls();
    byId('agent-realization-status').textContent = 'Reading the hash-pinned development record. No model, effect or new process is requested.';
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(ENDPOINT, {method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: controller.signal});
      if (!response.ok) throw new Error(`Development record HTTP ${response.status}`);
      render(await response.json());
    } catch (_) {
      clear(); byId('agent-realization-status').textContent = 'DEVELOPMENT RECORD UNAVAILABLE · no execution, provider request or automatic retry was issued.';
    } finally { clearTimeout(timer); loading = false; controls(); }
  }
  byId('agent-realization-read').addEventListener('click', read);
  document.addEventListener('se6:judge-state', event => { ready = event.detail?.ready === true; controls(); });
  document.addEventListener('se6:judge-reset', () => {
    clear(); byId('agent-realization-status').textContent = 'Session changed. Read the saved evidence again; no work was repeated.'; controls();
  });
  controls(); document.dispatchEvent(new Event('se6:judge-state-request'));
})();
