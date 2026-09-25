import unittest
import v9_send_worker as w

class ControlLabelSemanticsTests(unittest.TestCase):
    def test_visible_confirm_label_wins_over_internal_submit_name(self):
        self.assertTrue(w.control_is_confirm(
            '確認画面へ',
            '確認画面へ submitConfirm __DIRECT_SUBMIT__'))

    def test_final_send_label_stays_final(self):
        self.assertFalse(w.control_is_confirm(
            '確認して送信',
            '確認して送信 submitConfirm'))
        self.assertFalse(w.control_is_confirm(
            '送信する',
            'submit 送信する'))

if __name__=='__main__':
    unittest.main()
