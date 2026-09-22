import itertools
import sys
import time
import types
import unittest

try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    class _DummyFlask:
        def __init__(self,*a,**k): pass
        def get(self,*a,**k):
            return lambda f:f
        def post(self,*a,**k):
            return lambda f:f
    sys.modules['flask']=types.SimpleNamespace(
        Flask=_DummyFlask,
        jsonify=lambda *a,**k: (a[0] if len(a)==1 else (a or k)),
        request=types.SimpleNamespace(headers={},get_json=lambda **k:{}),
    )

import app as m

class Stage3AdaptiveSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.old_lanes=m.LANES
        self.old_streak=dict(m.LANE_EMPTY_STREAK)
        self.old_skip=dict(m.LANE_SKIP_UNTIL)
        m.LANE_EMPTY_STREAK.clear()
        m.LANE_SKIP_UNTIL.clear()
        for lane in ('A','B','C'):
            m.LANE_EMPTY_STREAK[lane]=0
            m.LANE_SKIP_UNTIL[lane]=0.0

    def tearDown(self):
        m.LANES=self.old_lanes
        m.LANE_EMPTY_STREAK.clear(); m.LANE_EMPTY_STREAK.update(self.old_streak)
        m.LANE_SKIP_UNTIL.clear(); m.LANE_SKIP_UNTIL.update(self.old_skip)

    def test_tech_defer_only_is_temporarily_cooled_down(self):
        before=time.time()
        m._record_lane_result('A',{
            'routes':4,
            'result_transport':'SUPERJSONBLOB_V1',
            'status_counts':{'TECH_DEFER':4},
            'code_counts':{'BROWSER_TIMEOUT':4},
        },200)
        self.assertEqual(m.LANE_EMPTY_STREAK['A'],1)
        self.assertGreater(m.LANE_SKIP_UNTIL['A'],before)

    def test_productive_safe_result_clears_prior_cooldown(self):
        m.LANE_EMPTY_STREAK['A']=2
        m.LANE_SKIP_UNTIL['A']=time.time()+300
        m._record_lane_result('A',{
            'routes':3,
            'result_transport':'SUPERJSONBLOB_V1',
            'status_counts':{'SAFE_RENDERED_STATIC':1,'TECH_DEFER':2},
            'code_counts':{'REMOTE_FULL_SEND_READY_V3':1},
        },200)
        self.assertEqual(m.LANE_EMPTY_STREAK['A'],0)
        self.assertEqual(m.LANE_SKIP_UNTIL['A'],0.0)

    def test_next_lane_skips_cooled_lane(self):
        m.LANES=itertools.cycle(('A','B','A','C'))
        m.LANE_SKIP_UNTIL['A']=time.time()+300
        self.assertEqual(m._next_lane(),'B')
        self.assertEqual(m._next_lane(),'C')

    def test_high_yield_lanes_keep_parallel_capacity(self):
        # DYNAMIC_JS and IFRAME_DEEP have materially higher measured SAFE yield
        # than DEEP, so they must not silently regress to the same low-capacity
        # setting. This changes scheduling capacity only; proof/safety gates are
        # still owned by the worker and executor contracts.
        self.assertGreaterEqual(m.LANE_CONCURRENCY['DYNAMIC_JS'], 4)
        self.assertGreaterEqual(m.LANE_CONCURRENCY['IFRAME_DEEP'], 3)
        self.assertGreater(m.LANE_CONCURRENCY['DYNAMIC_JS'], m.LANE_CONCURRENCY['DEEP'])
        self.assertGreater(m.LANE_CONCURRENCY['IFRAME_DEEP'], m.LANE_CONCURRENCY['DEEP'])
        for lane, concurrency in m.LANE_CONCURRENCY.items():
            self.assertGreaterEqual(m.LANE_MAX_ROWS[lane], concurrency)

    def test_network_route_handler_is_awaited_not_fire_and_forget(self):
        # Fire-and-forget Playwright route tasks kept asyncio.run() alive long
        # after proof publication. Keep network interception structured so a
        # completed worker can actually release the free Render browser slot.
        from pathlib import Path
        src=(Path(__file__).resolve().parent/'stage3_send_ready_worker_v1.py').read_text()
        self.assertIn('async def route_request(route):',src)
        self.assertIn("await ctx.route('**/*', route_request)",src)
        self.assertNotIn('asyncio.create_task(route.abort())',src)
        self.assertNotIn('asyncio.create_task(route.continue_())',src)

if __name__=='__main__':
    unittest.main(verbosity=2)
