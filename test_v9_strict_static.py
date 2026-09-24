import importlib.util
spec=importlib.util.spec_from_file_location('w','candidate_route_worker_v1.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
SAFE='''<html><body><form method="post" action="/contact"><input type="text" name="company" required><input type="text" name="name" required><input type="email" name="email" required><textarea name="message" required></textarea><button type="submit">Send</button></form></body></html>'''
p=w.strict_static_form_proof(SAFE,'https://example.com/contact',True);assert p and p['send_ready_proof_v2'] is True and p['control_kind']=='DIRECT_SUBMIT',p
PHONE=SAFE.replace('<textarea','<input type="tel" name="phone" required><textarea');assert w.strict_static_form_proof(PHONE,'https://example.com/contact',True) is None
UNKNOWN=SAFE.replace('<textarea','<input type="text" name="account_code" required><textarea');assert w.strict_static_form_proof(UNKNOWN,'https://example.com/contact',True) is None
CAP=SAFE.replace('<form','<div class="g-recaptcha"></div><form');assert w.strict_static_form_proof(CAP,'https://example.com/contact',True) is None
CROSS=SAFE.replace('action="/contact"','action="https://forms.other.test/x"');assert w.strict_static_form_proof(CROSS,'https://example.com/contact',True) is None
CONF=SAFE.replace('>Send</button>','>Confirm</button>');assert w.strict_static_form_proof(CONF,'https://example.com/contact',True) is None
NOINT=w.strict_static_form_proof(SAFE,'https://example.com/contact',False);assert NOINT is None
print('PASS')
