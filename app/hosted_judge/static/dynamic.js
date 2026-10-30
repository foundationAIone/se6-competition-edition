'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = String(text); if (cls) n.className = cls; return n; };
  const text = value => value === null || value === undefined ? 'Not reported' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
  const table = (headers, rows) => { const wrap = node('div', undefined, 'table-wrap'); const t = node('table'); const head = node('thead'); const tr = node('tr'); headers.forEach(h => { const th = node('th', h); th.scope = 'col'; tr.append(th); }); head.append(tr); t.append(head); const body = node('tbody'); rows.forEach(row => { const r = node('tr'); row.forEach(cell => r.append(node('td', text(cell)))); body.append(r); }); t.append(body); wrap.append(t); return wrap; };
  const details = (label, value) => { const d = node('details'); d.append(node('summary', label), node('pre', text(value))); return d; };
  const fields = value => { const dl = node('dl'); Object.entries(value || {}).forEach(([k,v]) => dl.append(node('dt', k.replaceAll('_',' ')), node('dd', text(v)))); return dl; };
  let data;
  const renderEvent = (scenario, index) => {
    const event = scenario.events[index]; const out = byId('event'); out.replaceChildren();
    out.append(node('h3', `${scenario.domain} · ${event.phase}`), node('h4','Question'), node('pre',text(event.question)), node('h4','Observed answer'), node('pre',text(event.answer)));
    const checks = event.checks || {}; const entries = Array.isArray(checks) ? checks.map((v,i) => [String(i+1),v]) : Object.entries(checks);
    out.append(node('h4','Independent checks'), table(['Check','Observed result'], entries));
    out.append(node('h4','Work and resources'), fields(event.metrics));
    const control = (data.control_scenarios || []).find(s => s.id === scenario.id);
    if (control && control.events[index]) {
      const c = control.events[index]; const passed = checks => Object.values(checks || {}).filter(v => v === true).length;
      out.append(node('h4','Memory-removal mechanism ablation'), node('p','This lane discards retained information. It is not a conventional stateful agent or direct Nemotron comparison.'),
        node('pre',c.answer), table(['Observed resource or check','Retained SE6 state','Memory removed'],
          [['Checks passed',passed(event.checks),passed(c.checks)],['Native transition attempts',event.metrics.native_transition_attempts,c.metrics.native_transition_attempts],
           ['End-to-end subprocess seconds',event.metrics.subprocess_wall_seconds,c.metrics.subprocess_wall_seconds]]));
    }
    const knowledge = event.knowledge || {}; const previous = index > 0 ? scenario.events[index-1].knowledge || {} : {};
    const size = (k, field) => Array.isArray(k[field]) ? k[field].length : 0;
    out.append(node('h4','Observable state change'), table(['Knowledge','Previous phase','Current phase'],
      ['constraints','active','invalidated','relations'].map(field => [field,size(previous,field),size(knowledge,field)])));
    const equation = item => (item.coefficients || []).map(([name,coefficient]) => `${coefficient}·${name}`).join(' + ') + ' = ' + item.rhs;
    const relationships = (knowledge.constraints || []).map(c => [c.label,equation(c),'Current premise']);
    (knowledge.active || []).forEach(c => relationships.push([String(c.reference).slice(0,18),equation(c),'Active verified deduction']));
    (knowledge.relations || []).forEach(r => relationships.push([r.subject,`${r.predicate} = ${r.value}`,r.status]));
    out.append(node('h4','Current relationships'), table(['Evidence or subject','Relationship','Status'],relationships));
    out.append(node('p',`${size(knowledge,'invalidated')} deduction(s) invalidated; ${event.receipts.length} canonical receipt(s) captured for this phase. Retained supplied facts are conditional on their source.`));
    out.append(details('Knowledge after this phase', event.knowledge), details('Canonical receipt field projection (raw records retained privately)', event.receipts || []), details('Realization stages', event.traces || []));
    out.append(details('Checkpoint transition (public projection)', {before:event.checkpoint_before,after:event.checkpoint_after}));
    [...byId('phases').children].forEach((b,i) => b.setAttribute('aria-current', String(i === index)));
  };
  const renderScenario = () => {
    const index = Number(byId('scenario').value); const scenario = data.scenarios[index]; const phases = byId('phases'); phases.replaceChildren();
    if (!scenario || !Array.isArray(scenario.events) || !scenario.events.length) { byId('event').replaceChildren(node('p','No event evidence is available.')); return; }
    scenario.events.forEach((e,i) => { const b = node('button',`${i+1}. ${e.phase}`); b.type = 'button'; b.addEventListener('click',() => renderEvent(scenario,i)); phases.append(b); }); renderEvent(scenario,0);
  };
  const load = async () => {
    try {
      const response = await fetch('/api/dynamic',{method:'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
      if (!response.ok) throw new Error(`Evidence endpoint returned HTTP ${response.status}`);
      data = await response.json(); if (!data || !Array.isArray(data.scenarios)) throw new Error('Evidence schema is unavailable');
      byId('status').textContent = `${data.name || 'Dynamic evidence'} · read-only review`;
      byId('conditions').replaceChildren(node('h3','Condition execution status'), fields(data.model_conditions));
      const bookkeeping = new Set(['operational_self_model_matches_observed','launch_identity_matches_driver','no_false_provider_or_world_authority','persistent_roundtrip','fresh_process_handoff']);
      const functional = scenarios => {
        const checks = (scenarios || []).flatMap(s => s.events).flatMap(e => Object.entries(e.checks || {}).filter(([name]) => !bookkeeping.has(name)).map(([,v]) => v));
        return `${checks.filter(v => v === true).length}/${checks.length}`;
      };
      byId('totals').replaceChildren(node('h3','Measured offline outcomes'), table(['Condition','Functional checks','Subprocess seconds','Provider cost'],
        [['Retained SE6 state',functional(data.scenarios),Number(data.totals.SE6.subprocess_wall_seconds).toFixed(1),'$0'],
         ['Memory-removal ablation',functional(data.control_scenarios),Number(data.totals.DROP_RETAINED_STATE.subprocess_wall_seconds).toFixed(1),'$0']]),
        details('Full counts and measured resources',data.totals));
      byId('equation').textContent = text(data.equation); byId('equation-status').textContent = text(data.equation_status);
      byId('operators').replaceChildren(table(['Operator','Execution status','Scope'],(data.operator_coverage || []).map(o => [o.operator,o.status,o.description])));
      byId('mechanisms').replaceChildren(details('Reported mechanisms',data.mechanisms));
      const select = byId('scenario'); select.replaceChildren(); data.scenarios.forEach((s,i) => { const option = node('option',`${s.id} · ${s.domain}`); option.value = String(i); select.append(option); }); select.disabled = !data.scenarios.length; select.addEventListener('change',renderScenario); renderScenario();
    } catch (error) { byId('status').textContent = `Evidence unavailable: ${error.message}. No work or inference was executed.`; }
  };
  load();
})();
