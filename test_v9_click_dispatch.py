import pathlib,unittest

class FinalClickDispatchContract(unittest.TestCase):
    def test_final_click_does_not_wait_on_implicit_navigation(self):
        s=pathlib.Path('v9_send_worker.py').read_text()
        self.assertIn("await loc.click(timeout=5000,no_wait_after=True)",s)
        self.assertIn("await page.wait_for_load_state('domcontentloaded',timeout=5000)",s)
        self.assertIn('settle_correlated_click_timeout',s)

if __name__=='__main__': unittest.main()
