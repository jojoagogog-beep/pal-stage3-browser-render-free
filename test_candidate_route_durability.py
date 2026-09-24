import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import candidate_route_worker_v1 as w

TASK={'kind':'PAL_CANDIDATE_ROUTE_TASK_V1','task_id':'task-1',
      'candidates':[{'candidate_id':1,'domain':'example.com','market':'GB-EN','country':'GB'}]}

class CandidateRouteDurabilityTests(unittest.TestCase):
    def test_blob_io_is_fail_fast_under_parent_runtime_ceiling(self):
        self.assertLessEqual(w.BLOB_TIMEOUT_SECONDS,12)

    def run_main(self, initial_state, publish_result, remote_done):
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'state.json'
            state.write_text(json.dumps(initial_state))
            result={'candidate_id':1,'domain':'example.com','market':'GB-EN',
                    'verified':True,'pages':1,'errors':0}
            with patch.object(w,'STATE',state),                  patch.object(w,'messages',return_value=[dict(TASK)]),                  patch.object(w,'durable_done_task_ids',return_value=remote_done),                  patch.object(w,'publish_messages',return_value=publish_result),                  patch.object(w,'safe_inspect',return_value=result),                  patch.object(w,'PRIORITY_MARKETS',set()),                  patch.object(w,'PRIORITY_STRICT',False),                  patch.object(w,'LANE_COUNT',1),                  patch.object(w,'LANE_INDEX',0),                  patch.object(w,'LANE_WORKERS',4),                  patch.object(w,'LANE_BATCH',16):
                w.main()
            return json.loads(state.read_text())

    def test_publish_failure_does_not_checkpoint_task(self):
        state=self.run_main({'processed_task_ids':[]},('NO_RESULT_TRANSPORT',False),set())
        self.assertNotIn('task-1',state['processed_task_ids'])
        self.assertFalse(state['publish_ok'])
        self.assertEqual(state['committed_tasks'],0)

    def test_publish_success_checkpoints_task(self):
        state=self.run_main({'processed_task_ids':[]},('SUPERJSONBLOB_V1',True),set())
        self.assertIn('task-1',state['processed_task_ids'])
        self.assertTrue(state['publish_ok'])
        self.assertEqual(state['committed_tasks'],1)

    def test_stale_local_processed_without_durable_done_is_reopened(self):
        state=self.run_main({'processed_task_ids':['task-1']},('SUPERJSONBLOB_V1',True),set())
        self.assertEqual(state['stale_local_done_reopened'],1)
        self.assertIn('task-1',state['processed_task_ids'])
        self.assertEqual(state['last_tasks'],1)
        self.assertEqual(state['last_candidates'],1)

    def test_durable_done_keeps_processed_task_skipped(self):
        state=self.run_main({'processed_task_ids':['task-1']},('SUPERJSONBLOB_V1',True),{'task-1'})
        self.assertEqual(state['stale_local_done_reopened'],0)
        self.assertEqual(state['last_tasks'],0)
        self.assertEqual(state['last_candidates'],0)

    def test_truncated_task_is_not_checkpointed(self):
        candidates=[{'candidate_id':i,'domain':f'c{i}.example.com','market':'GB-EN','country':'GB'}
                    for i in range(20)]
        task=dict(TASK,candidates=candidates)
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'state.json';state.write_text(json.dumps({'processed_task_ids':[]}))
            result={'candidate_id':1,'domain':'example.com','market':'GB-EN','verified':True,'pages':1,'errors':0}
            with patch.object(w,'STATE',state), patch.object(w,'messages',return_value=[task]), \
                 patch.object(w,'durable_done_task_ids',return_value=set()), \
                 patch.object(w,'publish_messages',return_value=('SUPERJSONBLOB_V1',True)), \
                 patch.object(w,'safe_inspect',return_value=result), patch.object(w,'PRIORITY_MARKETS',set()), \
                 patch.object(w,'PRIORITY_STRICT',False), patch.object(w,'LANE_COUNT',1), \
                 patch.object(w,'LANE_INDEX',0), patch.object(w,'LANE_WORKERS',4), patch.object(w,'LANE_BATCH',16):
                w.main()
            out=json.loads(state.read_text())
        self.assertEqual(out['last_candidates'],16)
        self.assertNotIn('task-1',out['processed_task_ids'])
        self.assertEqual(out['committed_tasks'],0)

    def test_32_results_are_persisted_before_done_checkpoint(self):
        candidates=[{'candidate_id':i,'domain':f'c{i}.example.com','market':'GB-EN','country':'GB'}
                    for i in range(33)]
        task=dict(TASK,candidates=candidates)
        calls=[]
        def publish(msgs):
            calls.append(msgs)
            return ('SUPERJSONBLOB_V1',True)
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'state.json';state.write_text(json.dumps({'processed_task_ids':[]}))
            result={'candidate_id':1,'domain':'example.com','market':'GB-EN','verified':True,'pages':1,'errors':0}
            with patch.object(w,'STATE',state), patch.object(w,'messages',return_value=[task]), \
                 patch.object(w,'durable_done_task_ids',return_value=set()), \
                 patch.object(w,'publish_messages',side_effect=publish), \
                 patch.object(w,'safe_inspect',return_value=result), patch.object(w,'PRIORITY_MARKETS',set()), \
                 patch.object(w,'PRIORITY_STRICT',False), patch.object(w,'LANE_COUNT',1), \
                 patch.object(w,'LANE_INDEX',0), patch.object(w,'LANE_WORKERS',8), patch.object(w,'LANE_BATCH',64):
                w.main()
            out=json.loads(state.read_text())
        self.assertGreaterEqual(len(calls),2)
        self.assertTrue(all(m.get('kind')!='PAL_CANDIDATE_ROUTE_TASK_DONE_V1' for m in calls[0]))
        self.assertTrue(any(m.get('kind')=='PAL_CANDIDATE_ROUTE_TASK_DONE_V1' for m in calls[-1]))
        self.assertIn('task-1',out['processed_task_ids'])

if __name__=='__main__':
    unittest.main()
