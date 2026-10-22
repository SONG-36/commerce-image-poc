"""C3 pure Quick policy and production/experimental boundary checks."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from image_workflow.generation import quick_prompt
import quick_redesign as cli


PROMPT_BEFORE = {
    "generate": "337550debf42d7ee0dd2061137b3695566aac631277e8ed95c32df55bcc57eab",
    "edit": "f060f82d9123ca54625d7bbaaac6c7c4743d3d0e81e80caf781d357dd9eb7683"
}

class QuickPromptPolicyTests(unittest.TestCase):
    def setUp(self):
        self.texts = {"requirements": "Anonymous design <data>", "product_facts": "Unverified operator statement"}
        self.order = [{"slot": 1, "role": "original", "file": "inputs/original.png"},
                      {"slot": 2, "role": "design_reference", "file": "inputs/reference_001.webp"}]

    def test_both_prompt_strings_match_pre_migration_fingerprints(self):
        for module in (cli, quick_prompt):
            with self.subTest(module=module.__name__):
                self.assertEqual(hashlib.sha256(module.build_prompt(self.texts, self.order).encode()).hexdigest(),
                                 PROMPT_BEFORE["generate"])
                self.assertEqual(hashlib.sha256(module.build_edit_prompt(self.texts, self.order, "Only current image").encode()).hexdigest(),
                                 PROMPT_BEFORE["edit"])

    def test_policy_builders_are_pure_and_preserve_inputs(self):
        before = copy.deepcopy((self.texts, self.order))
        with patch("builtins.open", side_effect=AssertionError("Prompt must not read/write files")), \
                patch.object(Path, "open", side_effect=AssertionError("Prompt must not read/write files")):
            self.assertIn(self.texts["requirements"], quick_prompt.build_prompt(self.texts, self.order))
            self.assertIn("Only current image", quick_prompt.build_edit_prompt(self.texts, self.order, "Only current image"))
        self.assertEqual((self.texts, self.order), before)
        imports = {node.module for node in ast.walk(ast.parse(Path(quick_prompt.__file__).read_text(encoding="utf-8")))
                   if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imports, {"pathlib"})

    def test_defaults_belong_to_business_policy_and_dimensions_remain_cli_only(self):
        import prepare_plan
        from infrastructure import openai_images
        self.assertEqual(quick_prompt.DEFAULT_REQUIREMENTS, "提升商业设计质量、排版与信息层级、光影与背景、场景表现及原有卖点的视觉表达。")
        self.assertEqual(quick_prompt.SIZES, ("1024x1536", "1024x1024", "1536x1024"))
        self.assertIs(cli.SIZES, quick_prompt.SIZES)
        self.assertIs(prepare_plan.SIZES, quick_prompt.SIZES)
        self.assertEqual(cli.DEFAULT_REQUIREMENTS, quick_prompt.DEFAULT_REQUIREMENTS)
        self.assertFalse(hasattr(openai_images, "DEFAULT_REQUIREMENTS"))
        self.assertFalse(hasattr(quick_prompt, "DIMENSIONS"))
        self.assertEqual(cli.DIMENSIONS, ("Product Fidelity", "Information Fidelity", "Visual Quality",
                                         "Hallucination", "Revision Effort", "Cost & Latency"))

    def test_edit_roles_and_feedback_remain_explicit_without_mutating_order(self):
        order = [{"slot": 1, "role": "current_image", "file": "inputs/current_image.png"},
                 {"slot": 2, "role": "original", "file": "inputs/product_001.png"},
                 {"slot": 3, "role": "design_reference", "file": "inputs/reference_001.png"}]
        expected = copy.deepcopy(order)
        prompt = quick_prompt.build_edit_prompt(self.texts, order, "Only current image")
        for role in ("图片 1：current_image，current_image.png", "图片 2：original，product_001.png",
                     "图片 3：design_reference，reference_001.png"):
            self.assertIn(role, prompt)
        self.assertIn("<revision_feedback>\nOnly current image\n</revision_feedback>", prompt)
        self.assertEqual(order, expected)

    def test_existing_builder_errors_stay_key_and_type_errors(self):
        for module in (cli, quick_prompt):
            with self.subTest(module=module.__name__):
                with self.assertRaises(KeyError) as caught:
                    module.build_prompt({}, self.order)
                self.assertEqual(caught.exception.args, ("requirements",))
                with self.assertRaises(KeyError) as caught:
                    module.build_edit_prompt(self.texts, [{"slot": 1, "file": "x"}], "feedback")
                self.assertEqual(caught.exception.args, ("role",))
                with self.assertRaises(TypeError):
                    module.build_prompt(self.texts, None)

    def test_cli_compatibility_wrappers_call_policy_and_keep_local_run_patch_seam(self):
        with patch.object(quick_prompt, "build_prompt", return_value="generated") as build:
            self.assertEqual(cli.build_prompt(self.texts, self.order), "generated")
            build.assert_called_once_with(self.texts, self.order)
        with patch.object(quick_prompt, "build_edit_prompt", return_value="edited") as edit:
            self.assertEqual(cli.build_edit_prompt(self.texts, self.order, "feedback"), "edited")
            edit.assert_called_once_with(self.texts, self.order, "feedback")
        import test_quick_redesign as fixtures
        fx = fixtures.QuickRedesignTests()
        fx.setUp()
        try:
            with patch.object(cli, "build_prompt", return_value="legacy CLI override") as build:
                path, record = fx.run_sample()
            self.assertEqual(record["status"], "LOCAL_CHECK_ONLY")
            self.assertEqual(json.loads((path.parent / "request.json").read_text())["prompt"], "legacy CLI override")
            build.assert_called_once()
        finally:
            fx.tearDown()
            fx.doCleanups()

    def test_production_bootstrap_and_generation_assemble_without_experimental_imports(self):
        script = r"""
import importlib.abc, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'generate_image','quick_redesign'}:
   raise AssertionError('Production must not import an experimental CLI: '+name)
sys.meta_path.insert(0,Block())
from openai import OpenAI
with patch('openai.OpenAI',side_effect=AssertionError('Client creation forbidden')):
 import prepare_plan
 import generate_plan_image as generation
 from image_workflow.generation import quick_prompt
 from infrastructure import openai_images
 store=SimpleNamespace()
 service=generation.GenerationService(store)
 with patch.object(generation,'execute_generation',return_value='record') as execute:
  assert service._generate({'id':'a'*32,'revision':1},'product_001')=='record'
  adapters=execute.call_args.kwargs
  assert adapters['io'].client_factory is openai_images.make_client
  assert adapters['prompts'].quick_generate is quick_prompt.build_prompt
  assert adapters['prompts'].quick_edit is quick_prompt.build_edit_prompt
  assert adapters['io'].t01_source_file==Path(generation.__file__).with_name('generate_image.py')
  assert adapters['io'].quick_source_file==Path(generation.__file__).with_name('quick_redesign.py')
 with tempfile.TemporaryDirectory() as directory:
  app=prepare_plan.create_app(Path(directory)/'runtime',Path(directory)/'case')
  assert app.test_client().get('/').status_code==200
assert not {'generate_image','quick_redesign'}.intersection(sys.modules)
print('production without experiment imports PASS')
"""
        result = subprocess.run([sys.executable, "-B", "-c", script, str(Path(cli.__file__).parent)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("production without experiment imports PASS", result.stdout)

    def test_production_import_direction_and_deploy_literal_are_preserved(self):
        root = Path(cli.__file__).parent
        paths = list((root / "infrastructure").rglob("*.py")) + list((root / "image_workflow").rglob("*.py"))
        paths += [root / "generate_plan_image.py", root / "prepare_plan.py", root / "evidence.py"]
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = {node.module.split(".")[0] for node in ast.walk(tree)
                       if isinstance(node, ast.ImportFrom) and node.module}
            imports.update(alias.name.split(".")[0] for node in ast.walk(tree)
                           if isinstance(node, ast.Import) for alias in node.names)
            self.assertFalse(imports & {"generate_image", "quick_redesign"}, str(path))
        tree = ast.parse((root / "prepare_plan.py").read_text(encoding="utf-8"))
        models = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "MODELS" for target in node.targets))
        self.assertEqual(models, ("gpt-5.4-mini", "gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"))


if __name__ == "__main__":
    unittest.main()
