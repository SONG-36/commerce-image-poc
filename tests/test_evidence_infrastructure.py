"""C1: anonymous sanitization contracts, legacy seams and SDK-free imports.

The 371-case fingerprint was captured from 5db7db1 before C1 edits. It contains
only synthetic values; no Git history, private runtime or API access is needed.
"""

import ast
import copy
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import evidence as legacy
from infrastructure import evidence as core


def behavior_fingerprint(module):
    """Anonymous pre-migration behavior, including native errors and input stability."""
    import copy
    import hashlib
    import json
    from unittest.mock import patch
    texts = [
        '', 'plain 商品', 'sk-short', 'sk-' + 'a' * 10, 'SK-' + 'a' * 10,
        'Bearer abc.def~', 'bearer short', 'ghp_' + 'a' * 20,
        'github_pat_' + 'a' * 20, 'before opaque-environment-secret after',
        '{"api_key":"opaque","name":"商品"}', '{"safe":" 商品 ","n":1}',
        '[{"type":"reasoning","summary":"hidden"},{"text":"visible"}]',
        '{"nested":"{\\"password\\":\\"opaque\\"}"}', '{"broken":',
    ]
    values = [
        None, False, True, 0, 7, 0.5, b'opaque', ('password', 'opaque'),
        [], {}, {'password': None}, {'password': ''}, {'password': []},
        {'password': {}}, {'password': 0}, {'password': False},
        {'type': 'reasoning', 'summary': 'hidden'},
        {'type': 'message', 'text': 'visible', 'usage': {'reasoning_tokens': 8}},
        {'headers': {'Proxy-Authorization': 'opaque', 'X-Api-Key': 'opaque', 'safe': 'keep'}},
        [{'type': 'reasoning'}, {'type': 'message', 'text': 'visible'}, None],
        {'nested': [{'credentials': 'opaque', 'name': '商品'}], 'token': 'opaque'},
        {1: 'non-string key'}, [b'bytes', ('pair', 1)],
        *texts,
    ]
    def normal(value):
        if isinstance(value, bytes):
            return {'bytes_hex': value.hex()}
        if isinstance(value, tuple):
            return {'tuple': [normal(item) for item in value]}
        if isinstance(value, dict):
            return {'dict': [[normal(key), normal(item)] for key, item in value.items()]}
        if isinstance(value, list):
            return [normal(item) for item in value]
        return value
    outcomes = []
    def call(name, *args):
        before = normal(copy.deepcopy(args))
        try:
            outcome = {'returned': normal(getattr(module, name)(*args))}
        except Exception as error:
            outcome = {'error_type': type(error).__name__, 'message': str(error)}
        assert normal(args) == before, name
        outcomes.append([name, before, outcome])
    for environment in ('', 'opaque-environment-secret', 'sk-' + 'b' * 12):
        with patch.dict('os.environ', {'OPENAI_API_KEY': environment}):
            for text in [*texts, None, 1, b'bytes', [], {}]:
                call('safe_text', text)
            for value in values:
                call('clean_record', value)
                call('contains_private', value)
    for name in ['Authorization', 'proxy-authorization', 'X-API-KEY', 'OPENAI_API_KEY',
                 'reasoning_tokens', 'TYPE', ' api_key ', '', None, 1, b'password']:
        call('private_field', name)
    for text in [*texts, None, 1, b'bytes']:
        for key in ('', None, 'opaque-environment-secret', b'bytes'):
            call('redact', text, key)
    encoded = json.dumps(outcomes, ensure_ascii=False, sort_keys=True).encode()
    return {'sha256': hashlib.sha256(encoded).hexdigest(), 'cases': len(outcomes)}


class EvidenceInfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"OPENAI_API_KEY": ""}))

    def test_explicit_redactor_keeps_its_narrow_rules_and_key_order(self):
        key = "opaque-explicit-key"
        self.assertEqual(core.redact("before " + key + " after", key), "before [REDACTED] after")
        self.assertEqual(core.redact("sk-" + "a" * 10, ""), "[REDACTED]")
        # T01's redactor does not acquire the broader Evidence token patterns.
        for value in ("SK-" + "a" * 10, "Bearer abc.def", "ghp_" + "a" * 20):
            self.assertEqual(core.redact(value, ""), value)
        self.assertEqual(core.redact("sk-short", None), "sk-short")

    def test_token_patterns_and_sensitive_field_normalization_are_unchanged(self):
        for value in ("SK-" + "a" * 10, "Bearer abc.def~", "ghp_" + "a" * 20,
                      "github_pat_" + "a" * 20):
            with self.subTest(value_type=value.split("_")[0][:6]):
                self.assertEqual(core.safe_text(value), "[REDACTED]")
                self.assertTrue(core.contains_private(value))
        for field in ("Authorization", "Proxy-Authorization", "OPENAI_API_KEY", "X-Api-Key",
                      "chain_of_thought", "encrypted_content"):
            self.assertTrue(core.private_field(field), field)
        for field in ("reasoning_tokens", " api_key ", "safe", ""):
            self.assertFalse(core.private_field(field), field)

    def test_nested_cleaning_removes_hidden_reasoning_and_retains_actual_usage(self):
        value = {"headers": {"Authorization": "opaque", "safe": "商品"},
                 "output": [{"type": "reasoning", "summary": ["hidden"]},
                            {"type": "message", "text": "visible"}],
                 "usage": {"reasoning_tokens": 7}, "nested": {"password": "opaque"}}
        original = copy.deepcopy(value)
        expected = {"headers": {"safe": "商品"}, "output": [{"type": "message", "text": "visible"}],
                    "usage": {"reasoning_tokens": 7}, "nested": {}}
        for module in (core, legacy):
            self.assertEqual(module.clean_record(value), expected)
            self.assertTrue(module.contains_private(value))
            self.assertEqual(module.clean_record({"type": "reasoning"}), {"omitted": "hidden reasoning"})
        self.assertEqual(value, original)

    def test_encoded_json_only_reserializes_when_private_content_is_present(self):
        untouched = '  { "label" : "商品", "n" : 1 }'
        secret = '  {"api_key":"opaque","label":"商品"}'
        broken = '{"broken":'
        for module in (core, legacy):
            self.assertEqual(module.clean_record(untouched), untouched)
            self.assertEqual(module.clean_record(secret), '{"label": "商品"}')
            self.assertEqual(module.clean_record(broken), broken)
            self.assertEqual(module.clean_record('[{"type":"reasoning"},{"text":"visible"}]'),
                             '[{"text": "visible"}]')

    def test_environment_key_is_looked_up_at_call_time_without_becoming_state(self):
        for module in (core, legacy):
            for key in ("first-opaque-canary", "second-opaque-canary"):
                with patch.dict(os.environ, {"OPENAI_API_KEY": key}):
                    self.assertEqual(module.safe_text("before " + key), "before [REDACTED]")
                    self.assertTrue(module.contains_private(key))
                    self.assertEqual(module.clean_record({"text": key}), {"text": "[REDACTED]"})
            self.assertEqual(module.safe_text("first-opaque-canary"), "first-opaque-canary")
            self.assertFalse(module.contains_private("first-opaque-canary"))

    def test_empty_values_unsupported_values_and_native_exceptions_are_retained(self):
        for module in (core, legacy):
            for item in (None, "", [], {}):
                self.assertFalse(module.contains_private({"password": item}))
                self.assertEqual(module.clean_record({"password": item}), {})
            for item in (0, False):
                self.assertTrue(module.contains_private({"password": item}))
            pair = ("password", "opaque")
            self.assertIs(module.clean_record(pair), pair)
            self.assertFalse(module.contains_private(pair))
            self.assertIsNone(module.clean_record(None))
            with self.assertRaises(TypeError):
                module.safe_text(None)
            with self.assertRaises(AttributeError):
                module.private_field(None)
            with self.assertRaises(AttributeError):
                module.clean_record({1: "non-string key"})

    def test_pre_migration_returns_errors_and_input_stability_match_for_both_entries(self):
        expected = {"sha256": "7fbf1c386a4d5fe85e9a7feec6adcf9272a268bbb9af91855e7d3a4865169bfc",
                    "cases": 371}
        self.assertEqual(behavior_fingerprint(core), expected)
        self.assertEqual(behavior_fingerprint(legacy), expected)

    def test_legacy_public_signatures_and_shared_constant_objects_remain(self):
        self.assertIs(legacy.PRIVATE_FIELDS, core.PRIVATE_FIELDS)
        self.assertIs(legacy.TOKEN_PATTERN, core.TOKEN_PATTERN)
        for name in ("safe_text", "private_field", "clean_record", "contains_private", "redact"):
            self.assertEqual(inspect.signature(getattr(legacy, name)), inspect.signature(getattr(core, name)))
        self.assertEqual(str(inspect.signature(legacy.redact)), "(text, key)")

    def test_legacy_redact_patch_reaches_recursion_imported_web_helpers_and_http_errors(self):
        import generate_plan_image
        import prepare_plan
        from image_workflow import Problem
        calls = []
        def replacement(text, key):
            calls.append((text, key))
            return text.replace("opaque-error", "[REDACTED]")
        with patch.object(legacy, "redact", side_effect=replacement):
            self.assertEqual(legacy.clean_record({"nested": ["opaque-error"]}),
                             {"nested": ["[REDACTED]"]})
            self.assertEqual(prepare_plan.safe_text("opaque-error"), "[REDACTED]")
            self.assertEqual(generate_plan_image.safe_text("opaque-error"), "[REDACTED]")
            with tempfile.TemporaryDirectory() as directory:
                app = prepare_plan.create_app(Path(directory) / "state", Path(directory) / "case")
                @app.get("/offline-error")
                def fail():
                    raise Problem("opaque-error", 502)
                self.assertEqual(app.test_client().get("/offline-error").json, {"error": "[REDACTED]"})
        self.assertTrue(calls)
        self.assertTrue(all(key == "" for _, key in calls))

    def test_t01_redact_patch_reaches_t01_and_quick_writers_without_changing_evidence_binding(self):
        import generate_image
        import quick_redesign
        original_evidence_redact = legacy.redact
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(generate_image, "redact", side_effect=lambda text, key: text.replace("opaque", "patched")) as redact:
            first, second = Path(directory) / "t01.json", Path(directory) / "quick.json"
            generate_image.write_json(first, {"label": "opaque"}, "")
            quick_redesign.save_json(second, {"label": "opaque"})
            self.assertEqual(json.loads(first.read_text()), {"label": "patched"})
            self.assertEqual(json.loads(second.read_text()), {"label": "patched"})
            self.assertEqual(redact.call_count, 2)
            # The old import captured a binding: patching generate_image later
            # did not replace evidence.redact.
            self.assertIs(legacy.redact, original_evidence_redact)
            self.assertEqual(legacy.safe_text("opaque"), "opaque")

    def test_legacy_recursive_and_predicate_monkeypatch_bindings_are_preserved(self):
        with patch.object(legacy, "safe_text", return_value="filtered") as text:
            self.assertEqual(legacy.clean_record({"nested": ["first", "second"]}),
                             {"nested": ["filtered", "filtered"]})
            self.assertEqual(text.call_count, 2)
        with patch.object(legacy, "private_field", side_effect=lambda name: name == "drop"):
            self.assertEqual(legacy.clean_record({"drop": "x", "keep": "y"}), {"keep": "y"})
            self.assertTrue(legacy.contains_private({"drop": "x"}))
        with patch.object(legacy, "contains_private", return_value=True) as check:
            self.assertEqual(legacy.clean_record('{ "visible" : "text" }'), '{"visible": "text"}')
            check.assert_called()
        original = legacy.clean_record
        with patch.object(legacy, "clean_record", wraps=original) as clean:
            self.assertEqual(clean({"nested": ["value"]}), {"nested": ["value"]})
            self.assertEqual(clean.call_count, 3)
        failure = RuntimeError("synthetic sanitizer failure")
        with patch.object(legacy, "redact", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                legacy.clean_record({"text": "visible"})
            self.assertIs(caught.exception, failure)

    def test_legacy_constant_rebinding_stays_local_and_reaches_all_legacy_helpers(self):
        with patch.object(legacy, "PRIVATE_FIELDS", {"custom"}):
            self.assertTrue(legacy.private_field("custom"))
            self.assertEqual(legacy.clean_record({"custom": "opaque", "password": "old"}), {"password": "old"})
            self.assertTrue(legacy.contains_private({"custom": "opaque"}))
            self.assertTrue(core.private_field("password"))
        with patch.object(legacy, "TOKEN_PATTERN", re.compile("CANARY")):
            self.assertEqual(legacy.safe_text("CANARY"), "[REDACTED]")
            self.assertTrue(legacy.contains_private("CANARY"))
            self.assertEqual(legacy.clean_record({"text": "CANARY"}), {"text": "[REDACTED]"})
            self.assertEqual(core.safe_text("CANARY"), "CANARY")

    def test_t01_quick_and_web_json_bytes_keep_their_distinct_policies(self):
        import generate_image
        import generate_plan_image
        import prepare_plan
        import quick_redesign
        value = {"Authorization": "opaque", "label": "商品", "usage": {"reasoning_tokens": 7},
                 "output": [{"type": "reasoning"}, {"type": "message", "text": "visible"}]}
        expected = {"label": "商品", "usage": {"reasoning_tokens": 7},
                    "output": [{"type": "message", "text": "visible"}]}
        encoded = (json.dumps(expected, ensure_ascii=False, indent=2) + "\n").encode()
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("web.json", "image.json", "quick.json", "t01.json")]
            prepare_plan.write_json(paths[0], value)
            generate_plan_image.write_json(paths[1], value)
            quick_redesign.save_json(paths[2], value)
            generate_image.write_json(paths[3], value, "")
            for path in paths[:3]:
                self.assertEqual(path.read_bytes(), encoded)
            self.assertEqual(paths[3].read_bytes(), (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())
            self.assertFalse(any(Path(directory).glob("*.tmp")))

    def test_fresh_process_imports_core_legacy_and_export_without_any_model_or_business_runtime(self):
        script = """
import importlib,importlib.abc,json,os,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
blocked={'openai','PIL','flask','generate_image','generate_plan_image','prepare_plan','quick_redesign','image_review','image_workflow'}
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in blocked:
   raise AssertionError('Forbidden sanitization dependency: '+name)
sys.meta_path.insert(0,Block())
def guard(event,args):
 if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
  raise AssertionError('Network forbidden')
 if event=='open' and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
  raise AssertionError('Import must not write files')
sys.addaudithook(guard)
module=importlib.import_module(sys.argv[2])
if sys.argv[2]=='experiment_export':
 module=importlib.import_module('evidence')
with patch.dict(os.environ,{'OPENAI_API_KEY':'opaque-child-canary'}), \
 patch('builtins.open',side_effect=AssertionError('No business files')), \
 patch.object(Path,'open',side_effect=AssertionError('No business files')):
 assert module.clean_record({'Authorization':'opaque','label':'opaque-child-canary','usage':{'total_tokens':4}})=={'label':'[REDACTED]','usage':{'total_tokens':4}}
 assert module.contains_private({'password':'opaque'})
assert not any(name.split('.')[0] in blocked for name in sys.modules)
print('independent import and in-memory sanitization PASS')
"""
        for name in ("infrastructure.evidence", "evidence", "experiment_export"):
            with self.subTest(module=name):
                result = subprocess.run([sys.executable, "-B", "-c", script,
                                         str(Path(__file__).resolve().parents[1] / "src"), name],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("independent import", result.stdout)

    def test_infrastructure_is_stdlib_only_and_legacy_module_has_no_filter_implementation(self):
        tree = ast.parse(Path(core.__file__).read_text())
        imports = {node.module if isinstance(node, ast.ImportFrom) else alias.name
                   for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        self.assertEqual(imports, {"json", "os", "re"})
        shim = ast.parse(Path(legacy.__file__).read_text())
        self.assertFalse(any(isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.DictComp, ast.ListComp))
                             for node in ast.walk(shim)))
        imported = {node.module for node in ast.walk(shim) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imported, {"infrastructure", "infrastructure.evidence"})
        self.assertEqual(len(list((Path(core.__file__).parent).glob("*.py"))), 2)


if __name__ == "__main__":
    unittest.main()
