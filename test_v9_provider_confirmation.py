import unittest
from pathlib import Path
import v9_send_worker as w

class Node:
    def __init__(self,visible): self.visible=visible
    async def is_visible(self): return self.visible

class Nodes:
    def __init__(self,values): self.values=[Node(x) for x in values]
    async def count(self): return len(self.values)
    def nth(self,i): return self.values[i]

class Page:
    def __init__(self,mapping): self.mapping=mapping
    def locator(self,sel): return Nodes(self.mapping.get(sel,[]))

class ProviderConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_gravity_confirmation_visible(self):
        p=Page({'[id^="gform_confirmation_message_"]':[True]})
        self.assertTrue(await w.provider_confirmation_visible(p))

    async def test_siteplus_confirmation_visible_only_after_reveal(self):
        p=Page({'.form__holder.form-success.success':[False,True]})
        self.assertTrue(await w.provider_confirmation_visible(p))
        p=Page({'.form__holder.form-success.success':[False]})
        self.assertFalse(await w.provider_confirmation_visible(p))

    async def test_no_provider_confirmation(self):
        p=Page({})
        self.assertFalse(await w.provider_confirmation_visible(p))

    def test_confirmation_is_wired_to_success_evidence(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn("'provider_confirmation_dom':provider_confirmation_dom",src)
        self.assertIn("provider_success or provider_confirmation_dom or new_success",src)

if __name__=='__main__':
    unittest.main()
