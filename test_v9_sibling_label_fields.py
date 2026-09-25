import unittest
from pathlib import Path
import v9_send_worker as w

class SiblingLabelFieldTests(unittest.TestCase):
    def test_parent_sibling_label_is_in_sender_metadata(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn("querySelector(':scope > label')",src)
        self.assertIn("e.parentElement",src)

    def test_japanese_email_label_is_email(self):
        self.assertIsNotNone(w.EMAIL.search('メールアドレス*'))

if __name__=='__main__':
    unittest.main()
