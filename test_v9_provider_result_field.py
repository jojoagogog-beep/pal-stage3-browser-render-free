import unittest
import v9_send_worker as w

class ProviderResultFieldTests(unittest.TestCase):
    def test_yith_result_success(self):
        self.assertEqual(w.provider_app_status({'result':'success','redirect':'/request-quote/123'}),'success')

    def test_yith_result_failure(self):
        self.assertEqual(w.provider_app_status({'result':'failure','messages':'invalid'}),'failure')

    def test_status_keeps_precedence(self):
        self.assertEqual(w.provider_app_status({'status':'mail_sent','result':'failure'}),'mail_sent')

    def test_non_dict_is_empty(self):
        self.assertEqual(w.provider_app_status(['success']),'')
        self.assertEqual(w.provider_app_status(None),'')

if __name__=='__main__':
    unittest.main()
