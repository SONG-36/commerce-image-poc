"""Local cutover contracts; no SSH, real data, model calls or service starts."""

import ast
import hashlib
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class SourceCutoverTests(unittest.TestCase):
    def test_formal_factory_and_existing_wsgi_entry_are_the_same_function(self):
        import app
        import prepare_plan
        self.assertIs(prepare_plan.create_app, app.create_app)
        self.assertEqual(str(inspect.signature(app.create_app)), "(runtime_dir=None, case_dir=None)")
        self.assertEqual(app.create_app.__module__, "app")
        tree = ast.parse(Path(prepare_plan.__file__).read_text())
        self.assertFalse(any(isinstance(n, (ast.ClassDef, ast.FunctionDef)) for n in ast.walk(tree)))
        with tempfile.TemporaryDirectory() as directory:
            flask_app = prepare_plan.create_app(Path(directory) / "runtime", Path(directory) / "case")
            self.assertEqual(flask_app.import_name, "prepare_plan")
            self.assertEqual(flask_app.root_path, str(Path(app.__file__).parent))
            self.assertEqual(flask_app.static_folder, str(Path(app.__file__).parent / "static"))
            self.assertEqual(flask_app.template_folder, "templates")
            self.assertFalse((Path(directory) / "runtime").exists())

    def test_deploy_model_preflight_handles_staged_app_and_older_release_without_ssh(self):
        script = Path(__file__).resolve().parents[1] / "scripts/deploy_pilot.py"
        module = ast.parse(script.read_text())
        remote = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "REMOTE" for t in n.targets))
        # Execute ONLY the source/model parser against anonymous temporary files.
        parser = remote[remote.index("entry = "):remote.index("assert p['model']")]
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory)
            (old / "src").mkdir()
            legacy = b"MODELS = ('old-allowed',)\n"
            official = b"MODELS = ('new-allowed',)\n"
            (old / "src/prepare_plan.py").write_bytes(legacy)
            for files, expected in (({}, ("old-allowed",)),
                                    ({"src/app.py": official}, ("new-allowed",))):
                scope = {"ast": ast, "files": files, "old": old}
                exec(compile(parser, str(script), "exec"), scope)
                self.assertEqual(scope["models"], expected)
            (old / "src/app.py").write_bytes(official)
            scope = {"ast": ast, "files": {}, "old": old}
            exec(compile(parser, str(script), "exec"), scope)
            self.assertEqual(scope["models"], ("new-allowed",))

    def test_both_web_help_entrypoints_exit_without_starting_a_service(self):
        source = Path(__file__).resolve().parents[1] / "src"
        for name in ("app.py", "prepare_plan.py"):
            result = subprocess.run([sys.executable, "-B", str(source / name), "--help"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--port", result.stdout)

    def test_old_and_formal_experiment_commands_keep_the_same_help_and_module_execution(self):
        source = Path(__file__).resolve().parents[1] / "src"
        for name in ("generate_image", "quick_redesign"):
            outputs = []
            for entry in (source / (name + ".py"), source / "cli" / (name + ".py")):
                result = subprocess.run([sys.executable, "-B", str(entry), "--help"],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--run-paid", result.stdout)
                outputs.append(result.stdout)
            self.assertEqual(outputs[0], outputs[1])
            result = subprocess.run([sys.executable, "-B", "-m", "cli." + name, "--help"],
                                    env={**os.environ, "PYTHONPATH": str(source)},
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_retired_modules_have_no_formal_callers_and_source_hash_inputs_are_single_files(self):
        from image_workflow.tasks import generation_runtime
        source = Path(__file__).resolve().parents[1] / "src"
        retired = {"generate_plan_image", "image_review", "experiment_export", "evidence"}
        for name in retired:
            self.assertFalse((source / (name + ".py")).exists())
        for path in source.rglob("*.py"):
            if path.parent == source / "cli" or path.name in {"generate_image.py", "quick_redesign.py", "prepare_plan.py"}:
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({a.name.split('.')[0] for a in node.names} & (retired | {"cli"}), str(path))
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    self.assertNotIn(node.module.split('.')[0], retired | {"cli"}, str(path))
        io = generation_runtime._runtime().io
        self.assertEqual(io.source_file, Path(generation_runtime.__file__))
        self.assertEqual(io.t01_source_file, source / "cli/generate_image.py")
        self.assertEqual(io.quick_source_file, source / "cli/quick_redesign.py")

    def test_deploy_retirement_only_omits_authorized_source_files_from_the_new_release(self):
        script = Path(__file__).resolve().parents[1] / "scripts/deploy_pilot.py"
        module = ast.parse(script.read_text())
        remote = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "REMOTE" for t in n.targets))
        parser = remote[remote.index("retired = "):remote.index("entry = ")]
        digest = lambda value: hashlib.sha256(value).hexdigest()
        expected = {"src/evidence.py": "old-source", "src/prepare_plan.py": "kept-source"}
        files = {"src/app.py": b"anonymous source"}
        target = {"src/prepare_plan.py": "kept-source", "src/app.py": digest(files["src/app.py"])}
        scope = {"expected": expected.copy(), "files": files, "p": {"target_hashes": target}, "digest": digest}
        exec(compile(parser, str(script), "exec"), scope)
        self.assertEqual(scope["retired"], {"src/evidence.py"})
        self.assertEqual(scope["combined"], target)
        self.assertEqual(scope["expected"], expected)  # Old backup manifest remains intact.
        scope["expected"] = {**expected, "config/anonymous.txt": "protected"}
        with self.assertRaisesRegex(AssertionError, "Unexpected removed"):
            exec(compile(parser, str(script), "exec"), scope)


if __name__ == "__main__":
    unittest.main()
