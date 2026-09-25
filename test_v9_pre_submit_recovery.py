import unittest
from pathlib import Path
import v9_send_worker as w

class PreSubmitRecoveryTests(unittest.TestCase):
    def test_email_example_placeholder_is_recognized(self):
        self.assertIsNotNone(w.EMAIL_EXAMPLE.search('you@company.com'))
        self.assertIsNone(w.EMAIL_EXAMPLE.search('company.com'))

    def test_safe_confirmation_check_text(self):
        self.assertIsNotNone(w.SUBMIT_CONFIRM_CHECK.search('上記の内容でよろしければチェックボックスにチェックを入れてください。チェックがないと送信できません'))
        self.assertIsNone(w.SUBMIT_CONFIRM_CHECK.search('ニュースレターを購読する'))

    def test_lazy_form_reveal_is_wired(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn('async def reveal_candidate_forms',src)
        self.assertIn('await reveal_candidate_forms(page',src)

if __name__=='__main__':
    unittest.main()
