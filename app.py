# PAL_REPAIR_OWNER=RENDER_BROWSER | Cross-lane edits prohibited; use published interfaces/contracts.
# PAL_REPAIR_PROTOCOL_V2=GLOBAL_SINGLE_WRITER | CLAIM_LANE=RENDER_BROWSER before edit; ACCEPT_LANE after tests.
from __future__ import annotations
import hashlib, hmac, itertools, json, os, subprocess, sys, threading, time, urllib.request
from pathlib import Path
from flask import Flask, jsonify, request

HERE=Path(__file__).resolve().parent
WORKER=HERE/'stage3_send_ready_worker_v1.py'
STAGE2_WORKER=HERE/'candidate_route_worker_v1.py'
V9_SEND_WORKER=HERE/'v9_send_worker.py'
def _secret_text(path):
    try:return Path(path).read_text().strip()
    except Exception:return ''

def _v9_production_authorized(generation):
    try:
        g=int(generation or 0)
        if g<=0:return False
        url=os.environ.get('PAL_V9_CONTROL_HEALTH_URL','https://pal-b2b-v9-plane.jojoagogog.workers.dev/health')
        req=urllib.request.Request(url,headers={'User-Agent':'PAL-Render-V9-Control/1.0','Cache-Control':'no-cache'})
        with urllib.request.urlopen(req,timeout=8) as r:
            d=json.loads(r.read().decode('utf-8'))
        cut=d.get('cutover') or {}; led=cut.get('ledger') or {}
        return bool(d.get('service')=='PAL_B2B_V9_PLANE' and d.get('authority')=='GLOBAL_LEDGER_DO'
                    and d.get('mode')=='PRODUCTION' and d.get('ledger_mode')=='PRODUCTION'
                    and d.get('external_send_enabled') is True
                    and int(cut.get('generation') or 0)==g and int(led.get('generation') or 0)==g
                    and led.get('mode')=='PRODUCTION' and led.get('history_sync_complete') is True
                    and led.get('legacy_writer_disabled') is True and led.get('production_unlock') is True)
    except Exception:
        return False

def _v9_failover_authorized(generation,control_url):
    try:
        g=int(generation or 0); url=str(control_url or '').strip()
        if g<=0 or not url.startswith('https://superjsonblob.com/api/jsonBlob/'): return False
        # Never run standby while Cloudflare production authority is healthy.
        if _v9_production_authorized(g): return False
        req=urllib.request.Request(url+'?ts='+str(time.time_ns()),headers={'User-Agent':'PAL-Render-V9-Failover/1.0','Cache-Control':'no-cache'})
        with urllib.request.urlopen(req,timeout=8) as r:
            d=json.loads(r.read().decode('utf-8'))
        if d.get('schema')!='PAL_V9_FAILOVER_CONTROL_V1' or d.get('mode')!='FAILOVER': return False
        if int(d.get('generation') or 0)!=g or int(d.get('lease_until_epoch') or 0)<=int(time.time())+5: return False
        if d.get('lease_owner')!='MAC_V9_FAILOVER': return False
        sig=str(d.get('sig') or ''); unsigned={k:v for k,v in d.items() if k!='sig'}
        raw=json.dumps(unsigned,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
        exp=hmac.new(TOKEN.encode(),raw,hashlib.sha256).hexdigest()
        return bool(sig and hmac.compare_digest(sig,exp))
    except Exception:
        return False

TOKEN=(os.environ.get('PAL_RENDER_TOKEN','') or _secret_text('/etc/secrets/stage3_token'))
SERVICE_NAME=str(os.environ.get('RENDER_SERVICE_NAME','') or '')
# Primary is dual-role under one heavy-resource lock: Stage2 route verification
# and Stage3 Browser never overlap. Shard1 keeps Stage3/Sender priority and may use idle time for bounded V9 Stage2.
STAGE2_PRIMARY_ROLE=(SERVICE_NAME=='pal-stage3-browser-free-v1')
SCHEDULER_REVISION='STAGE2_FAIR_HANDOFF_V11_FAST_REPROOF'
V9_STAGE2_SHARD1_REVISION='V9_STAGE2_SHARD1_IDLE_ONLY_V1'
V9_STRICT_STATIC_REVISION='V9_STAGE2_STRICT_STATIC_FULL_V1'
# Browser proof yield is materially higher on DYNAMIC_JS/IFRAME_DEEP than DEEP.
# Keep every lane represented, but do not spend 25% of the free Render browser
# budget on low-yield technical DEEP retries. This changes scheduling only;
# every route still passes the exact same proof/safety contract.
LANES=itertools.cycle(('DYNAMIC_JS','DEEP','DYNAMIC_JS','FAST_DOM',
                       'DYNAMIC_JS','DEEP','IFRAME_DEEP','FAST_DOM'))
RUN_LOCK=threading.Lock()  # shared heavy-resource lock: Stage3 Browser OR Stage2 route worker
STAGE2_LOCK=threading.Lock()
STAGE2_STATE_LOCK=threading.Lock()
BROWSER_DEMAND_LOCK=threading.Lock()
BROWSER_DEMAND_UNTIL=0.0
BROWSER_PRIORITY_GRACE_SECONDS=max(30,min(300,int(os.environ.get('PAL_RENDER_BROWSER_PRIORITY_GRACE_SECONDS','120') or 120)))
STAGE2_DEMAND_LOCK=threading.Lock()
STAGE2_DEMAND_UNTIL=0.0
STAGE2_DEMAND_SECONDS=max(120,min(600,int(os.environ.get('PAL_RENDER_STAGE2_DEMAND_SECONDS','300') or 300)))
STAGE2_TURN_LOCK=threading.Lock()
STAGE2_TURN_UNTIL=0.0
STAGE2_TURN_SECONDS=max(60,min(180,int(os.environ.get('PAL_RENDER_STAGE2_TURN_SECONDS','120') or 120)))
# Primary Render is dual-role, but Stage3 Browser is the measured revenue
# bottleneck. When shard-0 Browser backlog is deep, do not hand the only
# Chromium-safe heavy slot to Stage2 after every Browser quantum. Stage2 still
# has Cloudflare/remote/fallback lanes and regains this Render slot as soon as
# Browser backlog drains to the bounded low-water mark.
STAGE2_YIELD_MAX_BROWSER_BACKLOG=max(0,min(4096,int(
    os.environ.get('PAL_RENDER_STAGE2_YIELD_MAX_BROWSER_BACKLOG','256') or 256)))
STAGE2_THREAD=None
STAGE2_STATE={'status':'IDLE','at':0,'started_at':0,'duration_seconds':0,'returncode':None,'run_count':0,'last_summary':{},'last_completed':None,'workers':0,'batch':0,'priority_markets':[]}
V9_STAGE2_PENDING_LOCK=threading.Lock()
V9_STAGE2_PENDING=None
V9_SEND_STATE_LOCK=threading.Lock()
V9_SEND_PENDING_LOCK=threading.Lock()
V9_SEND_THREAD=None
V9_SEND_PENDING=None
V9_SEND_STATE={'status':'IDLE','at':0,'duration_seconds':0,'returncode':None,'run_count':0,'last_summary':{},'last_completed':None}
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
# Authenticated /wake calls may supply the current Browser task/result blob URLs.
# This removes a fragile dependency on Render dashboard env values drifting from
# the Mac controller's authoritative remote_transport_v2.json. Values are still
# restricted to the approved SuperJSONBlob host and never exposed in /health.
ACTIVE_TASK_BLOB_URL=''
ACTIVE_RESULT_BLOB_URL=''
BROWSER_LANES=('FAST_DOM','DYNAMIC_JS','IFRAME_DEEP','DEEP')
LANE_EMPTY_STREAK={lane:0 for lane in BROWSER_LANES}
LANE_SKIP_UNTIL={lane:0.0 for lane in LANE_EMPTY_STREAK}
LANE_EMPTY_BASE_COOLDOWN_SECONDS=max(10,min(120,int(os.environ.get('PAL_RENDER_EMPTY_LANE_COOLDOWN_SECONDS','30') or 30)))
LEASE_SECONDS=max(180,min(600,int(os.environ.get('PAL_RENDER_LEASE_SECONDS','240') or 240)))
IDLE_SLEEP_SECONDS=max(2,min(30,int(os.environ.get('PAL_RENDER_IDLE_SLEEP_SECONDS','8') or 8)))
# Render Free is memory-bound: even two concurrent Browser inspections OOM-killed
# the gunicorn worker. Keep exactly one live Browser inspection / renderer.
# FAST_DOM may process up to four routes *serially inside the same Chromium
# process* so high-confidence send-reproof candidates amortize browser launch
# overhead without increasing concurrent memory pressure. Proof/safety gates are unchanged.
LANE_MAX_ROWS={'DYNAMIC_JS':3,'IFRAME_DEEP':2,'DEEP':2,'FAST_DOM':6}
LANE_CONCURRENCY={'DYNAMIC_JS':1,'IFRAME_DEEP':1,'DEEP':1,'FAST_DOM':1}
# The per-route budget must exceed the internal navigation + render budget.
# Previously 16-18s wrapped a page.goto() that could itself wait 30s, making
# OVERALL_ROUTE_TIMEOUT_OR_ERROR inevitable on otherwise valid slower sites.
LANE_DEADLINE_SECONDS={'DYNAMIC_JS':165,'IFRAME_DEEP':110,'DEEP':150,'FAST_DOM':165}
LANE_ROUTE_TIMEOUT_SECONDS={'DYNAMIC_JS':50,'IFRAME_DEEP':50,'DEEP':55,'FAST_DOM':25}
LANE_RETRY_TIMEOUT_SECONDS={'DYNAMIC_JS':50,'IFRAME_DEEP':50,'DEEP':55,'FAST_DOM':25}
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

def _browser_demand_remaining(now=None):
    now=time.time() if now is None else float(now)
    with BROWSER_DEMAND_LOCK:
        return max(0.0,float(BROWSER_DEMAND_UNTIL)-now)

def _note_browser_demand(now=None):
    global BROWSER_DEMAND_UNTIL
    now=time.time() if now is None else float(now)
    with BROWSER_DEMAND_LOCK:
        BROWSER_DEMAND_UNTIL=max(float(BROWSER_DEMAND_UNTIL),now+BROWSER_PRIORITY_GRACE_SECONDS)
        return max(0.0,BROWSER_DEMAND_UNTIL-now)

def _stage2_demand_remaining(now=None):
    now=time.time() if now is None else float(now)
    with STAGE2_DEMAND_LOCK:
        return max(0.0,float(STAGE2_DEMAND_UNTIL)-now)

def _note_stage2_demand(now=None):
    global STAGE2_DEMAND_UNTIL
    now=time.time() if now is None else float(now)
    with STAGE2_DEMAND_LOCK:
        STAGE2_DEMAND_UNTIL=max(float(STAGE2_DEMAND_UNTIL),now+STAGE2_DEMAND_SECONDS)
        return max(0.0,STAGE2_DEMAND_UNTIL-now)

def _clear_stage2_demand():
    global STAGE2_DEMAND_UNTIL
    with STAGE2_DEMAND_LOCK:
        STAGE2_DEMAND_UNTIL=0.0

def _stage2_turn_remaining(now=None):
    now=time.time() if now is None else float(now)
    with STAGE2_TURN_LOCK:
        return max(0.0,float(STAGE2_TURN_UNTIL)-now)

def _grant_stage2_turn(now=None):
    global STAGE2_TURN_UNTIL
    now=time.time() if now is None else float(now)
    with STAGE2_TURN_LOCK:
        STAGE2_TURN_UNTIL=max(float(STAGE2_TURN_UNTIL),now+STAGE2_TURN_SECONDS)
        return max(0.0,STAGE2_TURN_UNTIL-now)

def _clear_stage2_turn():
    global STAGE2_TURN_UNTIL
    with STAGE2_TURN_LOCK:
        STAGE2_TURN_UNTIL=0.0

def _primary_browser_backlog():
    """Authoritative queued Browser routes owned by primary/shard-0."""
    if not STAGE2_PRIMARY_ROLE:
        return 0
    counts=_browser_queue_lane_counts()
    if not isinstance(counts,dict):
        return None
    return sum(max(0,int(v or 0)) for v in counts.values())

def _stage2_fairness_allowed():
    backlog=_primary_browser_backlog()
    return backlog is None or backlog<=STAGE2_YIELD_MAX_BROWSER_BACKLOG

def _stage2_blocked_by_browser(browser_wait,browser_queued,pump_alive):
    """Stage2 gets a fairness turn only after the Browser low-water mark."""
    backlog=_primary_browser_backlog()
    if backlog is not None and backlog>STAGE2_YIELD_MAX_BROWSER_BACKLOG:
        return True
    if _stage2_turn_remaining()>0 and _stage2_demand_remaining()>0:
        return False
    # A queued Browser backlog alone must not reserve the shared primary slot
    # while Browser is idle. Active Browser demand/pump gets priority; otherwise
    # Stage2 may use the idle slot and Stage3 reclaims it on the next wake.
    return bool(float(browser_wait or 0)>0 or pump_alive)

def _resource_owner():
    vt=V9_SEND_THREAD
    if vt and vt.is_alive():
        return 'V9_SENDER'
    t=PUMP_THREAD
    if t and t.is_alive():
        return 'STAGE3_BROWSER'
    st=STAGE2_THREAD
    if st and st.is_alive():
        return 'STAGE2_ROUTE'
    return 'IDLE'

def _stage2_snapshot():
    with STAGE2_STATE_LOCK:
        out=dict(STAGE2_STATE)
    t=STAGE2_THREAD
    out['thread_alive']=bool(t and t.is_alive())
    return out

def _valid_blob_url(raw):
    u=str(raw or '').strip()
    return u.startswith('https://superjsonblob.com/api/jsonBlob/') and len(u)<300

def route_shard(route_id, shard_count=2):
    try: rid=int(route_id or 0); count=max(1,int(shard_count))
    except Exception: return -1
    if rid<=0:return -1
    # Stable hash avoids pathological ID-parity skew while remaining fully
    # deterministic across Render clones and deploys.
    return hashlib.sha256(str(rid).encode('ascii')).digest()[0] % count

def _browser_queue_has_tasks(url=None):
    """Return whether this Render shard owns Browser work; None on I/O error.

    A MAC_WAKE must not reserve the shared free Render heavy lane when the
    Browser queue is empty *for this deterministic shard*. Treating an odd
    route owned by shard1 as work for primary/shard0 made primary spin empty
    Browser lanes and continuously reject Stage2 route work. Unknown/error
    remains conservative (None), so a transient JSONBlob read failure never
    suppresses real proof work.
    """
    u=str(url or ACTIVE_TASK_BLOB_URL or os.environ.get('PAL_ROUTE_TASK_BLOB_URL','')).strip()
    if not _valid_blob_url(u):
        return None
    try:
        sep='&' if '?' in u else '?'
        req=urllib.request.Request(
            u+sep+'_pal_ts='+str(time.time_ns()),
            headers={'User-Agent':'PAL-Render-Queue-Probe/1.0',
                     'Accept':'application/json',
                     'Cache-Control':'no-cache, no-store',
                     'Pragma':'no-cache'})
        with urllib.request.urlopen(req,timeout=4) as resp:
            raw=resp.read(2000001)
        if len(raw)>2000000:
            return None
        data=json.loads(raw.decode('utf-8','ignore'))
        shard_index=0 if STAGE2_PRIMARY_ROLE else 1
        for task in (data.get('tasks') or []):
            if not isinstance(task,dict):
                continue
            if str(task.get('kind') or '')!='PAL_BROWSER_PREFLIGHT_TASK_V1':
                continue
            for rec in (task.get('routes') or []):
                if not isinstance(rec,dict):
                    continue
                try: rid=int(rec.get('route_id') or 0)
                except Exception: rid=0
                if rid>0 and route_shard(rid,2)==shard_index:
                    return True
        return False
    except Exception:
        return None

_LANE_QUEUE_CACHE={'at':0.0,'url':'','priority':(),'shard':-1,'counts':None}

def _lane_done_ids(lane):
    # The Browser worker checkpoints completed task IDs per lane. The task Blob
    # remains controller-owned until the next Mac cycle, so count only tasks
    # that this Render service has not already durably completed.
    try:
        p=Path('/tmp/pal_stage3_'+str(lane).lower()+'_dual_shard_v3.json')
        d=json.loads(p.read_text())
        return {str(x) for x in (d.get('processed_task_ids') or []) if str(x)}
    except Exception:
        return set()

def _browser_queue_lane_counts(url=None, max_age=3.0):
    # Scheduling only: count authoritative queued Browser routes for this
    # deterministic Render shard. Proof/safety/send contracts are untouched.
    u=str(url or ACTIVE_TASK_BLOB_URL or os.environ.get('PAL_ROUTE_TASK_BLOB_URL','')).strip()
    if not _valid_blob_url(u):
        return None
    shard_index=0 if STAGE2_PRIMARY_ROLE else 1
    priority=tuple(ACTIVE_PRIORITY_MARKETS)
    now=time.time()
    cached=_LANE_QUEUE_CACHE
    if (cached.get('url')==u and cached.get('priority')==priority
        and int(cached.get('shard') if cached.get('shard') is not None else -1)==shard_index
        and cached.get('counts') is not None
        and now-float(cached.get('at') or 0)<=max(0.0,float(max_age))):
        return dict(cached['counts'])
    try:
        sep='&' if '?' in u else '?'
        req=urllib.request.Request(
            u+sep+'_pal_lane_ts='+str(time.time_ns()),
            headers={'User-Agent':'PAL-Render-Lane-Probe/1.0',
                     'Accept':'application/json',
                     'Cache-Control':'no-cache, no-store',
                     'Pragma':'no-cache'})
        with urllib.request.urlopen(req,timeout=4) as resp:
            raw=resp.read(2000001)
        if len(raw)>2000000:
            return None
        data=json.loads(raw.decode('utf-8','ignore'))
        all_counts={lane:0 for lane in BROWSER_LANES}
        priority_counts={lane:0 for lane in BROWSER_LANES}
        done_by_lane={lane:_lane_done_ids(lane) for lane in BROWSER_LANES}
        for task in (data.get('tasks') or []):
            if not isinstance(task,dict) or str(task.get('kind') or '')!='PAL_BROWSER_PREFLIGHT_TASK_V1':
                continue
            lane=str(task.get('lane_hint') or '').upper()
            if lane not in all_counts:
                continue
            tid=str(task.get('task_id') or '')
            if tid and tid in done_by_lane.get(lane,set()):
                continue
            task_market=str(task.get('market') or '')
            for rec in (task.get('routes') or []):
                if not isinstance(rec,dict):
                    continue
                try: rid=int(rec.get('route_id') or 0)
                except Exception: rid=0
                if rid<=0 or route_shard(rid,2)!=shard_index:
                    continue
                market=str(rec.get('market') or task_market)
                all_counts[lane]+=1
                if priority and market in priority:
                    priority_counts[lane]+=1
        counts=priority_counts if sum(priority_counts.values())>0 else all_counts
        cached.update(at=now,url=u,priority=priority,shard=shard_index,counts=dict(counts))
        return dict(counts)
    except Exception:
        return None

def _release_idle_browser_priority():
    """Yield the shared Stage3/Stage2 heavy slot after Browser queue drains."""
    global BROWSER_DEMAND_UNTIL,LEASE_UNTIL
    now=time.time()
    with BROWSER_DEMAND_LOCK:
        BROWSER_DEMAND_UNTIL=min(float(BROWSER_DEMAND_UNTIL),now)
    with LEASE_LOCK:
        LEASE_UNTIL=min(float(LEASE_UNTIL),now+2.0)

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
            'PAL_CANDIDATE_ROUTE_WORKERS':str(max(4,min(24,int(workers)))),
            'PAL_CANDIDATE_ROUTE_BATCH':str(max(16,min(128,int(batch)))),
            'PAL_ROUTE_RESULT_KEEP':'48',
            'PAL_CANDIDATE_ROUTE_STATE_FILE':'/tmp/pal_candidate_route_state_v1.json',
            # Render is the high-throughput read-only verifier. Bound fallback
            # sitemap breadth so one bad site cannot consume the whole 220s run.
            # Acceptance/safety checks are unchanged.
            'PAL_CANDIDATE_ROUTE_DEPTH':'3',
            'PAL_CANDIDATE_ROUTE_SITEMAP_ROOTS':'3',
            'PAL_CANDIDATE_ROUTE_SITEMAP_CHILDREN':'3',
            'PAL_ROUTE_PRIORITY_MARKETS':','.join(priority_markets[:8]),
            'PAL_ROUTE_PRIORITY_STRICT':'1',
        })
        cp=subprocess.run([sys.executable,str(STAGE2_WORKER)],env=env,text=True,capture_output=True,timeout=(220 if STAGE2_PRIMARY_ROLE else 75))
        summary=_worker_summary(cp.stdout or '')
        completed={
            'status':'PASS' if cp.returncode==0 else 'ERROR',
            'at':int(time.time()),'duration_seconds':round(time.time()-started,2),
            'returncode':cp.returncode,'summary':summary,
            'stderr_tail':(cp.stderr or '')[-1600:],
            'stdout_tail':(cp.stdout or '')[-1600:],
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
        try: RUN_LOCK.release()
        except RuntimeError: pass
        # Heavy-lane priority is Sender > Browser proof > Stage2 supply.
        sender_started=_start_pending_v9_send()
        browser_started=False
        if not sender_started and _browser_demand_remaining()>0:
            try:
                body,_=start_or_extend('STAGE2_HANDOFF')
                browser_started=str(body.get('status') or '')=='STARTED'
            except Exception:
                browser_started=False
        stage2_started=False if (sender_started or browser_started) else _start_pending_v9_stage2()
        print(json.dumps({'event':'STAGE2_STOPPED','v9_sender_started':bool(sender_started),'browser_started':bool(browser_started),'v9_stage2_started':bool(stage2_started)},separators=(',',':')),flush=True)

def _v9_stage2_pending_snapshot():
    with V9_STAGE2_PENDING_LOCK:
        p=dict(V9_STAGE2_PENDING) if isinstance(V9_STAGE2_PENDING,dict) else None
    if not p:return None
    return {'queued_at':p.get('queued_at'),'workers':p.get('workers'),'batch':p.get('batch'),'priority_markets':list(p.get('priority_markets') or [])}

def _queue_v9_stage2(task_url,result_url,priority_markets,workers,batch):
    global V9_STAGE2_PENDING
    with V9_STAGE2_PENDING_LOCK:
        V9_STAGE2_PENDING={'task_url':task_url,'result_url':result_url,'priority_markets':list(priority_markets or [])[:8],
                           'workers':int(workers),'batch':int(batch),'queued_at':int(time.time())}
    with STAGE2_STATE_LOCK:
        if not (STAGE2_THREAD and STAGE2_THREAD.is_alive()):
            STAGE2_STATE.update(status='QUEUED',at=int(time.time()),priority_markets=list(priority_markets or [])[:8],workers=int(workers),batch=int(batch))

def _start_pending_v9_stage2():
    global V9_STAGE2_PENDING,STAGE2_THREAD
    if STAGE2_PRIMARY_ROLE:return False
    if (V9_SEND_THREAD and V9_SEND_THREAD.is_alive()) or _v9_send_pending_snapshot() is not None:return False
    with V9_STAGE2_PENDING_LOCK:
        pending=dict(V9_STAGE2_PENDING) if isinstance(V9_STAGE2_PENDING,dict) else None
    if not pending or (STAGE2_THREAD and STAGE2_THREAD.is_alive()):return False
    if not STAGE2_LOCK.acquire(blocking=False):return False
    if not RUN_LOCK.acquire(blocking=False):
        try:STAGE2_LOCK.release()
        except RuntimeError:pass
        return False
    try:
        with V9_STAGE2_PENDING_LOCK:
            pending=dict(V9_STAGE2_PENDING) if isinstance(V9_STAGE2_PENDING,dict) else pending
            V9_STAGE2_PENDING=None
        with STAGE2_STATE_LOCK:
            STAGE2_STATE.update(status='RUNNING',at=int(time.time()),started_at=int(time.time()),duration_seconds=0,returncode=None,
                                workers=int(pending['workers']),batch=int(pending['batch']),priority_markets=list(pending['priority_markets']))
        STAGE2_THREAD=threading.Thread(target=_stage2_runner,
            args=(pending['task_url'],pending['result_url'],pending['priority_markets'],pending['workers'],pending['batch']),
            name='pal-v9-stage2-shard1',daemon=True)
        STAGE2_THREAD.start();return True
    except Exception:
        with V9_STAGE2_PENDING_LOCK:
            if V9_STAGE2_PENDING is None:V9_STAGE2_PENDING=pending
        try:STAGE2_LOCK.release()
        except RuntimeError:pass
        try:RUN_LOCK.release()
        except RuntimeError:pass
        raise

def _v9_send_pending_snapshot():
    with V9_SEND_PENDING_LOCK:
        p=dict(V9_SEND_PENDING) if isinstance(V9_SEND_PENDING,dict) else None
    if not p:
        return None
    # Blob URLs are intentionally not exposed in health/state.
    out={'mode':p.get('mode'),'queued_at':p.get('queued_at')}
    if p.get('generation') is not None: out['generation']=p.get('generation')
    if p.get('sender_shard') is not None: out['sender_shard']=p.get('sender_shard')
    return out

def _queue_v9_send(task_url,result_url,mode,generation=0,authority='',failover_control_url='',sender_shard=1):
    global V9_SEND_PENDING
    with V9_SEND_PENDING_LOCK:
        V9_SEND_PENDING={'task_url':task_url,'result_url':result_url,'mode':mode,'generation':int(generation or 0),'authority':str(authority or ''),'failover_control_url':str(failover_control_url or ''),'sender_shard':0 if int(sender_shard or 0)==0 else 1,'queued_at':int(time.time())}
    with V9_SEND_STATE_LOCK:
        if not (V9_SEND_THREAD and V9_SEND_THREAD.is_alive()):
            V9_SEND_STATE.update(status='QUEUED',at=int(time.time()))

def _start_pending_v9_send():
    global V9_SEND_PENDING,V9_SEND_THREAD
    with V9_SEND_PENDING_LOCK:
        pending=dict(V9_SEND_PENDING) if isinstance(V9_SEND_PENDING,dict) else None
    if not pending or (V9_SEND_THREAD and V9_SEND_THREAD.is_alive()):
        return False
    if str(pending.get('mode') or '').upper()=='PRODUCTION':
        auth=str(pending.get('authority') or '')
        g=int(pending.get('generation') or 0)
        control_ok=((auth=='GLOBAL_LEDGER_DO' and _v9_production_authorized(g)) or
                    (auth=='FAILOVER_BLOB_V1' and _v9_failover_authorized(g,pending.get('failover_control_url'))))
        if not control_ok:
            with V9_SEND_PENDING_LOCK:
                if V9_SEND_PENDING is not None: V9_SEND_PENDING=None
            with V9_SEND_STATE_LOCK:
                V9_SEND_STATE.update(status='CONTROL_REVOKED',at=int(time.time()),returncode=None)
            return False
    if not RUN_LOCK.acquire(blocking=False):
        return False
    try:
        with V9_SEND_PENDING_LOCK:
            # Another request may have replaced the pending payload. Take the newest.
            pending=dict(V9_SEND_PENDING) if isinstance(V9_SEND_PENDING,dict) else pending
            V9_SEND_PENDING=None
        with V9_SEND_STATE_LOCK:
            V9_SEND_STATE.update(status='RUNNING',at=int(time.time()),returncode=None)
        V9_SEND_THREAD=threading.Thread(
            target=_v9_send_runner,
            args=(pending['task_url'],pending['result_url'],pending['mode'],int(pending.get('generation') or 0),str(pending.get('authority') or ''),str(pending.get('failover_control_url') or ''),int(pending.get('sender_shard') or 0)),
            name='pal-v9-send',daemon=True)
        V9_SEND_THREAD.start()
        return True
    except Exception:
        with V9_SEND_PENDING_LOCK:
            if V9_SEND_PENDING is None:
                V9_SEND_PENDING=pending
        try: RUN_LOCK.release()
        except RuntimeError: pass
        raise

def _v9_send_runner(task_url,result_url,mode,generation=0,authority='',failover_control_url='',sender_shard=1):
    global V9_SEND_THREAD
    started=time.time()
    try:
        env=os.environ.copy()
        env.update({'PAL_V9_SEND_TASK_BLOB_URL':task_url,'PAL_V9_SEND_RESULT_BLOB_URL':result_url,'PAL_V9_SEND_MODE':mode,'PAL_V9_CUTOVER_GENERATION':str(int(generation or 0)),'PAL_V9_CONTROL_HEALTH_URL':os.environ.get('PAL_V9_CONTROL_HEALTH_URL','https://pal-b2b-v9-plane.jojoagogog.workers.dev/health'),'PAL_V9_PRODUCTION_AUTHORITY':str(authority),'PAL_V9_FAILOVER_CONTROL_URL':str(failover_control_url),'PAL_V9_FAILOVER_SECRET':TOKEN,'PAL_V9_SENDER_SHARD':str(0 if int(sender_shard or 0)==0 else 1),'PAL_V9_SEND_MAX_TASKS':'2','PAL_V9_SEND_CONCURRENCY':'2','PAL_V9_TASK_WALL_TIMEOUT':'180'})
        cp=subprocess.run([sys.executable,str(V9_SEND_WORKER)],env=env,text=True,capture_output=True,timeout=300)
        summary=_worker_summary(cp.stdout or '')
        completed={'status':'PASS' if cp.returncode==0 else 'ERROR','at':int(time.time()),
                   'duration_seconds':round(time.time()-started,2),'returncode':cp.returncode,
                   'summary':summary,'stderr_tail':(cp.stderr or '')[-1600:],'stdout_tail':(cp.stdout or '')[-1600:],
                   'mode':mode}
        with V9_SEND_STATE_LOCK:
            V9_SEND_STATE.update(status=completed['status'],at=completed['at'],duration_seconds=completed['duration_seconds'],
                                 returncode=cp.returncode,run_count=int(V9_SEND_STATE.get('run_count') or 0)+1,
                                 last_summary=summary,last_completed=completed)
    except subprocess.TimeoutExpired:
        completed={'status':'TIMEOUT','at':int(time.time()),'duration_seconds':round(time.time()-started,2),
                   'returncode':None,'summary':{},'mode':mode}
        with V9_SEND_STATE_LOCK:
            V9_SEND_STATE.update(status='TIMEOUT',at=completed['at'],duration_seconds=completed['duration_seconds'],
                                 returncode=None,run_count=int(V9_SEND_STATE.get('run_count') or 0)+1,last_summary={},last_completed=completed)
    except Exception as e:
        with V9_SEND_STATE_LOCK:
            V9_SEND_STATE.update(status='ERROR',at=int(time.time()),duration_seconds=round(time.time()-started,2),
                                 returncode=None,run_count=int(V9_SEND_STATE.get('run_count') or 0)+1,last_summary={'error':type(e).__name__})
    finally:
        V9_SEND_THREAD=None
        try: RUN_LOCK.release()
        except RuntimeError: pass
        # Do not immediately give the scarce shard1 heavy slot back to Browser.
        # The external controller decides the next owner on its next tick and
        # always evaluates safe send inventory before replenishment work.
        # This removes the ~60s Browser quantum from every send batch while
        # preserving RUN_LOCK single-owner safety.
        print(json.dumps({'event':'V9_SEND_STOPPED','handoff':'CONTROLLER_PRIORITY'},separators=(',',':')),flush=True)

def _v9_send_snapshot():
    with V9_SEND_STATE_LOCK:
        out=dict(V9_SEND_STATE)
    t=V9_SEND_THREAD
    out['thread_alive']=bool(t and t.is_alive())
    return out

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
    counts=_browser_queue_lane_counts()
    if isinstance(counts,dict):
        # FAST_DOM is the measured high-yield lane and processes up to three
        # routes serially per Chromium launch. Give any queued FAST_DOM work one
        # quantum before falling back to backlog size; this prevents a large
        # low-yield DYNAMIC_JS backlog from starving a small high-value lane.
        if (int(counts.get('FAST_DOM') or 0)>0
                and float(LANE_SKIP_UNTIL.get('FAST_DOM') or 0)<=now):
            lane='FAST_DOM'
            LANE_EMPTY_STREAK[lane]=0
            return lane
        live=[(int(n or 0),lane) for lane,n in counts.items()
              if int(n or 0)>0 and float(LANE_SKIP_UNTIL.get(lane) or 0)<=now]
        if live:
            live.sort(key=lambda x:(-x[0],x[1]))
            lane=live[0][1]
            LANE_EMPTY_STREAK[lane]=0
            LANE_SKIP_UNTIL[lane]=0.0
            return lane
    fallback=None
    fallback_until=None
    for _ in range(12):
        lane=next(LANES)
        until=float(LANE_SKIP_UNTIL.get(lane) or 0)
        if fallback is None or until < fallback_until:
            fallback,lane_until=lane,until
            fallback_until=lane_until
        if until<=now:
            return lane
    return fallback or next(LANES)

def _record_lane_result(lane,summary,code):
    summary=summary or {}
    routes=int(summary.get('routes') or 0)
    transport=str(summary.get('result_transport') or '')
    status_counts=summary.get('status_counts') or {}
    code_counts=summary.get('code_counts') or {}
    if code>=500:
        return
    # Any route result is useful queue progress, including TECH_DEFER:
    # that route is checkpointed/retry-delayed and the next unique route can run.
    # Cooling a lane after a TECH_DEFER-only batch froze large live backlogs.
    no_productive_output=(routes<=0 or transport=='NO_MESSAGES' or
                          (not status_counts and not code_counts))
    if no_productive_output:
        streak=int(LANE_EMPTY_STREAK.get(lane) or 0)+1
        LANE_EMPTY_STREAK[lane]=streak
        base=LANE_EMPTY_BASE_COOLDOWN_SECONDS*(2**min(streak-1,2))
        if transport=='NO_MESSAGES':
            cooldown=max(180,min(600,base*4))
        else:
            cooldown=max(90,min(360,base*2))
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
        lane_concurrency=max(1,min(4,int(LANE_CONCURRENCY.get(lane,2))))
        lane_deadline=int(LANE_DEADLINE_SECONDS.get(lane,90))
        lane_route_timeout=int(LANE_ROUTE_TIMEOUT_SECONDS.get(lane,24))
        lane_retry_timeout=int(LANE_RETRY_TIMEOUT_SECONDS.get(lane,lane_route_timeout))
        if _valid_blob_url(ACTIVE_TASK_BLOB_URL):
            # Stage3 worker intentionally prefers the Browser-specific variable
            # over the legacy generic route queue. Keep both aligned so a
            # controller-supplied queue can never be shadowed by stale Render
            # environment/default values.
            env['PAL_BROWSER_TASK_BLOB_URL']=ACTIVE_TASK_BLOB_URL
            env['PAL_ROUTE_TASK_BLOB_URL']=ACTIVE_TASK_BLOB_URL
        if _valid_blob_url(ACTIVE_RESULT_BLOB_URL):
            env['PAL_BROWSER_RESULT_BLOB_URL']=ACTIVE_RESULT_BLOB_URL
        env.update({
            'PAL_STAGE3_LANE_MODE':lane,
            'PAL_STAGE3_CONCURRENCY':str(lane_concurrency),
            'PAL_STAGE3_RENDERER_PROCESS_LIMIT':'1',
            'PAL_STAGE3_PRIORITY_MARKETS':','.join(ACTIVE_PRIORITY_MARKETS),
            'PAL_STAGE3_MAX_ROWS':str(lane_max),
            'PAL_STAGE3_ROUTE_TIMEOUT_SECONDS':str(lane_route_timeout),
            'PAL_STAGE3_RETRY_TIMEOUT_SECONDS':str(lane_retry_timeout),
            'PAL_STAGE3_RETRY_LIMIT':'0',
            'PAL_STAGE3_RECENT_ROUTE_SECONDS':'900',
            'PAL_STAGE3_RECENT_TECH_SECONDS':'600',
            # New topology namespace: never inherit task completion IDs from
            # the former single-owner worker after splitting the queue 2 ways.
            'PAL_STAGE3_STATE_FILE':'/tmp/pal_stage3_'+lane.lower()+'_dual_shard_v3.json',
            'PAL_STAGE3_DEADLINE_EPOCH':str(int(time.time())+lane_deadline),
            'PAL_STAGE3_PRODUCER':'PAL_RENDER_STAGE3_BROWSER_V1',
            # Both Render services now participate in Stage3. Primary is
            # shard 0 when its shared Stage2/Stage3 lock is available; shard1 is
            # shard 1 continuously. Deterministic route-id sharding prevents the
            # two services from duplicating Browser work while preserving all
            # proof/safety gates.
            'PAL_STAGE3_SHARD_COUNT':'2',
            'PAL_STAGE3_SHARD_INDEX':('0' if STAGE2_PRIMARY_ROLE else '1'),
        })
        cp=subprocess.run(
            [sys.executable,str(WORKER)],env=env,text=True,
            # A lane must release the single free Render service promptly even
            # if Chromium/Playwright teardown misbehaves. Worker-level route
            # budgets are already <=42s and results stream durably per batch.
            capture_output=True,timeout=190,
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
    crash=None
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
            # Revenue sender outranks Browser proof on both shards. A queued
            # sender gets the next heavy slot after one completed Browser quantum.
            # RUN_LOCK still guarantees Browser and sender never overlap.
            if _v9_send_pending_snapshot() is not None:
                _release_idle_browser_priority()
                with STATE_LOCK:
                    STATE['idle_exit_reason']='YIELD_TO_WAITING_V9_SENDER'
                break
            if not STAGE2_PRIMARY_ROLE and _v9_stage2_pending_snapshot() is not None:
                _release_idle_browser_priority()
                with STATE_LOCK:
                    STATE['idle_exit_reason']='YIELD_TO_WAITING_V9_STAGE2'
                break
            # Primary shares one memory-safe heavy slot with Stage2. Once a
            # valid Stage2 request has waited through one complete Browser
            # quantum, yield the lock so the next controller tick can drain a
            # bounded route batch. Stage2's own lock still prevents overlap,
            # and its completion hands priority back to queued Browser work.
            if (STAGE2_PRIMARY_ROLE and _stage2_demand_remaining()>0
                    and _stage2_fairness_allowed()):
                # Reserve the next lock acquisition for Stage2 only after the
                # shard-0 Browser backlog reaches its low-water mark. Under a
                # deep Stage3 backlog, continuing Browser work is the higher
                # yield use of this single heavy slot; Stage2 remains served by
                # its independent external/fallback lanes.
                _grant_stage2_turn()
                _release_idle_browser_priority()
                with STATE_LOCK:
                    STATE['idle_exit_reason']='YIELD_TO_WAITING_STAGE2'
                break
            tasks=int(summary.get('tasks') or 0)
            routes=int(summary.get('routes') or 0)
            if code>=500:
                time.sleep(min(30,5*max(1,int(_snapshot().get('failure_streak') or 1))))
                continue
            if tasks<=0 and routes<=0:
                idle_rounds+=1
                queued=_browser_queue_has_tasks()
                if queued is False:
                    _release_idle_browser_priority()
                    with STATE_LOCK:
                        STATE['idle_exit_reason']='NO_BROWSER_TASKS'
                    break
                time.sleep(IDLE_SLEEP_SECONDS if idle_rounds>=2 else 2)
            else:
                idle_rounds=0
    except Exception as e:
        crash={'type':type(e).__name__,'detail':str(e)[:240]}
        with STATE_LOCK:
            STATE['status']='ERROR'
            STATE['pump_error']=dict(crash)
            STATE['failure_streak']=int(STATE.get('failure_streak') or 0)+1
            STATE['at']=int(time.time())
        print(json.dumps({'event':'PUMP_CRASHED','error':crash},separators=(',',':')),flush=True)
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
        sender_started=_start_pending_v9_send()
        stage2_started=False if sender_started else _start_pending_v9_stage2()
        print(json.dumps({'event':'PUMP_STOPPED','reason':'CRASH' if crash else 'LEASE_EXPIRED','v9_sender_started':bool(sender_started),'v9_stage2_started':bool(stage2_started)},separators=(',',':')),flush=True)

def start_or_extend(source,priority_markets=None,task_url=None,result_url=None):
    global PUMP_THREAD,ACTIVE_PRIORITY_MARKETS,ACTIVE_TASK_BLOB_URL,ACTIVE_RESULT_BLOB_URL
    if priority_markets is not None:
        clean=[]
        for x in priority_markets:
            x=str(x or '').strip()
            if x and x not in clean: clean.append(x)
        ACTIVE_PRIORITY_MARKETS=clean[:8]
    if task_url is not None:
        if not _valid_blob_url(task_url):
            return {'status':'BAD_TASK_BLOB_URL'},400
        ACTIVE_TASK_BLOB_URL=str(task_url).strip()
    if result_url is not None:
        if not _valid_blob_url(result_url):
            return {'status':'BAD_RESULT_BLOB_URL'},400
        ACTIVE_RESULT_BLOB_URL=str(result_url).strip()
    if source=='MAC_WAKE':
        queued=_browser_queue_has_tasks(ACTIVE_TASK_BLOB_URL)
        if queued is False:
            _release_idle_browser_priority()
            return {'status':'NO_BROWSER_TASKS','source':source,
                    'state':_snapshot()},200
    _note_browser_demand()
    _extend_lease(source)
    if (STAGE2_PRIMARY_ROLE and _stage2_turn_remaining()>0
            and _stage2_demand_remaining()>0):
        return {'status':'BUSY_STAGE2_PRIORITY','source':source,
                'stage2_turn_seconds':round(_stage2_turn_remaining(),1),
                'state':_snapshot()},202
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
    if not STAGE2_PRIMARY_ROLE:
        return jsonify(status='STAGE3_BROWSER_RESERVED',
                       service_role='STAGE3_BROWSER'),409
    body=request.get_json(silent=True) or {}
    task_url=str(body.get('task_url') or '')
    result_url=str(body.get('result_url') or '')
    if not _valid_blob_url(task_url) or not _valid_blob_url(result_url):
        return jsonify(status='BAD_BLOB_URL'),400
    markets=[]
    for x in body.get('priority_markets') or []:
        x=str(x or '').strip()
        if x and x not in markets: markets.append(x)
    workers=max(4,min(24,int(body.get('workers') or 8)))
    batch=max(16,min(128,int(body.get('batch') or 64)))
    _note_stage2_demand()
    # Stage3 Browser owns the scarce Render Free memory lane. Stage2 is useful
    # external I/O work, but it must never overlap Chromium. Browser demand is
    # renewed by every /wake call, so once an in-flight Stage2 run finishes the
    # next cycle yields the shared lock to Stage3 instead of immediately
    # starting another 24-worker Stage2 batch.
    browser_wait=_browser_demand_remaining()
    browser_queued=None
    if _valid_blob_url(ACTIVE_TASK_BLOB_URL):
        browser_queued=_browser_queue_has_tasks(ACTIVE_TASK_BLOB_URL)
    if _stage2_blocked_by_browser(
            browser_wait,browser_queued,bool(PUMP_THREAD and PUMP_THREAD.is_alive())):
        return jsonify(status='BUSY_STAGE3_PRIORITY',
                       browser_demand_seconds=round(browser_wait,1),
                       browser_queue_pending=browser_queued,
                       resource_owner=_resource_owner()),202
    if not STAGE2_LOCK.acquire(blocking=False):
        return jsonify(status='BUSY',state=_stage2_snapshot()),202
    if not RUN_LOCK.acquire(blocking=False):
        try: STAGE2_LOCK.release()
        except RuntimeError: pass
        return jsonify(status='BUSY_STAGE3_PRIORITY',
                       browser_demand_seconds=round(_browser_demand_remaining(),1),
                       resource_owner=_resource_owner()),202
    try:
        _clear_stage2_turn()
        _clear_stage2_demand()
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
    except Exception:
        STAGE2_THREAD=None
        try: STAGE2_LOCK.release()
        except RuntimeError: pass
        try: RUN_LOCK.release()
        except RuntimeError: pass
        raise

@app.get('/stage2-state')
def stage2_state():
    if not allowed():
        return ('unauthorized',401)
    return jsonify(_stage2_snapshot())

@app.post('/v9-stage2-wake')
def v9_stage2_wake():
    """Queue one bounded Stage2 turn on shard1 without preempting Browser/Sender."""
    if not allowed():return ('unauthorized',401)
    if STAGE2_PRIMARY_ROLE:return jsonify(status='V9_STAGE2_SHARD1_ONLY'),409
    payload=request.get_json(silent=True) or {};task_url=str(payload.get('task_url') or '');result_url=str(payload.get('result_url') or '')
    if not _valid_blob_url(task_url) or not _valid_blob_url(result_url):return jsonify(status='BAD_BLOB_URL'),400
    markets=[]
    for x in payload.get('priority_markets') or []:
        x=str(x or '').strip()
        if x and x not in markets:markets.append(x)
    # Shard1 is the only production sender. Keep Stage2 turns short so
    # Browser proof and Sender can reclaim the shared heavy slot promptly.
    workers=max(4,min(8,int(payload.get('workers') or 8)));batch=max(16,min(32,int(payload.get('batch') or 32)))
    _queue_v9_stage2(task_url,result_url,markets,workers,batch)
    if (V9_SEND_THREAD and V9_SEND_THREAD.is_alive()) or _v9_send_pending_snapshot() is not None:
        return jsonify(status='QUEUED_BEHIND_SENDER',revision=V9_STAGE2_SHARD1_REVISION,v9_stage2_pending=_v9_stage2_pending_snapshot()),202
    if PUMP_THREAD and PUMP_THREAD.is_alive():
        return jsonify(status='QUEUED_AFTER_BROWSER_QUANTUM',revision=V9_STAGE2_SHARD1_REVISION,state=_snapshot(),v9_stage2_pending=_v9_stage2_pending_snapshot()),202
    if _start_pending_v9_stage2():
        return jsonify(status='STARTED',revision=V9_STAGE2_SHARD1_REVISION,state=_stage2_snapshot()),202
    return jsonify(status='QUEUED_LOCK_BUSY',revision=V9_STAGE2_SHARD1_REVISION,resource_owner=_resource_owner(),v9_stage2_pending=_v9_stage2_pending_snapshot()),202

@app.get('/health')
def health():
    return jsonify(service='PAL_RENDER_STAGE3_BROWSER_V1',status='PASS',
                   scheduler_revision=SCHEDULER_REVISION,
                   v9_stage2_shard1_revision=(V9_STAGE2_SHARD1_REVISION if not STAGE2_PRIMARY_ROLE else None),
                   v9_strict_static_revision=V9_STRICT_STATIC_REVISION,
                   v9_stage2_pending=(_v9_stage2_pending_snapshot() if not STAGE2_PRIMARY_ROLE else None),
                   external_cron_primary_enabled=True,
                   service_name=SERVICE_NAME,
                   service_role=('STAGE2_STAGE3_DUAL' if STAGE2_PRIMARY_ROLE else 'STAGE3_BROWSER'),
                   worker_protocol='AWAITED_ROUTE_HANDLER_V1',
                   resource_profile='RENDER_FREE_SHARED_LOCK_V5_DYNAMIC_BLOB',
                   exit_policy='BOUNDED_EVENT_LOOP_V1',
                   resource_owner=_resource_owner(),
                   browser_demand_seconds=round(_browser_demand_remaining(),1),
                   stage2_demand_seconds=round(_stage2_demand_remaining(),1),
                   stage2_turn_seconds=round(_stage2_turn_remaining(),1),
                   stage2_busy=bool(STAGE2_THREAD and STAGE2_THREAD.is_alive()),
                   dynamic_blob_override=bool(_valid_blob_url(ACTIVE_TASK_BLOB_URL) and _valid_blob_url(ACTIVE_RESULT_BLOB_URL)),
                   lane_max_rows=LANE_MAX_ROWS,
                   lane_concurrency=LANE_CONCURRENCY,
                   lane_deadline_seconds=LANE_DEADLINE_SECONDS,
                   lane_empty_streak=LANE_EMPTY_STREAK,
                   lane_skip_until=LANE_SKIP_UNTIL,
                   v9_sender_enabled=True,
                   v9_sender_control_revision='DUAL_AUTHORITY_DUAL_SHARD_FAILOVER_V2',
                   v9_sender_worker_revision='V9_SENDER_DEDICATED_2X_V14_TABLE_LABELS_QUERY_CREATED',
                   v9_sender_production_enabled=True,
                   v9_sender_pending=_v9_send_pending_snapshot(),
                   v9_send_state=_v9_send_snapshot(),
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
    # Primary is dual-role: Stage2 and Stage3 never overlap because both use
    # RUN_LOCK. A Stage3 wake received while Stage2 is running records Browser
    # demand, so Stage2 yields the next quantum instead of monopolizing shard 0.
    # This restores the intended two-shard Stage3 topology without extra services.
    payload=request.get_json(silent=True) or {}
    pm=payload.get('priority_markets') if isinstance(payload,dict) else None
    task_url=payload.get('task_url') if isinstance(payload,dict) else None
    result_url=payload.get('result_url') if isinstance(payload,dict) else None
    body,code=start_or_extend('MAC_WAKE',pm,task_url,result_url)
    return jsonify(body),code


@app.post('/v9-send-wake')
def v9_send_wake():
    global V9_SEND_THREAD
    if not allowed():
        return ('unauthorized',401)
    payload=request.get_json(silent=True) or {}
    task_url=str(payload.get('task_url') or '')
    result_url=str(payload.get('result_url') or '')
    mode=str(payload.get('mode') or 'SHADOW').upper();generation=int(payload.get('cutover_generation') or 0);sender_shard=0 if int(payload.get('sender_shard') or 0)==0 else 1
    if mode not in {'SHADOW','PRODUCTION'}:
        return jsonify(status='BAD_MODE'),400
    authority=str(payload.get('production_authority') or '')
    failover_control_url=str(payload.get('failover_control_url') or '')
    if mode=='PRODUCTION':
        cloud_authorized=(authority=='GLOBAL_LEDGER_DO' and _v9_production_authorized(generation))
        failover_authorized=(authority=='FAILOVER_BLOB_V1' and _v9_failover_authorized(generation,failover_control_url))
        if not (cloud_authorized or failover_authorized):
            return jsonify(status='PRODUCTION_LOCKED',cloud_authorized=cloud_authorized,failover_authorized=failover_authorized),403
    if not _valid_blob_url(task_url) or not _valid_blob_url(result_url):
        return jsonify(status='BAD_BLOB_URL'),400
    # Idempotent wake: a retry while the same sender is already running must
    # never enqueue a second sender turn for the same task blob.
    if V9_SEND_THREAD and V9_SEND_THREAD.is_alive():
        return jsonify(status='ALREADY_RUNNING',mode=mode,resource_owner=_resource_owner(),
                       v9_send_state=_v9_send_snapshot()),202
    with V9_SEND_PENDING_LOCK:
        pending=dict(V9_SEND_PENDING) if isinstance(V9_SEND_PENDING,dict) else None
    if pending and pending.get('task_url')==task_url and pending.get('result_url')==result_url and pending.get('mode')==mode and int(pending.get('generation') or 0)==generation and int(pending.get('sender_shard') or 0)==sender_shard:
        return jsonify(status='QUEUED',mode=mode,resource_owner=_resource_owner(),
                       v9_sender_pending=_v9_send_pending_snapshot(),
                       v9_send_state=_v9_send_snapshot(),state=_snapshot()),202
    _queue_v9_send(task_url,result_url,mode,generation,authority,failover_control_url,sender_shard)
    if _start_pending_v9_send():
        return jsonify(status='STARTED',mode=mode,v9_send_state=_v9_send_snapshot()),202
    return jsonify(status='QUEUED',mode=mode,resource_owner=_resource_owner(),
                   v9_sender_pending=_v9_send_pending_snapshot(),
                   v9_send_state=_v9_send_snapshot(),state=_snapshot()),202

@app.get('/v9-send-state')
def v9_send_state():
    if not allowed():
        return ('unauthorized',401)
    return jsonify(state=_v9_send_snapshot(),pending=_v9_send_pending_snapshot(),resource_owner=_resource_owner())

@app.post('/tick')
def tick():
    if not allowed():
        return ('unauthorized',401)
    if STAGE2_PRIMARY_ROLE:
        return jsonify(status='STAGE2_PRIMARY_RESERVED',
                       service_role='STAGE2_PRIMARY'),409
    _note_browser_demand()
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
