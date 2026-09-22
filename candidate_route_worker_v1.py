# blob512 e2e trigger 1789695148758
# stage2-stage3 queue refresh 2026-09-19 v2
from __future__ import annotations
import concurrent.futures, html, json, os, re, subprocess, time, urllib.request
try:
    import requests
except Exception:
    requests=None
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

TASK_TOPIC=os.environ.get('PAL_TASK_TOPIC','')
RESULT_TOPIC=os.environ.get('PAL_RESULT_TOPIC','')
TASK_BLOB=os.environ.get('PAL_ROUTE_TASK_BLOB_URL','')
RESULT_BLOB=os.environ.get('PAL_ROUTE_RESULT_BLOB_URL','')
STATE=Path(os.environ.get('PAL_CANDIDATE_ROUTE_STATE_FILE','pal_offload/candidate_route_state_v1.json'))
LANE_COUNT=max(1,int(os.environ.get('PAL_CANDIDATE_ROUTE_LANE_COUNT','1') or 1))
LANE_INDEX=max(0,min(LANE_COUNT-1,int(os.environ.get('PAL_CANDIDATE_ROUTE_LANE_INDEX','0') or 0)))
LANE_WORKERS=max(4,min(48,int(os.environ.get('PAL_CANDIDATE_ROUTE_WORKERS','8') or 8)))
LANE_BATCH=max(16,min(256,int(os.environ.get('PAL_CANDIDATE_ROUTE_BATCH','32') or 32)))
LANE_DEPTH=max(3,min(8,int(os.environ.get('PAL_CANDIDATE_ROUTE_DEPTH','4') or 4)))
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36'
CONTACT=re.compile(r'(contact|inquir|enquir|get.{0,4}in.{0,4}touch|request.{0,8}(?:a.{0,3})?quote|quotation|sales|commercial|vendor|supplier|procurement|partnership|proposal|お問い合わせ|問合せ|相談)',re.I)
ROUTE_CONTACT=re.compile(r'(?:^|[\s/_-])(contact(?:[\s/_-]*us)?|contactus|inquiry|enquiry|get[\s_-]*in[\s_-]*touch|request[\s_-]*(?:a[\s_-]*)?quote|rfq|business[\s_-]*contact|sales[\s_-]*contact|commercial[\s_-]*contact)(?:$|[\s/_-])',re.I)
VENDOR_ONLY=re.compile(r'(?:^|[\s/_-])(vendor|vendors|supplier|suppliers|procurement|partnership|partnerships)(?:$|[\s/_-])',re.I)
BUSINESS=re.compile(r'(sales|commercial|vendor|supplier|procurement|partnership|partner|proposal|business.{0,8}(?:inquiry|enquiry|contact)|corporate.{0,8}(?:inquiry|enquiry|contact)|work.{0,4}with.{0,4}us|request.{0,8}(?:a.{0,3})?quote)',re.I)
BAD=re.compile(r'(career|jobs?|recruit|press|media|news|blog|support|help|privacy|security|complaint|investor)',re.I)
FORM=re.compile(r'(hubspot|marketo|pardot|formstack|gravityforms|wpforms|jotform|salesforce)',re.I)
PRIORITY_MARKETS={x.strip() for x in os.environ.get('PAL_ROUTE_PRIORITY_MARKETS','').split(',') if x.strip()}
PRIORITY_STRICT=os.environ.get('PAL_ROUTE_PRIORITY_STRICT','').lower() in {'1','true','yes'}

def _priority_filter(tasks):
    if not PRIORITY_MARKETS:return list(tasks)
    preferred=[]
    for task in tasks:
        markets={str(r.get('market') or '') for r in (task.get('candidates') or []) if isinstance(r,dict)}
        if markets & PRIORITY_MARKETS:preferred.append(task)
    if preferred or PRIORITY_STRICT:return preferred
    return list(tasks)

SENSITIVE_FIELD=re.compile(r'(phone|tel|mobile|address|postal|postcode|zip|電話|住所|郵便|都道府県|市区町村|番地)',re.I)
SUBMIT_HINT=re.compile(r'(send|submit|contact|inquiry|enquiry|送信|確認|次へ)',re.I)
CAPTCHA=re.compile(r'(recaptcha|hcaptcha|turnstile|captcha)',re.I)
PROHIBIT=re.compile(r'(no unsolicited|no sales solicit|sales solicitations? (?:are )?(?:not|prohibited)|営業(?:目的|勧誘).{0,12}(禁止|お断り)|セールス.{0,12}(禁止|お断り))',re.I)
COMMON=('vendor','vendors','supplier','suppliers','procurement','partnership','partnerships','business/inquiry','business/contact','sales/contact','commercial','request-a-quote','proposal','contact','contact-us','contactus','inquiry','enquiry','get-in-touch','quote','sales','business','お問い合わせ')

def host(u):
    try:return (urlsplit(str(u or '')).hostname or '').lower().removeprefix('www.')
    except Exception:return ''

def www_alias_url(u):
    try:
        p=urlsplit(str(u or ''))
        raw=(p.hostname or '').lower()
        if not raw or raw.startswith('www.'):
            return ''
        port=(':'+str(p.port)) if p.port else ''
        return urlunsplit((p.scheme,'www.'+raw+port,p.path,p.query,p.fragment))
    except Exception:
        return ''

def clean(s):return ' '.join(re.sub(r'<[^>]+>',' ',html.unescape(str(s or ''))).split())

def static_sendability_score(doc):
    """Cheap Stage-2 sendability estimate. Safety is re-checked authoritatively in Stage 3."""
    best=0
    for form in re.findall(r'<form\b.*?</form>',doc or '',re.I|re.S)[:12]:
        if re.search(r'(search|newsletter|subscribe|login|career|recruit|comment|review)',form,re.I):continue
        if CAPTCHA.search(form):continue
        email_ok=bool(re.search(r"type=[\"']email[\"']|name=[\"'][^\"']*(?:email|mail)",form,re.I))
        message_ok=bool(re.search(r"<textarea\b|name=[\"'][^\"']*(?:message|inquiry|enquiry|comment|description)",form,re.I))
        submit_ok=bool(re.search(r"type=[\"']submit[\"']|<button[^>]*>[^<]*(?:send|submit|contact|inquiry|enquiry|送信|確認|次へ)",form,re.I))
        if not (email_ok and message_ok and submit_ok):continue
        sensitive_required=False
        for tag in re.findall(r'<(?:input|textarea|select)\b[^>]*>',form,re.I|re.S):
            if re.search(r"\brequired\b|aria-required=[\"']true",tag,re.I) and SENSITIVE_FIELD.search(tag):
                sensitive_required=True;break
        if sensitive_required:continue
        opener=re.search(r'<form\b[^>]*>',form,re.I|re.S)
        # Stage 2 is an evidence gate, not a guesser. A static form is eligible only
        # when it is an actual POST workflow; GET forms are commonly search/filter UI.
        if not opener or not re.search(r"method=[\"']?post",opener.group(0),re.I):
            continue
        score=80
        if re.search(r'(contact|inquir|enquir|お問い合わせ|問合せ|相談|business|sales)',form,re.I):score+=10
        best=max(best,score)
    return min(90,best)

def fetch(u,timeout=4,max_bytes=600000):
    marker='__PAL_HTTP_META__'
    def once(target):
        cmd=['curl','-L','-sS','--compressed','--connect-timeout','2','--max-time',str(int(timeout)),
             '-A',UA,'-H','Accept: text/html,application/xhtml+xml',
             '-w','\n'+marker+'%{http_code}\t%{url_effective}\n',str(target)]
        try:
            cp=subprocess.run(cmd,capture_output=True,timeout=timeout+2)
            raw=(cp.stdout or b'').decode('utf-8','ignore');pos=raw.rfind('\n'+marker)
            stderr=(cp.stderr or b'').decode('utf-8','ignore')
            if pos<0:
                return '',0,'',int(cp.returncode or 0),stderr
            body=raw[:pos][:max_bytes];meta=raw[pos+1+len(marker):].strip().split('	',1)
            final=(meta[1] if len(meta)>1 else str(target))
            return final,int(meta[0] or 0),body,int(cp.returncode or 0),stderr
        except Exception as e:
            return '',0,'',-1,type(e).__name__
    final,status,body,rc,err=once(u)
    if rc==0 and status>0:
        return final,status,body
    # Discovery normalizes company domains without www. Some official sites
    # publish DNS/TLS only on www; retry that exact same-domain alias for curl
    # DNS/certificate failures. TLS verification remains enabled.
    fallback=www_alias_url(u)
    if fallback and (rc in {6,60} or re.search(r'(Could not resolve host|SSL certificate problem)',err,re.I)):
        final,status,body,_,_=once(fallback)
    return final,status,body

def _blob_get(url):
    sep='&' if '?' in url else '?'
    fresh=url+sep+'_pal_ts='+str(time.time_ns())
    headers={'User-Agent':UA,'Accept':'application/json',
             'Cache-Control':'no-cache, no-store','Pragma':'no-cache'}
    if requests is not None:
        rr=requests.get(fresh,headers=headers,timeout=60)
        rr.raise_for_status()
        raw=rr.content
    else:
        cp=subprocess.run([
            'curl','-fsS','--connect-timeout','5','--max-time','60',
            '-A',UA,'-H','Accept: application/json',
            '-H','Cache-Control: no-cache, no-store','-H','Pragma: no-cache',
            fresh
        ],capture_output=True,timeout=65)
        if cp.returncode!=0:
            raise RuntimeError('BLOB_GET_CURL_'+str(cp.returncode))
        raw=cp.stdout or b''
    if len(raw)>25000000:
        raise RuntimeError('BLOB_TOO_LARGE')
    return json.loads(raw.decode('utf-8','ignore'))

def _blob_put(url,obj):
    data=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode()
    headers={'Content-Type':'application/json','User-Agent':UA}
    if requests is not None:
        rr=requests.put(url,data=data,headers=headers,timeout=60)
        rr.raise_for_status()
        return True
    cp=subprocess.run([
        'curl','-fsS','--connect-timeout','5','--max-time','60',
        '-X','PUT','-A',UA,'-H','Content-Type: application/json',
        '--data-binary','@-',url
    ],input=data,capture_output=True,timeout=65)
    if cp.returncode!=0:
        raise RuntimeError('BLOB_PUT_CURL_'+str(cp.returncode))
    return True

def _post_ntfy(msg):
    if not RESULT_TOPIC:return False
    try:
        data=json.dumps(msg,ensure_ascii=False,separators=(',',':')).encode()
        q=urllib.request.Request('https://ntfy.sh/'+RESULT_TOPIC,data=data,method='POST',
                                 headers={'Content-Type':'application/json','User-Agent':UA})
        urllib.request.urlopen(q,timeout=10).read()
        return True
    except Exception:return False

def publish_messages(msgs):
    if RESULT_BLOB:
        try:
            q=_blob_get(RESULT_BLOB)
            prior=[x for x in (q.get('messages') or []) if isinstance(x,dict)]
            keys={(str(x.get('kind') or ''),str(x.get('run_id') or ''),str(x.get('task_id') or ''),int(x.get('batch_index') or -1)) for x in msgs}
            prior=[x for x in prior if (str(x.get('kind') or ''),str(x.get('run_id') or ''),str(x.get('task_id') or ''),int(x.get('batch_index') or -1)) not in keys]
            payload={'schema':'PAL_ROUTE_RESULT_QUEUE_V1','updated_at_epoch':int(time.time()),
                     'messages':(prior+list(msgs))[-256:]}
            _blob_put(RESULT_BLOB,payload)
            return 'SUPERJSONBLOB_V1'
        except Exception:
            pass
    ok=0
    for m in msgs:
        ok+=1 if _post_ntfy(m) else 0
    return 'NTFY_FALLBACK' if ok else 'NO_RESULT_TRANSPORT'

def _event_payload(e):
    try:return json.loads(e.get('message') or '{}')
    except Exception:
        att=e.get('attachment') or {};au=str(att.get('url') or '')
        if not au:return None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(au,headers={'User-Agent':UA}),timeout=12) as ar:
                    return json.loads(ar.read(1800000).decode('utf-8','ignore'))
            except Exception:
                if attempt<2:time.sleep(0.35*(attempt+1))
        return None

def messages():
    out=[];seen=set();blob_ok=False
    if TASK_BLOB:
        try:
            q=_blob_get(TASK_BLOB);blob_ok=True
            for m in q.get('tasks') or []:
                if not isinstance(m,dict) or m.get('kind')!='PAL_CANDIDATE_ROUTE_TASK_V1':continue
                tid=str(m.get('task_id') or '')
                if tid and tid not in seen:seen.add(tid);out.append(m)
        except Exception:
            pass
    if TASK_TOPIC and not blob_ok:
        u=f'https://ntfy.sh/{TASK_TOPIC}/json?poll=1&since=3h'
        try:
            with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':UA}),timeout=12) as r:
                raw=r.read(4500000).decode('utf-8','ignore')
            for line in raw.splitlines():
                try:e=json.loads(line)
                except Exception:continue
                m=_event_payload(e)
                if not isinstance(m,dict) or m.get('kind')!='PAL_CANDIDATE_ROUTE_TASK_V1':continue
                tid=str(m.get('task_id') or '')
                if tid and tid not in seen:seen.add(tid);out.append(m)
        except Exception:
            pass
    return out

def sitemap_contact_urls(root,domain):
    """Find official contact/business URLs from sitemap roots and one sitemap-index level."""
    base=urlsplit(root); site=f'{base.scheme}://{base.netloc}/'
    sitemap_urls=[
        urljoin(site,'sitemap.xml'),
        urljoin(site,'sitemap_index.xml'),
        urljoin(site,'wp-sitemap.xml'),
    ]
    # robots.txt often points to the real sitemap index.
    try:
        rfu,rst,rdoc=fetch(urljoin(site,'robots.txt'),2,180000)
        if rfu and host(rfu)==domain and rst<400 and rdoc:
            for m in re.findall(r'^\\s*Sitemap:\\s*(\\S+)',rdoc,re.I|re.M):
                u=html.unescape(m).strip()
                if host(u)==domain:sitemap_urls.append(u)
    except Exception:
        pass
    sm_seen=set();page_urls=[];child=[]
    for sm in sitemap_urls[:5]:
        if sm in sm_seen:continue
        sm_seen.add(sm)
        fu,st,doc=fetch(sm,3,900000)
        if not fu or host(fu)!=domain or st>=400 or not doc:continue
        locs=[html.unescape(x).strip() for x in re.findall(r'<loc[^>]*>(.*?)</loc>',doc,re.I|re.S)]
        for u in locs:
            if host(u)!=domain:continue
            path=(urlsplit(u).path or '').lower()
            if ('sitemap' in path and path.endswith('.xml')) or path.endswith('sitemap.xml'):
                child.append(u)
            else:
                page_urls.append(u)
    # One bounded child level covers WordPress and common sitemap-index layouts.
    for sm in child[:8]:
        if sm in sm_seen:continue
        sm_seen.add(sm)
        fu,st,doc=fetch(sm,3,900000)
        if not fu or host(fu)!=domain or st>=400 or not doc:continue
        page_urls.extend(html.unescape(x).strip() for x in re.findall(r'<loc[^>]*>(.*?)</loc>',doc,re.I|re.S))
    out=[];seen=set()
    for u in page_urls:
        if host(u)!=domain or u in seen:continue
        blob=urlsplit(u).path.replace('-',' ').replace('_',' ')
        if BAD.search(blob) or not CONTACT.search(blob):continue
        rank=-2 if BUSINESS.search(blob) else -1
        out.append((rank,u,'SITEMAP'));seen.add(u)
    out.sort(key=lambda x:(x[0],len(x[1])))
    return out[:12]

def candidate_urls(root,doc,domain,preferred=(),sitemap=()):
    found=[];seen=set()
    # 1) Exact links explicitly published by the company are strongest evidence.
    for m in re.finditer(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>",doc,re.I|re.S):
        href=html.unescape(m.group(1));lab=clean(m.group(2));u=urljoin(root,href).split('#',1)[0]
        blob=lab+' '+urlsplit(u).path.replace('-',' ').replace('_',' ')
        if u in seen or host(u)!=domain or BAD.search(blob) or not CONTACT.search(blob):continue
        rank=-6 if BUSINESS.search(blob) else -5
        found.append((rank,u,lab));seen.add(u)
    # 2) Sitemap URLs are also company-published evidence.
    for rank,u,label in list(sitemap or []):
        if u not in seen:
            found.append((-4 if BUSINESS.search(urlsplit(u).path) else -3,u,label));seen.add(u)
    # 3) Learned SENT_CONFIRMED paths are useful priors, but never outrank observed links.
    for p in list(preferred or []):
        u=urljoin(root,'/'+str(p).lstrip('/'))
        if u not in seen:found.append((-2,u,str(p)));seen.add(u)
    # 4) Generic guesses are last-resort only. Prefer canonical contact/inquiry
    # paths before vendor/supplier guesses so the bounded LANE_DEPTH budget is
    # spent on routes that can actually satisfy ROUTE_CONTACT.
    for p in COMMON:
        u=urljoin(root,'/'+p)
        if u in seen:continue
        generic_rank = 2 if ROUTE_CONTACT.search(' '+p.replace('-',' ')+' ') else (3 if BUSINESS.search(p) else 4)
        found.append((generic_rank,u,p));seen.add(u)
    found.sort(key=lambda x:(x[0],len(x[1])))
    return found[:12]

def route_quality_score(url,label,static_hint,provider_hint,strong_contact,explicit_business,preferred=()):
    score=0
    if static_hint: score+=40
    if provider_hint: score+=20
    if strong_contact: score+=15
    if explicit_business: score+=15
    path=(urlsplit(str(url or '')).path or '/').lower().strip('/')
    learned={str(x or '').lower().strip('/') for x in (preferred or [])}
    if path in learned: score+=10
    if BUSINESS.search(str(label or '')+' '+path): score+=10
    return min(100,score)

def inspect(rec):
    domain=str(rec.get('domain') or '').lower().removeprefix('www.')
    homepage=str(rec.get('homepage_url') or ('https://'+domain+'/'))
    src=str(rec.get('source_url') or homepage)
    def url_key(u):
        try:
            q=urlsplit(str(u or ''))
            return (host(u),(q.path or '/').rstrip('/') or '/',q.query or '')
        except Exception:
            return ('',str(u or '').rstrip('/'),'')
    rejected_urls=[]
    for raw in [rec.get('rejected_contact_url')]+list(rec.get('rejected_contact_urls') or []):
        u=str(raw or '').strip()
        if u and host(u)==domain and url_key(u) not in {url_key(x) for x in rejected_urls}:
            rejected_urls.append(u)
    rejected_keys={url_key(x) for x in rejected_urls}
    root,status,doc=fetch(src,4)
    if (not root or host(root)!=domain or status>=400 or not doc) and src.rstrip('/')!=homepage.rstrip('/'):
        root,status,doc=fetch(homepage,4)
    if not root or host(root)!=domain:
        return {'candidate_id':rec.get('candidate_id'),'domain':domain,'country_code':rec.get('country'),
                'market':rec.get('market'),'verified':False,'pages':0,'errors':1}
    epoch=int(time.time())
    item={'candidate_id':rec.get('candidate_id'),'domain':domain,'country_code':rec.get('country'),
          'market':rec.get('market'),'verified':bool(200<=status<400 or status in (401,403)),
          'final_url':root,'http_status':status,'last_seen_epoch':epoch,'pages':1,'errors':0}
    if status>=400:return item
    pages=1;errors=0

    initial_plain=clean(doc)[:120000]
    initial_static=bool(re.search(r'<form\b',doc,re.I))
    initial_provider=bool(FORM.search(doc))
    initial_path=urlsplit(root).path or '/'
    initial_route_text=initial_path.replace('-',' ').replace('_',' ')
    initial_contact=bool(ROUTE_CONTACT.search(' '+initial_route_text+' '))
    initial_vendor_only=bool(VENDOR_ONLY.search(' '+initial_route_text+' ')) and not initial_contact
    initial_business=bool(BUSINESS.search(initial_route_text))
    require_explicit_business=bool(rec.get('require_explicit_business_channel'))
    initial_sendability=static_sendability_score(doc) if initial_static else 0
    initial_rejected=url_key(root) in rejected_keys
    if (initial_static or initial_provider or initial_contact) and not initial_rejected and not CAPTCHA.search(doc) and not PROHIBIT.search(initial_plain):
        # Stage 2 is high recall. General official contact forms are allowed to
        # reach Stage 3; Stage 3 remains the authoritative business/safety gate.
        qscore=route_quality_score(root,'LEARNED_OR_START_URL',initial_static,initial_provider,initial_contact,initial_business,rec.get('preferred_contact_paths') or [])
        qscore=min(100,max(qscore,initial_sendability+(10 if initial_business else 0), (85 if initial_business else 75) if initial_contact else 0))
        rendered_required=bool(initial_contact and not initial_static and not initial_provider)
        if (not initial_vendor_only and initial_contact
                and (not require_explicit_business or initial_business)
                and (initial_sendability>=70 or (initial_provider and qscore>=60) or rendered_required)):
            item['route_hint']={'contact_url':root,'anchor':'LEARNED_OR_START_URL',
              'static_form_hint':initial_static,'dynamic_hint':bool((initial_provider and initial_sendability<70) or rendered_required),
              'contact_intent_hint':initial_contact,'explicit_business_hint':initial_business,
              'route_quality_score':qscore,'static_sendability_score':initial_sendability,
              'stage2_evidence_pass':True,
              'stage2_evidence':{'official_same_domain':True,'form_present':bool(initial_static or initial_provider),
                                 'requires_rendered_stage3':rendered_required,
                                 'contact_intent':initial_contact,'captcha_absent':True,'sales_prohibited_absent':True,
                                 'sendability_score':initial_sendability},
              'trusted_source_id':'PAL_CANDIDATE_ROUTE_OFFLOAD_V13_CONTACT_ROUTE'}
            item['pages']=pages;item['errors']=errors
            return item
    sitemap=sitemap_contact_urls(root,domain)
    if sitemap:pages+=1
    best_hint=None;best_score=-1
    for _,u,label in candidate_urls(root,doc,domain,rec.get('preferred_contact_paths') or [],sitemap)[:LANE_DEPTH]:
        if url_key(u) in rejected_keys:
            continue
        fu,st,fd=fetch(u,3,500000);pages+=1
        if fu and url_key(fu) in rejected_keys:
            continue
        if not fu or host(fu)!=domain or st>=400:errors+=1;continue
        plain=clean(fd)[:120000]
        if CAPTCHA.search(fd) or PROHIBIT.search(plain):continue
        static_hint=bool(re.search(r'<form\b',fd,re.I))
        provider_hint=bool(FORM.search(fd))
        route_blob=(str(label)+' '+urlsplit(fu).path.replace('-',' ').replace('_',' '))
        strong_contact=bool(ROUTE_CONTACT.search(' '+route_blob+' '))
        vendor_only=bool(VENDOR_ONLY.search(' '+route_blob+' ')) and not strong_contact
        explicit_business=bool(BUSINESS.search(route_blob))
        if not (static_hint or provider_hint or strong_contact):continue
        sendability=static_sendability_score(fd) if static_hint else 0
        qscore=route_quality_score(fu,label,static_hint,provider_hint,strong_contact,explicit_business,rec.get('preferred_contact_paths') or [])
        qscore=min(100,max(qscore,sendability+(10 if explicit_business else 0), (85 if explicit_business else 75) if strong_contact else 0))
        # Stage 2 is intentionally high recall; Stage 3 will reject non-business
        # or unsafe forms before anything can become SEND_READY.
        rendered_required=bool(strong_contact and not static_hint and not provider_hint)
        acceptable=(not vendor_only) and strong_contact and (not require_explicit_business or explicit_business) and ((sendability>=70) or (provider_hint and qscore>=60) or rendered_required)
        if not acceptable:continue
        hint={'contact_url':fu,'anchor':str(label)[:160],
              'static_form_hint':static_hint,'dynamic_hint':bool((provider_hint and sendability<70) or rendered_required),
              'contact_intent_hint':strong_contact,'explicit_business_hint':explicit_business,
              'route_quality_score':qscore,'static_sendability_score':sendability,
              'stage2_evidence_pass':True,
              'stage2_evidence':{'official_same_domain':True,'form_present':bool(static_hint or provider_hint),
                                 'requires_rendered_stage3':rendered_required,
                                 'contact_intent':strong_contact,'captcha_absent':True,'sales_prohibited_absent':True,
                                 'sendability_score':sendability},
              'trusted_source_id':'PAL_CANDIDATE_ROUTE_OFFLOAD_V13_CONTACT_ROUTE'}
        if qscore>best_score:
            best_score=qscore;best_hint=hint
        if qscore>=90:break
    if best_hint:item['route_hint']=best_hint
    item['pages']=pages;item['errors']=errors
    return item

def main():
    started=time.monotonic()
    try:state=json.loads(STATE.read_text())
    except Exception:state={}
    processed=list(state.get('processed_task_ids') or []);done=set(processed);pending=[]
    for m in messages():
        tid=str(m.get('task_id') or '')
        if not tid or tid in done:continue
        slot=sum(tid.encode('utf-8')) % LANE_COUNT
        if slot!=LANE_INDEX:continue
        pending.append(m)
    pending=_priority_filter(pending)
    # The shared task blob is already ordered by revenue priority: Stage-3 browser
    # first, then fresh route work for the currently open market. Preserve that order
    # here instead of re-sorting by timestamp and starving the active market.
    ordered=pending[:32]
    selected=[];rows=[];seen_tasks=set();seen_domains=set()
    for task in ordered:
        tid=str(task.get('task_id') or '')
        if not tid or tid in seen_tasks:continue
        seen_tasks.add(tid)
        part=[]
        for rec in list(task.get('candidates') or []):
            domain=str(rec.get('domain') or '').lower().removeprefix('www.')
            if not domain or domain in seen_domains:continue
            seen_domains.add(domain);part.append(rec)
        selected.append(task)
        room=max(0,LANE_BATCH-len(rows))
        if room:rows.extend(part[:room])
        if len(rows)>=LANE_BATCH:
            break
    pending=selected;results=[]
    if rows:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(LANE_WORKERS,len(rows))) as ex:
            for x in ex.map(inspect,rows):results.append(x)
    task_ids=[str(t.get('task_id') or '') for t in pending if t.get('task_id')]
    run_id=str(int(time.time()))+'-'+str(os.getpid());out_msgs=[]
    for i in range(0,len(results),32):
        out_msgs.append({'kind':'PAL_CANDIDATE_ROUTE_BATCH_V2','run_id':run_id,'batch_index':i//32,
              'items':results[i:i+32],'task_ids':task_ids,'last_seen_epoch':int(time.time())})
    for tid in task_ids:
        out_msgs.append({'kind':'PAL_CANDIDATE_ROUTE_TASK_DONE_V1','task_id':tid,'run_id':run_id,'last_seen_epoch':int(time.time())})
    transport=publish_messages(out_msgs) if out_msgs else ('SUPERJSONBLOB_V1' if RESULT_BLOB else 'NO_RESULTS')
    processed=(processed+task_ids)[-1600:]
    state={'updated_at_epoch':int(time.time()),'processed_task_ids':processed,'last_tasks':len(pending),
           'last_candidates':len(rows),'last_pages_checked':sum(int(x.get('pages') or 0) for x in results),
           'last_routes':sum(bool(x.get('route_hint')) for x in results),
           'last_verified':sum(bool(x.get('verified')) for x in results),
           'last_errors':sum(int(x.get('errors') or 0) for x in results),
           'last_elapsed_seconds':round(time.monotonic()-started,3),'transport':transport}
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps({'status':'PASS','tasks':len(pending),'candidates':len(rows),
                      'pages_checked':state['last_pages_checked'],'routes':state['last_routes'],
                      'verified':state['last_verified'],'errors':state['last_errors'],
                      'elapsed_seconds':state['last_elapsed_seconds'],'transport':transport}))

if __name__=='__main__':main()
