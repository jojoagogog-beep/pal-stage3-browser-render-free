import unittest
import v9_send_worker as w

class ClickStartedFailClosedTests(unittest.IsolatedAsyncioTestCase):
    async def test_preexisting_click_marker_never_reopens_browser(self):
        old=w.MODE
        w.MODE='PRODUCTION'
        try:
            task={
                'token_id':'t1','company_key':'c1','route_id':1,
                'canonical_url':'https://example.com/contact',
                'message_body':'hello',
                'submit_started':True,
                'click_started':True,
            }
            res=await w.process_task(object(),task)
            self.assertEqual(res['outcome'],'AMBIGUOUS_HOLD')
            self.assertEqual(res['reason'],'CLICK_ALREADY_STARTED_FAIL_CLOSED')
            self.assertFalse(res['evidence']['resend_safe'])
        finally:
            w.MODE=old

if __name__=='__main__':
    unittest.main()
