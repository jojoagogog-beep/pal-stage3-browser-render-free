import unittest
import v9_send_worker as sender
import stage3_send_ready_worker_v1 as stage3

SCRIPT = r"""
if (document.getElementById("contact-page")) {
 const form = document.getElementById("contact-form");
 form.addEventListener("submit", async e => {
   const payload = { phone: val(inputs.phone?.value), message: val(inputs.message?.value) };
   if (!payload.phone) return displayMessage("Phone number is required.", "error");
   const res = await fetch("/api/contact", {method:"POST"});
 });
}
"""

class ScriptRequiredSensitiveTests(unittest.TestCase):
    def test_sender_detects_phone_required_from_contact_script(self):
        self.assertEqual(sender.script_required_sensitive_kinds(SCRIPT), {"phone"})

    def test_stage3_detects_same_phone_requirement(self):
        self.assertEqual(stage3.script_required_sensitive_kinds(SCRIPT), {"phone"})

    def test_non_contact_script_does_not_create_requirement(self):
        s='if (!payload.phone) alert("Phone required")'
        self.assertEqual(sender.script_required_sensitive_kinds(s), set())
        self.assertEqual(stage3.script_required_sensitive_kinds(s), set())

if __name__ == "__main__":
    unittest.main()
