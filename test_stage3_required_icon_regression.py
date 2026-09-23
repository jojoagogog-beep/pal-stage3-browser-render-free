import pathlib
import unittest
import stage3_send_ready_worker_v1 as w

class RequiredIconRegressionTests(unittest.TestCase):
    def test_required_icon_is_part_of_required_semantics(self):
        src=pathlib.Path(__file__).with_name("stage3_send_ready_worker_v1.py").read_text()
        self.assertIn("rowRequiredIcon",src)
        self.assertIn("d.rowRequiredIcon===true",src)
        self.assertIn("asterisk|required|mandatory|hissu|必須",src)

    def test_sibling_required_badge_patterns_are_scanned(self):
        src=pathlib.Path(__file__).with_name("stage3_send_ready_worker_v1.py").read_text()
        self.assertIn(".form02",src)
        self.assertIn(".form03",src)
        self.assertIn(".req,.required,.hissu",src)

    def test_transactional_privacy_consent_gate(self):
        self.assertTrue(w.form_requires_transactional_consent(
            "プライバシーポリシーに同意の上、送信いただきますようお願いいたします。"))
        self.assertFalse(w.form_requires_transactional_consent(
            "プライバシーポリシーをご確認ください。"))

    def test_safe_privacy_consent_radio_choice(self):
        rows=[{"desc":"プライバシーポリシーに同意する","value":"true"}]
        self.assertEqual(w.safe_consent_radio_choice(rows),rows[0])

    def test_marketing_or_negative_consent_is_never_selected(self):
        marketing=[{"desc":"マーケティング情報の受信に同意する","value":"yes"}]
        negative=[{"desc":"プライバシーポリシーに同意しない","value":"no"}]
        self.assertIsNone(w.safe_consent_radio_choice(marketing))
        self.assertIsNone(w.safe_consent_radio_choice(negative))

if __name__=="__main__":
    unittest.main()
