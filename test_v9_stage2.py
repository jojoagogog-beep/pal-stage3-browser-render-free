import pathlib,unittest
class V9Stage2Tests(unittest.TestCase):
 def test_idle_only_endpoint_present(self):
  s=pathlib.Path('app.py').read_text()
  self.assertIn("@app.post('/v9-stage2-wake')",s)
  self.assertIn("BUSY_HIGHER_PRIORITY",s)
  self.assertIn("V9_SEND_THREAD and V9_SEND_THREAD.is_alive()",s)
  self.assertIn("PUMP_THREAD and PUMP_THREAD.is_alive()",s)
  self.assertIn("STAGE2_PRIMARY_ROLE",s)
  self.assertIn("RUN_LOCK.acquire(blocking=False)",s)
 def test_revision_exposed(self):
  s=pathlib.Path('app.py').read_text();self.assertIn('V9_STAGE2_SHARD1_IDLE_ONLY_V1',s);self.assertIn('v9_stage2_shard1_revision',s)
if __name__=='__main__':unittest.main()
