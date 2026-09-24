import pathlib,unittest
class RevocationGate(unittest.TestCase):
 def test_app_rechecks_queued_generation(self):
  s=pathlib.Path('app.py').read_text()
  self.assertIn("'generation':int(generation or 0)",s)
  self.assertIn("not _v9_production_authorized(int(pending.get('generation') or 0))",s)
  self.assertIn("status='CONTROL_REVOKED'",s)
  self.assertNotIn('env_enabled or cloud_authorized',s)
 def test_worker_rechecks_before_browser_and_clicks(self):
  s=pathlib.Path('v9_send_worker.py').read_text()
  self.assertIn('def _production_control_ok():',s)
  self.assertIn('PRODUCTION_CONTROL_REVOKED_PRE_BROWSER',s)
  self.assertIn('PRODUCTION_CONTROL_REVOKED_PRE_CLICK',s)
  self.assertIn('PRODUCTION_CONTROL_REVOKED_BEFORE_FINAL',s)
  self.assertGreaterEqual(s.count('await asyncio.to_thread(_production_control_ok)'),3)
if __name__=='__main__':unittest.main()
