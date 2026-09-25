import unittest
from pathlib import Path

class DefaultButtonSubmitRegressionTests(unittest.TestCase):
    def test_sender_uses_effective_dom_button_type(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn("typ:(e.type||e.getAttribute('type')||'').toLowerCase()",src)
        self.assertIn("e=>(e.type||e.getAttribute('type')||'').toLowerCase()",src)

if __name__=='__main__':
    unittest.main()
