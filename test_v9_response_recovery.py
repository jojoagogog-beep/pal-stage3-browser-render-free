import unittest
import v9_send_worker as w

class Resp:
    def __init__(self,status=302,location='/done'):
        self.status=status
        self.headers={'location':location}

class Req:
    def __init__(self,resp):
        self.method='POST'
        self.url='https://example.com/contact'
        self._resp=resp
        self.calls=0
    async def response(self):
        self.calls+=1
        return self._resp

class ResponseRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovers_correlated_response_once(self):
        req=Req(Resp(302,'/thanks'))
        responses=[];objs=[]
        n=await w.recover_correlated_request_responses([req],responses,objs)
        self.assertEqual(n,1)
        self.assertEqual(responses[0]['status'],302)
        self.assertEqual(responses[0]['location'],'/thanks')
        self.assertTrue(responses[0]['matches_form_payload'])
        self.assertEqual(len(objs),1)

    async def test_deduplicates_existing_response(self):
        req=Req(Resp(302,'/thanks'))
        responses=[{'method':'POST','url':req.url,'status':302,'location':'/thanks','matches_form_payload':True}]
        objs=[]
        n=await w.recover_correlated_request_responses([req],responses,objs)
        self.assertEqual(n,0)
        self.assertEqual(len(responses),1)

if __name__=='__main__':
    unittest.main()
