import unittest
import v9_send_worker as w

class ConfirmLabelTests(unittest.TestCase):
    def test_japanese_confirm_screen_labels(self):
        for text in ('確認画面へ','確認画面に進む','確認画面に進める','入力内容を確認','次へ'):
            self.assertIsNotNone(w.CONFIRM.search(text), text)

    def test_final_send_is_not_confirm(self):
        self.assertIsNone(w.CONFIRM.search('送信する'))
        self.assertIsNotNone(w.FINAL.search('送信する'))

if __name__=='__main__':
    unittest.main()
