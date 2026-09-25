import unittest
from unittest.mock import AsyncMock, patch
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
    async def test_refresh_reacquires_final_before_barrier(self):
        old=(0,Loc(True,True,trial_fail=True),'Send')
        new=(1,Loc(True,True),'Send')
        with patch.object(w,'control_actionable',new=AsyncMock(side_effect=[False,True])), \
             patch.object(w,'final_control_matching_text',new=AsyncMock(return_value=new)) as find, \
             patch.object(w.asyncio,'sleep',new=AsyncMock()):
            got=await w.refresh_actionable_control(object(),old,'final','Send')
        self.assertIs(got,new)
        find.assert_awaited_once()

    async def test_stage3_submit_text_recovers_generic_ambiguity(self):
        form=object(); expected=(1,Loc(True,True),'Send')
        with patch.object(w,'control',new=AsyncMock(side_effect=[None,None])), \
             patch.object(w,'final_control_matching_text',new=AsyncMock(return_value=expected)) as find:
            confirm,final=await w.resolve_pre_submit_controls(form,False,False,'Send')
        self.assertIsNone(confirm)
        self.assertIs(final,expected)
        find.assert_awaited_once_with(form,'Send')

    async def test_stage3_submit_text_does_not_bypass_confirm_step(self):
        form=object(); generic_final=(0,Loc(True,True),'Send')
        with patch.object(w,'control',new=AsyncMock(side_effect=[None,generic_final])), \
             patch.object(w,'final_control_matching_text',new=AsyncMock()) as find:
            confirm,final=await w.resolve_pre_submit_controls(form,True,False,'Send')
        self.assertIs(confirm,generic_final)
        self.assertIsNone(final)
        find.assert_not_awaited()

if __name__=='__main__':
    unittest.main()
