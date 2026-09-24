import pathlib,unittest
class HandoffContract(unittest.TestCase):
 def test_stage2_yields_to_sender(self):
  s=pathlib.Path('app.py').read_text()
  self.assertIn("sender_started=_start_pending_v9_send()",s)
  self.assertIn("'event':'STAGE2_STOPPED'",s)
 def test_sender_resumes_stage2(self):
  s=pathlib.Path('app.py').read_text()
  self.assertIn("'event':'V9_SEND_STOPPED'",s)
  self.assertIn("stage2_started=_start_pending_v9_stage2()",s)
if __name__=='__main__':unittest.main()
