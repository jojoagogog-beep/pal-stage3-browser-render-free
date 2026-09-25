from __future__ import annotations
import asyncio,json,os,re,time,hashlib,hmac,threading
from urllib.parse import urlsplit,unquote_plus
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
SENDER_SHARD=0 if str(os.environ.get('PAL_V9_SENDER_SHARD','1')).strip()=='0' else 1
PROHIBIT=re.compile(r'(営業(?:目的|メール|連絡|勧誘).{0,24}(?:お断り|禁止|不可)|セールス.{0,24}(?:お断り|禁止)|勧誘.{0,24}(?:お断り|禁止)|no\s+(?:sales|solicitation|marketing)\s+(?:messages?|inquiries|contacts?))',re.I)
SENSITIVE=re.compile(r'(\bphone\b|\btel(?:ephone)?\b|\bmobile\b|携帯|電話|\baddress\b|\bpostal\b|\bzip\b|住所|都道府県|市区町村|番地|date of birth|生年月日|\bage\b|年齢)',re.I)
EMAIL=re.compile(r'(e-?mail|(?:^|[_\-\s])mail(?:$|[_\-\s])|メール)',re.I)
MESSAGE=re.compile(r'(message|inquir|enquir|comment|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)',re.I)
COMPANY=re.compile(r'(company|organization|organisation|会社|法人|企業)',re.I)
FIRST_NAME=re.compile(r'(first.?name|given.?name|名(?:前)?$)',re.I)
LAST_NAME=re.compile(r'(last.?name|family.?name|sur.?name|姓$)',re.I)
NAME=re.compile(r'(full.?name|your.?name|contact.?name|お名前|氏名|\bname\b)',re.I)
SUBJECT=re.compile(r'(subject|件名|title)',re.I)
URLRX=re.compile(r'(website|web.?site|url|サイト)',re.I)
CAPTCHA_SEL='.g-recaptcha,.h-captcha,.cf-turnstile,[data-sitekey],iframe[src*="recaptcha"],iframe[src*="hcaptcha"]'
BOT_HINT=re.compile(r'(?:captcha|recaptcha|hcaptcha|turnstile|not[-_ ]?a?[-_ ]?robot|not[-_ ]?robot|chk[-_ ]?not[-_ ]?robot|human[-_ ]?(?:check|verification)|help\s+us\s+prevent\s+spam|anti[- ]?spam|spam\s+(?:check|question|protection)|security\s+(?:question|check)|which\s+is\s+(?:bigger|larger|smaller)|what\s+is\s+\d+\s*[+\-x×*]\s*\d+|\bquiz\b)',re.I)
SUCCESS=re.compile(r'(送信が完了|送信完了|お問い合わせ.{0,30}(?:ありがとう|受け付け|受付)|thank\s+you.{0,80}(?:message|inquir|contact)|(?:message|inquir(?:y|ies)|request).{0,80}(?:sent|received|submitted)|successfully\s+(?:sent|submitted))',re.I)
FAIL=re.compile(r'(入力してください|未入力|入力.{0,20}エラー|エラーがあります|必須(?:項目)?です|必須項目|正しく入力|入力内容.{0,20}(?:誤|エラー)|ご確認の上.{0,40}(?:修正|戻る)|required field|please.{0,30}(?:fill|enter|select|choose)|failed\s+to\s+send|unable\s+to\s+send|could\s+not\s+send|there\s+was\s+an\s+error.{0,60}send|validation error|invalid)',re.I)
FINAL=re.compile(r'(この内容で送信|内容を送信|確認して送信|送信する|^送信$|send\s*(?:message|inquiry|enquiry)?$|submit\s*(?:message|inquiry|enquiry|form)?$)',re.I)
CONFIRM=re.compile(r'(確認画面へ|入力内容を確認|内容を確認|確認する|confirm|review|next|次へ)',re.I)
REJECT_CONTROL=re.compile(r'(戻る|back|cancel|修正|reset|clear|クリア)',re.I)
SAFE_CHOICE=re.compile(r'(general|other|business|partnership|collaboration|inquiry|enquiry|contact|その他|一般|法人|協業|提携|ご相談)',re.I)
UNSAFE_CHOICE=re.compile(r'(job|career|employment|採用|求人|support|customer service|technical support|newsletter|marketing|subscribe|個人|患者|student)',re.I)
CONSENT_OK=re.compile(r'(privacy|terms|policy|consent|agree(?:ment)?|個人情報|プライバシー|規約|同意)',re.I)
CONSENT_BAD=re.compile(r'(newsletter|marketing|promotional|メルマガ|広告|案内を受け取|subscribe)',re.I)
COMPLETION_PATH=re.compile(r'/(?:thanks?|thank[-_]?you|complete(?:d)?|completion|success|sent)(?:/|$)',re.I)
CONFIRM_PATH=re.compile(r'/(?:confirm|confirmation|review|check)(?:/|$)',re.I)
SUCCESS_QUERY=re.compile(r'(?:[?&](?:contact-form-sent|form[-_]?sent|submitted|submission[-_]?success|success)=)(?:1|true|yes|sent|success|\d+)(?:&|$)',re.I)

def host(u):return (urlsplit(str(u or '')).hostname or '').lower().removeprefix('www.')
def _get(u):
 r=requests.get(u,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},params={'ts':int(time.time())},timeout=20);r.raise_for_status();return r.json()
def _put(u,o):
 r=requests.put(u,json=o,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},timeout=20);r.raise_for_status()
TASK_WRITE_LOCK=threading.Lock()
def _mark_click_started(task):
 token=str(task.get('token_id') or '')
 if not token:return False
 with TASK_WRITE_LOCK:
  for attempt in range(4):
   try:q=_get(TASK_URL)
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
   try:_put(TASK_URL,q)
   except Exception:
    time.sleep(.35*(attempt+1));continue
   # Verify the durable marker after the write. A controller/task-queue
   # read-modify-write racing this worker may otherwise erase the marker.
   try:
    v=_get(TASK_URL)
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
    const email=/(e-?mail|メール)/i,msg=/(message|inquir|enquir|comment|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)/i;
    const contact=/(contact|inquiry|enquiry|お問い合わせ|お問合せ|ご相談)/i;
    return [...document.querySelectorAll('form')].slice(0,20).map((f,fi)=>{
      if(!vis(f)) return null;
      let hasE=false,hasM=false;
      for(const e of [...f.querySelectorAll('input,textarea,select')].slice(0,80)){
        if(!vis(e)) continue;
        const d=[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText].filter(Boolean).join(' ');
        const typ=(e.getAttribute('type')||'').toLowerCase();
        hasE=hasE||typ==='email'||email.test(d);hasM=hasM||e.tagName==='TEXTAREA'||msg.test(d);
      }
      const txt=(f.innerText||'').slice(0,5000);
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
async def proof_form_shape_ok(form,proof_submit_text=''):
 try:
  ok=bool(await form.evaluate("""f=>{const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0&&!e.disabled};const email=/(e-?mail|メール)/i,msg=/(message|inquir|enquir|comment|お問い合わせ内容|問い合わせ内容|ご用件|内容|詳細)/i;let E=false,M=false;for(const e of [...f.querySelectorAll('input,textarea,select')].slice(0,80)){if(!vis(e))continue;const d=[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText].filter(Boolean).join(' ');const t=(e.getAttribute('type')||'').toLowerCase();E=E||t==='email'||email.test(d);M=M||e.tagName==='TEXTAREA'||msg.test(d)}return E&&M}"""))
  if not ok:return False
  expected=' '.join(str(proof_submit_text or '').split()).lower()
  if not expected:return True
  xs=form.locator('button,input[type=submit],input[type=button],input[type=image]')
  for i in range(min(await xs.count(),40)):
   d=' '.join((await desc(xs.nth(i))).split()).lower()
   if d and (expected==d or expected in d or d in expected):return True
  return False
 except:return False
async def choose_form_any_frame(page,proof_frame_index=None,proof_form_index=None,proof_submit_text=''):
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
    if await pf.is_visible() and await proof_form_shape_ok(pf,proof_submit_text):return (1000,pfr,pfi,pf)
  except Exception:pass
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

async def fill_form(page,form,message,email,market):
 company='Practical AI Lab'; name='Practical AI Lab 運営' if market=='JP-JA' else 'Practical AI Lab'; site='https://practical-ai-lab.pages.dev/' if market=='JP-JA' else 'https://practical-ai-lab.pages.dev/global/'
 fields=form.locator('input,textarea,select'); required_unknown=[]; sensitive=[]; filled={'email':False,'message':False};fill_deadline=time.monotonic()+25.0
 try:
  meta=await fields.evaluate_all("""els => els.slice(0,60).map((e,i)=>{
    const s=getComputedStyle(e),r=e.getBoundingClientRect();
    return {i,visible:s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0,
      enabled:!e.disabled,name:e.name||'',id:e.id||'',tag:e.tagName.toLowerCase(),typ:(e.getAttribute('type')||e.tagName).toLowerCase(),
      d:[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText,...[...(e.labels||[])].map(l=>l.innerText||''),e.closest('label')?.innerText||''].filter(Boolean).join(' '),
      cls:String(e.className||''),required:!!e.required||e.getAttribute('aria-required')==='true',
      options:e.tagName==='SELECT'?[...e.options].map(o=>o.textContent||''):[]};
  })""")
 except Exception:
  meta=[]
 for m in meta:
  req=False;d=''
  try:
   if not m.get('visible') or not m.get('enabled'):continue
   i=int(m.get('i') or 0);e=fields.nth(i);tag=str(m.get('tag') or '');typ=str(m.get('typ') or tag);d=' '.join(str(m.get('d') or '').split())[:500];cls=str(m.get('cls') or '')
   class_required=any(re.fullmatch(r'(?:required|mandatory|hissu(?:val)?|req(?:uired)?(?:field)?)',tok,re.I) for tok in cls.split())
   req=bool(m.get('required') or class_required or (re.search(r'(必須|required|mandatory)',d,re.I) and not re.search(r'(任意|optional)',d,re.I)))
   if time.monotonic()>fill_deadline:return {'ok':False,'filled':filled,'sensitive':sensitive[:8],'required_unknown':required_unknown[:8],'timed_out':True}
   core=bool(typ in {'email','url'} or EMAIL.search(d) or tag=='textarea' or MESSAGE.search(d)
             or COMPANY.search(d) or FIRST_NAME.search(d) or LAST_NAME.search(d)
             or NAME.search(d) or SUBJECT.search(d) or URLRX.search(d))
   if typ in {'hidden','submit','button','image','reset','password','file'}:
    if req and typ=='file':required_unknown.append(d or 'file')
    continue
   if not req and not core:continue
   if BOT_HINT.search(d):
    if req:required_unknown.append(('human_challenge:'+d)[:160])
    continue
   if SENSITIVE.search(d) and not EMAIL.search(d):
    if req:sensitive.append(d[:160])
    continue
   if typ in {'checkbox','radio'}:
    if not req:continue
    if typ=='checkbox' and CONSENT_OK.search(d) and not CONSENT_BAD.search(d):await e.check(timeout=1500);continue
    if typ=='radio' and SAFE_CHOICE.search(d) and not UNSAFE_CHOICE.search(d):await e.check(timeout=1500);continue
    required_unknown.append(d[:160] or typ);continue
   if tag=='select':
    if not req:continue
    pick=None
    for idx,opt in enumerate(m.get('options') or []):
     if idx and SAFE_CHOICE.search(str(opt)) and not UNSAFE_CHOICE.search(str(opt)):pick=idx;break
    if pick is None:required_unknown.append(d[:160] or 'select');continue
    await e.select_option(index=pick,timeout=1500);continue
   value=None
   if typ=='email' or EMAIL.search(d):value=email;filled['email']=True
   elif tag=='textarea' or MESSAGE.search(d):value=message;filled['message']=True
   elif COMPANY.search(d):value=company
   elif re.search(r'(ふりがな|ひらがな)',d,re.I):value='ぷらくてぃかるえーあいらぼ'
   elif re.search(r'(フリガナ|カナ|kana)',d,re.I):value='プラクティカルエーアイラボ'
   elif FIRST_NAME.search(d):value='Practical AI'
   elif LAST_NAME.search(d):value='Lab'
   elif NAME.search(d):value=name
   elif re.search(r'(部署|部門|department|designation|job.?title|position|役職|職種)',d,re.I):value='Operations'
   elif typ=='url' or URLRX.search(d):value=site
   elif SUBJECT.search(d):value='AI workflow fit check' if market!='JP-JA' else 'AI業務改善のご相談'
   elif req and typ in {'text','search','input'}:value=company
   elif req:required_unknown.append(d[:160] or typ);continue
   if value is not None:
    try:
     await e.fill(value,timeout=1800)
    except Exception:
     # React/SPA forms can replace the input node during hydration. Reacquire
     # the same logical field by stable name/id before declaring it unfillable.
     name=str(m.get('name') or '') if isinstance(m,dict) else ''
     eid=str(m.get('id') or '') if isinstance(m,dict) else ''
     retry=None
     if name: retry=form.locator(f'[name="{name}"]').first
     elif eid: retry=form.locator(f'#{eid}').first
     if retry is None: raise
     await retry.fill(value,timeout=3000)
  except Exception as ex:
   if req:required_unknown.append((d or type(ex).__name__)[:160])
 return {'ok':filled['email'] and filled['message'] and not sensitive and not required_unknown,'filled':filled,'sensitive':sensitive[:8],'required_unknown':required_unknown[:8]}
async def control(form,kind='final'):
 xs=form.locator('button,input[type=submit],input[type=button],input[type=image]');semantic=[];fallback=[]
 try:
  meta=await xs.evaluate_all("""els => els.slice(0,40).map((e,i)=>{
    const s=getComputedStyle(e),r=e.getBoundingClientRect();
    return {i,visible:s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0,
      enabled:!e.disabled,d:[e.name,e.id,e.placeholder,e.getAttribute('aria-label'),e.value,e.innerText].filter(Boolean).join(' '),
      typ:(e.getAttribute('type')||'').toLowerCase()};
  })""")
 except Exception:return None
 for m in meta:
  if not m.get('visible') or not m.get('enabled'):continue
  i=int(m.get('i') or 0);d=' '.join(str(m.get('d') or '').split())[:500];typ=str(m.get('typ') or '');compact=re.sub(r'\s+','',d)
  if REJECT_CONTROL.search(d):continue
  is_confirm=bool(CONFIRM.search(d) and not re.search(r'(送\\s*信|send|submit)',d,re.I))
  if kind=='confirm':
   if is_confirm:semantic.append((i,xs.nth(i),d))
   continue
  explicit_final=bool(FINAL.search(d) or re.fullmatch(r'送信',compact,re.I))
  if explicit_final and not is_confirm:semantic.append((i,xs.nth(i),d))
  elif typ=='submit' and not is_confirm:fallback.append((i,xs.nth(i),d))
 if len(semantic)==1:return semantic[0]
 if not semantic and len(fallback)==1:return fallback[0]
 return None
async def unique_final_on_page(page):
 hits=[]
 try:n=min(await page.locator('form').count(),20)
 except:return None
 for fi in range(n):
  try:
   f=page.locator('form').nth(fi)
   if not await f.is_visible():continue
   c=await control(f,'final')
   if c:hits.append((fi,c))
  except:continue
 return hits[0] if len(hits)==1 else None
async def click_and_evidence(page,loc,message,email,before_text):
 before_url=str(page.url or '')
 mutations=[];responses=[];resp_objs=[]
 def on_req(req):
  try:
   if str(req.method).upper() not in {'GET','HEAD','OPTIONS'}:mutations.append({'method':req.method,'url':req.url[:500],'matches_form_payload':_payload_match(req.post_data or '',message,email)})
  except:pass
 def on_resp(resp):
  try:
   req=resp.request
   if str(req.method).upper() not in {'GET','HEAD','OPTIONS'}:
    m=_payload_match(req.post_data or '',message,email);hdrs=resp.headers or {};responses.append({'method':req.method,'url':req.url[:500],'status':int(resp.status),'location':str(hdrs.get('location') or '')[:500],'matches_form_payload':m});
    if m:resp_objs.append(resp)
  except:pass
 page.on('request',on_req);page.on('response',on_resp);click_error=''
 try:
  await loc.click(timeout=5000)
  try:await page.wait_for_load_state('domcontentloaded',timeout=5000)
  except:pass
  await page.wait_for_timeout(1500)
 except Exception as e:click_error=type(e).__name__+':'+str(e)[:180]
 finally:
  try:page.remove_listener('request',on_req);page.remove_listener('response',on_resp)
  except:pass
 provider_success=False;provider_fail=False;bodies=[]
 before_success=SUCCESS.search(before_text or ''); before_failure=FAIL.search(before_text or '')
 for resp in resp_objs[:6]:
  try:
   raw=(await asyncio.wait_for(resp.text(),1.5))[:65536]
   st='';body_success=False;body_fail=False
   try:
    o=json.loads(raw);st=str(o.get('status') or '').lower() if isinstance(o,dict) else ''
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
 after_success=SUCCESS.search(after)
 before_success_text=SUCCESS.search(before_text or '')
 new_success=bool(after_success and (not before_success_text or after_success.group(0)!=before_success_text.group(0)))
 before_fail=FAIL.search(before_text or ''); after_fail=FAIL.search(after)
 new_validation_text=bool(after_fail and (not before_fail or after_fail.group(0)!=before_fail.group(0)))
 success_match=(after_success.group(0)[:240] if after_success else '')
 failure_match=(after_fail.group(0)[:240] if after_fail else '')
 final_text_excerpt=after[:1600]
 try: invalid_control_count=await page.locator('input:invalid,textarea:invalid,select:invalid').count()
 except: invalid_control_count=0
 try:
  payload_values_remaining=await page.locator('input,textarea').evaluate_all("(els,a)=>els.filter(e=>{const v=String(e.value||'');return v===String(a.email||'')||v===String(a.message||'')}).length",{'email':email,'message':message})
 except: payload_values_remaining=-1
 payload_cleared=(payload_values_remaining==0)
 validation=bool(new_validation_text or invalid_control_count>0)
 corr2xx=any(x['matches_form_payload'] and 200<=x['status']<300 for x in responses);corr4xx=any(x['matches_form_payload'] and x['status'] in {400,401,403,404,405,410,415,422} for x in responses)
 def pathmatch(rx,u):
  try:return bool(rx.search(urlsplit(str(u or '')).path or '/'))
  except:return False
 corr3xx=[x for x in responses if x['matches_form_payload'] and 300<=x['status']<400]
 corr204=any(x['matches_form_payload'] and x['status']==204 for x in responses)
 redirect_completion=any(pathmatch(COMPLETION_PATH,x.get('location')) for x in corr3xx)
 redirect_success_query=any(bool(SUCCESS_QUERY.search(str(x.get('location') or ''))) for x in corr3xx)
 redirect_confirm=any(pathmatch(CONFIRM_PATH,x.get('location')) for x in corr3xx)
 final_completion=pathmatch(COMPLETION_PATH,page.url)
 final_success_query=bool(SUCCESS_QUERY.search(str(page.url or '')))
 try:
  bu=urlsplit(before_url);au=urlsplit(str(page.url or ''));path_changed=(bu.netloc==au.netloc and (bu.path.rstrip('/') or '/')!=(au.path.rstrip('/') or '/'))
 except:path_changed=False
 correlated_2xx_navigation=bool(corr2xx and path_changed and not pathmatch(CONFIRM_PATH,page.url))
 correlated_3xx_cleared=bool(corr3xx and payload_cleared and not redirect_confirm and not pathmatch(CONFIRM_PATH,page.url))
 ev={'clicked_once':True,'submit_request_observed':bool(mutations),'submit_request_correlated':any(x['matches_form_payload'] for x in mutations),'submit_request_2xx':corr2xx,'submit_request_204':corr204,'submit_redirect_completion':redirect_completion,'submit_redirect_success_query':redirect_success_query,'submit_redirect_confirm':redirect_confirm,'final_completion_path':final_completion,'final_success_query':final_success_query,'post_submit_path_changed':path_changed,'payload_values_remaining':payload_values_remaining,'payload_cleared':payload_cleared,'correlated_2xx_navigation':correlated_2xx_navigation,'correlated_3xx_cleared':correlated_3xx_cleared,'server_success':provider_success,'server_not_sent':provider_fail or corr4xx,'success_dom':new_success,'success_match':success_match,'failure_match':failure_match,'final_text_excerpt':final_text_excerpt,'validation_error':validation,'new_validation_text':new_validation_text,'invalid_control_count':invalid_control_count,'network_mutations':mutations[:8],'network_responses':responses[:8],'response_bodies':bodies,'final_url':page.url[:500],'click_error':click_error}
 if (provider_success or new_success or corr204 or redirect_completion or redirect_success_query or final_completion or final_success_query or correlated_2xx_navigation or correlated_3xx_cleared) and not ev['server_not_sent'] and not validation:return 'SENT_CONFIRMED',ev
 if provider_fail or corr4xx or validation:return 'CONFIRMED_NOT_SENT',ev
 return 'AMBIGUOUS_HOLD',ev
async def await_submit_barrier(task,timeout=65.0):
 if MODE!='PRODUCTION' or task.get('submit_started') is True:return task
 token=str(task.get('token_id') or '');deadline=time.monotonic()+max(1.0,float(timeout))
 while time.monotonic()<deadline:
  try:q=await asyncio.to_thread(_get,TASK_URL)
  except Exception:
   await asyncio.sleep(.5);continue
  for x in (q.get('tasks') or []):
   if isinstance(x,dict) and str(x.get('token_id') or '')==token and x.get('submit_started') is True:return x
  await asyncio.sleep(.5)
 return None

async def process_task(browser,t):
 out={'kind':'PAL_V9_SEND_RESULT_V1','token_id':str(t.get('token_id') or ''),'company_key':str(t.get('company_key') or ''),'route_id':int(t.get('route_id') or 0),'at_epoch':int(time.time())}
 if not out['token_id'] or not t.get('canonical_url') or not t.get('message_body'):return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'INVALID_TASK','evidence':{'pre_submit':True}}
 if MODE=='PRODUCTION' and t.get('submit_started') is not True:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'SUBMIT_BARRIER_MISSING','evidence':{'pre_submit':True}}
 if MODE=='PRODUCTION' and not _proof_control_ok(t,60000):return {**out,'outcome':'TECH_RETRY','reason':'PROOF_EXPIRED_PRE_BROWSER','evidence':{'pre_submit':True,'proof_expires_at':t.get('proof_expires_at')}}
 if MODE=='PRODUCTION' and not await asyncio.to_thread(_production_control_ok):return {**out,'outcome':'TECH_RETRY','reason':'PRODUCTION_CONTROL_REVOKED_PRE_BROWSER','evidence':{'pre_submit':True,'control_recheck':True}}
 canonical_url=str(t['canonical_url']);domain=str(t.get('official_domain') or host(canonical_url));proof_url=str(t.get('proof_url') or '')
 url=proof_url if proof_url and host(proof_url)==domain else canonical_url;ctx=None;click_barrier=False
 try:
  ctx=await browser.new_context(user_agent=UA,ignore_https_errors=False);page=await ctx.new_page();page.set_default_timeout(3000)
  await page.route('**/*',lambda route: route.abort() if route.request.resource_type in {'image','media','font'} else route.continue_())
  nav_timeout=False;nav_alias_fallback=False
  try:
   await page.goto(url,wait_until='domcontentloaded',timeout=14000)
  except PlaywrightTimeoutError:
   nav_timeout=True
  except Exception as nav_exc:
   msg=str(nav_exc);u=urlsplit(url);fallback=''
   if (u.scheme.lower()=='https' and u.hostname and not u.hostname.lower().startswith('www.')
       and re.search(r'net::ERR_(?:CERT_AUTHORITY_INVALID|CERT_COMMON_NAME_INVALID|NAME_NOT_RESOLVED)',msg,re.I)):
    fallback=u._replace(netloc='www.'+str(u.netloc)).geturl()
   if fallback and host(fallback)==domain:
    nav_alias_fallback=True;url=fallback
    try:await page.goto(fallback,wait_until='domcontentloaded',timeout=14000)
    except PlaywrightTimeoutError:nav_timeout=True
   else:
    raise
  await page.wait_for_timeout(600 if nav_timeout else (800 if str(t.get('proof_lane') or '')=='FAST_DOM' else 1600))
  if host(page.url)!=domain:return {**out,'outcome':'SAFETY_BLOCKED','reason':'DOMAIN_CHANGED','evidence':{'final_url':page.url[:500]}}
  txt=await body_text(page,3500)
  if txt is None:return {**out,'outcome':'TECH_RETRY','reason':'BODY_UNREADABLE_PRE_SUBMIT','evidence':{'pre_submit':True,'navigation_timeout':nav_timeout,'final_url':page.url[:500]}}
  if nav_timeout:
   has_form=await has_any_form(page)
   if not has_form:
    # A navigation timeout can still leave a usable page that finishes
    # hydrating the contact form a moment later. Re-check the live DOM/frames
    # before declaring a technical retry; never click or submit in this wait.
    for delay_ms in (1200,1800):
     await page.wait_for_timeout(delay_ms)
     if await has_any_form(page):
      has_form=True;break
   if not has_form:return {**out,'outcome':'TECH_RETRY','reason':'NAVIGATION_TIMEOUT_NO_FORM','evidence':{'pre_submit':True,'final_url':page.url[:500],'late_form_wait_ms':3000}}
  if PROHIBIT.search(txt):return {**out,'outcome':'SAFETY_BLOCKED','reason':'SALES_PROHIBITED','evidence':{'pre_submit':True}}
  if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA','evidence':{'pre_submit':True}}
  chosen=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),t.get('proof_submit_text'))
  if not chosen:
   await page.wait_for_timeout(1800)
   if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA','evidence':{'pre_submit':True,'late_render':True}}
   chosen=await choose_form_any_frame(page,t.get('proof_frame_index'),t.get('proof_form_index'),t.get('proof_submit_text'))
  if not chosen:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'BUSINESS_CONTACT_FORM_NOT_FOUND','evidence':{'pre_submit':True,'late_retry':True}}
  _,frame_i,fi,form=chosen;fill=await fill_form(page,form,str(t['message_body']),str(t.get('reply_address') or ''),str(t.get('market') or ''))
  if fill.get('timed_out'):return {**out,'outcome':'TECH_RETRY','reason':'FILL_TIMEOUT_PRE_SUBMIT','evidence':{**fill,'pre_submit':True}}
  if fill['sensitive']:return {**out,'outcome':'SAFETY_BLOCKED','reason':'REQUIRED_SENSITIVE','evidence':fill}
  if not fill['ok']:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'REQUIRED_UNFILLABLE','evidence':{**fill,'pre_submit':True}}
  await page.wait_for_timeout(250)
  if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA_AFTER_FILL','evidence':{'pre_submit':True}}
  try:form_action=str(await form.get_attribute('action') or '')
  except:form_action=''
  confirm_action=bool(re.search(r'(confirm|review|check|kakunin|確認)',unquote_plus(form_action),re.I))
  confirm=await control(form,'confirm');final=await control(form,'final')
  if confirm_action and confirm is None and final is not None:
   confirm=final;final=None
  elif confirm is not None:
   final=None
  if final is None and confirm is None:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'SUBMIT_CONTROL_NOT_FOUND','evidence':{'pre_submit':True,'form_action':form_action[:500]}}
  if MODE!='PRODUCTION':return {**out,'outcome':'SHADOW_PREPARED','reason':'PRE_SUBMIT_ONLY','evidence':{'frame_index':frame_i,'form_index':fi,'form_action':form_action[:500],'final_control':bool(final),'confirm_control':bool(confirm)}}
  before=txt
  if MODE=='PRODUCTION' and not _proof_control_ok(t,30000):return {**out,'outcome':'TECH_RETRY','reason':'PROOF_EXPIRED_PRE_CLICK','evidence':{'pre_submit':True,'proof_expires_at':t.get('proof_expires_at')}}
  if MODE=='PRODUCTION' and not await asyncio.to_thread(_production_control_ok):return {**out,'outcome':'TECH_RETRY','reason':'PRODUCTION_CONTROL_REVOKED_PRE_CLICK','evidence':{'pre_submit':True,'control_recheck':True}}
  if confirm is not None:
   if MODE=='PRODUCTION' and not await asyncio.to_thread(_mark_click_started,t):return {**out,'outcome':'TECH_RETRY','reason':'CLICK_BARRIER_WRITE_FAILED','evidence':{'pre_submit':True}}
   click_barrier=True
   outcome,cev=await click_and_evidence(page,confirm[1],str(t['message_body']),str(t.get('reply_address') or ''),before)
   if outcome=='SENT_CONFIRMED':return {**out,'outcome':outcome,'reason':'CONFIRM_CLICK_SENT','evidence':cev}
   if outcome=='CONFIRMED_NOT_SENT':return {**out,'outcome':outcome,'reason':'CONFIRM_REJECTED','evidence':cev}
   corr_redirect=any(x.get('matches_form_payload') and 300<=int(x.get('status') or 0)<400 for x in (cev.get('network_responses') or []))
   if not (confirm_action and corr_redirect and not cev.get('validation_error') and not cev.get('server_not_sent')):
    return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'CONFIRM_AMBIGUOUS','evidence':cev}
   await page.wait_for_timeout(500)
   final_forms=[]
   for fri,root in enumerate(list(page.frames)[:12]):
    try:n=min(await root.locator('form').count(),12)
    except Exception:continue
    for j in range(n):
     f2=root.locator('form').nth(j)
     try:
      if not await f2.is_visible():continue
      c2=await control(f2,'final')
      if c2 is not None:final_forms.append((fri,j,f2,c2))
     except:continue
   if len(final_forms)!=1:return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'CONFIRM_NO_UNIQUE_FINAL_CONTROL','evidence':{**cev,'confirm_navigation':True,'final_candidates':len(final_forms)}}
   final_frame_i,final_form_i,form,final=final_forms[0]
   before=await body_text(page,3500) or ''
   if await visible_captcha_any(page):return {**out,'outcome':'SAFETY_BLOCKED','reason':'CAPTCHA_ON_CONFIRM_PAGE','evidence':{**cev,'confirm_navigation':True,'frame_index':final_frame_i,'form_index':final_form_i}}
   if MODE=='PRODUCTION' and not _proof_control_ok(t,30000):return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'PROOF_EXPIRED_BEFORE_FINAL','evidence':{**cev,'proof_expires_at':t.get('proof_expires_at')}}
   if MODE=='PRODUCTION' and not await asyncio.to_thread(_production_control_ok):return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'PRODUCTION_CONTROL_REVOKED_BEFORE_FINAL','evidence':{**cev,'control_recheck':True}}
  if MODE=='PRODUCTION' and not click_barrier:
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
async def main():
 q=_get(TASK_URL);tasks=[x for x in (q.get('tasks') or []) if isinstance(x,dict) and x.get('kind')=='PAL_V9_SEND_TASK_V1' and (0 if str(x.get('sender_shard',1)).strip()=='0' else 1)==SENDER_SHARD][:MAX_TASKS_PER_TURN];results=[]
 if not tasks:
  print(json.dumps({'status':'PASS','mode':MODE,'sender_shard':SENDER_SHARD,'tasks':0,'results':[]},ensure_ascii=False));return
 async with async_playwright() as p:
  chromium_path=(os.environ.get('PAL_CHROMIUM_PATH','').strip() or ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' if Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists() else '')))
  launch_kw={'headless':True,'args':['--disable-dev-shm-usage','--no-sandbox']}
  if chromium_path: launch_kw['executable_path']=chromium_path
  browser=await p.chromium.launch(**launch_kw)
  deferred=0
  try:
   armed_all=await asyncio.gather(*(await_submit_barrier(t,20.0) for t in tasks))
   ready=[x for x in armed_all if x is not None]
   deferred=len(tasks)-len(ready)
   sem=asyncio.Semaphore(SEND_CONCURRENCY)
   result_lock=asyncio.Lock()
   async def publish_one(res):
    async with result_lock:
     for attempt in range(3):
      try:
       try:r=await asyncio.to_thread(_get,RESULT_URL);prior=[x for x in (r.get('messages') or []) if isinstance(x,dict)]
       except:prior=[]
       tok=res.get('token_id');prior=[x for x in prior if x.get('token_id')!=tok]
       await asyncio.to_thread(_put,RESULT_URL,{'schema':'PAL_V9_SEND_RESULT_QUEUE_V1','updated_at_epoch':int(time.time()),'messages':(prior+[res])[-256:]})
       return True
      except Exception:
       if attempt<2:await asyncio.sleep(0.75*(attempt+1))
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
   try:await asyncio.wait_for(browser.close(),timeout=5.0)
   except:pass
 try:r=_get(RESULT_URL);prior=[x for x in (r.get('messages') or []) if isinstance(x,dict)]
 except:prior=[]
 keys={x.get('token_id') for x in results};prior=[x for x in prior if x.get('token_id') not in keys];_put(RESULT_URL,{'schema':'PAL_V9_SEND_RESULT_QUEUE_V1','updated_at_epoch':int(time.time()),'messages':(prior+results)[-256:]})
 print(json.dumps({'status':'PASS','mode':MODE,'sender_shard':SENDER_SHARD,'tasks':len(tasks),'max_tasks':MAX_TASKS_PER_TURN,'concurrency':SEND_CONCURRENCY,'deferred_unarmed':deferred,'results':[{k:x.get(k) for k in ('token_id','outcome','reason')} for x in results]},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
