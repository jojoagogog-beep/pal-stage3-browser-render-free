import unittest
from pathlib import Path
import v9_send_worker as w

class FrameworkRequiredTests(unittest.TestCase):
    def test_ng_invalid_is_required_hint(self):
        self.assertTrue(w.field_required_hint(False,'form-control ng-invalid ng-pristine','Phone Number'))

    def test_ng_valid_is_not_required_hint(self):
        self.assertFalse(w.field_required_hint(False,'form-control ng-valid ng-dirty','Optional note'))

    def test_stage3_scanner_knows_ng_invalid(self):
        src=Path('stage3_send_ready_worker_v1.py').read_text()
        self.assertIn("frameworkRequired=classes.some(c=>/^ng-invalid$/i.test(c))",src)

if __name__=='__main__':
    unittest.main()
