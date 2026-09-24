import unittest
from pathlib import Path
import v9_send_worker as w
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
        self.assertIn("V9_SEND_SHARD1_ONLY",src)
if __name__=='__main__': unittest.main()
