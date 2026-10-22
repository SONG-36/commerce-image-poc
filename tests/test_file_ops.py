"""Temporary-file contracts for G1; no private runtime or model calls."""

import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import file_ops
from image_workflow import experiment_export
from cli import generate_image
from image_workflow.tasks import generation_runtime as generate_plan_image
import app as prepare_plan
from cli import quick_redesign


class FileOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_safe_path_returns_lexical_descendant_without_creating_files(self):
        root = self.root / '.runtime' / 'sessions'
        expected = root / 'new-task' / 'state.json'
        self.assertEqual(file_ops.safe_path(root, 'new-task/state.json'), expected)
        self.assertFalse(root.exists())
        self.assertEqual(file_ops.safe_path(root), root)

    def test_absolute_traversal_and_backslash_paths_keep_original_error(self):
        for relative in ['/tmp/foreign', '../foreign', 'a/../../foreign', 'a\\foreign']:
            with self.subTest(relative=relative), self.assertRaises(file_ops.ExportError) as caught:
                file_ops.safe_path(self.root, relative)
            self.assertEqual(str(caught.exception), '导出已停止：记录包含越界路径。')

    def test_final_intermediate_and_dangling_symlinks_are_refused(self):
        (self.root / 'real').mkdir()
        (self.root / 'real' / 'state.json').write_text('{}')
        (self.root / 'link').symlink_to(self.root / 'real', target_is_directory=True)
        (self.root / 'missing').symlink_to(self.root / 'not-there')
        for relative in ['link', 'link/state.json', 'missing']:
            with self.subTest(relative=relative), self.assertRaises(file_ops.ExportError) as caught:
                file_ops.safe_path(self.root, relative)
            self.assertEqual(str(caught.exception), '导出已停止：允许范围内发现符号链接。')

    def test_symlink_in_runtime_ancestry_is_refused(self):
        actual = self.root / 'actual'
        (actual / 'sessions' / 'task').mkdir(parents=True)
        runtime = self.root / '.runtime'
        runtime.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(file_ops.ExportError, '运行目录是符号链接'):
            file_ops.safe_path(runtime / 'sessions' / 'task', 'state.json')

    def test_trusted_platform_ancestor_outside_runtime_remains_allowed(self):
        actual = self.root / 'platform'
        (actual / '.runtime' / 'sessions').mkdir(parents=True)
        link = self.root / 'platform-link'
        link.symlink_to(actual, target_is_directory=True)
        root = link / '.runtime' / 'sessions'
        self.assertEqual(file_ops.safe_path(root, 'state.json'), root / 'state.json')

    def test_read_json_preserves_unicode_and_native_failures(self):
        path = self.root / 'state.json'
        path.write_bytes('["商品", {"value": 2}]'.encode('utf-8'))
        self.assertEqual(file_ops.read_json(path), ['商品', {'value': 2}])
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            file_ops.read_json(path)
        path.write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError):
            file_ops.read_json(path)
        with self.assertRaises(FileNotFoundError):
            file_ops.read_json(self.root / 'missing.json')
        with self.assertRaises(IsADirectoryError):
            file_ops.read_json(self.root)

    def test_atomic_write_keeps_exact_encoding_and_replacement_order(self):
        path = self.root / 'state.json'
        temporary = self.root / 'state.json.tmp'
        path.write_bytes(b'old-state')
        temporary.write_bytes(b'old-temporary')
        events = []
        original_write, original_replace = Path.write_text, Path.replace

        def write(target, text, *args, **kwargs):
            self.assertEqual(path.read_bytes(), b'old-state')
            events.append(('write', target.name, kwargs.get('encoding')))
            return original_write(target, text, *args, **kwargs)

        def replace(source, target):
            self.assertEqual(path.read_bytes(), b'old-state')
            events.append(('replace', source.name, target.name))
            return original_replace(source, target)

        with patch.object(Path, 'write_text', new=write), patch.object(Path, 'replace', new=replace):
            result = file_ops.write_json_atomic(path, {'商品': '保持', 'count': 1})
        self.assertIsNone(result)
        self.assertEqual(events, [('write', 'state.json.tmp', 'utf-8'), ('replace', 'state.json.tmp', 'state.json')])
        self.assertEqual(path.read_bytes(), '{\n  "商品": "保持",\n  "count": 1\n}\n'.encode('utf-8'))
        self.assertFalse(temporary.exists())

    def test_exclusive_write_never_overwrites_or_uses_temporary_file(self):
        path = self.root / 'version.json'
        file_ops.write_json_exclusive(path, {'version': 1})
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            file_ops.write_json_exclusive(path, {'version': 2})
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.root / 'version.json.tmp').exists())

    def test_validation_precedes_transform_and_serialization(self):
        target = self.root / 'target.json'
        target.write_text('{}')
        path = self.root / 'link.json'
        path.symlink_to(target)
        for writer in (file_ops.write_json_atomic, file_ops.write_json_exclusive):
            transform = unittest.mock.Mock(side_effect=AssertionError('must not transform'))
            with self.subTest(writer=writer.__name__), self.assertRaises(file_ops.ExportError):
                writer(path, {'invalid': object()}, transform=transform)
            transform.assert_not_called()
        self.assertEqual(target.read_text(), '{}')

    def test_serialization_and_missing_parent_fail_without_creating_directories(self):
        path = self.root / 'state.json'
        path.write_bytes(b'old-state')
        for writer in (file_ops.write_json_atomic, file_ops.write_json_exclusive):
            with self.subTest(writer=writer.__name__), self.assertRaises(TypeError):
                writer(path, {'invalid': object()})
            self.assertEqual(path.read_bytes(), b'old-state')
            self.assertFalse((self.root / 'state.json.tmp').exists())
            with self.assertRaises(FileNotFoundError):
                writer(self.root / 'missing' / 'state.json', {})
            self.assertFalse((self.root / 'missing').exists())

    def test_failed_replace_preserves_old_target_and_new_temporary_bytes(self):
        path = self.root / 'state.json'
        path.write_bytes(b'old-state')
        error = OSError('synthetic replace failure')
        with patch.object(Path, 'replace', side_effect=error), self.assertRaises(OSError) as caught:
            file_ops.write_json_atomic(path, {'new': True})
        self.assertIs(caught.exception, error)
        self.assertEqual(path.read_bytes(), b'old-state')
        self.assertEqual((self.root / 'state.json.tmp').read_bytes(), b'{\n  "new": true\n}\n')

    def test_temporary_symlink_is_checked_after_transformation_without_writing(self):
        path = self.root / 'state.json'
        foreign = self.root / 'foreign'
        foreign.write_bytes(b'preserve')
        (self.root / 'state.json.tmp').symlink_to(foreign)
        seen = []
        with self.assertRaises(file_ops.ExportError):
            file_ops.write_json_atomic(path, {}, transform=lambda value: seen.append('transform') or value)
        self.assertEqual(seen, ['transform'])
        self.assertFalse(path.exists())
        self.assertEqual(foreign.read_bytes(), b'preserve')

    def test_neutral_json_has_no_implicit_redaction_but_wrappers_keep_their_policy(self):
        value = {'api_key': 'synthetic-field', 'label': '商品', 'usage': {'reasoning_tokens': 7}}
        neutral, planning, generation, legacy, quick = [self.root / (name + '.json')
                                                     for name in ('neutral', 'planning', 'generation', 'legacy', 'quick')]
        file_ops.write_json_atomic(neutral, value)
        self.assertEqual(file_ops.read_json(neutral), value)
        prepare_plan.write_json(planning, value)
        generate_plan_image.write_json(generation, value)
        generate_image.write_json(legacy, value, '')
        quick_redesign.save_json(quick, value)
        clean = {'label': '商品', 'usage': {'reasoning_tokens': 7}}
        for path in (planning, generation, quick):
            self.assertEqual(file_ops.read_json(path), clean)
        self.assertEqual(planning.read_bytes(), generation.read_bytes())
        self.assertEqual(planning.read_bytes(), quick.read_bytes())
        self.assertEqual(file_ops.read_json(legacy), value)
        immutable = self.root / 'immutable.json'
        prepare_plan.write_json(immutable, value, exclusive=True)
        with self.assertRaises(FileExistsError):
            prepare_plan.write_json(immutable, {}, exclusive=True)
        self.assertEqual(immutable.read_bytes(), planning.read_bytes())

    def test_legacy_direct_writer_still_overwrites_and_applies_explicit_redaction(self):
        path = self.root / 'legacy.json'
        path.write_text('old')
        key = 'synthetic-private-value'
        generate_image.write_json(path, {'text': 'before ' + key}, key)
        self.assertEqual(file_ops.read_json(path), {'text': 'before [REDACTED]'})
        self.assertFalse((self.root / 'legacy.json.tmp').exists())

    def test_export_keeps_exception_identity_and_read_error_translation(self):
        self.assertIs(experiment_export.ExportError, file_ops.ExportError)
        self.assertEqual(file_ops.ExportError.__name__, 'ExportError')
        self.assertIs(experiment_export.safe_path, file_ops.safe_path)
        missing = self.root / 'missing.json'
        with self.assertRaises(FileNotFoundError):
            prepare_plan.read_json(missing)
        with self.assertRaises(FileNotFoundError):
            generate_plan_image.read_json(missing)
        with self.assertRaises(experiment_export.ExportError) as caught:
            experiment_export.read_json(self.root, missing.name)
        self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)
        self.assertEqual(str(caught.exception), '导出已停止：证据 JSON 缺失或无法解析。')
        damaged = self.root / 'damaged.json'
        damaged.write_text('{broken', encoding='utf-8')
        with self.assertRaises(experiment_export.ExportError) as caught:
            experiment_export.read_json(self.root, damaged.name)
        self.assertIsInstance(caught.exception.__cause__, json.JSONDecodeError)
        self.assertEqual(str(caught.exception), '导出已停止：证据 JSON 缺失或无法解析。')
        with self.assertRaises(experiment_export.ExportError) as caught:
            experiment_export.read_json(self.root, '../foreign')
        self.assertIsNone(caught.exception.__cause__)

    def test_hash_is_byte_based_and_old_import_remains_compatible(self):
        for raw in (b'', b'\x00\xff\x01', '商品'.encode('utf-8')):
            self.assertEqual(file_ops.sha256(raw), hashlib.sha256(raw).hexdigest())
        self.assertIs(generate_image.sha256, file_ops.sha256)

    def test_shared_module_and_consumers_have_no_reverse_file_dependencies(self):
        source = Path(file_ops.__file__).parent
        for name in ('file_ops', 'image_workflow.tasks.generation_runtime', 'image_workflow.tasks.review', 'cli.quick_redesign', 'app'):
            tree = ast.parse((source / (name.replace('.', '/') + '.py')).read_text())
            imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
            modules = {node.module for node in imports if isinstance(node, ast.ImportFrom)}
            modules.update(alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names)
            if name == 'file_ops':
                self.assertEqual(modules, {'hashlib', 'json', 'pathlib'})
            if name in ('image_workflow.tasks.generation_runtime', 'image_workflow.tasks.review', 'cli.quick_redesign'):
                self.assertNotIn('experiment_export', modules)
            if name == 'image_workflow.tasks.review':
                self.assertNotIn('generate_plan_image', modules)
                self.assertNotIn('generate_image', modules)
            for node in imports:
                if isinstance(node, ast.ImportFrom) and node.module == 'experiment_export':
                    self.assertNotIn('safe_path', {alias.name for alias in node.names})


if __name__ == '__main__':
    unittest.main()
