import unittest
from unittest.mock import patch
import stage3_send_ready_worker_v1 as w

class _Headers:
    def __init__(self,ctype='text/html; charset=utf-8'): self.ctype=ctype
    def get(self,k,default=None): return self.ctype if k.lower()=='content-type' else default
    def get_content_charset(self): return 'utf-8'

class _Resp:
    def __init__(self,url,body=b'hello',ctype='text/html; charset=utf-8'):
        self._url=url; self._body=body; self.headers=_Headers(ctype)
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def geturl(self): return self._url
    def read(self,n=-1): return self._body[:n] if n>=0 else self._body

class Stage3HttpBodyFallbackTests(unittest.TestCase):
    def test_same_origin_text_is_returned(self):
        with patch.object(w.urllib.request,'urlopen',return_value=_Resp('https://www.example.com/contact',b'No sales here')):
            self.assertEqual(w.fetch_same_origin_text('https://example.com/contact','example.com'),'No sales here')

    def test_cross_origin_redirect_is_rejected(self):
        with patch.object(w.urllib.request,'urlopen',return_value=_Resp('https://other.example/contact',b'content')):
            self.assertEqual(w.fetch_same_origin_text('https://example.com/contact','example.com'),'')

    def test_binary_content_is_rejected(self):
        with patch.object(w.urllib.request,'urlopen',return_value=_Resp('https://example.com/file',b'abc','application/octet-stream')):
            self.assertEqual(w.fetch_same_origin_text('https://example.com/file','example.com'),'')

if __name__=='__main__':
    unittest.main()
