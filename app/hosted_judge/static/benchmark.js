(() => {
  'use strict';
  const byId=id=>document.getElementById(id);
  const element=(tag,text)=>{const node=document.createElement(tag);node.textContent=typeof text==='string'?text:JSON.stringify(text,null,2);return node;};
  const labels={A:'Direct model',B:'Conventional shared tools + memory',C:'Supported V11 realization',D:'Same fields + ordinary traversal'};
  let view;
  async function repeat(event){
    event.preventDefault();const button=byId('benchmark-run'),status=byId('benchmark-repeat-status');button.disabled=true;
    const request_id=crypto.randomUUID().replaceAll('-','');
    try{
      const session=await (await fetch('/api/session',{credentials:'same-origin',cache:'no-store',redirect:'error'})).json();
      const response=await fetch('/api/benchmark/run',{method:'POST',credentials:'same-origin',redirect:'error',headers:{'Content-Type':'application/json','X-Judge-CSRF':session.csrf_token},body:JSON.stringify({request_id,task_id:byId('benchmark-task').value,condition:byId('benchmark-condition').value})});
      let result=await response.json();if(!response.ok)throw new Error(result.error || 'Native task rejected');
      const started=Date.now();while(result.status==='RUNNING'){
        status.textContent='Running actual offline native work. Provider calls: 0. Polling reads only.';
        if(Date.now()-started>180000)throw new Error('Status wait ended; no automatic resubmission.');
        await new Promise(resolve=>setTimeout(resolve,1000));
        result=await (await fetch('/api/benchmark/result/'+request_id,{credentials:'same-origin',cache:'no-store',redirect:'error'})).json();
      }
      status.textContent=result.status+' · actual native repeat · model NOT_EXECUTED · frozen first results unchanged';
      byId('benchmark-repeat-result').replaceChildren(element('pre',result));
    }catch(error){status.textContent=error.message+' No retry or model call occurred.';}
    finally{button.disabled=false;}
  }
  function render(){
    const category=byId('benchmark-category').value,body=byId('benchmark-rows');body.replaceChildren();
    for(const task of view.tasks.filter(x=>category==='ALL'||x.category===category)){
      const row=element('tr','');row.append(element('th',task.id),element('td',`${task.category} · ${task.phases} phase(s)`));
      for(const condition of ['A','B','C','D']){
        const record=task.conditions[condition],cell=element('td','');
        cell.append(element('strong',record.grading_status || record.native_status || 'NOT_EXECUTED'),element('p',`Native: ${record.native_status || 'NOT_EXECUTED'} · Model: NOT_EXECUTED`));
        if(record.wall_seconds!=null)cell.append(element('small',`${Number(record.wall_seconds).toFixed(2)}s local wall`));
        const details=element('details','');details.append(element('summary','Actual software evidence'),element('pre',record));cell.append(details);row.append(cell);
      }
      const details=element('details','');details.append(element('summary','Public task phases'),element('pre',task.public_questions));const cell=element('td','');cell.append(details);row.append(cell);body.append(row);
    }
  }
  function renderPilot(pilot){
    if(!pilot)return;
    const box=byId('frozen-live-pilot');
    box.replaceChildren(element('h3','Actual Nemotron pilot — frozen, independently scored'));
    const notice=element('p','UNASSESSABLE · no overall winner · 16 actual provider responses, 3 whole tasks / 4 phases. Viewing makes ZERO new calls. All authorizations are spent.');notice.className='notice';box.append(notice);
    box.append(element('p','Business numbers: B/C/D correct, but all business wrappers invalid; A also miscalculated revenue/contribution. All eight affine relations are wrong and omit scope fields. Graph truth is correct in all four lanes; A omitted the receipt list. B/C/D requests match byte-for-byte, so no field advantage is established.'));
    const summary=element('table','');summary.className='benchmark-table';const head=element('tr','');
    for(const title of ['Condition','Complete tasks','Unassessable','Input / output','Provider estimate'])head.append(element('th',title));summary.append(head);
    for(const arm of ['A','B','C','D']){const g=pilot.aggregates[arm],c=pilot.costs[arm],row=element('tr','');row.append(element('th',arm),element('td',`${g.complete_successes}/3`),element('td',String(g.unassessable)),element('td',`${c.input_tokens} / ${c.completion_tokens}`),element('td','$'+c.tariff_estimate_usd));summary.append(row);}box.append(summary);
    box.append(element('p',`Total ${pilot.total_prompt_tokens} input + ${pilot.total_completion_tokens} completion tokens; reported reasoning 0. $${pilot.total_tariff_estimate_usd} estimate, actual billing unknown. Campaign ${pilot.coordinator_wall_seconds.toFixed(3)}s; prior native preparation and audit costs are separate.`));
    const table=element('table','');table.className='benchmark-table';const th=element('tr','');
    for(const title of ['Task / phase','Lane','Official result','Actual answer and diagnosis','Tokens','Request window','Estimate'])th.append(element('th',title));table.append(th);
    for(const r of pilot.rows){const row=element('tr',''),answer=element('td',''),detail=element('details','');
      detail.append(element('summary','Actual captured answer'),element('pre',r.actual_answer_text),element('p',r.diagnostic_not_regraded),element('pre',{checks:r.official_checks,reason:r.official_reason,request_sha256:r.request_sha256,response_sha256:r.provider_response_sha256,native_scope:r.native_scope}));answer.append(detail);
      row.append(element('th',r.task_id+' / '+r.phase_id),element('td',r.condition),element('td',r.official_status),answer,element('td',String(r.total_tokens)),element('td',r.request_window_seconds.toFixed(3)+'s'),element('td','$'+r.tariff_estimate_usd));table.append(row);}
    const scroll=element('div','');scroll.className='benchmark-scroll';scroll.append(table);box.append(scroll);
    const evidence=element('details','');evidence.append(element('summary','Independent evidence, limitations and prior native resources'),element('pre',{source_revision:pilot.source_revision,source_manifest_sha256:pilot.source_manifest_sha256,external_capture_sha256:pilot.external_capture_sha256,scorer_sha256:pilot.scorer_sha256,oracle_sha256:pilot.oracle_sha256,limits:pilot.limitations,costs:pilot.costs}));box.append(evidence);
  }
  async function init(){
    try{
      const response=await fetch('/api/benchmark',{credentials:'same-origin',cache:'no-store',redirect:'error'});if(!response.ok)throw new Error('HTTP '+response.status);
      view=await response.json();if(view.status==='NOT_CONFIGURED')throw new Error('Frozen suite not configured');
      const phases=view.tasks.reduce((n,t)=>n+t.phases,0);
      byId('benchmark-status').textContent=`FROZEN OFFLINE SOFTWARE EVALUATION · 30 unique task units · ${phases} phases · ZERO new model calls. Full 30-task model study remains unexecuted; the separate frozen live pilot is shown above.`;
      const summary=byId('benchmark-summary');summary.replaceChildren(element('h3','Thirty-task native/software cohort — model study not executed'));
      const table=element('table','');table.className='benchmark-table';
      const head=element('tr','');for(const title of ['Control','Complete tasks','Unassessable','Local wall'])head.append(element('th',title));table.append(head);
      for(const condition of ['B','C','D']){const record=view.aggregate.arms[condition],cost=view.aggregate.costs[condition],row=element('tr','');
        row.append(element('th',labels[condition]),element('td',`${record.complete_successes}/${record.task_units}`),element('td',String(record.unassessable)),element('td',`${cost.supervisor_wall_seconds.toFixed(2)}s`));table.append(row);}
      summary.append(table,element('p','A has no model answer. These software results do not establish Nemotron superiority, cognition or a Merkabah advantage. All registered failures and unresolved tasks remain recorded.'));
      const limitations=element('details','');limitations.append(element('summary','Limitations and exact measurements'),element('pre',{aggregate:view.aggregate,comparisons:view.comparisons,scope:view.scope,limitations:view.limitations}));summary.append(limitations);
      renderPilot(view.live_pilot);
      byId('benchmark-pilot').replaceChildren(element('pre',view.pilot));
      byId('v2-evidence').replaceChildren(element('pre',view.v2));
      byId('benchmark-provenance').replaceChildren(element('pre',{source:view.source,controls:view.controls,coverage:view.coverage}));
      const select=byId('benchmark-category');for(const category of [...new Set(view.tasks.map(t=>t.category))]){const option=element('option',category);option.value=category;select.append(option);}select.onchange=render;render();
      const tasks=byId('benchmark-task');for(const task of view.tasks){const option=element('option',`${task.id} · ${task.phases} phase(s)`);option.value=task.id;tasks.append(option);}byId('benchmark-form').onsubmit=repeat;byId('benchmark-run').disabled=false;
    }catch(error){byId('benchmark-status').textContent='Benchmark evidence unavailable: '+error.message;}
  }
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init):init();
})();
