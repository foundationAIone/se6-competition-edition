'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const show = value => value === undefined || value === null ? 'Not supplied' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
  const el = (tag, value, cls) => { const n = document.createElement(tag); if (value !== undefined) n.textContent = show(value); if (cls) n.className = cls; return n; };
  const list = value => Array.isArray(value) ? value : value && typeof value === 'object' ? Object.entries(value).map(([id,v]) => typeof v === 'object' && v ? {id,...v} : {id,value:v}) : [];
  const fields = value => { const dl = el('dl'); Object.entries(value || {}).forEach(([k,v]) => dl.append(el('dt',k.replaceAll('_',' ')),el('dd',v))); return dl; };
  const detail = (label, value) => { const d = el('details'); d.append(el('summary',label),el('pre',value)); return d; };
  const table = (headers, rows) => { const wrap=el('div',undefined,'table-wrap'),t=el('table'),head=el('thead'),hr=el('tr'); headers.forEach(label=>{const th=el('th',label);th.scope='col';hr.append(th);});head.append(hr);t.append(head);const body=el('tbody');rows.forEach(row=>{const tr=el('tr');row.forEach(v=>tr.append(el('td',v)));body.append(tr);});t.append(body);wrap.append(t);return wrap; };
  let payload;
  function topology(graph) {
    const box=el('section');box.append(el('h4','Actual plan topology'),el('p','Cards are a display layout of supplied plan nodes. Arrows mean depends on; no physical coordinates, geometric rotations or Flower-of-Life simulation are implied.'));
    if(!graph || !Array.isArray(graph.nodes) || !graph.nodes.length){box.append(el('p','No plan topology was supplied for this round.'));return box;}
    const nodes=graph.nodes;const validString=x=>typeof x==='string' && x.length>0 && x.length<=128;
    if(nodes.length>64){box.append(el('p','Malformed or excessive topology projection; graph not rendered.','notice'));return box;}
    const ids=new Set(nodes.map(n=>n && n.id));
    if(nodes.length>64 || ids.size!==nodes.length || nodes.some(n=>!n || !validString(n.id) || !validString(n.route) || typeof n.admitted!=='boolean' || !Array.isArray(n.depends_on) || n.depends_on.length>64 || new Set(n.depends_on).size!==n.depends_on.length || n.depends_on.some(d=>!validString(d) || !ids.has(d) || d===n.id))){box.append(el('p','Malformed or excessive topology projection; graph not rendered.','notice'));return box;}
    const edges=nodes.flatMap(n=>n.depends_on.map(d=>[n.id,d]));
    const visited=new Set();let progress=true;while(progress){progress=false;for(const n of nodes)if(!visited.has(n.id) && n.depends_on.every(d=>visited.has(d))){visited.add(n.id);progress=true;}}
    if(edges.length>256 || visited.size!==nodes.length){box.append(el('p','Cyclic or excessive dependency projection; graph not rendered.','notice'));return box;}
    const cards=el('div',undefined,'topology-cards');
    nodes.forEach(n=>{const card=el('article',undefined,'topology-node');card.append(el('h5',n.id),el('p',n.route),el('p',n.admitted?'Admitted by supplied plan gate':'Not admitted / skipped'),el('p',n.depends_on.length?'Depends on → '+n.depends_on.join(', '):'No prerequisite in supplied plan'));cards.append(card);});box.append(cards);
    box.append(table(['Plan node','Depends on prerequisite'],edges));
    if(!edges.length)box.append(el('p','No dependency edges are present in this supplied plan.'));
    box.append(fields({flower_recentered_terminal:graph.flower_recentered_terminal,scope:graph.scope}));return box;
  }
  function stageFlow(canonical,receipts) {
    const box=el('section');box.append(el('h4','Reported stage evidence'),el('p','Mapping → Possibility → Kernel proof → Return. This display summarizes supplied observations. A stage label or a nonempty candidate is not proof of a performed or verified action.'));
    if(!canonical || typeof canonical!=='object'){box.append(el('p','No canonical stage projection supplied.'));return box;}
    const cards=el('div',undefined,'stage-cards');
    const values=[['Mapping',canonical.mapper || 'Not supplied'],['Possibility',canonical.qpre || 'Not supplied'],['Kernel proof',{independent_checkpoint_replay:canonical.independent_checkpoint_replay,receipt_verification:(Array.isArray(receipts)?receipts:[]).map(r=>({operation:r.operation,verification_passed:r.verification_passed}))}],['Return',{returned_center_changed:canonical.returned_center_changed,admission:canonical.admission,skips:canonical.skips}]];
    values.forEach(([label,value])=>{const card=el('article',undefined,'stage-card');card.append(el('h5',label),el('pre',value));cards.append(card);});box.append(cards);return box;
  }
  function renderRound(item,index) {
    const rounds=list(item.rounds || item.events);const r=rounds[index];const out=$('round');out.replaceChildren();
    if(!r){out.append(el('p','No round evidence supplied. No result is inferred.'));return;}
    out.append(el('h3',r.phase || r.name || `Round ${index+1}`),el('h4','Question'),el('pre',r.question || item.question));
    const canonical=r.outputs?.canonical || r.nativeoutputs?.canonical;
    out.append(el('h4','Observed native/controller output'),el('pre',r.outputs?.answer ?? r.outputs ?? r.nativeoutputs ?? r.output ?? r.answer));
    out.append(topology(canonical?.plan_graph),stageFlow(canonical,r.receipts));
    if(canonical)out.append(detail('Full public canonical projection',canonical));
    out.append(el('h4','Measured resources'),fields(r.resources || r.metrics || {}));
    out.append(el('h4','Skipped or unsupported work'),el('pre',r.skips ?? r.skip_reasons ?? []));
    out.append(detail('Before and after evidence',{before:r.before ?? r.checkpoint_before,after:r.after ?? r.checkpoint_after}));
    out.append(detail('Correction and transfer consequences',{correction:r.correction,transfer:r.transfer,checks:r.checks}));
    out.append(detail('Exact admitted receipt projection',r.receipts || []),detail('Actual realization trace projection',r.traces || []));
    [...$('rounds').children].forEach((b,i)=>b.setAttribute('aria-current',String(i===index)));
  }
  function renderCase() {
    const item=list(payload.cases) [Number($('case-select').value)];$('rounds').replaceChildren();
    if(!item){$('round').replaceChildren(el('p','No accepted case evidence is currently supplied.'));return;}
    const rounds=list(item.rounds || item.events);
    if(!rounds.length){$('round').replaceChildren(el('h3',item.id || item.name),el('pre',item));return;}
    rounds.forEach((r,i)=>{const b=el('button',`${i+1}. ${r.phase || r.name || 'observed round'}`);b.type='button';b.addEventListener('click',()=>renderRound(item,i));$('rounds').append(b);});renderRound(item,0);
  }
  async function init() {
    try {
      const response=await fetch('/api/canonical',{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);payload=await response.json();if(!payload || typeof payload!=='object' || !payload.equation)throw new Error('Canonical evidence schema missing');
      $('status').textContent=`${payload.name || 'Canonical evidence'} · read-only source and result review`;
      const eq=payload.equation;$('equations').replaceChildren(fields({primary_reference:eq.primary_reference,transcription_status:eq.transcription_status,secondary_source_contract:eq.contract,secondary_source_document_sha256:eq.source_document_sha256}));
      for(const [value,label] of [[eq.owner_older_latex,'Primary: owner-selected older action-dependent variant'],[eq.source_operational_latex ?? eq.operational_latex,'Secondary: source-exact V6.1 operational composition'],[eq.recursive_latex,'Source recursive closure'],[eq.official_reference_latex,'Secondary: September 30 integral reference, not equated'],[eq.owner_latest_latex,'Earlier abbreviated owner quotation']]){const block=el('div',undefined,'equation-block');block.append(el('h3',label),el('pre',value));$('equations').append(block);}
      $('reconciliation').replaceChildren(el('h3','Reconciliation status'),el('pre',eq.reconciliation));
      const operators=list(payload.operators || payload.operator_coverage);$('operators').replaceChildren(table(['Operator','Evidence status','Source attribution','Supported scope / skip reason'],operators.map(o=>[o.operator || o.id,o.status,o.source || o.source_ref,o.skip_reason ? `${o.description || ''}\nSkip: ${o.skip_reason}` : o.description || o.value])));
      $('conditions').replaceChildren(fields(payload.conditions || payload.model_conditions || {}));$('limits').replaceChildren(detail('Limits and unavailable comparisons',payload.limits));
      const select=$('case-select');select.replaceChildren();list(payload.cases).forEach((item,i)=>{const option=el('option',`${item.id || item.name || i+1}${item.domain ? ' · '+item.domain : ''}`);option.value=String(i);select.append(option);});select.disabled=!select.children.length;select.addEventListener('change',renderCase);renderCase();
    } catch(error) {$('status').textContent=`Canonical evidence unavailable: ${error.message}. Nothing was executed.`;}
  }
  init();
})();
