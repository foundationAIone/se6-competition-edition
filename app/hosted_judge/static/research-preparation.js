'use strict';
(() => {
  const button=document.getElementById('research-preparation-read');
  if(!button)return;
  function scoreTable(block,container,label){
    const heading=document.createElement('h3');heading.textContent=label+' · '+block.label;container.append(heading);
    const table=document.createElement('table'),head=document.createElement('tr');
    for(const text of ['Arm','Recall@5','All required','Processed']){const th=document.createElement('th');th.textContent=text;head.append(th);}
    table.append(head);
    for(const arm of ['se6','bm25']){
      const row=block.scores[arm],tr=document.createElement('tr');
      for(const text of [arm==='se6'?'SE6':'BM25',(row.recall_at_5*100).toFixed(1)+'%',(row.all_evidence_success*100).toFixed(1)+'%',row.successfully_processed+'/'+row.cases]){const td=document.createElement('td');td.textContent=text;tr.append(td);}
      table.append(tr);
    }
    container.append(table);
  }
  button.addEventListener('click',async()=>{
    const status=document.getElementById('research-preparation-status');
    const content=document.getElementById('research-preparation-content');
    button.disabled=true;
    try{
      const response=await fetch('/api/research-preparation/evidence',{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw Error(`Saved preparation unavailable (HTTP ${response.status})`);
      const value=await response.json();
      const scored=value.schema==='se6-retrieval-result-view-v1';
      const graded=value.schema==='se6-research-repair-result-view-v2';
      const repair=graded||value.schema==='se6-research-repair-result-view-v1';
      if((!scored&&!repair&&value.schema!=='se6-research-preparation-view-v1')||value.provider_calls!==(graded?30:0)||value.production_connected!==false||value.alpha_changed!==false)throw Error('Research scope mismatch');
      content.replaceChildren();
      if(repair){
        document.getElementById('research-preparation-heading').textContent='Repaired SE6 retrieval · fresh measured comparison';
        button.previousElementSibling.textContent=graded?'Fresh retrieval and preserved original results. The retrieval pass used no model. Separately approved grading recovered30original saved outputs; no reader responses were regenerated. Those judgments do not measure the repaired retriever.':'Distinct fresh evaluation and preserved historical result. Shared retrieval foundation, actual SE6 eligibility and retained method selection. Local repair made zero new provider calls; saved reader outputs remain ungraded.';
        button.textContent='READ SAVED REPAIR RESULT · NO EXECUTION';
        scoreTable(value.fresh_evaluation,content,'Fresh frozen subset');
        scoreTable(value.historical,content,'Preserved original · now development evidence');
        const reader=document.createElement('p');reader.textContent='Reader recovery: '+value.reader_recovery.grading_status+' · '+value.reader_recovery.completed_responses+' completed responses preserved · '+value.reader_recovery.new_provider_calls+' recorded grader calls.';content.append(reader);
        if(graded){
          const title=document.createElement('h3');title.textContent='Original saved outputs · model-graded15-pair subset';content.append(title);
          const note=document.createElement('p');note.textContent='Original20-case and repaired-retriever response accuracy remain unmeasured. These are blinded Nemotron judgments on15previously completed pairs, not human-verified truth or an official full benchmark score.';content.append(note);
          const table=document.createElement('table'),head=document.createElement('tr');
          for(const text of ['Arm','Correct','Model-graded accuracy']){const th=document.createElement('th');th.textContent=text;head.append(th);}table.append(head);
          for(const arm of ['se6','bm25']){const row=value.reader_recovery.paired_accuracy[arm],tr=document.createElement('tr');for(const text of [arm==='se6'?'SE6':'BM25',row.correct+'/'+row.denominator,(row.accuracy*100).toFixed(1)+'%']){const td=document.createElement('td');td.textContent=text;tr.append(td);}table.append(tr);}content.append(table);
        }
      }else if(scored){
        document.getElementById('research-preparation-heading').textContent='Measured LongMemEval-S retrieval comparison';
        const description=button.previousElementSibling;
        description.textContent=value.label+' Complete histories, separate cold stores and external annotation grading. This is not final-answer accuracy or an official full benchmark score.';
        button.textContent='READ SAVED RETRIEVAL RESULT · NO EXECUTION';
        scoreTable(value,content,'Recorded retrieval');
      }
      const fields=repair?['development','architecture','resources','reader_recovery','limitations','paid_proposal','evidence_pins']:(scored?['selection','resources','limitations','qa_proposal','evidence_pins']:['adapter','dataset','control','isolation','secondary','paid_proposal','remaining_blockers','evidence_pins']);
      for(const key of fields){
        const item=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');
        summary.textContent=key.replaceAll('_',' ');pre.textContent=JSON.stringify(value[key],null,2);
        item.append(summary,pre);content.append(item);
      }
      status.textContent=graded?'FRESH RETRIEVAL RECORDED · SAVED OUTPUTS GRADED · READ-ONLY VIEW':(repair?'FRESH RETRIEVAL RECORDED · ZERO NEW PROVIDER CALLS · SAVED RESPONSES NOT GRADED':(scored?'EXTERNAL RETRIEVAL RECORDED · NO ANSWERING MODEL · ZERO PROVIDER CALLS':'LOCAL PREPARATION VERIFIED · EXTERNAL EVALUATION BLOCKED · ZERO PROVIDER CALLS'));
    }catch(error){status.textContent=error.message;content.replaceChildren();}
    finally{button.disabled=false;}
  });
})();
