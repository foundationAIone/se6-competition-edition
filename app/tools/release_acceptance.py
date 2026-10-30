"""One real offline HTTP workflow and cold process recovery, no production/provider access."""
from pathlib import Path
import argparse,datetime,hashlib,http.cookiejar,json,os,signal,subprocess,sys,time,urllib.request,urllib.error,uuid

ROOT=Path(__file__).resolve().parents[1]
QUESTION=('ROUTINE: 1 technician-hours, $11 materials cost, $65 customer revenue.\n'
          'DEEP: 3 technician-hours, $27 materials cost, $145 customer revenue.\n'
          'We completed 12 jobs. The original log recorded 20 technician-hours. The materials budget is $210.\n'
          'Calculate revenue, materials and gross contribution.\nDetermine whether materials exceed budget.')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--leave-running',action='store_true');a=p.parse_args()
    out=a.evidence.resolve();assert not out.exists() and not out.is_relative_to(ROOT)
    out.mkdir(parents=True);store=out/'runtime';jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
    proc=None;log=None;origin=None;result={'schema':'se6-clean-release-acceptance-v1','started_at_utc':stamp(),'provider_calls':0,'production_connected':False,'cases':[]}

    def start(label):
        nonlocal proc,log,origin
        att=out/(label+'-attestation.json');log=(out/(label+'-server.log')).open('wb')
        env={k:v for k,v in os.environ.items() if k not in ('NEBIUS_API_KEY','OPENAI_API_KEY','PYTHONPATH','PYTHONHOME')}
        env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1'})
        flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0
        proc=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/run_dashboard.py'),'--port','0','--store',str(store),'--attestation',str(att)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        deadline=time.monotonic()+30
        while not att.exists():
            assert proc.poll() is None,'Owned server exited; inspect its private log'
            assert time.monotonic()<deadline,'Startup deadline; no retry'
            time.sleep(.1)
        value=json.loads(att.read_bytes());assert value['production_connected'] is False
        if value['actual_pid']!=proc.pid:
            # Windows venv python.exe is a redirector; verify its actual child.
            assert os.name=='nt'
            command=f'(Get-CimInstance Win32_Process -Filter "ProcessId = {int(value["actual_pid"])}").ParentProcessId'
            parent=subprocess.check_output(['powershell','-NoProfile','-Command',command],text=True,timeout=10)
            assert int(parent.strip())==proc.pid,'Attested server is not our child'
        origin=value['origin'];assert origin.startswith('http://127.0.0.1:')
        result[label+'_pid']=value['actual_pid'];result[label+'_launcher_pid']=proc.pid;result[label+'_attestation_sha256']=sha(att)
        return value

    def stop():
        nonlocal proc,log
        if proc is not None and proc.poll() is None:
            proc.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGINT)
            proc.wait(timeout=20)
        if log:log.close()
        proc=None;log=None

    def request(path,data=None,csrf=None):
        headers={}
        if data is not None:headers={'Origin':origin,'Content-Type':'application/json','X-Judge-CSRF':csrf or ''}
        req=urllib.request.Request(origin+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with client.open(req,timeout=10) as r:
            raw=r.read();return r.status,json.loads(raw) if 'application/json' in r.headers.get('Content-Type','') else raw

    def run(question,csrf,label):
        rid=uuid.uuid4().hex;started=time.perf_counter();cpu=time.process_time()
        status,value=request('/api/run',{'question':question,'request_id':rid},csrf);assert status in (200,202)
        deadline=time.monotonic()+120
        while value.get('status')=='RUNNING':
            assert time.monotonic()<deadline,'Job deadline; outcome uncertain, never resubmit'
            time.sleep(.5);status,value=request('/api/result/'+rid)
        (out/(label+'-result.json')).write_text(json.dumps(value,indent=2)+'\n')
        assert value.get('status')!='FAILED_CLOSED',value
        assert value['provider_calls']==0 and value['realization_loop']['status']=='BOUNDED_END_TO_END_RENEWED'
        assert value['comparison']['baseline_status']=='NOT_EXECUTED_NOT_AUTHORIZED'
        result['cases'].append({'label':label,'request_id':rid,'at_utc':stamp(),'wall_seconds':time.perf_counter()-started,'acceptance_parent_cpu_seconds':time.process_time()-cpu,'resources':value['realization_loop']['resources'],'result_sha256':sha(out/(label+'-result.json'))})
        return value

    try:
        start('initial');assert request('/healthz')[1]['status']=='ok'
        for name in ('/','/demo/comparison/','/app.js','/style.css'):
            # Asset routes are defined by the existing application, not guessed file names.
            if name in ('/app.js','/style.css'):continue
            status,page=request(name);assert status==200 and b'RUN BOTH' in page
        routes={'index.html':'/','dynamic.html':'/dynamic','canonical.html':'/canonical'}
        for file in (ROOT/'hosted_judge/static').iterdir():
            if file.is_file():
                status,raw=request(routes.get(file.name,'/'+file.name));assert status==200 and hashlib.sha256(raw).hexdigest()==sha(file)
        session=request('/api/session')[1];assert session['native_available']
        try:request('/api/run',{'question':QUESTION,'request_id':uuid.uuid4().hex},'invalid')
        except urllib.error.HTTPError as e:assert e.code==403
        else:raise AssertionError('Missing CSRF rejection')
        first=run(QUESTION,session['csrf_token'],'initial')
        assert 'Revenue: $1100.00' in first['answer'] and 'deep = 4' in first['realization_loop']['cycles'][1]['selected_result']
        assert first['realization_loop']['after_step']==2
        # The exact pair is prepared by the real gateway but never dispatched.
        packets=list((store/'recursive-realization').rglob('*.json'))
        result['retained_files_before_restart']=len(packets)
        stop();start('recovered')
        cold=request('/api/session')[1];assert cold['state_restored_from_disk'] is True
        second=run('Correct technician-hours to 22.',cold['csrf_token'],'correction')
        assert 'Revenue: $1180.00' in second['answer'] and 'Budget exceeded: YES' in second['answer']
        assert second['realization_loop']['after_step']==4
        assert second['realization_loop']['cycles'][0]['before_state_sha256']==first['realization_loop']['cycles'][1]['after_state_sha256']
        assert second['realization_loop']['cycles'][0]['restored_prior_from_disk'] is True
        effects=list((store/'recursive-realization').rglob('effects-ledger/effects/*.json'))
        assert len(effects)==4, len(effects)
        result.update({'status':'PASS','actual_http_jobs':2,'verified_artifact_effects':4,'cold_process_recovery':'VERIFIED','retained_steps':[0,2,4],'source_manifest_sha256':sha(ROOT/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'),'origin':origin,'csrf_rejection':'VERIFIED','baseline':'NOT_EXECUTED_NOT_AUTHORIZED','complete_cpu_total':None,'local_money':None})
        if a.leave_running:
            result['owned_preview_pid']=result['recovered_pid'];log.close();log=None;proc=None
    except Exception as error:
        result.update({'status':'FAIL','error_type':type(error).__name__,'error':str(error)[:2000]})
        raise
    finally:
        stop();result['finished_at_utc']=stamp();(out/'ACCEPTANCE_PRIVATE.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:result[k] for k in ('status','provider_calls','production_connected')}))

if __name__=='__main__':main()
