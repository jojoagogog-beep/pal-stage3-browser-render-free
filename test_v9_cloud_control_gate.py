import pathlib,unittest
class CloudControlGate(unittest.TestCase):
 def test_cloud_control_gate_present(self):
  s=pathlib.Path('app.py').read_text()
  self.assertIn('def _v9_production_authorized(generation):',s)
  self.assertIn("d.get('external_send_enabled') is True",s)
  self.assertIn("d.get('ledger_mode')=='PRODUCTION'",s)
  self.assertIn("int(led.get('generation') or 0)==g",s)
  self.assertIn("production_authority",s)
  self.assertIn("GLOBAL_LEDGER_DO",s)
 def test_fail_closed(self):
  s=pathlib.Path('app.py').read_text()
  self.assertIn('except Exception:\n        return False',s)
  self.assertIn("return jsonify(status='PRODUCTION_LOCKED'",s)
if __name__=='__main__':unittest.main()
