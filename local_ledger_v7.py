# PAL_REPAIR_OWNER=INTEGRATION_E2E | Cross-lane edits prohibited; use published interfaces/contracts.
# PAL_REPAIR_PROTOCOL_V2=GLOBAL_SINGLE_WRITER | CLAIM_LANE=INTEGRATION_E2E before edit; ACCEPT_LANE after tests.
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from safety_contract_v6 import passes_http_preflight

HERE = Path(__file__).resolve().parent
B2B = HERE.parent
DB = HERE / "local_production_v6.sqlite3"
V41 = Path(os.getenv("PAL_V6_V41_DB", str(B2B / "v41" / "production_v41.sqlite3"))).expanduser()
LEGACY = Path(os.getenv("PAL_V6_LEGACY_LEDGER", str(B2B / "outreach_ledger_v1.jsonl"))).expanduser()

TERMINAL = {
    "SENT_CONFIRMED",
    "CONFIRMED_NOT_SENT",
    "SAFETY_BLOCKED",
    "AMBIGUOUS_HOLD",
    "TECH_FAILED_FINAL",
}

# These are terminals observed in the V6 live executor before the Cloudflare
# free-tier rows-read quota was exhausted. Keep them protected during local
# fallback. Legacy history is loaded separately below.
KNOWN_RECENT_PROTECTED_DOMAINS = {
    "disks.co.uk",
    "cpfl-tvs.com",
    "grcarr.com",
    "bricktiles.com",
    "motionwell.com.sg",
    "natural-rubber.com",
    "ht2000.co.uk",
    "matsushima.jp",
    "shallbe.jp",
    "toeisangyo.jp",
    "meisters-g.tokyo.jp",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def host(value: str) -> str:
    return (urlparse(str(value or "")).hostname or "").lower().removeprefix("www.")


def all_safety_pass(c: dict) -> bool:
    keys = (
        "official_domain_verified",
        "contact_route_verified",
        "dnc_clear",
        "sales_prohibited_clear",
        "captcha_checked",
        "personal_required_clear",
        "public_entity_clear",
        "legal_risk_pass",
    )
    rendered_lanes = {"FAST_DOM", "DYNAMIC_JS", "IFRAME_DEEP", "DEEP", "LIVE_PREFLIGHT"}
    return (
        all(c.get(k) is True for k in keys)
        and c.get("stage3_final_rendered") is True
        and str(c.get("stage3_lane_mode") or "").upper() in rendered_lanes
        and bool(str(c.get("stage3_proof_source") or ""))
        and bool(c.get("form_fingerprint"))
        and bool(c.get("message_hash"))
    )


def _provider_success_event(e: dict) -> bool:
    event_types={
        str(x.get("type") or "")
        for x in (e.get("form_events") or [])
        if isinstance(x,dict)
    }
    cf7=e.get("cf7_event") if isinstance(e.get("cf7_event"),dict) else {}
    if cf7:
        event_types.add(str(cf7.get("type") or ""))
    return bool(event_types & {
        "wpcf7mailsent","wpformsAjaxSubmitSuccess",
        "gform_confirmation_loaded","fluentform_submission_success",
    })


def deterministic_not_sent_evidence(e: dict) -> bool:
    """Canonical pre/post-click evidence that proves this exact form was not sent.

    Browser classification and durable-ledger admission both call this helper so
    they cannot drift. Unrelated telemetry does not create delivery ambiguity:
    only a form-correlated request or a positive provider signal does.
    """
    if not isinstance(e,dict):
        return False
    positive=bool(
        e.get("server_success") is True
        or e.get("success_dom") is True
        or e.get("thank_you_navigation") is True
        or (e.get("form_disappeared") is True and e.get("validation_error") is False)
        or _provider_success_event(e)
    )
    correlated=e.get("submit_request_correlated") is True

    # Explicit provider/server non-delivery is definitive only when it does not
    # conflict with a positive delivery signal.
    if e.get("server_not_sent") is True and not positive:
        return True

    # Playwright timed out before any click/request could cross the submit
    # action. This is a pre-submit failure, not an ambiguous delivery.
    if (
        e.get("click_error")
        and e.get("clicked_once") is False
        and e.get("submit_request_observed") is False
        and not correlated
        and not positive
        and e.get("form_disappeared") is not True
    ):
        return True

    # A visible/server validation failure with no request correlated to the
    # filled payload proves the form did not submit. Analytics/telemetry traffic
    # may set submit_request_observed=True, so correlation is the decisive bit.
    if (
        e.get("validation_error") is True
        and not correlated
        and not positive
        and e.get("server_success") is not True
    ):
        return True
    return False


def deterministic_provider_not_sent(e: dict) -> bool:
    """Compatibility alias retained for older callers."""
    return deterministic_not_sent_evidence(e)


def evidence_pass(e: dict) -> bool:
    if e.get("server_not_sent") is True:
        return False
    if (
        e.get("validation_error") is True
        and e.get("server_success") is not True
        and e.get("thank_you_navigation") is not True
    ):
        return False
    independent = sum(
        bool(v)
        for v in (
            e.get("submit_request_2xx") is True,
            e.get("server_success") is True,
            e.get("success_dom") is True,
            e.get("thank_you_navigation") is True,
            e.get("form_disappeared") is True and e.get("validation_error") is False,
        )
    )
    return independent >= 2


@dataclass
class LocalLedgerClient:
    db_path: Path = DB
    timeout: float = 12.0

    @classmethod
    def from_env(cls) -> "LocalLedgerClient":
        raw = os.getenv("PAL_V6_LOCAL_LEDGER_DB", "").strip()
        path = Path(raw).expanduser() if raw else DB
        obj = cls(path)
        obj._init()
        return obj

    def _con(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("PRAGMA busy_timeout=15000")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def _init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = self._con()
        try:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta(
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS protected_companies(
                  domain TEXT PRIMARY KEY,
                  company_id TEXT,
                  reason TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_protected_company_id
                  ON protected_companies(company_id);

                CREATE TABLE IF NOT EXISTS send_jobs(
                  job_id TEXT PRIMARY KEY,
                  send_key TEXT UNIQUE NOT NULL,
                  company_id TEXT NOT NULL,
                  normalized_domain TEXT NOT NULL,
                  route_id TEXT NOT NULL,
                  canonical_route TEXT NOT NULL,
                  market TEXT NOT NULL,
                  campaign_version TEXT NOT NULL,
                  message_version TEXT NOT NULL,
                  message_body TEXT NOT NULL,
                  priority_score REAL NOT NULL DEFAULT 0,
                  state TEXT NOT NULL,
                  retry_count INTEGER NOT NULL DEFAULT 0,
                  next_eligible_at INTEGER NOT NULL DEFAULT 0,
                  lease_id TEXT,
                  lease_expires_at INTEGER,
                  executor_id TEXT,
                  safety_contract_json TEXT NOT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_claim
                  ON send_jobs(state,market,campaign_version,message_version,retry_count,priority_score,next_eligible_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_company
                  ON send_jobs(company_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_domain
                  ON send_jobs(normalized_domain);

                CREATE TABLE IF NOT EXISTS send_attempts(
                  attempt_id TEXT PRIMARY KEY,
                  job_id TEXT NOT NULL UNIQUE,
                  send_key TEXT NOT NULL,
                  state TEXT NOT NULL,
                  started_at INTEGER NOT NULL,
                  submit_started_at INTEGER NOT NULL,
                  ended_at INTEGER,
                  detail_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS send_attempt_history(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  attempt_id TEXT NOT NULL,
                  job_id TEXT NOT NULL,
                  send_key TEXT NOT NULL,
                  state TEXT NOT NULL,
                  started_at INTEGER NOT NULL,
                  submit_started_at INTEGER NOT NULL,
                  ended_at INTEGER,
                  detail_json TEXT NOT NULL,
                  archived_at INTEGER NOT NULL,
                  archive_reason TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_attempt_history_job ON send_attempt_history(job_id,archived_at);

                CREATE TABLE IF NOT EXISTS terminal_receipts(
                  job_id TEXT PRIMARY KEY,
                  terminal_state TEXT NOT NULL,
                  evidence_json TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS terminal_receipt_history(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  job_id TEXT NOT NULL,
                  terminal_state TEXT NOT NULL,
                  evidence_json TEXT NOT NULL,
                  created_at INTEGER NOT NULL,
                  recovered_at INTEGER NOT NULL,
                  recovery_reason TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_terminal_history_job ON terminal_receipt_history(job_id,recovered_at);

                CREATE TABLE IF NOT EXISTS heartbeat(
                  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                  at INTEGER NOT NULL,
                  executor_id TEXT NOT NULL,
                  version TEXT NOT NULL,
                  active_slots INTEGER NOT NULL
                );
                """
            )
        finally:
            c.close()
        self._seed_history_once()

    def _seed_history_once(self) -> None:
        c = self._con()
        try:
            row = c.execute("SELECT value FROM meta WHERE key='history_seeded_v2'").fetchone()
            if row:
                return
        finally:
            c.close()

        route_ids: set[int] = set()
        domains: set[str] = set(KNOWN_RECENT_PROTECTED_DOMAINS)
        if LEGACY.exists():
            try:
                with LEGACY.open(errors="ignore") as f:
                    for line in f:
                        try:
                            row = json.loads(line)
                        except Exception:
                            continue
                        status = str(row.get("status") or "")
                        attempted = row.get("send_attempted") is True
                        if not attempted and status not in {
                            "SENT_VERIFIED", "SENT_CONFIRMED", "AMBIGUOUS_HOLD",
                            "POSSIBLE_DELIVERY", "SENT_UNVERIFIED", "SEND_UNVERIFIED",
                        }:
                            continue
                        d = host(row.get("contact_url") or row.get("final_url") or "")
                        if d:
                            domains.add(d)
                        pid = str(row.get("prospect_id") or "")
                        if pid.startswith("v5_"):
                            try:
                                route_ids.add(int(pid.split("_", 1)[1]))
                            except Exception:
                                pass
            except Exception:
                pass

        company_for_domain: dict[str, str] = {}
        if V41.exists():
            vc = sqlite3.connect(f"file:{V41.resolve()}?mode=ro", uri=True, timeout=10)
            vc.row_factory = sqlite3.Row
            try:
                if route_ids:
                    ids = sorted(route_ids)
                    for i in range(0, len(ids), 500):
                        part = ids[i:i+500]
                        marks = ",".join("?" for _ in part)
                        for r in vc.execute(
                            f"""SELECT r.id,c.id company_id,c.domain
                                FROM routes r JOIN companies c ON c.id=r.company_id
                                WHERE r.id IN ({marks})""",
                            part,
                        ):
                            d = str(r["domain"] or "").lower().removeprefix("www.")
                            if d:
                                domains.add(d)
                                company_for_domain[d] = str(r["company_id"])
                doms = sorted(domains)
                for i in range(0, len(doms), 400):
                    part = doms[i:i+400]
                    marks = ",".join("?" for _ in part)
                    for r in vc.execute(
                        f"""SELECT id company_id,domain FROM companies
                            WHERE lower(replace(domain,'www.','')) IN ({marks})""",
                        [d.lower() for d in part],
                    ):
                        d = str(r["domain"] or "").lower().removeprefix("www.")
                        company_for_domain[d] = str(r["company_id"])
            finally:
                vc.close()

        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            ts = now_ms()
            for d in sorted(domains):
                c.execute(
                    """INSERT OR IGNORE INTO protected_companies(domain,company_id,reason,created_at)
                       VALUES(?,?,?,?)""",
                    (d, company_for_domain.get(d), "HISTORICAL_SEND_OR_POSSIBLE", ts),
                )
            c.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('history_seeded_v2',?)",
                (json.dumps({"domains": len(domains), "route_ids": len(route_ids), "at": ts}),),
            )
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def _protected(self, c: sqlite3.Connection, company_id: str, domain: str) -> bool:
        row = c.execute(
            """SELECT 1 FROM protected_companies
               WHERE domain=? OR (company_id IS NOT NULL AND company_id=?)
               LIMIT 1""",
            (domain, company_id),
        ).fetchone()
        if row:
            return True
        row = c.execute(
            """SELECT 1 FROM terminal_receipts t
               JOIN send_jobs j ON j.job_id=t.job_id
               WHERE (j.company_id=? OR j.normalized_domain=?)
                 AND t.terminal_state IN ('SENT_CONFIRMED','AMBIGUOUS_HOLD')
               LIMIT 1""",
            (company_id, domain),
        ).fetchone()
        return bool(row)

    def _terminalize(self, c: sqlite3.Connection, job: sqlite3.Row, state: str, evidence: dict) -> str:
        ts = now_ms()
        c.execute(
            """INSERT OR IGNORE INTO terminal_receipts(job_id,terminal_state,evidence_json,created_at)
               VALUES(?,?,?,?)""",
            (job["job_id"], state, json.dumps(evidence, ensure_ascii=False), ts),
        )
        c.execute(
            """UPDATE send_jobs
               SET state=?,lease_id=NULL,lease_expires_at=NULL,executor_id=NULL,updated_at=?
               WHERE job_id=?""",
            (state, ts, job["job_id"]),
        )
        if state in {"SENT_CONFIRMED", "AMBIGUOUS_HOLD"}:
            c.execute(
                """INSERT INTO protected_companies(domain,company_id,reason,created_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(domain) DO UPDATE SET
                     company_id=COALESCE(protected_companies.company_id,excluded.company_id),
                     reason=excluded.reason""",
                (job["normalized_domain"], job["company_id"], state, ts),
            )
        return state

    def _reconcile(self, c: sqlite3.Connection, ts: int) -> None:
        # A stale post-barrier job is never retried; it is ambiguous.
        stale_submit = list(c.execute(
            """SELECT * FROM send_jobs
               WHERE state='SUBMIT_STARTED' AND updated_at<=?""",
            (ts - 60000,),
        ))
        for job in stale_submit:
            self._terminalize(c, job, "AMBIGUOUS_HOLD", {"reason": "STALE_POST_BARRIER_LOCAL_FAILOVER"})

        # Enforce one in-flight/reverify job per company/domain even for legacy rows
        # created before the transactional intake guard existed. If the company is
        # already protected by a confirmed/ambiguous terminal, no active/reverify
        # job may survive. Otherwise preserve exactly one best job and supersede the
        # rest before they can churn through verification again.
        activeish = list(c.execute(
            """SELECT * FROM send_jobs
               WHERE state IN ('READY','VERIFIED','LEASED','SUBMIT_STARTED',
                               'NEEDS_VERIFY','STALE_REVERIFY')
               ORDER BY updated_at DESC, created_at DESC"""
        ))
        grouped = {}
        for job in activeish:
            key = str(job["company_id"] or "").strip() or ("domain:" + str(job["normalized_domain"] or "").lower())
            grouped.setdefault(key, []).append(job)
        state_rank = {
            "SUBMIT_STARTED": 0, "LEASED": 1, "READY": 2, "VERIFIED": 3,
            "NEEDS_VERIFY": 4, "STALE_REVERIFY": 5,
        }
        for jobs in grouped.values():
            protected = self._protected(
                c,
                str(jobs[0]["company_id"] or ""),
                str(jobs[0]["normalized_domain"] or "").lower(),
            )
            if protected:
                keep = None
                losers = jobs
                reason = "COMPANY_ALREADY_PROTECTED_SUPERSEDED"
            elif len(jobs) > 1:
                keep = sorted(
                    jobs,
                    key=lambda j: (
                        state_rank.get(str(j["state"] or ""), 99),
                        -int(j["updated_at"] or 0),
                        -int(j["created_at"] or 0),
                    ),
                )[0]
                losers = [j for j in jobs if j["job_id"] != keep["job_id"]]
                reason = "DUPLICATE_ACTIVE_JOB_SUPERSEDED"
            else:
                continue
            for job in losers:
                self._terminalize(
                    c, job, "TECH_FAILED_FINAL",
                    {
                        "reason": reason,
                        "superseded_by_job_id": str(keep["job_id"]) if keep is not None else None,
                        "submit_request_observed": False,
                        "deterministic": True,
                    },
                )

        # VERIFIED must mean genuinely send-ready. Older V6 rows could retain a
        # placeholder/expired contract while still carrying the VERIFIED label.
        # Move those rows out of the claimable queue; a later valid intake can
        # refresh the same send_key back to READY/VERIFIED without losing history.
        for job in list(c.execute("SELECT * FROM send_jobs WHERE state IN ('READY','VERIFIED','NEEDS_VERIFY')")):
            try:
                contract = json.loads(job["safety_contract_json"] or "{}")
            except Exception:
                contract = {}
            contract_ok = (
                passes_http_preflight(contract, ts)
                if job["state"] == "NEEDS_VERIFY"
                else all_safety_pass(contract)
            )
            if (not contract_ok or
                    int(contract.get("expires_at") or 0) <= ts + 60000):
                c.execute(
                    """UPDATE send_jobs SET state='STALE_REVERIFY',lease_id=NULL,
                       lease_expires_at=NULL,executor_id=NULL,updated_at=? WHERE job_id=?""",
                    (ts, job["job_id"]),
                )

        # An expired lease is reusable only while its authoritative contract is
        # still complete and has at least a one-minute safety margin. Otherwise
        # it also returns to re-verification instead of masquerading as VERIFIED.
        expired = list(c.execute(
            "SELECT * FROM send_jobs WHERE state='LEASED' AND COALESCE(lease_expires_at,0)<=?",
            (ts,),
        ))
        for job in expired:
            try:
                contract = json.loads(job["safety_contract_json"] or "{}")
            except Exception:
                contract = {}
            fresh_margin = int(contract.get("expires_at") or 0) > ts + 60000
            if all_safety_pass(contract) and fresh_margin:
                state = 'VERIFIED'
            elif passes_http_preflight(contract, ts) and fresh_margin:
                # A leased preflight-only job may lose its executor during a
                # restart/resource handoff before any submit barrier. Preserve
                # its verification requirement instead of discarding a still
                # fresh strict HTTP/STATIC_DOM proof as STALE_REVERIFY.
                state = 'NEEDS_VERIFY'
            else:
                state = 'STALE_REVERIFY'
            c.execute(
                """UPDATE send_jobs SET state=?,lease_id=NULL,lease_expires_at=NULL,
                   executor_id=NULL,updated_at=? WHERE job_id=?""",
                (state, ts, job["job_id"]),
            )

    def intake(self, body: dict) -> dict:
        contract = dict(body.get("safety_contract") or {})
        ts = now_ms()
        send_key = str(body.get("send_key") or "")
        company_id = str(body.get("company_id") or "")
        domain = str(body.get("normalized_company_domain") or "").lower().removeprefix("www.")
        route_id = str(body.get("route_id") or "")
        route = str(body.get("canonical_route") or "")
        market = str(body.get("market") or "")
        message_body = str(body.get("message_body") or "")
        if not all((send_key, company_id, domain, route_id, route, market, message_body)):
            return {"error": "INVALID_IDENTITY_OR_MESSAGE"}
        if str(contract.get("message_hash") or "") != sha256_text(message_body):
            return {"error": "MESSAGE_HASH_MISMATCH"}

        candidate_only = (
            body.get("candidate_only") is True
            and body.get("admission_legal_verified") is True
            and body.get("admission_route_safety_clear") is True
            and contract.get("official_domain_verified") is True
            and bool(contract.get("message_hash"))
            and (
                int(body.get("form_shape") or 0) == 1
                or body.get("candidate_reverify_only") is True
            )
        )
        admission_only = body.get("admission_only") is True
        # VERIFIED means genuinely send-ready. Candidate-only rows must stay
        # outside the production ledger until Verify has completed every safety
        # gate and produced a non-empty form fingerprint.
        preflight_only = (
            body.get("preflight_only") is True
            and passes_http_preflight(contract, ts)
        )
        if candidate_only or admission_only:
            return {"error": "VERIFY_REQUIRED_BEFORE_LEDGER"}
        elif preflight_only:
            state = "NEEDS_VERIFY"
        elif all_safety_pass(contract) and int(contract.get("expires_at") or 0) > ts:
            state = "READY" if int(body.get("next_eligible_at") or 0) <= ts else "VERIFIED"
        else:
            return {"error": "ADMISSION_SAFETY_INCOMPLETE"}

        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            if self._protected(c, company_id, domain):
                c.rollback()
                return {"duplicate": True, "state": "COMPANY_ALREADY_CONTACTED_OR_AMBIGUOUS"}
            # One company/domain may have only one in-flight send job at a time,
            # even when another official form produces a different send_key.
            # BEGIN IMMEDIATE serializes this check with insert/update.
            other_active = c.execute(
                """SELECT job_id,state,send_key FROM send_jobs
                   WHERE (company_id=? OR normalized_domain=?)
                     AND send_key<>?
                     AND state IN ('READY','VERIFIED','NEEDS_VERIFY','LEASED','SUBMIT_STARTED')
                   LIMIT 1""",
                (company_id, domain, send_key),
            ).fetchone()
            if other_active:
                c.commit()
                return {"duplicate": True, "state": "COMPANY_ACTIVE_JOB",
                        "active_state": str(other_active["state"] or "")}
            existing = c.execute("SELECT * FROM send_jobs WHERE send_key=?", (send_key,)).fetchone()
            priority = float(body.get("priority_score") or 0.0)
            if existing:
                # TECH_FAILED_FINAL is produced only by pre_submit_fail() while the job
                # is still LEASED, before the submit barrier. If a fresh authoritative
                # contract now passes every safety gate, recover that same idempotent
                # job instead of permanently discarding a newly verified sendable form.
                # Post-submit terminal outcomes are route-terminal and never recovered.
                if (existing["state"] == "TECH_FAILED_FINAL"
                        and all_safety_pass(contract)
                        and int(contract.get("expires_at") or 0) > ts):
                    prior = c.execute("SELECT * FROM terminal_receipts WHERE job_id=? AND terminal_state=?",
                                      (existing["job_id"], existing["state"])).fetchone()
                    recoverable=True
                    try:
                        prior_ev=json.loads(prior["evidence_json"] or "{}") if prior else {}
                    except Exception:
                        prior_ev={}
                    prior_reason=str(prior_ev.get("reason") or "")
                    if prior_reason in {"DUPLICATE_ACTIVE_JOB_SUPERSEDED",
                                        "COMPANY_ALREADY_PROTECTED_SUPERSEDED"}:
                        recoverable=False

                    # A fresh timestamp alone is not a repaired form.  Stage5
                    # feedback deliberately invalidates a failed proof and asks
                    # Stage2/3 for a better route or a stronger rendered proof.
                    # Re-admitting the same route with the same proof modality
                    # creates a tight TECH_FAILED_FINAL -> fresh proof -> READY
                    # loop that burns executor slots without improving evidence.
                    try:
                        old_contract=json.loads(existing["safety_contract_json"] or "{}")
                    except Exception:
                        old_contract={}
                    old_route_id=str(existing["route_id"] or "")
                    old_route=str(existing["canonical_route"] or "")
                    old_source=str(old_contract.get("stage3_proof_source") or "")
                    new_source=str(contract.get("stage3_proof_source") or "")
                    old_lane=str(old_contract.get("stage3_lane_mode") or "").upper()
                    new_lane=str(contract.get("stage3_lane_mode") or "").upper()
                    old_fp=str(old_contract.get("form_fingerprint") or "")
                    new_fp=str(contract.get("form_fingerprint") or "")
                    route_changed=(route_id!=old_route_id or route!=old_route)
                    fingerprint_changed=bool(old_fp and new_fp and old_fp!=new_fp)
                    source_rank={"":0,"HTTP_FIRST_V2_STATIC_ONLY":1,
                                 "CLOUDFLARE_STATIC_DOM_V1":1,
                                 "RENDERED_BROWSER_V2":2,"LIVE_BROWSER_PREFLIGHT":3}
                    lane_rank={"":0,"STATIC_DOM":1,"FAST_DOM":2,"DYNAMIC_JS":3,
                               "IFRAME_DEEP":4,"DEEP":4,"LIVE_PREFLIGHT":5}
                    proof_modality_improved=(
                        source_rank.get(new_source,0)>source_rank.get(old_source,0)
                        or lane_rank.get(new_lane,0)>lane_rank.get(old_lane,0)
                    )
                    fingerprint_repair_reasons={
                        "PRE_SUBMIT_REQUIRED_MISSING",
                        "BUSINESS_CONTACT_FORM_NOT_FOUND",
                    }
                    material_repair=(
                        route_changed
                        or proof_modality_improved
                        or (fingerprint_changed and prior_reason in fingerprint_repair_reasons)
                    )
                    # Keep pre-submit technical recovery bounded. Post-submit
                    # CONFIRMED_NOT_SENT is never eligible for same-route recovery.
                    recovered_before=int(c.execute("SELECT count(*) FROM terminal_receipt_history WHERE job_id=?",
                                                   (existing["job_id"],)).fetchone()[0] or 0)
                    repairable_pre_submit={
                        "PRE_SUBMIT_REQUIRED_MISSING","BUSINESS_CONTACT_FORM_NOT_FOUND",
                        "FINAL_SUBMIT_CONTROL_NOT_FOUND","CONFIRM_CONTROL_NOT_FOUND",
                        "SUBMIT_OR_CONFIRM_CONTROL_NOT_FOUND","FORM_NO_SAFE_DIRECT_STATIC_FORM",
                        "BROWSER_TIMEOUTERROR",
                    }
                    max_recoveries=2 if prior_reason in repairable_pre_submit else 1
                    if recovered_before>=max_recoveries:
                        recoverable=False
                    # Route/form-location failures require evidence that the
                    # repair actually changed something material.  Timeout-only
                    # failures may still use the bounded legacy recovery path.
                    if (prior_reason in repairable_pre_submit
                            and prior_reason!="BROWSER_TIMEOUTERROR"
                            and not material_repair):
                        recoverable=False
                    if recoverable and prior:
                        c.execute("""INSERT INTO terminal_receipt_history(
                            job_id,terminal_state,evidence_json,created_at,recovered_at,recovery_reason)
                            VALUES(?,?,?,?,?,?)""",
                            (prior["job_id"], prior["terminal_state"], prior["evidence_json"],
                             int(prior["created_at"]), ts, "FRESH_FINAL_FORM_VERIFY_PASS"))
                        attempt=c.execute("SELECT * FROM send_attempts WHERE job_id=?",(existing["job_id"],)).fetchone()
                        if attempt:
                            c.execute("""INSERT INTO send_attempt_history(
                                attempt_id,job_id,send_key,state,started_at,submit_started_at,ended_at,detail_json,archived_at,archive_reason)
                                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                (attempt["attempt_id"],attempt["job_id"],attempt["send_key"],attempt["state"],
                                 int(attempt["started_at"]),int(attempt["submit_started_at"]),attempt["ended_at"],
                                 attempt["detail_json"],ts,"FRESH_FINAL_FORM_VERIFY_PASS"))
                            c.execute("DELETE FROM send_attempts WHERE job_id=?",(existing["job_id"],))
                        c.execute("DELETE FROM terminal_receipts WHERE job_id=?", (existing["job_id"],))
                    elif not recoverable:
                        prior=None
                    if not prior:
                        # Do not reactivate anything whose non-delivery is not proven.
                        c.execute("UPDATE send_jobs SET priority_score=MAX(priority_score,?),updated_at=? WHERE send_key=?",
                                  (priority,ts,send_key))
                        c.commit()
                        return {"duplicate":True,"state":existing["state"],"priority_score":max(priority,float(existing["priority_score"] or 0))}
                    refreshed_state = "READY" if int(body.get("next_eligible_at") or 0) <= ts else "VERIFIED"
                    c.execute("""UPDATE send_jobs
                               SET priority_score=MAX(priority_score,?),state=?,retry_count=0,
                                   canonical_route=?,normalized_domain=?,market=?,message_body=?,
                                   campaign_version=?,message_version=?,next_eligible_at=?,safety_contract_json=?,lease_id=NULL,
                                   lease_expires_at=NULL,executor_id=NULL,updated_at=?
                               WHERE job_id=?""",
                              (priority, refreshed_state, route, domain, market, message_body,
                               str(body.get("campaign_version") or ""),str(body.get("message_version") or ""),
                               int(body.get("next_eligible_at") or 0), json.dumps(contract, ensure_ascii=False),
                               ts, existing["job_id"]))
                    c.commit()
                    return {"duplicate": True, "state": refreshed_state, "refreshed": True,
                            "recovered_pre_submit_tech_failure": True,
                            "priority_score": max(priority, float(existing["priority_score"] or 0))}
                if (existing["state"] not in TERMINAL
                        and (preflight_only or all_safety_pass(contract))
                        and int(contract.get("expires_at") or 0) > ts):
                    refreshed_state = (
                        "NEEDS_VERIFY" if preflight_only
                        else ("READY" if int(body.get("next_eligible_at") or 0) <= ts else "VERIFIED")
                    )
                    if existing["state"] not in {"LEASED", "SUBMIT_STARTED"}:
                        c.execute(
                            """UPDATE send_jobs
                               SET priority_score=MAX(priority_score,?),state=?,canonical_route=?,
                                   normalized_domain=?,market=?,message_body=?,next_eligible_at=?,
                                   safety_contract_json=?,updated_at=?
                               WHERE send_key=?""",
                            (
                                priority, refreshed_state, route, domain, market, message_body,
                                int(body.get("next_eligible_at") or 0),
                                json.dumps(contract, ensure_ascii=False), ts, send_key,
                            ),
                        )
                        c.commit()
                        return {"duplicate": True, "state": refreshed_state, "refreshed": True,
                                "priority_score": max(priority, float(existing["priority_score"] or 0))}
                c.execute(
                    """UPDATE send_jobs SET priority_score=MAX(priority_score,?),updated_at=?
                       WHERE send_key=?""",
                    (priority, ts, send_key),
                )
                c.commit()
                return {"duplicate": True, "state": existing["state"], "priority_score": max(priority, float(existing["priority_score"] or 0))}
            job_id = str(uuid.uuid4())
            c.execute(
                """INSERT INTO send_jobs(
                     job_id,send_key,company_id,normalized_domain,route_id,canonical_route,market,
                     campaign_version,message_version,message_body,priority_score,state,retry_count,
                     next_eligible_at,safety_contract_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, send_key, company_id, domain, route_id, route, market,
                    str(body.get("campaign_version") or ""), str(body.get("message_version") or ""),
                    message_body, priority, state, 0, int(body.get("next_eligible_at") or 0),
                    json.dumps(contract, ensure_ascii=False), ts, ts,
                ),
            )
            c.commit()
            return {"accepted": True, "job_id": job_id, "state": state}
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def intake_batch(self, payloads: list[dict]) -> dict:
        out = {
            "accepted": 0, "refreshed_sendable": 0, "effective_sendable": 0,
            "duplicates": 0, "errors": 0, "states": {},
            "accepted_route_ids": [], "refreshed_route_ids": [],
            "duplicate_route_ids": [], "error_route_ids": [],
            "route_states": {},
        }
        for payload in list(payloads or [])[:500]:
            try:
                rid = int(payload.get("route_id") or 0)
            except Exception:
                rid = 0
            try:
                r = self.intake(payload)
                state = str(r.get("state") or r.get("error") or "UNKNOWN")
                if r.get("duplicate"):
                    # A fresh proof can revive the same idempotent job back to
                    # READY/VERIFIED. That is a successful Stage4 handoff, not a
                    # dead duplicate. Keep duplicate accounting only for rows
                    # that remain non-sendable.
                    if r.get("refreshed") is True and state in {"READY","VERIFIED","NEEDS_VERIFY"}:
                        out["refreshed_sendable"] += 1
                        if rid > 0:
                            out["refreshed_route_ids"].append(rid)
                    else:
                        out["duplicates"] += 1
                        if rid > 0:
                            out["duplicate_route_ids"].append(rid)
                elif r.get("accepted"):
                    out["accepted"] += 1
                    if rid > 0:
                        out["accepted_route_ids"].append(rid)
                else:
                    out["errors"] += 1
                    if rid > 0:
                        out["error_route_ids"].append(rid)
                if rid > 0:
                    out["route_states"][str(rid)] = state
                out["states"][state] = int(out["states"].get(state, 0)) + 1
                out["effective_sendable"] = int(out["accepted"]) + int(out["refreshed_sendable"])
            except Exception as exc:
                out["errors"] += 1
                if rid > 0:
                    out["error_route_ids"].append(rid)
                    out["route_states"][str(rid)] = "ERROR_" + type(exc).__name__
        return out

    def reconcile(self) -> dict:
        ts = now_ms()
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            self._reconcile(c, ts)
            counts = {str(r[0]): int(r[1]) for r in c.execute(
                "SELECT state,count(*) FROM send_jobs GROUP BY state"
            )}
            c.commit()
            return {"status": "PASS", "states": counts}
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def claim(
        self,
        executor_id: str,
        version: str,
        limit: int = 2,
        allowed_markets: list[str] | None = None,
        campaign_version: str = "",
        message_version: str = "",
    ) -> dict:
        ts = now_ms()
        markets = [str(x) for x in (allowed_markets or []) if str(x)]
        if not markets:
            return {"jobs": [], "reason": "NO_OPEN_MARKETS"}
        limit = max(1, min(2, int(limit)))
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            self._reconcile(c, ts)
            marks = ",".join("?" for _ in markets)
            params: list[object] = [ts, ts + 60000, *markets]
            where = [
                "j.state IN ('READY','VERIFIED','NEEDS_VERIFY')",
                "j.next_eligible_at<=?",
                "COALESCE(json_extract(j.safety_contract_json,'$.expires_at'),0)>?",
                f"j.market IN ({marks})",
                """NOT EXISTS (
                    SELECT 1 FROM protected_companies p
                    WHERE p.domain=j.normalized_domain
                       OR (p.company_id IS NOT NULL AND p.company_id=j.company_id)
                )""",
                """NOT EXISTS (
                    SELECT 1 FROM terminal_receipts t2
                    JOIN send_jobs j2 ON j2.job_id=t2.job_id
                    WHERE (j2.company_id=j.company_id OR j2.normalized_domain=j.normalized_domain)
                      AND t2.terminal_state IN ('SENT_CONFIRMED','AMBIGUOUS_HOLD')
                )""",
            ]
            if campaign_version:
                where.append("j.campaign_version=?")
                params.append(str(campaign_version))
            if message_version:
                where.append("j.message_version=?")
                params.append(str(message_version))
            params.append(max(limit * 20, 40))
            rows = list(c.execute(
                f"""SELECT j.* FROM send_jobs j
                    WHERE {' AND '.join(where)}
                    ORDER BY
                             CASE WHEN coalesce(json_extract(j.safety_contract_json,'$.stage3_final_rendered'),0)=1
                                  THEN 0 ELSE 1 END,
                             CASE upper(coalesce(json_extract(j.safety_contract_json,'$.stage3_lane_mode'),''))
                                  WHEN 'LIVE_PREFLIGHT' THEN 0
                                  WHEN 'DYNAMIC_JS' THEN 1
                                  WHEN 'IFRAME_DEEP' THEN 2
                                  WHEN 'FAST_DOM' THEN 3
                                  WHEN 'DEEP' THEN 4
                                  WHEN 'STATIC_DOM' THEN 5
                                  ELSE 6 END,
                             COALESCE(json_extract(j.safety_contract_json,'$.expires_at'),9223372036854775807) ASC,
                             j.priority_score DESC,
                             j.retry_count ASC,
                             CASE j.state WHEN 'READY' THEN 0 WHEN 'VERIFIED' THEN 1 ELSE 2 END,
                             j.created_at
                    LIMIT ?""",
                params,
            ))
            claimed = []
            used_companies: set[str] = set()
            used_domains: set[str] = set()
            for row in rows:
                company_key=str(row["company_id"] or "")
                domain_key=str(row["normalized_domain"] or "").lower()
                if company_key in used_companies or domain_key in used_domains:
                    continue
                lease_id = str(uuid.uuid4())
                lease_exp = ts + 120000
                cur = c.execute(
                    """UPDATE send_jobs
                       SET state='LEASED',lease_id=?,lease_expires_at=?,executor_id=?,updated_at=?
                       WHERE job_id=? AND state IN ('READY','VERIFIED','NEEDS_VERIFY')""",
                    (lease_id, lease_exp, executor_id, ts, row["job_id"]),
                )
                if cur.rowcount != 1:
                    continue
                d = dict(row)
                d["state"] = "LEASED"
                d["lease_id"] = lease_id
                d["lease_expires_at"] = lease_exp
                d["executor_version"] = version
                d["safety_contract"] = json.loads(row["safety_contract_json"] or "{}")
                claimed.append(d)
                used_companies.add(company_key)
                used_domains.add(domain_key)
                if len(claimed) >= limit:
                    break
            c.commit()
            return {"jobs": claimed}
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def heartbeat(self, executor_id: str, version: str, active_slots: int) -> dict:
        c = self._con()
        try:
            c.execute(
                """INSERT INTO heartbeat(singleton,at,executor_id,version,active_slots)
                   VALUES(1,?,?,?,?)
                   ON CONFLICT(singleton) DO UPDATE SET
                     at=excluded.at,executor_id=excluded.executor_id,
                     version=excluded.version,active_slots=excluded.active_slots""",
                (now_ms(), str(executor_id), str(version), max(0, min(2, int(active_slots)))),
            )
            return {"ok": True}
        finally:
            c.close()

    def submit_started(self, body: dict) -> dict:
        ts = now_ms()
        job_id = str(body.get("job_id") or "")
        lease_id = str(body.get("lease_id") or "")
        final = dict(body.get("final_safety_contract") or {})
        if os.getenv("PAL_V6_PERMISSIONED_SEND_ONLY", "false").lower() == "true":
            basis = str(body.get("permission_basis") or "")
            evidence_hash = str(body.get("permission_evidence_hash") or "")
            candidate_id = body.get("permission_candidate_id")
            if (
                basis != "EXPLICIT_BUSINESS_INVITATION"
                or len(evidence_hash) != 64
                or not candidate_id
            ):
                return {"error": "PERMISSION_BARRIER_REJECTED"}
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            job = c.execute("SELECT * FROM send_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not job:
                c.rollback(); return {"error": "JOB_NOT_FOUND"}
            if job["state"] in TERMINAL:
                c.rollback(); return {"state": job["state"], "idempotent": True}
            if job["state"] != "LEASED":
                c.rollback(); return {"error": "NOT_LEASED", "state": job["state"]}
            if job["lease_id"] != lease_id or int(job["lease_expires_at"] or 0) <= ts:
                c.rollback(); return {"error": "LEASE_INVALID"}
            verified_at = int(final.get("verified_at") or 0)
            if (
                not all_safety_pass(final)
                or int(final.get("expires_at") or 0) <= ts
                or verified_at < ts - 120000
                or verified_at > ts + 5000
            ):
                self._terminalize(c, job, "SAFETY_BLOCKED", {"reason": "FINAL_SAFETY_RECHECK_FAILED"})
                c.commit(); return {"state": "SAFETY_BLOCKED"}
            stored = json.loads(job["safety_contract_json"] or "{}")
            if str(final.get("message_hash") or "") != str(stored.get("message_hash") or ""):
                self._terminalize(c, job, "SAFETY_BLOCKED", {"reason": "IMMUTABLE_MESSAGE_MISMATCH"})
                c.commit(); return {"state": "SAFETY_BLOCKED"}
            attempt_id = str(body.get("attempt_id") or uuid.uuid4())
            c.execute(
                """UPDATE send_jobs SET state='SUBMIT_STARTED',safety_contract_json=?,updated_at=?
                   WHERE job_id=? AND state='LEASED'""",
                (json.dumps(final, ensure_ascii=False), ts, job_id),
            )
            c.execute(
                """INSERT INTO send_attempts(
                     attempt_id,job_id,send_key,state,started_at,submit_started_at,detail_json)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    attempt_id, job_id, job["send_key"], "SUBMIT_STARTED", ts, ts,
                    json.dumps(
                        {
                            "executor_id": str(body.get("executor_id") or ""),
                            "executor_version": str(body.get("executor_version") or ""),
                            "form_fingerprint": str(final.get("form_fingerprint") or ""),
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            c.commit()
            return {"state": "SUBMIT_STARTED", "attempt_id": attempt_id}
        except sqlite3.IntegrityError:
            c.rollback()
            row = c.execute("SELECT state FROM send_jobs WHERE job_id=?", (job_id,)).fetchone()
            return {"error": "DUPLICATE_SUBMIT_BARRIER", "state": row["state"] if row else "UNKNOWN"}
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def receipt(self, body: dict) -> dict:
        job_id = str(body.get("job_id") or "")
        outcome = str(body.get("outcome") or "")
        evidence = dict(body.get("evidence") or {})
        if outcome not in {"SENT_CONFIRMED", "CONFIRMED_NOT_SENT", "AMBIGUOUS_HOLD"}:
            return {"error": "INVALID_OUTCOME"}
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            prior = c.execute("SELECT terminal_state FROM terminal_receipts WHERE job_id=?", (job_id,)).fetchone()
            if prior:
                c.rollback(); return {"state": prior["terminal_state"], "idempotent": True}
            job = c.execute("SELECT * FROM send_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not job:
                c.rollback(); return {"error": "JOB_NOT_FOUND"}
            if job["state"] != "SUBMIT_STARTED":
                c.rollback(); return {"error": "SUBMIT_NOT_STARTED", "state": job["state"]}
            if outcome == "SENT_CONFIRMED" and not evidence_pass(evidence):
                c.rollback(); return {"error": "INSUFFICIENT_SUCCESS_EVIDENCE"}
            if outcome == "CONFIRMED_NOT_SENT" and not deterministic_not_sent_evidence(evidence):
                c.rollback(); return {"error": "NOT_SENT_EVIDENCE_REQUIRED"}
            # A proven non-delivery closes this exact route. The controller may
            # discover a different official route, but the same form is not retried.
            ts2 = now_ms()
            attempt = c.execute(
                "SELECT * FROM send_attempts WHERE job_id=? AND state='SUBMIT_STARTED' ORDER BY started_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            self._terminalize(c, job, outcome, evidence)
            if attempt:
                c.execute(
                    """INSERT OR IGNORE INTO send_attempt_history(
                         attempt_id,job_id,send_key,state,started_at,submit_started_at,ended_at,
                         detail_json,archived_at,archive_reason)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        attempt["attempt_id"], attempt["job_id"], attempt["send_key"], outcome,
                        int(attempt["started_at"]), int(attempt["submit_started_at"]), ts2,
                        json.dumps(evidence, ensure_ascii=False), ts2,
                        "TERMINAL_RECEIPT_" + outcome,
                    ),
                )
                c.execute("DELETE FROM send_attempts WHERE attempt_id=?", (attempt["attempt_id"],))
            c.commit()
            return {"state": outcome}
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def pre_submit_fail(self, body: dict) -> dict:
        job_id = str(body.get("job_id") or "")
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            job = c.execute("SELECT * FROM send_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not job:
                c.rollback(); return {"error": "JOB_NOT_FOUND"}
            if job["state"] in TERMINAL:
                c.rollback(); return {"state": job["state"], "idempotent": True}
            if job["state"] != "LEASED":
                c.rollback(); return {"error": "NOT_LEASED", "state": job["state"]}
            reason = str(body.get("reason") or "PRE_SUBMIT_TECH_FAILURE")
            try:
                stored = json.loads(job["safety_contract_json"] or "{}")
            except Exception:
                stored = {}
            now = now_ms()
            if passes_http_preflight(stored, now):
                retry_state = "NEEDS_VERIFY"
            elif (all_safety_pass(stored)
                    and int(stored.get("expires_at") or 0) > now):
                retry_state = "VERIFIED"
            else:
                retry_state = "STALE_REVERIFY"
            # Shared risk-infrastructure outages are not candidate/form failures.
            # Keep the job recoverable and fail closed until the common cache is
            # healthy again; do not burn the per-job retry budget and terminalize.
            if reason == "RISK_SANCTIONS_SCREEN_UNAVAILABLE":
                defer_until = now_ms() + 300000
                c.execute(
                    """UPDATE send_jobs SET state=?,lease_id=NULL,
                       lease_expires_at=NULL,executor_id=NULL,next_eligible_at=?,updated_at=?
                       WHERE job_id=?""",
                    (retry_state, defer_until, now_ms(), job_id),
                )
                c.commit()
                return {"state":retry_state,"deferred":True,
                        "reason":reason,"next_eligible_at":defer_until}
            retry = int(job["retry_count"] or 0) + 1
            deterministic = reason in {
                "FORM_NO_SAFE_DIRECT_STATIC_FORM",
                "FINAL_SUBMIT_CONTROL_NOT_FOUND",
                "STATIC_EXPORT_FORM_ACTION",
                "EMAIL_HANDOFF_FORM",
                "BUSINESS_CONTACT_FORM_NOT_FOUND",
                "PRE_SUBMIT_REQUIRED_MISSING",
                "RISK_LEGAL_ENTITY_IDENTITY_WEAK",
            }
            if deterministic or retry > 2:
                state = self._terminalize(
                    c, job, "TECH_FAILED_FINAL",
                    {"reason": reason, "retry": retry, "deterministic": deterministic},
                )
                c.commit(); return {"state": state}
            # Never immediately reclaim the same transient pre-submit failure.
            # Immediate retry used to let one hydrating/timeout form monopolize
            # the scarce browser slot three times in a row. Give other jobs a
            # turn and allow the remote page to settle before the next attempt.
            retry_delay_ms=min(300000,60000*(2**max(0,retry-1)))
            defer_until=now+retry_delay_ms
            c.execute(
                """UPDATE send_jobs SET state=?,retry_count=?,lease_id=NULL,
                   lease_expires_at=NULL,executor_id=NULL,next_eligible_at=?,updated_at=?
                   WHERE job_id=?""",
                (retry_state, retry, defer_until, now_ms(), job_id),
            )
            c.commit()
            return {"state": retry_state, "retry_count": retry,
                    "deferred": True, "next_eligible_at": defer_until,
                    "retry_delay_ms": retry_delay_ms}
        except Exception:
            c.rollback(); raise
        finally:
            c.close()

    def release_prepared(self, body: dict) -> dict:
        ts = now_ms()
        job_id = str(body.get("job_id") or "")
        lease_id = str(body.get("lease_id") or "")
        final = dict(body.get("final_safety_contract") or {})
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            job = c.execute("SELECT * FROM send_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not job:
                c.rollback(); return {"error": "JOB_NOT_FOUND"}
            if job["state"] in TERMINAL:
                c.rollback(); return {"state": job["state"], "idempotent": True}
            if job["state"] != "LEASED" or job["lease_id"] != lease_id:
                c.rollback(); return {"error": "LEASE_INVALID", "state": job["state"]}
            stored = json.loads(job["safety_contract_json"] or "{}")
            if not all_safety_pass(final) or str(final.get("message_hash") or "") != str(stored.get("message_hash") or ""):
                state = self._terminalize(c, job, "SAFETY_BLOCKED", {"reason": "FINAL_SAFETY_RECHECK_FAILED"})
                c.commit(); return {"state": state}
            hold = ts + max(60000, min(1800000, int(body.get("hold_ms") or 600000)))
            c.execute(
                """UPDATE send_jobs SET state='VERIFIED',safety_contract_json=?,
                   lease_id=NULL,lease_expires_at=NULL,executor_id=NULL,
                   next_eligible_at=?,updated_at=? WHERE job_id=?""",
                (json.dumps(final, ensure_ascii=False), hold, ts, job_id),
            )
            c.commit()
            return {"state": "VERIFIED", "prepared": True, "next_eligible_at": hold}
        except Exception:
            c.rollback(); raise
        finally:
            c.close()

    def safety_block(self, body: dict) -> dict:
        job_id = str(body.get("job_id") or "")
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            job = c.execute("SELECT * FROM send_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not job:
                c.rollback(); return {"error": "JOB_NOT_FOUND"}
            if job["state"] in TERMINAL:
                c.rollback(); return {"state": job["state"], "idempotent": True}
            if job["state"] == "SUBMIT_STARTED":
                c.rollback(); return {"error": "POST_BARRIER_CANNOT_SAFETY_RETRY", "state": job["state"]}
            state = self._terminalize(
                c, job, "SAFETY_BLOCKED",
                {"reason": str(body.get("reason") or "FINAL_SAFETY_BLOCK")},
            )
            c.commit()
            return {"state": state}
        except Exception:
            c.rollback(); raise
        finally:
            c.close()

    def priority_batch(self, updates: list[dict]) -> dict:
        c = self._con()
        updated = 0
        try:
            c.execute("BEGIN IMMEDIATE")
            for row in list(updates or [])[:500]:
                rid = str(row.get("route_id") or "")
                try:
                    score = float(row.get("priority_score") or 0)
                except Exception:
                    continue
                cur = c.execute(
                    """UPDATE send_jobs SET priority_score=MAX(priority_score,?),updated_at=?
                       WHERE route_id=? AND state IN ('VERIFIED','READY')""",
                    (score, now_ms(), rid),
                )
                updated += max(0, int(cur.rowcount or 0))
            c.commit()
            return {"updated": updated}
        except Exception:
            c.rollback(); raise
        finally:
            c.close()

    def _metric_core(self, campaign: str | None = None, message: str | None = None) -> dict:
        ts = now_ms()
        cut = ts - 3600000
        c = self._con()
        try:
            c.execute("BEGIN IMMEDIATE")
            self._reconcile(c, ts)
            c.commit()
            where = ""
            params: list[object] = []
            if campaign is not None and message is not None:
                where = " WHERE campaign_version=? AND message_version=?"
                params = [campaign, message]
            states = {
                str(r["state"]): int(r["n"])
                for r in c.execute(f"SELECT state,count(*) n FROM send_jobs{where} GROUP BY state", params)
            }
            if campaign is None:
                term_sql = """SELECT terminal_state,count(*) n FROM terminal_receipts
                              WHERE created_at>=? GROUP BY terminal_state"""
                term_params = [cut]
            else:
                term_sql = """SELECT t.terminal_state,count(*) n
                              FROM terminal_receipts t JOIN send_jobs j ON j.job_id=t.job_id
                              WHERE t.created_at>=? AND j.campaign_version=? AND j.message_version=?
                              GROUP BY t.terminal_state"""
                term_params = [cut, campaign, message]
            terminal = {str(r["terminal_state"]): int(r["n"]) for r in c.execute(term_sql, term_params)}
            return {
                "states": states,
                "terminal_60m": terminal,
                "verified_inventory": int(states.get("VERIFIED", 0)),
                "ready_inventory_open": int(states.get("READY", 0)),
                "leased": int(states.get("LEASED", 0)),
                "submit_started": int(states.get("SUBMIT_STARTED", 0)),
                "queue_depth": int(states.get("VERIFIED", 0)) + int(states.get("READY", 0)),
                "duplicate_attempts": 0,
            }
        finally:
            c.close()

    def metrics(self) -> dict:
        return self._metric_core()

    def campaign_metrics(self, campaign_version: str, message_version: str) -> dict:
        out = self._metric_core(str(campaign_version), str(message_version))
        out["campaign_version"] = str(campaign_version)
        out["message_version"] = str(message_version)
        out["sent_confirmed_60m"] = int(out["terminal_60m"].get("SENT_CONFIRMED", 0))
        c = self._con()
        try:
            row = c.execute(
                """SELECT count(*) n FROM terminal_receipts t
                   JOIN send_jobs j ON j.job_id=t.job_id
                   WHERE t.terminal_state='SENT_CONFIRMED'
                     AND j.campaign_version=? AND j.message_version=?""",
                (str(campaign_version), str(message_version)),
            ).fetchone()
            out["sent_confirmed_total"] = int(row["n"] or 0)
        finally:
            c.close()
        return out

    def peek(self, limit: int = 100) -> dict:
        c = self._con()
        try:
            rows = [
                dict(r)
                for r in c.execute(
                    """SELECT route_id,state,priority_score,retry_count,next_eligible_at,created_at
                       FROM send_jobs WHERE state IN ('VERIFIED','READY')
                       ORDER BY priority_score DESC,created_at LIMIT ?""",
                    (max(1, min(250, int(limit))),),
                )
            ]
            return {"jobs": rows}
        finally:
            c.close()

    def recent(self, limit: int = 50) -> dict:
        c = self._con()
        try:
            rows = []
            for r in c.execute(
                """SELECT j.route_id,j.company_id,j.state,j.priority_score,
                          t.terminal_state,t.evidence_json,t.created_at
                   FROM terminal_receipts t JOIN send_jobs j ON j.job_id=t.job_id
                   ORDER BY t.created_at DESC LIMIT ?""",
                (max(1, min(100, int(limit))),),
            ):
                d = dict(r)
                try:
                    d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
                except Exception:
                    d["evidence"] = {}
                rows.append(d)
            return {"receipts": rows}
        finally:
            c.close()

    def budget(self) -> dict:
        c = self._con()
        try:
            hb = c.execute("SELECT * FROM heartbeat WHERE singleton=1").fetchone()
            return {
                "mode": "LOCAL_SQLITE_ZERO_COST",
                "paid_upgrade_allowed": False,
                "executor_heartbeat": dict(hb) if hb else None,
            }
        finally:
            c.close()

    def protected_routes(self) -> dict:
        c = self._con()
        try:
            rows = [dict(r) for r in c.execute("SELECT domain,company_id,reason FROM protected_companies ORDER BY domain")]
            return {"rows": rows, "count": len(rows)}
        finally:
            c.close()


# Compatibility alias so callers can use LedgerClient.from_env().
LedgerClient = LocalLedgerClient
