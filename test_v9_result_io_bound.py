import unittest
import v9_send_worker as w

class ResultIoBoundTests(unittest.TestCase):
    def test_result_timeout_is_shorter_than_general_blob_timeout(self):
        self.assertGreaterEqual(w.RESULT_IO_TIMEOUT, 3)
        self.assertLessEqual(w.RESULT_IO_TIMEOUT, 12)

    def test_batch_publisher_uses_result_specific_io_and_dedupes(self):
        old_get, old_put = w._get_result, w._put_result
        calls = []
        try:
            w._get_result = lambda url: {"messages":[{"token_id":"same","old":1},{"token_id":"keep"}]}
            w._put_result = lambda url, payload: calls.append(payload)
            w.publish_result_batch_sync([{"token_id":"same","new":1}])
        finally:
            w._get_result, w._put_result = old_get, old_put
        self.assertEqual(len(calls),1)
        msgs=calls[0]["messages"]
        self.assertEqual([x["token_id"] for x in msgs],["keep","same"])
        self.assertEqual(msgs[-1]["new"],1)

if __name__=="__main__":
    unittest.main()
