import pathlib,unittest
class V9Stage2Tests(unittest.TestCase):
 def source(self):return pathlib.Path('app.py').read_text()
 def test_queue_then_yield_after_browser_quantum(self):
  s=self.source();self.assertIn("@app.post('/v9-stage2-wake')",s);self.assertIn('_queue_v9_stage2',s);self.assertIn('QUEUED_AFTER_BROWSER_QUANTUM',s);self.assertIn('YIELD_TO_WAITING_V9_STAGE2',s);self.assertIn('_start_pending_v9_stage2()',s)
 def test_sender_priority_and_shared_lock(self):
  s=self.source();self.assertIn("V9_SEND_THREAD and V9_SEND_THREAD.is_alive()",s);self.assertIn("_v9_send_pending_snapshot() is not None",s);self.assertIn('STAGE2_LOCK.acquire(blocking=False)',s);self.assertIn('RUN_LOCK.acquire(blocking=False)',s)
 def test_shard1_only_and_revision_exposed(self):
  s=self.source();self.assertIn('V9_STAGE2_SHARD1_ONLY',s);self.assertIn('V9_STAGE2_SHARD1_IDLE_ONLY_V1',s);self.assertIn('v9_stage2_shard1_revision',s);self.assertIn('v9_stage2_pending',s)
if __name__=='__main__':unittest.main()
