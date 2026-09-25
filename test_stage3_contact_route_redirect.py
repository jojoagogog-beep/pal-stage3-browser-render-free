import unittest
import stage3_send_ready_worker_v1 as w

class ContactRouteRedirectTests(unittest.TestCase):
    def test_contact_route_to_home_is_rejected(self):
        self.assertTrue(w.contact_route_lost_to_home(
            'https://www.tekbasic.com/contact.html',
            'https://www.tekbasic.com/'
        ))

    def test_contact_route_with_www_alias_same_path_is_allowed(self):
        self.assertFalse(w.contact_route_lost_to_home(
            'https://tekbasic.com/contact.html',
            'https://www.tekbasic.com/contact.html'
        ))

    def test_non_contact_route_to_home_is_not_classified_here(self):
        self.assertFalse(w.contact_route_lost_to_home(
            'https://example.com/products',
            'https://example.com/'
        ))

    def test_real_contact_page_stays_allowed(self):
        self.assertFalse(w.contact_route_lost_to_home(
            'https://example.com/contact',
            'https://example.com/contact/'
        ))

if __name__=='__main__':
    unittest.main()
