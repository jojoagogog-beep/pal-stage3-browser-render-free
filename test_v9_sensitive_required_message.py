import unittest
import v9_send_worker as w

class SensitiveRequiredMessageTests(unittest.TestCase):
    def test_phone_required_is_failure(self):
        for text in (
            'Phone number is required.',
            'Phone required',
            'Telephone is required',
            'Mobile phone is required',
            'ZIP is required',
            'Postal code required',
        ):
            self.assertIsNotNone(w.FAIL.search(text), text)

    def test_optional_sensitive_wording_is_not_failure(self):
        for text in (
            'Phone number (optional)',
            'Telephone optional',
            'Address line 2 optional',
        ):
            self.assertIsNone(w.FAIL.search(text), text)

if __name__=='__main__':
    unittest.main()
