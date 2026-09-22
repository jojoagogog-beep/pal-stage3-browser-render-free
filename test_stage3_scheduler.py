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

    def test_fast_dom_gets_majority_but_all_lanes_remain_represented(self):
        from pathlib import Path
        src=(Path(__file__).resolve().parent/'app.py').read_text()
        self.assertIn("'FAST_DOM','DYNAMIC_JS','FAST_DOM','IFRAME_DEEP'",src)
        self.assertIn("'FAST_DOM','DEEP','FAST_DOM','FAST_DOM'",src)

    def test_free_plan_browser_parallelism_is_memory_safe(self):
        # Render Free still OOM-killed the service at two-way browser parallelism.
        # Keep exactly one live Browser route/renderer per process. FAST_DOM may
        # amortize one Chromium launch across three routes, but only serially.
        self.assertEqual(set(m.LANE_CONCURRENCY.values()), {1})
        self.assertEqual(m.LANE_MAX_ROWS['DYNAMIC_JS'],1)
        self.assertEqual(m.LANE_MAX_ROWS['IFRAME_DEEP'],1)
        self.assertEqual(m.LANE_MAX_ROWS['DEEP'],1)
        self.assertEqual(m.LANE_MAX_ROWS['FAST_DOM'],3)
        self.assertGreaterEqual(m.LANE_DEADLINE_SECONDS['FAST_DOM'],100)

    def test_secret_file_fallbacks_keep_clone_credentials_out_of_repo(self):
        from pathlib import Path
        app=(Path(__file__).resolve().parent/'app.py').read_text()
        worker=(Path(__file__).resolve().parent/'stage3_send_ready_worker_v1.py').read_text()
        self.assertIn('/etc/secrets/stage3_token',app)
        self.assertIn('/etc/secrets/stage3_transport',worker)
        self.assertIn("browser_task_blob_url",worker)
        self.assertIn("browser_result_blob_url",worker)

    def test_browser_demand_lease_is_bounded_and_refreshable(self):
        old=m.BROWSER_DEMAND_UNTIL
        try:
            m.BROWSER_DEMAND_UNTIL=0.0
            remaining=m._note_browser_demand(now=1000.0)
            self.assertEqual(remaining,float(m.BROWSER_PRIORITY_GRACE_SECONDS))
            self.assertGreater(m._browser_demand_remaining(now=1001.0),0)
            first=m.BROWSER_DEMAND_UNTIL
            m._note_browser_demand(now=1010.0)
            self.assertGreater(m.BROWSER_DEMAND_UNTIL,first)
        finally:
            m.BROWSER_DEMAND_UNTIL=old

    def test_stage2_and_stage3_share_the_heavy_resource_lock(self):
        from pathlib import Path
        src=(Path(__file__).resolve().parent/'app.py').read_text()
        self.assertIn("RUN_LOCK=threading.Lock()  # shared heavy-resource lock",src)
        self.assertIn("status='BUSY_STAGE3_PRIORITY'",src)
        self.assertIn("browser_wait=_browser_demand_remaining()",src)
        self.assertIn("try: RUN_LOCK.release()",src)

    def test_browser_routes_are_deterministically_sharded(self):
        from pathlib import Path
        src=(Path(__file__).resolve().parent/'stage3_send_ready_worker_v1.py').read_text()
        self.assertIn("PAL_STAGE3_SHARD_COUNT','2'",src)
        self.assertIn("RENDER_SERVICE_NAME",src)
        self.assertIn("endswith('-v2')",src)
        self.assertIn("(rid % SHARD_COUNT)==SHARD_INDEX",src)
        self.assertIn("not shard_accept(rec) or not lane_accept(rec)",src)

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
        self.assertIn('def _run_main():',src)
        self.assertNotIn("if __name__=='__main__':asyncio.run(amain())",src)

if __name__=='__main__':
    unittest.main(verbosity=2)
