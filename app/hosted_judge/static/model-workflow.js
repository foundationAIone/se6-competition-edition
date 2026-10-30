'use strict';
(() => {
  const byId = id => document.getElementById(id);
  if (!byId('model-workflow')) return;
  const ENDPOINT = '/api/model-workflow/evidence';
  const SCHEMA = 'se6-model-workflow-view-v1';
  const STATES = new Set(['BLOCKED_PENDING_EXACT_BUDGET', 'RUNNING', 'CAPTURED_AWAITING_EVALUATION', 'COMPLETE', 'INCOMPLETE', 'INVALIDATED']);
  let ready = false, loading = false, saved = null;
  const node = (tag, text) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = typeof text === 'object' ? JSON.stringify(text, null, 2) : String(text);
    return element;
  };
  const text = value => value === null || value === undefined ? 'UNKNOWN — not supplied or not measured' : typeof value === 'object' ? JSON.stringify(value, (_key, item) => item === null ? 'UNKNOWN — not supplied or not measured' : item, 2) : String(value);
  function controls() {
    byId('model-workflow-read').disabled = !ready || loading;
    byId('model-workflow-export').disabled = !saved || loading;
    byId('model-workflow').setAttribute('aria-busy', String(loading));
  }
  function line(parent, label, value) {
    const row = node('p'); row.append(node('strong', `${label}: `), node('span', text(value))); parent.append(row);
  }
  function clear() {
    byId('model-workflow-summary').replaceChildren();
    byId('model-workflow-projects').replaceChildren();
    byId('model-workflow-provenance').replaceChildren();
    saved = null;
  }
  function detail(parent, label, value) {
    const box = node('details'); box.append(node('summary', label), node('pre', text(value))); parent.append(box);
  }
  function projectNumber(project) {
    const match = String(project.project_id ?? '').match(/\d+/);
    return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER;
  }
  function render(record) {
    if (!record || record.schema !== SCHEMA || !STATES.has(record.status) || !['PREPARED', 'RECORDED'].includes(record.record_kind)) throw new Error('Unsupported saved-record schema or status. No execution is established.');
    if (record.responses_committed === true && (record.record_kind !== 'RECORDED' || record.status === 'BLOCKED_PENDING_EXACT_BUDGET')) throw new Error('Inconsistent committed-record status.');
    if (record.status === 'COMPLETE' && record.responses_committed !== true) throw new Error('Complete result has no committed responses.');
    clear();
    // Defense in depth: never export unreleased case/answer fields from a
    // malformed prepared response, even though the trusted reader strips them.
    saved = Object.fromEntries(['schema', 'status', 'record_kind', 'responses_committed', 'protocol_sha256', 'source_manifest_sha256', 'model', 'limits', 'scope'].map(key => [key, record[key]]));
    saved.projects = record.responses_committed === true && Array.isArray(record.projects) ? record.projects : [];
    saved.aggregate = record.responses_committed === true ? record.aggregate : null;
    byId('model-workflow-status').textContent = `MODEL_COMPARISON: ${record.status}`;
    byId('model-workflow-kind').textContent = record.status === 'BLOCKED_PENDING_EXACT_BUDGET' ? 'PREPARED · NO MODEL COMPARISON EXECUTED' : record.status === 'RUNNING' ? 'SAVED IN-PROGRESS RECORD · OUTCOME UNVERIFIED' : 'RECORDED PILOT · READ ONLY';
    const summary = byId('model-workflow-summary'), provenance = byId('model-workflow-provenance');
    line(summary, 'Execution status', record.status);
    line(summary, 'Design', '3 independently generated projects × 2 related stages × 2 arms. Three project sequences are the independent units.');
    line(summary, 'Illustrated story rule', 'Lowest numeric project identifier, selected before outcomes. All three projects remain visible.');
    line(summary, 'New model calls authorized by this viewer', 0);
    line(provenance, 'Protocol SHA-256', record.protocol_sha256);
    line(provenance, 'Executing source manifest SHA-256', record.source_manifest_sha256);
    detail(provenance, 'Model and matched settings', record.model);
    detail(provenance, 'Declared request, token, tool-loop and cost limits', record.limits);
    detail(provenance, 'Evidence scope and limitations', record.scope);
    if (record.responses_committed !== true) {
      line(summary, 'Results', `${record.status === 'BLOCKED_PENDING_EXACT_BUDGET' ? 'NOT_EXECUTED' : 'NOT_RELEASED'}. No proposed patch, scored answer, action or comparative result is shown before responses are committed.`);
      line(summary, 'Advantage', 'NOT_ESTABLISHED — an unexecuted comparison has no score.');
      controls(); return;
    }
    line(summary, 'Responses', 'Committed records. This is read-only replay, not a new provider request or repair.');
    detail(summary, 'Aggregate pilot results — all projects and material costs', record.aggregate);
    if (record.status !== 'COMPLETE') line(summary, 'Incomplete or invalidated scope', 'Preserve failures and missing outcomes. Captured proposals or dispatch receipts alone do not establish successful goals.');
    const projects = Array.isArray(record.projects) ? [...record.projects].sort((a, b) => projectNumber(a) - projectNumber(b) || String(a.project_id).localeCompare(String(b.project_id))) : [];
    if (!projects.length) line(summary, 'Project records', 'UNKNOWN — no committed project projection is available.');
    for (const [index, project] of projects.entries()) {
      const card = node('article'); card.className = 'model-workflow-project';
      card.append(node('h3', `${project.project_id || 'UNKNOWN PROJECT'}${index === 0 ? ' · preselected illustration' : ''}`));
      if (project.task) line(card, 'Developer problem', project.task);
      const stages = Array.isArray(project.stages) ? [...project.stages].sort((a, b) => Number(a.stage) - Number(b.stage)) : [];
      for (const stage of stages) {
        const section = node('section'); section.className = 'model-workflow-stage';
        section.append(node('h4', `Stage ${text(stage.stage)} · ${stage.change_kind || stage.change || 'change not supplied'}`));
        const columns = node('div'); columns.className = 'model-workflow-arms';
        for (const [key, title] of [['conventional', 'Same model · conventional tools and notes'], ['se6', 'Same model · actual SE6']]) {
          const arm = (stage.arms || {})[key] || {}, column = node('div'); column.className = 'model-workflow-arm';
          column.append(node('h5', title)); line(column, 'Recorded status', arm.status);
          detail(column, 'Untrusted model interpretations / proposals', arm.model_proposals ?? arm.model_proposal);
          detail(column, 'Actual inspection and tool events', arm.tool_events);
          detail(column, key === 'se6' ? 'Actual Native selection and Boundary' : 'Actual conventional decision and checks', arm.native_or_control_decision ?? arm.native_receipts);
          detail(column, 'Action actually dispatched', arm.action);
          detail(column, 'Independent consequence witness', arm.independent_verdict ?? arm.independent_witness);
          detail(column, 'Verified retention and invalidation', arm.retention);
          detail(column, 'Cold-process continuation and consumed context', arm.cold_continuation ?? arm.retention?.cold_continuation);
          detail(column, 'Measured resources — unknown values remain UNKNOWN', arm.resources);
          columns.append(column);
        }
        section.append(columns); card.append(section);
      }
      byId('model-workflow-projects').append(card);
    }
    controls();
  }
  async function load() {
    if (!ready || loading) return;
    loading = true; clear(); controls();
    byId('model-workflow-status').textContent = 'Reading the saved source-bound pilot record. No inference or action is requested.';
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(ENDPOINT, {method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: controller.signal});
      if (!response.ok) throw new Error(`Saved-record HTTP ${response.status}. Current execution is not established.`);
      const record = await response.json(); render(record);
    } catch (_) {
      clear(); byId('model-workflow-kind').textContent = 'READ UNAVAILABLE · NO EXECUTION REQUESTED';
      byId('model-workflow-status').textContent = 'MODEL_COMPARISON: UNKNOWN. The saved record could not be verified or read. No provider call, repair or retry was issued.';
    } finally { clearTimeout(timer); loading = false; controls(); }
  }
  byId('model-workflow-read').addEventListener('click', load);
  byId('model-workflow-export').addEventListener('click', () => {
    if (!saved || loading) return;
    const blob = new Blob([JSON.stringify(saved, null, 2)], {type: 'application/json'}), url = URL.createObjectURL(blob), link = node('a');
    link.href = url; link.download = 'se6-model-workflow-saved-record.json'; link.click(); URL.revokeObjectURL(url);
  });
  document.addEventListener('se6:judge-state', event => { ready = event.detail?.ready === true; controls(); });
  document.addEventListener('se6:judge-reset', () => {
    clear(); byId('model-workflow-kind').textContent = 'SAVED RECORD · NOT LOADED';
    byId('model-workflow-status').textContent = 'Judge session changed. Read the saved record again; no execution was repeated.'; controls();
  });
  controls(); document.dispatchEvent(new Event('se6:judge-state-request'));
})();
