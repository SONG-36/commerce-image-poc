"""Task navigation and isolation checks; no real model clients."""

import io
import json
from unittest.mock import patch
import unittest
import zipfile

import test_generate_plan_image as fixtures


class TaskHomeTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.GenerationPageTests(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.client=self.fx.client
        block=patch.object(fixtures.web,'OpenAI',side_effect=AssertionError('Real planning API forbidden'))
        block.start(); self.addCleanup(block.stop)

    def create(self,title,marker):
        response=self.client.post('/api/sessions',headers=fixtures.HEADERS,
            data={'title':title,'product':(io.BytesIO(fixtures.png()),'p.png'),'reference':(io.BytesIO(fixtures.png()),'r.png'),
                  'listing':marker,'description':marker,'requirements':marker})
        self.assertEqual(response.status_code,200,response.json)
        return response.json['state']

    def test_named_creation_list_explicit_restore_and_new_page_do_not_auto_load_current(self):
        a=self.create('任务 A','A-only'); b=self.create('任务 B','B-only')
        self.assertNotEqual(a['id'],b['id'])
        self.assertIn('创建新任务',self.client.get('/').get_data(as_text=True))
        listing=self.client.get('/api/tasks').json['tasks']
        self.assertTrue({'任务 A','任务 B'}.issubset({t['title'] for t in listing}))
        for state in [a,b,a]:
            self.assertEqual(self.client.get('/prepare/'+state['id']).status_code,200)
            returned=self.client.get('/api/sessions/'+state['id']).json['state']
            self.assertEqual(returned['inputs'],state['inputs'])
        self.assertIn('data-session-id=""',self.client.get('/prepare/new').get_data(as_text=True))
        with self.client.get('/static/prepare.js') as response:
            self.assertNotIn('/api/current',response.get_data(as_text=True))
        self.assertEqual(self.client.get('/?session='+a['id']).location,'/prepare/'+a['id'])
        restarted=fixtures.web.create_app(self.fx.runtime).test_client()
        self.assertEqual(len(restarted.get('/api/tasks').json['tasks']),3)
        self.assertEqual(self.fx.requests,[])

    def test_generation_edit_review_and_exports_stay_with_the_named_task(self):
        a=self.fx.state; b=self.fx.confirmed(1)
        with self.fx.with_sdk():
            self.assertEqual(self.fx.post('reference_001',a).status_code,200)
            self.assertEqual(self.fx.post('reference_001',b).status_code,200)
        ca=self.fx.cards(a).json['cards'][0]; cb=self.fx.cards(b).json['cards'][0]
        self.assertEqual(self.client.post(f"/api/sessions/{b['id']}/review/reference_001",headers=fixtures.HEADERS,
            json={'confirmed_revision':b['revision'],'card_revision':cb['card_revision'],'run_id':cb['selected_run'],'action':'pass'}).status_code,200)
        self.assertEqual(self.client.post(f"/api/sessions/{a['id']}/export-passed",headers=fixtures.HEADERS).status_code,409)
        before_b={p:p.read_bytes() for p in self.fx.store.folder(b['id']).rglob('*') if p.is_file()}
        foreign=self.client.post(f"/api/sessions/{a['id']}/revise/reference_001",headers=fixtures.HEADERS,
            json={'confirmed_revision':a['revision'],'card_revision':ca['card_revision'],'parent_run_id':cb['selected_run'],'feedback':'change','operation_id':'3'*32})
        self.assertEqual(foreign.status_code,409)
        foreign_url=f"/api/sessions/{a['id']}/generated-images/{a['revision']}/reference_001/{cb['selected_run']}"
        self.assertEqual(self.client.get(foreign_url).status_code,404)
        self.assertEqual(self.client.post(f"/api/sessions/{a['id']}/review/reference_001",headers=fixtures.HEADERS,
            json={'confirmed_revision':a['revision'],'card_revision':ca['card_revision'],'run_id':ca['selected_run'],'action':'pass'}).status_code,200)
        exported=self.client.post(f"/api/sessions/{a['id']}/export-experiment",headers=fixtures.HEADERS)
        self.assertEqual(exported.status_code,200)
        with zipfile.ZipFile(io.BytesIO(exported.data)) as z:
            manifest=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/manifest.json'))))
            self.assertIn(ca['selected_run'],manifest['run_ids']); self.assertNotIn(cb['selected_run'],manifest['run_ids'])
        for p,data in before_b.items(): self.assertEqual(p.read_bytes(),data)

    def test_task_id_image_path_and_symlink_escape_are_rejected(self):
        self.assertEqual(self.client.get('/prepare/invalid').status_code,404)
        folder=self.fx.store.folder(self.fx.state['id'])
        state=json.loads((folder/'state.json').read_text())
        state['images'][0]['file']='../'+self.fx.confirmed(1)['id']+'/inputs/product_001.png'
        (folder/'state.json').write_text(json.dumps(state))
        self.assertEqual(self.client.get('/api/sessions/'+state['id']).status_code,409)
        original=self.fx.state
        (folder/'state.json').write_text(json.dumps(original))
        image=folder/original['images'][0]['file']
        outside=self.fx.store.folder(self.fx.confirmed(1)['id'])/'inputs/product_001.png'
        image.unlink(); image.symlink_to(outside)
        self.assertEqual(self.client.get('/api/sessions/'+state['id']).status_code,409)


if __name__=='__main__': unittest.main()
