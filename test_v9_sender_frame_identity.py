import unittest
from pathlib import Path
import v9_send_worker as w

class Frame:
    def __init__(self,url): self.url=url

class Page:
    def __init__(self,frames,main,url):
        self.frames=frames;self.main_frame=main;self.url=url

class SenderFrameIdentityTests(unittest.TestCase):
    def test_stage3_compatible_frame_order(self):
        main=Frame('https://example.com/contact')
        ad=Frame('https://ads.example.net/widget')
        provider=Frame('https://forms.typeform.com/to/x')
        same=Frame('https://example.com/embed/contact')
        page=Page([main,ad,provider,same],main,main.url)
        roots=w.ordered_form_frames(page,'example.com')
        self.assertEqual(roots,[main,same,provider,ad])

    def test_main_frame_is_always_zero(self):
        main=Frame('https://example.com/contact')
        page=Page([Frame('https://x.invalid'),main],main,main.url)
        self.assertIs(w.ordered_form_frames(page,'example.com')[0],main)

    def test_confirm_step_starts_from_canonical_form(self):
        task={'canonical_url':'https://example.com/contact','official_domain':'example.com',
              'proof_url':'https://example.com/contact/confirm/','proof_confirm_step':True}
        self.assertEqual(w.sender_start_url(task),'https://example.com/contact')

    def test_direct_proof_can_start_from_same_domain_proof_url(self):
        task={'canonical_url':'https://example.com/contact','official_domain':'example.com',
              'proof_url':'https://example.com/contact-us','proof_confirm_step':False}
        self.assertEqual(w.sender_start_url(task),'https://example.com/contact-us')

    def test_cross_domain_proof_url_is_rejected(self):
        task={'canonical_url':'https://example.com/contact','official_domain':'example.com',
              'proof_url':'https://evil.invalid/contact','proof_confirm_step':False}
        self.assertEqual(w.sender_start_url(task),'https://example.com/contact')

    def test_japanese_validation_errors_are_failures(self):
        for text in ('入力にエラーがあります','【社名】は必須項目です','下記をご確認の上「戻る」ボタンにて修正'):
            self.assertIsNotNone(w.FAIL.search(text))

    def test_mail_field_alias_is_email(self):
        self.assertIsNotNone(w.EMAIL.search('mail'))
        self.assertIsNotNone(w.EMAIL.search('contact_mail'))
        self.assertIsNone(w.EMAIL.search('mailing_address'))

    def test_static_submit_marker_is_not_part_of_button_identity(self):
        self.assertEqual(w.normalize_proof_submit_text('Send Message __DIRECT_SUBMIT__'),'send message')
        self.assertEqual(w.normalize_proof_submit_text('Get Started __DIRECT_SUBMIT__'),'get started')

    def test_explicit_success_beats_reset_form_invalid_controls(self):
        self.assertFalse(w.post_submit_validation(False,5,False,True,True))
        self.assertTrue(w.post_submit_validation(True,0,False,True,True))
        self.assertTrue(w.post_submit_validation(False,5,False,False,True))

    def test_browser_form_scan_knows_mail_alias(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertGreaterEqual(src.count("(?:^|[^a-z])mail(?:$|[^a-z])"),3)

    def test_table_cell_labels_are_used_in_sender_field_detection(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertGreaterEqual(src.count("closest('td')?.previousElementSibling?.innerText"),3)

if __name__=='__main__':
    unittest.main()
