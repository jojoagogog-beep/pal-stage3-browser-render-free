from __future__ import annotations
import itertools, json, os, subprocess, sys, threading, time
from pathlib import Path
from flask import Flask, jsonify, request

HERE=Path(__file__).resolve().parent
WORKER=HERE/'stage3_send_ready_worker_v1.py'
STAGE2_WORKER=HERE/'candidate_route_worker_v1.py'
TOKEN=os.environ.get('PAL_RENDER_TOKEN','')
# Browser proof yield is materially higher on DYNAMIC_JS/IFRAME_DEEP than DEEP.
# Keep every lane represented, but do not spend 25% of the free Render browser
# budget on low-yield technical DEEP retries. This changes scheduling only;
# every route still passes the exact same proof/safety contract.
LANES=itertools.cycle(('DYNAMIC_JS','FAST_DOM','DYNAMIC_JS',
                       'IFRAME_DEEP','DYNAMIC_JS','DEEP'))
RUN_LOCK=threading.Lock()
STAGE2_LOCK=threading.Lock()
STAGE2_STATE_LOCK=threading.Lock()
STAGE2_THREAD=None
STAGE2_STATE={'status':'IDLE','at':0,'started_at':0,'duration_seconds':0,'returncode':None,'run_count':0,'last_summary':{},'last_completed':None,'workers':0,'batch':0,'priority_markets':[]}
STATE_LOCK=threading.Lock()
LEASE_LOCK=threading.Lock()
STATE={
    'status':'IDLE','lane':None,'at':0,'duration_seconds':0,'returncode':None,
    'pump_alive':False,'last_trigger':'BOOT','last_cron_wake_epoch':0,
    'run_count':0,'failure_streak':0,'last_completed':None,
}
LEASE_UNTIL=0.0
PUMP_THREAD=None
ACTIVE_PRIORITY_MARKETS=[]
LANE_EMPTY_STREAK={lane:0 for lane in ('FAST_DOM','DYNAMIC_JS','IFRAME_DEEP','DEEP')}
LANE_SKIP_UNTIL={lane:0.0 for lane in LANE_EMPTY_STREAK}
LANE_EMPTY_BASE_COOLDOWN_SECONDS=max(10,min(120,int(os.environ.get('PAL_RENDER_EMPTY_LANE_COOLDOWN_SECONDS','30') or 30)))
LEASE_SECONDS=max(120,min(600,int(os.environ.get('PAL_RENDER_LEASE_SECONDS','180') or 180)))
IDLE_SLEEP_SECONDS=max(2,min(30,int(os.environ.get('PAL_RENDER_IDLE_SLEEP_SECONDS','8') or 8)))
# Keep the high-yield dynamic lane wide, but bound slow/low-yield deep lanes so
# one batch cannot monopolize the free Render browser for several minutes.
LANE_MAX_ROWS={'DYNAMIC_JS':4,'IFRAME_DEEP':4,'DEEP':2,'FAST_DOM':4}
# The per-route budget must exceed the internal navigation + render budget.
# Previously 16-18s wrapped a page.goto() that could itself wait 30s, making
# OVERALL_ROUTE_TIMEOUT_OR_ERROR inevitable on otherwise valid slower sites.
LANE_DEADLINE_SECONDS={'DYNAMIC_JS':58,'IFRAME_DEEP':58,'DEEP':52,'FAST_DOM':45}
LANE_ROUTE_TIMEOUT_SECONDS={'DYNAMIC_JS':42,'IFRAME_DEEP':42,'DEEP':38,'FAST_DOM':30}
LANE_RETRY_TIMEOUT_SECONDS={'DYNAMIC_JS':42,'IFRAME_DEEP':42,'DEEP':38,'FAST_DOM':30}
app=Flask(__name__)

def allowed():
    got=request.headers.get('x-pal-token','')
    return bool(TOKEN and got==TOKEN)

def _worker_summary(stdout):
    for raw in reversed((stdout or '').splitlines()):
        raw=raw.strip()
        if not raw.startswith('{'):
            continue
        try:
            obj=json.loads(raw)
        except Exception:
            continue
        if isinstance(obj,dict) and 'status' in obj:
            return obj
    return {}

def _lease_remaining():
    with LEASE_LOCK:
        return max(0,round(LEASE_UNTIL-time.time(),1))

def _stage2_snapshot():
    with STAGE2_STATE_LOCK:
        out=dict(STAGE2_STATE)
    t=STAGE2_THREAD
    out['thread_alive']=bool(t and t.is_alive())
    return out

def _valid_blob_url(raw):
    u=str(raw or '').strip()
    return u.startswith('https://superjsonblob.com/api/jsonBlob/') and len(u)<300

def _stage2_runner(task_url,result_url,priority_markets,workers,batch):
    global STAGE2_THREAD
    started=time.time()
    try:
        env=os.environ.copy()
        env.update({
            'PAL_ROUTE_TASK_BLOB_URL':task_url,
            'PAL_ROUTE_RESULT_BLOB_URL':result_url,
            'PAL_CANDIDATE_ROUTE_LANE_COUNT':'1',
            'PAL_CANDIDATE_ROUTE_LANE_INDEX':'0',
            'PAL_CANDIDATE_ROUTE_WORKERS':str(max(4,min(16,int(workers)))),
            'PAL_CANDIDATE_ROUTE_BATCH':str(max(16,min(128,int(batch)))),
            # Render is the high-throughput read-only verifier. Bound fallback
            # sitemap breadth so one bad site cannot consume the whole 220s run.
            # Acceptance/safety checks are unchanged.
            'PAL_CANDIDATE_ROUTE_DEPTH':'3',
            'PAL_CANDIDATE_ROUTE_SITEMAP_ROOTS':'3',
            'PAL_CANDIDATE_ROUTE_SITEMAP_CHILDREN':'3',
            'PAL_ROUTE_PRIORITY_MARKETS':','.join(priority_markets[:8]),
            'PAL_ROUTE_PRIORITY_STRICT':'1',
        })
        cp=subprocess.run([sys.executable,str(STAGE2_WORKER)],env=env,text=True,capture_output=True,timeout=220)
        summary=_worker_summary(cp.stdout or '')
        completed={
            'status':'PASS' if cp.returncode==0 else 'ERROR',
            'at':int(time.time()),'duration_seconds':round(time.time()-started,2),
            'returncode':cp.returncode,'summary':summary,
            'workers':int(workers),'batch':int(batch),
            'priority_markets':list(priority_markets),
        }
        with STAGE2_STATE_LOCK:
            STAGE2_STATE.update(
                status=completed['status'],at=completed['at'],
                duration_seconds=completed['duration_seconds'],
                returncode=cp.returncode,
                run_count=int(STAGE2_STATE.get('run_count') or 0)+1,
                last_summary=summary,last_completed=completed,
            )
    except subprocess.TimeoutExpired:
        completed={'status':'TIMEOUT','at':int(time.time()),
                   'duration_seconds':round(time.time()-started,2),'returncode':None,
                   'summary':{},'workers':int(workers),'batch':int(batch),
                   'priority_markets':list(priority_markets)}
        with STAGE2_STATE_LOCK:
            STAGE2_STATE.update(status='TIMEOUT',at=completed['at'],
                duration_seconds=completed['duration_seconds'],returncode=None,
                run_count=int(STAGE2_STATE.get('run_count') or 0)+1,
                last_summary={},last_completed=completed)
    except Exception as e:
        with STAGE2_STATE_LOCK:
            STAGE2_STATE.update(status='ERROR',at=int(time.time()),
                duration_seconds=round(time.time()-started,2),returncode=None,
                run_count=int(STAGE2_STATE.get('run_count') or 0)+1,
                last_summary={'error':type(e).__name__})
    finally:
        STAGE2_THREAD=None
        try: STAGE2_LOCK.release()
        except RuntimeError: pass

def _snapshot():
    with STATE_LOCK:
        out=dict(STATE)
    out['lease_seconds_remaining']=_lease_remaining()
    t=PUMP_THREAD
    out['pump_alive']=bool(t and t.is_alive())
    out['priority_markets']=list(ACTIVE_PRIORITY_MARKETS)
    return out

def _extend_lease(source):
    global LEASE_UNTIL
    now=time.time()
    with LEASE_LOCK:
        LEASE_UNTIL=max(LEASE_UNTIL,now+LEASE_SECONDS)
    with STATE_LOCK:
        STATE['last_trigger']=source
        if source=='EXTERNAL_CRON':
            STATE['last_cron_wake_epoch']=int(now)

def _next_lane():
    now=time.time()
    fallback=None
    fallback_until=None
    for _ in range(12):
        lane=_next_lane()
        until=float(LANE_SKIP_UNTIL.get(lane) or 0)
        if fallback is None or until < fallback_until:
            fallback,lane_until=lane,until
            fallback_until=lane_until
        if until<=now:
            return lane
    return fallback or next(LANES)

def _record_lane_result(lane,summary,code):
    routes=int((summary or {}).get('routes') or 0)
    if code>=500:
        return
    if routes<=0:
        streak=int(LANE_EMPTY_STREAK.get(lane) or 0)+1
        LANE_EMPTY_STREAK[lane]=streak
        cooldown=min(180,LANE_EMPTY_BASE_COOLDOWN_SECONDS*(2**min(streak-1,2)))
        LANE_SKIP_UNTIL[lane]=time.time()+cooldown
    else:
        LANE_EMPTY_STREAK[lane]=0
        LANE_SKIP_UNTIL[lane]=0.0

def execute_lane(lane):
    started=time.time()
    try:
        env=os.environ.copy()
        configured_max=max(1,min(240,int(os.environ.get('PAL_STAGE3_MAX_ROWS','12') or 12)))
        lane_max=min(configured_max,int(LANE_MAX_ROWS.get(lane,6)))
        lane_deadline=int(LANE_DEADLINE_SECONDS.get(lane,90))
        lane_route_timeout=int(LANE_ROUTE_TIMEOUT_SECONDS.get(lane,24))
        lane_retry_timeout=int(LANE_RETRY_TIMEOUT_SECONDS.get(lane,lane_route_timeout))
        env.update({
            'PAL_STAGE3_LANE_MODE':lane,
            'PAL_STAGE3_CONCURRENCY':os.environ.get('PAL_STAGE3_CONCURRENCY','4'),
            'PAL_STAGE3_RENDERER_PROCESS_LIMIT':os.environ.get('PAL_STAGE3_RENDERER_PROCESS_LIMIT','4'),
            'PAL_STAGE3_PRIORITY_MARKETS':','.join(ACTIVE_PRIORITY_MARKETS),
            'PAL_STAGE3_MAX_ROWS':str(lane_max),
            'PAL_STAGE3_ROUTE_TIMEOUT_SECONDS':str(lane_route_timeout),
            'PAL_STAGE3_RETRY_TIMEOUT_SECONDS':str(lane_retry_timeout),
            'PAL_STAGE3_RETRY_LIMIT':'0',
            'PAL_STAGE3_RECENT_ROUTE_SECONDS':'900',
            'PAL_STAGE3_RECENT_TECH_SECONDS':'600',
            'PAL_STAGE3_STATE_FILE':'/tmp/pal_stage3_'+lane.lower()+'.json',
            'PAL_STAGE3_DEADLINE_EPOCH':str(int(time.time())+lane_deadline),
            'PAL_STAGE3_PRODUCER':'PAL_RENDER_STAGE3_BROWSER_V1',
        })
        cp=subprocess.run(
            [sys.executable,str(WORKER)],env=env,text=True,
            capture_output=True,timeout=220,
        )
        out=(cp.stdout or '')[-7000:]
        err=(cp.stderr or '')[-2000:]
        summary=_worker_summary(out)
        body={
            'status':'PASS' if cp.returncode==0 else 'ERROR',
            'lane':lane,'returncode':cp.returncode,
            'duration_seconds':round(time.time()-started,2),
            'worker_summary':summary,
            'stdout_tail':out[-1800:],'stderr_tail':err[-700:],
        }
        code=200 if cp.returncode==0 else 500
    except subprocess.TimeoutExpired:
        body={'status':'TIMEOUT','lane':lane,
              'duration_seconds':round(time.time()-started,2),'worker_summary':{}}
        code=504
    except Exception as e:
        body={'status':'ERROR','lane':lane,'error':type(e).__name__,
              'detail':str(e)[:240],
              'duration_seconds':round(time.time()-started,2),'worker_summary':{}}
        code=500
    with STATE_LOCK:
        runs=int(STATE.get('run_count') or 0)+1
        failures=(int(STATE.get('failure_streak') or 0)+1) if code>=500 else 0
        completed={
            'lane':lane,
            'status':body.get('status'),
            'at':int(time.time()),
            'duration_seconds':body.get('duration_seconds'),
            'worker_summary':body.get('worker_summary') or {},
        }
        keep={
            'last_trigger':STATE.get('last_trigger'),
            'last_cron_wake_epoch':STATE.get('last_cron_wake_epoch',0),
        }
        STATE.clear()
        STATE.update({k:v for k,v in body.items() if k not in ('stdout_tail','stderr_tail')})
        STATE.update(keep)
        STATE.update(at=int(time.time()),pump_alive=bool(PUMP_THREAD and PUMP_THREAD.is_alive()),
                     run_count=runs,failure_streak=failures,last_completed=completed)
    print(json.dumps({
        'event':'LANE_FINISHED','lane':lane,'code':code,
        'duration_seconds':body.get('duration_seconds'),
        'worker_summary':body.get('worker_summary') or {},
    },separators=(',',':')),flush=True)
    return body,code

def background_pump():
    global PUMP_THREAD
    idle_rounds=0
    try:
        while _lease_remaining()>0:
            lane=_next_lane()
            with STATE_LOCK:
                keep_runs=int(STATE.get('run_count') or 0)
                keep_failures=int(STATE.get('failure_streak') or 0)
                keep_cron=int(STATE.get('last_cron_wake_epoch') or 0)
                keep_trigger=STATE.get('last_trigger')
                keep_completed=STATE.get('last_completed')
                STATE.clear()
                STATE.update(
                    status='RUNNING',lane=lane,at=int(time.time()),
                    duration_seconds=0,returncode=None,pump_alive=True,
                    run_count=keep_runs,failure_streak=keep_failures,
                    last_cron_wake_epoch=keep_cron,last_trigger=keep_trigger,
                    last_completed=keep_completed,
                )
            body,code=execute_lane(lane)
            summary=body.get('worker_summary') or {}
            _record_lane_result(lane,summary,code)
            tasks=int(summary.get('tasks') or 0)
            routes=int(summary.get('routes') or 0)
            if code>=500:
                time.sleep(min(30,5*max(1,int(_snapshot().get('failure_streak') or 1))))
                continue
            if tasks<=0 and routes<=0:
                idle_rounds+=1
                time.sleep(IDLE_SLEEP_SECONDS if idle_rounds>=2 else 2)
            else:
                idle_rounds=0
    finally:
        with STATE_LOCK:
            STATE['pump_alive']=False
            if STATE.get('status')=='RUNNING':
                STATE['status']='IDLE'
            STATE['at']=int(time.time())
        PUMP_THREAD=None
        try:
            RUN_LOCK.release()
        except RuntimeError:
            pass
        print(json.dumps({'event':'PUMP_STOPPED','reason':'LEASE_EXPIRED'},separators=(',',':')),flush=True)

def start_or_extend(source,priority_markets=None):
    global PUMP_THREAD,ACTIVE_PRIORITY_MARKETS
    if priority_markets is not None:
        clean=[]
        for x in priority_markets:
            x=str(x or '').strip()
            if x and x not in clean: clean.append(x)
        ACTIVE_PRIORITY_MARKETS=clean[:8]
    _extend_lease(source)
    if not RUN_LOCK.acquire(blocking=False):
        return {'status':'BUSY','source':source,'state':_snapshot()},202
    try:
        with STATE_LOCK:
            STATE['last_trigger']=source
            STATE['pump_alive']=True
        PUMP_THREAD=threading.Thread(target=background_pump,name='pal-render-pump',daemon=True)
        PUMP_THREAD.start()
        print(json.dumps({'event':'PUMP_STARTED','source':source,'lease_seconds':LEASE_SECONDS},
                         separators=(',',':')),flush=True)
        return {'status':'STARTED','source':source,'lease_seconds':LEASE_SECONDS,
                'state':_snapshot()},202
    except Exception:
        try:
            RUN_LOCK.release()
        except RuntimeError:
            pass
        raise


@app.post('/stage2-wake')
def stage2_wake():
    global STAGE2_THREAD
    if not allowed():
        return ('unauthorized',401)
    body=request.get_json(silent=True) or {}
    task_url=str(body.get('task_url') or '')
    result_url=str(body.get('result_url') or '')
    if not _valid_blob_url(task_url) or not _valid_blob_url(result_url):
        return jsonify(status='BAD_BLOB_URL'),400
    markets=[]
    for x in body.get('priority_markets') or []:
        x=str(x or '').strip()
        if x and x not in markets: markets.append(x)
    workers=max(4,min(16,int(body.get('workers') or 8)))
    batch=max(16,min(128,int(body.get('batch') or 64)))
    if not STAGE2_LOCK.acquire(blocking=False):
        return jsonify(status='BUSY',state=_stage2_snapshot()),202
    with STAGE2_STATE_LOCK:
        STAGE2_STATE.update(status='RUNNING',at=int(time.time()),started_at=int(time.time()),
                            duration_seconds=0,returncode=None,
                            workers=workers,batch=batch,priority_markets=list(markets))
    STAGE2_THREAD=threading.Thread(
        target=_stage2_runner,
        args=(task_url,result_url,markets,workers,batch),
        daemon=True,
    )
    STAGE2_THREAD.start()
    return jsonify(status='STARTED',state=_stage2_snapshot()),202

@app.get('/stage2-state')
def stage2_state():
    if not allowed():
        return ('unauthorized',401)
    return jsonify(_stage2_snapshot())

@app.get('/health')
def health():
    return jsonify(service='PAL_RENDER_STAGE3_BROWSER_V1',status='PASS',
                   lane_max_rows=LANE_MAX_ROWS,
                   lane_deadline_seconds=LANE_DEADLINE_SECONDS,
                   lane_empty_streak=LANE_EMPTY_STREAK,
                   lane_skip_until=LANE_SKIP_UNTIL,
                   worker_state=_snapshot())

@app.get('/state')
def state():
    if not allowed():
        return ('unauthorized',401)
    return jsonify(_snapshot())

@app.post('/cron-wake-v1')
def cron_wake():
    body,code=start_or_extend('EXTERNAL_CRON')
    return jsonify(body),code

@app.post('/wake')
def wake():
    if not allowed():
        return ('unauthorized',401)
    payload=request.get_json(silent=True) or {}
    pm=payload.get('priority_markets') if isinstance(payload,dict) else None
    body,code=start_or_extend('MAC_WAKE',pm)
    return jsonify(body),code

@app.post('/tick')
def tick():
    if not allowed():
        return ('unauthorized',401)
    _extend_lease('SYNC_TICK')
    if not RUN_LOCK.acquire(blocking=False):
        return jsonify(status='BUSY',state=_snapshot()),202
    lane=next(LANES)
    with STATE_LOCK:
        STATE['last_trigger']='SYNC_TICK'
        STATE['pump_alive']=False
        STATE['status']='RUNNING'
        STATE['lane']=lane
        STATE['at']=int(time.time())
    try:
        body,code=execute_lane(lane)
        _record_lane_result(lane,body.get('worker_summary') or {},code)
        return jsonify(body),code
    finally:
        RUN_LOCK.release()
