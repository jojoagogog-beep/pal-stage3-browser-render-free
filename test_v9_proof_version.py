import unittest
import stage3_send_ready_worker_v1 as stage3

class ProofVersionTests(unittest.TestCase):
    def test_stage3_emits_v4_proof(self):
        self.assertEqual(stage3.PROOF_VERSION, "STAGE3_FULL_SEND_READY_V4")
        self.assertEqual(stage3.base_result({"route_id": 1})["proof_version"], stage3.PROOF_VERSION)

if __name__ == "__main__":
    unittest.main()
