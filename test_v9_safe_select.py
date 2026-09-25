import unittest
import stage3_send_ready_worker_v1 as w

class SafeSelectTests(unittest.TestCase):
    def test_picks_single_neutral_other(self):
        opts=[{'v':'','t':'--選択してください--'},{'v':'sales','t':'見積に関すること'},{'v':'other','t':'その他'}]
        self.assertEqual(w.safe_select_value(opts),'other')

    def test_does_not_pick_specific_or_unsafe_category(self):
        opts=[{'v':'support','t':'Technical support'},{'v':'career','t':'Career'}]
        self.assertIsNone(w.safe_select_value(opts))

    def test_ambiguous_neutral_choices_fail_closed(self):
        opts=[{'v':'general','t':'General'},{'v':'other','t':'Other'}]
        self.assertIsNone(w.safe_select_value(opts))

if __name__=='__main__':
    unittest.main()
