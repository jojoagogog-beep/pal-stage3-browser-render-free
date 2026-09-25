import pathlib,re,unittest

class TaskBarrierIOBound(unittest.TestCase):
    def test_click_barrier_uses_short_fail_closed_io(self):
        s=pathlib.Path('v9_send_worker.py').read_text()
        self.assertIn("TASK_BARRIER_IO_TIMEOUT=max(2.0,min(8.0",s)
        m=re.search(r"def _mark_click_started\(task\):(.*?)\ndef _cloud_control_ok",s,re.S)
        self.assertIsNotNone(m)
        block=m.group(1)
        self.assertIn("for attempt in range(2):",block)
        self.assertIn("_get_task(TASK_URL)",block)
        self.assertIn("_put_task(TASK_URL,q)",block)
        self.assertNotIn("_get(TASK_URL)",block)
        self.assertNotIn("_put(TASK_URL,q)",block)

    def test_submit_barrier_uses_short_task_io(self):
        s=pathlib.Path('v9_send_worker.py').read_text()
        m=re.search(r"async def await_submit_barrier\(.*?\):(.*?)\nasync def process_task",s,re.S)
        self.assertIsNotNone(m)
        self.assertIn("asyncio.to_thread(_get_task,TASK_URL)",m.group(1))
        self.assertNotIn("asyncio.to_thread(_get,TASK_URL)",m.group(1))

if __name__=='__main__': unittest.main()
