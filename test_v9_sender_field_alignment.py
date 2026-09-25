import unittest
import v9_send_worker as w

class SenderSafeSelectAlignmentTests(unittest.TestCase):
    def test_single_safe_choice_is_selected(self):
        opts=[
            {'v':'','t':'Select one'},
            {'v':'learn','t':'Learn More'},
            {'v':'partner','t':'Explore Partnership Opportunities'},
        ]
        self.assertEqual(w.safe_select_value(opts),'partner')

    def test_ambiguous_safe_choices_fail_closed(self):
        opts=[{'v':'general','t':'General'},{'v':'other','t':'Other'}]
        self.assertIsNone(w.safe_select_value(opts))

    def test_unsafe_choice_is_never_selected(self):
        opts=[{'v':'career','t':'Career'},{'v':'support','t':'Technical Support'}]
        self.assertIsNone(w.safe_select_value(opts))

class SenderStickyFillTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_value_fallback_survives_framework_overwrite(self):
        class Loc:
            def __init__(self): self.value=''
            async def fill(self,value,timeout=None): self.value=''
            async def input_value(self,timeout=None): return self.value
            async def evaluate(self,script,value): self.value=value
        loc=Loc()
        await w.sticky_fill(loc,'Practical AI Lab')
        self.assertEqual(loc.value,'Practical AI Lab')

if __name__=='__main__':
    unittest.main()
