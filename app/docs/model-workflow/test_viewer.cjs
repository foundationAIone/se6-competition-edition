/* Focused offline UI projection guards. Synthetic records, no browser/provider/World execution. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../../hosted_judge/static/model-workflow.js'),'utf8');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.handlers={};this._text='';this.disabled=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent||'').join(' ');}
  set innerHTML(_){throw new Error('Unsafe HTML insertion');}
  append(...values){this.children.push(...values);}
  replaceChildren(...values){this._text='';this.children=[...values];}
  setAttribute(key,value){this[key]=value;}
  addEventListener(name,fn){this.handlers[name]=fn;}
  click(){return this.handlers.click?.();}
}
function setup(payload,{ok=true,status=200}={}){
  const ids=['model-workflow','model-workflow-read','model-workflow-export','model-workflow-summary','model-workflow-projects','model-workflow-provenance','model-workflow-status','model-workflow-kind'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element()])),listeners={},calls=[],blobs=[];
  const document={getElementById:id=>elements[id],createElement:tag=>new Element(tag),addEventListener:(name,fn)=>{listeners[name]=fn;},dispatchEvent:event=>listeners[event.type]?.(event)};
  const context={document,Event:class{constructor(type){this.type=type;}},AbortController,Blob,setTimeout,clearTimeout,URL:{createObjectURL:b=>{blobs.push(b);return'blob:test';},revokeObjectURL:()=>{}},fetch:async(url,options)=>{calls.push({url,options});return{ok,status,json:async()=>payload};}};
  vm.runInNewContext(source,context);document.dispatchEvent({type:'se6:judge-state',detail:{ready:true}});
  return{elements,document,calls,blobs};
}
const prepared=()=>({schema:'se6-model-workflow-view-v1',status:'BLOCKED_PENDING_EXACT_BUDGET',record_kind:'PREPARED',responses_committed:false,protocol_sha256:null,source_manifest_sha256:null,model:{identifier:'TEST_ONLY_NOT_PROVIDER'},limits:{usd_cap:null,max_requests:36},scope:['SYNTHETIC UI GUARD FIXTURE'],aggregate:null,projects:[]});
const stage=number=>({stage:number,change_kind:number===1?'INITIAL':'CHANGED_ROOT',arms:{se6:{status:'REFUSED',model_proposals:['<img src=x onerror=bad()>'],native_receipts:['TEST_ONLY'],independent_verdict:null,resources:{cpu_seconds:null}},conventional:{status:'INCOMPLETE',tool_events:['TEST_ONLY'],resources:{cpu_seconds:null}}}});
async function main(){
  let checks=0;
  {
    const record=prepared();record.projects=[{project_id:'HIDDEN_ANSWER_DO_NOT_RENDER'}];record.aggregate={secret:'HIDDEN_SCORE_DO_NOT_RENDER'};
    const c=setup(record);assert.equal(c.calls.length,0);await c.elements['model-workflow-read'].click();
    assert.equal(c.calls.length,1);assert.equal(c.calls[0].url,'/api/model-workflow/evidence');assert.equal(c.calls[0].options.method,'GET');assert.equal(c.calls[0].options.body,undefined);
    assert.match(c.elements['model-workflow-status'].textContent,/BLOCKED_PENDING_EXACT_BUDGET/);assert.equal(c.elements['model-workflow-projects'].children.length,0);
    c.elements['model-workflow-export'].click();const exported=JSON.parse(await c.blobs[0].text());assert.deepEqual(exported.projects,[]);assert.equal(exported.aggregate,null);checks++;
  }
  {
    const record={...prepared(),status:'COMPLETE',record_kind:'RECORDED',responses_committed:true,aggregate:{scope:'TEST_ONLY',advantage:'NOT_ESTABLISHED'},projects:[3,1,2].map(id=>({project_id:`project-${id}`,stages:[stage(2),stage(1)]}))};
    const c=setup(record);await c.elements['model-workflow-read'].click();const projects=c.elements['model-workflow-projects'].children;
    assert.equal(projects.length,3);assert.match(projects[0].children[0].textContent,/project-1.*preselected/);assert.match(projects[1].children[0].textContent,/project-2/);
    assert.match(projects[0].textContent,/Stage 1.*INITIAL/);assert.match(projects[0].textContent,/UNKNOWN/);assert.match(projects[0].textContent,/<img src=x onerror=bad\(\)>/);assert.match(c.elements['model-workflow-summary'].textContent,/read-only replay/);checks++;
  }
  {
    const c=setup({...prepared(),responses_committed:true});await c.elements['model-workflow-read'].click();assert.match(c.elements['model-workflow-status'].textContent,/UNKNOWN/);assert.equal(c.elements['model-workflow-export'].disabled,true);checks++;
  }
  {
    const c=setup(prepared(),{ok:false,status:403});await c.elements['model-workflow-read'].click();assert.match(c.elements['model-workflow-status'].textContent,/UNKNOWN/);assert.equal(c.calls.length,1);assert.equal(c.elements['model-workflow-projects'].children.length,0);checks++;
  }
  {
    const c=setup({...prepared(),schema:'forged'});await c.elements['model-workflow-read'].click();assert.match(c.elements['model-workflow-status'].textContent,/UNKNOWN/);assert.equal(c.elements['model-workflow-export'].disabled,true);checks++;
  }
  {
    const c=setup(prepared());await c.elements['model-workflow-read'].click();c.document.dispatchEvent({type:'se6:judge-reset'});assert.equal(c.elements['model-workflow-export'].disabled,true);assert.match(c.elements['model-workflow-status'].textContent,/session changed/);assert.equal(c.calls.length,1);checks++;
  }
  {
    const c=setup({...prepared(),status:'RUNNING',record_kind:'RECORDED'});await c.elements['model-workflow-read'].click();assert.match(c.elements['model-workflow-kind'].textContent,/IN-PROGRESS/);assert.match(c.elements['model-workflow-summary'].textContent,/NOT_RELEASED/);assert(!c.elements['model-workflow-summary'].textContent.includes('NOT_EXECUTED'));checks++;
  }
  {
    const c=setup({...prepared(),status:'COMPLETE',record_kind:'RECORDED'});await c.elements['model-workflow-read'].click();assert.match(c.elements['model-workflow-status'].textContent,/UNKNOWN/);assert.equal(c.elements['model-workflow-export'].disabled,true);checks++;
  }
  assert(!/method:\s*['"]POST['"]/.test(source));console.log(JSON.stringify({status:'PASS',checks,provider_calls:0,world_effects:0,scope:'Synthetic UI projection guards only'}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
