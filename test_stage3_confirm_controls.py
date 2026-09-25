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

    def test_retryable_confirm_accepts_same_safe_submitter(self):
        x={"tag":"input","type":"submit","label":"確認画面へ",
           "text":"確認画面へ submitConfirm","frame_index":0}
        self.assertTrue(w.retryable_confirm_control("確認画面へ",x,0))

    def test_retryable_confirm_rejects_final_send_submitter(self):
        x={"tag":"input","type":"submit","label":"この内容で送信",
           "text":"この内容で送信 submitConfirm","frame_index":0}
        self.assertFalse(w.retryable_confirm_control("確認画面へ",x,0))

    def test_retryable_confirm_rejects_other_frame(self):
        x={"tag":"input","type":"submit","label":"確認画面へ",
           "text":"確認画面へ submitConfirm","frame_index":1}
        self.assertFalse(w.retryable_confirm_control("確認画面へ",x,0))

class SemanticLabelTests(unittest.TestCase):
    def test_visible_send_label_wins_over_internal_confirm_name(self):
        x={"tag":"input","type":"button","label":"送信する","text":"送信する submitConfirm confirmButton"}
        self.assertEqual(w.final_control_candidates([x]),[x])

    def test_visible_confirm_label_is_not_final_even_if_internal_name_contains_submit(self):
        x={"tag":"input","type":"submit","label":"確認画面へ","text":"確認画面へ submitConfirm submitButton"}
        self.assertEqual(w.final_control_candidates([x]),[])
        self.assertTrue(w.safe_confirm_text(w.control_semantic_text(x)))

    def test_japanese_confirm_progression_variants(self):
        for text in ('確認画面に進む','確認画面に進める','入力内容の確認画面へ'):
            self.assertIsNotNone(w.CONFIRM.search(text), text)

if __name__=="__main__":
    unittest.main()
