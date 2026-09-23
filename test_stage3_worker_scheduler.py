import importlib
import os
import sys
import types
import unittest

# The tests exercise pure scheduling helpers and do not launch a browser.
try:
    import playwright.async_api  # noqa: F401
except ModuleNotFoundError:
    async_api=types.ModuleType('playwright.async_api')
    async_api.async_playwright=lambda: None
    class _TimeoutError(Exception):
        pass
    async_api.TimeoutError=_TimeoutError
    pkg=types.ModuleType('playwright')
    pkg.async_api=async_api
    sys.modules['playwright']=pkg
    sys.modules['playwright.async_api']=async_api

import stage3_send_ready_worker_v1 as w

class Stage3WorkerSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.old_lane=w.LANE_MODE

    def tearDown(self):
        w.LANE_MODE=self.old_lane

    def test_task_lane_quality_uses_best_eligible_route(self):
        w.LANE_MODE='DEEP'
        task={'routes':[
            {'route_id':1,'static_status':'TECH_DEFER','stage3_quality':0},
            {'route_id':2,'static_status':'DYNAMIC_HINT_CANDIDATE','stage3_quality':9000},
            {'route_id':3,'static_status':'TECH_DEFER','stage3_quality':3000},
        ]}
        self.assertEqual(w.task_lane_quality(task),3000)

    def test_task_lane_quality_minus_one_when_lane_has_no_route(self):
        w.LANE_MODE='FAST_DOM'
        task={'routes':[{'route_id':1,'static_status':'TECH_DEFER','stage3_quality':9000}]}
        self.assertEqual(w.task_lane_quality(task),-1)

    def test_cold_browser_launch_still_gets_one_primary_batch_budget(self):
        old_deadline=100.0
        now_after_launch=180.0
        got=w.effective_work_deadline(old_deadline,42,now=now_after_launch)
        self.assertGreaterEqual(got,227.0)

    def test_existing_later_deadline_is_not_shortened(self):
        self.assertEqual(w.effective_work_deadline(500.0,42,now=100.0),500.0)

    def test_task_blob_falls_back_to_browser_queue(self):
        old_candidates=list(w._TASK_BLOB_CANDIDATES)
        old_get=w.blob_get
        try:
            w._TASK_BLOB_CANDIDATES=['legacy-route-blob','browser-blob']
            def fake_get(url):
                if url=='legacy-route-blob':
                    return {'tasks':[{'kind':'PAL_CANDIDATE_ROUTE_BATCH_V2','task_id':'route-1'}]}
                return {'tasks':[{'kind':'PAL_BROWSER_PREFLIGHT_TASK_V1','task_id':'browser-1','routes':[]}]}
            w.blob_get=fake_get
            got=w.task_messages()
            self.assertEqual([x['task_id'] for x in got],['browser-1'])
        finally:
            w._TASK_BLOB_CANDIDATES=old_candidates
            w.blob_get=old_get

    def test_browser_queue_precedes_legacy_generic_env(self):
        keys=('PAL_ROUTE_TASK_BLOB_URL','PAL_BROWSER_TASK_BLOB_URL','PAL_STAGE3_TRANSPORT_CONFIG_FILE')
        old={k:os.environ.get(k) for k in keys}
        try:
            os.environ['PAL_ROUTE_TASK_BLOB_URL']='https://superjsonblob.com/api/jsonBlob/legacy-stage2'
            os.environ.pop('PAL_BROWSER_TASK_BLOB_URL',None)
            os.environ['PAL_STAGE3_TRANSPORT_CONFIG_FILE']='/tmp/pal-no-such-stage3-transport.json'
            ww=importlib.reload(w)
            self.assertEqual(ww.TASK_BLOB,ww._DEFAULT_BROWSER_TASK_BLOB)
            self.assertLess(
                ww._TASK_BLOB_CANDIDATES.index(ww._DEFAULT_BROWSER_TASK_BLOB),
                ww._TASK_BLOB_CANDIDATES.index(os.environ['PAL_ROUTE_TASK_BLOB_URL']))
        finally:
            for k,v in old.items():
                if v is None: os.environ.pop(k,None)
                else: os.environ[k]=v
            importlib.reload(w)

if __name__=='__main__':
    unittest.main(verbosity=2)
