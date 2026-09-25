import unittest
from pathlib import Path
import stage3_send_ready_worker_v1 as w

class Stage3PerfBoundsTests(unittest.TestCase):
    def test_fast_dom_navigation_is_bounded(self):
        self.assertLessEqual(w.stage3_navigation_timeout_ms(46,'FAST_DOM'),10000)
        self.assertGreaterEqual(w.stage3_navigation_timeout_ms(46,'FAST_DOM'),6000)

    def test_deep_lane_keeps_more_budget(self):
        self.assertGreater(w.stage3_navigation_timeout_ms(46,'DEEP'),
                           w.stage3_navigation_timeout_ms(46,'FAST_DOM'))

    def test_post_confirm_text_scan_is_bounded(self):
        src=Path('stage3_send_ready_worker_v1.py').read_text()
        self.assertNotIn("root2.locator('body').inner_text()",src)
        self.assertIn('timeout=1.5',src)

    def test_outer_form_scan_budget_exceeds_inner_dom_budget(self):
        src=Path('stage3_send_ready_worker_v1.py').read_text()
        self.assertIn('timeout=3.0',src)
        self.assertIn("per_root_timeout=3.75 if LANE_MODE in {'IFRAME_DEEP','DEEP'} else 3.5",src)

if __name__=='__main__':
    unittest.main()
