from __future__ import annotations
import itertools, json, os, subprocess, sys, threading, time
from pathlib import Path
from flask import Flask, jsonify, request

HERE=Path(__file__).resolve().parent
WORKER=HERE/'stage3_send_ready_worker_v1.py'
TOKEN=os.environ.get('PAL_RENDER_TOKEN','')
LANES=itertools.cycle(('DYNAMIC_JS','IFRAME_DEEP','DEEP','FAST_DOM'))
LOCK=threading.Lock()
STATE_LOCK=threading.Lock()
STATE={'status':'IDLE','lane':None,'at':0,'duration_seconds':0,'returncode':None}
app=Flask(__name__)

def allowed():
    got=request.headers.get('x-pal-token','')
    return bool(TOKEN and got==TOKEN)

def execute_lane(lane):
    started=time.time()
    try:
        env=os.environ.copy()
        env.update({
            'PAL_STAGE3_LANE_MODE':lane,
            # Render free instance is the off-host browser lane. Two Chromium
            # routes in parallel stay bounded while removing the hard 1-row/tick
            # ceiling that limited Stage3 to roughly one route per minute.
            'PAL_STAGE3_CONCURRENCY':'2',
            'PAL_STAGE3_MAX_ROWS':'2',
            'PAL_STAGE3_ROUTE_TIMEOUT_SECONDS':'55',
            'PAL_STAGE3_RETRY_TIMEOUT_SECONDS':'55',
            'PAL_STAGE3_RETRY_LIMIT':'0',
            'PAL_STAGE3_RECENT_ROUTE_SECONDS':'900',
            'PAL_STAGE3_RECENT_TECH_SECONDS':'180',
            'PAL_STAGE3_STATE_FILE':'/tmp/pal_stage3_'+lane.lower()+'.json',
            'PAL_STAGE3_DEADLINE_EPOCH':str(int(time.time())+180),
            'PAL_STAGE3_PRODUCER':'PAL_RENDER_STAGE3_BROWSER_V1',
        })
        cp=subprocess.run(
            [sys.executable,str(WORKER)],env=env,text=True,
            capture_output=True,timeout=190,
        )
        out=(cp.stdout or '')[-5000:]
        err=(cp.stderr or '')[-1500:]
        body={
            'status':'PASS' if cp.returncode==0 else 'ERROR',
            'lane':lane,'returncode':cp.returncode,
            'duration_seconds':round(time.time()-started,2),
            'stdout_tail':out[-1800:],'stderr_tail':err[-600:],
        }
        code=200 if cp.returncode==0 else 500
    except subprocess.TimeoutExpired:
        body={'status':'TIMEOUT','lane':lane,
              'duration_seconds':round(time.time()-started,2)}
        code=504
    except Exception as e:
        body={'status':'ERROR','lane':lane,'error':type(e).__name__,
              'duration_seconds':round(time.time()-started,2)}
        code=500
    with STATE_LOCK:
        STATE.clear()
        STATE.update({k:v for k,v in body.items() if k not in ('stdout_tail','stderr_tail')})
        STATE['at']=int(time.time())
    return body,code

def background_lane(lane):
    try:
        execute_lane(lane)
    finally:
        LOCK.release()

@app.get('/health')
def health():
    with STATE_LOCK:
        state=dict(STATE)
    return jsonify(service='PAL_RENDER_STAGE3_BROWSER_V1',status='PASS',
                   worker_state=state)

@app.get('/state')
def state():
    if not allowed():
        return ('unauthorized',401)
    with STATE_LOCK:
        return jsonify(dict(STATE))

@app.post('/wake')
def wake():
    if not allowed():
        return ('unauthorized',401)
    if not LOCK.acquire(blocking=False):
        with STATE_LOCK:
            state=dict(STATE)
        return jsonify(status='BUSY',state=state),202
    lane=next(LANES)
    with STATE_LOCK:
        STATE.clear()
        STATE.update(status='RUNNING',lane=lane,at=int(time.time()),
                     duration_seconds=0,returncode=None)
    threading.Thread(target=background_lane,args=(lane,),daemon=True).start()
    return jsonify(status='STARTED',lane=lane),202

@app.post('/tick')
def tick():
    if not allowed():
        return ('unauthorized',401)
    if not LOCK.acquire(blocking=False):
        return jsonify(status='BUSY'),202
    lane=next(LANES)
    with STATE_LOCK:
        STATE.clear()
        STATE.update(status='RUNNING',lane=lane,at=int(time.time()),
                     duration_seconds=0,returncode=None)
    try:
        body,code=execute_lane(lane)
        return jsonify(body),code
    finally:
        LOCK.release()
