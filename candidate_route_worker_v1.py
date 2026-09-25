# PAL_REPAIR_OWNER=RENDER_BROWSER | Cross-lane edits prohibited; use published interfaces/contracts.
# PAL_REPAIR_PROTOCOL_V2=GLOBAL_SINGLE_WRITER | CLAIM_LANE=RENDER_BROWSER before edit; ACCEPT_LANE after tests.
# blob512 e2e trigger 1789695148758
# stage2-stage3 queue refresh 2026-09-19 v2
from __future__ import annotations
import concurrent.futures, hashlib, html, json, os, re, subprocess, time, urllib.request
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
try:
    STATE.parent.mkdir(parents=True,exist_ok=True)
except Exception:
    pass
LANE_COUNT=max(1,int(os.environ.get('PAL_CANDIDATE_ROUTE_LANE_COUNT','1') or 1))
LANE_INDEX=max(0,min(LANE_COUNT-1,int(os.environ.get('PAL_CANDIDATE_ROUTE_LANE_INDEX','0') or 0)))
LANE_WORKERS=max(4,min(48,int(os.environ.get('PAL_CANDIDATE_ROUTE_WORKERS','8') or 8)))
LANE_BATCH=max(16,min(256,int(os.environ.get('PAL_CANDIDATE_ROUTE_BATCH','32') or 32)))
RESULT_KEEP=max(16,min(96,int(os.environ.get('PAL_ROUTE_RESULT_KEEP','48') or 48)))
LANE_DEPTH=max(2,min(8,int(os.environ.get('PAL_CANDIDATE_ROUTE_DEPTH','4') or 4)))
SITEMAP_ROOT_LIMIT=max(1,min(5,int(os.environ.get('PAL_CANDIDATE_ROUTE_SITEMAP_ROOTS','5') or 5)))
SITEMAP_CHILD_LIMIT=max(0,min(8,int(os.environ.get('PAL_CANDIDATE_ROUTE_SITEMAP_CHILDREN','8') or 8)))
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36'
BLOB_TIMEOUT_SECONDS=12
CHECKPOINT_ROWS=max(8,min(32,int(os.environ.get('PAL_CANDIDATE_ROUTE_CHECKPOINT_ROWS','16') or 16)))
CONTACT=re.compile(r'(contact|inquir|enquir|get.{0,4}in.{0,4}touch|request.{0,8}(?:a.{0,3})?quote|quotation|sales|commercial|vendor|supplier|procurement|partnership|proposal|お問い合わせ|問合せ|相談)',re.I)
ROUTE_CONTACT=re.compile(r'(?:^|[\s/_-])(contact(?:[\s/_-]*us)?|contactus|inquiry|enquiry|get[\s_-]*in[\s_-]*touch|request[\s_-]*(?:a[\s_-]*)?quote|rfq|business[\s_-]*contact|sales[\s_-]*contact|commercial[\s_-]*contact)(?:$|[\s/_-])',re.I)
VENDOR_ONLY=re.compile(r'(?:^|[\s/_-])(vendor|vendors|supplier|suppliers|procurement|partnership|partnerships)(?:$|[\s/_-])',re.I)
BUSINESS=re.compile(r'(sales|commercial|vendor|supplier|procurement|partnership|partner|proposal|business.{0,8}(?:inquiry|enquiry|contact)|corporate.{0,8}(?:inquiry|enquiry|contact)|work.{0,4}with.{0,4}us|request.{0,8}(?:a.{0,3})?quote)',re.I)
ACTIONABLE_BUSINESS=re.compile(
    r'(business[-_/ ]?(?:inquir(?:y|ies)|enquir(?:y|ies))|'
    r'sales[-_/ ]?(?:inquir(?:y|ies)|enquir(?:y|ies))|(?:sales|business|commercial)[-_/ ]+contact|'
    r'(?:talk[-_/ ]?to|contact[-_/ ]?)(?:our[-_/ ]+)?sales|'
    r'request[-_/ ]+(?:a[-_/ ]+)?quote|quote[-_/ ]+request|get[-_/ ]+(?:a[-_/ ]+)?quote|'
    r'(?:request|schedule|book)[-_/ ]+(?:a[-_/ ]+)?demo|'
    r'(?:schedule|book|request)[-_/ ]+(?:a[-_/ ]+)?(?:free[-_/ ]+)?consult(?:ation|ing[-_/ ]+call)|'
    r'(?:book|schedule)[-_/ ]+(?:a[-_/ ]+)?(?:discovery[-_/ ]+|intro(?:ductory)?[-_/ ]+)?call|'
    r'submit[-_/ ]+(?:a[-_/ ]+)?proposal|work[-_/ ]?with[-_/ ]?us|'
    r'become[-_/ ]?a[-_/ ]?(?:partner|vendor|supplier)|'
    r'(?:discuss|tell[-_/ ]+us[-_/ ]+about)[-_ /]+(?:your[-_/ ]+|a[-_/ ]+)?project|'
    r'project[-_/ ]+(?:inquir|enquir)|new[-_/ ]+business[-_/ ]+(?:inquir|enquir|opportunit)|'
    r'free[-_/ ]+consultation|rfq|rfp)',re.I)
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

def _html_attr(tag,name):
    m=re.search(r'\b'+re.escape(name)+r'\s*=\s*(?:["\']([^"\']*)["\']|([^\s>]+))',str(tag or ''),re.I)
    return html.unescape((m.group(1) if m and m.group(1) is not None else (m.group(2) if m else '')) or '').strip()

def strict_static_form_proof(doc,page_url,contact_intent=False):
    """Return V9 FULL static proof only for deterministic, directly sendable forms.

    This deliberately rejects uncertain required controls. The live sender still
    re-checks domain, prohibition text, CAPTCHA and field requirements before any
    click, so this proof removes redundant Browser preflight rather than safety.
    """
    raw=str(doc or '')
    if not contact_intent or not raw or CAPTCHA.search(raw) or PROHIBIT.search(clean(raw)[:160000]):
        return None
    page_host=host(page_url)
    if not page_host:return None
    for form in re.findall(r'<form\b.*?</form>',raw,re.I|re.S)[:12]:
        if re.search(r'(search|newsletter|subscribe|login|career|recruit|comment|review)',form,re.I):continue
        opener=re.search(r'<form\b[^>]*>',form,re.I|re.S)
        if not opener or not re.search(r"\bmethod\s*=\s*[\"']?post\b",opener.group(0),re.I):continue
        action=_html_attr(opener.group(0),'action')
        if action:
            try:
                ah=host(urljoin(page_url,action))
            except Exception:ah=''
            if not ah or ah!=page_host:continue
        # Direct send only. A pure confirmation/next control stays on Browser.
        controls=[]
        for m in re.finditer(r'<button\b([^>]*)>(.*?)</button>|<input\b([^>]*)>',form,re.I|re.S):
            tag=m.group(0); typ=_html_attr(tag,'type').lower(); txt=clean((m.group(2) or '')+' '+_html_attr(tag,'value')+' '+_html_attr(tag,'aria-label'))
            if (tag.lower().startswith('<button') and typ in ('','submit')) or (tag.lower().startswith('<input') and typ=='submit'):
                controls.append(txt)
        direct=[x for x in controls if re.search(r'(send|submit|送信(?:する)?|問い合わせ(?:る)?|問合せ(?:る)?)',x,re.I) and not re.search(r'^(確認|confirm|review|next|次へ)$',x,re.I)]
        if len(direct)!=1:continue
        schema=[]; has_email=False;has_message=False;required_sensitive=False;required_unfillable=False
        for m in re.finditer(r'<(input|textarea|select)\b[^>]*>',form,re.I|re.S):
            tag=m.group(0); kind=m.group(1).lower(); typ=(_html_attr(tag,'type') or kind).lower();
            if typ in {'hidden','submit','button','image','reset'}:continue
            name=_html_attr(tag,'name');fid=_html_attr(tag,'id');ph=_html_attr(tag,'placeholder');aria=_html_attr(tag,'aria-label')
            desc=' '.join(x for x in (name,fid,ph,aria) if x).strip(); req=bool(re.search(r'\brequired\b',tag,re.I) or _html_attr(tag,'aria-required').lower()=='true')
            role=''
            if typ=='email' or re.search(r'(e-?mail|メール)',desc,re.I):role='email';has_email=True
            elif kind=='textarea' or re.search(r'(message|inquir|enquir|comment|description|内容|詳細|用件)',desc,re.I):role='message';has_message=True
            elif re.search(r'(company|organization|organisation|会社|法人|企業)',desc,re.I):role='company'
            elif re.search(r'(full.?name|contact.?name|your.?name|氏名|お名前|担当者|(^|[_-])name($|[_-]))',desc,re.I):role='name'
            elif re.search(r'(subject|件名|title)',desc,re.I):role='subject'
            elif typ=='url' or re.search(r'(website|web.?site|url|サイト)',desc,re.I):role='url'
            sensitive=bool(SENSITIVE_FIELD.search(desc) or typ in {'tel','file','password','date','datetime-local'})
            if req and sensitive:required_sensitive=True
            if req and not sensitive:
                if typ=='checkbox':
                    if not re.search(r'(privacy|terms|policy|consent|agree|同意|個人情報|プライバシ|規約)',desc,re.I):required_unfillable=True
                elif typ=='radio' or kind=='select':required_unfillable=True
                elif role not in {'email','message','company','name','subject','url'}:required_unfillable=True
            schema.append({'id':fid,'name':name,'tag':kind,'type':typ,'required':req,'role':role,'desc':desc[:240]})
        if not has_email or not has_message or required_sensitive or required_unfillable:continue
        normalized=re.sub(r'\s+',' ',form).strip()
        return {
            'proof_contract':'V9_STATIC_FULL_SEND_READY_V1','proof_version':'STAGE3_FULL_SEND_READY_V3','proof_source':'RENDER_STAGE2_STATIC_DOM_V9',
            'stage3_send_ready':True,'send_ready_proof_v2':True,'required_fillable':True,'business_contact_form':True,
            'required_sensitive':False,'required_unfillable':False,'captcha_present':False,'sales_prohibited':False,'control_kind':'DIRECT_SUBMIT',
            'form_fingerprint':hashlib.sha256(normalized.encode('utf-8','ignore')).hexdigest(),'field_schema':schema,'form_action':action or page_url,
            'final_url':page_url,'submit_text':direct[0][:120]
        }
    return None

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
        rr=requests.get(fresh,headers=headers,timeout=BLOB_TIMEOUT_SECONDS)
        rr.raise_for_status()
        raw=rr.content
    else:
        cp=subprocess.run([
            'curl','-fsS','--connect-timeout','3','--max-time',str(BLOB_TIMEOUT_SECONDS),
            '-A',UA,'-H','Accept: application/json',
            '-H','Cache-Control: no-cache, no-store','-H','Pragma: no-cache',
            fresh
        ],capture_output=True,timeout=BLOB_TIMEOUT_SECONDS+3)
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
        rr=requests.put(url,data=data,headers=headers,timeout=BLOB_TIMEOUT_SECONDS)
        rr.raise_for_status()
        return True
    cp=subprocess.run([
        'curl','-fsS','--connect-timeout','3','--max-time',str(BLOB_TIMEOUT_SECONDS),
        '-X','PUT','-A',UA,'-H','Content-Type: application/json',
        '--data-binary','@-',url
    ],input=data,capture_output=True,timeout=BLOB_TIMEOUT_SECONDS+3)
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
    """Publish result + DONE records and report whether the whole task batch is durable.

    A task may be checkpointed into processed_task_ids only after every result/DONE
    record is durably published. Otherwise the source task must remain retryable;
    marking it processed on a transport failure leaves the authoritative task queue
    full forever while the worker reports zero pending work.
    """
    if RESULT_BLOB:
        try:
            q=_blob_get(RESULT_BLOB)
            prior=[x for x in (q.get('messages') or []) if isinstance(x,dict)]
            keys={(str(x.get('kind') or ''),str(x.get('run_id') or ''),str(x.get('task_id') or ''),int(x.get('batch_index') or -1)) for x in msgs}
            prior=[x for x in prior if (str(x.get('kind') or ''),str(x.get('run_id') or ''),str(x.get('task_id') or ''),int(x.get('batch_index') or -1)) not in keys]
            payload={'schema':'PAL_ROUTE_RESULT_QUEUE_V1','updated_at_epoch':int(time.time()),
                     'messages':(prior+list(msgs))[-RESULT_KEEP:]}
            _blob_put(RESULT_BLOB,payload)
            return 'SUPERJSONBLOB_V1',True
        except Exception:
            pass
    ok=0
    for m in msgs:
        ok+=1 if _post_ntfy(m) else 0
    if msgs and ok==len(msgs):
        return 'NTFY_FALLBACK',True
    if ok:
        return 'NTFY_PARTIAL',False
    return 'NO_RESULT_TRANSPORT',False

def durable_done_task_ids():
    """Return task ids with a durable DONE record in the authoritative result blob.

    None means the result store could not be read, in which case local state is
    left untouched (fail conservative). An empty set is a successful read with
    no DONE records.
    """
    if not RESULT_BLOB:
        return None
    try:
        q=_blob_get(RESULT_BLOB)
        return {
            str(m.get('task_id') or '')
            for m in (q.get('messages') or [])
            if isinstance(m,dict)
            and str(m.get('kind') or '')=='PAL_CANDIDATE_ROUTE_TASK_DONE_V1'
            and str(m.get('task_id') or '')
        }
    except Exception:
        return None

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
    for sm in sitemap_urls[:SITEMAP_ROOT_LIMIT]:
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
    for sm in child[:SITEMAP_CHILD_LIMIT]:
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

def candidate_urls(root,doc,domain,preferred=(),sitemap=(),observed=()):
    found=[];seen=set()
    # 0) Reuse exact same-domain URLs already observed upstream. These are not
    # trusted blindly: inspect() still fetches the page and applies the unchanged
    # CAPTCHA/prohibition/form/contact-intent checks before emitting evidence.
    for raw in list(observed or []):
        u=str(raw or '').strip()
        if not u: continue
        if not u.startswith('http'):
            u=urljoin(root,u)
        if host(u)!=domain or u in seen: continue
        blob=urlsplit(u).path.replace('-',' ').replace('_',' ')
        if BAD.search(blob) or not CONTACT.search(blob): continue
        found.append((-8 if BUSINESS.search(blob) else -7,u,'OBSERVED_CONTACT'))
        seen.add(u)
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
    initial_business=bool(ACTIONABLE_BUSINESS.search(initial_route_text))
    require_explicit_business=bool(rec.get('require_explicit_business_channel'))
    initial_sendability=static_sendability_score(doc) if initial_static else 0
    initial_rejected=url_key(root) in rejected_keys
    initial_hint=None;initial_hint_score=-1
    if (initial_static or initial_provider or initial_contact) and not initial_rejected and not CAPTCHA.search(doc) and not PROHIBIT.search(initial_plain):
        # Stage 2 is high recall. Keep a safe generic contact route as fallback,
        # but do not stop discovery before checking whether the same official
        # site publishes a more explicit sales/quote/business route. Stage 3
        # remains the authoritative business/safety gate.
        qscore=route_quality_score(root,'LEARNED_OR_START_URL',initial_static,initial_provider,initial_contact,initial_business,rec.get('preferred_contact_paths') or [])
        qscore=min(100,max(qscore,initial_sendability+(10 if initial_business else 0), (85 if initial_business else 75) if initial_contact else 0))
        rendered_required=bool(initial_contact and not initial_static and not initial_provider)
        if (not initial_vendor_only and initial_contact
                and (not require_explicit_business or initial_business)
                and (initial_sendability>=70 or (initial_provider and qscore>=60) or rendered_required)):
            initial_hint={'contact_url':root,'anchor':'LEARNED_OR_START_URL',
              'static_form_hint':initial_static,'dynamic_hint':bool((initial_provider and initial_sendability<70) or rendered_required),
              'contact_intent_hint':initial_contact,'explicit_business_hint':initial_business,
              'route_quality_score':qscore,'static_sendability_score':initial_sendability,
              'stage2_evidence_pass':True,
              'stage2_evidence':{'official_same_domain':True,'form_present':bool(initial_static or initial_provider),
                                 'requires_rendered_stage3':rendered_required,
                                 'contact_intent':initial_contact,'captcha_absent':True,'sales_prohibited_absent':True,
                                 'sendability_score':initial_sendability},
              'trusted_source_id':'PAL_CANDIDATE_ROUTE_OFFLOAD_V13_CONTACT_ROUTE'}
            if initial_static and initial_sendability>=70:
                strict_proof=strict_static_form_proof(doc,root,initial_contact)
                if strict_proof:initial_hint['strict_static_proof']=strict_proof
            initial_hint_score=qscore
            # Stop early only when the start URL already has a strong static
            # form. A dynamic contact/business page is valid Stage2 evidence, but
            # continuing the same bounded search may find a much higher-yield
            # static form and avoid an expensive low-yield Stage3 Browser pass.
            if initial_business and initial_static and initial_sendability>=70:
                item['route_hint']=initial_hint
                item['pages']=pages;item['errors']=errors
                return item
    observed=[]
    for raw in list(rec.get('observed_contact_urls') or []):
        u=str(raw or '').strip()
        if u and host(u)==domain and url_key(u) not in rejected_keys:
            if u not in observed: observed.append(u)

    best_hint=initial_hint;best_score=initial_hint_score;attempted={url_key(root)}
    def evaluate(candidates):
        nonlocal pages,errors,best_hint,best_score
        for _,u,label in candidates:
            key=url_key(u)
            if key in rejected_keys or key in attempted:
                continue
            attempted.add(key)
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
            explicit_business=bool(ACTIONABLE_BUSINESS.search(route_blob))
            if not (static_hint or provider_hint or strong_contact):continue
            sendability=static_sendability_score(fd) if static_hint else 0
            qscore=route_quality_score(fu,label,static_hint,provider_hint,strong_contact,explicit_business,rec.get('preferred_contact_paths') or [])
            qscore=min(100,max(qscore,sendability+(10 if explicit_business else 0), (85 if explicit_business else 75) if strong_contact else 0))
            # Acceptance criteria are unchanged; this patch changes discovery order only.
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
            if static_hint and sendability>=70:
                strict_proof=strict_static_form_proof(fd,fu,strong_contact)
                if strict_proof:hint['strict_static_proof']=strict_proof
            if qscore>best_score:
                best_score=qscore;best_hint=hint
            # A dynamic route is useful fallback evidence, but live measurements
            # show its Stage3 FULL-proof yield is far lower than a static form.
            # Stay inside the same bounded candidate list and keep looking for a
            # deterministic static form; only that stronger result ends probing.
            if static_hint and sendability>=70:
                return True
        return False
    def bounded_candidates(sitemap=(),cap=None):
        """Keep the same probe budget while reserving explicit B2B routes."""
        cap=max(1,int(cap or LANE_DEPTH))
        ranked=candidate_urls(root,doc,domain,rec.get('preferred_contact_paths') or [],sitemap,observed)
        chosen=list(ranked[:cap])
        def explicit_contact(cand):
            rank,u,label=cand
            blob=(str(label)+' '+urlsplit(str(u or '')).path.replace('-',' ').replace('_',' '))
            # Outside the US, only elevate an explicit route that the company
            # actually published/observed (negative rank). For US strict B2B
            # routing, keep the existing bounded guessed-path reservation.
            published_or_us_strict=(int(rank)<0 or require_explicit_business)
            return bool(published_or_us_strict
                        and ACTIONABLE_BUSINESS.search(blob)
                        and ROUTE_CONTACT.search(' '+blob+' '))
        # Generic /contact pages can consume the bounded probe budget before a
        # company-published /sales/contact, /business/inquiry or quote route.
        # Reserve up to two existing slots for those higher-yield routes; the
        # total page-probe cap is unchanged for every market.
        explicit=[x for x in ranked if explicit_contact(x)]
        reserve=min(2,cap)
        for cand in explicit[:reserve]:
            if cand in chosen:
                continue
            replace=None
            for idx in range(len(chosen)-1,-1,-1):
                if not explicit_contact(chosen[idx]):
                    replace=idx
                    break
            if replace is None:
                if len(chosen)<cap:
                    chosen.append(cand)
                continue
            chosen[replace]=cand
        chosen.sort(key=lambda cand:(0 if explicit_contact(cand) else 1,cand[0],len(cand[1])))
        return chosen[:cap]

    # Fast path: observed upstream URLs, live page links and learned paths first.
    evaluate(bounded_candidates([],LANE_DEPTH))
    if best_hint and best_hint.get('static_form_hint') and int(best_hint.get('static_sendability_score') or 0)>=70:
        item['route_hint']=best_hint
        item['pages']=pages;item['errors']=errors
        return item

    # If the fast path found only dynamic evidence, use the existing bounded
    # sitemap fallback to look for a stronger static form before committing the
    # candidate to Stage3 Browser. The dynamic hint remains the fallback.
    sitemap=sitemap_contact_urls(root,domain)
    if sitemap:pages+=1
    evaluate(bounded_candidates(sitemap,max(LANE_DEPTH,4)))
    if best_hint:item['route_hint']=best_hint
    item['pages']=pages;item['errors']=errors
    return item

def safe_inspect(rec):
    """Fail-isolate one candidate so a 128-row batch cannot die on one bad site."""
    try:
        return inspect(rec)
    except Exception as e:
        return {
            'candidate_id':rec.get('candidate_id'),
            'domain':str(rec.get('domain') or '').lower().removeprefix('www.'),
            'country_code':rec.get('country'),
            'market':rec.get('market'),
            'verified':False,
            'pages':0,
            'errors':1,
            'worker_error':type(e).__name__,
        }


def main():
    started=time.monotonic()
    try:state=json.loads(STATE.read_text())
    except Exception:state={}
    processed=list(state.get('processed_task_ids') or [])
    current_messages=messages()
    current_ids={str(m.get('task_id') or '') for m in current_messages if str(m.get('task_id') or '')}
    remote_done=durable_done_task_ids()
    stale_local_done=set()
    if remote_done is not None:
        stale_local_done=(set(processed) & current_ids) - set(remote_done)
        if stale_local_done:
            processed=[tid for tid in processed if tid not in stale_local_done]
    done=set(processed);pending=[]
    for m in current_messages:
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
    selected=[];rows=[];seen_tasks=set();seen_domains=set();complete_task_ids=[]
    for task in ordered:
        tid=str(task.get('task_id') or '')
        if not tid or tid in seen_tasks:continue
        room=max(0,LANE_BATCH-len(rows))
        if room<=0:break
        seen_tasks.add(tid)
        part=[]
        for rec in list(task.get('candidates') or []):
            domain=str(rec.get('domain') or '').lower().removeprefix('www.')
            if not domain or domain in seen_domains:continue
            seen_domains.add(domain);part.append(rec)
        taken=part[:room]
        selected.append(task);rows.extend(taken)
        # Never emit TASK_DONE for a task whose unique candidate slice was
        # truncated by the global batch cap. That task remains retryable and
        # its already-published route results are idempotent on the next pass.
        if len(taken)==len(part):complete_task_ids.append(tid)
        if len(rows)>=LANE_BATCH:break
    pending=selected;results=[]
    task_ids=[str(t.get('task_id') or '') for t in pending if t.get('task_id')]
    run_id=str(int(time.time()))+'-'+str(os.getpid())
    transport=('SUPERJSONBLOB_V1' if RESULT_BLOB else 'NO_RESULTS')
    publish_ok=True;durable_results=0;incremental_enabled=True
    if rows:
        # Persist completed inspections in small bounded chunks instead of
        # waiting for the slowest site in the whole batch. Sixteen rows keeps
        # result visibility smooth while remaining cheap enough for the blob
        # transport and parent Render runtime ceiling.
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(LANE_WORKERS,len(rows))) as ex:
            futures=[ex.submit(safe_inspect,rec) for rec in rows]
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())
                if incremental_enabled and len(results)-durable_results>=CHECKPOINT_ROWS:
                    chunk=results[durable_results:durable_results+CHECKPOINT_ROWS]
                    msg={'kind':'PAL_CANDIDATE_ROUTE_BATCH_V2','run_id':run_id,
                         'batch_index':durable_results//CHECKPOINT_ROWS,'items':chunk,
                         'task_ids':task_ids,'last_seen_epoch':int(time.time())}
                    transport,ok=publish_messages([msg])
                    if ok:
                        durable_results+=len(chunk)
                    else:
                        # Keep processing, then retry the undurable suffix in one
                        # final publish. Never checkpoint tasks on a failed write.
                        incremental_enabled=False;publish_ok=False
    final_msgs=[]
    for i in range(durable_results,len(results),CHECKPOINT_ROWS):
        final_msgs.append({'kind':'PAL_CANDIDATE_ROUTE_BATCH_V2','run_id':run_id,
              'batch_index':i//CHECKPOINT_ROWS,'items':results[i:i+CHECKPOINT_ROWS],
              'task_ids':task_ids,'last_seen_epoch':int(time.time())})
    # DONE is emitted only for tasks fully represented inside this run's batch.
    # A truncated final task remains retryable, preventing silent candidate loss.
    for tid in complete_task_ids:
        final_msgs.append({'kind':'PAL_CANDIDATE_ROUTE_TASK_DONE_V1','task_id':tid,
                           'run_id':run_id,'last_seen_epoch':int(time.time())})
    if final_msgs:
        transport,final_ok=publish_messages(final_msgs)
        publish_ok=bool(final_ok)
        if final_ok:durable_results=len(results)
    elif results:
        publish_ok=(durable_results==len(results))
    else:
        publish_ok=True
    committed_task_ids=complete_task_ids if publish_ok and durable_results==len(results) else []
    processed=(processed+committed_task_ids)[-1600:]
    state={'updated_at_epoch':int(time.time()),'processed_task_ids':processed,'last_tasks':len(pending),
           'last_candidates':len(rows),'last_pages_checked':sum(int(x.get('pages') or 0) for x in results),
           'last_routes':sum(bool(x.get('route_hint')) for x in results),
           'last_verified':sum(bool(x.get('verified')) for x in results),
           'last_errors':sum(int(x.get('errors') or 0) for x in results),
           'last_inspect_exceptions':sum(bool(x.get('worker_error')) for x in results),
           'last_elapsed_seconds':round(time.monotonic()-started,3),'transport':transport,
           'publish_ok':bool(publish_ok),'committed_tasks':len(committed_task_ids),
           'stale_local_done_reopened':len(stale_local_done)}
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps({'status':'PASS','tasks':len(pending),'candidates':len(rows),
                      'pages_checked':state['last_pages_checked'],'routes':state['last_routes'],
                      'verified':state['last_verified'],'errors':state['last_errors'],
                      'inspect_exceptions':state['last_inspect_exceptions'],
                      'elapsed_seconds':state['last_elapsed_seconds'],'transport':transport}))

if __name__=='__main__':main()
