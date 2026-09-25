import unittest
import v9_send_worker as w

class FakePage:
    def __init__(self):
        self.calls=[]
    async def wait_for_timeout(self,ms):
        self.calls.append(('timeout',ms))
    async def wait_for_load_state(self,state,timeout=None):
        self.calls.append(('load',state,timeout))

class ClickTimeoutSettleTests(unittest.IsolatedAsyncioTestCase):
    async def test_does_not_wait_without_correlated_post(self):
        p=FakePage()
        ok=await w.settle_correlated_click_timeout(
            p,'TimeoutError',[{'matches_form_payload':False}])
        self.assertFalse(ok)
        self.assertEqual(p.calls,[])

    async def test_waits_for_existing_correlated_submission(self):
        p=FakePage()
        ok=await w.settle_correlated_click_timeout(
            p,'TimeoutError',[{'matches_form_payload':True}])
        self.assertTrue(ok)
        self.assertEqual(p.calls[0],('timeout',2200))
        self.assertIn(('load','domcontentloaded',4000),p.calls)
        self.assertEqual(p.calls[-1],('timeout',600))

if __name__=='__main__':
    unittest.main()
