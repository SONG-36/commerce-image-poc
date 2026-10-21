"""Planning package regressions using anonymous temporary data and fake clients."""

import hashlib
import json
import os
from pathlib import Path
import ast
import base64
import copy
from contextlib import contextmanager
from dataclasses import replace
import importlib.util
import itertools
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from file_ops import read_json, sha256, write_json_atomic, write_json_exclusive
from image_workflow.planning import request as construction, validation
from image_workflow.planning import service


def compatibility_fingerprints(*, details=False):
    """Legacy entry-point failures, captured before migration on 663dcc3."""
    import httpx
    import test_prepare_plan as fixtures

    cases = {}
    for scenario in ('success', 'unknown_model', 'changed_image', 'missing_key',
                     'incomplete', 'bad_json', 'wrong_ids', 'rate_limit', 'interrupt'):
        fx = fixtures.PreparePlanTests()
        fx.setUp()
        try:
            web = fixtures.web
            state = fx.load_case()
            folder = fx.runtime / 'sessions' / state['id']
            if scenario == 'changed_image':
                (folder / state['images'][0]['file']).write_bytes(b'changed anonymous bytes')
            environment = {'OPENAI_PLANNING_MODEL': 'not-supported'} if scenario == 'unknown_model' else {}
            if scenario == 'missing_key':
                environment['OPENAI_API_KEY'] = ''
            writes = []
            original = web.write_json

            def write(path, value, exclusive=False):
                metadata = value if isinstance(value, dict) else {}
                writes.append([path.name, metadata.get('status'), metadata.get('api_call_attempted'), exclusive])
                return original(path, value, exclusive=exclusive)

            def respond(body, result):
                if scenario == 'interrupt':
                    raise KeyboardInterrupt()
                if scenario == 'rate_limit':
                    return httpx.Response(429, json={'error': {'message': 'offline limit', 'type': 'rate_limit_error'}})
                if scenario == 'wrong_ids':
                    result['references'] = {'reference_999': next(iter(result['references'].values()))}
                return httpx.Response(200, json={'id': 'resp_package_mock',
                    'status': 'in_progress' if scenario == 'incomplete' else 'completed', 'model': body['model'],
                    'output': [{'type': 'message', 'id': 'msg_package_mock', 'role': 'assistant',
                                'content': [{'type': 'output_text', 'text': '{broken' if scenario == 'bad_json'
                                             else json.dumps(result), 'annotations': []}]}],
                    'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}},
                    headers={'x-request-id': 'req_package_mock'})

            outcome = None
            with patch.dict(os.environ, environment), fx.with_ai(respond), patch.object(web, 'write_json', side_effect=write):
                try:
                    result, _ = web.call_ai(fx.app.extensions['plan_store'], state, 'understand', None, '')
                    outcome = {'result': result}
                except BaseException as error:
                    outcome = {'type': type(error).__name__, 'message': str(error),
                               'status': getattr(error, 'status', None),
                               'cause': type(error.__cause__).__name__ if error.__cause__ else None}
            if scenario == 'success':
                assert 'result' in outcome, outcome
            else:
                assert outcome['type'] == ('KeyboardInterrupt' if scenario == 'interrupt' else 'Problem'), outcome
            assert len(fx.requests) == (0 if scenario in ('unknown_model', 'changed_image', 'missing_key') else 1)
            call = next((folder / 'calls').iterdir())
            files = {}
            for path in sorted(call.iterdir()):
                if path.name == 'run.json':
                    record = web.read_json(path)
                    for key in ('id', 'run_id', 'session_id', 'started_at', 'finished_at', 'elapsed_seconds',
                                'api_started_at', 'api_elapsed_seconds', 'source_sha256'):
                        record.pop(key, None)
                    files[path.name] = record
                else:
                    files[path.name] = path.read_text()
            assert not fx.app.extensions['plan_store'].planning
            payload = json.dumps({'outcome': outcome, 'files': files, 'writes': writes},
                                 ensure_ascii=False, sort_keys=True)
            # This direct compatibility call uses a public state containing image
            # URLs. Normalize only its random Task ID; keep Image IDs/order/bytes.
            payload = payload.replace(state['id'], '<TASK>')
            cases[scenario] = json.loads(payload) if details else hashlib.sha256(payload.encode()).hexdigest()
        finally:
            fx.tearDown()
            fx.doCleanups()
    return cases


class PlanningPackageTests(unittest.TestCase):
    MODELS = ('gpt-5.4-mini', 'gpt-4.1-mini', 'gpt-4.1-mini-2025-04-14')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'task'
        (self.folder / 'inputs').mkdir(parents=True)
        self.source = self.root / 'legacy_entry.py'
        self.source.write_bytes(b'# anonymous entry source\n')
        self.ids = ['reference_001', 'reference_002']
        self.state = {'id': 'a' * 32, 'revision': 1,
                      'inputs': {'listing': 'L', 'description': 'D', 'requirements': 'R'},
                      'images': [], 'product': None, 'references': {}, 'plans': {},
                      'corrections': {'product': [], 'references': {}}}
        self.image_bytes = {}
        for identity in ['product_001', *self.ids]:
            relative = f'inputs/{identity}.png'
            raw = ('anonymous bytes for ' + identity).encode()
            (self.folder / relative).write_bytes(raw)
            self.image_bytes[relative] = raw
            self.state['images'].append({'id': identity, 'role': identity.split('_')[0], 'name': 'same.png',
                                         'file': relative, 'mime': 'image/png', 'sha256': sha256(raw)})
        (self.folder / 'versions').mkdir()
        for path in [self.folder / 'state.json', self.folder / 'versions/000001.json']:
            write_json_exclusive(path, self.state)
        self.original = {p: p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        self.writes, self.requests, self.clients = [], [], []
        self.activity = {}
        self.result = validation.response_shape('understand', self.ids)
        self.response_status, self.output_override = 'completed', None
        self.environment = {'OPENAI_API_KEY': 'offline-test-only'}
        self.io = service.PlanningIO(client_factory=self.client_factory, write_json=self.write,
                                     safe_text=lambda text: text, now=lambda: 'fixed time', new_id=uuid4,
                                     sdk_version=lambda name: 'offline-sdk', source_file=self.source,
                                     clock=itertools.count(0, .25).__next__)

    def write(self, path, value, exclusive=False):
        metadata = value if isinstance(value, dict) else {}
        self.writes.append((path.name, metadata.get('status'), exclusive))
        writer = write_json_exclusive if exclusive else write_json_atomic
        writer(path, value)

    @contextmanager
    def client_factory(self, **options):
        self.clients.append(options)
        yield SimpleNamespace(responses=SimpleNamespace(create=self.respond))

    def respond(self, **arguments):
        self.assertEqual(self.activity[self.state['id']]['status'], 'RUNNING')
        self.assertTrue(self.activity[self.state['id']]['api_call_attempted'])
        self.requests.append(arguments)
        text = self.output_override if self.output_override is not None else json.dumps(self.result)
        raw = {'id': 'resp_offline', 'model': arguments['model'], 'status': self.response_status,
               'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}],
               'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}}
        return SimpleNamespace(_request_id='req_offline', status=self.response_status, output_text=text,
                               model_dump=lambda mode: copy.deepcopy(raw))

    def execute(self, action='understand', target=None, **overrides):
        options = {'case_id_for': lambda state: 'case-anonymous', 'activity': self.activity,
                   'models': self.MODELS, 'environment': self.environment, 'io': self.io, **overrides}
        return service.execute_planning(self.folder, self.state, action, target, 'feedback', **options)

    def latest_record(self):
        path = sorted(self.folder.glob('calls/*/run.json'), key=lambda path: path.stat().st_mtime_ns)[-1]
        return read_json(path), path.parent

    def test_builder_is_pure_with_explicit_configuration_for_all_actions_models(self):
        before = copy.deepcopy((self.state, self.image_bytes))
        with patch('builtins.open', side_effect=AssertionError('Pure builder must not open files')), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('No image reads')), \
                patch.object(os, 'environ', {}):
            for model in self.MODELS:
                for action in ('understand', 'product', 'reference', 'plan', 'replan'):
                    target = self.ids[1] if action in ('reference', 'plan') else None
                    arguments, order = construction.build_planning_request(
                        self.state, action, target, 'feedback', model, self.image_bytes, reasoning_model=self.MODELS[0])
                    selected = construction.planning_images(self.state, action, target)
                    self.assertEqual([image['id'] for image in order], [image['id'] for image in selected])
                    parts = arguments['input'][0]['content']
                    image_parts = [part for part in parts if part['type'] == 'input_image']
                    self.assertEqual(len(image_parts), len(selected))
                    for image, part in zip(selected, image_parts):
                        self.assertEqual(base64.b64decode(part['image_url'].split(',', 1)[1]), self.image_bytes[image['file']])
                        self.assertEqual(part['detail'], 'auto')
                    self.assertEqual(arguments['instructions'], construction.RULES)
                    self.assertEqual(arguments.get('reasoning'), {'effort': 'low'} if model == self.MODELS[0] else None)
                    self.assertEqual(arguments['max_output_tokens'], 6000 if action in ('understand', 'replan') else 2500)
        self.assertEqual((self.state, self.image_bytes), before)

    def test_result_validation_preserves_ids_and_checks_structure_only(self):
        candidate = validation.response_shape('understand', list(reversed(self.ids)))
        clean = validation.validate_result(candidate, 'understand', self.ids)
        self.assertEqual(list(clean['references']), self.ids)
        self.assertEqual(list(clean['plans']), self.ids)
        for group in ('references', 'plans'):
            for replacement in ({}, {'reference_999': candidate[group][self.ids[0]]}):
                bad = copy.deepcopy(candidate)
                bad[group] = replacement
                with self.assertRaises(validation.Problem) as caught:
                    validation.validate_result(bad, 'understand', self.ids)
                self.assertEqual(caught.exception.status, 502)
        for bad in (None, [], {'product': {}}, {'product': {key: ' ' for key in validation.PRODUCT_FIELDS}}):
            with self.assertRaises(validation.Problem):
                validation.validate_result(bad, 'product', self.ids)

    def test_execution_default_builder_does_not_apply_task_state(self):
        before = copy.deepcopy(self.state)
        result, call_id = self.execute()
        record, evidence = self.latest_record()
        self.assertEqual(result, self.result)
        self.assertEqual(record['id'], call_id)
        self.assertEqual(record['status'], 'AI_RESULT_RECEIVED')
        self.assertEqual(record['usage'], {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30})
        self.assertEqual(record['source_sha256'], sha256(self.source.read_bytes()))
        self.assertNotEqual(record['source_sha256'], sha256(Path(service.__file__).read_bytes()))
        self.assertEqual(record['parent_version_file'], 'versions/000001.json')
        self.assertEqual(self.clients, [{'api_key': 'offline-test-only', 'base_url': 'https://api.openai.com/v1',
                                         'max_retries': 0, 'timeout': 120.0}])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(read_json(evidence / 'request.json'), self.requests[0])
        self.assertEqual([name for name, _, _ in self.writes],
                         ['run.json', 'request.json', 'image_order.json', 'run.json', 'response.json', 'result.json', 'run.json'])
        for path, raw in self.original.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(self.state, before)
        self.assertEqual(self.activity, {})
        self.assertFalse((evidence / 'applied.json').exists())
        for path in evidence.iterdir():
            self.assertNotIn('offline-test-only', path.read_text())

    def test_targeted_execution_loads_and_sends_only_its_product_and_reference(self):
        self.result = validation.response_shape('plan', self.ids)
        self.execute('plan', self.ids[1])
        record, _ = self.latest_record()
        self.assertEqual([item['id'] for item in record['inputs']], ['product_001', self.ids[1]])
        context = json.loads(self.requests[0]['input'][0]['content'][0]['text'])
        self.assertEqual(context['target'], self.ids[1])
        self.assertNotIn(self.ids[0], context['current']['corrections']['references'])

    def test_invalid_model_or_changed_image_stops_before_build_and_client(self):
        for scenario in ('unknown_model', 'changed_image'):
            environment = {**self.environment, 'OPENAI_PLANNING_MODEL': 'not-supported'} if scenario == 'unknown_model' else self.environment
            if scenario == 'changed_image':
                (self.folder / self.state['images'][0]['file']).write_bytes(b'changed')
            with patch.object(service, 'build_planning_request', side_effect=AssertionError('Must not build')), \
                    self.assertRaises(validation.Problem) as caught:
                self.execute(environment=environment)
            self.assertEqual(caught.exception.status, 400)
            record, evidence = self.latest_record()
            self.assertFalse(record['api_call_attempted'])
            self.assertEqual(record['error']['type'], 'Problem')
            self.assertFalse((evidence / 'request.json').exists())
        self.assertEqual(self.clients, [])
        self.assertEqual(self.activity, {})

    def test_missing_key_saves_request_and_fails_without_sdk_attempt(self):
        with self.assertRaises(validation.Problem) as caught:
            self.execute(environment={})
        self.assertEqual(caught.exception.status, 503)
        record, evidence = self.latest_record()
        self.assertEqual(record['status'], 'FAILED')
        self.assertFalse(record['api_call_attempted'])
        self.assertTrue((evidence / 'request.json').is_file())
        self.assertTrue((evidence / 'image_order.json').is_file())
        self.assertIn('product_001', (evidence / 'prompt.txt').read_text())
        self.assertEqual(self.clients, [])

    def test_client_construction_and_request_errors_keep_original_attempt_flags(self):
        for stage in ('construction', 'request'):
            error = RuntimeError('offline ' + stage + ' failure')
            if stage == 'construction':
                io = replace(self.io, client_factory=unittest.mock.Mock(side_effect=error))
                context = patch.object(self, 'respond', wraps=self.respond)
            else:
                io = self.io
                context = patch.object(self, 'respond', side_effect=error)
            with context, self.assertRaises(validation.Problem) as caught:
                self.execute(io=io)
            self.assertIs(caught.exception.__cause__, error)
            self.assertEqual(caught.exception.status, 502)
            record, evidence = self.latest_record()
            self.assertEqual(record['api_call_attempted'], stage == 'request')
            self.assertEqual(record['error']['type'], 'RuntimeError')
            self.assertEqual('api_elapsed_seconds' in record, stage == 'request')
            self.assertFalse((evidence / 'response.json').exists())
            self.assertEqual(self.activity, {})
            if stage == 'construction':
                self.assertEqual(io.client_factory.call_count, 1)
        self.assertEqual(len(self.clients), 1)

    def test_incomplete_malformed_or_wrong_id_responses_are_preserved_before_failure(self):
        for scenario in ('incomplete', 'bad_json', 'wrong_ids'):
            self.response_status = 'in_progress' if scenario == 'incomplete' else 'completed'
            self.output_override = '{broken' if scenario == 'bad_json' else None
            self.result = validation.response_shape('understand', ['reference_999'] if scenario == 'wrong_ids' else self.ids)
            start = len(self.writes)
            with self.assertRaises(validation.Problem) as caught:
                self.execute()
            self.assertEqual(caught.exception.status, 502)
            record, evidence = self.latest_record()
            self.assertEqual(record['request_id'], 'req_offline')
            self.assertTrue((evidence / 'response.json').is_file())
            self.assertFalse((evidence / 'result.json').exists())
            names = [name for name, _, _ in self.writes[start:]]
            self.assertLess(names.index('response.json'), names.index('error.json'))
            self.assertEqual(record['status'], 'FAILED')

    def test_keyboard_interrupt_only_finalizes_original_running_record(self):
        with patch.object(self, 'respond', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.execute()
        record, evidence = self.latest_record()
        self.assertEqual(record['status'], 'RUNNING')
        self.assertTrue(record['api_call_attempted'])
        self.assertIn('api_elapsed_seconds', record)
        self.assertIn('finished_at', record)
        self.assertFalse((evidence / 'error.json').exists())
        self.assertEqual(self.activity, {})

    def test_legacy_exports_mock_seams_and_deploy_model_literal_are_compatible(self):
        import prepare_plan as web
        self.assertIs(web.Problem, validation.Problem)
        self.assertIs(web.validate_result, validation.validate_result)
        self.assertIs(web.planning_images, construction.planning_images)
        self.assertEqual(web.MODELS, self.MODELS)
        tree = ast.parse(Path(web.__file__).read_text())
        models = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'MODELS' for target in node.targets))
        self.assertEqual(models, web.MODELS)
        store = SimpleNamespace(folder=lambda identity: self.folder, case_id=lambda state: 'case-test', planning={})
        with patch.object(web, 'OpenAI') as sdk, patch.object(web, 'write_json') as writer, \
                patch.object(web, 'execute_planning', return_value=('result', 'call')) as execute:
            self.assertEqual(web.call_ai(store, self.state, 'understand', None, ''), ('result', 'call'))
        options = execute.call_args.kwargs
        self.assertIs(options['io'].client_factory, sdk)
        self.assertIs(options['io'].write_json, writer)
        self.assertEqual(options['io'].source_file, Path(web.__file__))
        self.assertIs(options['request_builder'], web.build_planning_request)
        self.assertIs(options['validator'], web.validate_result)

    def test_import_and_execute_in_fresh_process_without_http_sdk_or_other_workflows(self):
        script = '''
import importlib.abc, sys
from unittest.mock import patch
sys.path[:0] = ['src', 'tests']
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'prepare_plan','flask','openai','generate_image','generate_plan_image','image_review','quick_redesign'}:
            raise AssertionError('Forbidden planning dependency: ' + fullname)
sys.meta_path.insert(0, Block())
from test_planning_package import PlanningPackageTests
fixture = PlanningPackageTests('test_execution_default_builder_does_not_apply_task_state')
fixture.setUp()
try:
    with patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')):
        fixture.test_execution_default_builder_does_not_apply_task_state()
finally:
    fixture.doCleanups()
print('Independent planning execution PASS')
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Independent planning execution PASS', result.stdout)

    def test_project_import_graph_resolves_relative_imports_without_cycles(self):
        source = Path(__file__).resolve().parents[1] / 'src'
        graph = {}
        for path in source.rglob('*.py'):
            is_package = path.name == '__init__.py'
            module = '.'.join(path.relative_to(source).with_suffix('').parts)
            if is_package:
                module = module.removesuffix('.__init__')
            package = module if is_package else module.rpartition('.')[0]
            graph[module] = set()
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    graph[module].update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    target = importlib.util.resolve_name('.' * node.level + (node.module or ''), package) if node.level else node.module
                    graph[module].add(target)
                    graph[module].update(f'{target}.{alias.name}' for alias in node.names)
        forbidden = {'prepare_plan', 'flask', 'openai', 'generate_plan_image', 'image_review', 'quick_redesign', 'generate_image'}
        for module, dependencies in graph.items():
            if module.startswith('image_workflow'):
                self.assertFalse(dependencies & forbidden, (module, dependencies))

        def visit(module, ancestors):
            self.assertNotIn(module, ancestors, f'import cycle: {ancestors} -> {module}')
            for target in graph[module] & graph.keys():
                visit(target, [*ancestors, module])

        for module in graph:
            visit(module, [])

    def test_legacy_success_failure_evidence_and_write_order_match_original(self):
        self.assertEqual(compatibility_fingerprints(), FAILURE_GOLDEN)


# Original 663dcc3, compiled before/after migration for an exact comparison.
# Dynamic Task/Call IDs, timestamps/durations and entry-source hashes are checked
# separately; sent text, inputs, response/error content and write order stay exact.
FAILURE_GOLDEN = {
    "bad_json": "61e70b7fe7251d40b8fde0a2a6a6689272c68d4c39c435c24f7dfc582ca1522e",
    "changed_image": "b872ad23989b57ee4b72ed603ec2505526b4cb56e48994010614bf500da7ae3c",
    "incomplete": "9e85f47cffd449e9c06e6422712bcafaed1e7091ab71e0477166f66a0af31b1e",
    "interrupt": "11597f1f9ee476bff0c9a39d05e44687363ae77732605a353d29793989a076ed",
    "missing_key": "d716c813d040d6d81cf8c67060d5cd442be105bf4d9de8c7a7538cec8fefd804",
    "rate_limit": "fa224c73b9da2b919f35e50bf600739dfad9fcc5dd4028d5b42d4060792bbad9",
    "success": "bff0502c0a09c2b0c2b5f7fea0f51977be0cd9c6b51468fedda440fb4f4d3c45",
    "unknown_model": "1f37b738c3e17c20870a54fd48bd0cc671c5db5f4c84c31814cd3e07c2fc01ba",
    "wrong_ids": "010cd54a8128ae9e1af4a2a3de98e11b3689f2e3977d0a1e314092bef75d9e05"
}

if __name__ == '__main__':
    unittest.main()
