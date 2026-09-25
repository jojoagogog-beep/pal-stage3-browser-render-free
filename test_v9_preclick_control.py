import unittest
import v9_send_worker as w

class Loc:
    def __init__(self,visible=True,enabled=True,fail=False,trial_fail=False):
        self.visible=visible; self.enabled=enabled; self.fail=fail; self.trial_fail=trial_fail
    async def is_visible(self):
        if self.fail: raise RuntimeError('detached')
        return self.visible
    async def is_enabled(self):
        if self.fail: raise RuntimeError('detached')
        return self.enabled
    async def click(self,trial=False,timeout=None):
        if self.trial_fail: raise RuntimeError('not actionable')
        return None

class PreclickControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_actionable_control_passes(self):
        self.assertTrue(await w.control_actionable((0,Loc(True,True),'Submit')))
    async def test_hidden_control_fails(self):
        self.assertFalse(await w.control_actionable((0,Loc(False,True),'Submit')))
    async def test_disabled_control_fails(self):
        self.assertFalse(await w.control_actionable((0,Loc(True,False),'Submit')))
    async def test_detached_control_fails(self):
        self.assertFalse(await w.control_actionable((0,Loc(fail=True),'Submit')))
    async def test_trial_actionability_failure_fails_before_barrier(self):
        self.assertFalse(await w.control_actionable((0,Loc(True,True,trial_fail=True),'Submit')))

if __name__=='__main__':
    unittest.main()
