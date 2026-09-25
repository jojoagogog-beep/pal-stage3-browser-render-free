import unittest
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

    def test_japanese_validation_errors_are_failures(self):
        for text in ('入力にエラーがあります','【社名】は必須項目です','下記をご確認の上「戻る」ボタンにて修正'):
            self.assertIsNotNone(w.FAIL.search(text))

    def test_mail_field_alias_is_email(self):
        self.assertIsNotNone(w.EMAIL.search('mail'))
        self.assertIsNotNone(w.EMAIL.search('contact_mail'))
        self.assertIsNone(w.EMAIL.search('mailing_address'))

if __name__=='__main__': unittest.main()
