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

if __name__=='__main__': unittest.main()
