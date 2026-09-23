import unittest
import stage3_send_ready_worker_v1 as w

class ConfirmControlTests(unittest.TestCase):
    def test_normalized_confirm_match_tolerates_whitespace_and_suffix(self):
        self.assertTrue(w.confirm_control_matches("確認画面へ", "  確認画面へ   next "))

    def test_confirm_match_rejects_explicit_send_action(self):
        self.assertFalse(w.safe_confirm_text("確認して送信"))
        self.assertFalse(w.confirm_control_matches("確認画面へ", "確認して送信"))

    def test_final_accepts_explicit_input_button_send(self):
        xs=[{"tag":"input","type":"button","text":"送信する"}]
        got=w.final_control_candidates(xs)
        self.assertEqual(got,xs)

    def test_final_rejects_image_input_even_if_internal_name_says_submit(self):
        xs=[{"tag":"input","type":"image","text":"submit_button"}]
        self.assertEqual(w.final_control_candidates(xs),[])

    def test_final_rejects_nonfinal_back_button(self):
        xs=[{"tag":"button","type":"button","text":"戻る"}]
        self.assertEqual(w.final_control_candidates(xs),[])

    def test_single_generic_real_submit_remains_existing_safe_fallback(self):
        xs=[{"tag":"button","type":"submit","text":"Continue"}]
        self.assertEqual(w.final_control_candidates(xs),xs)

if __name__=="__main__":
    unittest.main()
