import unittest
from pathlib import Path

class V6EngineAdapterTests(unittest.TestCase):
    def test_render_uses_v6_engine(self):
        app=Path("app.py").read_text()
        self.assertIn("V9_SEND_WORKER=HERE/\'v6_v9_send_worker.py\'",app)
        docker=Path("Dockerfile").read_text()
        for name in ("v6_v9_send_worker.py","browser_slots_v7.py","local_ledger_v7.py","safety_contract_v6.py"):
            self.assertIn(name,docker)
    def test_adapter_uses_old_browser_slots_pipeline(self):
        s=Path("v6_v9_send_worker.py").read_text()
        self.assertIn("BrowserSlots(2)",s)
        self.assertIn("prepare_same_page",s)
        self.assertIn("revalidate_prepared_fields",s)
        self.assertIn("submit_prepared",s)
        self.assertIn("_mark_click_started",s)
    def test_v9_policy_gates_remain(self):
        s=Path("v6_v9_send_worker.py").read_text()
        self.assertIn("_proof_control_ok",s)
        self.assertIn("_production_control_ok",s)
        self.assertIn("CLICK_ALREADY_STARTED_FAIL_CLOSED",s)

if __name__=="__main__": unittest.main()
