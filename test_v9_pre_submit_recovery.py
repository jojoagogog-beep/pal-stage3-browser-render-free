import unittest
from pathlib import Path
import v9_send_worker as w

class PreSubmitRecoveryTests(unittest.TestCase):
    def test_email_example_placeholder_is_recognized(self):
        self.assertIsNotNone(w.EMAIL_EXAMPLE.search('you@company.com'))
        self.assertIsNone(w.EMAIL_EXAMPLE.search('company.com'))

    def test_safe_confirmation_check_text(self):
        self.assertIsNotNone(w.SUBMIT_CONFIRM_CHECK.search('上記の内容でよろしければチェックボックスにチェックを入れてください。チェックがないと送信できません'))
        self.assertIsNone(w.SUBMIT_CONFIRM_CHECK.search('ニュースレターを購読する'))

    def test_lazy_form_reveal_is_wired(self):
        src=Path('v9_send_worker.py').read_text()
        self.assertIn('async def reveal_candidate_forms',src)
        self.assertIn('await reveal_candidate_forms(page',src)

    def test_privacy_policy_is_safe_consent(self):
        text='By checking this box, I agree to the Privacy Policy'
        self.assertIsNotNone(w.CONSENT_OK.search(text))
        self.assertIsNone(w.CONSENT_BAD.search(text))

class VisibleFieldRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_reacquire_prefers_current_visible_identity(self):
        class Fields:
            def __init__(self): self.items=['stale-hidden','current-visible']
            async def evaluate_all(self,script,arg): return [1]
            def nth(self,i): return self.items[i]
        class Form:
            def locator(self,sel): return Fields()
        self.assertEqual(
            await w.reacquire_visible_field(Form(),name='email',eid='email',fallback_index=0),
            'current-visible')

    def test_fill_flags_are_set_only_after_successful_fill(self):
        src=Path('v9_send_worker.py').read_text()
        start=src.index('value=None;is_email_field=False;is_message_field=False')
        end=src.index('except Exception as ex:',start)
        block=src[start:end]
        self.assertLess(block.index('await target.fill(value,timeout=3000)'),block.index("if is_email_field:filled['email']=True"))
        self.assertNotIn("EMAIL.search(d) or EMAIL_EXAMPLE.search(d):value=email;filled['email']=True",block)
        self.assertNotIn("form.locator(f'[name=",block)

class SafeCheckboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_label_fallback_checks_consent(self):
        class Loc:
            def __init__(self): self.checked=False
            async def check(self,timeout=None): raise RuntimeError('native hidden')
            async def is_checked(self,timeout=None): return self.checked
            async def evaluate(self,script): self.checked=True
        self.assertTrue(await w.safe_checkbox_check(Loc()))

    async def test_failed_label_fallback_returns_false(self):
        class Loc:
            async def check(self,timeout=None): raise RuntimeError('native hidden')
            async def is_checked(self,timeout=None): return False
            async def evaluate(self,script): raise RuntimeError('no label')
        self.assertFalse(await w.safe_checkbox_check(Loc()))

if __name__=='__main__':
    unittest.main()
