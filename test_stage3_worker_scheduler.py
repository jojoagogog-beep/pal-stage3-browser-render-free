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

    def test_lane_accept_respects_explicit_fast_dom_promotion(self):
        rec={'route_id':814,'static_status':'DYNAMIC_HINT_CANDIDATE',
             'stage2_static_sendability':80,'lane_hint':'FAST_DOM',
             'force_rendered':False}
        w.LANE_MODE='FAST_DOM'
        self.assertTrue(w.lane_accept(rec))
        w.LANE_MODE='DYNAMIC_JS'
        self.assertFalse(w.lane_accept(rec))

    def test_lane_accept_respects_explicit_force_dynamic_lane(self):
        rec={'route_id':999,'static_status':'STATIC_FORM_CANDIDATE',
             'stage2_static_sendability':90,'lane_hint':'DYNAMIC_JS',
             'force_rendered':True}
        w.LANE_MODE='DYNAMIC_JS'
        self.assertTrue(w.lane_accept(rec))
        w.LANE_MODE='FAST_DOM'
        self.assertFalse(w.lane_accept(rec))

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


def _task(market,n,quality=0,admitted=0):
    return {'task_id':f'{market}-{n}','routes':[
        {'market':market,'stage3_quality':quality,'route_id':abs(hash((market,n)))%1000,
         'static_status':'STATIC_FORM_CANDIDATE','admitted_rank':int(admitted)}]}


class RankPendingTasksTests(unittest.TestCase):
    """2026-09-24: a flat quality sort let one PRIORITY_MARKETS entry with
    more ADMITTED/high-quality tasks (stage3_quality is weighted +20000 per
    admitted route) consume a worker's entire bounded lease before a market
    with a far larger backlog got a single task. Live evidence: JP-JA took
    18/30 Browser dispatches in a 30-minute window while GB-EN, the largest
    open-market backlog, took only 4."""

    def setUp(self):
        self.old_lane=w.LANE_MODE
        w.LANE_MODE='FAST_DOM'

    def tearDown(self):
        w.LANE_MODE=self.old_lane

    def test_admitted_heavy_market_no_longer_monopolizes_the_lease_front(self):
        pending=(
            [_task('JP-JA',i,quality=20000) for i in range(2)]
            +[_task('GB-EN',i) for i in range(6)]
            +[_task('SG-EN',i) for i in range(4)]
            +[_task('NZ-EN',i) for i in range(1)]
        )
        ranked=w.rank_pending_tasks(pending,['JP-JA','GB-EN','SG-EN','NZ-EN'])
        front_markets={t['task_id'].rsplit('-',1)[0] for t in ranked[:4]}
        self.assertEqual(front_markets,{'JP-JA','GB-EN','SG-EN','NZ-EN'})
        nz_position=[t['task_id'] for t in ranked].index('NZ-EN-0')
        self.assertLess(nz_position,4,f'NZ-EN starved to position {nz_position}')

    def test_quality_priority_is_preserved_within_a_single_market(self):
        pending=[_task('GB-EN','low',quality=0),_task('GB-EN','high',quality=9999)]
        ranked=w.rank_pending_tasks(pending,['GB-EN'])
        self.assertEqual([t['task_id'] for t in ranked],['GB-EN-high','GB-EN-low'])

    def test_admitted_task_outranks_higher_quality_nonadmitted_in_same_market(self):
        pending=[
            _task('JP-JA','high',quality=99999,admitted=0),
            _task('JP-JA','admit',quality=100,admitted=1),
        ]
        ranked=w.rank_pending_tasks(pending,['JP-JA'])
        self.assertEqual(ranked[0]['task_id'],'JP-JA-admit',ranked)

    def test_route_work_rank_puts_admitted_before_high_quality_generic(self):
        admitted={'route_id':174,'market':'JP-JA','admitted_rank':1,
                  'stage3_quality':100,'prior_rendered_success':False}
        high={'route_id':677,'market':'JP-JA','admitted_rank':0,
              'stage3_quality':99999,'prior_rendered_success':False}
        got=sorted([high,admitted],key=w.route_work_rank)
        self.assertEqual(got[0]['route_id'],174,got)

    def test_static_evidence_outranks_generic_fresh_route(self):
        static={'route_id':3018,'market':'JP-JA','admitted_rank':0,
                'stage3_quality':100,'prior_rendered_success':False,
                'retry_rank':1,'stage2_route_quality':75,
                'stage2_static_sendability':0,'static_status':'STATIC_FORM_CANDIDATE',
                'static_quality':70,'form_shape_signal':1,'expansion_signal':0,
                'force_rendered':False}
        fresh={'route_id':12642,'market':'JP-JA','admitted_rank':0,
               'stage3_quality':99999,'prior_rendered_success':False,
               'retry_rank':2,'stage2_route_quality':75,
               'stage2_static_sendability':0,'static_status':'DYNAMIC_HINT_CANDIDATE',
               'static_quality':0,'form_shape_signal':0,'expansion_signal':0,
               'force_rendered':False}
        got=sorted([fresh,static],key=w.route_work_rank)
        self.assertEqual(got[0]['route_id'],3018,got)

    def test_task_has_shard_work_filters_foreign_shard_only_task(self):
        old_count,old_index,old_lane=w.SHARD_COUNT,w.SHARD_INDEX,w.LANE_MODE
        try:
            w.SHARD_COUNT=2
            w.SHARD_INDEX=0
            w.LANE_MODE='DYNAMIC_JS'
            owned=next(r for r in range(100,400) if w.route_shard(r,2)==0)
            foreign=next(r for r in range(100,400) if w.route_shard(r,2)==1)
            base={'market':'JP-JA','static_status':'DYNAMIC_HINT_CANDIDATE',
                  'stage3_quality':1,'admitted_rank':0}
            self.assertTrue(w.task_has_shard_work({'routes':[dict(base,route_id=owned)]}))
            self.assertFalse(w.task_has_shard_work({'routes':[dict(base,route_id=foreign)]}))
        finally:
            w.SHARD_COUNT=old_count
            w.SHARD_INDEX=old_index
            w.LANE_MODE=old_lane

    def test_route_yield_class_orders_admitted_before_generic_high_signal(self):
        admitted={'route_id':174,'admitted_rank':1,'stage2_route_quality':0,
                  'stage2_static_sendability':0,'retry_rank':1,
                  'static_status':'DYNAMIC_HINT_CANDIDATE'}
        high={'route_id':677,'admitted_rank':0,'stage2_route_quality':90,
              'stage2_static_sendability':80,'retry_rank':2,
              'static_status':'DYNAMIC_HINT_CANDIDATE'}
        generic={'route_id':999,'admitted_rank':0,'stage2_route_quality':75,
                 'stage2_static_sendability':0,'retry_rank':2,
                 'static_status':'DYNAMIC_HINT_CANDIDATE'}
        self.assertLess(w.route_yield_class(admitted),w.route_yield_class(high))
        self.assertLess(w.route_yield_class(high),w.route_yield_class(generic))

    def test_task_has_shard_work_filters_other_shard_and_other_lane(self):
        old_count,old_index,old_lane=w.SHARD_COUNT,w.SHARD_INDEX,w.LANE_MODE
        try:
            w.SHARD_COUNT=2; w.SHARD_INDEX=1; w.LANE_MODE='DYNAMIC_JS'
            own=next(r for r in range(1,500) if w.route_shard(r,2)==1)
            other=next(r for r in range(1,500) if w.route_shard(r,2)==0)
            self.assertTrue(w.task_has_shard_work({'routes':[
                {'route_id':own,'static_status':'DYNAMIC_HINT_CANDIDATE'}]}))
            self.assertFalse(w.task_has_shard_work({'routes':[
                {'route_id':other,'static_status':'DYNAMIC_HINT_CANDIDATE'}]}))
            self.assertFalse(w.task_has_shard_work({'routes':[
                {'route_id':own,'static_status':'STATIC_FORM_CANDIDATE'}]}))
        finally:
            w.SHARD_COUNT=old_count; w.SHARD_INDEX=old_index; w.LANE_MODE=old_lane

    def test_priority_order_still_wins_the_first_pick_each_round(self):
        pending=[_task('SG-EN',i) for i in range(2)]+[_task('GB-EN',i) for i in range(2)]
        ranked=w.rank_pending_tasks(pending,['SG-EN','GB-EN'])
        self.assertTrue(ranked[0]['task_id'].startswith('SG-EN'))

    def test_non_priority_market_tasks_keep_flat_quality_order_after_priority_block(self):
        pending=[_task('GB-EN',0,quality=1),_task('US-ET','low',quality=1),_task('US-ET','high',quality=9)]
        ranked=w.rank_pending_tasks(pending,['GB-EN'])
        self.assertEqual([t['task_id'] for t in ranked],['GB-EN-0','US-ET-high','US-ET-low'])

    def test_empty_priority_markets_falls_back_to_flat_quality_order(self):
        pending=[_task('US-ET','low',quality=1),_task('US-ET','high',quality=9)]
        ranked=w.rank_pending_tasks(pending,[])
        self.assertEqual([t['task_id'] for t in ranked],['US-ET-high','US-ET-low'])


if __name__=='__main__':
    unittest.main(verbosity=2)
