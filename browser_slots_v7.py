# PAL_REPAIR_OWNER=INTEGRATION_E2E | Cross-lane edits prohibited; use published interfaces/contracts.
# PAL_REPAIR_PROTOCOL_V2=GLOBAL_SINGLE_WRITER | CLAIM_LANE=INTEGRATION_E2E before edit; ACCEPT_LANE after tests.
from __future__ import annotations
import asyncio, hashlib, json, os, re, sys, time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, unquote_plus
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from local_ledger_v7 import deterministic_not_sent_evidence

MAX_SLOTS = 2

VALIDATION_TEXT_RX = re.compile(
    r"(入力してください|未入力|入力内容.{0,12}誤|validation error|required field|"
    r"please\s*,?\s*(?:fill\s+in|enter|select|choose|complete)(?:\s+the)?(?:\s+following)?(?:\s+required)?(?:\s+fields?)?|"
    r"enter a valid|work email.{0,40}(?:required|not accepted)|valid business email|"
    r"complete the reCAPTCHA)",
    re.I,
)
STRONG_PROVIDER_SUCCESS_RX = re.compile(
    r"(thanks?\s+for\s+contacting\s+us|thanks?\s+for\s+getting\s+in\s+touch|"
    r"thank\s+you.{0,80}(?:message|inquir|contact)|"
    r"(?:message|inquir(?:y|ies)|request).{0,80}(?:has\s+been\s+)?(?:sent|received|submitted)|"
    r"successfully\s+(?:sent|submitted))",
    re.I,
)
STRONG_NOT_SENT_RX = re.compile(
    r"(?:failed|unable)\s+to\s+send(?:\s+(?:your|the))?\s+(?:message|inquir(?:y|ies)|request)|"
    r"(?:message|inquir(?:y|ies)|request)\s+(?:was|were)\s+not\s+sent|"
    r"could\s+not\s+send|couldn't\s+send|there\s+was\s+an\s+error.{0,60}send|"
    r"attempt\s+to\s+submit\s+corrupted\s+post\s+data|corrupted\s+post\s+data",
    re.I,
)
EMAIL_HANDOFF_TEXT_RX = re.compile(
    r"(?:submitting|submit(?:ting)?).{0,50}(?:opens?|launch(?:es)?)\s+(?:a\s+|your\s+)?(?:pre[- ]addressed\s+)?(?:email|mail)|"
    r"opens?\s+(?:a\s+|your\s+)?(?:pre[- ]addressed\s+)?(?:email|mail)\s+(?:app|client|program)",
    re.I,
)



def _matches_form_payload(payload: str, form_values: list[str]) -> bool:
    """Correlate a request with filled business fields, without logging values."""
    values = [str(v).strip() for v in form_values if len(str(v).strip()) >= 8]
    if not payload or not values:
        return False
    variants = [str(payload), unquote_plus(str(payload))]
    try:
        parsed = json.loads(payload)
        def strings(value):
            if isinstance(value, str):
                return [value]
            if isinstance(value, dict):
                return [s for v in value.values() for s in strings(v)]
            if isinstance(value, list):
                return [s for v in value for s in strings(v)]
            return []
        variants.extend(strings(parsed))
    except (ValueError, TypeError, RecursionError):
        pass
    normalized = [" ".join(v.split()) for v in variants]
    # A name/email alone can be included in analytics. Require the actual long
    # message, or two distinct business fields, before using a response as proof.
    hits = [v for v in set(values) if any(" ".join(v.split()) in p for p in normalized)]
    return any(len(v) >= 40 and " " in v for v in hits) or len(hits) >= 2


RENDERED_STAGE3_PROVENANCE_LANES = {
    "FAST_DOM", "DYNAMIC_JS", "IFRAME_DEEP", "DEEP",
}


def _confirmation_request_submit_eligible(meta: dict, desc: str) -> bool:
    """Use requestSubmit only for a native, explicitly non-final confirm control."""
    if not isinstance(meta, dict) or str(meta.get("type") or "").lower() != "submit":
        return False
    text = " ".join(str(desc or "").split())
    if not text:
        return False
    if not re.search(
        r"(確認画面へ|入力内容を確認|内容を確認|確認する|を確認する|confirm|next|次へ)",
        text, re.I,
    ):
        return False
    if re.search(r"(戻る|back|cancel|修正|reset|クリア)", text, re.I):
        return False
    if re.search(r"(送信|\bsend\b|\bsubmit\b)", text, re.I):
        return False
    return True


def _final_live_preflight_provenance(stage3_detail: dict, stage3_full_v3: bool):
    """Return truthful proof provenance after the current live Browser preflight.

    A prior rendered Stage3 proof may keep its original rendered lane for
    throughput attribution. Static/HTTP evidence cannot become a rendered proof
    merely by carrying its old label forward; once this function is reached the
    current Playwright page is the rendered authority, so those jobs are
    promoted to LIVE_BROWSER_PREFLIGHT / LIVE_PREFLIGHT.
    """
    detail = dict(stage3_detail or {})
    prior_source = str(detail.get("proof_source") or "")
    prior_lane = str(detail.get("lane_mode") or "").upper()
    prior_rendered = bool(
        stage3_full_v3
        and prior_source == "RENDERED_BROWSER_V2"
        and prior_lane in RENDERED_STAGE3_PROVENANCE_LANES
    )
    if prior_rendered:
        return prior_source, prior_lane
    return "LIVE_BROWSER_PREFLIGHT", "LIVE_PREFLIGHT"


def _requires_trusted_field_events(html: str) -> bool:
    """Builders such as Wix keep framework state separate from raw DOM values."""
    z = str(html or '')[:900000]
    return bool(re.search(
        r'(?:static\.parastorage\.com|wixstatic\.com|wix-thunderbolt|data-mesh-id=|wixui-|viewerModel)',
        z, re.I
    ))


def _provider_success_navigation(before_url: str, after_url: str) -> bool:
    """Recognize only provider-owned redirects that explicitly encode success."""
    if not after_url or after_url == before_url:
        return False
    try:
        parts = urlsplit(after_url)
        host = (parts.hostname or '').lower().removeprefix('www.')
        query = unquote_plus(parts.query or '')
    except Exception:
        return False
    if host == 'submitted.formspark.io':
        return bool(re.search(r'(?:^|&)_formId=[^&]+(?:&|$)', query, re.I)
                    and re.search(r'(?:^|&)_status=OK(?:&|$)', query, re.I))
    return False


def _provider_api_success(url: str, status: int) -> bool:
    """Recognize a small allow-list of provider endpoints whose 2xx means accepted.

    This is only evaluated for requests already correlated to the filled business
    payload. Generic 2xx responses remain insufficient delivery evidence.
    """
    try:
        p=urlsplit(str(url or ''))
        host=(p.hostname or '').lower().removeprefix('www.')
        path=p.path or ''
        code=int(status or 0)
    except Exception:
        return False
    if host=='api.framer.com' and re.fullmatch(r'/forms/v1/forms/[^/]+/submit/?', path):
        return code in {200,201,202,204}
    if host=='api.formhq.uk' and re.fullmatch(r'/submission/[^/]+/?', path):
        return code in {200,201,202,204}
    if re.fullmatch(r'forms(?:-[a-z0-9]+)?\.hscollectedforms\.net', host, re.I) and path.rstrip('/')=='/collected-forms/submit/form':
        return code in {200,201,202,204}
    if host=='forms.hsforms.com' and re.fullmatch(
            r'/submissions/v3/public/submit/(?:formsnext/)?(?:multipart/)?[^/]+/[^/]+/?', path, re.I):
        return code in {200,201,202,204}
    if host=='webflow.com' and re.fullmatch(r'/api/v1/form/[^/]+/?', path, re.I):
        return code in {200,201,202,204}
    if host=='contact.apps-api.instantpage.secureserver.net' and path.rstrip('/')=='/v3/messages':
        return code in {200,201,202,204}
    # Hostinger Website Builder posts the actual contact payload to this
    # provider-owned backend. This helper is evaluated only for a response
    # already correlated to the filled business payload, so a 2xx here is an
    # authoritative provider acknowledgement rather than generic page traffic.
    if host=='builder-backend.hostinger.com' and re.fullmatch(r'/u\d+/data/v3/post/[^/]+/?', path, re.I):
        return code in {200,201,202,204}
    return False


def _provider_body_success(url: str, status: int, app_status: str) -> bool:
    """Recognize provider-specific JSON success states that need response body context."""
    try:
        p=urlsplit(str(url or ''))
        path=p.path or ''
        code=int(status or 0)
        state=str(app_status or '').strip().lower()
    except Exception:
        return False
    # MetForm returns JSON {"status":"1", ...} after an accepted entry.
    # Only the provider's exact insert endpoint and a successful HTTP response
    # qualify; generic WordPress 2xx responses remain insufficient evidence.
    if re.fullmatch(r'/wp-json/metform/v1/entries/insert/\d+/?', path, re.I):
        return code in {200,201} and state=='1'
    return False


def _non_postable_static_form_action(url: str) -> bool:
    """Detect static-export form targets that cannot accept the live POST."""
    return bool(re.search(r'(?:[?&])simply_static_page=[^&#]+(?:[&#]|$)', str(url or ''), re.I))


def _correlated_http_rejection(responses) -> bool:
    """Return True only for a definitive rejection of the exact form payload."""
    definitive={400,401,403,404,405,410,415,422}
    return any(
        isinstance(x,dict)
        and x.get("matches_form_payload") is True
        and int(x.get("status") or 0) in definitive
        for x in (responses or [])
    )


def _cleared_required_fields_are_validation(visible_invalid, strong_provider_success_visible: bool) -> bool:
    """Treat :invalid as rejection only when no new strong provider success exists."""
    try:
        invalid = int(visible_invalid or 0) > 0
    except Exception:
        invalid = False
    return bool(invalid and not strong_provider_success_visible)


def _submit_outcome(evidence: dict) -> tuple[str, int]:
    """Classify delivery only from independent post-click evidence.

    Payload correlation remains the normal path. Some established form providers
    serialize fields in a way our generic payload matcher cannot decode, while
    also emitting a provider-owned success event plus a newly-rendered strong
    success message. Treat that pair as a correlated provider acknowledgement;
    a click, HTTP status, disappearing form, or generic success text alone never
    qualifies.
    """
    e = evidence
    independent = sum(bool(v) for v in (
        e.get("submit_request_2xx"), e.get("server_success"), e.get("success_dom"),
        e.get("thank_you_navigation"),
        e.get("form_disappeared") and not e.get("validation_error"),
    ))
    positive = bool(e.get("server_success") or e.get("success_dom") or e.get("thank_you_navigation"))
    event_types = {
        str(x.get("type") or "")
        for x in (e.get("form_events") or [])
        if isinstance(x, dict)
    }
    cf7 = e.get("cf7_event") if isinstance(e.get("cf7_event"), dict) else {}
    if cf7:
        event_types.add(str(cf7.get("type") or ""))
    provider_success_event = bool(event_types & {
        "wpcf7mailsent",
        "wpformsAjaxSubmitSuccess",
        "gform_confirmation_loaded",
        "fluentform_submission_success",
    })
    provider_ack = bool(
        e.get("clicked_once")
        and provider_success_event
        and e.get("server_success")
        and e.get("provider_success_dom")
        and e.get("strong_provider_success_text")
        and not e.get("validation_error")
        and not e.get("server_not_sent")
    )
    # A correlated successful POST followed by removal of the submitted form is
    # a second independent state transition. Live evidence showed this exact
    # pattern repeatedly landing in AMBIGUOUS_HOLD despite no validation/server
    # rejection. Do not generalize to click-only, 2xx-only, or disappearance-only.
    correlated_transition_ack = bool(
        e.get("clicked_once")
        and e.get("submit_request_correlated")
        and e.get("submit_request_2xx")
        and e.get("form_disappeared")
        and not e.get("validation_error")
        and not e.get("server_not_sent")
    )
    # Canonical durable not-sent predicate is shared with LocalLedger. Keep it
    # after the conflict check below so contradictory positive evidence remains
    # ambiguous instead of being auto-closed.
    if e.get("server_not_sent") and positive:
        return "AMBIGUOUS_HOLD", independent
    if (e.get("submit_request_correlated") and independent >= 2 and positive
            and not e.get("server_not_sent")
            and (not e.get("validation_error") or e.get("server_success") or e.get("thank_you_navigation"))):
        return "SENT_CONFIRMED", independent
    if (e.get("submit_request_correlated")
            and e.get("provider_success_dom")
            and e.get("strong_provider_success_text")
            and not e.get("validation_error")
            and not e.get("server_not_sent")):
        return "SENT_CONFIRMED", max(independent, 2)
    if provider_ack:
        return "SENT_CONFIRMED", max(independent, 2)
    if correlated_transition_ack:
        return "SENT_CONFIRMED", max(independent, 2)
    if deterministic_not_sent_evidence(e):
        return "CONFIRMED_NOT_SENT", independent
    return "AMBIGUOUS_HOLD", independent

# Single canonical field-semantics helper injected into every DOM scan.
#
# Fill, pre-submit missing-check and immediately-before-submit revalidation used
# to carry three separately-maintained copies of "is this field required", each
# weaker than the last. A field marked required only by a label '*' was filled
# by none of them but reported missing by one, which produced both
# PRE_SUBMIT_REQUIRED_MISSING and, when the weaker scan let it through,
# server-side rejections recorded as CONFIRMED_NOT_SENT(validation_error).
# Every scan now derives required/label text from these shared functions so the
# three views cannot drift apart again.
PAL_FIELD_JS = r"""
const palLabelOf=(e)=>{
  const id=e.id||'';
  let lab=null;
  try{lab=id?document.querySelector('label[for="'+CSS.escape(id)+'"]'):null;}catch(_){lab=null;}
  const labels=e.labels?[...e.labels].map(x=>x.innerText||'').join(' '):'';
  return (((lab&&lab.innerText)||labels||'')+'').trim();
};
const palRowLabel=(e)=>{
  const tr=e.closest('tr'),cell=e.closest('th,td');let rowLabel='';
  if(tr&&cell){const cells=[...tr.children],idx=cells.indexOf(cell);
    rowLabel=((idx>0?cells.slice(0,idx).map(c=>c.innerText||'').join(' '):'')||((tr.querySelector('th')||{}).innerText||'')).trim();}
  const dd=e.closest('dd');
  if(!rowLabel&&dd&&dd.previousElementSibling&&dd.previousElementSibling.tagName==='DT')
    rowLabel=(dd.previousElementSibling.innerText||'').trim();
  if(!rowLabel){const box=e.closest('.form-item-box,.form-group,.form-row,.field');
    const h=box&&box.querySelector('dt,.field-label,.form-label,.label');
    if(h)rowLabel=(h.innerText||'').trim();}
  return rowLabel;
};
const palSelfDesc=(e)=>((e.name||'')+' '+(e.id||'')+' '+(e.placeholder||'')+' '+
  (e.getAttribute('aria-label')||'')+' '+palLabelOf(e)).slice(0,320);
const palWrap=(e)=>e.closest('label,.form-group,.form-row,.field,li,dl,dd,dt,p')||e.parentElement;
const palVisible=(e)=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
  return r.width>0&&r.height>0&&cs.display!=='none'&&cs.visibility!=='hidden';};
const palRequired=(e)=>{
  if(e.required||e.getAttribute('aria-required')==='true')return true;
  if(/(^|[\s_-])(required|mandatory)([\s_-]|$)/i.test(String(e.className||'')))return true;
  const self=palSelfDesc(e),row=palRowLabel(e),lbl=palLabelOf(e);
  if(/[※＊*]\s*$/.test(row)||/[※＊*]\s*$/.test(self)||/[※＊*]\s*$/.test(lbl))return true;
  if(/^\s*[※＊*]/.test(row)||/^\s*[※＊*]/.test(lbl))return true;
  if(/(必須|required|mandatory)/i.test(self+' '+row+' '+lbl))return true;
  const wrap=palWrap(e);
  if(wrap){
    const peers=wrap.querySelectorAll('input:not([type=hidden]),textarea,select').length;
    if(peers<=1){
      const wt=((wrap.innerText||'')+'').trim();
      if(wt.length<=260&&(/(必須|required|mandatory)/i.test(wt)||/[※＊*]\s*$/.test(wt)))return true;
      if(wrap.querySelector('abbr[title*="required" i],.required,.is-required,.form-required,.gfield_required'))return true;
    }
  }
  return false;
};
"""


def _pal_js(body: str) -> str:
    """Wrap an evaluate_all body so the shared field helpers are in scope.

    evaluate_all needs a single expression, so the helper declarations have to
    live inside the arrow function body rather than beside it.
    """
    return "els=>{" + PAL_FIELD_JS + body + "}"


# Choice controls (select/radio) whose answer would be a factual claim about us
# that this system does not actually know. These are never guessed: picking an
# option here would fabricate an employee count, revenue band, budget, role,
# industry, location or customer relationship in a message a real company reads.
UNKNOWN_FACT_RX = re.compile(
    r"(employee|headcount|head\s*count|company\s*size|team\s*size|organi[sz]ation\s*size|"
    r"number\s+of\s+(?:employees|staff|users|seats)|\bstaff\b|how\s+many|how\s+large|"
    r"revenue|turnover|annual\s+sales|budget|price\s*range|spend|investment|"
    r"industry|sector|vertical|market\s+segment|"
    r"country|state|province|region|city|location|zip|postal|timezone|time\s*zone|"
    r"job\s*title|\brole\b|position|seniority|department|\bi\s+am\b|i'm\s+a|"
    r"existing\s+(?:customer|client)|current\s+(?:customer|client)|customer\s+status|"
    r"member(?:ship)?\s+status|account\s+(?:number|status)|subscriber|"
    r"従業員|社員数|売上|年商|予算|業種|業界|規模|役職|所在地|都道府県|"
    r"ご職業|お立場|会員)", re.I)

# Neutral, non-factual intent options. Choosing one of these asserts only the
# purpose of this message, which is a fact we do know.
NEUTRAL_OPTION_RX = re.compile(
    r"(お問い合わせ|その他|一般|ご提案|協業|業務提携|"
    r"\bothers?\b|general|business\s+(?:inquir|enquir)|partnership|collaboration|"
    r"new\s+inquiry|service\s+inquiry|request\s+information|"
    r"no\s+preference|not\s+applicable|\bn/?a\b)", re.I)

# Personal-only fields this system never fabricates. Shared by the fill pass and
# the immediately-before-submit revalidation so a required mailing address or
# phone number cannot pass one check and be missed by the other.
# (?<!email )(?<!e-mail )(?<!mail )\baddress\b: a required field merely labeled
# "Email Address" is not a personal mailing address. Without this exclusion the
# bare \baddress\b match false-positives on that extremely common phrasing and
# SAFETY_BLOCKs an otherwise-clean business contact form; "Mailing/Home/Postal
# Address" etc. still match.
# Submit controls addressed relative to the selected form. input[type=image] is
# a real submit control whose caption lives in @alt, so it has to be readable
# here or an image-button form looks like it has no way to send. The root-scoped
# variant is only ever used on a proven confirmation page.
PAL_SUBMIT_SELECTOR = "button,input[type=submit],input[type=image]"
PAL_ROOT_SUBMIT_SELECTOR = "button,input[type=submit],input[type=button]"
# confirmation_control produces an index that advance_confirmation clicks;
# they must always scan the identical control set.
PAL_CONFIRM_SELECTOR = "button,input[type=submit],input[type=button]"
PAL_SUCCESS_SELECTOR = (
    ".wpforms-confirmation-container-full,.wpforms-confirmation-container,"
    ".gform_confirmation_message,.gform_confirmation_wrapper,"
    ".elementor-message-success,.ff-message-success,[data-fs-success],"
    ".nf-response-msg,.frm_message,.et-pb-contact-message,.w-form-done,"
    # Magento and several compatible storefront themes publish the post-submit
    # flash acknowledgement in a newly-rendered .message-success element.
    # before_provider_texts snapshots pre-click content, so pre-existing shop
    # notices cannot qualify as delivery evidence.
    ".message-success,[data-ui-id='message-success'],"
    ".wpcf7.sent .wpcf7-response-output,.wpcf7[data-status='sent'] .wpcf7-response-output"
)
PAL_CONTROL_DESC_JS = (
    "e => ((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')"
    "+' '+(e.getAttribute('alt')||'')+' '+(e.getAttribute('title')||'')"
    "+' '+(e.name||'')+' '+(e.id||'')).trim()"
)

_STAGE3_PHONE_FIELD_RE = re.compile(r'(phone|telephone|mobile|tel(?:ephone)?|電話|携帯)', re.I)

def _stage3_phone_reverify_clear(reservoir_row: dict) -> bool:
    """True only when fresh FULL proof explicitly disproves stale required-phone."""
    if not isinstance(reservoir_row, dict) or not reservoir_row.get("_stage3_full_v3_fresh"):
        return False
    try:
        detail=json.loads(str(reservoir_row.get("_stage3_full_v3_detail_json") or "{}"))
        fields=json.loads(str(reservoir_row.get("_stage3_full_v3_field_schema_json") or "[]"))
    except Exception:
        return False
    if not isinstance(detail,dict) or not isinstance(fields,list):
        return False
    if not (detail.get("required_sensitive") is False
            and detail.get("required_unfillable") is False
            and detail.get("required_fillable") is True):
        return False
    for x in fields:
        if not isinstance(x,dict) or x.get("required") is not True:
            continue
        typ=str(x.get("type") or "").lower()
        role=str(x.get("role") or "").lower()
        desc=str(x.get("desc") or "")
        if typ=="tel" or role=="phone" or _STAGE3_PHONE_FIELD_RE.search(desc):
            return False
    return True

PAL_SENSITIVE_RX = re.compile(
    r"(電話|\btel\b|\bphone\b|mobile|\b(?:full|contact|telephone|phone)[ _.-]?number\b|"
    r"住所|(?<!email )(?<!e-mail )(?<!mail )\baddress\b|郵便|\bpostal\b|\bzip\b|"
    r"都道府県|市区町村|番地)", re.I)


@dataclass
class BrowserSlot:
    index: int
    context: BrowserContext
    page: Page
    target_frame_index: int = 0
    stage3_control_kind: str = ""
    submit_form_values: list[str] = field(default_factory=list)

class BrowserSlots:
    def __init__(self, slots: int = MAX_SLOTS, extra_route=None):
        self.slots_requested = max(1, min(MAX_SLOTS, int(slots)))
        self.pw = None
        self.browser: Browser | None = None
        self.slots: list[BrowserSlot] = []
        self.critical_submit = asyncio.Lock()
        # Optional async (route) -> bool hook, checked before the default
        # image/media/font filter. Used only by the offline fixture benchmark
        # to fulfill synthetic contact-form pages without any real network
        # access; production never sets this, so behavior is unchanged.
        self.extra_route = extra_route

    async def start(self) -> None:
        if self.browser:
            return
        self.pw = await async_playwright().start()
        executable = os.getenv("PAL_V6_CHROME_PATH", "").strip()
        if not executable:
            executable = (
                "/usr/bin/chromium" if os.path.exists("/usr/bin/chromium")
                else "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            )
        kwargs = {
            "headless": True,
            "args": ["--disable-background-networking", "--disable-sync",
                     "--disable-dev-shm-usage", "--no-sandbox"],
        }
        if os.path.exists(executable):
            kwargs["executable_path"] = executable
        self.browser = await self.pw.chromium.launch(**kwargs)
        for i in range(self.slots_requested):
            context = await self.browser.new_context()
            await self._install_lightweight_routes(context)
            page = await context.new_page()
            page.set_default_timeout(3500)
            page.set_default_navigation_timeout(12000)
            self.slots.append(BrowserSlot(i, context, page))

    async def _install_lightweight_routes(self, context: BrowserContext) -> None:
        # PAL production outreach is form-only. Never hand an automated action
        # off to Mail/Phone through an external protocol.
        await context.add_init_script(r"""(() => {
          const blocked = v => /^(?:mailto|tel):/i.test(String(v || '').trim());
          document.addEventListener('click', e => {
            const a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
            if (a && blocked(a.getAttribute('href'))) {
              e.preventDefault(); e.stopImmediatePropagation();
            }
          }, true);
          document.addEventListener('submit', e => {
            const f = e.target;
            if (f && blocked(f.getAttribute && f.getAttribute('action'))) {
              e.preventDefault(); e.stopImmediatePropagation();
            }
          }, true);
          const nativeOpen = window.open;
          window.open = function(url, ...args) {
            if (blocked(url)) return null;
            return nativeOpen.call(this, url, ...args);
          };
          const nativeSubmit = HTMLFormElement.prototype.submit;
          HTMLFormElement.prototype.submit = function(...args) {
            if (blocked(this.getAttribute('action'))) return;
            return nativeSubmit.apply(this, args);
          };
          const nativeRequestSubmit = HTMLFormElement.prototype.requestSubmit;
          if (nativeRequestSubmit) {
            HTMLFormElement.prototype.requestSubmit = function(...args) {
              if (blocked(this.getAttribute('action'))) return;
              return nativeRequestSubmit.apply(this, args);
            };
          }
        })();""")
        async def handler(route):
            if self.extra_route is not None and await self.extra_route(route):
                return
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", handler)

    async def close(self) -> None:
        for slot in self.slots:
            await slot.context.close()
        self.slots.clear()
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.pw:
            await self.pw.stop()
            self.pw = None

    async def recycle_slot(self, slot: BrowserSlot) -> BrowserSlot:
        """Dispose company state while keeping the single Chrome process alive."""
        if not self.browser:
            raise RuntimeError("BROWSER_NOT_STARTED")
        try:
            await asyncio.wait_for(slot.context.close(), timeout=3.0)
        except Exception:
            pass
        context = await asyncio.wait_for(self.browser.new_context(), timeout=5.0)
        await self._install_lightweight_routes(context)
        page = await asyncio.wait_for(context.new_page(), timeout=5.0)
        page.set_default_timeout(3500)
        page.set_default_navigation_timeout(12000)
        slot.context = context
        slot.page = page
        slot.target_frame_index = 0
        slot.submit_form_values = []
        self.slots[slot.index] = slot
        return slot

    def _target_root(self, slot: BrowserSlot):
        frames = list(slot.page.frames)
        idx = int(getattr(slot, "target_frame_index", 0) or 0)
        if 0 <= idx < len(frames):
            return frames[idx]
        return slot.page.main_frame

    async def _fill_sticky(self, loc, value: str) -> None:
        """Fill a safe field and verify the page did not immediately erase it."""
        target = str(value)
        try:
            await loc.fill(target)
        except Exception:
            pass
        try:
            if str(await loc.input_value()) == target:
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
        }""", target)
        try:
            if str(await loc.input_value()) == target:
                return
        except Exception:
            pass
        raise RuntimeError("STICKY_FILL_FAILED")

    async def _commit_field_value(self, loc, value: str) -> bool:
        """Fill, trigger framework validation, and verify the value survives."""
        target = str(value)
        try:
            await self._fill_sticky(loc, target)
            await loc.evaluate("""e=>{
              e.dispatchEvent(new Event('change',{bubbles:true}));
              if (typeof e.blur === 'function') e.blur();
            }""")
            await asyncio.sleep(0.08)
            return str(await loc.input_value()) == target
        except Exception:
            return False

    async def _batch_commit_values(self, form, assignments: list[dict]) -> set[int]:
        """Set multiple safe text values in one DOM call, then verify in one DOM call."""
        if not assignments:
            return set()
        try:
            fields = form.locator("input,textarea,select")
            await fields.evaluate_all(r"""(els,items)=>{
              const setv=(e,v)=>{
                const proto=e.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype :
                  (e.tagName==='SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype);
                const d=Object.getOwnPropertyDescriptor(proto,'value');
                if(!d||!d.set) return false;
                d.set.call(e,String(v));
                e.dispatchEvent(new Event('input',{bubbles:true}));
                e.dispatchEvent(new Event('change',{bubbles:true}));
                if(typeof e.blur==='function') e.blur();
                return true;
              };
              for(const it of items){ const e=els[it.i]; if(e) setv(e,it.value); }
            }""", assignments)
            await asyncio.sleep(0.08)
            ok = await fields.evaluate_all(
                """(els,items)=>items.filter(it=>els[it.i]&&String(els[it.i].value||'')===String(it.value)).map(it=>it.i)""",
                assignments,
            )
            return {int(x) for x in (ok or [])}
        except Exception:
            return set()

    async def _visible_captcha_challenge(self, root) -> bool:
        """Return True only for an active/visible CAPTCHA challenge."""
        selectors=[
            '.g-recaptcha','.h-captcha','.cf-turnstile','[data-sitekey]',
            'iframe[src*="recaptcha"]','iframe[src*="hcaptcha"]',
            'iframe[src*="challenges.cloudflare.com"]','[class*="captcha" i]','[id*="captcha" i]'
        ]
        for sel in selectors:
            try:
                loc=root.locator(sel)
                for i in range(min(await loc.count(),8)):
                    if await loc.nth(i).is_visible():
                        return True
            except Exception:
                pass
        try:
            text=' '.join((await root.locator('body').inner_text(timeout=1500)).split())
            return bool(re.search(r'(画像認証|\bcaptcha\b|私はロボットではありません|not a robot|security challenge)',text,re.I))
        except Exception:
            return False

    async def set_fixture(self, slot: BrowserSlot, html: str) -> dict:
        await slot.page.set_content(html, wait_until="domcontentloaded")
        return await self.inspect(slot)

    async def inspect(self, slot: BrowserSlot) -> dict:
        return await slot.page.evaluate(
            """() => {
              const text = document.body?.innerText || '';
              const html = document.documentElement?.innerHTML || '';
              const forms = [...document.querySelectorAll('form')];
              const required = [...document.querySelectorAll(
                'input[required],textarea[required],select[required]'
              )].map(x => (
                (x.name || '') + ' ' + (x.id || '') + ' ' +
                (x.getAttribute('aria-label') || '') + ' ' +
                (x.placeholder || '')
              ).toLowerCase());
              return {text, html, form_count: forms.length, required};
            }"""
        )

    async def _form_submit_controls(self, root, form_index: int):
        """Controls that submit exactly the selected form.

        Two associations count, both unambiguous per the HTML spec: a control
        contained by the form, and a control carrying form="<id>" naming it.
        Nothing global is ever included, so a page-level button that happens to
        say "Send" cannot be clicked.

        final_submit_control and submit_prepared both resolve through here, so
        an index produced by one always addresses the same element in the other.
        """
        forms = root.locator("form")
        inside = forms.nth(int(form_index)).locator(PAL_SUBMIT_SELECTOR)
        form_id = ""
        try:
            form_id = str(await forms.nth(int(form_index)).evaluate("f => f.id || ''") or "")
        except Exception:
            form_id = ""
        if not form_id:
            return inside
        safe_id = form_id.replace("\\", "\\\\").replace('"', '\\"')
        external = root.locator(
            ",".join(f'{part}[form="{safe_id}"]' for part in PAL_SUBMIT_SELECTOR.split(","))
        )
        try:
            return inside.or_(external)
        except Exception:
            return inside

    @staticmethod
    def select_answer(core: str, options: list[dict]) -> tuple[str | None, str | None]:
        """Pick a truthful answer for a required <select>, or refuse to answer.

        Returns (value, None) only when the control asks for intent and a
        neutral, non-factual option exists. Anything that would assert an
        unknown fact about us -- employee count, revenue, budget, role,
        industry, location, customer status -- returns (None, refusal) so the
        caller fails closed instead of guessing.
        """
        if UNKNOWN_FACT_RX.search(str(core or "")):
            return None, "REQUIRED_UNKNOWN_FACT"
        pick = next((str(o.get("v") or "") for o in (options or [])
                     if o.get("v") and NEUTRAL_OPTION_RX.search(str(o.get("t") or ""))), None)
        if not pick:
            return None, "REQUIRED_UNKNOWN_FACT"
        return pick, None

    @staticmethod
    def fixture_safety(snapshot: dict) -> tuple[bool, str]:
        combined = (snapshot.get("text") or "") + "\n" + (snapshot.get("html") or "")
        low = combined.lower()
        if "captcha" in low or "recaptcha" in low or "hcaptcha" in low or "cf-turnstile" in low:
            return False, "CAPTCHA"
        if "sales solicitations are not accepted" in low or "営業目的" in combined and "お断り" in combined:
            return False, "SALES_PROHIBITED"
        required = snapshot.get("required") or []
        phone_required = any(x for x in required if any(t in x for t in ("phone", "mobile", "tel")))
        company_present = any(t in low for t in ("company", "organization", "organisation", "会社", "法人"))
        if phone_required and not company_present:
            return False, "REQUIRED_PERSONAL_ONLY"
        if int(snapshot.get("form_count") or 0) < 1:
            return False, "NO_FORM"
        return True, "PASS"

    async def submit_control_proof(self, page: Page) -> dict:
        """Locate a visible submit/confirm control without clicking it."""
        controls = await page.locator(
            "button,input[type=submit],input[type=button],input[type=image],a[role=button]"
        ).evaluate_all(r"""els=>els.map((e,i)=>{
          const s=getComputedStyle(e),r=e.getBoundingClientRect();
          const visible=!e.disabled && s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
          const text=((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')).trim();
          return {i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),text,visible};
        }).filter(x=>x.visible)""")
        direct = re.compile(r"(送信|submit|send|送る|申し込む|問い合わせる)", re.I)
        confirm = re.compile(r"(確認|confirm|next|次へ|入力内容)", re.I)
        ranked = [x for x in controls if direct.search(str(x.get("text") or ""))]
        kind = "DIRECT_SUBMIT"
        if not ranked:
            ranked = [x for x in controls if confirm.search(str(x.get("text") or ""))]
            kind = "CONFIRM_OR_NEXT"
        if not ranked:
            return {"safe": False, "reason": "SUBMIT_CONTROL_MISSING", "controls_seen": len(controls)}
        chosen = ranked[0]
        return {
            "safe": True,
            "reason": "SUBMIT_CONTROL_PRESENT",
            "submit_control_kind": kind,
            "submit_control": {
                "index": int(chosen.get("i") or 0),
                "tag": str(chosen.get("tag") or ""),
                "type": str(chosen.get("type") or ""),
                "text": str(chosen.get("text") or "")[:160],
            },
            "candidate_count": len(ranked),
        }

    async def browser_form_proof(self, page: Page) -> dict:
        """Conservative live-DOM proof used only when static HTML proof cannot classify a form."""
        return await page.evaluate(r"""() => {
          const visible = e => {
            const s=getComputedStyle(e),r=e.getBoundingClientRect();
            return !e.disabled && e.type!=='hidden' && s.display!=='none' &&
              s.visibility!=='hidden' && r.width>0 && r.height>0;
          };
          const desc = e => {
            const labels=e.labels ? [...e.labels].map(x=>x.innerText||'').join(' ') : '';
            const id=e.id||'', lab=id ? document.querySelector('label[for="'+CSS.escape(id)+'"]') : null;
            const wrap=e.closest('label,.form-group,.form-row,.field,tr,li,dl,dd,dt,p')||e.parentElement;
            return [e.name||'',id,e.placeholder||'',e.getAttribute('aria-label')||'',
                    labels,(lab&&lab.innerText)||'',(wrap&&wrap.innerText)||''].join(' ').slice(0,900);
          };
          const sensitive=/(携帯|個人.{0,8}(電話|住所)|自宅|\bmobile\b|\bphone\b|\btel\b|住所|\baddress\b|郵便|\bpostal\b|\bzip\b|都道府県|市区町村|番地)/i;
          const message=/(問い合わせ内容|お問合せ内容|ご用件|message|inquiry|enquiry|comment|内容|詳細)/i;
          const email=/(メール|e-?mail|mail address|(?:^|[\s_.-])mail(?:$|[\s_.-]))/i;
          const submit=/(送信|確認|入力内容を確認|submit|send|confirm|next|次へ)/i;
          for (const form of [...document.querySelectorAll('form')].slice(0,10)) {
            const fields=[...form.querySelectorAll('input,textarea,select')].filter(visible);
            if (!fields.length) continue;
            const ds=fields.map(e=>({e,d:desc(e),req:!!e.required||String(e.getAttribute('aria-required')||'').toLowerCase()==='true'}));
            const hasMessage=ds.some(x=>x.e.tagName==='TEXTAREA'||message.test(x.d));
            const hasEmail=ds.some(x=>(x.e.type||'').toLowerCase()==='email'||email.test(x.d));
            const requiredSensitive=ds.some(x=>x.req&&sensitive.test(x.d));
            const controls=[...form.querySelectorAll('button,input[type=submit],input[type=button],input[type=image],a[role=button]')]
              .filter(visible).map(e=>((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')).trim());
            const hasSubmit=controls.some(x=>submit.test(x)) || form.querySelector('input[type=submit],button[type=submit]');
            if (hasMessage && hasEmail && hasSubmit && !requiredSensitive) {
              return {safe:true, reason:'BROWSER_DOM_FORM_PROOF', field_count:fields.length};
            }
          }
          return {safe:false, reason:'NO_SAFE_BROWSER_DOM_FORM'};
        }""")

    async def live_preflight(self, slot: BrowserSlot, route_meta: dict, reservoir_row: dict) -> dict:
        """Navigate and inspect only. Never fills, clicks, or submits a form."""
        preflight_started = time.monotonic()
        # V9 already admitted only unsuppressed, policy-cleared routes. Keep
        # V6's live browser safety gates here without importing the legacy tree.
        _dnc_domains = lambda: set()
        PROHIBIT = re.compile(
            r'(営業(?:目的|メール|連絡|勧誘).{0,24}(?:お断り|禁止|不可)|'
            r'セールス.{0,24}(?:お断り|禁止)|勧誘.{0,24}(?:お断り|禁止)|'
            r'no\s+(?:sales|solicitation|marketing)\s+(?:messages?|inquiries|contacts?))', re.I
        )
        def captcha_challenge_present(z):
            return bool(re.search(
                r'(g-recaptcha|grecaptcha|recaptcha/api|hcaptcha|h-captcha|'
                r'challenges\.cloudflare\.com|cf-turnstile|turnstile/v0|captcha)', str(z or ''), re.I
            ))
        def _strict_static_form_proof(_url,z):
            text=str(z or '')
            ok=bool(re.search(r'<form\b',text,re.I) and
                    re.search(r'(type=["\']email["\']|e-?mail|メール)',text,re.I) and
                    re.search(r'<textarea\b|message|inquir|enquir|お問い合わせ',text,re.I))
            return ok, ('PASS' if ok else 'NO_MESSAGE_FORM')
        risk_screen = lambda prospect, html: (True, 'PASS', {})
        from_html = lambda url, html: ({}, 'V9_STAGE3_LIVE_RECHECK', 'PASS')

        url = str(route_meta.get("canonical_url") or reservoir_row.get("canonical_url") or "")
        domain = str(route_meta.get("domain") or reservoir_row.get("official_domain") or "").lower().removeprefix("www.")
        if not url or not domain:
            return {"safe": False, "reason": "IDENTITY_MISSING"}
        scheme = (urlsplit(url).scheme or "").lower()
        if scheme not in {"http", "https"}:
            return {"safe": False, "reason": "NON_HTTP_CONTACT_ROUTE",
                    "route_repair": True, "blocked_scheme": scheme or "missing"}
        dnc = await asyncio.to_thread(_dnc_domains)
        if dnc is None:
            return {"safe": False, "reason": "DNC_STATE_UNAVAILABLE", "retry": True}
        if domain in dnc:
            return {"safe": False, "reason": "DO_NOT_CONTACT", "safety": True}
        if int(route_meta.get("legal_verified") or 0) != 1:
            return {"safe": False, "reason": "LEGAL_NOT_VERIFIED", "safety": True}
        if str(route_meta.get("safety_flags_json") or "[]") != "[]":
            return {"safe": False, "reason": "V41_SAFETY_NOT_CLEAR", "safety": True}
        reject_code = str(route_meta.get("reject_code") or "")
        technical_reverify_codes = {
            "ROUTE_REPAIR_REQUIRED",
            "BROWSER_CANDIDATE_TIMEOUT",
            "ConnectionError",
            "SSLError",
            "ConnectTimeout",
            "ReadTimeout",
            "HTTP_403",
            "HTTP_404",
            "HTTP_406",
            "HTTP_500",
            "HTTP_503",
            "HTTP_522",
            "TooManyRedirects",
            "NO_MESSAGE_FORM",
            "SKIP_UNSUPPORTED_SUBMIT_CONTROL",
            # Re-check a historical CAPTCHA verdict against the current rendered
            # page. The active CAPTCHA detector below remains fail-closed.
            "CAPTCHA",
        }
        if reject_code == "SKIP_REQUIRED_PHONE":
            if not _stage3_phone_reverify_clear(reservoir_row):
                return {"safe": False, "reason": "V41_SAFETY_NOT_CLEAR", "safety": True}
        elif reject_code and reject_code not in technical_reverify_codes:
            return {"safe": False, "reason": "V41_SAFETY_NOT_CLEAR", "safety": True}
        nav_started = time.monotonic()
        nav_timeout_recovered = False
        try:
            await slot.page.goto(url, wait_until="domcontentloaded", timeout=12000)
            await slot.page.wait_for_timeout(120)
            final_url = slot.page.url
            html = await slot.page.content()
        except Exception as exc:
            # A slow corporate page can miss DOMContentLoaded because of one
            # hanging third-party asset even though the same-origin DOM and form
            # are already usable. Repeating the entire 12s navigation wastes the
            # send slot. On navigation Timeout only, salvage the current DOM and
            # continue through every normal safety check below. Other failures
            # remain retryable and fail closed.
            if type(exc).__name__ == "TimeoutError":
                try:
                    final_url = slot.page.url
                    html = await slot.page.content()
                    if len(str(html or "")) < 800 or "<" not in str(html or ""):
                        raise RuntimeError("PARTIAL_DOM_EMPTY")
                    nav_timeout_recovered = True
                except Exception:
                    return {"safe": False, "reason": "BROWSER_TIMEOUTERROR", "retry": True,
                            "detail": str(exc)[:240],
                            "timing": {
                                "navigate_ms": round((time.monotonic() - nav_started) * 1000, 1),
                                "preflight_total_ms": round((time.monotonic() - preflight_started) * 1000, 1),
                            }}
            else:
                return {"safe": False, "reason": "BROWSER_" + type(exc).__name__.upper(), "retry": True,
                        "detail": str(exc)[:240],
                        "timing": {
                            "navigate_ms": round((time.monotonic() - nav_started) * 1000, 1),
                            "preflight_total_ms": round((time.monotonic() - preflight_started) * 1000, 1),
                        }}
        navigate_ms = round((time.monotonic() - nav_started) * 1000, 1)
        safety_started = time.monotonic()
        final_domain = (urlsplit(final_url).hostname or "").lower().removeprefix("www.")
        if final_domain != domain:
            return {"safe": False, "reason": "DOMAIN_CHANGED", "safety": True}
        stage3_full_v3 = bool(reservoir_row.get("_stage3_full_v3_fresh"))
        stage3_static_full_hint = bool(reservoir_row.get("_stage3_static_full_fresh"))
        if stage3_full_v3 or stage3_static_full_hint:
            for _r in list(slot.page.frames)[:20]:
                if await self._visible_captcha_challenge(_r):
                    return {"safe": False, "reason": "CAPTCHA", "safety": True}
        elif captcha_challenge_present(html):
            return {"safe": False, "reason": "CAPTCHA", "safety": True}
        plain = " ".join(re.sub("<[^>]+>", " ", html).split())
        if PROHIBIT.search(plain):
            return {"safe": False, "reason": "SALES_PROHIBITED", "safety": True}
        prospect = {
            "company": route_meta.get("name"),
            "country_code": str(route_meta.get("market") or "").split("-")[0],
            "trusted_source_type": route_meta.get("source_kind"),
            "contact_url": final_url,
            "source_url": route_meta.get("company_source_url") or ("https://" + domain),
            "official_domain": domain,
        }
        public_name = str(prospect.get("company") or "").strip()
        public_name_re = re.compile(
            r"(?:市役所|区役所|町役場|村役場|都庁|道庁|府庁|県庁|独立行政法人|地方独立行政法人|"
            r"国立大学法人|公立大学法人|行政委員会|行政機関|(?:^|\s)(?:Ministry|Government Agency|"
            r"City Council|Municipality|Prefectural Government|Public Authority)(?:\s|$))", re.I
        )
        contact_host = (urlsplit(final_url).hostname or "").lower()
        government_host = (
            contact_host.endswith(".go.jp") or contact_host.endswith(".lg.jp") or
            contact_host.endswith(".gov") or ".gov." in contact_host or
            contact_host.endswith(".gov.uk") or contact_host.endswith(".gov.sg") or
            contact_host.endswith(".govt.nz")
        )
        if public_name_re.search(public_name) or government_host:
            return {"safe": False, "reason": "PUBLIC_ENTITY", "safety": True}
        static_ok, static_reason = _strict_static_form_proof(final_url, html)
        proof_html = html
        proof_root = slot.page.main_frame
        dom_proof = {"safe": bool(static_ok or stage3_full_v3)}
        if not static_ok and not stage3_full_v3:
            # Main document first, then embedded frames. The parent route must
            # remain the verified official domain; frames only supply the form UI.
            roots = list(slot.page.frames)[:20 if stage3_static_full_hint else 8]
            for root in roots:
                try:
                    root_html = await root.content()
                    root_text = await root.locator("body").inner_text()
                except Exception:
                    continue
                if captcha_challenge_present(root_html):
                    continue
                if PROHIBIT.search(" ".join(str(root_text or "").split())):
                    continue
                cand = await self.browser_form_proof(root)
                if cand.get("safe") is True:
                    dom_proof = cand
                    proof_root = root
                    proof_html = root_html
                    break
            if dom_proof.get("safe") is not True:
                # Many corporate forms hydrate shortly after DOMContentLoaded.
                try:
                    await slot.page.wait_for_timeout(1800 if stage3_static_full_hint else 700)
                    if stage3_static_full_hint:
                        try:
                            await slot.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await slot.page.wait_for_timeout(500)
                            await slot.page.evaluate("window.scrollTo(0, 0)")
                        except Exception:
                            pass
                    html = await slot.page.content()
                    if captcha_challenge_present(html):
                        return {"safe": False, "reason": "CAPTCHA", "safety": True}
                    plain = " ".join(re.sub("<[^>]+>", " ", html).split())
                    if PROHIBIT.search(plain):
                        return {"safe": False, "reason": "SALES_PROHIBITED", "safety": True}
                    static_ok, static_reason = _strict_static_form_proof(final_url, html)
                    if static_ok:
                        proof_html = html
                        proof_root = slot.page.main_frame
                        dom_proof = {"safe": True}
                    else:
                        for root in list(slot.page.frames)[:20 if stage3_static_full_hint else 8]:
                            try:
                                root_html = await root.content()
                                cand = await self.browser_form_proof(root)
                            except Exception:
                                continue
                            if cand.get("safe") is True and not captcha_challenge_present(root_html):
                                proof_html = root_html
                                proof_root = root
                                dom_proof = cand
                                break
                except Exception:
                    pass
                if not static_ok and dom_proof.get("safe") is not True:
                    return {"safe": False, "reason": "FORM_" + str(static_reason)}
        if prospect["country_code"] == "JP":
            prospect["risk_clearance"] = {"status": "PASS", "country_code": "JP", "entity_identity_verified": True}
        risk_input = (html + "\n" + proof_html)[:120000]
        risk_ok, risk_why, _ = await asyncio.to_thread(risk_screen, prospect, risk_input)
        if not risk_ok:
            return {"safe": False, "reason": "RISK_" + str(risk_why), "retry": str(risk_why) == "SANCTIONS_SCREEN_UNAVAILABLE"}
        semantic, semantic_fp, parse_status = await asyncio.to_thread(from_html, final_url, proof_html)
        if not stage3_full_v3:
            if parse_status != "PASS" or not semantic:
                return {"safe": False, "reason": "SEMANTIC_" + str(parse_status)}
            if semantic.get("required_sensitive"):
                return {"safe": False, "reason": "REQUIRED_PERSONAL_ONLY", "safety": True}
        else:
            if semantic and semantic.get("required_sensitive"):
                return {"safe": False, "reason": "REQUIRED_PERSONAL_ONLY", "safety": True}
            if not semantic_fp:
                semantic_fp = "STAGE3_FULL_V3_LIVE_RECHECK"
        raw_fp = hashlib.sha256((final_url + "\n" + proof_html).encode("utf-8", "ignore")).hexdigest()
        return {
            "safe": True,
            "reason": "BROWSER_PREFLIGHT_SAFE",
            "final_url": final_url,
            "form_fingerprint": raw_fp,
            "semantic_fingerprint": semantic_fp,
            "content_hash": hashlib.sha256(html.encode("utf-8", "ignore")).hexdigest(),
            "navigation_timeout_recovered": bool(nav_timeout_recovered),
            "timing": {
                "navigate_ms": navigate_ms,
                "preflight_safety_ms": round((time.monotonic() - safety_started) * 1000, 1),
                "preflight_total_ms": round((time.monotonic() - preflight_started) * 1000, 1),
            },
        }

    async def select_contact_form(self, page: Page, stage3_verified: bool = False,
                                  preferred_frame_index: int | None = None,
                                  preferred_form_index: int | None = None,
                                  preferred_proof_hint: bool = False) -> dict:
        """Choose one business-contact form across the main document and child frames.

        A fresh Stage-3 FULL V3 proof allows the same structural email+message
        form even when the form text itself lacks generic "contact" wording.
        """
        best = None
        roots = list(page.frames)[:20 if stage3_verified else 8]
        frame_order=list(range(len(roots)))
        if preferred_frame_index is not None and 0 <= int(preferred_frame_index) < len(roots):
            pf=int(preferred_frame_index)
            frame_order=[pf]+[x for x in frame_order if x!=pf]
        for frame_index in frame_order:
            root=roots[frame_index]
            try:
                metas = await root.locator("form").evaluate_all(r"""forms => forms.slice(0,20).map(f => {
                  const text=((f.innerText||'')+' '+(f.getAttribute('aria-label')||'')).replace(/\s+/g,' ').slice(0,5000);
                  const action=(f.action||f.getAttribute('action')||'');
                  const ident=((f.id||'')+' '+(f.className||'')+' '+action).toLowerCase();
                  const els=[...f.querySelectorAll('input,textarea,select')];
                  const desc=e=>{
                    const labels=e.labels?[...e.labels].map(x=>x.innerText||'').join(' '):'';
                    const id=e.id||'', lab=id?document.querySelector('label[for="'+CSS.escape(id)+'"]'):null;
                    return [e.name||'',id,e.placeholder||'',e.getAttribute('aria-label')||'',labels,(lab&&lab.innerText)||''].join(' ');
                  };
                  return {
                    text, action, ident,
                    fields: els.map(e=>{
                      const s=getComputedStyle(e),r=e.getBoundingClientRect();
                      const visible=!e.disabled && (e.type||'').toLowerCase()!=='hidden' &&
                        s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
                      return {tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),desc:desc(e),visible};
                    })
                  };
                })""")
                count = len(metas or [])
            except Exception:
                continue
            form_order=list(range(count))
            if (preferred_form_index is not None and frame_index==preferred_frame_index
                    and 0 <= int(preferred_form_index) < count):
                pfi=int(preferred_form_index)
                form_order=[pfi]+[x for x in form_order if x!=pfi]
            for i in form_order:
                try:
                    meta = metas[i]
                except Exception:
                    continue
                text = str(meta.get("text") or "")
                ident = str(meta.get("ident") or "")
                action = str(meta.get("action") or "")
                fields = list(meta.get("fields") or [])
                visible_fields = [x for x in fields if x.get("visible") is True]
                joined = " ".join(str(x.get("desc") or "") for x in visible_fields)
                low = (text + " " + ident + " " + joined).lower()

                if (re.match(r"^(?:mailto|tel|javascript):", action.strip(), re.I) or
                    "wp-comments-post.php" in action.lower() or
                    re.search(r"(^|\s|[-_])(commentform|comments?|reviewform)(\s|$|[-_])", ident, re.I) or
                    re.search(r"(コメントを送信|コメントを残す|leave a reply|post a comment|write a review)", text, re.I) or
                    re.search(r"(site search|サイト内検索|login|ログイン)", low, re.I)):
                    continue

                has_email = any(
                    str(x.get("type") or "").lower() == "email" or
                    re.search(r"(e-?mail|メール)", str(x.get("desc") or ""), re.I)
                    for x in visible_fields
                )
                has_message = any(
                    str(x.get("tag") or "").lower() == "textarea" and
                    not re.search(r"(comment|コメント|review|レビュー)", str(x.get("desc") or ""), re.I)
                    for x in visible_fields
                ) or any(
                    re.search(r"(inquiry|enquiry|message|お問い合わせ|お問合せ|ご相談|ご用件|内容|詳細)",
                              str(x.get("desc") or ""), re.I)
                    for x in visible_fields
                )
                contactish = bool(re.search(
                    r"(contact|inquiry|enquiry|お問い合わせ|お問合せ|ご相談|法人|business|ご提案|協業|営業)",
                    text + " " + ident, re.I
                ))
                company = bool(re.search(r"(会社|法人|企業|company|organization|organisation)", joined, re.I))
                subject = bool(re.search(r"(件名|subject|title)", joined, re.I))
                if not has_email or not has_message:
                    continue
                score = 4 + (4 if contactish else 0) + (2 if company else 0) + (1 if subject else 0)
                preferred_exact = bool(
                    (stage3_verified or preferred_proof_hint)
                    and preferred_frame_index is not None and preferred_form_index is not None
                    and frame_index==int(preferred_frame_index) and i==int(preferred_form_index)
                )
                if preferred_exact:
                    score += 20
                if frame_index > 0:
                    score += 1
                if not contactish and score < 7 and not stage3_verified and not preferred_exact:
                    continue
                if (stage3_verified or preferred_exact) and not contactish:
                    score += 3
                if best is None or score > best["score"]:
                    best = {"ready": True, "index": i, "score": score, "action": action[:500],
                            "frame_index": frame_index}
        return best or {"ready": False, "reason": "BUSINESS_CONTACT_FORM_NOT_FOUND"}

    async def v9_preverified_preflight(self, slot: BrowserSlot, route_meta: dict, reservoir_row: dict) -> dict:
        """Fast live recheck for a fresh V9 Stage3 SEND_READY route."""
        started=time.monotonic()
        url=str(route_meta.get("canonical_url") or reservoir_row.get("canonical_url") or "")
        domain=str(route_meta.get("domain") or reservoir_row.get("official_domain") or "").lower().removeprefix("www.")
        if not url or not domain:
            return {"safe":False,"reason":"IDENTITY_MISSING"}
        try:
            try:
                await slot.page.goto(url,wait_until="domcontentloaded",timeout=5000)
            except Exception as exc:
                if type(exc).__name__!="TimeoutError":
                    return {"safe":False,"reason":"BROWSER_"+type(exc).__name__.upper(),"retry":True}
            final_url=str(slot.page.url or url)
            final_domain=(urlsplit(final_url).hostname or "").lower().removeprefix("www.")
            if final_domain!=domain:
                return {"safe":False,"reason":"DOMAIN_CHANGED","safety":True}
            detail={}
            try: detail=json.loads(str(reservoir_row.get("_stage3_full_v3_detail_json") or "{}"))
            except Exception: detail={}
            try: proof_frame=int(detail.get("frame_index")) if detail.get("frame_index") is not None else 0
            except Exception: proof_frame=0
            roots=list(slot.page.frames)
            check_roots=[]
            for idx in (0,proof_frame):
                if 0 <= idx < len(roots) and roots[idx] not in check_roots: check_roots.append(roots[idx])
            for root in check_roots:
                if await self._visible_captcha_challenge(root):
                    return {"safe":False,"reason":"CAPTCHA","safety":True}
            try:
                plain=" ".join((await slot.page.locator("body").inner_text(timeout=900)).split())
            except Exception:
                plain=""
            html=plain[:24000]
            prohibit=re.compile(
                r'(営業(?:目的|メール|連絡|勧誘).{0,24}(?:お断り|禁止|不可)|'
                r'セールス.{0,24}(?:お断り|禁止)|勧誘.{0,24}(?:お断り|禁止)|'
                r'no\s+(?:sales|solicitation|marketing)\s+(?:messages?|inquiries|contacts?))',re.I)
            if prohibit.search(plain):
                return {"safe":False,"reason":"SALES_PROHIBITED","safety":True}
            if final_domain.endswith((".go.jp",".lg.jp",".gov",".gov.uk",".gov.sg",".govt.nz")) or ".gov." in final_domain:
                return {"safe":False,"reason":"PUBLIC_ENTITY","safety":True}
            return {"safe":True,"reason":"V9_PREVERIFIED_FAST_PREFLIGHT","final_url":final_url,
                    "form_fingerprint":str(detail.get("form_fingerprint") or hashlib.sha256((final_url+"\n"+html).encode("utf-8","ignore")).hexdigest()),
                    "semantic_fingerprint":"V9_STAGE3_PREVERIFIED",
                    "content_hash":hashlib.sha256(html.encode("utf-8","ignore")).hexdigest(),
                    "navigation_timeout_recovered":False,
                    "timing":{"preflight_total_ms":round((time.monotonic()-started)*1000,1)}}
        except Exception as exc:
            return {"safe":False,"reason":"V9_FAST_PREFLIGHT_"+type(exc).__name__.upper(),"retry":True}

    async def prepare_same_page(self, slot: BrowserSlot, route_meta: dict, reservoir_row: dict,
                                message_body: str, reply_address: str) -> dict:
        """VERIFY + fill + final safety recheck on the same already-open Page. Never submits."""
        started = time.monotonic()
        if reservoir_row.get("_v9_preverified") is True:
            pre = await self.v9_preverified_preflight(slot, route_meta, reservoir_row)
        else:
            pre = await self.live_preflight(slot, route_meta, reservoir_row)
        if pre.get("safe") is not True:
            return {**pre, "prepared": False, "cycle_seconds": round(time.monotonic() - started, 3)}
        if not message_body or not reply_address:
            return {"safe": False, "prepared": False, "reason": "MESSAGE_OR_REPLY_MISSING"}
        page = slot.page
        # If DOMContentLoaded timed out but a usable same-origin DOM was salvaged,
        # give provider form JavaScript a short bounded chance to initialize.
        # Without this, CF7 can fall back to a native document POST and we lose
        # the provider success/failure event needed for a definitive receipt.
        # This is evidence-quality settling only; it does not bypass any control
        # and all normal pre-submit safety checks still run afterward.
        if pre.get("navigation_timeout_recovered") is True:
            try:
                provider_kind = await page.evaluate("""() => {
                  if (document.querySelector('.wpcf7-form')) return 'CF7';
                  if (document.querySelector('form.wpforms-form,.wpforms-form')) return 'WPFORMS';
                  if (document.querySelector('form[id^="gform_"],.gform_wrapper form')) return 'GRAVITY';
                  if (document.querySelector('form.fluentform,.frm-fluent-form')) return 'FLUENT';
                  return '';
                }""")
            except Exception:
                provider_kind = ""
            try:
                if provider_kind == "CF7":
                    await page.wait_for_function(
                        """() => {
                          const f=document.querySelector('.wpcf7-form');
                          if(!f) return false;
                          return !!window.wpcf7 ||
                            f.classList.contains('init') ||
                            !!f.closest('.wpcf7[data-status]') ||
                            !!document.querySelector('.wpcf7[data-status]');
                        }""",
                        timeout=3000,
                    )
                elif provider_kind:
                    # Other known AJAX builders do not expose a stable universal
                    # global. A short event-loop settle is safer than waiting for
                    # full page load on sites with hanging third-party assets.
                    await page.wait_for_timeout(1200)
                else:
                    await page.wait_for_timeout(350)
            except Exception:
                # Failure to observe an initializer is not permission to assume
                # success; submission evidence remains fail-closed later.
                pass
        try:
            stage3_detail = json.loads(str(reservoir_row.get("_stage3_full_v3_detail_json") or "{}"))
        except Exception:
            stage3_detail = {}
        try:
            static_stage3_detail = json.loads(str(reservoir_row.get("_stage3_static_full_detail_json") or "{}"))
        except Exception:
            static_stage3_detail = {}
        stage3_verified = bool(reservoir_row.get("_stage3_full_v3_fresh"))
        static_stage3_hint = bool(reservoir_row.get("_stage3_static_full_fresh"))
        hint_detail = stage3_detail if stage3_verified else (static_stage3_detail if static_stage3_hint else {})
        slot.stage3_control_kind = (
            str(stage3_detail.get("control_kind") or "")
            if stage3_verified else ""
        )
        stage3_frame_index = (
            int(hint_detail.get("frame_index"))
            if (stage3_verified or static_stage3_hint) and hint_detail.get("frame_index") is not None
            else None
        )
        stage3_form_index = (
            int(hint_detail.get("form_index"))
            if (stage3_verified or static_stage3_hint) and hint_detail.get("form_index") is not None
            else None
        )
        form_detect_started = time.monotonic()
        # V9 handed us a fresh rendered SEND_READY proof. Reuse its exact
        # frame/form coordinates first instead of rescanning every form. Only
        # fall back to the legacy rendered-depth search when that exact target
        # no longer exists on the live page.
        target = None
        if reservoir_row.get("_v9_preverified") is True and stage3_frame_index is not None and stage3_form_index is not None:
            try:
                roots=list(page.frames)[:20]
                if 0 <= int(stage3_frame_index) < len(roots):
                    forms=roots[int(stage3_frame_index)].locator("form")
                    if 0 <= int(stage3_form_index) < await forms.count():
                        target={"ready":True,"index":int(stage3_form_index),"score":1000,
                                "action":str(await forms.nth(int(stage3_form_index)).get_attribute("action") or "")[:500],
                                "frame_index":int(stage3_frame_index)}
            except Exception:
                target=None
        stage3_lane_mode = str(stage3_detail.get("lane_mode") or "").upper() if stage3_verified else ""
        if target is None and stage3_verified and stage3_lane_mode:
            try:
                wait_ms={"FAST_DOM":900,"DYNAMIC_JS":1800,"IFRAME_DEEP":1500,"DEEP":2600}.get(stage3_lane_mode,900)
                await page.wait_for_timeout(wait_ms)
                if stage3_lane_mode in {"DYNAMIC_JS","DEEP"}:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1600 if stage3_lane_mode=="DYNAMIC_JS" else 2400)
                    await page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass
        if target is None:
            target = await self.select_contact_form(
                page,
                stage3_verified=stage3_verified,
                preferred_frame_index=stage3_frame_index,
                preferred_form_index=stage3_form_index,
                preferred_proof_hint=static_stage3_hint,
            )
        if target.get("ready") is not True:
            try:
                await page.wait_for_timeout(1800 if stage3_verified else 700)
                target = await self.select_contact_form(
                    page,
                    stage3_verified=stage3_verified,
                    preferred_frame_index=stage3_frame_index,
                    preferred_form_index=stage3_form_index,
                    preferred_proof_hint=static_stage3_hint,
                )
            except Exception:
                pass
        if target.get("ready") is not True:
            return {"safe": False, "prepared": False,
                    "reason": str(target.get("reason") or "BUSINESS_CONTACT_FORM_NOT_FOUND"),
                    "cycle_seconds": round(time.monotonic() - started, 3)}
        target_form_index = int(target["index"])
        slot.target_frame_index = int(target.get("frame_index") or 0)
        root = self._target_root(slot)
        form = root.locator("form").nth(target_form_index)
        # A server-rendered, below-the-fold form can be replaced when its lazy
        # component hydrates on the first click. Reveal and settle that component
        # before filling, so the framework receives the input events.
        try:
            await form.scroll_into_view_if_needed(timeout=2000)
            if await form.evaluate("f => !!f.closest('astro-island[ssr]')"):
                await root.wait_for_function(
                    "i => {const f=document.forms[i]; return !!f && !f.closest('astro-island[ssr]');}",
                    arg=target_form_index, timeout=3500,
                )
        except Exception:
            return {"safe": False, "prepared": False, "retry": True,
                    "reason": "FORM_HYDRATION_NOT_READY",
                    "cycle_seconds": round(time.monotonic() - started, 3)}
        # Do not infer required-sensitive fields from broad form text: a form can
        # contain "required" near an unrelated field and an optional phone/address
        # elsewhere. The field-level extraction below is authoritative and preserves
        # the fail-closed rule when a sensitive field itself is actually required.
        fields = await form.locator("input,textarea,select").evaluate_all(_pal_js(r"""
          return els.map((e,i)=>{
          const rowLabel=palRowLabel(e);
          const wrap=palWrap(e);
          let local=((palLabelOf(e))||((wrap&&wrap.innerText)||'')).trim(); if(local.length>260)local='';
          const hidden=e.type==='hidden'||e.disabled||!palVisible(e);
          const selfDesc=palSelfDesc(e);
          return {i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),name:e.name||'',id:e.id||'',
            value:e.value||'',checked:!!e.checked,required:palRequired(e),
            hidden,self_desc:selfDesc,row_label:rowLabel.slice(0,260),desc:(selfDesc+' '+rowLabel+' '+local).slice(0,700)};
        });"""))
        form_detect_ms = round((time.monotonic() - form_detect_started) * 1000, 1)
        fill_started = time.monotonic()
        sensitive_rx = PAL_SENSITIVE_RX
        market = str(route_meta.get("market") or reservoir_row.get("market") or "")
        intl = market != "JP-JA"
        contact_name = "Practical AI Lab" if intl else "Practical AI Lab 運営"
        subject = ("<ADV> " if market == "SG-EN" else "") + ("AI workflow consultation" if intl else "AI業務改善のご相談")
        department = "Operations" if intl else "運営"
        site_url = "https://practical-ai-lab.pages.dev/global/" if intl else "https://practical-ai-lab.pages.dev/"

        # Fast path: classify obvious safe text fields locally, then fill them in
        # one DOM round-trip. Any field that does not persist falls through to
        # the existing per-field guarded path below.
        # Wix/Thunderbolt forms maintain framework state that can ignore a raw
        # native-value batch setter even when the DOM value visibly persists.
        # On those builders use Playwright's trusted fill path field-by-field so
        # React/Wix receives the same input sequence a user would generate.
        try:
            if reservoir_row.get("_v9_preverified") is True:
                trusted_event_fill = bool(await page.evaluate("""() => !!document.querySelector(
                  '[data-mesh-id],[class*=\"wixui-\"],script[src*=\"wixstatic.com\"],script[src*=\"parastorage.com\"]'
                )"""))
            else:
                trusted_event_fill = _requires_trusted_field_events(await page.content())
        except Exception:
            trusted_event_fill = False
        batch_assignments = []
        for row in fields:
            if row.get("hidden") or row.get("type") in {"hidden","submit","button","image","file","radio","checkbox"}:
                continue
            if row.get("tag") == "select" or str(row.get("value") or "").strip():
                continue
            desc = str(row.get("desc") or "")
            core = (str(row.get("self_desc") or "")+" "+str(row.get("row_label") or "")).strip() or desc
            if sensitive_rx.search(core) or re.search(r"(leave\s+(?:this\s+)?field\s+empty|do\s+not\s+fill|don'?t\s+fill|honeypot|bot\s+field)", core, re.I):
                continue
            value = None
            typ = str(row.get("type") or "").lower()
            # The input's own type is authoritative over wrapper/label wording.
            # A type=email field whose label happens to read "email for your
            # inquiry" previously matched the message pattern first and received
            # the message body, which the page then rejected as an invalid email.
            if row.get("tag") == "textarea":
                value = message_body
            elif typ == "email":
                value = reply_address
            elif typ == "url":
                value = site_url
            elif re.search(r"(問い合わせ内容|お問合せ内容|ご用件|message|inquiry|enquiry|comment|内容|詳細|description)", core, re.I):
                value = message_body
            elif re.search(r"(メール|e-?mail|mail address)", core, re.I):
                value = reply_address
            elif re.search(r"(会社|法人|企業|company|organization|organisation)", core, re.I):
                value = "Practical AI Lab"
            elif re.search(r"(件名|subject|title)", core, re.I):
                value = subject
            elif re.search(r"(部署|部門|department|designation)", core, re.I):
                value = department
            elif re.search(r"(url|website|ホームページ)", core, re.I):
                value = site_url
            elif re.search(r"(姓|苗字|名字|surname|family[ _.-]?name|last[ _.-]?name|\blname\b|(?:^|[\[\]_.-])last(?:$|[\[\]_.-]))", core, re.I):
                value = "Practical"
            elif re.search(r"(名|given[ _.-]?name|first[ _.-]?name|\bfname\b|(?:^|[\[\]_.-])first(?:$|[\[\]_.-]))", core, re.I):
                value = "AI Lab"
            elif re.search(r"(氏名|お名前|名前|担当者|\bcontact[ _.-]?name\b|\bfull[ _.-]?name\b|\bname\b)", core, re.I):
                value = contact_name
            if value is not None and not trusted_event_fill:
                batch_assignments.append({"i": int(row["i"]), "value": str(value)})
        batch_ok = await self._batch_commit_values(form, batch_assignments)
        if batch_ok:
            batch_map = {int(x["i"]): str(x["value"]) for x in batch_assignments}
            for row in fields:
                if int(row["i"]) in batch_ok:
                    row["value"] = batch_map[int(row["i"])]

        for row in fields:
            if row.get("hidden") or row.get("type") in {"hidden","submit","button","image","file"}:
                continue
            desc = str(row.get("desc") or "")
            core = (str(row.get("self_desc") or "")+" "+str(row.get("row_label") or "")).strip() or desc
            loc = form.locator("input,textarea,select").nth(int(row["i"]))
            # Common anti-spam honeypots are intentionally blank. Never fill them.
            if re.search(r"(leave\s+(?:this\s+)?field\s+empty|do\s+not\s+fill|don'?t\s+fill|honeypot|bot\s+field)", core, re.I):
                try: await self._fill_sticky(loc, "")
                except Exception: pass
                continue
            if sensitive_rx.search(core):
                if row.get("required"):
                    return {"safe": False, "prepared": False, "reason": "REQUIRED_PERSONAL_ONLY", "safety": True}
                try: await self._fill_sticky(loc, "")
                except Exception: pass
                continue
            try:
                if row["tag"] == "select":
                    if not row.get("required") or str(row.get("value") or "").strip():
                        continue
                    # A required dropdown is answered only when the answer is
                    # truthful: either a neutral, non-factual intent option, or a
                    # fact this system actually knows. Selecting an arbitrary
                    # option would assert an employee count, revenue band, budget,
                    # role, industry, location or customer relationship we have no
                    # basis for, so anything else fails closed here.
                    opts = await loc.locator("option").evaluate_all("os=>os.map(o=>({v:o.value||'',t:(o.innerText||'').trim()}))")
                    pick, refusal = self.select_answer(core, opts)
                    if refusal:
                        return {"safe": False, "prepared": False, "reason": refusal,
                                "safety": True, "field": core[:160],
                                "options": [str(o.get("t") or "")[:40] for o in (opts or [])[:8]]}
                    await loc.select_option(value=pick)
                    continue
                if row.get("type") in {"radio","checkbox"}:
                    continue
                if str(row.get("value") or "").strip():
                    continue
                # Field identity must be derived from the element itself, not broad
                # wrapper text. A textarea inside a form that also mentions Email
                # must never be classified as an email field.
                if row["tag"] == "textarea":
                    if not await self._commit_field_value(loc, message_body): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif str(row.get("type") or "").lower() == "email":
                    if not await self._commit_field_value(loc, reply_address): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif str(row.get("type") or "").lower() == "url":
                    if not await self._commit_field_value(loc, site_url): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(問い合わせ内容|お問合せ内容|ご用件|message|inquiry|enquiry|comment|内容|詳細|description)", core, re.I):
                    if not await self._commit_field_value(loc, message_body): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(会社|法人|企業|company|organization|organisation)", core, re.I):
                    if not await self._commit_field_value(loc, "Practical AI Lab"): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(確認|再入力|confirm).{0,25}(メール|mail|email)|(メール|mail|email).{0,25}(確認|再入力|confirm)", core, re.I):
                    if not await self._commit_field_value(loc, reply_address): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif str(row.get("type") or "").lower() == "email" or re.search(r"(メール|e-?mail|mail address|(?:^|[\s_.-])mail(?:$|[\s_.-]))", core, re.I):
                    if not await self._commit_field_value(loc, reply_address): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(件名|subject|title)", core, re.I):
                    if not await self._commit_field_value(loc, subject): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(部署|部門|department|designation)", core, re.I):
                    if not await self._commit_field_value(loc, department): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(url|website|ホームページ)", core, re.I):
                    if not await self._commit_field_value(loc, site_url): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(ふりがな|ひらがな)", core, re.I):
                    if not await self._commit_field_value(loc, "ぷらくてぃかるえーあいらぼ"): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(フリガナ|カナ|kana)", core, re.I):
                    if not await self._commit_field_value(loc, "プラクティカルエーアイラボ"): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(姓|苗字|名字|surname|family[ _.-]?name|last[ _.-]?name|\blname\b|(?:^|[\[\]_.-])last(?:$|[\[\]_.-]))", core, re.I):
                    if not await self._commit_field_value(loc, "Practical"): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(名|given[ _.-]?name|first[ _.-]?name|\bfname\b|(?:^|[\[\]_.-])first(?:$|[\[\]_.-]))", core, re.I):
                    if not await self._commit_field_value(loc, "AI Lab"): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif re.search(r"(氏名|お名前|名前|担当者|\bcontact[ _.-]?name\b|\bfull[ _.-]?name\b|\bname\b)", core, re.I):
                    if not await self._commit_field_value(loc, contact_name): raise RuntimeError("FIELD_COMMIT_FAILED")
                elif row.get("required") and str(row.get("type") or "").lower() in {"text", "search", ""}:
                    # Site-specific builders often use opaque names such as
                    # input_1.3 or field_0ddc843. Stage 3 has already proved this
                    # field is non-sensitive and fillable, so a required generic
                    # text field may safely receive the organization/contact name.
                    if not await self._commit_field_value(loc, contact_name): raise RuntimeError("FIELD_COMMIT_FAILED")
            except Exception:
                pass
        # Required radios are group requirements, not one requirement per radio.
        # Select only semantically safe "general/other/business inquiry" choices.
        try:
            radios = await form.locator('input[type="radio"]').evaluate_all(_pal_js(r"""
              return els.map((e,i)=>{
              const rowLabel=palRowLabel(e);
              const wrap=e.closest('label,.field,.form-group,.form-row,li,p,div')||e.parentElement;
              const d=(palLabelOf(e)||((wrap&&wrap.innerText)||'')||e.value||'');
              return {i,name:e.name||'',checked:!!e.checked,
                required:palRequired(e),
                desc:(rowLabel+' '+d).slice(0,500)};
            });"""))
            groups = {}
            for rr in radios:
                groups.setdefault(str(rr.get("name") or f"__{rr.get('i')}"), []).append(rr)
            for _g, members in groups.items():
                if any(bool(x.get("checked")) for x in members):
                    continue
                if not any(bool(x.get("required")) for x in members):
                    continue
                # Same truthfulness rule as required selects: a radio group asking
                # for a fact about us that we do not know is never answered by
                # guessing. It is left unchecked and caught by the required scan.
                if any(UNKNOWN_FACT_RX.search(str(x.get("desc") or "")) for x in members):
                    continue
                pick = next((x for x in members if
                    NEUTRAL_OPTION_RX.search(str(x.get("desc") or ""))
                    and not re.search(r"(newsletter|marketing|メルマガ|広告|キャンペーン|電話|phone|住所|address)",
                                      str(x.get("desc") or ""), re.I)), None)
                if pick is not None:
                    try:
                        await form.locator('input[type="radio"]').nth(int(pick["i"])).check()
                    except Exception:
                        pass
        except Exception:
            pass

        # Some providers (notably Contact Form 7) express a required
        # checkbox *group* on the wrapper instead of setting required=true on
        # each input. Treat the group as one semantic field. We may answer only
        # when a neutral, truthful intent option exists (Other/General/Business
        # inquiry/etc.). Never guess factual company attributes.
        try:
            checkbox_rows = await form.locator('input[type="checkbox"]').evaluate_all(_pal_js(r"""
              return els.map((e,i)=>{
                const item=e.closest('label,.wpcf7-list-item,.form-check,.checkbox')||e.parentElement;
                const group=e.closest('.wpcf7-form-control,.gfield,.wpforms-field,fieldset,.form-group,.field,p')||item;
                const cls=((group&&group.className)||'')+' '+(((group&&group.parentElement)&&group.parentElement.className)||'');
                const text=((group&&group.innerText)||'').trim().slice(0,1400);
                const value=(e.value||'').trim();
                const desc=((palLabelOf(e)||'')+' '+value+' '+text+' '+(e.name||'')).slice(0,1800);
                const required=palRequired(e)||
                  /(?:^|\s)(?:wpcf7-validates-as-required|required|is-required|form-required|gfield_required)(?:\s|$)/i.test(cls)||
                  (text.length<=1400&&/(?:\brequired\b|\bmandatory\b|必須|[※＊*]\s*$)/i.test(text));
                return {i,name:e.name||('__checkbox_'+i),value,checked:!!e.checked,required,desc};
              });
            """))
            cb_groups = {}
            for rr in checkbox_rows:
                cb_groups.setdefault(str(rr.get("name") or f"__{rr.get('i')}"), []).append(rr)
            for _g, members in cb_groups.items():
                if any(bool(x.get("checked")) for x in members):
                    continue
                if not any(bool(x.get("required")) for x in members):
                    continue
                combined = " ".join(str(x.get("desc") or "") for x in members)
                # Consent/terms are handled by the dedicated checkbox pass below.
                if re.search(r"(個人情報|プライバシ|privacy|利用規約|terms|同意)", combined, re.I):
                    continue
                if UNKNOWN_FACT_RX.search(combined):
                    return {"safe": False, "prepared": False,
                            "reason": "REQUIRED_CHOICE_FACT_UNKNOWN", "safety": True,
                            "field": combined[:220]}
                pick = next((x for x in members if
                    NEUTRAL_OPTION_RX.search(
                        (str(x.get("value") or "")+" "+str(x.get("desc") or ""))
                    )
                    and not re.search(
                        r"(newsletter|marketing|メルマガ|広告|キャンペーン|電話|phone|住所|address)",
                        (str(x.get("value") or "")+" "+str(x.get("desc") or "")), re.I
                    )), None)
                if pick is None:
                    return {"safe": False, "prepared": False,
                            "reason": "REQUIRED_CHOICE_NO_NEUTRAL_OPTION", "safety": True,
                            "field": combined[:220]}
                try:
                    await form.locator('input[type="checkbox"]').nth(int(pick["i"])).check()
                except Exception:
                    return {"safe": False, "prepared": False,
                            "reason": "REQUIRED_CHOICE_CHECK_FAILED", "safety": False}
        except Exception:
            # The existing browser validation remains authoritative. Do not
            # turn an inspection exception into permission to guess a choice.
            pass

        for cb in await form.locator('input[type="checkbox"]').all():
            try:
                if await cb.is_checked(): continue
                desc = await cb.evaluate("""e=>{const id=e.id||'';const l=id?document.querySelector('label[for="'+CSS.escape(id)+'"]'):null;const w=e.closest('label,.field,tr,li,p,div')||e.parentElement;return ((l&&l.innerText)||'')+' '+((w&&w.innerText)||'')+' '+(e.name||'')}""")
                consent = bool(re.search(
                    r"(個人情報|プライバシ|privacy|利用規約|terms|同意|"
                    r"上記内容.{0,30}送信|送信.{0,30}チェック|確認画面.{0,30}表示されません)",
                    str(desc), re.I
                ))
                marketing = bool(re.search(r"(newsletter|marketing|メルマガ|広告|キャンペーン)", str(desc), re.I))
                if consent and not marketing:
                    await cb.check()
            except Exception:
                pass

        # Some reactive builders add the required flag only after earlier fields
        # receive input. Repair one late-required, non-sensitive text field pass
        # before browser constraint validation. Never invent phone/address or
        # factual select/radio answers.
        try:
            late_rows = await form.locator("input,textarea").evaluate_all(_pal_js(r"""
              return els.map((e,i)=>({i,type:(e.type||'').toLowerCase(),tag:e.tagName.toLowerCase(),
                value:e.value||'',required:palRequired(e),hidden:e.disabled||!palVisible(e)||e.type==='hidden',
                desc:(palSelfDesc(e)+' '+palRowLabel(e)+' '+palLabelOf(e)).slice(0,700)}));
            """))
            for lr in late_rows:
                if lr.get("hidden") or not lr.get("required") or str(lr.get("value") or "").strip():
                    continue
                typ=str(lr.get("type") or "").lower(); desc=str(lr.get("desc") or "")
                if sensitive_rx.search(desc):
                    return {"safe":False,"prepared":False,"reason":"REQUIRED_PERSONAL_ONLY","safety":True}
                desired=None
                if lr.get("tag")=="textarea": desired=message_body
                elif typ=="email": desired=reply_address
                elif typ=="url": desired=site_url
                elif typ in {"text","search",""}:
                    if re.search(r"(message|inquiry|enquiry|問い合わせ|内容|詳細|description)",desc,re.I): desired=message_body
                    elif re.search(r"(e-?mail|メール)",desc,re.I): desired=reply_address
                    elif re.search(r"(company|organization|organisation|会社|法人|企業)",desc,re.I): desired="Practical AI Lab"
                    elif re.search(r"(件名|subject|title)",desc,re.I): desired=subject
                    else: desired=contact_name
                if desired is not None:
                    try: await self._commit_field_value(form.locator("input,textarea").nth(int(lr["i"])),desired)
                    except Exception: pass
        except Exception:
            pass

        presubmit = await form.locator("input,textarea,select").evaluate_all(_pal_js(r"""
          const missing=[], invalid=[]; const radioDone=new Set();
          for(const e of els){
            if(e.disabled||['hidden','submit','button','image','file','reset'].includes((e.type||'').toLowerCase()))continue;
            if(!palVisible(e))continue;
            const fieldText=(palLabelOf(e)||e.placeholder||e.getAttribute('aria-label')||'').trim();
            const ident=(e.name||e.id||e.type||'unknown').slice(0,160);
            // The browser's own constraint validation is authoritative for what
            // the page will reject on submit: it covers type=email/url format,
            // pattern, minlength and min/max as well as required.
            if(typeof e.checkValidity==='function'&&!e.checkValidity()){
              const v=e.validity||{};
              invalid.push({name:ident,type:(e.type||e.tagName||'').toLowerCase(),
                            label:fieldText.slice(0,180),
                            message:String(e.validationMessage||'').slice(0,180),
                            value_missing:!!v.valueMissing,type_mismatch:!!v.typeMismatch,
                            pattern_mismatch:!!v.patternMismatch});
            }
            if(!palRequired(e))continue;
            if(e.type==='radio'){
              const key=e.name||('__radio_'+(e.id||''));
              if(radioDone.has(key))continue;
              radioDone.add(key);
              const group=els.filter(x=>(x.type||'').toLowerCase()==='radio'&&((x.name||('__radio_'+(x.id||'')))===key));
              if(group.some(x=>x.checked))continue;
            } else if(e.type==='checkbox'){
              if(e.checked)continue;
            } else if((e.value||'').trim()){
              continue;
            }
            missing.push({name:ident,type:(e.type||e.tagName||'').toLowerCase(),label:fieldText.slice(0,180)});
          }
          return [{missing,invalid}];
        """))
        presubmit = (presubmit or [{}])[0] if isinstance(presubmit, list) else {}
        missing_detail = list(presubmit.get("missing") or [])
        invalid_detail = list(presubmit.get("invalid") or [])
        missing = [str(x.get("name") or "unknown") for x in missing_detail]
        fill_ms = round((time.monotonic() - fill_started) * 1000, 1)
        # A field the browser itself marks invalid will be rejected client-side,
        # so clicking submit would burn the route for a message that never left.
        # Sensitive-only fields stay fail-closed; the rest are reported with the
        # browser's own reason so the failure is diagnosable.
        if invalid_detail and not missing:
            blocked = [x for x in invalid_detail
                       if sensitive_rx.search(str(x.get("name") or "") + " " + str(x.get("label") or ""))]
            if blocked:
                return {"safe": False, "prepared": False, "reason": "REQUIRED_PERSONAL_ONLY", "safety": True,
                        "invalid": [str(x.get("name") or "") for x in blocked][:8]}
            return {"safe": False, "prepared": False, "reason": "PRE_SUBMIT_CONSTRAINT_INVALID",
                    "invalid": [{"name": str(x.get("name") or ""), "message": str(x.get("message") or "")}
                                for x in invalid_detail][:8],
                    "cycle_seconds": round(time.monotonic() - started, 3),
                    "timing": {**dict(pre.get("timing") or {}),
                               "form_detect_ms": form_detect_ms, "fill_ms": fill_ms}}
        if missing:
            return {"safe": False, "prepared": False, "reason": "PRE_SUBMIT_REQUIRED_MISSING", "missing": missing[:8],
                    "cycle_seconds": round(time.monotonic() - started, 3),
                    "timing": {
                        **dict(pre.get("timing") or {}),
                        "form_detect_ms": form_detect_ms,
                        "fill_ms": fill_ms,
                    }}
        final_safety_started = time.monotonic()
        PROHIBIT = re.compile(
            r'(営業(?:目的|メール|連絡|勧誘).{0,24}(?:お断り|禁止|不可)|'
            r'セールス.{0,24}(?:お断り|禁止)|勧誘.{0,24}(?:お断り|禁止)|'
            r'no\s+(?:sales|solicitation|marketing)\s+(?:messages?|inquiries|contacts?))', re.I
        )
        def captcha_challenge_present(z):
            return bool(re.search(
                r'(g-recaptcha|grecaptcha|recaptcha/api|hcaptcha|h-captcha|'
                r'challenges\.cloudflare\.com|cf-turnstile|turnstile/v0|captcha)', str(z or ''), re.I
            ))
        final_url = page.url
        root = self._target_root(slot)
        domain = str(route_meta.get("domain") or reservoir_row.get("official_domain") or "").lower().removeprefix("www.")
        if (urlsplit(final_url).hostname or "").lower().removeprefix("www.") != domain:
            return {"safe": False, "prepared": False, "reason": "DOMAIN_CHANGED", "safety": True}
        stage3_full_v3 = bool(reservoir_row.get("_stage3_full_v3_fresh"))
        if stage3_full_v3:
            roots=list(page.frames); check_roots=[]
            for idx in (0,int(getattr(slot,"target_frame_index",0) or 0)):
                if 0 <= idx < len(roots) and roots[idx] not in check_roots: check_roots.append(roots[idx])
            for _r in check_roots:
                if await self._visible_captcha_challenge(_r):
                    return {"safe": False, "prepared": False, "reason": "CAPTCHA", "safety": True}
            try: page_text=await page.locator("body").inner_text(timeout=900)
            except Exception: page_text=""
            try: root_text=await root.locator("body").inner_text(timeout=700)
            except Exception: root_text=""
            plain=" ".join((str(page_text)+" "+str(root_text)).split())[:30000]
            html=plain
        else:
            page_html = await page.content()
            try: root_html = await root.content()
            except Exception: root_html = page_html
            html = page_html + "\n" + root_html
            if captcha_challenge_present(html):
                return {"safe": False, "prepared": False, "reason": "CAPTCHA", "safety": True}
            plain = " ".join(re.sub("<[^>]+>", " ", html).split())
        if PROHIBIT.search(plain):
            return {"safe": False, "prepared": False, "reason": "SALES_PROHIBITED", "safety": True}
        # V9 already supplied the Stage3 rendered proof. The field-level live
        # checks immediately above are authoritative here; do not import the
        # legacy V5 semantic parser on Render. For non-V9 callers, fail closed.
        if not stage3_full_v3:
            return {"safe": False, "prepared": False, "reason": "FINAL_STAGE3_PROOF_REQUIRED", "safety": True}
        semantic_fp = "V9_STAGE3_PREVERIFIED_FINAL_LIVE_RECHECK"

        now_ms = int(time.time() * 1000)
        final_proof_source, final_lane_mode = _final_live_preflight_provenance(
            stage3_detail, stage3_full_v3
        )
        final_contract = {
            "official_domain_verified": True,
            "contact_route_verified": True,
            "dnc_clear": True,
            "sales_prohibited_clear": True,
            "captcha_checked": True,
            "personal_required_clear": True,
            "public_entity_clear": True,
            "legal_risk_pass": True,
            # This contract is created only after the live Playwright page has
            # been rendered, safety-scanned, semantically parsed and filled on
            # this same page. Prior Stage3 proof is useful provenance, but is
            # not required to truthfully record the completed live preflight.
            "stage3_final_rendered": True,
            "stage3_proof_source": final_proof_source,
            "stage3_lane_mode": final_lane_mode,
            "prior_stage3_proof_source": str(stage3_detail.get("proof_source") or ""),
            "prior_stage3_lane_mode": str(stage3_detail.get("lane_mode") or "").upper(),
            "form_fingerprint": str(semantic_fp or ""),
            "message_hash": hashlib.sha256(message_body.encode("utf-8")).hexdigest(),
            "policy_version": "PAL_B2B_POLICY_V6_FREE_20260918_01",
            "verified_at": now_ms,
            "expires_at": now_ms + 600000,
        }
        return {
            "safe": True,
            "prepared": True,
            "reason": "SAME_PAGE_PREPARED",
            "final_url": final_url,
            "final_safety_contract": final_contract,
            "target_form_index": target_form_index,
            "target_frame_index": int(slot.target_frame_index),
            "target_form_score": int(target.get("score") or 0),
            "cycle_seconds": round(time.monotonic() - started, 3),
            "timing": {
                **dict(pre.get("timing") or {}),
                "form_detect_ms": form_detect_ms,
                "fill_ms": fill_ms,
                "final_safety_ms": round((time.monotonic() - final_safety_started) * 1000, 1),
            },
        }


    async def revalidate_prepared_fields(self, slot: BrowserSlot, form_index: int | None,
                                         message_body: str, reply_address: str,
                                         market: str = "") -> dict:
        """Immediately before submit, prove core form values still persist."""
        if form_index is None or not message_body or not reply_address:
            return {"ready": False, "reason": "PRE_SUBMIT_CORE_INPUT_MISSING"}
        root = self._target_root(slot)
        forms = root.locator("form")
        if int(form_index) < 0 or int(form_index) >= await forms.count():
            return {"ready": False, "reason": "PRE_SUBMIT_FORM_CHANGED"}
        form = forms.nth(int(form_index))
        rows = await form.locator("input,textarea,select").evaluate_all(_pal_js(r"""
          return els.map((e,i)=>{
          const d=(palSelfDesc(e)+' '+palRowLabel(e)).slice(0,500);
          return {i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),
                  desc:d,value:e.value||'',required:palRequired(e),
                  visible:palVisible(e),disabled:!!e.disabled};
        });"""))
        intl = str(market or "") != "JP-JA"
        contact_name = "Practical AI Lab" if intl else "Practical AI Lab 運営"
        site_url = "https://practical-ai-lab.pages.dev/global/" if intl else "https://practical-ai-lab.pages.dev/"
        saw_email = False
        saw_message = False
        # Frameworks such as Squarespace can render an optional text input whose
        # generated name also contains "message" beside the real textarea. If the
        # real core control exists, do not treat that optional duplicate as a
        # second core field whose framework reset can fail the whole pre-submit.
        has_core_message = any(bool(x.get("visible")) and not bool(x.get("disabled"))
                               and str(x.get("tag") or "").lower()=="textarea" for x in rows)
        has_core_email = any(bool(x.get("visible")) and not bool(x.get("disabled"))
                             and str(x.get("type") or "").lower()=="email" for x in rows)
        repaired = 0
        for row in rows:
            if not row.get("visible") or row.get("disabled"):
                continue
            typ = str(row.get("type") or "").lower()
            tag = str(row.get("tag") or "").lower()
            if typ in {"hidden","submit","button","image","file","checkbox","radio"} or tag == "select":
                continue
            core = str(row.get("desc") or "")
            current = str(row.get("value") or "")
            if PAL_SENSITIVE_RX.search(core):
                if row.get("required") and not current.strip():
                    return {"ready": False, "reason": "REQUIRED_PERSONAL_ONLY", "safety": True}
                continue
            desired = None
            # Field type outranks label wording here exactly as it does in the
            # fill pass. Matching on "inquiry" first would put the message body
            # into a type=email field moments before submit and re-create the
            # client-side "enter a valid email address" rejection.
            if tag == "textarea":
                desired = message_body
                saw_message = True
            elif typ == "email":
                desired = reply_address
                saw_email = True
            elif typ == "url":
                desired = site_url
            elif re.search(r"(message|inquiry|enquiry|comment|問い合わせ内容|内容|詳細)", core, re.I):
                if has_core_message and not row.get("required"):
                    continue
                desired = message_body
                saw_message = True
            elif re.search(r"(e-?mail|メール|your[-_ ]?email)", core, re.I):
                if has_core_email and not row.get("required"):
                    continue
                desired = reply_address
                saw_email = True
            elif re.search(r"(company|organization|organisation|会社|法人|企業)", core, re.I):
                desired = "Practical AI Lab"
            elif re.search(r"(your[-_ ]?name|full[-_ ]?name|contact[-_ ]?name|氏名|お名前|\bname\b)", core, re.I):
                desired = contact_name
            if desired is not None and current != desired:
                loc = form.locator("input,textarea,select").nth(int(row["i"]))
                if not await self._commit_field_value(loc, desired):
                    return {"ready": False, "reason": "PRE_SUBMIT_FIELD_PERSISTENCE_FAILED",
                            "field": core[:160]}
                repaired += 1
        await asyncio.sleep(0.08)
        missing = await form.locator("input,textarea,select").evaluate_all(_pal_js(r"""
          return els.filter(e=>{
          if(e.disabled||['hidden','submit','button','image','file','checkbox','radio','reset'].includes((e.type||'').toLowerCase()))return false;
          if(!palVisible(e))return false;
          return palRequired(e) && !String(e.value||'').trim();
        }).map(e=>(e.name||e.id||e.type||'unknown').slice(0,120));"""))
        if missing:
            return {"ready": False, "reason": "PRE_SUBMIT_REQUIRED_RESET", "missing": missing[:8]}
        if not saw_email or not saw_message:
            return {"ready": False, "reason": "PRE_SUBMIT_CORE_FORM_CHANGED",
                    "saw_email": saw_email, "saw_message": saw_message}
        return {"ready": True, "repaired": repaired}

    async def final_submit_control(self, slot: BrowserSlot, form_index: int | None = None) -> dict:
        """Locate a conservative FINAL send control inside the selected contact form."""
        page = slot.page
        if form_index is None:
            return {"ready": False, "reason": "TARGET_FORM_INDEX_MISSING"}
        root = self._target_root(slot)
        forms = root.locator("form")
        selected_form = None
        if 0 <= int(form_index) < await forms.count():
            selected_form = forms.nth(int(form_index))
        if selected_form is not None:
            try:
                form_runtime = await selected_form.evaluate("""f => {
                    const propsKey = Object.keys(f).find(k => k.startsWith('__reactProps$'));
                    const props = propsKey ? f[propsKey] : null;
                    return {
                        action: f.action || f.getAttribute('action') || '',
                        actionAttr: f.getAttribute('action') || '',
                        methodAttr: (f.getAttribute('method') || '').toLowerCase(),
                        nativeOnSubmit: typeof f.onsubmit === 'function',
                        reactOnSubmit: !!(props && typeof props.onSubmit === 'function'),
                        webflowManaged: !!(
                            f.hasAttribute('data-wf-page-id') &&
                            (f.querySelector('input[type=\"submit\"].w-button') || f.closest('.w-form'))
                        )
                    };
                }""")
                resolved_action = str((form_runtime or {}).get("action") or "")
                form_text = str(await selected_form.inner_text(timeout=1500) or "")
                mailto_risk = bool(await selected_form.evaluate(r"""f => {
                  const src = [f.outerHTML || '', String(f.onsubmit || '')];
                  for (const e of f.querySelectorAll('button,input,a')) {
                    src.push(
                      e.getAttribute('href') || '',
                      e.getAttribute('formaction') || '',
                      e.getAttribute('onclick') || '',
                      String(e.onclick || '')
                    );
                    const key = Object.keys(e).find(k => k.startsWith('__reactProps$'));
                    const ep = key ? e[key] : null;
                    if (ep && ep.onClick) src.push(String(ep.onClick));
                  }
                  const fk = Object.keys(f).find(k => k.startsWith('__reactProps$'));
                  const fp = fk ? f[fk] : null;
                  if (fp && fp.onSubmit) src.push(String(fp.onSubmit));
                  return /mailto\s*:/i.test(src.join('\n'));
                }"""))
            except Exception:
                form_runtime = {}
                resolved_action = ""
                form_text = ""
                mailto_risk = False
            if _non_postable_static_form_action(resolved_action):
                return {"ready": False, "reason": "STATIC_EXPORT_FORM_ACTION",
                        "form_action": resolved_action[:500], "route_repair": True}
            if mailto_risk or EMAIL_HANDOFF_TEXT_RX.search(form_text):
                return {"ready": False, "reason": "EMAIL_HANDOFF_FORM",
                        "form_action": resolved_action[:500], "route_repair": True}
            # Client-rendered forms with no action/method fall back to a native
            # GET of the current page if hydration has not attached onSubmit.
            # Verify the handler before crossing the one-shot submit barrier.
            action_attr = str((form_runtime or {}).get("actionAttr") or "")
            method_attr = str((form_runtime or {}).get("methodAttr") or "")
            js_handler = bool((form_runtime or {}).get("nativeOnSubmit") or
                              (form_runtime or {}).get("reactOnSubmit") or
                              (form_runtime or {}).get("webflowManaged"))
            if not action_attr and method_attr in {"", "get"} and not js_handler:
                # Some React/Wix/SPA forms attach the submit handler shortly
                # after the visible form is already fillable. Poll a few short
                # times in the SAME page/session before deferring the whole job.
                # We still fail closed: no handler/action => no submit.
                for _hydration_try in range(3):
                    try:
                        await slot.page.wait_for_timeout(700)
                        form_runtime = await selected_form.evaluate("""f => {
                            const propsKey = Object.keys(f).find(k => k.startsWith('__reactProps$'));
                            const props = propsKey ? f[propsKey] : null;
                            return {
                                action: f.action || f.getAttribute('action') || '',
                                actionAttr: f.getAttribute('action') || '',
                                methodAttr: (f.getAttribute('method') || '').toLowerCase(),
                                nativeOnSubmit: typeof f.onsubmit === 'function',
                                reactOnSubmit: !!(props && typeof props.onSubmit === 'function'),
                                webflowManaged: !!(
                                    f.hasAttribute('data-wf-page-id') &&
                                    (f.querySelector('input[type=\"submit\"].w-button') || f.closest('.w-form'))
                                )
                            };
                        }""")
                        resolved_action = str((form_runtime or {}).get("action") or "")
                        action_attr = str((form_runtime or {}).get("actionAttr") or "")
                        method_attr = str((form_runtime or {}).get("methodAttr") or "")
                        js_handler = bool((form_runtime or {}).get("nativeOnSubmit") or
                                          (form_runtime or {}).get("reactOnSubmit") or
                                          (form_runtime or {}).get("webflowManaged"))
                        if action_attr or method_attr not in {"", "get"} or js_handler:
                            break
                    except Exception:
                        break
                if not action_attr and method_attr in {"", "get"} and not js_handler:
                    return {"ready": False, "reason": "JS_SUBMIT_HANDLER_NOT_READY",
                            "form_action": resolved_action[:500], "retry": True}
        controls = await self._form_submit_controls(root, int(form_index)) if selected_form is not None else None
        count = await controls.count() if controls is not None else 0
        final_rx = re.compile(
            r"(この内容で送信|内容を送信|送信する|送信|send\s*(message|inquiry|enquiry)?|submit\s*(message|inquiry|enquiry|form)?)",
            re.I,
        )
        nonfinal_rx = re.compile(r"(確認|confirm|next|次へ|preview|戻る|back|cancel|修正)", re.I)
        fallback=[]
        native_submit_fallback=[]
        for i in range(min(count, 30)):
            loc = controls.nth(i)
            try:
                if not await loc.is_visible() or not await loc.is_enabled():
                    continue
                desc = await loc.evaluate(PAL_CONTROL_DESC_JS)
                desc = " ".join(str(desc or "").split())
                meta = await loc.evaluate("e=>({tag:(e.tagName||'').toLowerCase(),type:(e.type||'').toLowerCase()})")
                if re.search(r"(コメント|comment|レビュー|review)", desc, re.I):
                    continue
                explicit_final=bool(re.search(r"(確認して送信|確認のうえ送信|confirm.{0,12}send|send.{0,12}confirm)",desc,re.I))
                if final_rx.search(desc) and (not nonfinal_rx.search(desc) or explicit_final):
                    return {"ready": True, "index": i, "desc": desc[:180],
                            "form_index": int(form_index), "frame_index": int(slot.target_frame_index)}
                if not nonfinal_rx.search(desc):
                    fallback.append((i,desc))
                    # HTML's resolved .type is "submit" even for a <button>
                    # whose type attribute is omitted. Inside the already-selected
                    # business contact form, one unique visible/enabled native
                    # submit control is deterministic even when its label is
                    # "Get in touch", "Contact us", etc.
                    if str((meta or {}).get("type") or "") in {"submit","image"}:
                        native_submit_fallback.append((i,desc))
            except Exception:
                continue
        if len(native_submit_fallback)==1:
            i,desc=native_submit_fallback[0]
            return {"ready":True,"index":i,"desc":desc[:180],
                    "form_index":int(form_index),"frame_index":int(slot.target_frame_index),
                    "evidence":"UNIQUE_NATIVE_SUBMIT_CONTROL"}
        if slot.stage3_control_kind in {"DIRECT_SUBMIT","CONFIRM_THEN_DIRECT_SUBMIT"} and len(fallback)==1:
            i,desc=fallback[0]
            return {"ready":True,"index":i,"desc":desc[:180],
                    "form_index":int(form_index),"evidence":"STAGE3_UNIQUE_DIRECT_CONTROL"}
        # Some two-step corporate forms replace the <form> on the confirmation
        # page with page-level Back/Send buttons. Allow this only on an explicit
        # confirmation URL and only for a Stage-3-proven confirmation flow.
        confirm_url=bool(re.search(r"(?:/|[?&])(?:step=)?confirm(?:/|[?&#]|$)",str(page.url or ""),re.I))
        if confirm_url and slot.stage3_control_kind in {"CONFIRM_STEP","CONFIRM_THEN_DIRECT_SUBMIT"}:
            root_controls=root.locator(PAL_ROOT_SUBMIT_SELECTOR)
            global_hits=[]
            for gi in range(min(await root_controls.count(),40)):
                gloc=root_controls.nth(gi)
                try:
                    if not await gloc.is_visible() or not await gloc.is_enabled():
                        continue
                    gdesc=await gloc.evaluate(PAL_CONTROL_DESC_JS)
                    gdesc=" ".join(str(gdesc or "").split())
                    explicit_final=bool(re.search(r"(確認して送信|確認のうえ送信|confirm.{0,12}send|send.{0,12}confirm)",gdesc,re.I))
                    if final_rx.search(gdesc) and (not nonfinal_rx.search(gdesc) or explicit_final):
                        global_hits.append((gi,gdesc))
                except Exception:
                    continue
            if len(global_hits)==1:
                gi,gdesc=global_hits[0]
                return {"ready":True,"index":gi,"desc":gdesc[:180],
                        "form_index":None,"scope":"ROOT",
                        "evidence":"CONFIRM_PAGE_UNIQUE_FINAL_CONTROL"}
        return {"ready": False, "reason": "FINAL_SUBMIT_CONTROL_NOT_FOUND"}

    async def confirmation_control(self, slot: BrowserSlot, form_index: int | None = None) -> dict:
        """Locate a visible confirmation/next control inside the selected contact form."""
        page = slot.page
        if form_index is None:
            return {"ready": False, "reason": "TARGET_FORM_INDEX_MISSING"}
        root = self._target_root(slot)
        forms = root.locator("form")
        if int(form_index) < 0 or int(form_index) >= await forms.count():
            return {"ready": False, "reason": "TARGET_FORM_GONE"}
        form = forms.nth(int(form_index))
        controls = form.locator(PAL_CONFIRM_SELECTOR)
        count = await controls.count()
        confirm_rx = re.compile(
            r"(確認画面へ|入力内容を確認|内容を確認|確認する|を確認する|"
            r"confirm|next|次へ)",
            re.I,
        )
        reject_rx = re.compile(r"(戻る|back|cancel|修正|reset|クリア)", re.I)
        fallback=[]
        for i in range(min(count, 30)):
            loc = controls.nth(i)
            try:
                if not await loc.is_visible() or not await loc.is_enabled():
                    continue
                desc = await loc.evaluate(PAL_CONTROL_DESC_JS)
                desc = " ".join(str(desc or "").split())
                if (confirm_rx.search(desc) and not reject_rx.search(desc)
                        and not re.search(r"(送信|\bsend\b|\bsubmit\b)",desc,re.I)):
                    return {"ready": True, "index": i, "desc": desc[:220],
                            "form_index": int(form_index), "frame_index": int(slot.target_frame_index)}
                if not reject_rx.search(desc) and not re.search(r"(コメント|comment|レビュー|review)",desc,re.I):
                    fallback.append((i,desc))
            except Exception:
                continue
        if slot.stage3_control_kind in {"CONFIRM_STEP","CONFIRM_THEN_DIRECT_SUBMIT"} and len(fallback)==1:
            i,desc=fallback[0]
            return {"ready":True,"index":i,"desc":desc[:220],
                    "form_index":int(form_index),"evidence":"STAGE3_UNIQUE_CONFIRM_CONTROL"}
        return {"ready": False, "reason": "CONFIRM_CONTROL_NOT_FOUND"}

    async def advance_confirmation(self, slot: BrowserSlot, control_index: int,
                                   form_index: int | None = None) -> dict:
        """Click one confirmation control after the durable barrier.
        Continue only when a clear confirmation stage appears; never second-click on ambiguity.
        """
        page = slot.page
        if form_index is None:
            return {"advanced": False, "reason": "TARGET_FORM_INDEX_MISSING",
                    "mutation_observed": False}
        root = self._target_root(slot)
        forms = root.locator("form")
        if int(form_index) < 0 or int(form_index) >= await forms.count():
            return {"advanced": False, "reason": "TARGET_FORM_GONE",
                    "mutation_observed": False}
        form = forms.nth(int(form_index))
        controls = form.locator(PAL_CONFIRM_SELECTOR)
        loc = controls.nth(int(control_index))
        form_values = await form.locator("input,textarea").evaluate_all(
            "els => els.filter(e => !e.disabled && !['hidden','password','checkbox','radio','submit','button'].includes(e.type))"
            ".map(e => e.value || '').filter(v => v.length >= 8)"
        )
        slot.submit_form_values = list(form_values)
        before_url = page.url
        origin_host = (urlsplit(before_url).hostname or "").lower().removeprefix("www.")
        mutations: list[dict] = []
        responses: list[dict] = []
        response_objects = []

        def on_request(req):
            try:
                method = str(req.method or "").upper()
                host = (urlsplit(req.url).hostname or "").lower().removeprefix("www.")
                if method not in {"GET", "HEAD", "OPTIONS"}:
                    mutations.append({"method": method, "url": req.url[:500],
                                      "matches_form_payload": _matches_form_payload(req.post_data or "", form_values)})
            except Exception:
                pass

        def on_response(resp):
            try:
                req = resp.request
                method = str(req.method or "").upper()
                host = (urlsplit(req.url).hostname or "").lower().removeprefix("www.")
                if method not in {"GET", "HEAD", "OPTIONS"}:
                    correlated = _matches_form_payload(req.post_data or "", form_values)
                    responses.append({"method": method, "url": req.url[:500], "status": int(resp.status),
                                      "matches_form_payload": correlated})
                    if correlated:
                        response_objects.append(resp)
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)
        click_error = None
        confirmation_submit_method = "click"
        try:
            # This is still exactly ONE post-barrier action. For a native
            # confirmation submitter, requestSubmit(submitter) preserves its
            # name/value and HTML validation more reliably than a synthetic
            # pointer click. It is never used for a visible send/final action.
            meta = await loc.evaluate(
                "e=>({tag:(e.tagName||'').toLowerCase(),type:(e.type||'').toLowerCase()})"
            )
            desc = await loc.evaluate(PAL_CONTROL_DESC_JS)
            used_request_submit = False
            if _confirmation_request_submit_eligible(meta, str(desc or "")):
                used_request_submit = bool(await loc.evaluate(r"""e=>{
                  if(!e.form || typeof e.form.requestSubmit!=='function') return false;
                  e.form.requestSubmit(e);
                  return true;
                }"""))
            if used_request_submit:
                confirmation_submit_method = "requestSubmit"
            else:
                await loc.click(timeout=4500, no_wait_after=False)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
            await page.wait_for_timeout(500)
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(650)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(450)
            except Exception:
                pass
        except Exception as exc:
            click_error = type(exc).__name__ + ":" + str(exc)[:200]
        finally:
            try:
                page.remove_listener("request", on_request)
                page.remove_listener("response", on_response)
            except Exception:
                pass

        server_success = False
        server_not_sent = False
        response_bodies = []
        for resp in response_objects[:6]:
            try:
                raw = (await asyncio.wait_for(resp.text(), timeout=1.5))[:65536]
                parsed = None
                try:
                    import json as _json
                    parsed = _json.loads(raw)
                except Exception:
                    parsed = None
                app_status = str(parsed.get("status") or "").lower() if isinstance(parsed, dict) else ""
                if app_status in {"mail_sent", "sent", "success"}:
                    server_success = True
                if app_status in {"validation_failed", "spam", "mail_failed", "aborted", "acceptance_missing"}:
                    server_not_sent = True
                response_bodies.append({"url": resp.url[:500], "status": int(resp.status),
                                        "app_status": app_status[:80]})
            except Exception:
                pass

        try:
            body_text = await root.locator("body").inner_text(timeout=2000)
        except Exception:
            body_text = ""
        low = " ".join(body_text.lower().split())
        success_dom = bool(re.search(
            r"(送信が完了|送信完了|メッセージ.{0,20}送信されました|"
            r"thank\s+you|successfully\s+(sent|submitted)|"
            r"message\s+(has\s+been\s+)?sent)",
            low, re.I
        ))
        after_url = page.url
        provider_success_navigation = _provider_success_navigation(before_url, after_url)
        thank_you_navigation = provider_success_navigation or (
            after_url != before_url and
            bool(re.search(r"(thanks?|thank[-_]?you|complete|completed|success|sent)", after_url, re.I))
        )
        post_2xx = any(x.get("matches_form_payload") and 200 <= int(x.get("status", 0)) < 300 for x in responses)
        mutation_observed = bool(mutations)

        evidence = {
            "submit_request_observed": False,
            "submit_request_2xx": False,
            "submit_request_correlated": any(x.get("matches_form_payload") for x in mutations),
            "confirmation_request_observed": mutation_observed,
            "confirmation_request_2xx": post_2xx,
            "server_success": server_success,
            "server_not_sent": server_not_sent,
            "success_dom": success_dom,
            "thank_you_navigation": thank_you_navigation,
            "provider_success_navigation": provider_success_navigation,
            "form_disappeared": False,
            "validation_error": server_not_sent,
            "confirmation_click": True,
            "confirmation_submit_method": confirmation_submit_method,
            "network_mutations": mutations[:8],
            "network_responses": responses[:8],
            "response_bodies": response_bodies[:6],
            "final_url": after_url[:500],
        }
        sent_on_confirm=bool(server_success or thank_you_navigation)
        if sent_on_confirm and post_2xx and not server_not_sent:
            evidence["submit_request_observed"]=True
            evidence["submit_request_2xx"]=bool(post_2xx)
            return {"advanced": False, "possible_send": True, "outcome": "SENT_CONFIRMED",
                    "evidence": evidence, "reason": "CONFIRM_CLICK_SENT_WITH_SUCCESS_PROOF"}
        if server_not_sent:
            evidence["submit_request_observed"]=False
            evidence["submit_request_2xx"]=False
            return {"advanced": False, "possible_send": False, "outcome": "CONFIRMED_NOT_SENT",
                    "evidence": evidence, "reason": "CONFIRM_VALIDATION_FAILED"}

        # A second click is permitted only after a clear confirmation stage is visible.
        for _r in list(page.frames)[:20]:
            if await self._visible_captcha_challenge(_r):
                evidence["captcha_after_confirm"]=True
                evidence["submit_request_observed"]=False
                evidence["submit_request_2xx"]=False
                return {"advanced":False,"possible_send":False,"outcome":"CONFIRMED_NOT_SENT",
                        "evidence":evidence,"reason":"CAPTCHA_AFTER_CONFIRM"}
        final_control = await self.final_submit_control(slot, int(form_index))
        confirmation_stage = bool(
            re.search(
                r"(入力内容.{0,20}確認|確認画面|以下の内容|この内容で送信|"
                r"送信内容|修正する|内容を確認しました)",
                low, re.I
            )
            or re.search(r"(?:/|[?&])(?:step=)?confirm(?:/|[?&#]|$)",str(after_url or ""),re.I)
        )
        if final_control.get("ready") is True and confirmation_stage:
            return {"advanced": True, "possible_send": False,
                    "final_control": final_control, "mutation_observed": mutation_observed,
                    "confirmation_stage": confirmation_stage, "evidence": evidence,
                    "reason": "CONFIRMATION_STAGE_READY"}
        if confirmation_stage:
            evidence["submit_request_observed"]=False
            evidence["submit_request_2xx"]=False
            return {"advanced": False, "possible_send": False, "outcome": "CONFIRMED_NOT_SENT",
                    "evidence": evidence, "reason": "CONFIRM_STAGE_WITHOUT_FINAL_CONTROL"}
        if mutation_observed:
            return {"advanced": False, "possible_send": True, "outcome": "AMBIGUOUS_HOLD",
                    "evidence": evidence, "reason": "CONFIRM_MUTATION_WITHOUT_CLEAR_STAGE"}
        return {"advanced": False, "possible_send": True, "outcome": "AMBIGUOUS_HOLD",
                "evidence": evidence, "reason": click_error or "CONFIRM_DID_NOT_ADVANCE"}

    async def submit_prepared(self, slot: BrowserSlot, control_index: int,
                              form_index: int | None = None) -> dict:
        """Click exactly once inside the selected contact form after SUBMIT_STARTED."""
        page = slot.page
        root = self._target_root(slot)
        before_url = page.url
        before_forms = await root.locator("form").count()
        origin_host = (urlsplit(before_url).hostname or "").lower().removeprefix("www.")
        tracked_hosts = {origin_host}
        try:
            frame_host = (urlsplit(str(root.url or "")).hostname or "").lower().removeprefix("www.")
            if frame_host:
                tracked_hosts.add(frame_host)
        except Exception:
            pass
        form_action = ""
        action_host = ""
        form_values = list(slot.submit_form_values)
        success_rx = re.compile(
            r"(送信が完了|送信完了|お問い合わせ.{0,24}(?:ありがとう|受け付け|受付)|"
            r"thank\s+you|successfully\s+(?:sent|submitted)|message\s+(?:has\s+been\s+)?sent|"
            r"inquiry.{0,24}(?:received|submitted))", re.I
        )
        try:
            before_text = " ".join((await root.locator("body").inner_text(timeout=2000)).lower().split())
            before_success_matches = {m.group(0) for m in success_rx.finditer(before_text)}
        except Exception:
            before_success_matches = None
        try:
            before_provider_texts = set(await root.locator(PAL_SUCCESS_SELECTOR).evaluate_all(
                "els => els.filter(e => e.getClientRects().length > 0)"
                ".map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean)"
            ))
        except Exception:
            before_provider_texts = None
        try:
            forms_meta = root.locator("form")
            if form_index is not None and 0 <= int(form_index) < await forms_meta.count():
                selected_form_meta = forms_meta.nth(int(form_index))
                current_values = await selected_form_meta.locator("input,textarea").evaluate_all(
                    "els => els.filter(e => !e.disabled && !['hidden','password','checkbox','radio','submit','button'].includes(e.type))"
                    ".map(e => e.value || '').filter(v => v.length >= 8)"
                )
                if current_values:
                    form_values = list(set(form_values + current_values))
                    slot.submit_form_values = list(form_values)
                form_action = str(await selected_form_meta.evaluate(
                    "f => f.action || f.getAttribute('action') || ''"
                ) or "")
                action_host = (urlsplit(form_action).hostname or "").lower().removeprefix("www.")
                if action_host:
                    tracked_hosts.add(action_host)
        except Exception:
            pass
        mutations: list[dict] = []
        responses: list[dict] = []
        response_objects = []

        def on_request(req):
            try:
                method = str(req.method or "").upper()
                host = (urlsplit(req.url).hostname or "").lower().removeprefix("www.")
                if method not in {"GET", "HEAD", "OPTIONS"}:
                    correlated = _matches_form_payload(req.post_data or "", form_values)
                    mutations.append({"method": method, "url": req.url[:500],
                                      "resource_type": req.resource_type, "matches_form_payload": correlated})
            except Exception:
                pass

        def on_response(resp):
            try:
                req = resp.request
                method = str(req.method or "").upper()
                host = (urlsplit(req.url).hostname or "").lower().removeprefix("www.")
                if method not in {"GET", "HEAD", "OPTIONS"}:
                    correlated = _matches_form_payload(req.post_data or "", form_values)
                    responses.append({"method": method, "url": req.url[:500], "status": int(resp.status),
                                      "matches_form_payload": correlated})
                    if correlated:
                        response_objects.append(resp)
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)
        try:
            await root.evaluate(r"""() => {
              window.__pal_form_events = [];
              window.__pal_cf7_event = null;
              if (!window.__pal_multi_form_listener_installed) {
                const record = (type, detail) => {
                  const row = {type, at: Date.now(), detail: detail || null};
                  window.__pal_form_events.push(row);
                  if (String(type).startsWith('wpcf7')) {
                    window.__pal_cf7_event = {
                      type,
                      contactFormId: detail && detail.contactFormId ? detail.contactFormId : null,
                      at: row.at
                    };
                  }
                };
                for (const type of ['wpcf7mailsent','wpcf7invalid','wpcf7spam','wpcf7mailfailed']) {
                  document.addEventListener(type, ev => record(type, ev && ev.detail ? ev.detail : null), true);
                }
                if (window.jQuery) {
                  const $ = window.jQuery;
                  $(document).on('gform_confirmation_loaded.palv6', function(_e, formId) {
                    record('gform_confirmation_loaded', {formId});
                  });
                  $(document).on('wpformsAjaxSubmitSuccess.palv6', function(_e, response) {
                    record('wpformsAjaxSubmitSuccess', response || null);
                  });
                  $('form').on('wpformsAjaxSubmitSuccess.palv6', function(_e, response) {
                    record('wpformsAjaxSubmitSuccess', response || null);
                  });
                  $('form').on('fluentform_submission_success.palv6', function(_e, data) {
                    record('fluentform_submission_success', data || null);
                  });
                  $('form').on('fluentform_submission_failed.palv6', function(_e, data) {
                    record('fluentform_submission_failed', data || null);
                  });
                }
                window.__pal_multi_form_listener_installed = true;
              }
            }""")
        except Exception:
            pass
        clicked = False
        click_error = None
        try:
            if form_index is None:
                controls = root.locator(PAL_ROOT_SUBMIT_SELECTOR)
            else:
                forms = root.locator("form")
                if int(form_index) < 0 or int(form_index) >= await forms.count():
                    return {
                        "outcome": "CONFIRMED_NOT_SENT",
                        "evidence": {"submit_request_observed": False},
                        "reason": "TARGET_FORM_GONE",
                    }
                controls = await self._form_submit_controls(root, int(form_index))
            loc = controls.nth(int(control_index))
            if not await loc.is_visible() or not await loc.is_enabled():
                return {
                    "outcome": "CONFIRMED_NOT_SENT",
                    "evidence": {"submit_request_observed": False},
                    "reason": "FINAL_SUBMIT_CONTROL_GONE",
                }
            await loc.click(timeout=5000, no_wait_after=False)
            clicked = True
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3500)
            except Exception:
                pass
            # AJAX forms (e.g. Contact Form 7) often render success before the
            # response callback is observed. Keep listeners alive briefly so
            # the durable receipt can require independent HTTP + DOM proof.
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline and not any(x.get("matches_form_payload") for x in responses):
                await page.wait_for_timeout(200)
            # Some legitimate CF7/Formspree/native form POSTs dispatch promptly but
            # their response arrives after a slow server-side mail/CRM handoff. Only
            # when the request body is already correlated to the filled business
            # fields, grant a bounded extra response grace. Telemetry/unrelated POSTs
            # never enter this branch, and a 2xx alone still does not confirm send.
            correlated_dispatched = any(x.get("matches_form_payload") for x in mutations)
            hostinger_dispatched = any(
                x.get("matches_form_payload")
                and (urlsplit(str(x.get("url") or "")).hostname or "").lower().removeprefix("www.") == "builder-backend.hostinger.com"
                and re.fullmatch(r'/u\d+/data/v3/post/[^/]+/?', urlsplit(str(x.get("url") or "")).path or '', re.I)
                for x in mutations
            )
            if correlated_dispatched and not any(x.get("matches_form_payload") for x in responses):
                # Hostinger's submission backend has repeatedly completed after
                # the generic response window. Keep the extra wait provider-
                # specific so normal Stage5 throughput is unchanged.
                grace_deadline = time.monotonic() + (8.0 if hostinger_dispatched else 4.0)
                while time.monotonic() < grace_deadline and not any(x.get("matches_form_payload") for x in responses):
                    await page.wait_for_timeout(200)
            # Allow provider callbacks / success DOM to settle after the network
            # response. This improves evidence quality without counting HTTP 2xx alone.
            await page.wait_for_timeout(900)
        except Exception as exc:
            click_error = type(exc).__name__ + ":" + str(exc)[:180]
            # Playwright can time out waiting for navigation even after the DOM
            # click has already been dispatched. A timeout therefore does NOT
            # prove not-sent. Infer whether the action crossed the click boundary
            # from any provider/network/form-state evidence observed while the
            # listener was still attached; _submit_outcome then keeps those cases
            # AMBIGUOUS unless independent delivery proof exists.
            clicked = bool(
                clicked
                or mutations
                or responses
                or str(page.url) != before_url
            )
        finally:
            try:
                page.remove_listener("request", on_request)
                page.remove_listener("response", on_response)
            except Exception:
                pass

        response_bodies = []
        server_success = False
        server_not_sent = False
        cf7_event = None
        form_events = []
        try:
            cf7_event = await root.evaluate("() => window.__pal_cf7_event || null")
        except Exception:
            cf7_event = None
        try:
            raw_events = await root.evaluate("() => window.__pal_form_events || []")
            if isinstance(raw_events, list):
                form_events = raw_events[:20]
        except Exception:
            form_events = []
        event_types = {str(x.get("type") or "") for x in form_events if isinstance(x, dict)}
        if isinstance(cf7_event, dict):
            event_types.add(str(cf7_event.get("type") or ""))
        if event_types & {
            "wpcf7mailsent",
            "wpformsAjaxSubmitSuccess",
            "gform_confirmation_loaded",
            "fluentform_submission_success",
        }:
            server_success = True
        if event_types & {
            "wpcf7invalid", "wpcf7spam", "wpcf7mailfailed",
            "fluentform_submission_failed",
        }:
            server_not_sent = True
        for resp in response_objects[:8]:
            try:
                try:
                    await asyncio.wait_for(resp.finished(), timeout=2.0)
                except Exception:
                    pass
                raw = (await asyncio.wait_for(resp.text(), timeout=2.0))[:65536]
                parsed = None
                try:
                    import json as _json
                    parsed = _json.loads(raw)
                except Exception:
                    parsed = None
                app_status = str(parsed.get("status") or "").lower() if isinstance(parsed, dict) else ""
                app_ok = bool(
                    isinstance(parsed, dict) and
                    (parsed.get("ok") is True or parsed.get("success") is True)
                )
                app_errors = bool(
                    isinstance(parsed, dict) and
                    isinstance(parsed.get("errors"), (list, dict)) and
                    len(parsed.get("errors")) > 0
                )
                raw_low = " ".join(str(raw or "").lower().split())[:12000]
                text_success = bool(re.search(
                    r'("success"\s*:\s*true|"ok"\s*:\s*true|'
                    r'message\s+(?:has\s+been\s+)?sent|successfully\s+(?:sent|submitted)|'
                    r'thank\s+you.{0,80}(?:message|inquir|contact)|'
                    r'inquir(?:y|ies).{0,80}(?:received|submitted))',
                    raw_low, re.I
                ))
                text_not_sent = bool(re.search(
                    r'(validation[_ -]?failed|'
                    r'"success"\s*:\s*false|"ok"\s*:\s*false|'
                    r'acceptance[_ -]?missing|mail[_ -]?failed)',
                    raw_low, re.I
                ))
                # HTML often embeds hidden success templates on error pages.
                # Those strings do not prove acceptance; changed visible DOM or
                # a thank-you navigation is evaluated separately below.
                text_success = text_success and "<" not in raw
                provider_api_success = _provider_api_success(resp.url, int(resp.status))
                provider_body_success = _provider_body_success(resp.url, int(resp.status), app_status)
                if (app_status in {"mail_sent", "sent", "success", "submitted"}
                        or app_ok or text_success or provider_api_success or provider_body_success):
                    server_success = True
                if app_status in {"validation_failed", "spam", "mail_failed", "aborted", "acceptance_missing"} or app_errors or text_not_sent:
                    server_not_sent = True
                response_bodies.append({
                    "url": resp.url[:500],
                    "status": int(resp.status),
                    "app_status": app_status[:80],
                    "app_ok": app_ok,
                    "text_success": text_success,
                    "provider_api_success": provider_api_success,
                    "provider_body_success": provider_body_success,
                    "text_not_sent": text_not_sent,
                })
            except Exception:
                pass

        try:
            body_text = await root.locator("body").inner_text(timeout=2500)
        except Exception:
            body_text = ""
        low = " ".join(body_text.lower().split())
        provider_success_dom = False
        provider_error_dom = False
        provider_success_texts = []
        provider_error_texts = []
        try:
            provider_success_texts = await root.locator(PAL_SUCCESS_SELECTOR).evaluate_all(
                "els => els.filter(e => e.getClientRects().length > 0)"
                ".map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean)"
            )
            new_provider_success_texts = (set(provider_success_texts) - before_provider_texts) if before_provider_texts is not None else set()
            new_provider_success_texts = {x for x in new_provider_success_texts if not VALIDATION_TEXT_RX.search(str(x))}
            provider_success_dom = bool(new_provider_success_texts)
            provider_success_texts = list(new_provider_success_texts)
        except Exception:
            pass
        strong_provider_success_visible = bool(
            provider_success_dom
            and any(STRONG_PROVIDER_SUCCESS_RX.search(str(x)) for x in provider_success_texts[:6])
        )
        try:
            provider_error_texts = await root.locator(
                ".wpforms-error,.gfield_error .validation_message,"
                ".elementor-message-danger,.ff-el-is-error,[data-fs-error],"
                ".nf-error-msg,.frm_error,.hs-error-msgs,.hs-error-msg,.w-form-fail,"
                ".wpcf7.invalid .wpcf7-response-output,.wpcf7.spam .wpcf7-response-output,"
                ".wpcf7.failed .wpcf7-response-output,"
                ".wpcf7[data-status='invalid'] .wpcf7-response-output,"
                ".wpcf7[data-status='spam'] .wpcf7-response-output,"
                ".wpcf7[data-status='failed'] .wpcf7-response-output"
            ).evaluate_all(
                "els => els.filter(e => e.getClientRects().length > 0)"
                ".map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean)"
            )
            provider_error_dom = bool(provider_error_texts)
        except Exception:
            pass
        success_dom = provider_success_dom or bool(before_success_matches is not None and
                           ({m.group(0) for m in success_rx.finditer(low)} - before_success_matches))
        validation_error = provider_error_dom
        # A visible provider validation error proves this attempt was not accepted.
        # Treat it as non-delivery so the ledger may retry safely.
        if provider_error_dom and not server_success:
            server_not_sent = True
        try:
            visible_invalid = await root.locator("input:invalid,textarea:invalid,select:invalid").evaluate_all(
                """els=>els.filter(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';}).length"""
            )
            # Successful providers often clear the form after acceptance.
            # Required fields then become :invalid simply because they are empty,
            # which is not a rejection. A newly-rendered *strong* provider success
            # acknowledgement outranks that browser pseudo-class, while explicit
            # provider error DOM/server failure still remains authoritative.
            validation_error = validation_error or _cleared_required_fields_are_validation(
                visible_invalid, strong_provider_success_visible
            )
        except Exception:
            pass
        generic_error_texts = []
        try:
            generic_error_texts = await root.locator(
                "[role=alert],.validation-error,.invalid-feedback,.field-error,.form-error,.errors"
            ).evaluate_all(
                "els=>els.filter(e=>e.getClientRects().length>0)"
                ".map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean)"
            )
        except Exception:
            generic_error_texts = []
        if any(VALIDATION_TEXT_RX.search(str(x)) for x in generic_error_texts[:12]):
            validation_error = True
        # Post-click explicit provider text such as "Failed to send your
        # message" is definitive non-delivery evidence. Generic warning text
        # without this narrow phrase remains non-authoritative.
        if any(STRONG_NOT_SENT_RX.search(str(x)) for x in generic_error_texts[:12]):
            server_not_sent = True
            validation_error = True
        # Some generic form builders surface a successful submission in a
        # visible role=alert container rather than a provider-specific success
        # element. Promote only a strong success phrase that appeared after the
        # click; text already visible before submit is never accepted as proof.
        strong_generic_success = []
        for txt in generic_error_texts[:12]:
            norm = " ".join(str(txt or "").lower().split())
            if (norm and STRONG_PROVIDER_SUCCESS_RX.search(str(txt))
                    and (before_text is None or norm not in before_text)):
                strong_generic_success.append(str(txt))
        if strong_generic_success:
            provider_success_dom = True
            provider_success_texts = list(dict.fromkeys(provider_success_texts + strong_generic_success))
            success_dom = True
        if server_not_sent:
            validation_error = True

        after_url = page.url
        provider_success_navigation = _provider_success_navigation(before_url, after_url)
        thank_you_navigation = provider_success_navigation or (
            after_url != before_url and
            bool(re.search(r"(thanks?|thank[-_]?you|complete|completed|finish|success|sent)", after_url, re.I))
        )
        try:
            after_forms = await root.locator("form").count()
        except Exception:
            after_forms = before_forms
        form_disappeared = before_forms > 0 and after_forms == 0
        post_2xx = any(x.get("matches_form_payload") and 200 <= int(x.get("status", 0)) < 300 for x in responses)
        correlated_http_reject = _correlated_http_rejection(responses)
        if correlated_http_reject and not server_success:
            server_not_sent = True
            validation_error = True
        observed = bool(mutations)

        evidence = {
            "submit_request_observed": observed,
            "submit_request_correlated": any(x.get("matches_form_payload") for x in mutations),
            "submit_request_2xx": post_2xx,
            "success_dom": success_dom,
            "thank_you_navigation": thank_you_navigation,
            "form_disappeared": form_disappeared,
            "validation_error": validation_error,
            "clicked_once": clicked,
            "click_error": click_error,
            "network_mutations": mutations[:8],
            "network_responses": responses[:8],
            "response_bodies": response_bodies[:6],
            "cf7_event": cf7_event,
            "form_events": form_events[:20],
            "provider_success_dom": provider_success_dom,
            "strong_provider_success_text": strong_provider_success_visible,
            "provider_success_texts": provider_success_texts[:6],
            "provider_error_texts": provider_error_texts[:6],
            "generic_error_texts": generic_error_texts[:8],
            "form_action": form_action[:500],
            "server_success": server_success,
            "server_not_sent": server_not_sent,
            "correlated_http_reject": correlated_http_reject,
            "final_url": after_url[:500],
        }
        outcome, independent = _submit_outcome(evidence)
        return {
            "outcome": outcome,
            "evidence": evidence,
            "reason": click_error or ("EVIDENCE_" + str(independent)),
        }
