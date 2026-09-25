import unittest
from unittest.mock import patch
import v9_send_worker as w

class SenderHardWatchdog(unittest.TestCase):
    def task(self):
        return {'token_id':'tok','company_key':'dom:example.com','route_id':7,'click_started':False}

    def test_preclick_timeout_is_retryable(self):
        r=w.hard_timeout_result(self.task(),{'click_started':False},110,True)
        self.assertEqual(r['outcome'],'TECH_RETRY')
        self.assertEqual(r['reason'],'WORKER_HARD_TIMEOUT_PRE_CLICK')
        self.assertTrue(r['evidence']['pre_submit'])
        self.assertTrue(r['evidence']['resend_safe'])

    def test_after_click_timeout_is_fail_closed(self):
        r=w.hard_timeout_result(self.task(),{'click_started':True},110,True)
        self.assertEqual(r['outcome'],'AMBIGUOUS_HOLD')
        self.assertFalse(r['evidence']['resend_safe'])

    def test_unknown_marker_is_fail_closed(self):
        r=w.hard_timeout_result(self.task(),None,110,False)
        self.assertEqual(r['outcome'],'AMBIGUOUS_HOLD')
        self.assertEqual(r['reason'],'WORKER_HARD_TIMEOUT_MARKER_UNKNOWN')

    def test_result_read_failure_never_blind_overwrites_queue(self):
        writes=[]
        with patch.object(w,'_get_result',side_effect=TimeoutError('read failed')), patch.object(w,'_put_result',side_effect=lambda u,o:writes.append(o)):
            with self.assertRaises(TimeoutError):
                w.publish_result_batch_sync([{'token_id':'tok','outcome':'TECH_RETRY'}])
        self.assertEqual(writes,[])

    def test_durable_single_publish_tracks_token_before_unlock(self):
        writes=[];published=set()
        with patch.object(w,'RESULT_URL','result-url'), patch.object(w,'_get_result',return_value={'messages':[{'token_id':'keep'}]}), patch.object(w,'_put_result',side_effect=lambda u,o:writes.append(o)):
            w.publish_one_result_sync({'token_id':'tok','outcome':'TECH_RETRY'},published)
        self.assertIn('tok',published)
        self.assertEqual([x['token_id'] for x in writes[0]['messages']],['keep','tok'])

if __name__=='__main__': unittest.main()
