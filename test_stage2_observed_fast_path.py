import importlib.util

spec=importlib.util.spec_from_file_location('w','candidate_route_worker_v1.py')
w=importlib.util.module_from_spec(spec); spec.loader.exec_module(w)

calls=[]
HOME='''<html><body><a href="/about">About</a></body></html>'''
FORM='''<html><body><form method="post">
<input type="email" name="email" required>
<textarea name="message" required></textarea>
<button type="submit">Send</button>
</form></body></html>'''

def fake_fetch(url,timeout=4,max_bytes=600000):
    calls.append(url)
    if url == 'https://example.com/':
        return url,200,HOME
    if url == 'https://example.com/contact':
        return url,200,FORM
    if 'sitemap' in url or url.endswith('/robots.txt'):
        raise AssertionError('sitemap fallback should not run when observed route passes')
    return url,404,''

w.fetch=fake_fetch
rec={
    'candidate_id':1,'domain':'example.com','country':'GB','market':'GB-EN',
    'source_url':'https://example.com/','homepage_url':'https://example.com/',
    'observed_contact_urls':['https://example.com/contact'],
    'preferred_contact_paths':[],
}
out=w.inspect(rec)
assert out.get('route_hint'), out
assert out['route_hint']['contact_url']=='https://example.com/contact', out
assert out['route_hint']['stage2_evidence_pass'] is True, out
assert out['route_hint']['stage2_evidence']['official_same_domain'] is True, out
assert out['route_hint']['stage2_evidence']['captcha_absent'] is True, out
assert out['route_hint']['stage2_evidence']['sales_prohibited_absent'] is True, out
assert calls==['https://example.com/','https://example.com/contact'], calls
print('PASS observed_fast_path calls=',calls)

# A generic start/contact URL remains a fallback, but an explicit business
# route published on that same page must win inside the same bounded probe cap.
prefer_calls=[]
GENERIC_CONTACT='''<html><body>
<a href="/sales/contact">Contact our sales team</a>
<form method="post"><input type="email" name="email" required>
<textarea name="message" required></textarea><button type="submit">Send</button></form>
</body></html>'''
SALES_CONTACT='''<html><body><h1>Sales Contact</h1>
<form method="post"><input type="email" name="email" required>
<textarea name="message" required></textarea><button type="submit">Send</button></form>
</body></html>'''
def prefer_fetch(url,timeout=4,max_bytes=600000):
    prefer_calls.append(url)
    if url == 'https://prefer.example/contact':
        return url,200,GENERIC_CONTACT
    if url == 'https://prefer.example/sales/contact':
        return url,200,SALES_CONTACT
    return url,404,''
w.fetch=prefer_fetch
prefer={
    'candidate_id':11,'domain':'prefer.example','country':'GB','market':'GB-EN',
    'source_url':'https://prefer.example/contact',
    'homepage_url':'https://prefer.example/',
    'observed_contact_urls':[],
    'preferred_contact_paths':[],
}
out=w.inspect(prefer)
assert out.get('route_hint'),out
assert out['route_hint']['contact_url']=='https://prefer.example/sales/contact',out
assert out['route_hint']['explicit_business_hint'] is True,out
assert len(prefer_calls)<=1+w.LANE_DEPTH,prefer_calls
print('PASS explicit_business_route_preferred calls=',prefer_calls)

# Safety regression: an observed route with explicit sales prohibition must never pass.
unsafe_calls=[]
UNSAFE='''<html><body><p>No sales solicitations.</p><form method="post">
<input type="email" name="email"><textarea name="message"></textarea>
<button type="submit">Send</button></form></body></html>'''
def unsafe_fetch(url,timeout=4,max_bytes=600000):
    unsafe_calls.append(url)
    if url == 'https://unsafe.example/':
        return url,200,HOME
    if url == 'https://unsafe.example/contact':
        return url,200,UNSAFE
    return url,404,''
w.fetch=unsafe_fetch
bad={
    'candidate_id':2,'domain':'unsafe.example','country':'GB','market':'GB-EN',
    'source_url':'https://unsafe.example/','homepage_url':'https://unsafe.example/',
    'observed_contact_urls':['https://unsafe.example/contact'],
    'preferred_contact_paths':[],
}
out=w.inspect(bad)
assert not out.get('route_hint'), out
print('PASS sales_prohibition_still_blocks')

# One broken company must fail closed without aborting a wide batch.
orig_inspect=w.inspect
def boom(_rec):
    raise RuntimeError('fixture-broken-site')
w.inspect=boom
isolated=w.safe_inspect({'candidate_id':3,'domain':'broken.example','country':'GB','market':'GB-EN'})
w.inspect=orig_inspect
assert isolated['verified'] is False, isolated
assert isolated['errors']==1, isolated
assert isolated['worker_error']=='RuntimeError', isolated
assert 'route_hint' not in isolated, isolated
print('PASS candidate_exception_fail_isolated')
