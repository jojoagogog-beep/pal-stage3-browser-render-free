import unittest
from pathlib import Path

class SenderBatchCapacityTests(unittest.TestCase):
    def test_sender_keeps_two_way_concurrency_and_drains_eight_per_wake(self):
        src=Path('app.py').read_text()
        self.assertIn("'PAL_V9_SEND_MAX_TASKS':'8'",src)
        self.assertIn("'PAL_V9_SEND_CONCURRENCY':'2'",src)
        self.assertIn("'PAL_V9_TASK_WALL_TIMEOUT':'30'",src)
        self.assertIn("str(V9_SEND_WORKER)],env=env,text=True,capture_output=True,timeout=270",src)

if __name__=='__main__':
    unittest.main()
