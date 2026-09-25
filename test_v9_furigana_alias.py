import unittest
import v9_send_worker as sender

class FuriganaAliasTests(unittest.TestCase):
    def test_sender_recognizes_furigana_field_name(self):
        self.assertIsNotNone(sender.KANA_FIELD.search('furigana'))

    def test_kana_examples_still_match(self):
        for text in ('フリガナ','カナ','kana','ふりがな'):
            self.assertIsNotNone(sender.KANA_FIELD.search(text), text)

if __name__=='__main__':
    unittest.main()
