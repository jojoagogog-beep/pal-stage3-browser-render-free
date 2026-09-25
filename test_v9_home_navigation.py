import unittest
import v9_send_worker as w

class HomeNavigationWithoutSubmissionTests(unittest.TestCase):
    def test_same_domain_contact_to_home_without_post_is_not_sent(self):
        self.assertTrue(w.home_navigation_without_submission(
            'https://www.tekbasic.com/contact.html',
            'https://www.tekbasic.com/',
            [],
            2,
            False,
        ))

    def test_real_submission_or_cleared_payload_is_not_classified_here(self):
        mutation=[{'url':'https://example.com/api/contact','method':'POST','matches_form_payload':True}]
        self.assertFalse(w.home_navigation_without_submission(
            'https://example.com/contact','https://example.com/',mutation,2,False))
        self.assertFalse(w.home_navigation_without_submission(
            'https://example.com/contact','https://example.com/',[],0,False))
        self.assertFalse(w.home_navigation_without_submission(
            'https://example.com/contact','https://example.com/',[],2,True))

    def test_unrelated_path_change_is_not_classified(self):
        self.assertFalse(w.home_navigation_without_submission(
            'https://example.com/contact','https://example.com/thanks',[],2,False))
        self.assertFalse(w.home_navigation_without_submission(
            'https://example.com/contact','https://other.example/',[],2,False))

if __name__ == '__main__':
    unittest.main()
