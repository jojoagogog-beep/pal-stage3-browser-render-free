import unittest
from pathlib import Path
import v9_send_worker as w
import app
class V9SenderSafetyTests(unittest.TestCase):
    def test_message_is_not_sensitive(self):
        self.assertIsNone(w.SENSITIVE.search('message'))
    def test_sensitive_phone_and_age_are_blocked(self):
        self.assertIsNotNone(w.SENSITIVE.search('Phone number'))
        self.assertIsNotNone(w.SENSITIVE.search('Age'))
    def test_final_and_confirm_are_separate(self):
        self.assertIsNotNone(w.FINAL.search('Send message'))
        self.assertIsNotNone(w.CONFIRM.search('Confirm'))
        self.assertIsNone(w.FINAL.search('Confirm'))
    def test_v9_send_route_source_is_present(self):
        src=Path('app.py').read_text()
        self.assertIn("@app.post('/v9-send-wake')",src)
        self.assertIn("RUN_LOCK.acquire(blocking=False)",src)
        self.assertIn("sender_shard",src)
        self.assertIn("DUAL_AUTHORITY_DUAL_SHARD_FAILOVER_V2",src)
        self.assertIn("PRODUCTION_LOCKED",src)
        self.assertIn("return 'V9_SENDER'",src)
        self.assertIn("YIELD_TO_WAITING_V9_SENDER",src)
        self.assertIn("status='QUEUED'",src)
    def test_sender_pending_snapshot_hides_blob_urls(self):
        old=app.V9_SEND_PENDING
        try:
            app.V9_SEND_PENDING={'task_url':'https://superjsonblob.com/api/jsonBlob/a','result_url':'https://superjsonblob.com/api/jsonBlob/b','mode':'SHADOW','queued_at':123}
            snap=app._v9_send_pending_snapshot()
            self.assertEqual(snap,{'mode':'SHADOW','queued_at':123})
            self.assertNotIn('task_url',snap)
        finally:
            app.V9_SEND_PENDING=old

    def test_duplicate_wake_while_running_is_idempotent(self):
        class Alive:
            def is_alive(self): return True
        old=(app.TOKEN,app.STAGE2_PRIMARY_ROLE,app.V9_SEND_THREAD,app.V9_SEND_PENDING)
        try:
            app.TOKEN='test-token';app.STAGE2_PRIMARY_ROLE=False;app.V9_SEND_THREAD=Alive();app.V9_SEND_PENDING=None
            c=app.app.test_client()
            r=c.post('/v9-send-wake',headers={'x-pal-token':'test-token'},json={
                'task_url':'https://superjsonblob.com/api/jsonBlob/a',
                'result_url':'https://superjsonblob.com/api/jsonBlob/b','mode':'SHADOW'})
            self.assertEqual(r.status_code,202)
            self.assertEqual(r.get_json().get('status'),'ALREADY_RUNNING')
            self.assertIsNone(app.V9_SEND_PENDING)
        finally:
            app.TOKEN,app.STAGE2_PRIMARY_ROLE,app.V9_SEND_THREAD,app.V9_SEND_PENDING=old

    def test_duplicate_queued_wake_does_not_replace_pending(self):
        task='https://superjsonblob.com/api/jsonBlob/a';result='https://superjsonblob.com/api/jsonBlob/b'
        pending={'task_url':task,'result_url':result,'mode':'SHADOW','queued_at':123}
        old=(app.TOKEN,app.STAGE2_PRIMARY_ROLE,app.V9_SEND_THREAD,app.V9_SEND_PENDING)
        try:
            app.TOKEN='test-token';app.STAGE2_PRIMARY_ROLE=False;app.V9_SEND_THREAD=None;app.V9_SEND_PENDING=dict(pending)
            c=app.app.test_client()
            r=c.post('/v9-send-wake',headers={'x-pal-token':'test-token'},json={'task_url':task,'result_url':result,'mode':'SHADOW'})
            self.assertEqual(r.status_code,202)
            self.assertEqual(r.get_json().get('status'),'QUEUED')
            self.assertEqual(app.V9_SEND_PENDING,pending)
        finally:
            app.TOKEN,app.STAGE2_PRIMARY_ROLE,app.V9_SEND_THREAD,app.V9_SEND_PENDING=old
    def test_sender_turn_capacity_is_four_bounded_tasks(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn("PAL_V9_SEND_MAX_TASKS','4'",src)
        self.assertIn('[:MAX_TASKS_PER_TURN]',src)
        self.assertIn('asyncio.Semaphore(SEND_CONCURRENCY)',src)
        self.assertEqual(w.MAX_TASKS_PER_TURN,4)
        self.assertEqual(w.SEND_CONCURRENCY,2)

    def test_production_waits_for_submit_barrier(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn('await_submit_barrier',src)
        self.assertIn('deferred_unarmed',src)

    def test_production_rejects_missing_proof_expiry(self):
        self.assertFalse(w._proof_control_ok({}))
        self.assertFalse(w._proof_control_ok({'proof_expires_at':None}))

    def test_optional_business_identity_fields_reach_fill_logic(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn("or COMPANY.search(d) or FIRST_NAME.search(d) or LAST_NAME.search(d)",src)
        self.assertIn("or NAME.search(d) or KANA_FIELD.search(d) or SUBJECT.search(d) or URLRX.search(d)",src)
if __name__=='__main__': unittest.main()
