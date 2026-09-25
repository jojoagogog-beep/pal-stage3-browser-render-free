import unittest
import v9_send_worker as w

class SubmissionRejectedTests(unittest.TestCase):
    def test_submission_rejected_is_failure(self):
        self.assertIsNotNone(w.FAIL.search('Submission Rejected'))
        self.assertIsNotNone(w.FAIL.search('Form submission rejected'))

    def test_explicit_submission_failure_is_failure(self):
        self.assertIsNotNone(w.FAIL.search('Your submission failed because of a server error.'))
        self.assertIsNotNone(w.FAIL.search('Form submission declined'))

    def test_generic_ui_error_is_not_enough_by_itself(self):
        self.assertIsNone(w.FAIL.search('Something went wrong'))

    def test_error_path_is_negative_evidence(self):
        self.assertIsNotNone(w.ERROR_PATH.search('/contact/error.htm'))
        self.assertIsNone(w.ERROR_PATH.search('/contact/success/'))

    def test_normal_success_message_is_not_failure(self):
        self.assertIsNone(w.FAIL.search('Thank you! We have received your email and will be in touch shortly.'))

if __name__=='__main__':
    unittest.main()
