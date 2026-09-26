from __future__ import annotations
import asyncio,json,os,re,time,hashlib,hmac,threading
from urllib.parse import urlsplit,unquote_plus,urljoin
from pathlib import Path
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

TASK_URL=os.environ.get('PAL_V9_SEND_TASK_BLOB_URL','').strip()
RESULT_URL=os.environ.get('PAL_V9_SEND_RESULT_BLOB_URL','').strip()
MODE=os.environ.get('PAL_V9_SEND_MODE','SHADOW').strip().upper()
CONTROL_URL=os.environ.get('PAL_V9_CONTROL_HEALTH_URL','https://pal-b2b-v9-plane.jojoagogog.workers.dev/health').strip()
CUTOVER_GENERATION=int(os.environ.get('PAL_V9_CUTOVER_GENERATION','0') or 0)
AUTHORITY=os.environ.get('PAL_V9_PRODUCTION_AUTHORITY','GLOBAL_LEDGER_DO').strip()
FAILOVER_CONTROL_URL=os.environ.get('PAL_V9_FAILOVER_CONTROL_URL','').strip()
FAILOVER_SECRET=os.environ.get('PAL_V9_FAILOVER_SECRET','')
UA='Practical-AI-Lab-V9-Sender/1.0'
MAX_TASKS_PER_TURN=max(1,min(8,int(os.environ.get('PAL_V9_SEND_MAX_TASKS','4') or 4)))
SEND_CONCURRENCY=max(1,min(4,int(os.environ.get('PAL_V9_SEND_CONCURRENCY','2') or 2)))
TASK_WALL_TIMEOUT=max(90.0,min(220.0,float(os.environ.get('PAL_V9_TASK_WALL_TIMEOUT','180') or 180)))
RESULT_IO_TIMEOUT=max(3.0,min(12.0,float(os.environ.get('PAL_V9_RESULT_IO_TIMEOUT','6') or 6)))
TASK_BARRIER_IO_TIMEOUT=max(2.0,min(8.0,float(os.environ.get('PAL_V9_TASK_BARRIER_IO_TIMEOUT','4') or 4)))
SENDER_SHARD=0 if str(os.environ.get('PAL_V9_SENDER_SHARD','1')).strip()=='0' else 1
PROHIBIT=re.compile(r'(営業(?:目的|メール|連絡|勧誘).{0,24}(?:お断り|禁止|不可)|セールス.{0,24}(?:お断り|禁止)|勧誘.{0,24}(?:お断り|禁止)|no\s+(?:sales|solicitation|marketing)\s+(?:messages?|inquiries|contacts?))',re.I)
SENSITIVE=re.compile(r'(\bphone\b|\btel(?:ephone)?\b|\bmobile\b|携帯|電話|\baddress\b|\bpostal\b|\bzip\b|住所|都道府県|市区町村|番地|date of birth|生年月日|\bage\b|年齢)',re.I)
EMAIL=re.compile(r'(e-?mail|(?:^|[^a-z])mail(?:$|[^a-z])|メール)',re.I)
EMAIL_EXAMPLE=re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+',re.I)
MESSAGE=re.compile(r'(message|inquir|enquir|comment|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)',re.I)
COMPANY=re.compile(r'(company|organization|organisation|会社|法人|企業)',re.I)
FIRST_NAME=re.compile(r'(first.?name|given.?name|名(?:前)?$)',re.I)
LAST_NAME=re.compile(r'(last.?name|family.?name|sur.?name|姓$)',re.I)
NAME=re.compile(r'(full.?name|your.?name|contact.?name|お名前|氏名|\bname\b)',re.I)
KANA_FIELD=re.compile(r'(ふりがな|ひらがな|フリガナ|カナ|kana|furigana)',re.I)
SUBJECT=re.compile(r'(subject|件名|title)',re.I)
URLRX=re.compile(r'(website|web.?site|url|サイト)',re.I)
CAPTCHA_SEL='.g-recaptcha,.h-captcha,.cf-turnstile,[data-sitekey],iframe[src*="recaptcha"],iframe[src*="hcaptcha"]'
BOT_HINT=re.compile(r'(?:captcha|recaptcha|hcaptcha|turnstile|not[-_ ]?a?[-_ ]?robot|not[-_ ]?robot|chk[-_ ]?not[-_ ]?robot|human[-_ ]?(?:check|verification)|help\s+us\s+prevent\s+spam|anti[- ]?spam|spam\s+(?:check|question|protection)|security\s+(?:question|check)|which\s+is\s+(?:bigger|larger|smaller)|what\s+is\s+\d+\s*[+\-x×*]\s*\d+|\bquiz\b)',re.I)
SUCCESS=re.compile(r'(送信が完了|thanks?\s+for\s+contacting\s+us|送信完了|お問い合わせ.{0,30}(?:ありがとう|受け付け|受付)|thank\s+you.{0,80}(?:for\s+(?:your\s+)?(?:message|inquir(?:y|ies)|enquir(?:y|ies)|contacting\s+us)|we\s+(?:have|\'ve)\s+received|(?:message|inquir(?:y|ies)|request).{0,30}(?:received|sent|submitted))|we(?:\'ve|\s+have)\s+received\s+your\s+(?:e-?mail|message|inquir(?:y|ies)|enquir(?:y|ies)|request)|(?:message|inquir(?:y|ies)|request).{0,80}(?:sent|received|submitted)|successfully\s+(?:sent|submitted))',re.I)
FAIL=re.compile(r'(入力してください|未入力|入力.{0,20}エラー|エラーがあります|必須(?:項目)?です|必須項目|正しく入力|入力内容.{0,20}(?:誤|エラー)|ご確認の上.{0,40}(?:修正|戻る)|required field|(?:phone(?:\s+number)?|telephone|mobile|address|postal(?:\s+code)?|postcode|zip).{0,30}(?:is\s+)?required|please.{0,30}(?:fill|enter|select|choose)|failed\s+to\s+send|unable\s+to\s+send|could\s+not\s+send|there\s+was\s+an\s+error.{0,60}send|validation error|invalid|submission.{0,24}(?:rejected|failed|declined))',re.I)
FINAL=re.compile(r'(この内容で送信|内容を送信|確認して送信|送信する|^送信$|send\s*(?:message|inquiry|enquiry)?$|submit\s*(?:message|inquiry|enquiry|form)?$)',re.I)
CONFIRM=re.compile(r'(確認画面(?:へ|に(?:進む|進める)?)|入力内容(?:を)?確認|内容(?:を)?確認|確認(?:する|へ)?|confirm|review|next|次へ)',re.I)
CONFIRM_PAGE_TEXT=re.compile(r'(入力内容.{0,40}(?:ご確認|確認)|入力内容のご確認|よろしければ.{0,30}(?:送信|send)|(?:review|confirm).{0,50}(?:information|details|内容).{0,80}(?:send|submit)|please.{0,60}(?:review|confirm).{0,80}(?:send|submit))',re.I)
REJECT_CONTROL=re.compile(r'(戻る|back|cancel|修正|reset|clear|クリア)',re.I)
SAFE_CHOICE=re.compile(r'(general|other|business|partnership|collaboration|inquiry|enquiry|contact|その他|一般|法人|協業|提携|ご相談)',re.I)
UNSAFE_CHOICE=re.compile(r'(job|career|employment|採用|求人|support|customer service|technical support|newsletter|marketing|subscribe|個人|患者|student)',re.I)
CONSENT_OK=re.compile(r'(privacy|terms|policy|consent|agree(?:ment)?|個人情報|プライバシー|規約|同意)',re.I)
CONSENT_BAD=re.compile(r'(newsletter|marketing|promotional|メルマガ|広告|案内を受け取|subscribe)',re.I)
SUBMIT_CONFIRM_CHECK=re.compile(r'(上記の内容でよろしければ|チェック.{0,40}(?:送信|send)|(?:送信|send).{0,40}(?:チェック|check)|confirm.{0,30}(?:submit|send))',re.I)
EMAIL_CLIENT_FORM=re.compile(r'(opens?\s+(?:in\s+)?(?:your\s+)?email\s+client|email\s+draft.{0,50}(?:ready|send)|hit\s+send\s+in\s+(?:your\s+)?mail\s+client|mailto:)',re.I)
COMPLETION_PATH=re.compile(r'/(?:thanks?|thank[-_]?you|complete(?:d)?|completion|success|sent)(?:/|$)',re.I)
ERROR_PATH=re.compile(r'/(?:error|failed|failure|invalid|reject(?:ed)?)(?:[._/-]|$)',re.I)
CONFIRM_PATH=re.compile(r'/(?:confirm|confirmation|review|check)(?:/|$)',re.I)
CONFIRM_QUERY=re.compile(r'(?:[?&](?:mode|step|action)=)(?:check|confirm|confirmation|review)(?:&|#|$)',re.I)
SUCCESS_QUERY=re.compile(r'(?:[?&](?:contact-form-sent|form[-_]?sent|submitted|submission[-_]?success|success)=)(?:1|true|yes|sent|success|\d+)(?:&|$)',re.I)

def host(u):return (urlsplit(str(u or '')).hostname or '').lower().removeprefix('www.')
def sensitive_kind(text):
 d=str(text or '')
 if re.search(r'(\bphone\b|\btelephone\b|\btel\b|\bmobile\b|携帯|電話)',d,re.I):return 'phone'
 if re.search(r'(\bpostal\b|\bpostcode\b|\bzip\b|郵便)',d,re.I):return 'postal'
 if re.search(r'(\baddress\b|住所|都道府県|市区町村|番地)',d,re.I):return 'address'
 return ''

def script_required_sensitive_kinds(text):
 s=str(text or '')[:500000]
 anchors=list(re.finditer(r'(?:contact[-_ ]?form|contact[-_ ]?page|/api/contact|contactForm)',s,re.I))
 if not anchors:return set()
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
 except Exception:return set()
 return script_required_sensitive_kinds(text)

def is_confirm_url(u):
 s=str(u or '')
 try:return bool(CONFIRM_PATH.search(urlsplit(s).path or '/') or CONFIRM_QUERY.search(s))
 except:return bool(CONFIRM_QUERY.search(s))
def strong_http_accept(status,payload_cleared):
 try:return int(status) in {201,202} and bool(payload_cleared)
 except:return False

def provider_app_status(payload):
 if not isinstance(payload,dict):return ''
 for key in ('status','result','state'):
  v=payload.get(key)
  if v not in (None,''):
   return str(v).strip().lower()
 return ''

def pre_submit_http_verdict(status):
 try:s=int(status)
 except:return None
 if s in {401,403,451}:return ('SAFETY_BLOCKED','SITE_ACCESS_DENIED_PRE_SUBMIT')
 if s==429 or 500<=s<=599:return ('TECH_RETRY','SITE_TEMPORARY_HTTP_PRE_SUBMIT')
 if 400<=s<=499:return ('CONFIRMED_NOT_SENT','ROUTE_HTTP_4XX_PRE_SUBMIT')
 return None

def field_required_hint(explicit=False,cls='',desc=''):
 tokens=str(cls or '').split()
 class_required=any(re.fullmatch(r'(?:required|mandatory|hissu(?:val)?|req(?:uired)?(?:field)?)',tok,re.I) for tok in tokens)
 framework_required=any(tok.lower()=='ng-invalid' for tok in tokens)
 d=str(desc or '')
 return bool(explicit or class_required or framework_required or (re.search(r'(必須|required|mandatory|※)',d,re.I) and not re.search(r'(任意|optional)',d,re.I)))

def safe_select_value(options):
 rows=[x for x in (options or []) if isinstance(x,dict)]
 safe=[]
 for x in rows:
  value=str(x.get('v') or '').strip(); text=str(x.get('t') or '').strip()
  if not value:continue
  if SAFE_CHOICE.search(text) and not UNSAFE_CHOICE.search(text):
   safe.append(value)
 return safe[0] if len(safe)==1 else None

async def sticky_fill(loc,value):
 target=str(value)
 async def accepted():
  try:
   actual=str(await loc.input_value(timeout=1200))
   if actual==target:return True
   # HTML single-line INPUT controls normalize CR/LF to spaces. Accept only
   # that browser-defined transformation; all other content differences still fail.
   try:tag=str(await loc.evaluate("e=>e.tagName") or '').upper()
   except Exception:tag=''
   if tag=='INPUT':
    normalized=target.replace('\r\n',' ').replace('\r',' ').replace('\n',' ')
    return actual==normalized
  except Exception:pass
  return False
 try:await loc.fill(target,timeout=2500)
 except Exception:pass
 if await accepted():return
 await loc.evaluate(r"""(e,v)=>{
   const proto=e.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype :
               (e.tagName==='SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype);
   const d=Object.getOwnPropertyDescriptor(proto,'value');
   if(!d||!d.set) throw new Error('NO_NATIVE_VALUE_SETTER');
   d.set.call(e,v);
   e.dispatchEvent(new Event('input',{bubbles:true}));
   e.dispatchEvent(new Event('change',{bubbles:true}));
 }""",target)
 if await accepted():return
 raise RuntimeError('STICKY_FILL_FAILED')

def same_form_redirect_failure(before_url,responses,payload_values_remaining,has_success=False):
 if has_success or int(payload_values_remaining or 0)<=0:return False
 try:
  b=urlsplit(str(before_url or ''));bp=(b.path.rstrip('/') or '/')
 except:return False
 for x in responses or []:
  try:
   if not x.get('matches_form_payload') or not (300<=int(x.get('status') or 0)<400):continue
   loc=str(x.get('location') or '')
   if not loc:continue
   absolute=urljoin(str(before_url or ''),loc);u=urlsplit(absolute);up=(u.path.rstrip('/') or '/')
   if host(absolute)==host(before_url) and up==bp:return True
  except:continue
 return False

def home_navigation_without_submission(before_url,after_url,mutations,payload_values_remaining,has_success=False):
 if has_success or mutations or int(payload_values_remaining or 0)<=0:return False
 try:
  b=urlsplit(str(before_url or ''));a=urlsplit(str(after_url or ''))
  bp=(b.path.rstrip('/') or '/');ap=(a.path.rstrip('/') or '/')
  return host(before_url)==host(after_url) and bp!='/' and ap=='/'
 except:return False

def sender_start_url(task):
 canonical=str((task or {}).get('canonical_url') or '');domain=str((task or {}).get('official_domain') or host(canonical));proof=str((task or {}).get('proof_url') or '')
 if bool((task or {}).get('proof_confirm_step')):return canonical
 return proof if proof and host(proof)==domain else canonical
def _get(u):
 r=requests.get(u,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},params={'ts':int(time.time())},timeout=20);r.raise_for_status();return r.json()
def _put(u,o):
 r=requests.put(u,json=o,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},timeout=20);r.raise_for_status()
def _get_result(u):
 r=requests.get(u,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},params={'ts':int(time.time())},timeout=RESULT_IO_TIMEOUT);r.raise_for_status();return r.json()
def _put_result(u,o):
 r=requests.put(u,json=o,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},timeout=RESULT_IO_TIMEOUT);r.raise_for_status()
def _get_task(u):
 r=requests.get(u,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},params={'ts':time.time_ns()},timeout=TASK_BARRIER_IO_TIMEOUT);r.raise_for_status();return r.json()
def _put_task(u,o):
 r=requests.put(u,json=o,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},timeout=TASK_BARRIER_IO_TIMEOUT);r.raise_for_status()
TASK_WRITE_LOCK=threading.Lock()
def _mark_click_started(task):
 token=str(task.get('token_id') or '')
 if not token:return False
 with TASK_WRITE_LOCK:
  for attempt in range(2):
   try:q=_get_task(TASK_URL)
   except Exception:
    time.sleep(.35*(attempt+1));continue
   found=False;stamp=int(time.time()*1000)
   for x in q.get('tasks') or []:
    if isinstance(x,dict) and str(x.get('token_id') or '')==token:
     if x.get('submit_started') is not True:
      found=False;break
     x['click_started']=True;x['click_started_at']=stamp
     found=True;break
   if not found:
    time.sleep(.35*(attempt+1));continue
   q['updated_at_epoch']=int(time.time())
   try:_put_task(TASK_URL,q)
   except Exception:
    time.sleep(.35*(attempt+1));continue
   # Verify the durable marker after the write. A controller/task-queue
   # read-modify-write racing this worker may otherwise erase the marker.
   try:
    v=_get_task(TASK_URL)
    ok=any(isinstance(x,dict) and str(x.get('token_id') or '')==token and x.get('click_started') is True for x in (v.get('tasks') or []))
   except Exception:ok=False
   if ok:
    task['click_started']=True;task['click_started_at']=stamp;return True
   time.sleep(.35*(attempt+1))
  return False

def _cloud_control_ok():
 if CUTOVER_GENERATION<=0:return False
 try:
  r=requests.get(CONTROL_URL,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},timeout=8);r.raise_for_status();d=r.json();cut=d.get('cutover') or {};led=cut.get('ledger') or {}
  return bool(d.get('service')=='PAL_B2B_V9_PLANE' and d.get('authority')=='GLOBAL_LEDGER_DO' and d.get('mode')=='PRODUCTION' and d.get('ledger_mode')=='PRODUCTION' and d.get('external_send_enabled') is True and int(cut.get('generation') or 0)==CUTOVER_GENERATION and int(led.get('generation') or 0)==CUTOVER_GENERATION and led.get('mode')=='PRODUCTION' and led.get('history_sync_complete') is True and led.get('legacy_writer_disabled') is True and led.get('production_unlock') is True)
 except Exception:return False

def _failover_control_ok():
 if not FAILOVER_CONTROL_URL or not FAILOVER_SECRET or _cloud_control_ok():return False
 try:
  r=requests.get(FAILOVER_CONTROL_URL,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},params={'ts':time.time_ns()},timeout=8);r.raise_for_status();d=r.json()
  if d.get('schema')!='PAL_V9_FAILOVER_CONTROL_V1' or d.get('mode')!='FAILOVER' or d.get('lease_owner')!='MAC_V9_FAILOVER':return False
  if int(d.get('generation') or 0)!=CUTOVER_GENERATION or int(d.get('lease_until_epoch') or 0)<=int(time.time())+5:return False
  sig=str(d.get('sig') or '');unsigned={k:v for k,v in d.items() if k!='sig'}
  raw=json.dumps(unsigned,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
  exp=hmac.new(FAILOVER_SECRET.encode(),raw,hashlib.sha256).hexdigest()
  return bool(sig and hmac.compare_digest(sig,exp))
 except Exception:return False

def _production_control_ok():
 if MODE!='PRODUCTION':return True
 if AUTHORITY=='GLOBAL_LEDGER_DO':return _cloud_control_ok()
 if AUTHORITY=='FAILOVER_BLOB_V1':return _failover_control_ok()
 return False

def _proof_control_ok(task,min_remaining_ms=30000):
 exp=task.get('proof_expires_at')
 if exp in (None,'',0):return False
 try:return int(exp)>int(time.time()*1000)+int(min_remaining_ms)
 except Exception:return False

def _payload_match(payload,message,email):
 if not payload:return False
 vals=[str(payload),unquote_plus(str(payload))]
 try:
  o=json.loads(payload)
  def walk(x):
   if isinstance(x,str):return [x]
   if isinstance(x,dict):return sum((walk(v) for v in x.values()),[])
   if isinstance(x,list):return sum((walk(v) for v in x),[])
   return []
  vals+=walk(o)
 except Exception:pass
 msg=' '.join(str(message or '').split()); em=str(email or '').strip()
 return any(msg and len(msg)>=40 and msg in ' '.join(v.split()) for v in vals) or any(em and em in v for v in vals)
async def desc(loc):
 try:return ' '.join(str(await loc.evaluate("e=>[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText].filter(Boolean).join(' ')" ) or '').split())[:500]
 except:return ''
async def visible_captcha(page):
 # One browser-side DOM pass instead of up to 120 Playwright round trips.
 try:
  return bool(await page.evaluate(r"""sel => {
    const visible = e => {
      const s=getComputedStyle(e),r=e.getBoundingClientRect();
      return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
    };
    for (const e of document.querySelectorAll(sel)) if (visible(e)) return true;
    const bot=/(captcha|recaptcha|hcaptcha|turnstile|not[-_ ]?a?[-_ ]?robot|not[-_ ]?robot|human[-_ ]?(?:check|verification)|help\s+us\s+prevent\s+spam|anti[- ]?spam|spam\s+(?:check|question|protection)|security\s+(?:question|check)|which\s+is\s+(?:bigger|larger|smaller)|what\s+is\s+\d+\s*[+\-x×*]\s*\d+|\bquiz\b)/i;
    for (const e of document.querySelectorAll('input,button,label')) {
      if (!visible(e)) continue;
      const meta=[e.name,e.id,e.className,e.value,e.innerText,e.getAttribute('aria-label'),e.getAttribute('for')].filter(Boolean).join(' ');
      if (bot.test(meta)) return true;
    }
    return false;
  }""",CAPTCHA_SEL))
 except:return False
async def body_text(page,timeout=3500):
 try:return ' '.join((await page.locator('body').inner_text(timeout=timeout)).split())
 except PlaywrightTimeoutError:
  try:return ' '.join(str(await page.evaluate("() => document.body ? document.body.innerText : ''") or '').split())
  except:return None
 except:return None

async def choose_form(page):
 # Score forms in one DOM pass; only return a Playwright locator for the winner.
 try:
  rows=await page.evaluate("""() => {
    const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0&&!e.disabled};
    const email=/(e-?mail|(?:^|[^a-z])mail(?:$|[^a-z])|メール)/i,msg=/(message|inquir|enquir|comment|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)/i;
    const contact=/(contact|inquiry|enquiry|お問い合わせ|お問合せ|ご相談)/i,emailClient=/(opens?\\s+(?:your\\s+)?email\\s+client|email\\s+draft.{0,50}(?:ready|send)|hit\\s+send\\s+in\\s+your\\s+mail\\s+client|mailto:)/i;
    return [...document.querySelectorAll('form')].slice(0,20).map((f,fi)=>{
      const fs=getComputedStyle(f);if(fs.display==='none'||fs.visibility==='hidden') return null;
      let hasE=false,hasM=false;
      for(const e of [...f.querySelectorAll('input,textarea,select')].slice(0,80)){
        if(!vis(e)) continue;
        const d=[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText,e.closest('td')?.previousElementSibling?.innerText,...[...(e.labels||[])].map(l=>l.innerText||'')].filter(Boolean).join(' ');
        const typ=(e.getAttribute('type')||'').toLowerCase();
        hasE=hasE||typ==='email'||email.test(d)||d.includes('@');hasM=hasM||e.tagName==='TEXTAREA'||msg.test(d);
      }
      const txt=(f.innerText||'').slice(0,5000);
      if(emailClient.test(txt)) return null;
      return {fi,hasE,hasM,score:(hasE?5:0)+(hasM?5:0)+(contact.test(txt)?3:0)};
    }).filter(x=>x&&x.hasE&&x.hasM).sort((a,b)=>b.score-a.score);
  }""")
  if not rows:return None
  fi=int(rows[0]['fi']);return (int(rows[0]['score']),fi,page.locator('form').nth(fi))
 except:return None

def ordered_form_frames(page,domain=''):
 all_frames=list(page.frames);main=page.main_frame;same=[];provider=[];other=[];domain=domain or host(page.url)
 provider_re=re.compile(r'(form|contact|hubspot|jotform|typeform|wufoo|formstack|marketo|pardot|salesforce)',re.I)
 for fr in all_frames:
  if fr is main:continue
  fu=str(getattr(fr,'url','') or '')
  if host(fu)==domain:same.append(fr)
  elif provider_re.search(fu):provider.append(fr)
  else:other.append(fr)
 return ([main]+same+provider+other)[:12]
def normalize_proof_submit_text(v):
 s=' '.join(str(v or '').split())
 return re.sub(r'\s*__[A-Z0-9_]+__\s*$','',s,flags=re.I).strip().lower()
def post_submit_validation(new_validation_text,invalid_control_count,provider_success,new_success,payload_cleared):
 return bool(new_validation_text or (int(invalid_control_count or 0)>0 and not ((provider_success or new_success) and payload_cleared)))

async def submitted_form_invalid_count(control):
 # Scope validation to the form actually submitted. Unrelated newsletter/login
 # forms may be :invalid and must not turn a successful contact submit into a failure.
 try:
  return int(await control.evaluate("""e=>{const f=e&&e.closest?e.closest('form'):null;return f?f.querySelectorAll('input:invalid,textarea:invalid,select:invalid').length:0}"""))
 except Exception:
  return 0
def schema_field_role(row):
 d=' '.join(str((row or {}).get(k) or '') for k in ('desc','name','id')).strip()
 typ=str((row or {}).get('type') or '').lower();tag=str((row or {}).get('tag') or '').lower()
 explicit=str((row or {}).get('role') or '').strip().lower()
 if explicit:return explicit
 if typ=='email' or re.search(r'(e-?mail|メール)',d,re.I):return 'email'
 if tag=='textarea' or re.search(r'(message|inquir|enquir|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細|description)',d,re.I):return 'message'
 if re.search(r'(会社|法人|企業|company|organization|organisation)',d,re.I):return 'company'
 if re.search(r'(ふりがな|ひらがな)',d,re.I):return 'name_hiragana'
 if re.search(r'(フリガナ|カナ|kana|furigana)',d,re.I):return 'name_katakana'
 if re.search(r'(姓|苗字|名字|surname|family[ _.-]?name|last[ _.-]?name|\\blname\\b)',d,re.I):return 'last_name'
 if re.search(r'(名|given[ _.-]?name|first[ _.-]?name|\\bfname\\b)',d,re.I):return 'first_name'
 if re.search(r'(氏名|お名前|名前|担当者|full.?name|contact.?name|\\bname\\b)',d,re.I):return 'name'
 if re.search(r'(件名|subject|title)',d,re.I):return 'subject'
 if re.search(r'(部署|部門|department|designation|job.?title|position|役職|職種)',d,re.I):return 'department'
 if typ=='url' or re.search(r'(url|website|ホームページ)',d,re.I):return 'url'
 return ''

async def proof_form_shape_ok(form,proof_submit_text='',proof_field_schema=None):
 try:
  try: form_text=' '.join((await form.inner_text(timeout=1200)).split())[:5000]
  except Exception: form_text=''
  if EMAIL_CLIENT_FORM.search(form_text):return False
  ok=bool(await form.evaluate("""f=>{const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0&&!e.disabled};const email=/(e-?mail|(?:^|[^a-z])mail(?:$|[^a-z])|メール)/i,msg=/(message|inquir|enquir|comment|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)/i;let E=false,M=false;for(const e of [...f.querySelectorAll('input,textarea,select')].slice(0,80)){if(!vis(e))continue;const d=[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText,e.closest('td')?.previousElementSibling?.innerText,...[...(e.labels||[])].map(l=>l.innerText||'')].filter(Boolean).join(' ');const t=(e.getAttribute('type')||'').toLowerCase();E=E||t==='email'||email.test(d)||d.includes('@');M=M||e.tagName==='TEXTAREA'||msg.test(d)}return E&&M}"""))
  if not ok:return False
  schema=[x for x in (proof_field_schema or []) if isinstance(x,dict)][:32]
  if schema:
   matched=0; matched_roles=set()
   for row in schema:
    role=schema_field_role(row)
    loc=await reacquire_visible_field(form,str(row.get('name') or ''),str(row.get('id') or ''),int(row.get('i') if row.get('i') is not None else -1))
    if loc is None:continue
    matched+=1
    if role:matched_roles.add(role)
   expected_roles={schema_field_role(x) for x in schema}
   expected_roles.discard('')
   if 'email' in expected_roles and 'email' not in matched_roles:return False
   if 'message' in expected_roles and 'message' not in matched_roles:return False
   if matched < min(2,len(schema)):return False
  expected=normalize_proof_submit_text(proof_submit_text)
  if not expected:return True
  xs=form.locator('button,input[type=submit],input[type=button],input[type=image]')
  for i in range(min(await xs.count(),40)):
   d=' '.join((await desc(xs.nth(i))).split()).lower()
   if d and (expected==d or expected in d or d in expected):return True
  return False
 except:return False
async def choose_form_any_frame(page,proof_frame_index=None,proof_form_index=None,proof_submit_text='',proof_field_schema=None):
 frames=ordered_form_frames(page)
 try:pfr=int(proof_frame_index) if proof_frame_index is not None else -1
 except:pfr=-1
 try:pfi=int(proof_form_index) if proof_form_index is not None else -1
 except:pfi=-1
 if 0<=pfr<len(frames):
  root=frames[pfr]
  try:
   forms=root.locator('form')
   if 0<=pfi<await forms.count():
    pf=forms.nth(pfi)
    if await proof_form_shape_ok(pf,proof_submit_text,proof_field_schema):return (1000,pfr,pfi,pf)
  except Exception:pass
 schema=[x for x in (proof_field_schema or []) if isinstance(x,dict)][:32]
 if schema:
  schema_hits=[]
  for fri,root in enumerate(frames):
   try:forms=root.locator('form');count=min(await forms.count(),12)
   except Exception:continue
   for fi in range(count):
    f=forms.nth(fi)
    if await proof_form_shape_ok(f,proof_submit_text,schema):
     schema_hits.append((950,fri,fi,f))
  if len(schema_hits)==1:return schema_hits[0]
 best=None
 for fri,root in enumerate(frames):
  c=await choose_form(root)
  if not c:continue
  score,fi,form=c;cand=(int(score),fri,int(fi),form)
  if best is None or cand[0]>best[0]:best=cand
 return best

async def visible_captcha_any(page):
 for root in list(page.frames)[:12]:
  try:
   if await visible_captcha(root):return True
  except Exception:pass
 return False

async def has_any_form(page):
 for root in list(page.frames)[:12]:
  try:
   if await root.locator('form').count()>0:return True
  except Exception:pass
 return False

async def advance_safe_multistep(page,proof_frame_index=None,proof_form_index=None,max_steps=3):
 frames=ordered_form_frames(page,host(page.url))
 try:pfr=int(proof_frame_index) if proof_frame_index is not None else -1
 except:pfr=-1
 try:pfi=int(proof_form_index) if proof_form_index is not None else -1
 except:pfi=-1
 targets=[]
 if 0<=pfr<len(frames):
  try:
   forms=frames[pfr].locator('form')
   if 0<=pfi<await forms.count():targets=[forms.nth(pfi)]
  except Exception:pass
 if not targets:
  for root in frames[:6]:
   try:
    forms=root.locator('form')
    for i in range(min(await forms.count(),4)):targets.append(forms.nth(i))
   except Exception:pass
 steps=0
 for _ in range(max(0,int(max_steps))):
  advanced=False
  for form in targets:
   try:
    # Stop once the actual contact fields are visible; normal sender logic
    # takes over from here.
    core=await form.locator('input,textarea').evaluate_all("""els=>{
      const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return !e.disabled&&s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
      let email=false,msg=false;
      for(const e of els){if(!vis(e))continue;const d=[e.name,e.id,e.placeholder,e.getAttribute('aria-label')].filter(Boolean).join(' ');const t=(e.type||'').toLowerCase();email=email||t==='email'||/(e-?mail|メール)/i.test(d);msg=msg||e.tagName==='TEXTAREA'||/(message|inquir|enquir|お問い合わせ内容|問い合わせ内容|内容)/i.test(d)}
      return {email,msg};
    }""")
    if core.get('email') and core.get('msg'):return steps
    xs=form.locator('button,input[type=button]')
    hits=[]
    for i in range(min(await xs.count(),30)):
     e=xs.nth(i)
     if not await e.is_visible() or not await e.is_enabled():continue
     typ=(await e.get_attribute('type') or 'button').lower()
     if typ=='submit':continue
     label=' '.join(str(await e.evaluate("e=>[e.getAttribute('aria-label'),e.value,e.innerText].filter(Boolean).join(' ')") or '').split())
     if re.fullmatch(r'(continue|next|次へ|続ける|進む)',label,re.I):hits.append(e)
    if len(hits)!=1:continue
    await hits[0].click(timeout=4000);await page.wait_for_timeout(500)
    steps+=1;advanced=True;break
   except Exception:continue
  if not advanced:break
 return steps

async def reveal_candidate_forms(page,proof_frame_index=None,proof_form_index=None):
 frames=ordered_form_frames(page,host(page.url));targets=[]
 try:pfr=int(proof_frame_index);pfi=int(proof_form_index)
 except Exception:pfr=pfi=-1
 if 0<=pfr<len(frames):
  try:
   forms=frames[pfr].locator('form')
   if 0<=pfi<await forms.count():targets.append(forms.nth(pfi))
  except Exception:pass
 if not targets:
  for root in frames[:6]:
   try:
    forms=root.locator('form')
    for i in range(min(await forms.count(),3)):targets.append(forms.nth(i))
   except Exception:pass
 moved=False
 for f in targets[:8]:
  try:
   await f.scroll_into_view_if_needed(timeout=2500);moved=True
  except Exception:pass
 if moved:await page.wait_for_timeout(1200)
 # Dynamic contact widgets often remain visibility:hidden until a normal
 # viewport traversal triggers their IntersectionObserver/animation hook.
 # Reproduce the same harmless viewport event Stage3 uses; never mutate CSS.
 try:
  await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
  await page.wait_for_timeout(1600)
  await page.evaluate("window.scrollTo(0, 0)")
  await page.wait_for_timeout(500)
  moved=True
 except Exception:pass
 return moved

async def safe_checkbox_check(loc,form=None,row=None):
 try:
  await loc.check(timeout=2200)
  if await loc.is_checked(timeout=1000):return True
 except Exception:pass
 try:
  await loc.evaluate(r"""e=>{
    const labs=[...(e.labels||[])];
    const visible=l=>{const s=getComputedStyle(l),r=l.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
    const lab=labs.find(visible)||e.closest('label');
    if(!lab || !visible(lab)) throw new Error('NO_VISIBLE_LABEL');
    lab.click();
  }""")
  if await loc.is_checked(timeout=1200):return True
 except Exception:pass
 field_id=str((row or {}).get('id') or '')
 if form is not None and field_id:
  try:
   labels=form.locator('label')
   indexes=await labels.evaluate_all(
    """(els,id)=>els.map((e,i)=>({i,forId:e.htmlFor||'',s:getComputedStyle(e),r:e.getBoundingClientRect()}))
      .filter(x=>x.forId===id&&x.s.display!=='none'&&x.s.visibility!=='hidden'&&x.r.width>0&&x.r.height>0)
      .map(x=>x.i)""",field_id)
   for idx in indexes[:3]:
    try:
     await labels.nth(int(idx)).click(timeout=3000)
     if await loc.is_checked(timeout=1000):return True
    except Exception:continue
  except Exception:pass
 return False

async def reacquire_visible_field(form,name='',eid='',fallback_index=-1):
 fields=form.locator('input,textarea,select')
 try:
  matches=await fields.evaluate_all("""(els,a)=>els.map((e,i)=>{
    const s=getComputedStyle(e),r=e.getBoundingClientRect();
    const visible=s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
    const identity=(a.id && e.id===a.id) || (a.name && e.name===a.name);
    return {i,ok:identity&&visible&&!e.disabled};
  }).filter(x=>x.ok).map(x=>x.i)""",{'name':str(name or ''),'id':str(eid or '')})
  if matches:return fields.nth(int(matches[0]))
 except Exception:pass
 try:
  if int(fallback_index)>=0:
   loc=fields.nth(int(fallback_index))
   if await loc.is_visible() and await loc.is_enabled():return loc
 except Exception:pass
 return None

def schema_role_value(role,message,email,market):
 company='Practical AI Lab';name='Practical AI Lab 運営' if market=='JP-JA' else 'Practical AI Lab'
 site='https://practical-ai-lab.pages.dev/' if market=='JP-JA' else 'https://practical-ai-lab.pages.dev/global/'
 return {
  'email':email,'message':message,'company':company,'name':name,
  'name_hiragana':'ぷらくてぃかるえーあいらぼ','name_katakana':'プラクティカルエーアイラボ',
  'first_name':'Practical AI','last_name':'Lab',
  'subject':('AI業務改善のご相談' if market=='JP-JA' else 'AI workflow fit check'),
  'department':'Operations','url':site,
 }.get(str(role or ''))

async def fill_proof_schema(form,schema,message,email,market):
 out={'email':False,'message':False,'matched':0,'filled':0,'ids':set(),'names':set(),'indices':set()}
 for row in [x for x in (schema or []) if isinstance(x,dict)][:32]:
  role=schema_field_role(row);value=schema_role_value(role,message,email,market)
  if value is None:continue
  try:i=int(row.get('i') if row.get('i') is not None else -1)
  except Exception:i=-1
  fid=str(row.get('id') or '');name=str(row.get('name') or '')
  loc=await reacquire_visible_field(form,name,fid,i)
  if loc is None:continue
  out['matched']+=1
  try:
   await sticky_fill(loc,value)
  except Exception:
   continue
  out['filled']+=1
  if fid:out['ids'].add(fid)
  if name:out['names'].add(name)
  if i>=0:out['indices'].add(i)
  if role=='email':out['email']=True
  if role=='message':out['message']=True
 return out

async def fill_form(page,form,message,email,market,proof_field_schema=None):
 company='Practical AI Lab'; name='Practical AI Lab 運営' if market=='JP-JA' else 'Practical AI Lab'; site='https://practical-ai-lab.pages.dev/' if market=='JP-JA' else 'https://practical-ai-lab.pages.dev/global/'
 fields=form.locator('input,textarea,select'); required_unknown=[]; sensitive=[]; filled={'email':False,'message':False};fill_deadline=time.monotonic()+45.0
 script_required=set()
 try:
  meta=await fields.evaluate_all("""els => els.slice(0,60).map((e,i)=>{
    const s=getComputedStyle(e),r=e.getBoundingClientRect();
    return {i,visible:s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0,
      enabled:!e.disabled,name:e.name||'',id:e.id||'',tag:e.tagName.toLowerCase(),typ:(e.getAttribute('type')||e.tagName).toLowerCase(),
      d:[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText,e.closest('td')?.previousElementSibling?.innerText,e.closest('dd')?.previousElementSibling?.innerText,e.closest('dl')?.querySelector('dt')?.innerText,e.closest('.contactConfirmWrap')?.innerText,(e.previousElementSibling&&e.previousElementSibling.tagName==='LABEL'?e.previousElementSibling.innerText:''),(e.parentElement&&e.parentElement.tagName!=='FORM'?e.parentElement.querySelector(':scope > label')?.innerText:''),e.closest('.form-group,.form-row,.field,.contact_area')?.querySelector('label')?.innerText,...[...(e.labels||[])].map(l=>l.innerText||''),e.closest('label')?.innerText||''].filter(Boolean).join(' '),
      cls:String(e.className||''),required:!!e.required||e.getAttribute('aria-required')==='true',
      options:e.tagName==='SELECT'?[...e.options].map(o=>({v:o.value||'',t:o.textContent||''})):[]};
  })""")
 except Exception:
  meta=[]
 mapped=await fill_proof_schema(form,proof_field_schema,message,email,market)
 filled['email']=bool(mapped.get('email'));filled['message']=bool(mapped.get('message'))
 if any(sensitive_kind(str(m.get('d') or '')) for m in meta):
  script_required=await same_origin_script_required_sensitive(page)
 for m in meta:
  req=False;d=''
  try:
   if not m.get('visible') or not m.get('enabled'):continue
   i=int(m.get('i') or 0);e=fields.nth(i);tag=str(m.get('tag') or '');typ=str(m.get('typ') or tag);d=' '.join(str(m.get('d') or '').split())[:500];cls=str(m.get('cls') or '')
   field_name=str(m.get('name') or '');field_id=str(m.get('id') or '')
   if ((field_id and field_id in mapped['ids']) or (field_name and field_name in mapped['names']) or i in mapped['indices']):
    continue
   kind=sensitive_kind(d)
   req=field_required_hint(bool(m.get('required')),cls,d) or bool(kind and kind in script_required)
   if time.monotonic()>fill_deadline:return {'ok':False,'filled':filled,'sensitive':sensitive[:8],'required_unknown':required_unknown[:8],'timed_out':True}
   core=bool(typ in {'email','url'} or EMAIL.search(d) or EMAIL_EXAMPLE.search(d) or tag=='textarea' or MESSAGE.search(d)
             or COMPANY.search(d) or FIRST_NAME.search(d) or LAST_NAME.search(d)
             or NAME.search(d) or KANA_FIELD.search(d) or SUBJECT.search(d) or URLRX.search(d))
   if typ in {'hidden','submit','button','image','reset','password','file'}:
    if req and typ=='file':required_unknown.append(d or 'file')
    continue
   if BOT_HINT.search(d):
    if req:required_unknown.append(('human_challenge:'+d)[:160])
    continue
   if typ=='checkbox':
    safe_check=bool((CONSENT_OK.search(d) and not CONSENT_BAD.search(d)) or SUBMIT_CONFIRM_CHECK.search(d))
    if safe_check:
     if await safe_checkbox_check(e,form,m):continue
     retry=await reacquire_visible_field(form,field_name,field_id,i)
     if retry is not None and await safe_checkbox_check(retry,form,m):continue
     if req:required_unknown.append(d[:160] or typ)
     continue
    if not req:continue
    required_unknown.append(d[:160] or typ);continue
   if typ=='radio':
    if not req:continue
    if SAFE_CHOICE.search(d) and not UNSAFE_CHOICE.search(d):await e.check(timeout=1500);continue
    required_unknown.append(d[:160] or typ);continue
   if not req and not core:continue
   if SENSITIVE.search(d) and not EMAIL.search(d) and not EMAIL_EXAMPLE.search(d):
    if req:sensitive.append(d[:160])
    continue
   if tag=='select':
    if not req:continue
    pick=safe_select_value(m.get('options') or [])
    if pick is None:required_unknown.append(d[:160] or 'select');continue
    await e.select_option(value=pick,timeout=2200);continue
   value=None;is_email_field=False;is_message_field=False
   if typ=='email' or EMAIL.search(d) or EMAIL_EXAMPLE.search(d):value=email;is_email_field=True
   elif tag=='textarea' or MESSAGE.search(d):value=message;is_message_field=True
   elif COMPANY.search(d):value=company
   elif re.search(r'(ふりがな|ひらがな)',d,re.I):value='ぷらくてぃかるえーあいらぼ'
   elif re.search(r'(フリガナ|カナ|kana|furigana)',d,re.I):value='プラクティカルエーアイラボ'
   elif FIRST_NAME.search(d):value='Practical AI'
   elif LAST_NAME.search(d):value='Lab'
   elif NAME.search(d):value=name
   elif re.search(r'(部署|部門|department|designation|job.?title|position|役職|職種)',d,re.I):value='Operations'
   elif typ=='url' or URLRX.search(d):value=site
   elif SUBJECT.search(d):value='AI workflow fit check' if market!='JP-JA' else 'AI業務改善のご相談'
   elif req and typ in {'text','search','input'}:value=company
   elif req:required_unknown.append(d[:160] or typ);continue
   if value is not None:
    target=e
    try:
     await sticky_fill(target,value)
    except Exception:
     # React/SPA forms can replace or duplicate inputs during hydration.
     # Reacquire the currently visible/enabled field, never a stale .first.
     target=await reacquire_visible_field(form,field_name,field_id,i)
     if target is None:raise
     await sticky_fill(target,value)
    if is_email_field:filled['email']=True
    if is_message_field:filled['message']=True
  except Exception as ex:
   if req:required_unknown.append((d or type(ex).__name__)[:160])
 return {'ok':filled['email'] and filled['message'] and not sensitive and not required_unknown,'filled':filled,'sensitive':sensitive[:8],'required_unknown':required_unknown[:8],'proof_schema_matched':int(mapped.get('matched') or 0),'proof_schema_filled':int(mapped.get('filled') or 0)}
def compact_control_text(value):
 return re.sub(r'\s+','',str(value or '')).casefold()

def control_is_confirm(label,desc_text=''):
 label=' '.join(str(label or '').split())[:300]
 d=' '.join(str(desc_text or '').split())[:500]
 probe=label or d;compact=compact_control_text(probe);label_compact=compact_control_text(label)
 if not (CONFIRM.search(probe) or CONFIRM.search(compact)):return False
 # Visible wording wins over internal names such as submitConfirm.
 # A genuinely final label such as 「確認して送信」 remains final.
 if FINAL.search(label) or FINAL.search(label_compact):return False
 return True

async def control(form,kind='final'):
 xs=form.locator('button,input[type=submit],input[type=button],input[type=image]');semantic=[];fallback=[]
 try:
  meta=await xs.evaluate_all("""els => els.slice(0,40).map((e,i)=>{
    const s=getComputedStyle(e),r=e.getBoundingClientRect();
    return {i,visible:s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0,
      enabled:!e.disabled,d:[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText].filter(Boolean).join(' '),
      label:[e.getAttribute('aria-label'),e.value,e.innerText,e.placeholder].filter(Boolean).join(' '),
      typ:(e.type||e.getAttribute('type')||'').toLowerCase()};
  })""")
 except Exception:return None
 for m in meta:
  if not m.get('visible') or not m.get('enabled'):continue
  i=int(m.get('i') or 0);d=' '.join(str(m.get('d') or '').split())[:500];label=' '.join(str(m.get('label') or '').split())[:300];typ=str(m.get('typ') or '');compact=re.sub(r'\s+','',d)
  if REJECT_CONTROL.search(d):continue
  is_confirm=control_is_confirm(label,d)
  if kind=='confirm':
   if is_confirm:semantic.append((i,xs.nth(i),d))
   continue
  explicit_final=bool(FINAL.search(d) or FINAL.search(compact) or re.fullmatch(r'送信',compact,re.I))
  if explicit_final and not is_confirm:semantic.append((i,xs.nth(i),d))
  elif typ=='submit' and not is_confirm:fallback.append((i,xs.nth(i),d))
 if len(semantic)==1:return semantic[0]
 if not semantic and len(fallback)==1:return fallback[0]
 return None
async def control_actionable(item):
 if item is None:return False
 try:
  loc=item[1] if isinstance(item,(tuple,list)) and len(item)>1 else item
  if not (await loc.is_visible() and await loc.is_enabled()):return False
  # Playwright trial mode runs the full actionability checks (including scroll,
  # stability and hit-target checks) without dispatching the click. This keeps
  # the durable click barrier unset until an actual click is likely to succeed.
  await loc.click(trial=True,timeout=2500)
  return True
 except Exception:return False

async def final_control_matching_text(form,expected_text=''):
 expected=' '.join(str(expected_text or '').split()).lower()
 if not expected:return await control(form,'final')
 xs=form.locator('button,input[type=submit],input[type=button],input[type=image]');hits=[]
 for i in range(min(await xs.count(),40)):
  e=xs.nth(i)
  try:
   if not await e.is_visible() or not await e.is_enabled():continue
   d=' '.join((await desc(e)).split());label=' '.join(str(await e.evaluate("e=>[e.getAttribute('aria-label'),e.value,e.innerText,e.placeholder].filter(Boolean).join(' ')") or '').split());low=d.lower();typ=str(await e.evaluate("e=>(e.type||e.getAttribute('type')||'').toLowerCase()") or '');compact=re.sub(r'\\s+','',d)
   if REJECT_CONTROL.search(d):continue
   is_confirm=control_is_confirm(label,d)
   is_final=bool(FINAL.search(d) or re.fullmatch(r'送信',compact,re.I) or typ=='submit') and not is_confirm
   if is_final and low and (expected==low or expected in low or low in expected):hits.append((i,e,d))
  except:continue
 return hits[0] if len(hits)==1 else None

async def form_contains_payload(form,email,message):
 try:
  found=await form.locator('input,textarea').evaluate_all("""(els,a)=>{
    const norm=(v)=>String(v||'').replace(/\r\n/g,'\n').replace(/\r/g,'\n').replace(/[ \t]+$/gm,'').trim();
    let email=false,message=false;
    const wantEmail=norm(a.email).toLowerCase(),wantMessage=norm(a.message);
    for(const e of els){
      const v=norm(e.value);
      if(v.toLowerCase()===wantEmail)email=true;
      if(v===wantMessage)message=true;
    }
    return {email,message};
  }""",{'email':email,'message':message})
  return bool(found.get('email') and found.get('message'))
 except Exception:return False

async def resolve_pre_submit_controls(form,proof_confirm_step=False,confirm_action=False,proof_submit_text=''):
 confirm=await control(form,'confirm');final=await control(form,'final')
 # Stage3 already proved the exact final control text on this same form.
 # Use that evidence only when generic heuristics found no actionable control,
 # and never to bypass a known confirmation step.
 if confirm is None and final is None and proof_submit_text and not proof_confirm_step and not confirm_action:
  final=await final_control_matching_text(form,proof_submit_text)
 if proof_confirm_step and confirm is None and final is not None:
  confirm=final;final=None
 elif confirm_action and confirm is None and final is not None:
  confirm=final;final=None
 elif confirm is not None:
  final=None
 return confirm,final

async def refresh_actionable_control(form,item,kind='final',expected_text=''):
 if await control_actionable(item):return item
 for delay in (0.2,0.5):
  try:await asyncio.sleep(delay)
  except Exception:pass
  try:
   candidate=(await final_control_matching_text(form,expected_text)) if (kind=='final' and expected_text) else (await control(form,kind))
  except Exception:candidate=None
  if candidate is not None and await control_actionable(candidate):return candidate
 return None

async def unique_final_on_page(page):
 hits=[]
 try:n=min(await page.locator('form').count(),20)
 except:return None
 for fi in range(n):
  try:
   f=page.locator('form').nth(fi)
   c=await control(f,'final')
   if c:hits.append((fi,c))
  except:continue
 return hits[0] if len(hits)==1 else None
async def settle_correlated_click_timeout(page,click_error,mutations):
 if not click_error or not any(bool(x.get('matches_form_payload')) for x in (mutations or [])):return False
 # A click timeout can occur after the POST has already left the page. Never
 # click again; only give that same in-flight submission a bounded settle time.
 try:await page.wait_for_timeout(2200)
 except:pass
 try:await page.wait_for_load_state('domcontentloaded',timeout=4000)
 except:pass
 try:await page.wait_for_timeout(600)
 except:pass
 return True

async def provider_confirmation_visible(page):
 for sel in ('[id^="gform_confirmation_message_"]','.gform_confirmation_message','.wpforms-confirmation-container-full','.mw_wp_form_complete','.form__holder.form-success.success','.form-success.success'):
  try:
   xs=page.locator(sel)
   for i in range(min(await xs.count(),4)):
    if await xs.nth(i).is_visible():return True
  except:pass
 return False

async def recover_correlated_request_responses(req_objs,responses,resp_objs):
 seen={(str(x.get('method') or ''),str(x.get('url') or ''),int(x.get('status') or 0)) for x in (responses or [])}
 added=0
 for req in list(req_objs or [])[:8]:
  try:
   # Some servers accept the POST but never finish a response. Do not let one
   # hung Request.response() consume the whole per-task wall clock after the
   # durable click barrier is already set.
   resp=await asyncio.wait_for(req.response(),timeout=1.5)
   if resp is None:continue
   method=str(req.method);url=str(req.url)[:500];status=int(resp.status);key=(method,url,status)
   if key in seen:continue
   hdrs=resp.headers or {}
   responses.append({'method':method,'url':url,'status':status,'location':str(hdrs.get('location') or '')[:500],'matches_form_payload':True})
   resp_objs.append(resp);seen.add(key);added+=1
  except Exception:pass
 return added

async def click_and_evidence(page,loc,message,email,before_text):
 before_url=str(page.url or '')
 mutations=[];responses=[];resp_objs=[];correlated_req_objs=[];captured_raw={};body_tasks=[];scheduled_resp_ids=set()
 async def capture_response_body(resp):
  try: captured_raw[id(resp)]=(await asyncio.wait_for(resp.text(),2.5))[:65536]
  except Exception: pass
 def on_req(req):
  try:
   if str(req.method).upper() not in {'GET','HEAD','OPTIONS'}:
    m=_payload_match(req.post_data or '',message,email);mutations.append({'method':req.method,'url':req.url[:500],'matches_form_payload':m})
    if m:correlated_req_objs.append(req)
  except:pass
 def on_resp(resp):
  try:
   req=resp.request
   if str(req.method).upper() not in {'GET','HEAD','OPTIONS'}:
    m=_payload_match(req.post_data or '',message,email);hdrs=resp.headers or {};responses.append({'method':req.method,'url':req.url[:500],'status':int(resp.status),'location':str(hdrs.get('location') or '')[:500],'matches_form_payload':m});
    if m:
     resp_objs.append(resp)
     if id(resp) not in scheduled_resp_ids and len(body_tasks)<8:
      scheduled_resp_ids.add(id(resp));body_tasks.append(asyncio.create_task(capture_response_body(resp)))
  except:pass
 page.on('request',on_req);page.on('response',on_resp);click_error=''
 try:
  # Trial click already verified actionability. Dispatch the real click without
  # coupling its success to Playwright's implicit navigation wait; post-click
  # navigation/network/DOM evidence is observed explicitly below.
  await loc.click(timeout=5000,no_wait_after=True)
  try:await page.wait_for_load_state('domcontentloaded',timeout=5000)
  except:pass
  await page.wait_for_timeout(1500)
 except Exception as e:
  click_error=type(e).__name__+':'+str(e)[:180]
  await settle_correlated_click_timeout(page,click_error,mutations)
 finally:
  # Some iframe/AJAX providers acknowledge the correlated POST after the
  # visible click returns. Keep listeners alive briefly, without re-clicking.
  if any(bool(x.get('matches_form_payload')) for x in mutations) and not any(bool(x.get('matches_form_payload')) for x in responses):
   for _ in range(5):
    try:await page.wait_for_timeout(500)
    except:break
    if any(bool(x.get('matches_form_payload')) for x in responses):break
    if await provider_confirmation_visible(page):break
  # The response event can be lost when a navigation destroys the old page
  # after the POST has already left. Ask the correlated Request objects for
  # their eventual Response before removing listeners; never re-submit.
  if correlated_req_objs:
   await recover_correlated_request_responses(correlated_req_objs,responses,resp_objs)
  for resp in resp_objs[:6]:
   if id(resp) not in scheduled_resp_ids and len(body_tasks)<8:
    scheduled_resp_ids.add(id(resp));body_tasks.append(asyncio.create_task(capture_response_body(resp)))
  if body_tasks:
   try:await asyncio.wait_for(asyncio.gather(*body_tasks,return_exceptions=True),3.5)
   except Exception:pass
  try:page.remove_listener('request',on_req);page.remove_listener('response',on_resp)
  except:pass
 provider_success=False;provider_fail=False;bodies=[]
 before_success=SUCCESS.search(before_text or ''); before_failure=FAIL.search(before_text or '')
 for resp in resp_objs[:6]:
  try:
   raw=captured_raw.get(id(resp))
   if raw is None:raw=(await asyncio.wait_for(resp.text(),1.5))[:65536]
   st='';body_success=False;body_fail=False
   try:
    o=json.loads(raw);st=provider_app_status(o)
   except Exception:
    clean=' '.join(re.sub(r'<[^>]+>',' ',raw).split())
    sm=SUCCESS.search(clean);fm=FAIL.search(clean)
    body_success=bool(sm and (not before_success or sm.group(0)!=before_success.group(0)))
    body_fail=bool(fm and (not before_failure or fm.group(0)!=before_failure.group(0)))
   provider_success|=st in {'mail_sent','sent','success','1'} or body_success
   provider_fail|=st in {'validation_failed','spam','mail_failed','aborted','acceptance_missing','failed','error'} or body_fail
   bodies.append({'status':int(resp.status),'app_status':st[:80],'body_success':body_success,'body_fail':body_fail})
  except:pass
 try:after=' '.join((await page.locator('body').inner_text(timeout=2500)).split())
 except:after=''
 correlated_mutation=any(bool(x.get('matches_form_payload')) for x in mutations)
 provider_confirmation_dom=bool(correlated_mutation and await provider_confirmation_visible(page))
 after_success=SUCCESS.search(after)
 before_success_text=SUCCESS.search(before_text or '')
 new_success=bool(after_success and (not before_success_text or after_success.group(0)!=before_success_text.group(0)))
 before_fail=FAIL.search(before_text or ''); after_fail=FAIL.search(after)
 new_validation_text=bool(after_fail and (not before_fail or after_fail.group(0)!=before_fail.group(0)))
 success_match=(after_success.group(0)[:240] if after_success else '')
 failure_match=(after_fail.group(0)[:240] if after_fail else '')
 final_text_excerpt=after[:1600]
 invalid_control_count=await submitted_form_invalid_count(loc)
 try:
  payload_values_remaining=await page.locator('input,textarea').evaluate_all("(els,a)=>els.filter(e=>{const v=String(e.value||'');return v===String(a.email||'')||v===String(a.message||'')}).length",{'email':email,'message':message})
 except: payload_values_remaining=-1
 payload_cleared=(payload_values_remaining==0)
 validation=post_submit_validation(new_validation_text,invalid_control_count,(provider_success or provider_confirmation_dom),new_success,payload_cleared)
 corr2xx=any(x['matches_form_payload'] and 200<=x['status']<300 for x in responses);corr4xx=any(x['matches_form_payload'] and x['status'] in {400,401,403,404,405,410,415,422} for x in responses)
 def pathmatch(rx,u):
  try:return bool(rx.search(urlsplit(str(u or '')).path or '/'))
  except:return False
 corr3xx=[x for x in responses if x['matches_form_payload'] and 300<=x['status']<400]
 corr204=any(x['matches_form_payload'] and x['status']==204 for x in responses)
 corr_created=any(x['matches_form_payload'] and strong_http_accept(x['status'],payload_cleared) for x in responses)
 redirect_completion=any(pathmatch(COMPLETION_PATH,x.get('location')) for x in corr3xx)
 redirect_success_query=any(bool(SUCCESS_QUERY.search(str(x.get('location') or ''))) for x in corr3xx)
 redirect_confirm=any(is_confirm_url(x.get('location')) for x in corr3xx)
 final_completion=pathmatch(COMPLETION_PATH,page.url)
 final_success_query=bool(SUCCESS_QUERY.search(str(page.url or '')))
 final_error_path=pathmatch(ERROR_PATH,page.url)
 redirect_error=any(pathmatch(ERROR_PATH,x.get('location')) for x in corr3xx)
 try:
  bu=urlsplit(before_url);au=urlsplit(str(page.url or ''));path_changed=(bu.netloc==au.netloc and (bu.path.rstrip('/') or '/')!=(au.path.rstrip('/') or '/'))
 except:path_changed=False
 correlated_2xx_navigation=bool(corr2xx and path_changed and not is_confirm_url(page.url) and not final_error_path)
 correlated_3xx_cleared=bool(corr3xx and payload_cleared and not redirect_confirm and not is_confirm_url(page.url) and not redirect_error and not final_error_path)
 has_success=bool(provider_success or provider_confirmation_dom or new_success)
 same_form_reject=same_form_redirect_failure(before_url,responses,payload_values_remaining,has_success)
 home_no_submit=home_navigation_without_submission(before_url,page.url,mutations,payload_values_remaining,has_success)
 ev={'clicked_once':True,'submit_request_observed':bool(mutations),'submit_request_correlated':correlated_mutation,'submit_request_2xx':corr2xx,'submit_request_204':corr204,'submit_request_created':corr_created,'submit_redirect_completion':redirect_completion,'submit_redirect_success_query':redirect_success_query,'submit_redirect_confirm':redirect_confirm,'final_completion_path':final_completion,'final_success_query':final_success_query,'final_error_path':final_error_path,'redirect_error':redirect_error,'post_submit_path_changed':path_changed,'payload_values_remaining':payload_values_remaining,'payload_cleared':payload_cleared,'correlated_2xx_navigation':correlated_2xx_navigation,'correlated_3xx_cleared':correlated_3xx_cleared,'same_form_redirect_failure':same_form_reject,'home_navigation_without_submission':home_no_submit,'server_success':provider_success,'provider_confirmation_dom':provider_confirmation_dom,'server_not_sent':provider_fail or corr4xx or final_error_path or redirect_error,'success_dom':new_success,'success_match':success_match,'failure_match':failure_match,'final_text_excerpt':final_text_excerpt,'validation_error':validation,'new_validation_text':new_validation_text,'invalid_control_count':invalid_control_count,'network_mutations':mutations[:8],'network_responses':responses[:8],'response_bodies':bodies,'final_url':page.url[:500],'click_error':click_error}
 if (provider_success or provider_confirmation_dom or new_success or corr204 or corr_created or redirect_completion or redirect_success_query or final_completion or final_success_query or correlated_2xx_navigation or correlated_3xx_cleared) and not ev['server_not_sent'] and not validation:return 'SENT_CONFIRMED',ev
 if ev['server_not_sent'] or validation or same_form_reject or home_no_submit:return 'CONFIRMED_NOT_SENT',ev
 return 'AMBIGUOUS_HOLD',ev
async def await_submit_barrier(task,timeout=65.0):
 if MODE!='PRODUCTION' or task.get('submit_started') is True:return task
 token=str(task.get('token_id') or '');deadline=time.monotonic()+max(1.0,float(timeout))
 while time.monotonic()<deadline:
  try:q=await asyncio.to_thread(_get_task,TASK_URL)
  except Exception:
   await asyncio.sleep(.5);continue
  for x in (q.get('tasks') or []):
   if isinstance(x,dict) and str(x.get('token_id') or '')==token and x.get('submit_started') is True:return x
  await asyncio.sleep(.5)
 return None

async def process_task(browser,t):
 out={'kind':'PAL_V9_SEND_RESULT_V1','token_id':str(t.get('token_id') or ''),'company_key':str(t.get('company_key') or ''),'route_id':int(t.get('route_id') or 0),'at_epoch':int(time.time())}
 if not out['token_id'] or not t.get('canonical_url') or not t.get('message_body'):return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'INVALID_TASK','evidence':{'pre_submit':True}}
 if MODE=='PRODUCTION' and t.get('click_started') is True:
  return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'CLICK_ALREADY_STARTED_FAIL_CLOSED','evidence':{'click_started':True,'resend_safe':False,'preexisting_marker':True}}
 if MODE=='PRODUCTION' and t.get('submit_started') is not True:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'SUBMIT_BARRIER_MISSING','evidence':{'pre_submit':True}}
 if MODE=='PRODUCTION' and not _proof_control_ok(t,60000):return {**out,'outcome':'TECH_RETRY','reason':'PROOF_EXPIRED_PRE_BROWSER','evidence':{'pre_submit':True,'proof_expires_at':t.get('proof_expires_at')}}
 if MODE=='PRODUCTION' and not await asyncio.to_thread(_production_control_ok):return {**out,'outcome':'TECH_RETRY','reason':'PRODUCTION_CONTROL_REVOKED_PRE_BROWSER','evidence':{'pre_submit':True,'control_recheck':True}}
 canonical_url=str(t['canonical_url']);domain=str(t.get('official_domain') or host(canonical_url));proof_url=str(t.get('proof_url') or '')
 fast_direct=(str(t.get('proof_lane') or '')=='DIRECT_LIVE_REVALIDATE')
 proof_confirm_step=bool(t.get('proof_confirm_step'))
 # A confirmation-page proof cannot be opened directly: it depends on state
 # created by filling the canonical form and taking the confirm transition.
 url=sender_start_url(t)
 initial_proof_submit_text='' if proof_confirm_step else t.get('proof_submit_text')
 proof_schema=[x for x in (t.get('proof_field_schema') or []) if isinstance(x,dict)][:32]
 ctx=None;click_barrier=False
 try:
  ctx=await browser.new_context(user_agent=UA,ignore_https_errors=False);page=await ctx.new_page();page.set_default_timeout(2200 if fast_direct else 3000)
  await page.route('**/*',lambda route: route.abort() if route.request.resource_type in {'image','media','font'} else route.continue_())
  nav_timeout=False;nav_alias_fallback=False;nav_http_status=None
  try:
   nav_resp=await page.goto(url,wait_until='domcontentloaded',timeout=(8000 if fast_direct else 14000))
   nav_http_status=(int(nav_resp.status) if nav_resp is not None else None)
  except PlaywrightTimeoutError:
   nav_timeout=True
  except Exception as nav_exc:
   msg=str(nav_exc);u=urlsplit(url);fallback=''
   if (u.scheme.lower()=='https' and u.hostname and not u.hostname.lower().startswith('www.')
       and re.search(r'net::ERR_(?:CERT_AUTHORITY_INVALID|CERT_COMMON_NAME_INVALID|NAME_NOT_RESOLVED)',msg,re.I)):
    fallback=u._replace(netloc='www.'+str(u.netloc)).geturl()
   if fallback and host(fallback)==domain:
    nav_alias_fallback=True;url=fallback
    try:
     nav_resp=await page.goto(fallback,wait_until='domcontentloaded',timeout=(8000 if fast_direct else 14000))
     nav_http_status=(int(nav_resp.status) if nav_resp is not None else None)
    except PlaywrightTimeoutError:nav_timeout=True
   else:
    raise
  await page.wait_for_timeout(400 if fast_direct else (600 if nav_timeout else (800 if str(t.get('proof_lane') or '')=='FAST_DOM' else 1600)))
  if host(page.url)!=domain:return {**out,'outcome':'SAFETY_BLOCKED','reason':'DOMAIN_CHANGED','evidence':{'final_url':page.url[:500]}}
  http_verdict=pre_submit_http_verdict(nav_http_status)
  if http_verdict:
   outcome,reason=http_verdict
   return {**out,'outcome':outcome,'reason':reason,'evidence':{'pre_submit':True,'http_status':nav_http_status,'final_url':page.url[:500],'navigation_timeout':nav_timeout}}
  txt=await body_text(page,2000 if fast_direct else 3500)
  if txt is None:return {**out,'outcome':'TECH_RETRY','reason':'BODY_UNREADABLE_PRE_SUBMIT','evidence':{'pre_submit':True,'navigation_timeout':nav_timeout,'final_url':page.url[:500]}}
  if nav_timeout:
   has_form=await has_any_form(page)
   if not has_form:
    # A navigation timeout can still leave a usable page that finishes
    # hydrating the contact form a moment later. Re-check the live DOM/frames
    # before declaring a technical retry; never click or submit in this wait.
    for delay_ms in ((400,700) if fast_direct else (1200,1800)):
     await page.wait_for_timeout(delay_ms)
     if await has_any_form(page):
      has_form=True;break
   if not has_form:return {**out,'outcome':'TECH_RETRY','reason':'NAVIGATION_TIMEOUT_NO_FORM','evidence':{'pre_submit':True,'final_url':page.url[:500],'late_form_wait_ms':3000}}
  if PROHIBIT.search(txt):return {**out,'outcome':'SAFETY_BLOCKED','reason':'SALES_PROHIBITED','evidence':{'pre_submit':True}}
  if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA','evidence':{'pre_submit':True}}
  chosen=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),initial_proof_submit_text,proof_schema)
  if not chosen:
   await reveal_candidate_forms(page,t.get('proof_frame_index'),t.get('proof_form_index'))
   if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA','evidence':{'pre_submit':True,'late_render':True}}
   chosen=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),initial_proof_submit_text,proof_schema)
  if not chosen:
   multistep_steps=await advance_safe_multistep(page,t.get('proof_frame_index'),t.get('proof_form_index'))
   if multistep_steps:
    chosen=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),initial_proof_submit_text,proof_schema)
  else:
   multistep_steps=0
  if not chosen:
   await page.wait_for_timeout(300 if fast_direct else 900)
   chosen=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),initial_proof_submit_text,proof_schema)
  if not chosen:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'BUSINESS_CONTACT_FORM_NOT_FOUND','evidence':{'pre_submit':True,'late_retry':True,'multistep_steps':multistep_steps}}
  _,frame_i,fi,form=chosen;fill=await fill_form(page,form,str(t['message_body']),str(t.get('reply_address') or ''),str(t.get('market') or ''),proof_schema)
  if fill.get('timed_out'):return {**out,'outcome':'TECH_RETRY','reason':'FILL_TIMEOUT_PRE_SUBMIT','evidence':{**fill,'pre_submit':True}}
  if fill['sensitive']:return {**out,'outcome':'SAFETY_BLOCKED','reason':'REQUIRED_SENSITIVE','evidence':fill}
  if not fill['ok']:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'REQUIRED_UNFILLABLE','evidence':{**fill,'pre_submit':True}}
  await page.wait_for_timeout(250 if fast_direct else 500)
  # Frameworks such as Contact Form 7 can reorder forms after field updates.
  # A positional nth() locator can then silently point at an unrelated search
  # form. Re-resolve the contact form and require the exact filled payload to
  # still be present before any submit control is considered.
  refreshed=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),initial_proof_submit_text,proof_schema)
  if not refreshed:return {**out,'outcome':'TECH_RETRY','reason':'FORM_IDENTITY_LOST_AFTER_FILL','evidence':{'pre_submit':True,'resend_safe':True}}
  _,frame_i,fi,form=refreshed
  if not await form_contains_payload(form,str(t.get('reply_address') or ''),str(t['message_body'])):
   return {**out,'outcome':'TECH_RETRY','reason':'FORM_PAYLOAD_LOST_AFTER_FILL','evidence':{'pre_submit':True,'resend_safe':True,'frame_index':frame_i,'form_index':fi}}
  if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA_AFTER_FILL','evidence':{'pre_submit':True}}
  try:form_action=str(await form.get_attribute('action') or '')
  except:form_action=''
  confirm_action=bool(re.search(r'(confirm|review|check|kakunin|確認)',unquote_plus(form_action),re.I))
  confirm,final=await resolve_pre_submit_controls(
   form,proof_confirm_step,confirm_action,initial_proof_submit_text)
  if final is None and confirm is None:
   # Hydrating forms can recreate the submit controls after the filled payload
   # is already stable. Rebind the same proven form twice before failing closed.
   for settle_ms in (400,700):
    await page.wait_for_timeout(settle_ms)
    refreshed=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),initial_proof_submit_text,proof_schema)
    if not refreshed:continue
    _,frame_i,fi,form=refreshed
    if not await form_contains_payload(form,str(t.get('reply_address') or ''),str(t['message_body'])):continue
    try:form_action=str(await form.get_attribute('action') or '')
    except:form_action=''
    confirm_action=bool(re.search(r'(confirm|review|check|kakunin|確認)',unquote_plus(form_action),re.I))
    confirm,final=await resolve_pre_submit_controls(
     form,proof_confirm_step,confirm_action,initial_proof_submit_text)
    if final is not None or confirm is not None:break
  if final is None and confirm is None:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'SUBMIT_CONTROL_NOT_FOUND','evidence':{'pre_submit':True,'form_action':form_action[:500]}}
  if MODE!='PRODUCTION':return {**out,'outcome':'SHADOW_PREPARED','reason':'PRE_SUBMIT_ONLY','evidence':{'frame_index':frame_i,'form_index':fi,'form_action':form_action[:500],'final_control':bool(final),'confirm_control':bool(confirm)}}
  before=txt
  if MODE=='PRODUCTION' and not _proof_control_ok(t,30000):return {**out,'outcome':'TECH_RETRY','reason':'PROOF_EXPIRED_PRE_CLICK','evidence':{'pre_submit':True,'proof_expires_at':t.get('proof_expires_at')}}
  if MODE=='PRODUCTION' and not await asyncio.to_thread(_production_control_ok):return {**out,'outcome':'TECH_RETRY','reason':'PRODUCTION_CONTROL_REVOKED_PRE_CLICK','evidence':{'pre_submit':True,'control_recheck':True}}
  if confirm is not None:
   if MODE=='PRODUCTION':
    confirm=await refresh_actionable_control(form,confirm,'confirm')
    if confirm is None:return {**out,'outcome':'TECH_RETRY','reason':'CONFIRM_CONTROL_STALE_PRE_CLICK','evidence':{'pre_submit':True,'resend_safe':True}}
   if MODE=='PRODUCTION' and not await asyncio.to_thread(_mark_click_started,t):return {**out,'outcome':'TECH_RETRY','reason':'CLICK_BARRIER_WRITE_FAILED','evidence':{'pre_submit':True}}
   click_barrier=True
   outcome,cev=await click_and_evidence(page,confirm[1],str(t['message_body']),str(t.get('reply_address') or ''),before)
   if outcome=='SENT_CONFIRMED':return {**out,'outcome':outcome,'reason':'CONFIRM_CLICK_SENT','evidence':cev}
   if outcome=='CONFIRMED_NOT_SENT':return {**out,'outcome':outcome,'reason':'CONFIRM_REJECTED','evidence':cev}
   corr_redirect=any(x.get('matches_form_payload') and 300<=int(x.get('status') or 0)<400 for x in (cev.get('network_responses') or []))
   try:confirm_landed=bool(CONFIRM_PATH.search(urlsplit(str(cev.get('final_url') or '')).path or '/'))
   except Exception:confirm_landed=False
   confirm_text=bool(CONFIRM_PAGE_TEXT.search(str(cev.get('final_text_excerpt') or '')))
   confirm_transition=bool(cev.get('submit_redirect_confirm') or confirm_landed or corr_redirect or confirm_text)
   if not (confirm_transition and not cev.get('validation_error') and not cev.get('server_not_sent')):
    return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'CONFIRM_AMBIGUOUS','evidence':{**cev,'confirm_action':confirm_action,'confirm_transition':confirm_transition}}
   await page.wait_for_timeout(500)
   final_forms=[];roots=ordered_form_frames(page,domain)
   try:pfr=int(t.get('proof_frame_index')) if t.get('proof_frame_index') is not None else -1
   except Exception:pfr=-1
   try:pfi=int(t.get('proof_form_index')) if t.get('proof_form_index') is not None else -1
   except Exception:pfi=-1
   # Prefer the exact confirmation-page form/control Stage3 proved.
   if proof_confirm_step and 0<=pfr<len(roots):
    try:
     forms=roots[pfr].locator('form')
     if 0<=pfi<await forms.count():
      f2=forms.nth(pfi)
      c2=await final_control_matching_text(f2,t.get('proof_submit_text'))
      if c2 is not None:final_forms.append((pfr,pfi,f2,c2))
    except Exception:pass
   if not final_forms:
    for fri,root in enumerate(roots):
     try:n=min(await root.locator('form').count(),12)
     except Exception:continue
     for j in range(n):
      f2=root.locator('form').nth(j)
      try:
       c2=await final_control_matching_text(f2,t.get('proof_submit_text')) if proof_confirm_step else await control(f2,'final')
       if c2 is not None:final_forms.append((fri,j,f2,c2))
      except:continue
   if len(final_forms)!=1:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'CONFIRM_NO_UNIQUE_FINAL_CONTROL','evidence':{**cev,'confirm_navigation':True,'final_candidates':len(final_forms),'proof_frame_index':pfr,'proof_form_index':pfi}}
   final_frame_i,final_form_i,form,final=final_forms[0]
   before=await body_text(page,3500) or ''
   if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA_ON_CONFIRM_PAGE','evidence':{**cev,'confirm_navigation':True,'frame_index':final_frame_i,'form_index':final_form_i}}
   if MODE=='PRODUCTION' and not _proof_control_ok(t,30000):return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'PROOF_EXPIRED_BEFORE_FINAL','evidence':{**cev,'proof_expires_at':t.get('proof_expires_at')}}
   if MODE=='PRODUCTION' and not await asyncio.to_thread(_production_control_ok):return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'PRODUCTION_CONTROL_REVOKED_BEFORE_FINAL','evidence':{**cev,'control_recheck':True}}
  if MODE=='PRODUCTION' and not click_barrier:
   final=await refresh_actionable_control(form,final,'final',t.get('proof_submit_text') or '')
   if final is None:return {**out,'outcome':'TECH_RETRY','reason':'SUBMIT_CONTROL_STALE_PRE_CLICK','evidence':{'pre_submit':True,'resend_safe':True}}
   if not await asyncio.to_thread(_mark_click_started,t):return {**out,'outcome':'TECH_RETRY','reason':'CLICK_BARRIER_WRITE_FAILED','evidence':{'pre_submit':True}}
   click_barrier=True
  outcome,ev=await click_and_evidence(page,final[1],str(t['message_body']),str(t.get('reply_address') or ''),before)
  return {**out,'outcome':outcome,'reason':'FINAL_CLICK_'+outcome,'evidence':ev}
 except Exception as e:
  detail=str(e)[:240]
  if MODE=='PRODUCTION' and not click_barrier and re.search(r'ERR_CERT_(?:AUTHORITY_INVALID|COMMON_NAME_INVALID|DATE_INVALID|INVALID)',detail,re.I):
   return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'TLS_INVALID_PRE_SUBMIT','evidence':{'pre_submit':True,'detail':detail}}
  if MODE=='PRODUCTION' and not click_barrier:return {**out,'outcome':'TECH_RETRY','reason':'WORKER_EXCEPTION_PRE_CLICK_'+type(e).__name__.upper(),'evidence':{'pre_submit':True,'detail':detail}}
  return {**out,'outcome':('AMBIGUOUS_HOLD' if MODE=='PRODUCTION' else 'SHADOW_PREPARED'),'reason':'WORKER_EXCEPTION_'+type(e).__name__.upper(),'evidence':{'detail':str(e)[:240],'click_started':bool(click_barrier)}}
 finally:
  if ctx:
   try:await asyncio.wait_for(ctx.close(),timeout=4.0)
   except:pass
def pre_browser_failure_result(t,reason='BROWSER_LAUNCH_TIMEOUT'):
 clicked=t.get('click_started') is True
 return {'kind':'PAL_V9_SEND_RESULT_V1','token_id':str(t.get('token_id') or ''),'company_key':str(t.get('company_key') or ''),'route_id':int(t.get('route_id') or 0),'at_epoch':int(time.time()),'outcome':('AMBIGUOUS_HOLD' if clicked else 'TECH_RETRY'),'reason':(reason+'_HOLD' if clicked else reason+'_PRE_CLICK'),'evidence':({'resend_safe':False,'click_started':True} if clicked else {'pre_submit':True,'click_started':False})}

RESULT_WRITE_LOCK=threading.Lock()
def _publish_result_batch_unlocked(results):
 r=_get_result(RESULT_URL);prior=[x for x in (r.get('messages') or []) if isinstance(x,dict)]
 keys={str(x.get('token_id') or '') for x in results}
 prior=[x for x in prior if str(x.get('token_id') or '') not in keys]
 _put_result(RESULT_URL,{'schema':'PAL_V9_SEND_RESULT_QUEUE_V1','updated_at_epoch':int(time.time()),'messages':(prior+results)[-256:]})

def publish_result_batch_sync(results):
 with RESULT_WRITE_LOCK:_publish_result_batch_unlocked(results)

def publish_one_result_sync(res,published_tokens=None):
 with RESULT_WRITE_LOCK:
  _publish_result_batch_unlocked([res])
  tok=str(res.get('token_id') or '')
  if tok and published_tokens is not None:published_tokens.add(tok)

def hard_timeout_result(t,remote_t=None,seconds=0,marker_read_ok=True):
 src=remote_t if isinstance(remote_t,dict) else t
 clicked=src.get('click_started') is True
 unknown=not marker_read_ok
 if unknown or clicked:
  return {'kind':'PAL_V9_SEND_RESULT_V1','token_id':str(t.get('token_id') or ''),'company_key':str(t.get('company_key') or ''),'route_id':int(t.get('route_id') or 0),'at_epoch':int(time.time()),'outcome':'AMBIGUOUS_HOLD','reason':('WORKER_HARD_TIMEOUT_MARKER_UNKNOWN' if unknown else 'WORKER_HARD_TIMEOUT_AFTER_CLICK'),'evidence':{'hard_timeout_seconds':float(seconds),'resend_safe':False,'click_started':(True if clicked else None),'marker_read_ok':bool(marker_read_ok)}}
 return {'kind':'PAL_V9_SEND_RESULT_V1','token_id':str(t.get('token_id') or ''),'company_key':str(t.get('company_key') or ''),'route_id':int(t.get('route_id') or 0),'at_epoch':int(time.time()),'outcome':'TECH_RETRY','reason':'WORKER_HARD_TIMEOUT_PRE_CLICK','evidence':{'hard_timeout_seconds':float(seconds),'pre_submit':True,'click_started':False,'resend_safe':True,'marker_read_ok':True}}

def start_hard_watchdog(tasks,seconds,stop_event,published_tokens):
 def watch():
  if stop_event.wait(float(seconds)):return
  marker_read_ok=True;remote_by_token={}
  try:
   q=_get_task(TASK_URL)
   remote_by_token={str(x.get('token_id') or ''):x for x in (q.get('tasks') or []) if isinstance(x,dict)}
  except Exception:
   marker_read_ok=False
  results=[]
  try:
   with RESULT_WRITE_LOCK:
    pending=[t for t in tasks if str(t.get('token_id') or '') not in published_tokens]
    results=[hard_timeout_result(t,remote_by_token.get(str(t.get('token_id') or '')),seconds,marker_read_ok) for t in pending]
    if results:_publish_result_batch_unlocked(results)
  except Exception:pass
  summary={'status':'PASS','mode':MODE,'sender_shard':SENDER_SHARD,'tasks':len(tasks),'hard_watchdog':True,'hard_timeout_seconds':float(seconds),'results':[{k:x.get(k) for k in ('token_id','outcome','reason')} for x in results]}
  try:os.write(1,(json.dumps(summary,ensure_ascii=False)+'\n').encode())
  except Exception:pass
  os._exit(0)
 th=threading.Thread(target=watch,name='v9-send-hard-watchdog',daemon=True);th.start();return th

async def main():
 q=_get(TASK_URL);tasks=[x for x in (q.get('tasks') or []) if isinstance(x,dict) and x.get('kind')=='PAL_V9_SEND_TASK_V1' and (0 if str(x.get('sender_shard',1)).strip()=='0' else 1)==SENDER_SHARD][:MAX_TASKS_PER_TURN];results=[]
 if not tasks:
  print(json.dumps({'status':'PASS','mode':MODE,'sender_shard':SENDER_SHARD,'tasks':0,'results':[]},ensure_ascii=False));return
 async with async_playwright() as p:
  chromium_path=(os.environ.get('PAL_CHROMIUM_PATH','').strip() or ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' if Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists() else '')))
  launch_kw={'headless':True,'args':['--disable-dev-shm-usage','--no-sandbox']}
  if chromium_path: launch_kw['executable_path']=chromium_path
  try:
   browser=await asyncio.wait_for(p.chromium.launch(**launch_kw),timeout=25.0)
  except asyncio.TimeoutError:
   results=[pre_browser_failure_result(t) for t in tasks]
   try:await asyncio.to_thread(publish_result_batch_sync,results)
   except Exception:pass
   print(json.dumps({'status':'PASS','mode':MODE,'sender_shard':SENDER_SHARD,'tasks':len(tasks),'browser_launch_timeout':True,'results':[{k:x.get(k) for k in ('token_id','outcome','reason')} for x in results]},ensure_ascii=False));return
  except Exception as e:
   reason='BROWSER_LAUNCH_'+type(e).__name__.upper()
   results=[pre_browser_failure_result(t,reason) for t in tasks]
   try:await asyncio.to_thread(publish_result_batch_sync,results)
   except Exception:pass
   print(json.dumps({'status':'PASS','mode':MODE,'sender_shard':SENDER_SHARD,'tasks':len(tasks),'browser_launch_error':type(e).__name__,'results':[{k:x.get(k) for k in ('token_id','outcome','reason')} for x in results]},ensure_ascii=False));return
  deferred=0;published_tokens=set();hard_stop=None
  try:
   armed_all=await asyncio.gather(*(await_submit_barrier(t,20.0) for t in tasks))
   ready=[x for x in armed_all if x is not None]
   deferred=len(tasks)-len(ready)
   if ready:
    waves=(len(ready)+SEND_CONCURRENCY-1)//SEND_CONCURRENCY
    hard_seconds=max(30.0,float(waves)*TASK_WALL_TIMEOUT+20.0)
    hard_stop=threading.Event();start_hard_watchdog(ready,hard_seconds,hard_stop,published_tokens)
   sem=asyncio.Semaphore(SEND_CONCURRENCY)
   result_lock=asyncio.Lock()
   async def publish_one(res):
    async with result_lock:
     for attempt in range(2):
      try:
       await asyncio.to_thread(publish_one_result_sync,res,published_tokens)
       return True
      except Exception:
       if attempt<1:await asyncio.sleep(0.5)
     return False
   async def run_one(t):
    async with sem:
     try:
      res=await asyncio.wait_for(process_task(browser,t),timeout=TASK_WALL_TIMEOUT)
     except asyncio.TimeoutError:
      clicked=t.get('click_started') is True
      res={'kind':'PAL_V9_SEND_RESULT_V1','token_id':str(t.get('token_id') or ''),'company_key':str(t.get('company_key') or ''),'route_id':int(t.get('route_id') or 0),'at_epoch':int(time.time()),'outcome':('AMBIGUOUS_HOLD' if clicked else 'TECH_RETRY'),'reason':('TASK_WALL_TIMEOUT_HOLD' if clicked else 'TASK_WALL_TIMEOUT_PRE_CLICK'),'evidence':({'wall_timeout_seconds':TASK_WALL_TIMEOUT,'resend_safe':False,'click_started':True} if clicked else {'wall_timeout_seconds':TASK_WALL_TIMEOUT,'pre_submit':True,'click_started':False})}
     await publish_one(res)
     return res
   if ready:
    results.extend(await asyncio.gather(*(run_one(t) for t in ready)))
  finally:
   if hard_stop is not None:hard_stop.set()
   try:await asyncio.wait_for(browser.close(),timeout=5.0)
   except:pass
 unpublished=[x for x in results if str(x.get('token_id') or '') not in published_tokens]
 if unpublished:
  try:await asyncio.to_thread(publish_result_batch_sync,unpublished)
  except Exception:pass
 print(json.dumps({'status':'PASS','mode':MODE,'sender_shard':SENDER_SHARD,'tasks':len(tasks),'max_tasks':MAX_TASKS_PER_TURN,'concurrency':SEND_CONCURRENCY,'deferred_unarmed':deferred,'results':[{k:x.get(k) for k in ('token_id','outcome','reason')} for x in results]},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
