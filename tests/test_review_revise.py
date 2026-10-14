"""T04 offline checks; real clients are blocked by the existing SDK fixtures."""

import io
import json
from pathlib import Path
import unittest
import zipfile

import httpx
import test_generate_plan_image as fixtures


class ReviewReviseTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.state = self.fx.state
        self.client = self.fx.client
        self.folder = self.fx.store.folder(self.state['id'])
        with self.fx.with_sdk():
            self.assertEqual(self.fx.post('reference_001').status_code, 200)

    def card(self, target='reference_001'):
        return next(c for c in self.fx.cards().json['cards'] if c['id']==target)

    def review(self, action, run_id, target='reference_001'):
        return self.client.post(f"/api/sessions/{self.state['id']}/review/{target}", headers=fixtures.HEADERS,
            json={'confirmed_revision':self.state['revision'],'card_revision':self.card(target)['card_revision'],'action':action,'run_id':run_id})

    def edit(self, feedback='背景改成更浅的粉色；保留商品及文字', operation_id=None, target='reference_001', parent=None):
        card=self.card(target)
        return self.client.post(f"/api/sessions/{self.state['id']}/revise/{target}", headers=fixtures.HEADERS,
            json={'confirmed_revision':self.state['revision'],'card_revision':card['card_revision'],
                  'operation_id':operation_id or __import__('uuid').uuid4().hex,'parent_run_id':parent or card['selected_run'],'feedback':feedback})

    def test_edit_uses_selected_image_first_exact_context_and_preserves_versions(self):
        original={p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        v1=self.card()['selected_run']
        with self.fx.with_sdk():
            result=self.edit()
        self.assertEqual(result.status_code,200,result.json)
        request=self.fx.requests[-1].read()
        self.assertLess(request.index(b'filename="current_image.png"'),request.index(b'filename="product_001.png"'))
        self.assertNotIn(b'DO_NOT_SEND_OTHER_IMAGE_HISTORY',request)
        self.assertNotIn(b'reference_002',request)
        run=next(self.folder.glob(f"generations/**/runs/{result.json['run_id']}"))
        record=json.loads((run/'run.json').read_text()); arguments=json.loads((run/'request.json').read_text())
        self.assertEqual(record['action'],'revise_image'); self.assertEqual(record['parent_run_id'],v1)
        self.assertEqual(record['parent_version'],1); self.assertEqual(record['version'],2)
        self.assertEqual(arguments['image_order'][0]['role'],'current_image')
        self.assertEqual(arguments['prompt'],(run/'prompt.txt').read_text())
        self.assertIn(self.state['inputs']['listing'],arguments['prompt'])
        self.assertIn(self.state['inputs']['requirements'],arguments['prompt'])
        self.assertIn(self.state['plans']['reference_001']['design'],arguments['prompt'])
        self.assertEqual([v['version'] for v in self.card()['versions']],[1,2])
        for path,data in original.items():
            if path.name!='current.json': self.assertEqual(path.read_bytes(),data)
        self.assertEqual(self.card('reference_002')['versions'],[])

    def test_pass_selection_branching_and_final_zip_use_accepted_version(self):
        v1=self.card()['selected_run']; self.assertEqual(self.review('pass',v1).status_code,200)
        with self.fx.with_sdk(): self.assertEqual(self.edit().status_code,200)
        v2=self.card()['selected_run']; self.assertNotEqual(v1,v2)
        self.assertEqual(self.card()['passed_run'],v1)
        self.assertEqual(self.review('select',v1).status_code,200)
        with self.fx.with_sdk(): self.assertEqual(self.edit().status_code,200)
        v3=self.card()['selected_run']; self.assertEqual(self.card()['versions'][-1]['parent_run_id'],v1)
        self.assertEqual(self.card()['passed_run'],v1)
        response=self.client.post(f"/api/sessions/{self.state['id']}/export-passed",headers=fixtures.HEADERS)
        self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(),['图片_01_V1.png'])
            self.assertEqual(archive.read(archive.namelist()[0]),next(self.folder.glob(f'generations/**/runs/{v1}/image.png')).read_bytes())
        self.assertEqual(self.review('pass',v3).status_code,200)
        self.assertEqual(self.card()['passed_run'],v3)
        restarted=fixtures.web.create_app(self.fx.runtime).test_client()
        data=restarted.get(f"/api/sessions/{self.state['id']}/generation").json
        self.assertEqual(data['cards'][0]['selected_run'],v3)
        self.assertEqual(data['cards'][0]['passed_run'],v3)
        events=[json.loads(p.read_text()) for p in self.folder.glob('generations/*/*/reviews/*.json')]
        self.assertEqual([e['action'] for e in sorted(events,key=lambda e:e['created_at'])],['pass','select','pass'])

    def test_failed_edit_preserves_accepted_and_selected_versions_no_auto_retry(self):
        v1=self.card()['selected_run']; self.review('pass',v1)
        before={p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file() and p.name!='current.json'}
        count=len(self.fx.requests)
        with self.fx.with_sdk(lambda request:httpx.Response(500,json={'error':{'message':'offline failure','type':'server_error'}})):
            response=self.edit()
        self.assertEqual(response.status_code,502); self.assertEqual(len(self.fx.requests),count+1)
        self.assertIn('计费尚未确认',response.json['error'])
        card=self.card(); self.assertEqual(card['selected_run'],v1); self.assertEqual(card['passed_run'],v1)
        self.assertEqual(len(card['versions']),1)
        for path,data in before.items(): self.assertEqual(path.read_bytes(),data)

    def test_same_operation_replay_does_not_call_model_twice(self):
        op='1'*32
        parent=self.card()['selected_run']
        with self.fx.with_sdk(): first=self.edit(operation_id=op)
        count=len(self.fx.requests)
        second=self.edit(operation_id=op,parent=parent)
        self.assertEqual(second.status_code,200); self.assertEqual(first.json['run_id'],second.json['run_id'])
        self.assertEqual(len(self.fx.requests),count)
        self.assertEqual(self.edit(feedback='changed',operation_id=op,parent=parent).status_code,409)

    def test_foreign_run_stale_version_empty_feedback_and_symlink_rejected_before_api(self):
        other=self.fx.confirmed(1)
        with self.fx.with_sdk(): self.assertEqual(self.fx.post('reference_001',other).status_code,200)
        foreign=self.fx.cards(other).json['cards'][0]['selected_run']
        self.assertEqual(self.edit(parent=foreign).status_code,409)
        self.assertEqual(self.review('select',foreign).status_code,409)
        self.assertEqual(self.edit(feedback='').status_code,400)
        card=self.card(); self.review('pass',card['selected_run'])
        response=self.client.post(f"/api/sessions/{self.state['id']}/revise/reference_001",headers=fixtures.HEADERS,
            json={'confirmed_revision':self.state['revision'],'card_revision':card['card_revision'],'operation_id':'2'*32,'parent_run_id':card['selected_run'],'feedback':'change'})
        self.assertEqual(response.status_code,409)

    def test_experiment_zip_keeps_t04_requests_parent_input_and_review_events(self):
        with self.fx.with_sdk(): response=self.edit()
        self.review('pass',response.json['run_id'])
        exported=self.client.post(f"/api/sessions/{self.state['id']}/export-experiment",headers=fixtures.HEADERS)
        self.assertEqual(exported.status_code,200,exported.json)
        with zipfile.ZipFile(io.BytesIO(exported.data)) as archive:
            manifest=json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/manifest.json'))))
            edit=next(r for r in manifest['runs'] if r['stage']=='T04')
            self.assertEqual(edit['version'],2); self.assertEqual(edit['inputs'][0]['id'],'current_image')
            self.assertTrue(any('/reviews/' in n for n in archive.namelist()))
            self.assertFalse(any('.env' in n for n in archive.namelist()))


if __name__=='__main__': unittest.main()
