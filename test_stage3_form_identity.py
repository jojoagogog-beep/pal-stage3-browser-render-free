import asyncio
import unittest
from unittest.mock import patch
import stage3_send_ready_worker_v1 as w

class FormIdentityTests(unittest.TestCase):
    def test_first_form_main_frame_survives_rescan(self):
        self.assertTrue(w.same_form_snapshot({'index':0,'frame_index':0},{'index':0,'frame_index':0}))
    def test_first_form_in_iframe_survives_rescan(self):
        self.assertTrue(w.same_form_snapshot({'index':0,'frame_index':2},{'index':0,'frame_index':2}))
    def test_different_form_or_frame_rejected(self):
        for after in ({'index':1,'frame_index':0},{'index':0,'frame_index':1}):
            self.assertFalse(w.same_form_snapshot({'index':0,'frame_index':0},after))
    def test_missing_and_malformed_indexes_fail_closed(self):
        for after in (None,{}, {'index':0}, {'index':-1,'frame_index':0}, {'index':False,'frame_index':0}, {'index':'0','frame_index':0}):
            self.assertFalse(w.same_form_snapshot({'index':0,'frame_index':0},after))

class TimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_records_phase_and_never_emits_proof(self):
        async def stalled(browser,rec,sem,slow=False,progress=None):
            progress['phase']='fill_fields'
            await asyncio.Event().wait()
        with patch.object(w,'inspect',stalled):
            result=await w.inspect_with_timeout(None,{'route_id':1},None,.01)
        self.assertEqual(result['timeout_phase'],'fill_fields')
        self.assertEqual(result['status'],'TECH_DEFER')
        self.assertFalse(result['stage3_send_ready'])
    async def test_external_cancellation_is_not_swallowed(self):
        async def stalled(*args,**kwargs): await asyncio.Event().wait()
        with patch.object(w,'inspect',stalled):
            task=asyncio.create_task(w.inspect_with_timeout(None,{'route_id':1},None,10))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
    async def test_completed_verdict_preserved(self):
        expected={'status':'REQUIRED_SENSITIVE','stage3_send_ready':False}
        async def done(*args,**kwargs):return expected
        with patch.object(w,'inspect',done):
            self.assertEqual(await w.inspect_with_timeout(None,{},None,.01),expected)

if __name__=='__main__': unittest.main()
