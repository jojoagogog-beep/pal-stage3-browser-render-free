import pathlib
import unittest

class RequestResponseBoundTests(unittest.TestCase):
    def test_correlated_response_wait_is_bounded(self):
        src=pathlib.Path('v9_send_worker.py').read_text()
        self.assertIn("await asyncio.wait_for(req.response(),timeout=1.5)",src)

if __name__=='__main__':
    unittest.main()
