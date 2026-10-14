"""Real elapsed-state metadata and duplicate prevention, using blocking local transports."""

import json
import threading
import unittest
from unittest.mock import patch

import httpx
import test_prepare_plan as fixtures


class OperationProgressTests(unittest.TestCase):
    def test_inflight_planning_is_visible_and_duplicate_rejected_without_retry(self):
        fx=fixtures.PreparePlanTests(); fx.setUp(); self.addCleanup(fx.doCleanups)
        state=fx.load_case(); entered=threading.Event(); release=threading.Event(); responses=[]
        def response(body,result):
            entered.set()
            if not release.wait(5): raise AssertionError('Test was not released')
            return httpx.Response(200,json={'id':'resp_progress','status':'completed','output':[{'type':'message','id':'msg','role':'assistant','content':[{'type':'output_text','text':json.dumps(result),'annotations':[]}]}]})
        with fx.with_ai(response):
            worker=threading.Thread(target=lambda:responses.append(fx.action(state,'understand')))
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                client=fx.app.test_client()
                current=client.get('/api/sessions/'+state['id']).json['activity']
                self.assertEqual(current['status'],'RUNNING'); self.assertEqual(current['action'],'understand')
                self.assertTrue(current['started_at']); self.assertTrue(current['api_call_attempted'])
                second=client.post('/api/sessions/'+state['id']+'/action',headers=fixtures.HEADERS,
                    json={'revision':state['revision'],'action':'understand'})
                self.assertEqual(second.status_code,409)
                self.assertEqual(len(fx.requests),1)
            finally:
                release.set(); worker.join(5)
        self.assertEqual(responses[0].status_code,200)
        final=fx.client.get('/api/sessions/'+state['id']).json['activity']
        self.assertEqual(final['status'],'AI_RESULT_RECEIVED'); self.assertIn('elapsed_seconds',final)
        self.assertTrue(final['finished_at'])

    def test_interrupted_planning_is_not_automatically_retried(self):
        fx=fixtures.PreparePlanTests(); fx.setUp(); self.addCleanup(fx.doCleanups)
        state=fx.load_case(); folder=fx.runtime/'sessions'/state['id']/'calls'/('4'*32); folder.mkdir(parents=True)
        (folder/'run.json').write_text(json.dumps({'id':'4'*32,'started_at':'2026-10-14T01:00:00+00:00','status':'RUNNING','action':'understand','api_call_attempted':True}))
        before=(folder/'run.json').read_bytes()
        restarted=fixtures.web.create_app(fx.runtime,fx.case).test_client()
        activity=restarted.get('/api/sessions/'+state['id']).json['activity']
        self.assertEqual(activity['status'],'INTERRUPTED')
        self.assertEqual((folder/'run.json').read_bytes(),before)
        self.assertEqual(fx.requests,[])
        with fx.client.get('/static/prepare.js') as response:
            script=response.get_data(as_text=True); self.assertIn('已等待',script); self.assertIn("setInterval(drawProgress,1000)",script)
            self.assertNotIn('90%',script)


if __name__=='__main__': unittest.main()
