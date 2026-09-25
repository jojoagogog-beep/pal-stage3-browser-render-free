import unittest
import v9_send_worker as w

class SubmissionRejectedTests(unittest.TestCase):
    def test_submission_rejected_is_failure(self):
        self.assertIsNotNone(w.FAIL.search('Submission Rejected'))
        self.assertIsNotNone(w.FAIL.search('Form submission rejected'))

    def test_normal_success_message_is_not_failure(self):
        self.assertIsNone(w.FAIL.search('Thank you! We have received your email and will be in touch shortly.'))

if __name__=='__main__':
    unittest.main()
