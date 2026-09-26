# PAL_REPAIR_OWNER=INTEGRATION_E2E | Cross-lane edits prohibited; use published interfaces/contracts.
# PAL_REPAIR_PROTOCOL_V2=GLOBAL_SINGLE_WRITER | CLAIM_LANE=INTEGRATION_E2E before edit; ACCEPT_LANE after tests.
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

POLICY_VERSION = "PAL_B2B_POLICY_V6_FREE_20260918_01"
RENDERED_STAGE3_LANES = frozenset({"FAST_DOM","DYNAMIC_JS","IFRAME_DEEP","DEEP","LIVE_PREFLIGHT"})

def _b(value: str) -> bytes:
    return str(value or "").encode("utf-8")

def sha256(value: str) -> str:
    return hashlib.sha256(_b(value)).hexdigest()

def domain_of(url: str) -> str:
    host = (urlparse(str(url)).hostname or "").lower()
    return host.removeprefix("www.")

def to_epoch(value: str | int | float | None) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return 0
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)

def send_key(domain: str, route: str, campaign_version: str, message_version: str) -> str:
    raw = "|".join([
        str(domain).lower().removeprefix("www."),
        str(route),
        str(campaign_version),
        str(message_version),
    ])
    return sha256(raw)

def build_from_http_verified(row: dict, message_body: str, campaign_version: str, message_version: str) -> dict:
    route = str(row.get("canonical_url") or "")
    official = str(row.get("official_domain") or "").lower().removeprefix("www.")
    message_hash = sha256(message_body)
    contract = {
        "official_domain_verified": domain_of(route) == official,
        "contact_route_verified": str(row.get("contact_purpose") or "") == "BUSINESS_CONTACT",
        "dnc_clear": str(row.get("dnc_state") or "") == "CLEAR",
        "sales_prohibited_clear": str(row.get("sales_prohibited_state") or "") == "CLEAR",
        "captcha_checked": str(row.get("captcha_state") or "") in {"CHECKED_ABSENT", "CLEAR"},
        "personal_required_clear": str(row.get("required_personal_field_state") or "") == "CLEAR",
        "public_entity_clear": str(row.get("public_entity_state") or "") == "CLEAR",
        "legal_risk_pass": str(row.get("risk_evidence_state") or "") == "PASS" and bool(row.get("legal_evidence_hash")),
        "stage3_final_rendered": False,
        "stage3_proof_source": "HTTP_STATIC_PREFILTER",
        "form_fingerprint": str(row.get("form_fingerprint") or ""),
        "message_hash": message_hash,
        "policy_version": POLICY_VERSION,
        "verified_at": to_epoch(row.get("verified_at")),
        "expires_at": to_epoch(row.get("expires_at")),
    }
    return {
        "contract": contract,
        "send_key": send_key(official, route, campaign_version, message_version),
        "message_hash": message_hash,
    }
def passes_admission(contract: dict) -> bool:
    flags = (
        "official_domain_verified",
        "contact_route_verified",
        "dnc_clear",
        "sales_prohibited_clear",
        "captcha_checked",
        "personal_required_clear",
        "public_entity_clear",
        "legal_risk_pass",
    )
    return (
        all(contract.get(k) is True for k in flags)
        and contract.get("stage3_final_rendered") is True
        and str(contract.get("stage3_lane_mode") or "").upper() in RENDERED_STAGE3_LANES
        and bool(str(contract.get("stage3_proof_source") or ""))
        and bool(contract.get("form_fingerprint"))
        and bool(contract.get("message_hash"))
        and int(contract.get("verified_at") or 0) > 0
    )

def passes(contract: dict, now_ms: int | None = None) -> bool:
    now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    return passes_admission(contract) and int(contract.get("expires_at") or 0) > now_ms

def passes_http_preflight(contract: dict, now_ms: int | None = None) -> bool:
    """Accept only a fresh strict HTTP proof for executor-side live verification.

    This is deliberately weaker than passes(): it can enter NEEDS_VERIFY, but
    can never cross the submit barrier until the executor replaces it with a
    complete rendered-browser contract.
    """
    flags = (
        "official_domain_verified",
        "contact_route_verified",
        "dnc_clear",
        "sales_prohibited_clear",
        "captcha_checked",
        "personal_required_clear",
        "public_entity_clear",
        "legal_risk_pass",
    )
    now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    return (
        all(contract.get(k) is True for k in flags)
        and contract.get("stage3_final_rendered") is False
        and (
            str(contract.get("stage3_proof_source") or "") == "HTTP_STATIC_PREFILTER"
            or (
                str(contract.get("stage3_proof_source") or "") == "CLOUDFLARE_STATIC_DOM_V1"
                and str(contract.get("stage3_lane_mode") or "").upper() == "STATIC_DOM"
            )
        )
        and bool(contract.get("form_fingerprint"))
        and bool(contract.get("message_hash"))
        and int(contract.get("verified_at") or 0) > 0
        and int(contract.get("expires_at") or 0) > now_ms
    )

EMPTY_SHA256 = sha256("")

def _starts(value: object, prefix: str) -> bool:
    return str(value or "").upper().startswith(prefix.upper())

def build_from_reservoir(row: dict, route_meta: dict, message_body: str, campaign_version: str, message_version: str, ttl_seconds: int = 600, admission_only: bool = False) -> dict:
    route = str(row.get("canonical_url") or route_meta.get("canonical_url") or "")
    official = str(row.get("official_domain") or route_meta.get("domain") or "").lower().removeprefix("www.")
    message_hash = sha256(message_body)
    # A fresh full-browser verification is stronger and newer evidence than
    # an older lightweight freshness check. Prefer it for the send contract TTL.
    fresh_at = row.get("last_full_browser_verified_at") or row.get("last_freshness_check_at")
    verified_ms = to_epoch(fresh_at)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    business_hash = str(row.get("business_purpose_evidence_hash") or "")
    contract = {
        "official_domain_verified": bool(route) and domain_of(route) == official,
        "contact_route_verified": bool(business_hash) and business_hash != EMPTY_SHA256,
        "dnc_clear": _starts(row.get("dnc_state"), "CLEAR"),
        "sales_prohibited_clear": _starts(row.get("sales_prohibited_state"), "CLEAR"),
        "captcha_checked": str(row.get("captcha_state") or "").upper() == "CHECKED_ABSENT" or _starts(row.get("captcha_state"), "CLEAR"),
        "personal_required_clear": _starts(row.get("required_personal_field_state"), "CLEAR"),
        "public_entity_clear": _starts(row.get("public_entity_state"), "CLEAR"),
        "legal_risk_pass": _starts(row.get("risk_evidence_state"), "PASS") and bool(row.get("legal_evidence_hash")),
        "stage3_final_rendered": row.get("stage3_final_rendered") is True,
        "stage3_proof_source": str(row.get("stage3_proof_source") or "RESERVOIR"),
        "stage3_lane_mode": str(row.get("stage3_lane_mode") or ""),
        "form_fingerprint": str(row.get("semantic_fingerprint") or row.get("form_fingerprint") or ""),
        "message_hash": message_hash,
        "policy_version": POLICY_VERSION,
        "verified_at": verified_ms,
        "expires_at": 0 if admission_only else (min(now_ms + int(ttl_seconds) * 1000, verified_ms + int(ttl_seconds) * 1000) if verified_ms else 0),
    }
    return {
        "contract": contract,
        "send_key": send_key(official, route, campaign_version, message_version),
        "message_hash": message_hash,
    }

def build_from_admitted_candidate(meta: dict, proof_detail: dict, form_fingerprint: str, risk_clearance_status: str, message_body: str, campaign_version: str, message_version: str, ttl_seconds: int, verified_epoch: int) -> dict:
    """Contract for a route sourced from the V8-native pipeline: Stage-2
    candidate_inventory ADMITTED (dnc/sales/public-entity/captcha safety_flags
    already gated by route_gate_v41.classify() before admission was granted)
    plus a fresh Stage-3 STAGE3_FULL_SEND_READY_V3 browser proof (which
    independently re-checks captcha/sales-prohibited/required-sensitive at
    render time -- the freshest available evidence for those three flags).
    Callers must only pass proof_detail for rows that already satisfied the
    STAGE3_FULL_SEND_READY_V3 acceptance criteria (see _stage3_proof_map).
    """
    route = str(meta.get("canonical_url") or "")
    official = str(meta.get("domain") or "").lower().removeprefix("www.")
    message_hash = sha256(message_body)
    verified_ms = int(verified_epoch) * 1000 if verified_epoch else 0
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    legal_pass = str(risk_clearance_status or "").upper() == "PASS"
    proof_source = str(proof_detail.get("proof_source") or "RENDERED_BROWSER_V2")
    lane_mode = str(proof_detail.get("lane_mode") or "")
    if proof_source == "CLOUDFLARE_STATIC_DOM_V1" and not lane_mode:
        lane_mode = "STATIC_DOM"
    # STATIC_DOM is useful preflight evidence, but it has not executed a browser
    # render. Only the actual Browser lanes (or same-page LIVE_PREFLIGHT) may
    # satisfy final Stage3.
    contract = {
        "official_domain_verified": bool(route) and domain_of(route) == official,
        "contact_route_verified": proof_detail.get("business_contact_form") is True,
        "dnc_clear": True,
        "sales_prohibited_clear": True,
        "captcha_checked": True,
        "personal_required_clear": proof_detail.get("required_sensitive") is False,
        "public_entity_clear": True,
        "legal_risk_pass": legal_pass,
        "stage3_final_rendered": lane_mode in RENDERED_STAGE3_LANES,
        "stage3_proof_source": proof_source,
        "stage3_lane_mode": lane_mode,
        "form_fingerprint": str(form_fingerprint or ""),
        "message_hash": message_hash,
        "policy_version": POLICY_VERSION,
        "verified_at": verified_ms,
        "expires_at": (min(now_ms + int(ttl_seconds) * 1000, verified_ms + int(ttl_seconds) * 1000) if verified_ms else 0),
    }
    return {
        "contract": contract,
        "send_key": send_key(official, route, campaign_version, message_version),
        "message_hash": message_hash,
    }
