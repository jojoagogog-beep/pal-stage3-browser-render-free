import unittest
import v9_send_worker as sender
import stage3_send_ready_worker_v1 as stage3

class SpacedControlLabelTests(unittest.TestCase):
    def test_sender_spaced_japanese_confirm(self):
        self.assertTrue(sender.control_is_confirm('確 認','確 認'))
        self.assertFalse(sender.control_is_confirm('送 信','送 信'))

    def test_sender_spaced_final_send(self):
        self.assertTrue(sender.FINAL.search(sender.compact_control_text('送 信')))

    def test_stage3_spaced_confirm_is_safe_confirm(self):
        self.assertTrue(stage3.safe_confirm_text('確 認'))
        x={'tag':'input','type':'submit','label':'確 認','text':'確 認'}
        self.assertEqual(stage3.final_control_candidates([x]),[])

    def test_stage3_spaced_final_is_final(self):
        x={'tag':'input','type':'submit','label':'送 信','text':'送 信'}
        self.assertEqual(stage3.final_control_candidates([x]),[x])

    def test_confirm_matching_ignores_spacing(self):
        self.assertTrue(stage3.confirm_control_matches('確 認','確認'))

if __name__=='__main__':
    unittest.main()
