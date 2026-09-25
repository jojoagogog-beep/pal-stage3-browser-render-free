import unittest
import v9_send_worker as w

class BrowserLaunchFailSafeTests(unittest.TestCase):
    def test_pre_click_launch_timeout_is_retryable(self):
        t={'token_id':'t1','company_key':'c1','route_id':1,'click_started':False}
        r=w.pre_browser_failure_result(t)
        self.assertEqual(r['outcome'],'TECH_RETRY')
        self.assertEqual(r['reason'],'BROWSER_LAUNCH_TIMEOUT_PRE_CLICK')
        self.assertTrue(r['evidence']['pre_submit'])
        self.assertFalse(r['evidence']['click_started'])

    def test_post_click_launch_failure_fails_closed(self):
        t={'token_id':'t2','company_key':'c2','route_id':2,'click_started':True}
        r=w.pre_browser_failure_result(t)
        self.assertEqual(r['outcome'],'AMBIGUOUS_HOLD')
        self.assertEqual(r['reason'],'BROWSER_LAUNCH_TIMEOUT_HOLD')
        self.assertFalse(r['evidence']['resend_safe'])
        self.assertTrue(r['evidence']['click_started'])

if __name__=='__main__':
    unittest.main()
