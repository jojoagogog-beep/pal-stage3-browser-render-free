import unittest
import v9_send_worker as sender
import stage3_send_ready_worker_v1 as stage3

class EmailClientFormTests(unittest.TestCase):
    def test_email_client_copy_is_rejected_by_both_layers(self):
        samples = [
            "Opens your email client with the message ready to send.",
            "Your email draft is ready — hit send in your mail client.",
            "mailto:sales@example.com",
        ]
        for text in samples:
            self.assertIsNotNone(sender.EMAIL_CLIENT_FORM.search(text), text)
            self.assertIsNotNone(stage3.EMAIL_CLIENT_FORM.search(text), text)

    def test_normal_web_form_copy_is_allowed(self):
        text = "Send your message through this contact form."
        self.assertIsNone(sender.EMAIL_CLIENT_FORM.search(text))
        self.assertIsNone(stage3.EMAIL_CLIENT_FORM.search(text))

if __name__ == "__main__":
    unittest.main()
