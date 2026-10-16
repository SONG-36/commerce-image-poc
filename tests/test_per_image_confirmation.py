"""Confirmation tokens, existing run buckets and batch cost guards; offline only."""

import copy
import io
import json
from pathlib import Path
import subprocess
import threading
import unittest
from uuid import uuid4
import zipfile

import httpx
import test_generate_plan_image as fixtures
import test_prepare_plan as planning


class PerImageConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.store, self.client = self.fx.store, self.fx.client
        self.state = self.fx.confirmed(3)
        self.state['confirmed'] = False
        self.store.save(self.state, {'action': 'offline_unconfirmed_fixture'})
        self.planner = planning.PreparePlanTests()
        self.planner.requests = []

    def view(self, state=None):
        return self.client.get(f"/api/sessions/{(state or self.state)['id']}/workspace").json

    def card(self, target, state=None):
        return next(c for c in self.view(state)['generation']['cards'] if c['id'] == target)

    def action(self, kind, target=None, feedback='', **extra):
        current = self.store.load(self.state['id'])
        response = self.client.post(f"/api/sessions/{current['id']}/action", headers=fixtures.HEADERS,
            json={'action': kind, 'target': target, 'revision': current['revision'], 'feedback': feedback, **extra})
        if response.status_code == 200:
            self.state = response.json['state']
        return response

    def confirm(self, target):
        response = self.action('confirm', target)
        self.assertEqual(response.status_code, 200, response.json)
        return self.card(target)

    def generate(self, target, *, batch=False, operation_id=None, state=None, client=None, **extra):
        state = state or self.state
        card = self.card(target, state)
        return (client or self.client).post(f"/api/sessions/{state['id']}/generate/{target}", headers=fixtures.HEADERS,
            json={'confirmed_revision': card['generation_revision'], 'card_revision': card['card_revision'],
                  'operation_id': operation_id or uuid4().hex, 'batch_only': batch, **extra})

    def operation(self, target, operation_id, revision=None, state=None):
        state = state or self.state
        revision = revision or self.card(target, state)['generation_revision']
        return self.client.get(f"/api/sessions/{state['id']}/operations/{target}/{operation_id}?confirmed_revision={revision}")

    def pass_card(self, target):
        card = self.card(target)
        response = self.client.post(f"/api/sessions/{self.state['id']}/review/{target}", headers=fixtures.HEADERS,
            json={'confirmed_revision': card['confirmed_revision'], 'card_revision': card['card_revision'],
                  'run_id': card['selected_run'], 'action': 'pass'})
        self.assertEqual(response.status_code, 200, response.json)

    def test_partial_confirmation_and_generation_are_bound_to_one_plan(self):
        first, second = fixtures.web.reference_ids(self.state)[:2]
        plans = copy.deepcopy(self.state['plans'])
        self.assertEqual(self.action('confirm').status_code, 400)
        self.assertEqual(self.action('confirm', first, plan_version=999).status_code, 409)
        first_card = self.confirm(first)
        entry = self.state['plan_confirmations'][first]
        self.assertEqual(entry['revision'], self.state['revision'])
        self.assertEqual(entry['plan_version'], first_card['plan_status']['plan_version'])
        self.assertEqual(self.state['plans'], plans)
        self.assertFalse(self.state['confirmed'])
        self.assertTrue(self.card(first)['generation_allowed'])
        self.assertFalse(self.card(second)['generation_allowed'])
        with self.fx.with_sdk():
            self.assertEqual(self.generate(second).status_code, 409)
            result = self.generate(first)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(len(self.fx.requests), 1)
        run = next(self.store.folder(self.state['id']).glob(f"generations/*/{first}/runs/{result.json['run_id']}/run.json"))
        record = json.loads(run.read_text())
        self.assertEqual(record['plan_confirmation'], entry)
        self.assertEqual(record['plan_version'], entry['plan_version'])
        self.assertEqual(record['plan_confirmation_source'], 'EXPLICIT_PER_IMAGE')
        package = self.client.post(f"/api/sessions/{self.state['id']}/export-experiment", headers=fixtures.HEADERS)
        self.assertEqual(package.status_code, 200, package.json)
        with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
            saved_run = next(name for name in archive.namelist() if name.endswith(f"{record['run_id']}/run.json"))
            self.assertEqual(json.loads(archive.read(saved_run))['plan_confirmation'], entry)
        revision = self.state['revision']
        self.confirm(first)  # Idempotent confirmation does not move images to another bucket.
        self.assertEqual(self.state['revision'], revision)
        self.assertTrue(self.card(first)['image_url'])

    def test_confirming_another_card_retains_prior_token_and_runs(self):
        first, second = fixtures.web.reference_ids(self.state)[:2]
        original = self.confirm(first)['generation_revision']
        self.confirm(second)
        self.assertEqual(self.card(first)['generation_revision'], original)
        with self.fx.with_sdk():
            stale = self.generate(first, confirmed_revision=self.state['revision'])
            self.assertEqual(stale.status_code, 409)
            result = self.generate(first)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['confirmed_revision'], original)
        self.assertTrue(self.card(second)['plan_status']['confirmed'])

    def test_edit_invalidates_only_target_and_pass_export_is_never_replaced(self):
        first, second = fixtures.web.reference_ids(self.state)[:2]
        self.confirm(first);self.confirm(second)
        with self.fx.with_sdk():
            self.assertEqual(self.generate(first).status_code, 200)
        self.pass_card(first)
        old = self.card(first)
        image = self.client.get(old['image_url']).data
        second_before = self.card(second)
        with self.planner.with_ai():
            self.assertEqual(self.action('plan', first, '保留外观，背景改浅粉').status_code, 200)
        self.assertFalse(self.card(first)['plan_status']['confirmed'])
        self.assertTrue(self.card(second)['plan_status']['confirmed'])
        self.assertEqual(self.card(second), second_before)
        self.assertEqual(self.generate(first).status_code, 409)
        self.confirm(first)
        self.assertTrue(self.card(first)['has_passed_history'])
        self.assertFalse(self.card(first)['batch_eligible'])
        with self.fx.with_sdk():
            self.assertEqual(self.generate(first).status_code, 200)
            self.assertEqual(self.generate(second).status_code, 200)
        new = self.card(first)
        self.assertNotEqual(new['image_url'], old['image_url'])
        self.assertEqual(new['accepted_result']['run_id'], old['passed_run'])
        self.assertEqual(self.client.get(old['image_url']).data, image)
        response = self.client.post(f"/api/sessions/{self.state['id']}/export-passed", headers=fixtures.HEADERS)
        self.assertEqual(response.status_code, 200, response.json)
        with zipfile.ZipFile(io.BytesIO(response.data)) as package:
            self.assertEqual(len(package.namelist()), 1)
            self.assertEqual(package.read(package.namelist()[0]), image)

    def test_understanding_context_and_replan_invalidate_only_affected_confirmations(self):
        targets = fixtures.web.reference_ids(self.state)
        for target in targets:self.confirm(target)
        with self.planner.with_ai():
            self.assertEqual(self.action('reference', targets[0], '仅借鉴排版').status_code, 200)
            self.assertFalse(self.card(targets[0])['plan_status']['confirmed'])
            self.assertTrue(self.card(targets[1])['plan_status']['confirmed'])
            self.assertEqual(self.action('confirm', targets[0]).status_code, 400)
            self.assertEqual(self.action('plan', targets[0], '更新本张计划').status_code, 200)
            self.confirm(targets[0])
            self.assertEqual(self.action('replan').status_code, 200)
            self.assertFalse(any(c['generation_allowed'] for c in self.view()['generation']['cards']))
            for target in targets:self.confirm(target)
            self.assertEqual(self.action('product', feedback='修正商品理解').status_code, 200)
        self.assertFalse(any(c['generation_allowed'] for c in self.view()['generation']['cards']))

    def test_legacy_confirmations_are_read_only_and_materialized_on_explicit_edit(self):
        self.state = self.fx.state
        folder = self.store.folder(self.state['id'])
        before = {p:p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        cards = self.view()['generation']['cards']
        self.assertTrue(all(c['plan_status']['legacy'] and c['generation_allowed'] for c in cards))
        self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
        first, second = fixtures.web.reference_ids(self.state)[:2]
        with self.fx.with_sdk():self.assertEqual(self.generate(second).status_code, 200)
        old = self.card(second)
        with self.planner.with_ai():self.assertEqual(self.action('plan', first, '只修改第一张').status_code, 200)
        self.assertEqual(self.card(second)['image_url'], old['image_url'])
        self.assertEqual(self.card(second)['generation_revision'], old['generation_revision'])
        self.assertTrue(self.card(second)['generation_allowed'])
        self.assertFalse(self.card(first)['generation_allowed'])

    def test_batch_skips_generated_passed_failed_and_old_plan_results(self):
        first, second, third = fixtures.web.reference_ids(self.state)
        for target in [first,second,third]:self.confirm(target)
        with self.fx.with_sdk():self.assertEqual(self.generate(first,batch=True).status_code,200)
        self.pass_card(first)
        with self.fx.with_sdk(lambda request:httpx.Response(429,json={'error':{'message':'offline rejected','type':'rate_limit_error'}})):
            self.assertEqual(self.generate(second,batch=True).status_code,502)
        self.assertFalse(self.card(first)['batch_eligible'])
        self.assertFalse(self.card(second)['batch_eligible'])
        self.assertTrue(self.card(third)['batch_eligible'])
        before=len(self.fx.requests)
        with self.fx.with_sdk():
            self.assertEqual(self.generate(first,batch=True).status_code,409)
            self.assertEqual(self.generate(second,batch=True).status_code,409)
            self.assertEqual(self.generate(third,batch=True).status_code,200)
        self.assertEqual(len(self.fx.requests),before+1)
        self.assertTrue(self.card(first)['passed_run'])
        with self.planner.with_ai():self.assertEqual(self.action('plan',first,'新计划仍保留旧 Pass').status_code,200)
        self.confirm(first)
        self.assertFalse(self.card(first)['batch_eligible'])

    def test_operation_query_resolves_success_and_definite_failure_without_retry(self):
        first,second = fixtures.web.reference_ids(self.state)[:2]
        self.confirm(first);self.confirm(second)
        operation=uuid4().hex
        with self.fx.with_sdk():self.assertEqual(self.generate(first,operation_id=operation).status_code,200)
        before=len(self.fx.requests)
        found=self.operation(first,operation).json
        self.assertEqual(found['status'],'SUCCEEDED');self.assertFalse(found['uncertain'])
        self.assertEqual(self.operation(first,uuid4().hex).json['status'],'NOT_FOUND')
        self.assertTrue(self.operation(first,uuid4().hex).json['uncertain'])
        failed=uuid4().hex
        with self.fx.with_sdk(lambda request:httpx.Response(429,json={'error':{'message':'offline rejected','type':'rate_limit_error'}})):
            self.assertEqual(self.generate(second,operation_id=failed).status_code,502)
        self.assertFalse(self.operation(second,failed).json['uncertain'])
        self.assertEqual(self.operation(second,operation).json['status'],'NOT_FOUND')
        self.assertEqual(self.operation('product_999',operation,revision=self.state['revision']).status_code,404)
        self.assertEqual(len(self.fx.requests),before+1)

    def test_connection_failure_is_paused_and_blocks_new_paid_attempts(self):
        first,second=fixtures.web.reference_ids(self.state)[:2]
        self.confirm(first);self.confirm(second)
        operation=uuid4().hex
        def disconnected(request):raise httpx.ConnectError('offline connection lost',request=request)
        with self.fx.with_sdk(disconnected):self.assertEqual(self.generate(first,operation_id=operation).status_code,502)
        outcome=self.operation(first,operation).json
        self.assertTrue(outcome['uncertain']);self.assertEqual(outcome['status'],'FAILED')
        self.assertTrue(self.card(first)['request_uncertain'])
        before=len(self.fx.requests)
        with self.fx.with_sdk():
            self.assertEqual(self.generate(first).status_code,409)
            self.assertEqual(self.generate(first,batch=True).status_code,409)
            self.assertEqual(self.generate(second,batch=True).status_code,200)
        self.assertEqual(len(self.fx.requests),before+1)

    def test_quick_batch_needs_no_plan_confirmation_and_keeps_other_tasks_unchanged(self):
        original = {p: p.read_bytes() for p in self.store.folder(self.state['id']).rglob('*') if p.is_file()}
        response = self.client.post('/api/sessions', headers=fixtures.HEADERS, data={
            'title': '离线快速批量测试', 'mode': 'quick_redesign', 'requirements': '保留商品，改善排版',
            'product': [(io.BytesIO(fixtures.png()), f'原图{i}.png') for i in range(2)]})
        self.assertEqual(response.status_code, 200, response.json)
        quick = response.json['state']
        self.assertFalse(quick['confirmed'])
        self.assertEqual(quick['plans'], {})
        self.assertTrue(all(c['batch_eligible'] for c in self.view(quick)['generation']['cards']))
        with self.fx.with_sdk():
            for target in ['product_001', 'product_002']:
                operation = uuid4().hex
                self.assertEqual(self.generate(target, state=quick, batch=True, operation_id=operation).status_code, 200)
                self.assertEqual(self.operation(target, operation, state=quick).json['status'], 'SUCCEEDED')
        restored = fixtures.web.create_app(self.fx.runtime).test_client()
        cards = restored.get(f"/api/sessions/{quick['id']}/workspace").json['generation']['cards']
        self.assertTrue(all(c['image_url'] and not c['batch_eligible'] for c in cards))
        for path, data in original.items():self.assertEqual(path.read_bytes(), data)

    def test_restart_reads_unfinished_run_without_resubmission(self):
        target=fixtures.web.reference_ids(self.state)[0];card=self.confirm(target);operation=uuid4().hex
        run='20261016T000000Z-'+uuid4().hex;service=self.fx.app.extensions['generation_service']
        folder=service.run_folder(self.state['id'],card['generation_revision'],target,run);folder.mkdir(parents=True)
        record={'run_id':run,'session_id':self.state['id'],'reference_id':target,'confirmed_revision':card['generation_revision'],
                'operation_id':operation,'status':'RUNNING','api_call_attempted':True,'started_at':'2026-10-16T00:00:00Z'}
        fixtures.web.write_json(folder/'run.json',record);fixtures.web.write_json(folder.parent.parent/'current.json',{'latest_run':run})
        before=(folder/'run.json').read_bytes()
        client=fixtures.web.create_app(self.fx.runtime).test_client()
        view=client.get(f"/api/sessions/{self.state['id']}/workspace").json
        self.assertEqual(view['generation']['cards'][0]['status'],'INTERRUPTED')
        self.assertFalse(view['generation']['cards'][0]['batch_eligible'])
        self.assertEqual(self.operation(target,operation).json['status'],'INTERRUPTED')
        self.assertEqual(self.generate(target,client=client).status_code,409)
        self.assertEqual((folder/'run.json').read_bytes(),before)
        self.assertEqual(self.fx.requests,[])

    def test_plan_changes_rejected_while_image_request_runs(self):
        target=fixtures.web.reference_ids(self.state)[0];self.confirm(target)
        entered,finish=threading.Event(),threading.Event();results=[]
        def slow(request):
            entered.set();finish.wait(5)
            return httpx.Response(400,json={'error':{'message':'offline failure','type':'invalid_request_error'}})
        with self.fx.with_sdk(slow):
            worker=threading.Thread(target=lambda:results.append(self.generate(target,client=self.fx.app.test_client())))
            worker.start();self.assertTrue(entered.wait(3))
            try:self.assertEqual(self.action('plan',target,'不可并行覆盖计划').status_code,409)
            finally:finish.set();worker.join(5)
        self.assertEqual(results[0].status_code,502)
        self.assertEqual(self.planner.requests,[])

    def test_javascript_sequential_batch_driver(self):
        result=subprocess.run(['node','--test',str(Path(__file__).with_name('batch_generate.test.cjs'))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
