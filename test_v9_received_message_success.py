import unittest
import v9_send_worker as w

class ReceivedMessageSuccessTests(unittest.TestCase):
    def test_weve_received_your_message(self):
        self.assertIsNotNone(w.SUCCESS.search("We've received your message and will respond within 1-2 business days."))

    def test_we_have_received_your_message(self):
        self.assertIsNotNone(w.SUCCESS.search("We have received your message."))

    def test_plain_contact_copy_is_not_success(self):
        self.assertIsNone(w.SUCCESS.search("Send us a message and we will get back to you."))

if __name__=='__main__':
    unittest.main()
