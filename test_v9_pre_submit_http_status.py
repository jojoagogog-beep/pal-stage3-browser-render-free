import unittest
import v9_send_worker as w

class PreSubmitHttpStatusTests(unittest.TestCase):
    def test_access_denied_is_safety_blocked(self):
        for status in (401,403,451):
            self.assertEqual(w.pre_submit_http_verdict(status),
                             ('SAFETY_BLOCKED','SITE_ACCESS_DENIED_PRE_SUBMIT'))

    def test_missing_route_is_confirmed_not_sent(self):
        for status in (400,404,410,422):
            self.assertEqual(w.pre_submit_http_verdict(status),
                             ('CONFIRMED_NOT_SENT','ROUTE_HTTP_4XX_PRE_SUBMIT'))

    def test_rate_limit_and_server_errors_retry(self):
        for status in (429,500,502,503):
            self.assertEqual(w.pre_submit_http_verdict(status),
                             ('TECH_RETRY','SITE_TEMPORARY_HTTP_PRE_SUBMIT'))

    def test_success_and_redirect_do_not_block(self):
        for status in (200,201,202,204,301,302):
            self.assertIsNone(w.pre_submit_http_verdict(status))

if __name__=='__main__':
    unittest.main()
