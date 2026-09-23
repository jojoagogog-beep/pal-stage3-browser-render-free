from __future__ import annotations
import asyncio, hashlib, json, os, re, ssl, sys, time, traceback, urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

def _transport_secret_config():
    path=Path(os.environ.get('PAL_STAGE3_TRANSPORT_CONFIG_FILE','/etc/secrets/stage3_transport'))
    try:
        obj=json.loads(path.read_text())
        return obj if isinstance(obj,dict) else {}
    except Exception:
        return {}

_TRANSPORT_SECRET=_transport_secret_config()
_DEFAULT_BROWSER_TASK_BLOB='https://superjsonblob.com/api/jsonBlob/cc1b98e3-f44a-4229-b6e2-f96c5a52c8fc'
_DEFAULT_BROWSER_RESULT_BLOB='https://superjsonblob.com/api/jsonBlob/f4776f37-7f0b-469f-86f6-92f94d1de939'
_TASK_BLOB_CANDIDATES=[]
for _u in (
    os.environ.get('PAL_ROUTE_TASK_BLOB_URL',''),
    str(_TRANSPORT_SECRET.get('browser_task_blob_url') or ''),
    _DEFAULT_BROWSER_TASK_BLOB,
):
    _u=str(_u or '').strip()
    if _u and _u not in _TASK_BLOB_CANDIDATES:
        _TASK_BLOB_CANDIDATES.append(_u)
TASK_BLOB=_TASK_BLOB_CANDIDATES[0] if _TASK_BLOB_CANDIDATES else ''
RESULT_BLOB=(os.environ.get('PAL_BROWSER_RESULT_BLOB_URL','')
             or str(_TRANSPORT_SECRET.get('browser_result_blob_url') or '')
             or _DEFAULT_BROWSER_RESULT_BLOB)
STATE=Path(os.environ.get('PAL_STAGE3_STATE_FILE','pal_offload/stage3_send_ready_state_v1.json'))
LANE_MODE=str(os.environ.get('PAL_STAGE3_LANE_MODE','FAST_DOM') or 'FAST_DOM').upper()
PRODUCER=str(os.environ.get('PAL_STAGE3_PRODUCER','PAL_STAGE3_BROWSER_WORKER_V1') or 'PAL_STAGE3_BROWSER_WORKER_V1')
LANE_CONCURRENCY=max(1,min(8,int(os.environ.get('PAL_STAGE3_CONCURRENCY','4') or 4)))
# Local fallback passes bounded budgets so one 8GB-Mac browser lane can finish
# and publish useful proof before the resource supervisor needs to reclaim it.
# GitHub/default runs keep the historical caps when these vars are absent.
MAX_ROWS=max(1,min(240,int(os.environ.get('PAL_STAGE3_MAX_ROWS','240') or 240)))
ROUTE_TIMEOUT_SECONDS=max(8,min(60,int(os.environ.get('PAL_STAGE3_ROUTE_TIMEOUT_SECONDS','46') or 46)))
RETRY_TIMEOUT_SECONDS=max(8,min(75,int(os.environ.get('PAL_STAGE3_RETRY_TIMEOUT_SECONDS','58') or 58)))
RETRY_LIMIT=max(0,min(48,int(os.environ.get('PAL_STAGE3_RETRY_LIMIT','48') or 48)))
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36'
PRIORITY_MARKETS=[x.strip() for x in os.environ.get('PAL_STAGE3_PRIORITY_MARKETS','').split(',') if x.strip()]
# Deterministic multi-service sharding. The default is two shards. Render clones
# inherit the same secret/task-blob config, so derive shard 1 from the service
# name when no explicit shard index is configured. This lets a service whose
# name ends in -v2 become shard 1 without replacing inherited env vars/secrets.
_RENDER_SERVICE_NAME=str(os.environ.get('RENDER_SERVICE_NAME','') or '').lower()
_DEFAULT_SHARD_INDEX='1' if (_RENDER_SERVICE_NAME.endswith('-v2') or 'shard1' in _RENDER_SERVICE_NAME) else '0'
SHARD_COUNT=max(1,min(16,int(os.environ.get('PAL_STAGE3_SHARD_COUNT','2') or 2)))
SHARD_INDEX=max(0,min(SHARD_COUNT-1,int(os.environ.get('PAL_STAGE3_SHARD_INDEX',_DEFAULT_SHARD_INDEX) or _DEFAULT_SHARD_INDEX)))
LOCAL_FALLBACK=os.environ.get('PAL_STAGE3_LOCAL_FALLBACK','').lower() in {'1','true','yes'}
LOCAL_RESULT_DIR=Path(os.environ['PAL_STAGE3_LOCAL_RESULT_DIR']) if LOCAL_FALLBACK and os.environ.get('PAL_STAGE3_LOCAL_RESULT_DIR') else None
_PRIORITY_RANK={m:i for i,m in enumerate(PRIORITY_MARKETS)}

def market_rank(rec):
    return _PRIORITY_RANK.get(str(rec.get('market') or ''),1000)

def shard_accept(rec):
    try: rid=int(rec.get('route_id') or 0)
    except Exception: return False
    return rid>0 and (rid % SHARD_COUNT)==SHARD_INDEX

def task_lane_quality(task):
    vals=[]
    for rec in (task.get('routes') or []):
        if not lane_accept(rec):
            continue
        try:
            vals.append(int(rec.get('stage3_quality') or 0))
        except Exception:
            vals.append(0)
    return max(vals) if vals else -1

def effective_work_deadline(deadline,route_timeout,now=None):
    if deadline is None:
        return None
    base=time.time() if now is None else float(now)
    # The caller's lease/deadline may be mostly consumed by a cold Chromium
    # launch. Once a route batch has been selected, guarantee one bounded
    # primary Browser pass so the run cannot return NO_MESSAGES solely because
    # browser startup was slow. The parent process still owns the hard cap.
    return max(float(deadline),base+max(8.0,float(route_timeout))+5.0)

def task_market_rank(task):
    return min((market_rank(r) for r in (task.get('routes') or [])),default=1000)

RECENT_ROUTE_SECONDS=max(60,min(3600,int(os.environ.get('PAL_STAGE3_RECENT_ROUTE_SECONDS','600') or 600)))
RECENT_TECH_SECONDS=max(60,min(1800,int(os.environ.get('PAL_STAGE3_RECENT_TECH_SECONDS','600') or 600)))
RECENT_SAFE_SECONDS=max(60,min(540,int(os.environ.get('PAL_STAGE3_RECENT_SAFE_SECONDS','420') or 420)))

def route_cache_key(rec):
    raw='|'.join((
        str(int(rec.get('route_id') or 0)),
        str(rec.get('canonical_url') or ''),
        str(rec.get('static_status') or ''),
    ))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def recent_route_blocked(rec,recent,now_epoch=None):
    entry=(recent or {}).get(route_cache_key(rec))
    if not isinstance(entry,dict):return False
    now_epoch=int(now_epoch or time.time())
    status=str(entry.get('status') or '')
    code=str(entry.get('code') or '')
    if status=='TECH_DEFER':
        ttl=RECENT_TECH_SECONDS
    elif status=='SAFE_RENDERED_STATIC' and code in {'REMOTE_FULL_SEND_READY_V3','REMOTE_FULL_STATIC_READY_V3'}:
        # Browser proof expires after ~10m and dispatcher refreshes at ~8m.
        # Let a proven route be revalidated before TTL expiry instead of
        # suppressing the refresh until the proof is already stale.
        ttl=RECENT_SAFE_SECONDS
    else:
        ttl=RECENT_ROUTE_SECONDS
    return int(entry.get('at') or 0)>=now_epoch-ttl

def remember_route(rec,result,recent,now_epoch=None):
    recent[route_cache_key(rec)]={
        'at':int(now_epoch or time.time()),
        'route_id':int(rec.get('route_id') or 0),
        'status':str(result.get('status') or 'UNKNOWN'),
        'code':str(result.get('code') or 'UNKNOWN'),
    }

try:
    import certifi
    SSL_CONTEXT=ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CONTEXT=ssl.create_default_context()
CAPTCHA=re.compile(r'(g-recaptcha|grecaptcha|recaptcha/api|hcaptcha|h-captcha|challenges\.cloudflare\.com|cf-turnstile|turnstile/v0|captcha)',re.I)
CAPTCHA_SELECTOR='iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],.g-recaptcha,.h-captcha,.cf-turnstile,[data-sitekey]'
PROHIBIT=re.compile(r'(no\s+(?:unsolicited|sales\s+solicit)|sales\s+solicitations?.{0,30}(?:not\s+accepted|prohibited|declin|refus)|(?:営業(?:目的|勧誘|メール|メ[ー－-]ル)|ご?提案|セールス).{0,40}(?:禁止|お断り|受け付け(?:て)?おりません|受付(?:して)?おりません|ご遠慮))',re.I)
SENSITIVE=re.compile(r'(電話|\btel\b|\bphone\b|mobile|\b(?:full|contact|telephone|phone)[ _.-]?number\b|住所|\baddress\b|郵便|postal|postcode|\bzip\b|都道府県|市区町村|番地)',re.I)
MARKETING=re.compile(r'(newsletter|marketing|メルマガ|広告|キャンペーン)',re.I)
CONSENT=re.compile(r'(privacy|terms|agree|consent|同意|プライバシー|利用規約|個人情報)',re.I)
FINAL=re.compile(r'(この内容で送信|内容を送信|送信する|送信|send\s*(message|inquiry|enquiry)?|submit\s*(message|inquiry|enquiry|form)?)',re.I)
NONFINAL=re.compile(r'(確認|confirm|next|次へ|preview|戻る|back|cancel|修正)',re.I)
CONFIRM=re.compile(r'(確認画面(?:へ)?|入力内容(?:を)?確認|内容(?:を)?確認|確認(?:する|へ)?|confirm|review|next|次へ)',re.I)


def lane_accept(rec):
    st=str(rec.get('static_status') or '')
    try: rid=int(rec.get('route_id') or 0)
    except Exception: rid=0
    if LANE_MODE=='FAST_DOM':
        return st=='STATIC_FORM_CANDIDATE'
    if LANE_MODE=='DYNAMIC_JS':
        return st=='DYNAMIC_HINT_CANDIDATE'
    if LANE_MODE=='IFRAME_DEEP':
        return st in {'','NO_MESSAGE_FORM'} and (rid % 2 == 0)
    if LANE_MODE=='DEEP':
        return st in {'TECH_DEFER','SAFETY_CANDIDATE'} or (st in {'','NO_MESSAGE_FORM'} and rid % 2 == 1)
    return True

def host(u):
    try:return (urlsplit(str(u or '')).hostname or '').lower().removeprefix('www.')
    except Exception:return ''

def www_fallback_url(u,official_domain):
    """Retry only the www alias of the same official apex host.

    Some official sites publish only www DNS/TLS while discovery normalizes the
    company domain by removing www. This preserves scheme/path/query and never
    crosses the official-domain boundary or disables TLS verification.
    """
    try:
        p=urlsplit(str(u or ''))
        raw=(p.hostname or '').lower()
        official=str(official_domain or '').lower().removeprefix('www.')
        if not raw or raw.startswith('www.') or raw!=official:
            return ''
        port=(':'+str(p.port)) if p.port else ''
        return urlunsplit((p.scheme,'www.'+raw+port,p.path,p.query,p.fragment))
    except Exception:
        return ''

def load_state():
    try:return json.loads(STATE.read_text())
    except Exception:return {}

def save_state(done,counts,recent_routes=None):
    now_epoch=int(time.time())
    recent=dict(recent_routes or {})
    cutoff=now_epoch-max(RECENT_ROUTE_SECONDS,RECENT_TECH_SECONDS)*2
    recent={k:v for k,v in recent.items()
            if isinstance(v,dict) and int(v.get('at') or 0)>=cutoff}
    if len(recent)>2000:
        recent=dict(sorted(recent.items(),key=lambda kv:int(kv[1].get('at') or 0))[-2000:])
    STATE.write_text(json.dumps({
      'updated_at_epoch':now_epoch,
      'processed_task_ids':list(done)[-1000:],
      'recent_route_results':recent,
      'last_status_counts':counts,
    },indent=2,sort_keys=True)+'\n')

def blob_get(url):
    # SuperJSONBlob may be served through caches. Always force a fresh read so
    # a just-published Stage-3 queue is not mistaken for an empty queue.
    sep='&' if '?' in url else '?'
    fresh=url+sep+'_pal_ts='+str(time.time_ns())
    q=urllib.request.Request(fresh,headers={
      'User-Agent':UA,'Accept':'application/json',
      'Cache-Control':'no-cache, no-store','Pragma':'no-cache'})
    with urllib.request.urlopen(q,timeout=15,context=SSL_CONTEXT) as r:
        raw=r.read(25000001)
    if len(raw)>25000000:
        raise RuntimeError('BLOB_TOO_LARGE')
    return json.loads(raw.decode('utf-8','ignore'))

def blob_put(url,obj):
    data=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode()
    q=urllib.request.Request(url,data=data,method='PUT',headers={
      'Content-Type':'application/json','User-Agent':UA,
      'Cache-Control':'no-cache, no-store'})
    with urllib.request.urlopen(q,timeout=20,context=SSL_CONTEXT) as r:r.read(10000)

def task_messages():
    if not _TASK_BLOB_CANDIDATES:
        print(json.dumps({'stage3_task_diag':{'error':'NO_TASK_BLOB'}}))
        return []
    last_error=None
    source_diags=[]
    out=[]
    source_index=None
    for idx,url in enumerate(_TASK_BLOB_CANDIDATES):
        try:
            q=blob_get(url)
        except Exception as e:
            last_error={'error':type(e).__name__,'detail':str(e)[:220],'source_index':idx}
            continue
        all_tasks=[m for m in (q.get('tasks') or []) if isinstance(m,dict)]
        browser=[m for m in all_tasks if m.get('kind')=='PAL_BROWSER_PREFLIGHT_TASK_V1']
        source_diags.append({'source_index':idx,'all_tasks':len(all_tasks),'browser_tasks':len(browser)})
        if browser:
            out=browser
            source_index=idx
            break
    if not out:
        diag={'sources':source_diags,'browser_tasks':0}
        if last_error:diag['last_error']=last_error
        print(json.dumps({'stage3_task_diag':diag}))
        return []
    print(json.dumps({'stage3_task_diag':{
        'source_index':source_index,'sources_checked':len(source_diags),
        'all_tasks':source_diags[-1]['all_tasks'],'browser_tasks':len(out)}}))
    seen=set();ded=[]
    for m in out:
        tid=str(m.get('task_id') or '')
        if not tid or tid in seen:continue
        seen.add(tid);ded.append(m)
    return ded

def publish(msgs):
    if not msgs:return 'NO_MESSAGES'
    if LOCAL_FALLBACK and LOCAL_RESULT_DIR is not None:
        try:
            LOCAL_RESULT_DIR.mkdir(parents=True,exist_ok=True)
            for msg in msgs:
                rid=int(msg.get('route_id') or 0)
                if rid<=0 or msg.get('kind')!='PAL_BROWSER_PREFLIGHT_V1':
                    raise ValueError('INVALID_LOCAL_BROWSER_RESULT')
                path=LOCAL_RESULT_DIR/(str(time.time_ns())+'-'+str(rid)+'.json')
                tmp=path.with_suffix('.tmp')
                with tmp.open('x',encoding='utf-8') as f:
                    json.dump(msg,f,ensure_ascii=False,separators=(',',':'))
                    f.flush();os.fsync(f.fileno())
                os.replace(tmp,path)
            return 'LOCAL_DURABLE_SPOOL_V1'
        except Exception as exc:
            print(json.dumps({'event':'LOCAL_PROOF_SAVE_FAILED','error':type(exc).__name__}),flush=True)
            return 'NO_RESULT_TRANSPORT'
    if not RESULT_BLOB:return 'NO_RESULT_TRANSPORT'
    try:
        q=blob_get(RESULT_BLOB)
        prior=[x for x in (q.get('messages') or []) if isinstance(x,dict)]
        keys={(str(x.get('kind') or ''),int(x.get('route_id') or 0)) for x in msgs}
        prior=[x for x in prior if (str(x.get('kind') or ''),int(x.get('route_id') or 0)) not in keys]
        blob_put(RESULT_BLOB,{'schema':'PAL_BROWSER_RESULT_QUEUE_V1','updated_at_epoch':int(time.time()),
                              'messages':(prior+msgs)[-512:]})
        return 'SUPERJSONBLOB_V1'
    except Exception:return 'NO_RESULT_TRANSPORT'

def base_result(rec):
    return {'kind':'PAL_BROWSER_PREFLIGHT_V1','route_id':int(rec.get('route_id') or 0),
      'market':str(rec.get('market') or ''),'official_domain':str(rec.get('official_domain') or '').lower().removeprefix('www.'),
      'last_seen_epoch':int(time.time()),'pages_checked':1,'proof_version':'STAGE3_FULL_SEND_READY_V3','lane_mode':LANE_MODE,
      'producer':PRODUCER}

async def sticky_fill(loc,value):
    target=str(value)
    try:
        await loc.fill(target)
    except Exception:
        pass
    try:
        if str(await loc.input_value())==target:
            return
    except Exception:
        pass
    await loc.evaluate(r"""(e,v)=>{
      const proto=e.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype :
                  (e.tagName==='SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype);
      const d=Object.getOwnPropertyDescriptor(proto,'value');
      if(!d||!d.set) throw new Error('NO_NATIVE_VALUE_SETTER');
      d.set.call(e,v);
      e.dispatchEvent(new Event('input',{bubbles:true}));
      e.dispatchEvent(new Event('change',{bubbles:true}));
    }""",target)
    try:
        if str(await loc.input_value())==target:
            return
    except Exception:
        pass
    raise RuntimeError('STICKY_FILL_FAILED')

async def visible_captcha(root):
    """Block only an actually rendered captcha/challenge, not a dormant script."""
    try:
        loc=root.locator(CAPTCHA_SELECTOR)
        for i in range(min(await loc.count(),12)):
            try:
                if await loc.nth(i).is_visible():
                    box=await loc.nth(i).bounding_box()
                    if box and box.get('width',0)>4 and box.get('height',0)>4:
                        return True
            except Exception:
                pass
        body=(await root.locator('body').inner_text())[:12000]
        if re.search(r'(verify you are human|prove you are human|human verification|current year.{0,50}(?:human|prove)|anti[- ]?spam.{0,40}(?:question|check|challenge)|checking your browser|complete the security check|captcha challenge|画像認証|画像内.{0,30}(?:文字列|文字|コード)|認証コード.{0,20}(?:画像|入力)|画像認証.{0,30}(?:正しくありません|必須))',body,re.I):
            return True
    except Exception:
        pass
    return False

async def inspect(browser,rec,sem,slow=False):
    async with sem:
        base=base_result(rec); rid=base['route_id'];url=str(rec.get('canonical_url') or '');domain=base['official_domain']
        if not rid or not url or not domain or host(url)!=domain:
            return {**base,'status':'TECH_DEFER','code':'INVALID_TASK','stage3_send_ready':False}
        ctx=None
        timeout_phase='context_init'
        try:
            ctx=await browser.new_context(user_agent=UA,ignore_https_errors=False)
            # Await routing decisions directly instead of spawning an untracked
            # asyncio task for every network request. The old create_task callback
            # left Playwright response/routing tasks alive after Browser work had
            # already been durably published; asyncio.run() then spent ~100s
            # draining them before the worker process could exit. This changes
            # resource handling only, never proof/safety semantics.
            async def route_request(route):
                if route.request.resource_type in {'image','media','font'}:
                    await route.abort()
                else:
                    await route.continue_()
            await ctx.route('**/*', route_request)
            deep_lane=LANE_MODE in {'DYNAMIC_JS','IFRAME_DEEP','DEEP'}
            page=await ctx.new_page(); page.set_default_timeout(9000 if (slow or deep_lane) else 5500)
            # Keep navigation inside the route-level wall-clock budget, including
            # one bounded apex->www retry. This prevents the outer asyncio.wait_for
            # from expiring before Playwright can return a meaningful verdict.
            route_budget_ms=max(8000,int(ROUTE_TIMEOUT_SECONDS*1000))
            nav_timeout=max(7000,min(18000,int(route_budget_ms*0.38)))
            async def navigate_ready(target):
                # A committed main document is enough to enter the bounded render
                # wait below. Requiring <body> immediately after commit caused
                # valid JS-heavy pages to burn 5s and return BROWSER_TIMEOUT before
                # their normal lane wait had a chance to hydrate the DOM.
                await page.goto(target,wait_until='commit',timeout=nav_timeout)
                try:
                    await page.wait_for_load_state(
                        'domcontentloaded',
                        timeout=max(2500,min(6000,nav_timeout//3)),
                    )
                except PlaywrightTimeoutError:
                    pass
            try:
                timeout_phase='navigate'
                await navigate_ready(url)
            except Exception as nav_exc:
                # Discovery stores company domains normalized without www.
                # Some official sites have no apex DNS or an apex certificate
                # mismatch but serve the identical route correctly on www.
                # Retry only that same-domain alias; never disable TLS checks.
                nav_error=str(nav_exc)
                fallback=www_fallback_url(url,domain)
                if (fallback and re.search(
                        r'net::ERR_(?:NAME_NOT_RESOLVED|CERT_COMMON_NAME_INVALID)',
                        nav_error,re.I)):
                    await navigate_ready(fallback)
                else:
                    raise
            # Four lane modes share the same safety gates but inspect different
            # render depths so one DOM assumption cannot dominate all results.
            try:
                lane_wait={'FAST_DOM':900,'DYNAMIC_JS':1800,'IFRAME_DEEP':1500,'DEEP':2600}.get(LANE_MODE,1200)
                if slow: lane_wait=max(lane_wait,2200)
                await page.wait_for_timeout(lane_wait)
                if LANE_MODE in {'DYNAMIC_JS','DEEP'} or slow:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1600 if LANE_MODE!='DEEP' else 2400)
                    await page.evaluate("window.scrollTo(0, 0)")
            except Exception:pass
            final_url=page.url
            if host(final_url)!=domain:
                return {**base,'status':'DOMAIN_CHANGED','code':'DOMAIN_CHANGED','final_url':final_url,'stage3_send_ready':False}
            timeout_phase='body_text'
            text=str(await page.evaluate(
                "() => ((document.body && document.body.innerText) || "
                "(document.documentElement && document.documentElement.innerText) || '')"
            ))[:180000]
            if not text.strip():
                return {**base,'status':'TECH_DEFER','code':'DOM_TEXT_EMPTY',
                        'final_url':final_url,'stage3_send_ready':False,
                        'timeout_phase':'body_text','lane_mode':LANE_MODE}
            if PROHIBIT.search(text):
                return {**base,'status':'SALES_PROHIBITED','code':'SALES_PROHIBITED','final_url':final_url,'stage3_send_ready':False}
            if await visible_captcha(page):
                return {**base,'status':'CAPTCHA','code':'VISIBLE_CAPTCHA','final_url':final_url,'stage3_send_ready':False}

            # Bounded structural diagnostics for false NO_SAFE_FORM analysis.
            # Never records field values or submitted content.
            scan_debug=[]

            async def scan_root(root,frame_index):
                try:
                    root_html=await root.content()
                    root_text=(await root.locator('body').inner_text())[:180000]
                except Exception:
                    root_html=''; root_text=''
                if PROHIBIT.search(root_text):
                    return None
                if await visible_captcha(root):
                    return None
                forms=root.locator('form'); n=min(await forms.count(),20); best_local=None
                root_diag={'frame_index':int(frame_index),'form_count':int(n),'evaluate_errors':0,'forms':[]}
                if len(scan_debug)<20:
                    scan_debug.append(root_diag)
                for i in range(n):
                    form=forms.nth(i)
                    try:
                        meta=await form.evaluate("""f=>{
                          const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return !e.disabled&&e.type!=='hidden'&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
                          const desc=e=>{const id=e.id||'',lab=id?document.querySelector('label[for="'+CSS.escape(id)+'"]'):null;
                            const labels=e.labels?[...e.labels].map(x=>x.innerText||'').join(' '):'';
                            const tr=e.closest('tr'),cell=e.closest('th,td');let rowLabel='';
                            if(tr&&cell){const cells=[...tr.children],idx=cells.indexOf(cell);
                              rowLabel=((idx>0?cells.slice(0,idx).map(c=>c.innerText||'').join(' '):'')||(tr.querySelector('th')?.innerText||'')).trim();}
                            const dd=e.closest('dd');
                            if(!rowLabel&&dd&&dd.previousElementSibling&&dd.previousElementSibling.tagName==='DT')
                              rowLabel=(dd.previousElementSibling.innerText||'').trim();
                            if(!rowLabel){const box=e.closest('.form-item-box,.form-group,.form-row,.field');
                              const h=box&&box.querySelector('dt,.field-label,.form-label,.label');
                              if(h)rowLabel=(h.innerText||'').trim();}
                            const w=e.closest('label,.form-group,.form-row,.field,li,dl,dd,dt,p')||e.parentElement;
                            let local=((lab&&lab.innerText)||labels||((w&&w.innerText)||'')).trim();if(local.length>300)local='';
                            const self=[e.name||'',id,e.placeholder||'',e.getAttribute('aria-label')||'',(lab&&lab.innerText)||'',labels].join(' ');
                            return {self:self.slice(0,500),local:local.slice(0,500),rowLabel:rowLabel.slice(0,500)};
                          };
                          const allFields=[...f.querySelectorAll('input,textarea,select')];
                          const fs=allFields.map((e,all_i)=>({e,all_i})).filter(x=>vis(x.e)).map(({e,all_i})=>{const d=desc(e);
                            const reqText=(d.self+' '+d.rowLabel+' '+d.local);
                            const req=!!e.required||e.getAttribute('aria-required')==='true'||/(?:^|\\s)required(?:\\s|$)/i.test(String(e.className||''))||/[※＊*]\\s*$/.test(d.rowLabel)||(/(必須|required|mandatory)/i.test(reqText)&&!/(任意|optional)/i.test(reqText));
                            return {i:all_i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),name:e.name||'',id:e.id||'',required:req,
                              checked:!!e.checked,value:e.value||'',self_desc:d.self.slice(0,500),local_desc:d.local.slice(0,500),row_label:d.rowLabel.slice(0,500),
                              desc:(d.self+' '+d.rowLabel+' '+d.local).slice(0,900)}});
                          const controls=[...f.querySelectorAll('button,input[type=submit],input[type=button],input[type=image]')].filter(vis)
                            .map((e,i)=>({i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),
                              text:((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.name||'')+' '+(e.id||'')).trim()}));
                          return {text:(f.innerText||'').slice(0,12000),action:f.action||'',method:(f.method||'get').toLowerCase(),ident:((f.id||'')+' '+(f.className||'')+' '+(f.action||'')).slice(0,1000),fields:fs,controls};
                        }""")
                    except Exception:
                        root_diag['evaluate_errors']=int(root_diag.get('evaluate_errors') or 0)+1
                        continue
                    blob=(str(meta.get('text') or '')+' '+str(meta.get('ident') or '')).lower()
                    ident_blob=str(meta.get('ident') or '').lower()
                    form_text=str(meta.get('text') or '').lower()
                    form_action=str(meta.get('action') or '').strip()
                    # mailto/tel/javascript actions are not web-form outreach.
                    # They cannot satisfy the Stage-3 -> Stage-4 web-submit contract.
                    if re.match(r'^(?:mailto|tel|javascript):',form_action,re.I):
                        continue
                    # Reject forms whose structure itself identifies a non-contact
                    # purpose. Do not reject a genuine contact form merely because
                    # its option text contains words such as "career" or "research".
                    if re.search(r'(?:^|[ _.-])(searchform|search-form|newsletter-form|subscribe-form|login-form|loginform|comment-form|commentform|review-form|job-application|career-application|recruitment-form)(?:$|[ _.-])',ident_blob,re.I):
                        continue
                    if re.search(r'(upload.{0,24}(?:resume|résumé|cv)|job application|employment application|apply.{0,24}(?:job|position|vacancy)|採用応募|求人応募)',form_text,re.I):
                        continue
                    fields=list(meta.get('fields') or [])
                    has_email=any(str(x.get('type') or '')=='email' or re.search(r'(e-?mail|メール)',str(x.get('desc') or ''),re.I) for x in fields)
                    has_msg=any(str(x.get('tag') or '')=='textarea' or re.search(r'(message|inquir|enquir|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)',str(x.get('desc') or ''),re.I) for x in fields)
                    form_diag={'index':int(i),'field_count':len(fields),
                               'has_email':bool(has_email),'has_message':bool(has_msg),
                               'ident':str(meta.get('ident') or '')[:180]}
                    if len(root_diag['forms'])<20:
                        root_diag['forms'].append(form_diag)
                    if not (has_email and has_msg):
                        form_diag['decision']='NO_EMAIL_OR_MESSAGE'
                        continue
                    ctrls=list(meta.get('controls') or [])
                    form_diag['control_count']=len(ctrls)
                    # A visible type=submit control on a verified contact form is a
                    # final control even when branded text says "Get in touch",
                    # "Contact us", etc. Exclude explicit Next/Confirm/Back controls.
                    direct=[x for x in ctrls
                            if not NONFINAL.search(str(x.get('text') or ''))
                            and (
                                FINAL.search(str(x.get('text') or ''))
                                or str(x.get('type') or '')=='submit'
                            )
                            and not (str(x.get('tag') or '')=='input' and str(x.get('type') or '') in {'button','image'})]
                    confirm=[x for x in ctrls if CONFIRM.search(str(x.get('text') or ''))]
                    safe_confirm=[]
                    for x in confirm:
                        tx=str(x.get('text') or '')
                        if re.search(r'(この内容で送信|内容を送信|送信する|確認して送信|送信$|\bsend\b|\bsubmit\b|確定)',tx,re.I):
                            continue
                        if CONFIRM.search(tx):
                            safe_confirm.append(x)
                    form_diag['direct_submit_count']=len(direct)
                    form_diag['safe_confirm_count']=len(safe_confirm)
                    if not direct and not safe_confirm:
                        form_diag['decision']='NO_SAFE_SUBMIT_CONTROL'
                        continue
                    form_diag['decision']='CANDIDATE'
                    # Do not reject a valid contact form only because its HTML method
                    # is GET or omitted. Many modern forms submit through JavaScript/AJAX.
                    # Email + message fields, explicit submit/confirm control, same-domain,
                    # captcha/prohibition checks, and full fillability remain mandatory.
                    kind='DIRECT_SUBMIT' if direct else 'CONFIRM_STEP'
                    chosen_control=direct[0] if direct else safe_confirm[0]
                    score=10+(3 if direct else 2)+(2 if re.search(r'(会社|法人|company|organization)',blob,re.I) else 0)
                    cand={'index':i,'fields':fields,'control':chosen_control,'control_kind':kind,'score':score,'frame_index':frame_index}
                    if best_local is None or score>best_local['score']:
                        best_local=cand
                return best_local

            frame_cap=20 if LANE_MODE in {'IFRAME_DEEP','DEEP'} else (12 if LANE_MODE=='DYNAMIC_JS' else 8)
            timeout_phase='form_scan'
            roots=list(page.frames)[:frame_cap]
            best=None
            # A valid direct-submit contact form is already sufficient once the
            # page/root safety gates above have passed. Do not keep scanning every
            # iframe after finding one: slow third-party frames were consuming the
            # entire route wall-clock budget and converting good routes into
            # OVERALL_ROUTE_TIMEOUT_OR_ERROR. Per-root timeouts are fail-closed;
            # a hung frame is skipped, never accepted.
            per_root_timeout=6.0 if LANE_MODE in {'IFRAME_DEEP','DEEP'} else 4.0
            for frame_index,root in enumerate(roots):
                try:
                    cand=await asyncio.wait_for(scan_root(root,frame_index),timeout=per_root_timeout)
                except Exception:
                    cand=None
                if cand and (best is None or cand['score']>best['score']):
                    best=cand
                if best and str(best.get('control_kind') or '')=='DIRECT_SUBMIT' and int(best.get('score') or 0)>=13:
                    break
            if not best:
                return {**base,'status':'NO_SAFE_FORM','code':'NO_DIRECT_SEND_READY_FORM',
                        'final_url':final_url,'stage3_send_ready':False,
                        'form_scan_debug':scan_debug[:20]}

            active_root=roots[int(best.get('frame_index') or 0)]
            forms=active_root.locator('form')
            form=forms.nth(int(best['index']))
            sensitive_required=[]
            unfillable=[]
            # Required radios are group requirements. Choose only a semantically
            # safe general/other/business-inquiry option; otherwise fail closed.
            radio_groups={}
            for rr in best['fields']:
                if str(rr.get('type') or '')=='radio' and bool(rr.get('required')):
                    key=str(rr.get('name') or ('__radio_'+str(rr.get('i'))))
                    radio_groups.setdefault(key,[]).append(rr)
            for _key,members in radio_groups.items():
                if any(bool(x.get('checked')) for x in members):
                    continue
                pick=next((x for x in members if
                    re.search(r'(その他|一般|法人|問い合わせ|business|other|general|new inquiry|service inquiry|request information|no preference|not applicable)',
                              str(x.get('desc') or ''),re.I)
                    and not re.search(r'(newsletter|marketing|メルマガ|広告|キャンペーン|電話|phone|住所|address)',
                                      str(x.get('desc') or ''),re.I)),None)
                if pick is None:
                    unfillable.append(str(members[0].get('desc') or 'required_radio')[:120])
                else:
                    try:
                        await form.locator('input,textarea,select').nth(int(pick['i'])).check()
                    except Exception:
                        unfillable.append(str(pick.get('desc') or 'required_radio')[:120])
            for row in best['fields']:
                i=int(row['i']);typ=str(row.get('type') or '');tag=str(row.get('tag') or '');desc=str(row.get('desc') or '')
                req=bool(row.get('required')); loc=form.locator('input,textarea,select').nth(i)
                self_desc=str(row.get('self_desc') or '')
                row_label=str(row.get('row_label') or '')
                identity=(str(row.get('name') or '')+' '+str(row.get('id') or '')+' '+self_desc+' '+row_label).strip()
                # Sensitive-field detection must use the field itself, not a broad
                # parent block that may also contain neighboring labels.
                sensitive_field=(typ=='tel' or bool(SENSITIVE.search(identity)))
                if sensitive_field:
                    if req:sensitive_required.append(identity[:120] or desc[:120])
                    continue
                if typ=='file':
                    if req:unfillable.append(desc[:120] or 'required_file')
                    continue
                if typ=='checkbox':
                    is_marketing=bool(MARKETING.search(desc))
                    is_consent=bool(CONSENT.search(desc))
                    if is_consent and not is_marketing:
                        try:await loc.check()
                        except Exception:
                            if req or is_consent:unfillable.append(desc[:120] or 'consent_checkbox')
                    elif req:
                        # Never opt into marketing/newsletters or unknown required choices.
                        unfillable.append(desc[:120] or 'required_checkbox')
                    continue
                if typ=='radio':
                    continue
                if tag=='select':
                    if not req:continue
                    try:
                        opts=await loc.locator('option').evaluate_all("os=>os.map(o=>({v:o.value||'',t:(o.innerText||'').trim()}))")
                        pick=next((o['v'] for o in opts if o.get('v') and re.search(
                            r'(お問い合わせ|その他|一般|法人|ご提案|協業|business|other|general|partnership|new inquiry|service inquiry|request information|no preference|not applicable)',
                            str(o.get('t') or ''),re.I)),None)
                        if pick:await loc.select_option(value=pick)
                        else:unfillable.append(desc[:120] or 'required_select')
                    except Exception:unfillable.append(desc[:120] or 'required_select')
                    continue
                value=None
                if tag=='textarea' or re.search(r'(message|inquir|enquir|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細|description)',desc,re.I):value='Business inquiry validation'
                elif typ=='email' or re.search(r'(e-?mail|メール)',desc,re.I):value='validation@example.com'
                elif re.search(r'(会社|法人|企業|company|organization|organisation)',desc,re.I):value='Practical AI Lab'
                elif re.search(r'(ふりがな|ひらがな)',desc,re.I):value='ぷらくてぃかるえーあいらぼ'
                elif re.search(r'(フリガナ|カナ|kana)',desc,re.I):value='プラクティカルエーアイラボ'
                elif re.search(r'(姓|苗字|名字|surname|family[ _.-]?name|last[ _.-]?name|\blname\b|(?:^|[\[\]_.-])last(?:$|[\[\]_.-]))',desc,re.I):value='Practical'
                elif re.search(r'(名|given[ _.-]?name|first[ _.-]?name|\bfname\b|(?:^|[\[\]_.-])first(?:$|[\[\]_.-]))',desc,re.I):value='AI Lab'
                elif re.search(r'(氏名|お名前|名前|担当者|full.?name|contact.?name|\bname\b)',desc,re.I):value='Practical AI Lab'
                elif re.search(r'(件名|subject|title)',desc,re.I):value='Business inquiry'
                elif re.search(r'(部署|部門|department|designation)',desc,re.I):value='Operations'
                elif re.search(r'(url|website|ホームページ)',desc,re.I):value='https://practical-ai-lab.pages.dev/'
                elif req and typ=='text':value='Practical AI Lab'
                if value is not None:
                    try:await sticky_fill(loc,value)
                    except Exception:
                        if req:unfillable.append(desc[:120] or 'fill_failed')
                elif req and not str(row.get('value') or '').strip():
                    unfillable.append(desc[:120] or 'unknown_required')

            if sensitive_required:
                return {**base,'status':'REQUIRED_SENSITIVE','code':'REQUIRED_SENSITIVE','final_url':final_url,
                        'required_sensitive':True,'stage3_send_ready':False,'blocked_fields':sensitive_required[:6]}
            if unfillable:
                return {**base,'status':'REQUIRED_UNFILLABLE','code':'REQUIRED_UNFILLABLE','final_url':final_url,
                        'required_sensitive':False,'required_unfillable':True,'stage3_send_ready':False,'blocked_fields':unfillable[:6]}
            valid=await form.evaluate("f=>f.checkValidity()")
            if not valid:
                invalid=await form.locator(':invalid').evaluate_all("els=>els.slice(0,8).map(e=>(e.name||e.id||e.type||e.tagName).slice(0,120))")
                return {**base,'status':'REQUIRED_UNFILLABLE','code':'BROWSER_CONSTRAINT_INVALID','final_url':final_url,
                        'required_unfillable':True,'stage3_send_ready':False,'blocked_fields':invalid}

            # Dynamic frameworks may reveal/mark fields required only after input
            # events or hydration. Re-scan the rendered form after all guarded
            # fills so Stage3 uses the same final-form semantics expected at send.
            try:
                post=await scan_root(active_root,int(best.get('frame_index') or 0))
            except Exception:
                post=None
            post_same=(isinstance(post,dict)
                       and int(post.get('index') or -1)==int(best.get('index') or -2))
            if not post_same:
                # The pre-fill form/control observation is not sufficient for a
                # FULL proof. Dynamic frameworks can disable/remove/replace the
                # submit control after guarded input events. If the selected form
                # is no longer independently discoverable with an enabled
                # submit/confirm control, fail closed instead of reusing stale
                # pre-fill metadata.
                return {**base,'status':'TECH_DEFER','code':'POST_FILL_CONTROL_NOT_READY',
                        'final_url':final_url,'stage3_send_ready':False,
                        'send_ready_proof_v2':False}
            post_sensitive=[]
            for row in list(post.get('fields') or []):
                if not bool(row.get('required')):
                    continue
                typ=str(row.get('type') or '')
                identity=(str(row.get('name') or '')+' '+str(row.get('id') or '')+' '+
                          str(row.get('self_desc') or '')+' '+str(row.get('row_label') or '')).strip()
                if typ=='tel' or SENSITIVE.search(identity):
                    post_sensitive.append(identity[:120] or str(row.get('desc') or '')[:120])
            if post_sensitive:
                return {**base,'status':'REQUIRED_SENSITIVE','code':'REQUIRED_SENSITIVE_POST_FILL',
                        'final_url':final_url,'required_sensitive':True,'required_unfillable':False,
                        'stage3_send_ready':False,'blocked_fields':post_sensitive[:6]}
            if await visible_captcha(active_root) or await visible_captcha(page):
                return {**base,'status':'CAPTCHA','code':'VISIBLE_CAPTCHA_AFTER_FILL','final_url':final_url,'stage3_send_ready':False}
            # Use the post-fill control, never the pre-fill snapshot. This keeps
            # Stage3's FULL proof aligned with the exact DOM state Stage5 sees
            # after filling the same required fields.
            control=post['control']
            control_kind=str(post.get('control_kind') or 'DIRECT_SUBMIT')
            if control_kind=='CONFIRM_STEP':
                target=str(control.get('text') or '')
                clicked=False
                # Use a real Playwright click. DOM element.click() can be ignored by
                # form frameworks that require a trusted pointer event, leaving us
                # on the input page and falsely reporting no final submit control.
                controls_loc=form.locator('button,input[type=submit],input[type=button],input[type=image]')
                for ci in range(min(await controls_loc.count(),40)):
                    loc2=controls_loc.nth(ci)
                    try:
                        if not await loc2.is_visible() or await loc2.is_disabled():
                            continue
                        tx=await loc2.evaluate("e=>((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.name||'')+' '+(e.id||'')).trim()")
                        if str(tx)==target:
                            await loc2.click(timeout=7000)
                            clicked=True
                            break
                    except Exception:
                        continue
                if not clicked:
                    return {**base,'status':'TECH_DEFER','code':'CONFIRM_CONTROL_NOT_FOUND','final_url':final_url,'stage3_send_ready':False}
                try:
                    await page.wait_for_load_state('domcontentloaded',timeout=5000)
                except Exception:
                    pass
                try:
                    await page.wait_for_timeout(700)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(700)
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(500)
                except Exception:pass
                final_url=page.url
                if host(final_url)!=domain:
                    return {**base,'status':'DOMAIN_CHANGED','code':'DOMAIN_CHANGED_AFTER_CONFIRM','final_url':final_url,'stage3_send_ready':False}
                current_roots=list(page.frames)[:frame_cap]
                all_ctrls=[]; prohibited=False; captcha_after=False
                for fi,root2 in enumerate(current_roots):
                    try:
                        if await visible_captcha(root2): captcha_after=True
                    except Exception: pass
                    try:
                        text3=(await root2.locator('body').inner_text())[:180000]
                        if PROHIBIT.search(text3): prohibited=True
                    except Exception: pass
                    try:
                        xs=await root2.locator('button,input[type=submit],input[type=button],input[type=image]').evaluate_all(r"""els=>els.map((e,i)=>{
                          const s=getComputedStyle(e),r=e.getBoundingClientRect(); const visible=!e.disabled&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
                          return {i,visible,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),text:((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.name||'')+' '+(e.id||'')).trim()};
                        }).filter(x=>x.visible)""")
                        for x in xs: x['frame_index']=fi
                        all_ctrls.extend(xs)
                    except Exception: pass
                if prohibited:
                    return {**base,'status':'SALES_PROHIBITED','code':'SALES_PROHIBITED_AFTER_CONFIRM','final_url':final_url,'stage3_send_ready':False}
                if captcha_after:
                    return {**base,'status':'CAPTCHA','code':'VISIBLE_CAPTCHA_AFTER_CONFIRM','final_url':final_url,'stage3_send_ready':False}
                finals=[x for x in all_ctrls if FINAL.search(str(x.get('text') or ''))
                        and (not NONFINAL.search(str(x.get('text') or '')) or re.search(r'(確認して送信|確認のうえ送信|confirm.{0,12}send|send.{0,12}confirm)',str(x.get('text') or ''),re.I))
                        and not (str(x.get('tag') or '')=='input' and str(x.get('type') or '') in {'button','image'})]
                if not finals:
                    fallback=[x for x in all_ctrls
                              if not NONFINAL.search(str(x.get('text') or ''))
                              and not re.search(r'(コメント|comment|レビュー|review|reset|clear)',str(x.get('text') or ''),re.I)
                              and (str(x.get('tag') or '')=='button' or str(x.get('type') or '')=='submit')]
                    if len(fallback)==1:
                        finals=fallback
                if not finals:
                    return {**base,'status':'TECH_DEFER','code':'FINAL_SUBMIT_CONTROL_NOT_FOUND_AFTER_CONFIRM','final_url':final_url,'stage3_send_ready':False}
                control=finals[0]
                control_kind='CONFIRM_THEN_DIRECT_SUBMIT'
            proof_fields=list(((post or {}).get('fields') if isinstance(post,dict) else None) or best.get('fields') or [])
            field_schema=[]
            for row in proof_fields[:32]:
                if not isinstance(row,dict) or row.get('visible') is False:
                    continue
                field_schema.append({k:row.get(k) for k in ('id','name','tag','type','required','desc') if k in row})
            schema_has_email=any(str(x.get('type') or '')=='email' or re.search(r'(e-?mail|メール)',str(x.get('desc') or ''),re.I) for x in field_schema)
            schema_has_message=any(str(x.get('tag') or '')=='textarea' or re.search(r'(message|inquir|enquir|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)',str(x.get('desc') or ''),re.I) for x in field_schema)
            if not field_schema or not schema_has_email or not schema_has_message:
                return {**base,'status':'TECH_DEFER','code':'INCOMPLETE_FIELD_SCHEMA','final_url':final_url,
                        'stage3_send_ready':False,'send_ready_proof_v2':False}
            return {**base,'status':'SAFE_RENDERED_STATIC','code':'REMOTE_FULL_SEND_READY_V3','final_url':final_url,
                    'required_sensitive':False,'required_unfillable':False,'confirm_step':control_kind!='DIRECT_SUBMIT',
                    'captcha_present':False,'sales_prohibited':False,
                    'stage3_send_ready':True,'send_ready_proof_v2':True,'required_fillable':True,
                    'business_contact_form':True,'control_kind':control_kind,'proof_source':'RENDERED_BROWSER_V2',
                    'lane_mode':LANE_MODE,'field_schema':field_schema,
                    'form_fingerprint':hashlib.sha256((final_url+'|frame='+str(best.get('frame_index') or 0)+'|'+str(best['index'])+'|'+str(control.get('text') or '')).encode()).hexdigest(),
                    'frame_index':int(best.get('frame_index') or 0),
                    'form_index':int(best.get('index') or 0),
                    'submit_text':str(control.get('text') or '')[:300]}
        except PlaywrightTimeoutError as e:
            return {**base,'status':'TECH_DEFER','code':'BROWSER_TIMEOUT','stage3_send_ready':False,
                    'timeout_phase':timeout_phase,'error_detail':str(e)[:300],'lane_mode':LANE_MODE}
        except Exception as e:
            return {**base,'status':'TECH_DEFER','code':'BROWSER_ERROR_'+type(e).__name__,
                    'error_detail':str(e)[:300],'lane_mode':LANE_MODE,'stage3_send_ready':False}
        finally:
            if ctx:
                try:await ctx.close()
                except Exception:pass

def _count_results(results):
    counts={}
    for x in results:
        st=str(x.get('status') or 'UNKNOWN')
        counts[st]=counts.get(st,0)+1
    return counts

async def amain():
    perf_start=time.monotonic()
    perf={}
    # A caller (e.g. the local Mac fallback, which runs this worker with
    # LANE_CONCURRENCY=1 against a hard external wall-clock cap) may set this
    # to force the worker to stop starting new work and exit cleanly -- with
    # its "done" bookkeeping saved -- well before an external SIGTERM. Without
    # this, an externally killed run loses ALL processed_task_ids bookkeeping
    # (it was previously written only once, at the very end), so every future
    # run re-fetches and re-inspects the exact same slow routes forever.
    deadline_raw=os.environ.get('PAL_STAGE3_DEADLINE_EPOCH','').strip()
    deadline=float(deadline_raw) if deadline_raw else None

    state=load_state();done=set(state.get('processed_task_ids') or [])
    recent_routes=dict(state.get('recent_route_results') or {})
    perf['load_state_ms']=round((time.monotonic()-perf_start)*1000,1)
    perf_fetch=time.monotonic()
    raw_tasks=task_messages()
    perf['task_fetch_ms']=round((time.monotonic()-perf_fetch)*1000,1)
    pending=[m for m in raw_tasks if str(m.get('task_id') or '') not in done]
    pending=[m for _,m in sorted(enumerate(pending),key=lambda im:(task_market_rank(im[1]),-task_lane_quality(im[1]),im[0]))]
    # Local fallback owns one expensive Browser process. With market-pure tasks,
    # hard-filter it to the controller's short-lived proof markets so one quantum
    # ends as soon as the currently-sendable markets are done. Remote/default
    # workers retain portfolio behavior.
    if LOCAL_FALLBACK and PRIORITY_MARKETS:
        pset=set(PRIORITY_MARKETS)
        pending=[m for m in pending if (set(str(r.get('market') or '') for r in (m.get('routes') or [])) or {''}).issubset(pset)]
    print(json.dumps({'stage3_pending_diag':{'raw_browser_tasks':len(raw_tasks),'done_ids':len(done),'pending_browser_tasks':len(pending),
      'priority_markets':PRIORITY_MARKETS,'max_rows':MAX_ROWS,'route_timeout_seconds':ROUTE_TIMEOUT_SECONDS,'retry_timeout_seconds':RETRY_TIMEOUT_SECONDS,'retry_limit':RETRY_LIMIT,
      'shard_index':SHARD_INDEX,'shard_count':SHARD_COUNT}}))
    # Dispatcher already ranks currently open markets first. Preserve shared-queue
    # order so closed-market quality scores cannot starve sendable live-market work.
    # Four logical lanes run concurrently on one free runner. Route each
    # candidate to the inspection style best suited to its prior static evidence.
    chosen=[];rows=[];seen=set();seen_routes=set();recent_skipped=0
    immediate_done=[]  # tasks with zero lane-eligible routes: trivially complete
    task_boundaries=[]  # (task_id, end_index_in_rows), in the order tasks were added
    for m in pending[:64]:
        tid=str(m.get('task_id') or '')
        if not tid or tid in seen:continue
        part=[];part_ids=set()
        ranked=sorted(list(m.get('routes') or [])[:12],key=lambda r:(market_rank(r),-int(r.get('stage3_quality') or 0)))
        for rec in ranked:
            try: rid=int(rec.get('route_id') or 0)
            except Exception: rid=0
            if rid<=0 or rid in seen_routes or rid in part_ids or not shard_accept(rec) or not lane_accept(rec):continue
            if recent_route_blocked(rec,recent_routes):
                recent_skipped+=1
                continue
            part_ids.add(rid);part.append(rec)
        if not part:
            seen.add(tid);chosen.append(m);immediate_done.append(tid);continue
        # MAX_ROWS is a hard per-run route budget. Older code let the first
        # eligible task bypass this cap (up to 12 routes), which made a nominal
        # 2-row Render run process 6-8 routes and hit the 190s outer timeout.
        # Partial tasks are safe: do NOT checkpoint the task as done; completed
        # routes enter recent_route_results, so the next run skips them and
        # continues with the remaining routes without duplicate Browser work.
        remaining=max(0,MAX_ROWS-len(rows))
        if remaining<=0:
            break
        selected=part[:remaining]
        for rec in selected:
            seen_routes.add(int(rec.get('route_id') or 0))
        seen.add(tid);chosen.append(m);rows.extend(selected)
        if len(selected)==len(part):
            task_boundaries.append((tid,len(rows)))
        if len(selected)<len(part) or len(rows)>=MAX_ROWS:
            break
    perf['selection_ms']=round((time.monotonic()-perf_start)*1000-perf.get('load_state_ms',0)-perf.get('task_fetch_ms',0),1)
    perf['pre_browser_total_ms']=round((time.monotonic()-perf_start)*1000,1)
    if not rows:
        # Tasks with no lane-eligible routes must still be checkpointed as done,
        # or they are re-fetched and re-scanned on every future run forever.
        if immediate_done:
            done.update(immediate_done)
            save_state(done,{'_note':'no_eligible_routes_this_lane'},recent_routes)
        perf['total_ms']=round((time.monotonic()-perf_start)*1000,1)
        print(json.dumps({'status':'PASS','tasks':0,'routes':0,'status_counts':{},
                          'recent_routes_skipped':recent_skipped,'timings':perf}));return
    done.update(immediate_done)
    sem=asyncio.Semaphore(LANE_CONCURRENCY);results=[]
    bnd_ptr=0
    transport='NO_RESULT_TRANSPORT'
    publish_ms=0.0
    async with async_playwright() as pw:
        exe=''
        for p in ('/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser',
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Chromium.app/Contents/MacOS/Chromium'):
            if Path(p).exists():exe=p;break
        if not exe:
            print(json.dumps({'status':'NO_BROWSER','tasks':0,'routes':0}));return
        browser_launch_started=time.monotonic()
        browser=await pw.chromium.launch(
            executable_path=exe,headless=True,args=[
                '--no-sandbox','--disable-dev-shm-usage','--disable-gpu',
                # Keep the single Playwright browser lane small on the 8GB host.
                # None of these flags changes DOM/form semantics; they only suppress
                # background browser services and cap renderer fan-out.
                '--renderer-process-limit='+str(max(1,min(8,int(os.environ.get('PAL_STAGE3_RENDERER_PROCESS_LIMIT','1') or 1)))),
                '--disable-background-networking',
                '--disable-component-update',
                '--disable-default-apps',
                '--disable-extensions',
                '--disable-sync',
                '--metrics-recording-only',
                '--no-first-run',
                '--disable-breakpad',
                '--disable-domain-reliability',
                '--disable-client-side-phishing-detection',
            ])
        perf['browser_launch_ms']=round((time.monotonic()-browser_launch_started)*1000,1)
        if deadline is not None:
            old_deadline=float(deadline)
            deadline=effective_work_deadline(deadline,ROUTE_TIMEOUT_SECONDS)
            perf['deadline_extension_seconds']=round(max(0.0,deadline-old_deadline),1)
        deadline_hit=False
        try:
            for i in range(0,len(rows),LANE_CONCURRENCY):
                if deadline and time.time()>deadline:
                    deadline_hit=True
                    break
                batch=rows[i:i+LANE_CONCURRENCY]
                got=await asyncio.gather(
                    *(asyncio.wait_for(inspect(browser,r,sem),timeout=ROUTE_TIMEOUT_SECONDS) for r in batch),
                    return_exceptions=True,
                )
                for rec,out in zip(batch,got):
                    if isinstance(out,BaseException):
                        b=base_result(rec)
                        value={**b,'status':'TECH_DEFER','code':'OVERALL_ROUTE_TIMEOUT_OR_ERROR',
                               'stage3_send_ready':False,'error_type':type(out).__name__,
                               'error_detail':repr(out)[:240]}
                    else:
                        value=out
                    results.append(value)
                    remember_route(rec,value,recent_routes)
                # Stream every completed batch immediately. A later runner
                # timeout must never discard Browser proofs already completed.
                publish_started=time.monotonic()
                batch_transport=publish(results[-len(batch):])
                publish_ms+=(time.monotonic()-publish_started)*1000
                if batch_transport not in {'SUPERJSONBLOB_V1','LOCAL_DURABLE_SPOOL_V1'}:
                    raise RuntimeError('BROWSER_RESULT_NOT_DURABLE')
                transport=batch_transport
                # Checkpoint every task whose full route set just completed, so
                # an external kill after this point cannot lose this progress:
                # the next run's `pending` naturally excludes it via `done`.
                newly=[]
                while bnd_ptr<len(task_boundaries) and task_boundaries[bnd_ptr][1]<=len(results):
                    newly.append(task_boundaries[bnd_ptr][0]);bnd_ptr+=1
                if newly:
                    done.update(newly)
                    save_state(done,_count_results(results),recent_routes)

            # Bounded second-pass verifier. Technical failures always retry.
            # If the independent static detector saw a form but Browser pass 1
            # returned NO_SAFE_FORM, retry with slower rendering/lazy-load scroll.
            # Skipped once the deadline has already been reached: it is
            # strictly additive quality work, never required for the rows
            # already checkpointed above.
            retry_idx=[] if (deadline and time.time()>deadline) else [
                i for i,x in enumerate(results)
                if str(x.get('status') or '')=='TECH_DEFER'
                or (
                    str(x.get('status') or '')=='NO_SAFE_FORM'
                    and str(rows[i].get('static_status') or '') in
                        {'STATIC_FORM_CANDIDATE','DYNAMIC_HINT_CANDIDATE'}
                )
            ][:RETRY_LIMIT]
            if retry_idx:
                retry_n=max(1,min(2,LANE_CONCURRENCY))
                retry_sem=asyncio.Semaphore(retry_n)
                for j in range(0,len(retry_idx),retry_n):
                    if deadline and time.time()>deadline:
                        break
                    idxs=retry_idx[j:j+retry_n]
                    got=await asyncio.gather(
                        *(asyncio.wait_for(inspect(browser,rows[i],retry_sem,slow=True),timeout=RETRY_TIMEOUT_SECONDS) for i in idxs),
                        return_exceptions=True,
                    )
                    changed=[]
                    for idx,out in zip(idxs,got):
                        if isinstance(out,BaseException):continue
                        old_status=str(results[idx].get('status') or '')
                        new_status=str(out.get('status') or '')
                        if new_status!=old_status or out.get('stage3_send_ready') is True:
                            results[idx]=out
                            changed.append(out)
                    if changed:
                        publish_started=time.monotonic()
                        changed_transport=publish(changed)
                        publish_ms+=(time.monotonic()-publish_started)*1000
                        if changed_transport in {'SUPERJSONBLOB_V1','LOCAL_DURABLE_SPOOL_V1'}:
                            transport=changed_transport
        finally:
            close_started=time.monotonic()
            try:
                await asyncio.wait_for(browser.close(),timeout=5)
            except Exception:
                pass
            perf['browser_close_ms']=round((time.monotonic()-close_started)*1000,1)
    counts={};codes={};samples={}
    for x in results:
        st=str(x.get('status') or 'UNKNOWN'); cd=str(x.get('code') or 'UNKNOWN')
        counts[st]=counts.get(st,0)+1; codes[cd]=codes.get(cd,0)+1
        samples.setdefault(cd,[])
        if len(samples[cd])<5:samples[cd].append(int(x.get('route_id') or 0))
    # Primary results were already durably streamed batch-by-batch above.
    # Do not GET+merge+PUT the entire result set a second time here: that duplicate
    # network round trip doubled tail latency and could keep the Render subprocess
    # alive long after the Browser work had finished.
    perf['publish_ms']=round(publish_ms,1)
    # Only tasks whose full route set actually got a result belong in `chosen`
    # for the done-marking below; a deadline-triggered early break can leave a
    # tail of `chosen` tasks with no results at all -- those must remain
    # pending, not be marked done, or their routes would be lost forever.
    completed_task_ids={tid for tid,end in task_boundaries if end<=len(results)}
    if transport!='NO_RESULT_TRANSPORT':
        # Mark each published task consumed. TECH_DEFER routes are retried by the
        # authoritative local dispatcher after its retry interval. Keeping the
        # whole task pending caused safe/terminal routes in the same task to be
        # re-run repeatedly and reduced unique Stage-3 throughput.
        for m in chosen:
            tid=str(m.get('task_id') or '')
            if tid not in immediate_done and tid not in completed_task_ids:continue
            if tid:done.add(tid)
    for rec,result in zip(rows,results):
        remember_route(rec,result,recent_routes)
    save_state(done,{**counts,'_result_transport':transport},recent_routes)
    perf['total_ms']=round((time.monotonic()-perf_start)*1000,1)
    perf['browser_and_publish_ms']=round(perf['total_ms']-perf.get('pre_browser_total_ms',0),1)
    print(json.dumps({'status':'PASS','tasks':len(chosen),'routes':len(rows),
      'status_counts':counts,'code_counts':codes,'code_samples':samples,
      'recent_routes_skipped':recent_skipped,'result_transport':transport,'timings':perf}))

def _run_main():
    # asyncio.run() waits for every residual task to finish cancellation. With
    # Playwright, response/transport bookkeeping can survive after browser.close()
    # and durable result/state publication, keeping a free Render slot occupied
    # for another ~100s. amain() has already closed the browser and saved all
    # authoritative output before it returns, so cancel residual bookkeeping
    # tasks without waiting indefinitely for their teardown.
    loop=asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    code=0
    try:
        loop.run_until_complete(amain())
    except BaseException:
        traceback.print_exc()
        code=1
    finally:
        pending=[t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in pending:
            t.cancel()
        try:
            loop.run_until_complete(asyncio.sleep(0))
        except BaseException:
            pass
        loop.close()
        try: sys.stdout.flush(); sys.stderr.flush()
        except Exception: pass
    return code

if __name__=='__main__':
    raise SystemExit(_run_main())
