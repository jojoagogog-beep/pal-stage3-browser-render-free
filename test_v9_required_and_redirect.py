import unittest
import v9_send_worker as w

class RequiredAndRedirectTests(unittest.TestCase):
    def test_optional_kana_field_is_core(self):
        self.assertIsNotNone(w.KANA_FIELD.search('kana'))
        self.assertIsNotNone(w.KANA_FIELD.search('フリガナ'))

    def test_required_hint_from_japanese_mark(self):
        self.assertTrue(w.field_required_hint(False,'','電話番号※'))
        self.assertTrue(w.field_required_hint(False,'','ご住所 ※'))
        self.assertFalse(w.field_required_hint(False,'','電話番号（任意）'))
        self.assertTrue(w.field_required_hint(True,'',''))

    def test_same_form_redirect_with_values_remaining_is_failure(self):
        rows=[{'matches_form_payload':True,'status':302,'location':'https://www.tsujikawa.co.jp/contact/'}]
        self.assertTrue(w.same_form_redirect_failure('https://www.tsujikawa.co.jp/contact/',rows,3,False))
        self.assertFalse(w.same_form_redirect_failure('https://www.tsujikawa.co.jp/contact/',rows,0,False))
        self.assertFalse(w.same_form_redirect_failure('https://www.tsujikawa.co.jp/contact/',rows,3,True))

    def test_relative_same_form_redirect(self):
        rows=[{'matches_form_payload':True,'status':302,'location':'./'}]
        self.assertTrue(w.same_form_redirect_failure('https://example.com/contact/',rows,2,False))
        rows=[{'matches_form_payload':True,'status':302,'location':'/thanks/'}]
        self.assertFalse(w.same_form_redirect_failure('https://example.com/contact/',rows,2,False))

if __name__=='__main__':
    unittest.main()
