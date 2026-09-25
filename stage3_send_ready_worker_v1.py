from __future__ import annotations
import asyncio, hashlib, json, os, re, ssl, sys, time, traceback, urllib.request
from itertools import zip_longest
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
# Stage3 Browser must consume the Browser-specific queue. Older Render service
# environments still carry PAL_ROUTE_TASK_BLOB_URL pointing at the generic
# Stage2 route queue; giving that legacy variable first priority makes a healthy
# Browser worker report tasks=0 forever while the real Browser queue fills.
# Prefer an explicit Browser variable/transport secret/default first, and keep
# the legacy generic route variable only as the final compatibility fallback.
for _u in (
    os.environ.get('PAL_BROWSER_TASK_BLOB_URL',''),
    str(_TRANSPORT_SECRET.get('browser_task_blob_url') or ''),
    _DEFAULT_BROWSER_TASK_BLOB,
    os.environ.get('PAL_ROUTE_TASK_BLOB_URL',''),
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
PROOF_VERSION='STAGE3_FULL_SEND_READY_V4'
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

def route_shard(route_id, shard_count=SHARD_COUNT):
    try: rid=int(route_id or 0); count=max(1,int(shard_count))
    except Exception: return -1
    if rid<=0:return -1
    # Same stable shard function as app.py queue probes. Using the hash rather
    # than raw route-id parity prevents one Render clone from receiving almost
    # the entire queue when route IDs are parity-skewed.
    return hashlib.sha256(str(rid).encode('ascii')).digest()[0] % count

def shard_accept(rec):
    try: rid=int(rec.get('route_id') or 0)
    except Exception: return False
    return rid>0 and route_shard(rid,SHARD_COUNT)==SHARD_INDEX

def stage3_navigation_timeout_ms(route_timeout_seconds,lane_mode,slow=False):
    budget=max(8000,int(float(route_timeout_seconds)*1000))
    lane=str(lane_mode or 'FAST_DOM').upper()
    cap={'FAST_DOM':10000,'DYNAMIC_JS':13000,'IFRAME_DEEP':15000,'DEEP':18000}.get(lane,12000)
    fraction={'FAST_DOM':0.25,'DYNAMIC_JS':0.30,'IFRAME_DEEP':0.33,'DEEP':0.38}.get(lane,0.30)
    if slow:cap=max(cap,15000)
    return max(6000,min(cap,int(budget*fraction)))

def task_eligible_routes(task):
    return [
        rec for rec in (task.get('routes') or [])
        if isinstance(rec,dict) and lane_accept(rec)
    ]

def task_has_shard_work(task):
    return any(shard_accept(rec) and lane_accept(rec)
               for rec in (task.get('routes') or []) if isinstance(rec,dict))

def task_lane_quality(task):
    vals=[]
    for rec in task_eligible_routes(task):
        try:
            vals.append(int(rec.get('stage3_quality') or 0))
        except Exception:
            vals.append(0)
    return max(vals) if vals else -1

def task_admitted_count(task):
    return sum(int(rec.get('admitted_rank') or 0) for rec in task_eligible_routes(task))

def route_yield_class(rec):
    if bool(rec.get('prior_rendered_success')):
        return 0
    if int(rec.get('admitted_rank') or 0)>0:
        return 1
    if bool(rec.get('force_rendered')):
        return 2
    rq=int(rec.get('stage2_route_quality') or 0)
    sendq=int(rec.get('stage2_static_sendability') or 0)
    if rq>=85 or sendq>=70:
        return 3
    static_status=str(rec.get('static_status') or '')
    static_quality=int(rec.get('static_quality') or 0)
    form_shape=int(rec.get('form_shape_signal') or 0)
    expansion=int(rec.get('expansion_signal') or 0)
    if (static_status=='STATIC_FORM_CANDIDATE'
            or form_shape>0 or expansion>0 or static_quality>=60):
        return 4
    if int(rec.get('retry_rank') or 0)>=2:
        return 5
    return 6

def route_work_rank(rec):
    return (
        market_rank(rec),
        route_yield_class(rec),
        -int(bool(rec.get('force_rendered'))),
        -int(rec.get('stage2_route_quality') or 0),
        -int(rec.get('stage2_static_sendability') or 0),
        -int(rec.get('static_quality') or 0),
        -int(rec.get('stage3_quality') or 0),
        int(rec.get('route_id') or 0),
    )

def task_best_route_rank(task):
    rows=task_eligible_routes(task)
    if not rows:
        return (999,1,0,0,0,0,10**12)
    # Market rank is handled by the round-robin outer scheduler.
    return min(route_work_rank(r)[1:] for r in rows)

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

def rank_pending_tasks(pending,priority_markets):
    """Order fetched tasks for one bounded worker lease.

    A flat quality sort (highest task_lane_quality first, portfolio-wide) let
    one PRIORITY_MARKETS entry with more ADMITTED/high-quality tasks (e.g.
    JP-JA, weighted +20000 per admitted route in stage3_quality) consume this
    worker's entire lease before a market with a far larger backlog (e.g.
    GB-EN) got a single task -- even though every PRIORITY_MARKETS entry is
    simultaneously sendable right now. Live evidence (2026-09-23/24):
    JP-JA took 18/30 dispatches in a 30-minute window while GB-EN, the
    largest open-market backlog, took 4. Sort each priority market's own
    tasks by quality first (ADMITTED conversions still lead within their own
    market), then round-robin one task per market so a bounded lease reaches
    every priority market before taking a second task from any single one.
    Non-priority-market tasks keep the prior flat quality sort, appended
    after the priority block -- they are not simultaneously sendable with
    each other so cross-market starvation does not apply to them.
    """
    pset=set(priority_markets or [])
    def _task_market(t):
        for r in (t.get('routes') or []):
            m=str(r.get('market') or '')
            if m:return m
        return str(t.get('market') or '')
    priority=[t for t in pending if _task_market(t) in pset]
    other=[t for t in pending if _task_market(t) not in pset]
    other=[m for _,m in sorted(
        enumerate(other),
        key=lambda im:(task_best_route_rank(im[1]),task_market_rank(im[1]),im[0]),
    )]
    by_market={}
    for idx,t in enumerate(priority):
        by_market.setdefault(_task_market(t),[]).append((idx,t))
    for m in by_market:
        by_market[m].sort(key=lambda im:(task_best_route_rank(im[1]),im[0]))
    cycle=[m for m in priority_markets if m in by_market]
    cycle.extend(m for m in by_market if m not in cycle)
    lists=[[t for _,t in by_market[m]] for m in cycle]
    interleaved=[t for group in zip_longest(*lists) for t in group
                 if t is not None] if lists else []
    return interleaved+other

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
    if rec.get('force_reproof') is True:
        return False
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
HUMAN_CHALLENGE=re.compile(r'(help\s+us\s+prevent\s+spam|anti[- ]?spam|spam\s+(?:check|question|protection)|security\s+(?:question|check)|human\s+(?:check|verification)|which\s+is\s+(?:bigger|larger|smaller)|what\s+is\s+\d+\s*[+\-x×*]\s*\d+|solve\s+(?:this|the)\s+(?:math|equation)|simple\s+(?:math|question)|\bquiz\b)',re.I)
PROHIBIT=re.compile(r'(no\s+(?:unsolicited|sales\s+solicit)|sales\s+solicitations?.{0,30}(?:not\s+accepted|prohibited|declin|refus)|(?:営業(?:目的|勧誘|メール|メ[ー－-]ル)|ご?提案|セールス).{0,40}(?:禁止|お断り|受け付け(?:て)?おりません|受付(?:して)?おりません|ご遠慮))',re.I)
SENSITIVE=re.compile(r'(電話|\btel\b|\bphone\b|mobile|\b(?:full|contact|telephone|phone)[ _.-]?number\b|住所|\baddress\b|郵便|postal|postcode|\bzip\b|都道府県|市区町村|番地)',re.I)
EMAIL_CLIENT_FORM=re.compile(r'(opens?\s+(?:in\s+)?(?:your\s+)?email\s+client|email\s+draft.{0,50}(?:ready|send)|hit\s+send\s+in\s+(?:your\s+)?mail\s+client|mailto:)',re.I)
MARKETING=re.compile(r'(newsletter|marketing|マーケティング|メルマガ|広告|キャンペーン|販促|プロモーション)',re.I)
CONSENT=re.compile(r'(privacy|terms|agree|consent|同意|プライバシー|利用規約|個人情報)',re.I)
CONSENT_GATE=re.compile(
    r'(同意(?:の)?上.{0,30}(?:送信|問い合わせ)|同意して.{0,30}(?:送信|問い合わせ)|'
    r'(?:送信|問い合わせ).{0,30}同意|must\s+agree.{0,50}(?:submit|send)|'
    r'agree.{0,50}(?:before|to).{0,30}(?:submit|send)|'
    r'consent.{0,50}(?:submit|send))',re.I)
FINAL=re.compile(r'(この内容で送信|内容を送信|送信する|送信|send\s*(message|inquiry|enquiry)?|submit\s*(message|inquiry|enquiry|form)?)',re.I)
NONFINAL=re.compile(r'(確認|confirm|next|次へ|preview|戻る|back|cancel|修正)',re.I)
CONFIRM=re.compile(r'(確認画面(?:へ|に(?:進む|進める)?)|入力内容(?:を)?確認|内容(?:を)?確認|確認(?:する|へ)?|confirm|review|next|次へ)',re.I)
COMPLETION_PATH=re.compile(r'/(?:thanks?|thank[-_]?you|complete(?:d)?|completion|success|sent)(?:/|$)',re.I)
CONTACT_ROUTE_HINT=re.compile(r'(?:^|/)(?:contact|inquiry|enquiry)(?:[./_-]|$)',re.I)

def contact_route_lost_to_home(before_url,after_url):
    try:
        b=urlsplit(str(before_url or '')); a=urlsplit(str(after_url or ''))
        bp=b.path.rstrip('/') or '/'; ap=a.path.rstrip('/') or '/'
        return host(before_url)==host(after_url) and bp!='/' and ap=='/' and bool(CONTACT_ROUTE_HINT.search(bp))
    except Exception:
        return False

def is_completion_route(url):
    try:
        return bool(COMPLETION_PATH.search(urlsplit(str(url or '')).path or '/'))
    except Exception:
        return False

def form_requires_transactional_consent(text):
    return bool(CONSENT_GATE.search(str(text or '')))

def safe_consent_radio_choice(members):
    rows=[x for x in (members or []) if isinstance(x,dict)]
    eligible=[]
    for x in rows:
        desc=(str(x.get('desc') or '')+' '+str(x.get('value') or '')).strip()
        if MARKETING.search(desc) or not CONSENT.search(desc):
            continue
        if re.search(r'(同意しない|同意しません|拒否|不同意|disagree|do\s+not\s+agree|decline|reject|no\b)',desc,re.I):
            continue
        if re.search(r'(同意する|同意します|agree|accept|consent|\byes\b|\btrue\b)',desc,re.I):
            eligible.append(x)
    if len(eligible)==1:
        return eligible[0]
    if not eligible and len(rows)==1:
        desc=(str(rows[0].get('desc') or '')+' '+str(rows[0].get('value') or '')).strip()
        negative=bool(re.search(
            r'(同意しない|同意しません|拒否|不同意|disagree|do\s+not\s+agree|decline|reject|\bno\b)',
            desc,re.I))
        if CONSENT.search(desc) and not MARKETING.search(desc) and not negative:
            return rows[0]
    return None

def safe_select_value(options):
    rows=[x for x in (options or []) if isinstance(x,dict)]
    safe=[]
    for x in rows:
        value=str(x.get('v') or '').strip()
        text=str(x.get('t') or '').strip()
        if not value:
            continue
        if re.search(r'(その他|一般|お問い合わせ|ご相談|法人|business|other|general|partnership|new inquiry|service inquiry|request information|no preference|not applicable)',text,re.I):
            if not re.search(r'(newsletter|marketing|メルマガ|広告|採用|求人|career|job|support|technical support|個人|患者|student)',text,re.I):
                safe.append(value)
    return safe[0] if len(safe)==1 else None

def normalized_control_text(value):
    return re.sub(r'\s+','',str(value or '')).strip().casefold()

def safe_confirm_text(value):
    text=str(value or '');compact=re.sub(r'\s+','',text)
    if not (CONFIRM.search(text) or CONFIRM.search(compact)):
        return False
    # A control that already explicitly says "send/submit" is a final action,
    # not a harmless confirmation step.
    if (re.search(r'(この内容で送信|内容を送信|送信する|確認して送信|送信$|\bsend\b|\bsubmit\b|確定)',text,re.I)
            or re.search(r'(この内容で送信|内容を送信|送信する|確認して送信|送信$|send|submit|確定)',compact,re.I)):
        return False
    return True

def confirm_control_matches(target,live):
    if not safe_confirm_text(target) or not safe_confirm_text(live):
        return False
    a=normalized_control_text(target); b=normalized_control_text(live)
    return bool(a and b and (a==b or a in b or b in a))

def control_semantic_text(control):
    if not isinstance(control,dict):
        return ''
    # Prefer only user-visible/action-label text. Internal name/id metadata may
    # contain strings like submitConfirm even on the final "送信する" button;
    # mixing that metadata into semantics caused false NONFINAL rejection.
    label=str(control.get('label') or '').strip()
    return label or str(control.get('text') or '').strip()

def final_control_candidates(controls):
    controls=[x for x in (controls or []) if isinstance(x,dict)]
    finals=[]
    for x in controls:
        semantic=control_semantic_text(x);compact=re.sub(r'\s+','',semantic)
        if not (FINAL.search(semantic) or FINAL.search(compact)):
            continue
        if (NONFINAL.search(semantic) or NONFINAL.search(compact)) and not re.search(
                r'(確認して送信|確認のうえ送信|confirm.{0,12}send|send.{0,12}confirm)',
                compact,re.I):
            continue
        # Explicitly-labelled JS final buttons are common after a confirm
        # step. Keep image inputs excluded because their semantic label can
        # come from a non-visible id/name rather than a user-facing action.
        if str(x.get('tag') or '')=='input' and str(x.get('type') or '')=='image':
            continue
        finals.append(x)
    if finals:
        return finals
    fallback=[]
    for x in controls:
        semantic=control_semantic_text(x);compact=re.sub(r'\s+','',semantic)
        if NONFINAL.search(semantic) or NONFINAL.search(compact):
            continue
        if re.search(r'(コメント|comment|レビュー|review|reset|clear)',semantic,re.I):
            continue
        if str(x.get('tag') or '')=='button' or str(x.get('type') or '')=='submit':
            fallback.append(x)
    return fallback if len(fallback)==1 else []

def retryable_confirm_control(target,control,frame_index):
    if not isinstance(control,dict):
        return False
    return bool(
        str(control.get('type') or '')=='submit'
        and int(control.get('frame_index') or 0)==int(frame_index or 0)
        and confirm_control_matches(target,control_semantic_text(control))
    )

async def wait_for_confirmation_ready(page,before_url,timeout_ms=7500):
    deadline=time.monotonic()+max(0.5,float(timeout_ms)/1000.0)
    saw_url_change=False; last_controls=[]; load_state_waited=False
    while True:
        try:
            if str(page.url or '')!=str(before_url or ''):
                saw_url_change=True
        except Exception:
            pass
        if saw_url_change and not load_state_waited:
            remaining=max(0.0,deadline-time.monotonic())
            if remaining>0:
                try:
                    await page.wait_for_load_state('domcontentloaded',timeout=max(250,min(3500,int(remaining*1000))))
                except Exception:
                    pass
            load_state_waited=True
        controls=[]
        try:
            for fi,root in enumerate(list(page.frames)[:4]):
                try:
                    xs=await root.locator('button,input[type=submit],input[type=button],input[type=image]').evaluate_all(r"""els=>els.map((e,i)=>{
                      const s=getComputedStyle(e),r=e.getBoundingClientRect();
                      const visible=!e.disabled&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
                      const label=((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')).trim();
                      return {i,visible,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),label,
                        text:(label+' '+(e.name||'')+' '+(e.id||'')).trim()};
                    }).filter(x=>x.visible)""")
                    for x in xs:x['frame_index']=fi
                    controls.extend(xs)
                except Exception:
                    continue
            last_controls=controls
            if final_control_candidates(controls):
                return {'ready':True,'url_changed':saw_url_change,'controls':controls}
        except Exception:
            pass
        if time.monotonic()>=deadline:
            return {'ready':False,'url_changed':saw_url_change,'controls':last_controls}
        try:await page.wait_for_timeout(200)
        except Exception:await asyncio.sleep(.2)


def strong_main_form_candidate(cand,frame_index):
    if not isinstance(cand,dict) or int(frame_index)!=0:
        return False
    kind=str(cand.get('control_kind') or '')
    score=int(cand.get('score') or 0)
    return ((kind=='DIRECT_SUBMIT' and score>=13)
            or (kind=='CONFIRM_STEP' and score>=12))

async def advance_safe_multistep_roots(roots,max_steps=3):
    """Advance only harmless non-submit wizard controls.

    This is used for forms that hide the real contact fields behind one or more
    Continue/Next steps. It never clicks submit/final controls.
    """
    steps=0
    for _ in range(max(0,int(max_steps))):
        advanced=False
        for root in list(roots or [])[:8]:
            try:
                forms=root.locator('form')
                for fi in range(min(await forms.count(),12)):
                    form=forms.nth(fi)
                    # If visible email + message fields already exist, normal
                    # form scanning should take over without any more clicks.
                    core=await form.locator('input,textarea').evaluate_all("""els=>{
                      const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return !e.disabled&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
                      let email=false,msg=false;
                      for(const e of els){if(!vis(e))continue;
                        const d=[e.name,e.id,e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ');
                        const t=(e.type||'').toLowerCase();
                        email=email||t==='email'||/(e-?mail|メール)/i.test(d);
                        msg=msg||e.tagName==='TEXTAREA'||/(message|inquir|enquir|お問い合わせ内容|問い合わせ内容|内容)/i.test(d);
                      }
                      return {email,msg};
                    }""")
                    if core.get('email') and core.get('msg'):
                        return steps
                    xs=form.locator('button,input[type=button]')
                    hits=[]
                    for i in range(min(await xs.count(),30)):
                        e=xs.nth(i)
                        if not await e.is_visible() or not await e.is_enabled():
                            continue
                        typ=(await e.get_attribute('type') or 'button').lower()
                        if typ=='submit':
                            continue
                        label=' '.join(str(await e.evaluate(
                            "e=>[e.getAttribute('aria-label'),e.value,e.innerText].filter(Boolean).join(' ')"
                        ) or '').split())
                        if re.fullmatch(r'(continue|next|次へ|続ける|進む)',label,re.I):
                            hits.append(e)
                    if len(hits)!=1:
                        continue
                    await hits[0].click(timeout=4000)
                    await root.wait_for_timeout(450)
                    steps+=1;advanced=True
                    break
                if advanced:
                    break
            except Exception:
                continue
        if not advanced:
            break
    return steps

def lane_accept(rec):
    # Dispatcher emits lane-pure Browser tasks and stamps every route with the
    # authoritative lane_hint. Respect it first instead of re-deriving the lane
    # from static_status: high-sendability DYNAMIC_HINT routes are intentionally
    # promoted to FAST_DOM, while force-rendered work is intentionally pinned to
    # DYNAMIC_JS. Re-deriving here previously made those routes unexecutable.
    hinted=str(rec.get('lane_hint') or '').upper()
    if hinted in {'FAST_DOM','DYNAMIC_JS','IFRAME_DEEP','DEEP'}:
        return hinted==LANE_MODE
    # Legacy/fallback tasks without lane_hint retain the historical inference.
    st=str(rec.get('static_status') or '')
    try: rid=int(rec.get('route_id') or 0)
    except Exception: rid=0
    try: sendq=int(rec.get('stage2_static_sendability') or 0)
    except Exception: sendq=0
    if rec.get('force_rendered') is True:
        return LANE_MODE=='DYNAMIC_JS'
    if LANE_MODE=='FAST_DOM':
        return st=='STATIC_FORM_CANDIDATE' or sendq>=70
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

def sensitive_kind(text):
    d=str(text or '')
    if re.search(r'(\bphone\b|\btelephone\b|\btel\b|\bmobile\b|携帯|電話)',d,re.I):return 'phone'
    if re.search(r'(\bpostal\b|\bpostcode\b|\bzip\b|郵便)',d,re.I):return 'postal'
    if re.search(r'(\baddress\b|住所|都道府県|市区町村|番地)',d,re.I):return 'address'
    return ''

def script_required_sensitive_kinds(text):
    s=str(text or '')[:500000]
    anchors=list(re.finditer(r'(?:contact[-_ ]?form|contact[-_ ]?page|/api/contact|contactForm)',s,re.I))
    if not anchors:
        return set()
    ctx='\n'.join(s[max(0,m.start()-800):min(len(s),m.start()+4200)] for m in anchors[:8])
    out=set()
    if re.search(r'(?:(?:phone(?:\s+number)?|telephone|mobile).{0,90}(?:is\s+)?required|if\s*\(\s*!\s*(?:[\w$]+\.)*(?:phone|telephone|mobile)\b)',ctx,re.I|re.S):out.add('phone')
    if re.search(r'(?:(?:postal(?:\s+code)?|postcode|zip).{0,90}(?:is\s+)?required|if\s*\(\s*!\s*(?:[\w$]+\.)*(?:postal|postcode|zip)\b)',ctx,re.I|re.S):out.add('postal')
    if re.search(r'(?:(?:address(?:\s+line\s*1)?).{0,90}(?:is\s+)?required|if\s*\(\s*!\s*(?:[\w$]+\.)*(?:address|addressLine1)\b)',ctx,re.I|re.S):out.add('address')
    return out

async def same_origin_script_required_sensitive(page):
    try:
        text=await asyncio.wait_for(page.evaluate("""async () => {
          const score=u=>/(contact|form|main|app|script)/i.test(u)?1:0;
          let urls=[...document.scripts].map(s=>s.src).filter(Boolean).filter(u=>{try{return new URL(u,location.href).origin===location.origin}catch{return false}});
          urls=[...new Set(urls)].sort((a,b)=>score(b)-score(a)).slice(0,6);
          let out='';
          for(const u of urls){
            try{
              const r=await fetch(u,{cache:'force-cache',credentials:'same-origin'});
              if(!r.ok)continue;
              const t=await r.text(); out+='\\n'+t.slice(0,180000);
              if(out.length>=500000)break;
            }catch{}
          }
          return out.slice(0,500000);
        }"""),timeout=4.5)
    except Exception:
        return set()
    return script_required_sensitive_kinds(text)

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

STATE_TOPOLOGY={
    'schema':'PAL_STAGE3_WORKER_STATE_V3_HASH_SHARD',
    'shard_strategy':'SHA256_ROUTE_ID_V1',
    'shard_count':SHARD_COUNT,
    'shard_index':SHARD_INDEX,
}
def load_state():
    try:
        data=json.loads(STATE.read_text())
    except Exception:
        return {}
    # processed_task_ids are only valid for the shard topology that produced
    # them. Reusing a two-shard done-set after role isolation moved Stage3 onto
    # a single service caused every surviving task to be skipped forever.
    # Preserve recent per-route retry evidence, but invalidate task completion
    # bookkeeping whenever topology/schema changes.
    topo=data.get('topology') if isinstance(data,dict) else None
    if topo!=STATE_TOPOLOGY:
        return {
            'recent_route_results':dict(data.get('recent_route_results') or {}) if isinstance(data,dict) else {},
            'processed_task_ids':[],
            'last_status_counts':dict(data.get('last_status_counts') or {}) if isinstance(data,dict) else {},
            'topology_reset_from':topo,
        }
    return data if isinstance(data,dict) else {}

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
      'topology':STATE_TOPOLOGY,
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
      'task_id':str(rec.get('_task_id') or rec.get('task_id') or ''),
      'market':str(rec.get('market') or ''),'official_domain':str(rec.get('official_domain') or '').lower().removeprefix('www.'),
      'last_seen_epoch':int(time.time()),'pages_checked':1,'proof_version':PROOF_VERSION,'lane_mode':LANE_MODE,
      'producer':PRODUCER}

async def sticky_fill(loc,value):
    target=str(value)
    try:
        await loc.fill(target,timeout=2500)
    except Exception:
        pass
    try:
        if str(await loc.input_value(timeout=1500))==target:
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
        if str(await loc.input_value(timeout=1500))==target:
            return
    except Exception:
        pass
    raise RuntimeError('STICKY_FILL_FAILED')

async def safe_choice_check(form,loc,row):
    """Select an already-approved radio/checkbox through its visible label proxy.

    Custom form themes often make the native input 0x0/hidden and style the
    associated <label>. Never select arbitrary hidden inputs: the caller has
    already limited this helper to a safe required category/consent choice.
    """
    try:
        await loc.check(timeout=2200)
        if await loc.is_checked():
            return True
    except Exception:
        pass
    # Common custom-control pattern: <label><input ...><span>...</span></label>.
    try:
        lab=loc.locator('xpath=ancestor::label[1]')
        if await lab.count()>0 and await lab.first.is_visible():
            await lab.first.click(timeout=3500)
            if await loc.is_checked():
                return True
    except Exception:
        pass
    # Also support <label for="field-id">...</label> without constructing a CSS
    # selector from an untrusted id. Locate the matching visible label by index.
    field_id=str((row or {}).get('id') or '')
    if field_id:
        try:
            labels=form.locator('label')
            indexes=await labels.evaluate_all(
                """(els,id)=>els.map((e,i)=>({i,forId:e.htmlFor||'',s:getComputedStyle(e),r:e.getBoundingClientRect()}))
                   .filter(x=>x.forId===id&&x.s.display!=='none'&&x.s.visibility!=='hidden'&&x.r.width>0&&x.r.height>0)
                   .map(x=>x.i)""",
                field_id,
            )
            for idx in indexes[:3]:
                try:
                    await labels.nth(int(idx)).click(timeout=3500)
                    if await loc.is_checked():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
    return False

async def visible_captcha(root):
    """Block only an actually rendered captcha/challenge, not a dormant script."""
    # Locator count/is_visible/bounding_box + innerText caused repeated layout and
    # protocol round-trips on JS-heavy pages. Evaluate the identical visibility
    # and challenge-text contract in one DOM pass and bound it independently.
    script=r"""() => {
      const sel='iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],.g-recaptcha,.h-captcha,.cf-turnstile,[data-sitekey]';
      const visible=e=>{
        try{
          const s=getComputedStyle(e),r=e.getBoundingClientRect();
          return s.display!=='none'&&s.visibility!=='hidden'&&r.width>4&&r.height>4;
        }catch(_){return false;}
      };
      if([...document.querySelectorAll(sel)].slice(0,12).some(visible)) return true;
      const body=((document.body&&document.body.textContent)||'').slice(0,12000);
      return /(verify you are human|prove you are human|human verification|current year.{0,50}(?:human|prove)|anti[- ]?spam.{0,40}(?:question|check|challenge)|checking your browser|complete the security check|captcha challenge|画像認証|画像内.{0,30}(?:文字列|文字|コード)|認証コード.{0,20}(?:画像|入力)|画像認証.{0,30}(?:正しくありません|必須))/i.test(body);
    }"""
    try:
        return bool(await asyncio.wait_for(root.evaluate(script),timeout=2.0))
    except asyncio.TimeoutError:
        # Fail closed: an uninspectable challenge state must never be accepted.
        return True
    except Exception:
        return False

def same_form_snapshot(before,after):
    """DOM form/frame indexes are zero-based; missing indexes are not zero."""
    if not isinstance(before,dict) or not isinstance(after,dict):
        return False
    for key in ('index','frame_index'):
        left,right=before.get(key),after.get(key)
        if type(left) is not int or type(right) is not int:
            return False
        if left<0 or right<0 or left!=right:
            return False
    return True

async def inspect_with_timeout(browser,rec,sem,timeout,slow=False):
    progress={'phase':'waiting_for_slot'}
    started=time.monotonic()
    try:
        return await asyncio.wait_for(
            inspect(browser,rec,sem,slow=slow,progress=progress),timeout=timeout)
    except asyncio.TimeoutError:
        return {**base_result(rec),'status':'TECH_DEFER',
                'code':'OVERALL_ROUTE_TIMEOUT_OR_ERROR','stage3_send_ready':False,
                'error_type':'TimeoutError','error_detail':'Route wall-clock budget exceeded',
                'timeout_phase':progress['phase'],'lane_mode':LANE_MODE,
                'elapsed_seconds':round(time.monotonic()-started,3)}

async def inspect(browser,rec,sem,slow=False,progress=None):
    async with sem:
        base=base_result(rec); rid=base['route_id'];url=str(rec.get('canonical_url') or '');domain=base['official_domain']
        if not rid or not url or not domain or host(url)!=domain:
            return {**base,'status':'TECH_DEFER','code':'INVALID_TASK','stage3_send_ready':False}
        if is_completion_route(url):
            return {**base,'status':'NO_SAFE_FORM','code':'COMPLETION_ROUTE_NOT_CONTACT',
                    'final_url':url,'stage3_send_ready':False,'send_ready_proof_v2':False}
        ctx=None
        progress=progress if progress is not None else {}
        def phase(name):
            progress['phase']=name
        phase('context_init')
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
            nav_timeout=stage3_navigation_timeout_ms(ROUTE_TIMEOUT_SECONDS,LANE_MODE,slow)
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
                phase('navigate')
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
                phase('render_wait')
                lane_wait={'FAST_DOM':900,'DYNAMIC_JS':1800,'IFRAME_DEEP':1500,'DEEP':2600}.get(LANE_MODE,1200)
                if slow: lane_wait=max(lane_wait,2200)
                await page.wait_for_timeout(lane_wait)
                # Static contact-form evidence can refer to a form below the
                # initial viewport. Duda-style sites keep such widgets
                # visibility:hidden behind a running-animation class until an
                # IntersectionObserver sees them. Trigger only that normal
                # viewport event; never mutate CSS/visibility or bypass gates.
                if LANE_MODE=='FAST_DOM' and (
                        bool(rec.get('static_full_preflight'))
                        or str(rec.get('static_status') or '')=='STATIC_FORM_CANDIDATE'):
                    try:
                        forms_for_reveal=page.locator('form')
                        for reveal_i in range(min(await forms_for_reveal.count(),4)):
                            try:
                                await forms_for_reveal.nth(reveal_i).scroll_into_view_if_needed(timeout=1800)
                                await page.wait_for_timeout(350)
                            except Exception:
                                continue
                        await page.wait_for_function("""() => [...document.forms].some(f =>
                          [...f.querySelectorAll('input,textarea,select,button')].some(e => {
                            const s=getComputedStyle(e),r=e.getBoundingClientRect();
                            return !e.disabled && e.type!=='hidden' &&
                                   s.display!=='none' && s.visibility!=='hidden' &&
                                   r.width>0 && r.height>0;
                          }))""", timeout=2500)
                    except PlaywrightTimeoutError:
                        pass
                    except Exception:
                        pass
                if LANE_MODE in {'DYNAMIC_JS','DEEP'} or slow:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1600 if LANE_MODE!='DEEP' else 2400)
                    await page.evaluate("window.scrollTo(0, 0)")
            except Exception:pass
            final_url=page.url
            if host(final_url)!=domain:
                return {**base,'status':'DOMAIN_CHANGED','code':'DOMAIN_CHANGED','final_url':final_url,'stage3_send_ready':False}
            if contact_route_lost_to_home(url,final_url):
                return {**base,'status':'NO_SAFE_FORM','code':'CONTACT_ROUTE_LOST_TO_HOME','final_url':final_url,'stage3_send_ready':False,'send_ready_proof_v2':False}
            phase('body_text')
            # innerText can force a full layout flush and stall on JS-heavy pages.
            # For the page-level prohibition/safety scan, textContent is sufficient
            # and avoids that layout cost. Bound this step independently so one
            # renderer cannot consume the entire route wall-clock budget here.
            try:
                raw_text=await asyncio.wait_for(
                    page.evaluate(
                        "() => ((document.body && document.body.textContent) || "
                        "(document.documentElement && document.documentElement.textContent) || '')"
                    ),
                    timeout=4.0,
                )
            except Exception:
                try:
                    raw_text=await asyncio.wait_for(
                        page.locator('body').text_content(timeout=3000),
                        timeout=3.5,
                    )
                except Exception:
                    return {**base,'status':'TECH_DEFER','code':'BODY_TEXT_TIMEOUT',
                            'final_url':final_url,'stage3_send_ready':False,
                            'timeout_phase':'body_text','lane_mode':LANE_MODE}
            text=str(raw_text or '')[:180000]
            if not text.strip():
                return {**base,'status':'TECH_DEFER','code':'DOM_TEXT_EMPTY',
                        'final_url':final_url,'stage3_send_ready':False,
                        'timeout_phase':'body_text','lane_mode':LANE_MODE}
            if PROHIBIT.search(text):
                return {**base,'status':'SALES_PROHIBITED','code':'SALES_PROHIBITED','final_url':final_url,'stage3_send_ready':False}
            phase('captcha_scan')
            if await visible_captcha(page):
                return {**base,'status':'CAPTCHA','code':'VISIBLE_CAPTCHA','final_url':final_url,'stage3_send_ready':False}

            # Bounded structural diagnostics for false NO_SAFE_FORM analysis.
            # Never records field values or submitted content.
            scan_debug=[]

            async def scan_root(root,frame_index):
                try:
                    # root.content() was unused and can serialize a very large DOM.
                    # textContent avoids layout flushes and is enough for the
                    # prohibition scan. Keep it independently bounded.
                    root_text=str(await asyncio.wait_for(
                        root.locator('body').text_content(timeout=1500),
                        timeout=2.0,
                    ) or '')[:180000]
                except Exception:
                    root_text=''
                if PROHIBIT.search(root_text):
                    return None
                if await visible_captcha(root):
                    return None
                # Collect metadata for all bounded forms in one browser-side DOM
                # evaluation. The previous implementation made one Playwright
                # round-trip per form (up to 12) and dominated route latency.
                # The same visibility/required/control semantics are preserved.
                try:
                    metas=await asyncio.wait_for(root.evaluate("""() => {
                      const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return !e.disabled&&e.type!=='hidden'&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
                      const choiceProxyVisible=e=>{
                        const typ=String(e.type||'').toLowerCase();
                        if(e.disabled||!(typ==='radio'||typ==='checkbox'))return false;
                        const labs=e.labels?[...e.labels]:[];
                        return labs.some(l=>{const s=getComputedStyle(l),r=l.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0});
                      };
                      const desc=e=>{const id=e.id||'',lab=id?document.querySelector('label[for="'+CSS.escape(id)+'"]'):null;
                        const labels=e.labels?[...e.labels].map(x=>(x.innerText||'').trim()).filter(Boolean).join(' ').trim():'';
                        const tr=e.closest('tr'),cell=e.closest('th,td');let rowLabel='',rowRequiredIcon=false,rowRequiredClass=false;
                        if(tr&&cell){const cells=[...tr.children],idx=cells.indexOf(cell);
                          const prior=(idx>0?cells.slice(0,idx):[]);
                          rowLabel=((prior.map(c=>c.innerText||'').join(' '))||(tr.querySelector('th')?.innerText||'')).trim();
                          const labelCells=prior.length?prior:[tr.querySelector('th')].filter(Boolean);
                          rowRequiredIcon=labelCells.some(c=>[...c.querySelectorAll('img')].some(img=>{
                            const src=String(img.getAttribute('src')||'').toLowerCase();
                            const alt=String(img.getAttribute('alt')||'').toLowerCase();
                            const title=String(img.getAttribute('title')||'').toLowerCase();
                            return /(asterisk|required|mandatory|hissu|必須)/.test(src+' '+alt+' '+title);
                          }));
                          rowRequiredClass=labelCells.some(c=>/(?:^|[ _-])(required|req|mandatory|hissu)(?:$|[ _-])/i.test(String(c.className||'')));
                        }
                        const prev=e.previousElementSibling;
                        if(!rowLabel&&prev&&prev.tagName==='LABEL')rowLabel=(prev.innerText||'').trim();
                        const dd=e.closest('dd');
                        if(!rowLabel&&dd&&dd.previousElementSibling&&dd.previousElementSibling.tagName==='DT'){
                          const dt=dd.previousElementSibling;
                          rowLabel=(dt.innerText||'').trim();
                          if(/(?:^|[ _-])(required|req|mandatory|hissu)(?:$|[ _-])/i.test(String(dt.className||'')))
                            rowRequiredIcon=true;
                        }
                        {const box=e.closest('fieldset,.form-item-box,.form-group,.form02,.form-row,.field,.mwform-field,.contact-field,.p-contact-group');
                          const h=box&&box.querySelector('legend,dt,label,.form__label,.form03,.field-label,.form-label,.label,.p-contact-group__header');
                          if(h){
                            const ht=(h.innerText||'').trim();
                            if(!rowLabel)rowLabel=ht;
                            if(/[※＊*]\\s*$/.test(ht)||/(必須|required|mandatory)/i.test(ht)
                              ||h.querySelector('.req,.required,.hissu,[class*="required"],[class*="mandatory"]')){
                              rowRequiredIcon=true;
                            }
                          }}
                        const w=e.closest('label,.form-group,.form-row,.field,li,dl,dd,dt,p')||e.parentElement;
                        let local=(((lab&&lab.innerText)||'').trim()||labels||((w&&w.innerText)||'').trim());
                        if(!local&&((e.type||'').toLowerCase()==='checkbox'||(e.type||'').toLowerCase()==='radio')){
                          const gp=e.parentElement&&e.parentElement.parentElement;
                          const gt=((gp&&gp.innerText)||'').trim();
                          if(gt&&gt.length<=300)local=gt;
                        }
                        if(local.length>300)local='';
                        const self=[e.name||'',id,e.placeholder||'',e.getAttribute('aria-label')||'',(lab&&lab.innerText)||'',labels].join(' ');
                        return {self:self.slice(0,500),local:local.slice(0,500),rowLabel:rowLabel.slice(0,500),rowRequiredIcon:(rowRequiredIcon||rowRequiredClass)};
                      };
                      return [...document.forms].slice(0,12).map((f,index)=>{
                        const allFields=[...f.querySelectorAll('input,textarea,select')];
                        const fs=allFields.map((e,all_i)=>({e,all_i})).filter(x=>vis(x.e)||choiceProxyVisible(x.e)).map(({e,all_i})=>{const d=desc(e);
                          const reqText=(d.self+' '+d.rowLabel+' '+d.local);
                          const classes=String(e.className||'').split(/\\s+/);
                          const classRequired=classes.some(c=>/^(?:required|mandatory|hissu(?:val)?|req(?:uired)?(?:field)?)$/i.test(c));
                          const frameworkRequired=classes.some(c=>/^ng-invalid$/i.test(c));
                          const req=!!e.required||e.getAttribute('aria-required')==='true'||d.rowRequiredIcon===true||classRequired||frameworkRequired||(/[※＊*]/.test(d.rowLabel+' '+d.local)&&!/(任意|optional)/i.test(reqText))||(/(必須|required|mandatory)/i.test(reqText)&&!/(任意|optional)/i.test(reqText));
                          return {i:all_i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),name:e.name||'',id:e.id||'',required:req,
                            checked:!!e.checked,value:e.value||'',self_desc:d.self.slice(0,500),local_desc:d.local.slice(0,500),row_label:d.rowLabel.slice(0,500),
                            desc:(d.self+' '+d.rowLabel+' '+d.local).slice(0,900)}});
                        const controls=[...f.querySelectorAll('button,input[type=submit],input[type=button],input[type=image]')].filter(vis)
                          .map((e,i)=>({i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),
                            text:((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.name||'')+' '+(e.id||'')).trim()}));
                        return {index,text:(f.innerText||'').slice(0,12000),action:f.action||'',method:(f.method||'get').toLowerCase(),
                          action_attr:f.getAttribute('action')||'',method_attr:f.getAttribute('method')||'',
                          ident:((f.id||'')+' '+(f.className||'')+' '+(f.action||'')).slice(0,1000),fields:fs,controls};
                      });
                    }"""),timeout=3.0)
                except Exception:
                    metas=[]
                n=len(metas); best_local=None
                root_diag={'frame_index':int(frame_index),'form_count':int(n),'evaluate_errors':0,'forms':[]}
                if len(scan_debug)<20:
                    scan_debug.append(root_diag)
                for meta in metas:
                    i=int(meta.get('index') or 0)
                    blob=(str(meta.get('text') or '')+' '+str(meta.get('ident') or '')).lower()
                    ident_blob=str(meta.get('ident') or '').lower()
                    form_text=str(meta.get('text') or '').lower()
                    form_action=str(meta.get('action') or '').strip()
                    form_action_attr=str(meta.get('action_attr') or '').strip()
                    form_method=str(meta.get('method') or 'get').strip().lower()
                    # mailto/tel/javascript actions are not web-form outreach.
                    # They cannot satisfy the Stage-3 -> Stage-4 web-submit contract.
                    if re.match(r'^(?:mailto|tel|javascript):',form_action,re.I):
                        continue
                    if EMAIL_CLIENT_FORM.search(form_text):
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
                               'ident':str(meta.get('ident') or '')[:180],
                               'method':form_method,'action':form_action[:240]}
                    if len(root_diag['forms'])<20:
                        root_diag['forms'].append(form_diag)
                    if not (has_email and has_msg):
                        form_diag['decision']='NO_EMAIL_OR_MESSAGE'
                        continue
                    human_challenge=[x for x in fields if bool(x.get('required')) and HUMAN_CHALLENGE.search(str(x.get('desc') or ''))]
                    if human_challenge:
                        form_diag['decision']='HUMAN_CHALLENGE_REQUIRED'
                        form_diag['human_challenge_count']=len(human_challenge)
                        continue
                    # A contact-looking form with an explicitly declared GET target
                    # that is clearly a placeholder/broken endpoint must not become
                    # SEND_READY. Omitted action/method remains allowed because many
                    # modern forms are submitted by JavaScript/AJAX.
                    try:
                        action_parts=urlsplit(form_action)
                        action_leaf=(action_parts.path or '').rstrip('/').split('/')[-1].lower()
                        current_scheme=urlsplit(str(page.url or '')).scheme.lower()
                        action_scheme=(action_parts.scheme or '').lower()
                    except Exception:
                        action_leaf='';current_scheme='';action_scheme=''
                    broken_leaf=bool(re.fullmatch(r'(?:string|dummy|placeholder|example|sample|test\d*|action)',action_leaf,re.I))
                    insecure_downgrade=bool(current_scheme=='https' and action_scheme=='http')
                    if form_method=='get' and bool(form_action_attr) and (broken_leaf or insecure_downgrade):
                        form_diag['decision']='BROKEN_GET_ACTION'
                        form_diag['broken_action_leaf']=action_leaf[:80]
                        form_diag['insecure_downgrade']=insecure_downgrade
                        continue
                    ctrls=list(meta.get('controls') or [])
                    form_diag['control_count']=len(ctrls)
                    # A visible type=submit control on a verified contact form is a
                    # final control even when branded text says "Get in touch",
                    # "Contact us", etc. Exclude explicit Next/Confirm/Back controls.
                    # Use user-visible semantics consistently. Internal names/ids such
                    # as submitConfirm must not turn a harmless confirmation
                    # control into a direct-send control.
                    direct=final_control_candidates(ctrls)
                    safe_confirm=[
                        x for x in ctrls
                        if safe_confirm_text(control_semantic_text(x))
                    ]
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
                    cand={'index':i,'fields':fields,'control':chosen_control,'control_kind':kind,'score':score,
                          'frame_index':frame_index,'form_text':form_text[:12000],
                          'form_action':form_action[:1000],'form_method':form_method}
                    if best_local is None or score>best_local['score']:
                        best_local=cand
                return best_local

            # Main-frame forms dominate successful outreach. Third-party ad/chat
            # iframes are expensive and almost never contain the target form.
            # Scan main/same-origin frames first, then only likely form-provider
            # frames, with a bounded cap. This changes scheduling only; every
            # inspected form still passes the same safety/fillability contract.
            all_roots=list(page.frames)
            main=page.main_frame
            same_origin=[]
            provider=[]
            other=[]
            provider_re=re.compile(r'(form|contact|hubspot|jotform|typeform|wufoo|formstack|marketo|pardot|salesforce)',re.I)
            for fr in all_roots:
                if fr is main:
                    continue
                fu=str(getattr(fr,'url','') or '')
                if host(fu)==domain:
                    same_origin.append(fr)
                elif provider_re.search(fu):
                    provider.append(fr)
                else:
                    other.append(fr)
            frame_cap=8 if LANE_MODE in {'IFRAME_DEEP','DEEP'} else (6 if LANE_MODE=='DYNAMIC_JS' else 4)
            if LANE_MODE in {'IFRAME_DEEP','DEEP'}:
                roots=([main]+same_origin+provider+other)[:frame_cap]
            else:
                # Unrelated third-party frames are ads/chat/analytics in normal
                # lanes. If the target form truly lives there, the explicit
                # IFRAME_DEEP/DEEP lane remains responsible for it.
                roots=([main]+same_origin+provider)[:frame_cap]
            phase('form_scan')
            best=None
            # A valid direct-submit contact form is already sufficient once the
            # page/root safety gates above have passed. Do not keep scanning every
            # iframe after finding one: slow third-party frames were consuming the
            # entire route wall-clock budget and converting good routes into
            # OVERALL_ROUTE_TIMEOUT_OR_ERROR. Per-root timeouts are fail-closed;
            # a hung frame is skipped, never accepted.
            per_root_timeout=3.5 if LANE_MODE in {'IFRAME_DEEP','DEEP'} else 2.75
            for frame_index,root in enumerate(roots):
                try:
                    cand=await asyncio.wait_for(scan_root(root,frame_index),timeout=per_root_timeout)
                except Exception:
                    cand=None
                if cand and (best is None or cand['score']>best['score']):
                    best=cand
                if strong_main_form_candidate(best,frame_index):
                    break
            multistep_steps=0
            if not best:
                phase('safe_multistep')
                multistep_steps=await advance_safe_multistep_roots(roots,3)
                if multistep_steps:
                    # Re-run the identical safety/form scan after harmless
                    # non-submit wizard advancement.
                    for frame_index,root in enumerate(roots):
                        try:
                            cand=await asyncio.wait_for(scan_root(root,frame_index),timeout=per_root_timeout)
                        except Exception:
                            cand=None
                        if cand and (best is None or cand['score']>best['score']):
                            best=cand
                        if strong_main_form_candidate(best,frame_index):
                            break
            if not best:
                return {**base,'status':'NO_SAFE_FORM','code':'NO_DIRECT_SEND_READY_FORM',
                        'final_url':final_url,'stage3_send_ready':False,
                        'multistep_steps':multistep_steps,
                        'form_scan_debug':scan_debug[:20]}

            active_root=roots[int(best.get('frame_index') or 0)]
            phase('fill_fields')
            forms=active_root.locator('form')
            form=forms.nth(int(best['index']))
            sensitive_required=[]
            unfillable=[]
            script_required=set()
            if any(sensitive_kind((str(x.get('name') or '')+' '+str(x.get('id') or '')+' '+str(x.get('self_desc') or '')+' '+str(x.get('row_label') or '')).strip()) for x in best['fields']):
                script_required=await same_origin_script_required_sensitive(page)
            # Required radios are group requirements. In addition, some forms
            # use a privacy-policy consent radio without the HTML required
            # attribute while explicitly stating that consent is required before
            # sending. Treat only that transactional consent pattern as gated;
            # marketing/newsletter choices remain excluded.
            consent_gate=form_requires_transactional_consent(best.get('form_text'))
            radio_groups={}
            for rr in best['fields']:
                if str(rr.get('type') or '')!='radio':
                    continue
                desc=str(rr.get('desc') or '')
                is_consent=bool(CONSENT.search(desc)) and not bool(MARKETING.search(desc))
                if bool(rr.get('required')) or (consent_gate and is_consent):
                    key=str(rr.get('name') or ('__radio_'+str(rr.get('i'))))
                    radio_groups.setdefault(key,[]).append(rr)
            for _key,members in radio_groups.items():
                if any(bool(x.get('checked')) for x in members):
                    continue
                consent_members=[x for x in members
                                 if CONSENT.search(str(x.get('desc') or ''))
                                 and not MARKETING.search(str(x.get('desc') or ''))]
                if consent_gate and consent_members:
                    pick=safe_consent_radio_choice(consent_members)
                else:
                    pick=next((x for x in members if
                        re.search(r'(その他|一般|法人|問い合わせ|business|other|general|new inquiry|service inquiry|request information|no preference|not applicable)',
                                  str(x.get('desc') or ''),re.I)
                        and not re.search(r'(newsletter|marketing|メルマガ|広告|キャンペーン|電話|phone|住所|address)',
                                          str(x.get('desc') or ''),re.I)),None)
                if pick is None:
                    unfillable.append(str(members[0].get('desc') or 'required_radio')[:120])
                else:
                    try:
                        choice_loc=form.locator('input,textarea,select').nth(int(pick['i']))
                        if not await safe_choice_check(form,choice_loc,pick):
                            unfillable.append(str(pick.get('desc') or 'required_radio')[:120])
                    except Exception:
                        unfillable.append(str(pick.get('desc') or 'required_radio')[:120])
            for row in best['fields']:
                i=int(row['i']);typ=str(row.get('type') or '');tag=str(row.get('tag') or '');desc=str(row.get('desc') or '')
                req=bool(row.get('required')); loc=form.locator('input,textarea,select').nth(i)
                self_desc=str(row.get('self_desc') or '')
                row_label=str(row.get('row_label') or '')
                identity=(str(row.get('name') or '')+' '+str(row.get('id') or '')+' '+self_desc+' '+row_label).strip()
                kind=sensitive_kind(identity)
                req=req or bool(kind and kind in script_required)
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
                        try:
                            if not await safe_choice_check(form,loc,row):
                                if req or is_consent:unfillable.append(desc[:120] or 'consent_checkbox')
                        except Exception:
                            if req or is_consent:unfillable.append(desc[:120] or 'consent_checkbox')
                    elif req:
                        # Never opt into marketing/newsletters or unknown required choices.
                        unfillable.append(desc[:120] or 'required_checkbox')
                    continue
                if typ=='radio':
                    continue
                if tag=='select':
                    try:
                        try: current=str(await loc.input_value(timeout=1200) or '').strip()
                        except Exception: current=''
                        if current:
                            continue
                        opts=await loc.locator('option').evaluate_all("os=>os.map(o=>({v:o.value||'',t:(o.innerText||'').trim()}))")
                        pick=safe_select_value(opts)
                        if pick:
                            await loc.select_option(value=pick,timeout=2500)
                        elif req:
                            unfillable.append(desc[:120] or 'required_select')
                    except Exception:
                        if req:unfillable.append(desc[:120] or 'required_select')
                    continue
                value=None
                if tag=='textarea' or re.search(r'(message|inquir|enquir|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細|description)',desc,re.I):value='Business inquiry validation'
                elif typ=='email' or re.search(r'(e-?mail|メール)',desc,re.I):value='validation@example.com'
                elif re.search(r'(会社|法人|企業|company|organization|organisation)',desc,re.I):value='Practical AI Lab'
                elif re.search(r'(ふりがな|ひらがな)',desc,re.I):value='ぷらくてぃかるえーあいらぼ'
                elif re.search(r'(フリガナ|カナ|kana|furigana)',desc,re.I):value='プラクティカルエーアイラボ'
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
            phase('constraint_check')
            valid=await form.evaluate("f=>f.checkValidity()")
            if not valid:
                invalid=await form.locator(':invalid').evaluate_all("els=>els.slice(0,8).map(e=>(e.name||e.id||e.type||e.tagName).slice(0,120))")
                return {**base,'status':'REQUIRED_UNFILLABLE','code':'BROWSER_CONSTRAINT_INVALID','final_url':final_url,
                        'required_unfillable':True,'stage3_send_ready':False,'blocked_fields':invalid}

            # Dynamic frameworks may reveal/mark fields required only after input
            # events or hydration. Re-scan the rendered form after all guarded
            # fills so Stage3 uses the same final-form semantics expected at send.
            phase('post_fill_scan')
            try:
                post=await scan_root(active_root,int(best.get('frame_index') or 0))
            except Exception:
                post=None
            post_same=same_form_snapshot(best,post)
            if not post_same:
                # Some JS form frameworks replace/enable the submit control only
                # after input/change handlers settle. Give that rendered state one
                # bounded second observation; no stale pre-fill proof is accepted.
                try:
                    await page.wait_for_timeout(700)
                    post=await scan_root(active_root,int(best.get('frame_index') or 0))
                except Exception:
                    post=None
                post_same=same_form_snapshot(best,post)
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
            phase('post_fill_captcha_scan')
            if await visible_captcha(active_root) or await visible_captcha(page):
                return {**base,'status':'CAPTCHA','code':'VISIBLE_CAPTCHA_AFTER_FILL','final_url':final_url,'stage3_send_ready':False}
            # Use the post-fill control, never the pre-fill snapshot. This keeps
            # Stage3's FULL proof aligned with the exact DOM state Stage5 sees
            # after filling the same required fields.
            control=post['control']
            control_kind=str(post.get('control_kind') or 'DIRECT_SUBMIT')
            if control_kind=='CONFIRM_STEP':
                phase('confirmation_step')
                target=str(control.get('text') or '')
                confirm_before_url=page.url
                clicked=False
                # Use the DOM index captured by the post-fill scan first. That
                # scan already verified this exact control as a safe confirm
                # action. Text can gain whitespace/framework suffixes between
                # scan and click, so fall back to semantic normalized matching.
                controls_loc=form.locator('button,input[type=submit],input[type=button],input[type=image]')
                control_count=min(await controls_loc.count(),40)
                try:
                    preferred_index=int(control.get('i'))
                except Exception:
                    preferred_index=-1
                if 0<=preferred_index<control_count:
                    loc2=controls_loc.nth(preferred_index)
                    try:
                        if await loc2.is_visible() and not await loc2.is_disabled():
                            tx=await loc2.evaluate("e=>((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.name||'')+' '+(e.id||'')).trim()")
                            if confirm_control_matches(target,tx):
                                await loc2.click(timeout=7000)
                                clicked=True
                    except Exception:
                        pass
                if not clicked:
                    for ci in range(control_count):
                        loc2=controls_loc.nth(ci)
                        try:
                            if not await loc2.is_visible() or await loc2.is_disabled():
                                continue
                            tx=await loc2.evaluate("e=>((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.name||'')+' '+(e.id||'')).trim()")
                            if confirm_control_matches(target,tx):
                                await loc2.click(timeout=7000)
                                clicked=True
                                break
                        except Exception:
                            continue
                if not clicked:
                    return {**base,'status':'TECH_DEFER','code':'CONFIRM_CONTROL_NOT_FOUND','final_url':final_url,'stage3_send_ready':False}
                settle=await wait_for_confirmation_ready(page,confirm_before_url,7500)
                if not settle.get('ready'):
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(350)
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(250)
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
                        text3=str(await asyncio.wait_for(root2.evaluate("() => ((document.body && document.body.textContent) || '')"),timeout=1.5) or '')[:180000]
                        if PROHIBIT.search(text3): prohibited=True
                    except Exception: pass
                    try:
                        xs=await root2.locator('button,input[type=submit],input[type=button],input[type=image]').evaluate_all(r"""els=>els.map((e,i)=>{
                          const s=getComputedStyle(e),r=e.getBoundingClientRect(); const visible=!e.disabled&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
                          const label=((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')).trim();
                          return {i,visible,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),label,
                            text:(label+' '+(e.name||'')+' '+(e.id||'')).trim()};
                        }).filter(x=>x.visible)""")
                        for x in xs: x['frame_index']=fi
                        all_ctrls.extend(xs)
                    except Exception: pass
                if prohibited:
                    return {**base,'status':'SALES_PROHIBITED','code':'SALES_PROHIBITED_AFTER_CONFIRM','final_url':final_url,'stage3_send_ready':False}
                if captcha_after:
                    return {**base,'status':'CAPTCHA','code':'VISIBLE_CAPTCHA_AFTER_CONFIRM','final_url':final_url,'stage3_send_ready':False}
                finals=final_control_candidates(all_ctrls)
                # Some server-backed/Javascript forms ignore a synthetic click
                # even though the exact safe confirmation submitter is visible.
                # If the SAME non-final confirm control is still present and no
                # final send control appeared, retry exactly once with the same
                # element as requestSubmit(submitter). This preserves the button
                # name/value used by backends to select the confirmation branch.
                # Never use this on any control whose visible semantics are send/
                # submit/final, and never fall back to form.submit().
                confirm_retry_used=False
                if not finals:
                    same_confirm=[
                        x for x in all_ctrls
                        if retryable_confirm_control(target,x,int(best.get('frame_index') or 0))
                    ]
                    if same_confirm:
                        try:
                            retry_loc=None
                            retry_controls=form.locator('button,input[type=submit],input[type=button],input[type=image]')
                            for ci in range(min(await retry_controls.count(),40)):
                                loc2=retry_controls.nth(ci)
                                if not await loc2.is_visible() or await loc2.is_disabled():
                                    continue
                                tx=await loc2.evaluate("e=>((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.name||'')+' '+(e.id||'')).trim()")
                                if confirm_control_matches(target,tx):
                                    retry_loc=loc2
                                    break
                            if retry_loc is not None:
                                retry_before_url=page.url
                                await retry_loc.evaluate("""e=>{
                                  if(!e.form || typeof e.form.requestSubmit!=='function') throw new Error('NO_REQUEST_SUBMIT');
                                  e.form.requestSubmit(e);
                                }""")
                                confirm_retry_used=True
                                await wait_for_confirmation_ready(page,retry_before_url,7500)
                                final_url=page.url
                                if host(final_url)!=domain:
                                    return {**base,'status':'DOMAIN_CHANGED','code':'DOMAIN_CHANGED_AFTER_CONFIRM_RETRY','final_url':final_url,'stage3_send_ready':False}
                                current_roots=list(page.frames)[:frame_cap]
                                all_ctrls=[]; prohibited=False; captcha_after=False
                                for fi,root2 in enumerate(current_roots):
                                    try:
                                        if await visible_captcha(root2): captcha_after=True
                                    except Exception: pass
                                    try:
                                        text3=str(await asyncio.wait_for(root2.evaluate("() => ((document.body && document.body.textContent) || '')"),timeout=1.5) or '')[:180000]
                                        if PROHIBIT.search(text3): prohibited=True
                                    except Exception: pass
                                    try:
                                        xs=await root2.locator('button,input[type=submit],input[type=button],input[type=image]').evaluate_all(r"""els=>els.map((e,i)=>{
                                          const s=getComputedStyle(e),r=e.getBoundingClientRect(); const visible=!e.disabled&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
                                          const label=((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')).trim();
                                          return {i,visible,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),label,
                                            text:(label+' '+(e.name||'')+' '+(e.id||'')).trim()};
                                        }).filter(x=>x.visible)""")
                                        for x in xs: x['frame_index']=fi
                                        all_ctrls.extend(xs)
                                    except Exception: pass
                                if prohibited:
                                    return {**base,'status':'SALES_PROHIBITED','code':'SALES_PROHIBITED_AFTER_CONFIRM_RETRY','final_url':final_url,'stage3_send_ready':False}
                                if captcha_after:
                                    return {**base,'status':'CAPTCHA','code':'VISIBLE_CAPTCHA_AFTER_CONFIRM_RETRY','final_url':final_url,'stage3_send_ready':False}
                                finals=final_control_candidates(all_ctrls)
                        except Exception:
                            confirm_retry_used=False
                if not finals:
                    return {**base,'status':'TECH_DEFER','code':'FINAL_SUBMIT_CONTROL_NOT_FOUND_AFTER_CONFIRM',
                            'final_url':final_url,'stage3_send_ready':False,
                            'confirm_request_submit_retry':confirm_retry_used,
                            'final_control_samples':[
                                {k:x.get(k) for k in ('frame_index','tag','type','label','text')}
                                for x in all_ctrls[:16]
                            ]}
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
            schema_has_captcha=any(CAPTCHA.search(' '.join(str(x.get(k) or '') for k in ('id','name','desc'))) for x in field_schema)
            if schema_has_captcha:
                return {**base,'status':'CAPTCHA','code':'CAPTCHA_FIELD_PRESENT','final_url':final_url,
                        'captcha_present':True,'stage3_send_ready':False,'send_ready_proof_v2':False,
                        'field_schema':field_schema,'lane_mode':LANE_MODE}
            if not field_schema or not schema_has_email or not schema_has_message:
                return {**base,'status':'TECH_DEFER','code':'INCOMPLETE_FIELD_SCHEMA','final_url':final_url,
                        'stage3_send_ready':False,'send_ready_proof_v2':False}
            return {**base,'status':'SAFE_RENDERED_STATIC','code':'REMOTE_FULL_SEND_READY_V3','final_url':final_url,
                    'required_sensitive':False,'required_unfillable':False,'confirm_step':control_kind!='DIRECT_SUBMIT',
                    'captcha_present':False,'sales_prohibited':False,
                    'stage3_send_ready':True,'send_ready_proof_v2':True,'required_fillable':True,
                    'business_contact_form':True,'control_kind':control_kind,'proof_source':'RENDERED_BROWSER_V2',
                    'lane_mode':LANE_MODE,'field_schema':field_schema,
                    'form_fingerprint':hashlib.sha256((final_url+'|frame='+str(best.get('frame_index') or 0)+'|'+str(best['index'])+'|'+control_semantic_text(control)).encode()).hexdigest(),
                    'frame_index':int(best.get('frame_index') or 0),
                    'form_index':int(best.get('index') or 0),
                    'form_action':str(best.get('form_action') or '')[:1000],
                    'form_method':str(best.get('form_method') or '')[:20],
                    'submit_text':control_semantic_text(control)[:300]}
        except PlaywrightTimeoutError as e:
            return {**base,'status':'TECH_DEFER','code':'BROWSER_TIMEOUT','stage3_send_ready':False,
                    'timeout_phase':progress['phase'],'error_detail':str(e)[:300],'lane_mode':LANE_MODE}
        except Exception as e:
            return {**base,'status':'TECH_DEFER','code':'BROWSER_ERROR_'+type(e).__name__,
                    'error_detail':str(e)[:300],'lane_mode':LANE_MODE,'stage3_send_ready':False}
        finally:
            if ctx:
                try:await asyncio.wait_for(ctx.close(),timeout=5)
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
    # Remove tasks that have no route this exact shard/lane can execute. Ranking
    # them ahead of real work caused primary/shard0 to spend whole Browser
    # quanta returning tasks=0/routes=0 while shard1-owned work sat in the same
    # shared task blob.
    pending=[m for m in pending if task_has_shard_work(m)]
    # All PRIORITY_MARKETS are currently sendable and must not starve one
    # another within this worker's bounded lease -- see rank_pending_tasks().
    pending=rank_pending_tasks(pending,PRIORITY_MARKETS)
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
        # Dispatcher emits market-pure, lane-pure tasks. A worker invocation for
        # one lane must never checkpoint another lane's task as globally done;
        # doing so made the first lane erase all work for the remaining lanes.
        task_lane=str(m.get('lane_hint') or '').upper()
        if task_lane and task_lane!=LANE_MODE:
            continue
        part=[];part_ids=set()
        ranked=sorted(list(m.get('routes') or [])[:12],key=route_work_rank)
        for rec in ranked:
            try: rid=int(rec.get('route_id') or 0)
            except Exception: rid=0
            if rid<=0 or rid in seen_routes or rid in part_ids or not shard_accept(rec) or not lane_accept(rec):continue
            if recent_route_blocked(rec,recent_routes):
                recent_skipped+=1
                continue
            part_ids.add(rid);part.append(rec)
        if not part:
            # Only retire an explicit task owned by this lane. Legacy/mixed or
            # other-lane tasks must remain visible to the appropriate future
            # worker invocation.
            if task_lane==LANE_MODE:
                seen.add(tid);chosen.append(m);immediate_done.append(tid)
            continue
        # MAX_ROWS is a hard per-run route budget. Older code let the first
        # eligible task bypass this cap (up to 12 routes), which made a nominal
        # 2-row Render run process 6-8 routes and hit the 190s outer timeout.
        # Partial tasks are safe: do NOT checkpoint the task as done; completed
        # routes enter recent_route_results, so the next run skips them and
        # continues with the remaining routes without duplicate Browser work.
        remaining=max(0,MAX_ROWS-len(rows))
        if remaining<=0:
            break
        selected=[{**rec,'_task_id':tid} for rec in part[:remaining]]
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
                    *(inspect_with_timeout(browser,r,sem,ROUTE_TIMEOUT_SECONDS) for r in batch),
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
                        *(inspect_with_timeout(browser,rows[i],retry_sem,RETRY_TIMEOUT_SECONDS,slow=True) for i in idxs),
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
    timeout_phases={}
    for result in results:
        phase_name=result.get('timeout_phase')
        if phase_name:
            timeout_phases[phase_name]=timeout_phases.get(phase_name,0)+1
    print(json.dumps({'status':'PASS','tasks':len(chosen),'routes':len(rows),
      'status_counts':counts,'code_counts':codes,'code_samples':samples,
      'timeout_phase_counts':timeout_phases,
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
