import pathlib
import unittest

class RequiredIconRegressionTests(unittest.TestCase):
    def test_required_icon_is_part_of_required_semantics(self):
        src=pathlib.Path(__file__).with_name("stage3_send_ready_worker_v1.py").read_text()
        self.assertIn("rowRequiredIcon",src)
        self.assertIn("d.rowRequiredIcon===true",src)
        self.assertIn("asterisk|required|mandatory|hissu|必須",src)

if __name__=="__main__":
    unittest.main()
