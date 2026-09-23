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
        self.assertIn("fieldset",src)
        self.assertIn(".p-contact-group__header",src)
        self.assertIn(".req,.required,.hissu",src)

    def test_completion_routes_are_rejected_before_browser_work(self):
        self.assertTrue(w.is_completion_route("https://example.com/contact/thanks"))
        self.assertTrue(w.is_completion_route("https://example.com/contact/thank-you/"))
        self.assertTrue(w.is_completion_route("https://example.com/contact/complete"))
        self.assertTrue(w.is_completion_route("https://example.com/contact/success/"))
        self.assertFalse(w.is_completion_route("https://example.com/contact"))
        self.assertFalse(w.is_completion_route("https://example.com/success-stories"))

    def test_strong_main_confirm_candidate_can_stop_extra_frame_scan(self):
        self.assertTrue(w.strong_main_form_candidate(
            {"control_kind":"CONFIRM_STEP","score":12},0))
        self.assertTrue(w.strong_main_form_candidate(
            {"control_kind":"DIRECT_SUBMIT","score":13},0))
        self.assertFalse(w.strong_main_form_candidate(
            {"control_kind":"CONFIRM_STEP","score":11},0))
        self.assertFalse(w.strong_main_form_candidate(
            {"control_kind":"CONFIRM_STEP","score":15},1))

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
