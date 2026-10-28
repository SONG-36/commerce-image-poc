"""Independent Task/Review adaptation, using temporary anonymous Run fixtures."""

from datetime import datetime, timezone
import io
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from file_ops import read_json
from image_workflow.tasks import review
from image_workflow.tasks.generation import GenerationRuntime, GenerationService
from persistence.review_state import ReviewFiles
import test_review_package as fixtures


class TaskReviewAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ReviewPackageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.state = {"id": self.fx.scope.task_id, "revision": 3,
                      "images": [{"id": name, "role": "reference"} for name in ("reference_001", "reference_002")]}
        self.state['listing_slots'] = [dict(id=f'reference_{101+i}', type='selling_point', enabled=True, reference_id=target) for i, target in enumerate(('reference_001', 'reference_002'))]
        self.target = self.fx.scope.image_id
        self.store = SimpleNamespace(
            folder=lambda task: self.fx.root / "sessions" / task, case_id=lambda state: "case-anonymous",
            image_history=lambda state, target: iter([state]), lock=threading.Lock(),
            load=lambda task: self.state, image_state=lambda state, target: state)
        self.executor = Mock(return_value={"status": "SUCCEEDED"})
        runtime = GenerationRuntime(
            io=SimpleNamespace(read_json=read_json, safe_text=lambda value: value), prompts=None,
            executor=self.executor, environment={}, models=("offline",),
            defaults={"size": "1024x1536"}, quick_sizes=("1024x1536",), timeout_seconds=180.0)
        self.generation = GenerationService(self.store, runtime=lambda: runtime, review=review,
                                            prepare_auxiliary=Mock(side_effect=AssertionError("Not editing")))

    def seeded(self):
        self.fx.seed(0)
        self.fx.seed(1)
        self.fx.pointer({"selected_run": self.fx.ids[0], "passed_run": self.fx.ids[0], "card_revision": 4})

    def assert_released(self):
        self.assertFalse(self.generation.active)
        self.assertFalse(self.generation.guard.locked())
        self.assertTrue(all(not lock.locked() for lock in self.generation.locks.values()))

    def test_scope_files_and_io_adapt_existing_store_and_paths_without_state_ownership(self):
        scope = review.image_scope(self.state, self.target)
        self.assertEqual(scope, self.fx.scope)
        files = review.review_files(self.generation, self.state, self.target)
        self.assertIsInstance(files, ReviewFiles)
        self.assertEqual(files.card_folder(), self.fx.files.card_folder())
        self.assertEqual(files.run_folder(self.fx.ids[0]), self.fx.files.run_folder(self.fx.ids[0]))
        self.assertFalse(hasattr(files, "active"))
        bindings = review.review_io(self.generation, self.state)
        self.assertEqual(bindings.case_id(), "case-anonymous")
        self.assertEqual(bindings.sanitize({"Authorization": "opaque", "label": "anonymous"}), {"label": "anonymous"})
        self.assertEqual(self.generation.locks, {})

    def test_version_and_image_queries_reuse_review_rules_and_do_not_write(self):
        self.seeded()
        before = self.fx.snapshot()
        self.assertEqual(review.versions(self.generation, self.state, self.target),
                         fixtures.versions(self.fx.scope, self.fx.files))
        data, version = review.image_bytes(self.generation, self.state, self.target, self.fx.ids[0])
        self.assertEqual(data, (self.fx.files.run_folder(self.fx.ids[0]) / "image.png").read_bytes())
        self.assertEqual(version["run_id"], self.fx.ids[0])
        self.assertEqual(self.fx.snapshot(), before)
        self.executor.assert_not_called()

    def test_select_and_explicit_pass_keep_distinct_version_pointers(self):
        self.seeded()
        event = review.review(self.generation, self.state, self.target, "select", self.fx.ids[1], 4)
        pointer = self.fx.files.read_pointer(self.fx.files.card_folder())
        self.assertEqual(event["before_passed_run"], self.fx.ids[0])
        self.assertEqual(pointer["selected_run"], self.fx.ids[1])
        self.assertEqual(pointer["passed_run"], self.fx.ids[0])
        self.assertEqual(pointer["card_revision"], 5)
        accepted = review.review(self.generation, self.state, self.target, "pass", self.fx.ids[1], 5)
        self.assertEqual(accepted["after_passed_run"], self.fx.ids[1])
        self.assertEqual(self.fx.files.read_pointer(self.fx.files.card_folder())["card_revision"], 6)
        self.assert_released()

    def test_actual_review_write_uses_existing_lock_and_allows_other_image(self):
        self.seeded()
        original_open = Path.open
        guard, locks, active = self.generation.guard, self.generation.locks, self.generation.active
        observed = []
        def opened(path, mode="r", *args, **kwargs):
            if mode == "x" and path.parent.name == "reviews":
                key = (self.state["id"], 3, self.target)
                self.assertIn(key, active)
                self.assertTrue(locks[key].locked())
                observed.append(locks[key])
                with self.assertRaisesRegex(ValueError, "正在生成"):
                    self.generation.generate(self.state, self.target)
                self.assertEqual(self.generation.generate(self.state, "reference_002")["status"], "SUCCEEDED")
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, "open", opened):
            review.review(self.generation, self.state, self.target, "select", self.fx.ids[1], 4)
        self.assertEqual(len(observed), 1)
        self.assertIs(self.generation.guard, guard)
        self.assertIs(self.generation.locks, locks)
        self.assertIs(self.generation.active, active)
        self.assertIs(locks[(self.state["id"], 3, self.target)], observed[0])
        self.assertEqual(self.executor.call_count, 1)
        self.assert_released()

    def test_review_error_precedence_and_storage_failure_release_original_lock(self):
        self.seeded()
        with self.assertRaisesRegex(ValueError, "状态已改变"):
            review.review(self.generation, self.state, self.target, "unknown", self.fx.ids[1], 3)
        with self.assertRaisesRegex(ValueError, "不支持"):
            review.review(self.generation, self.state, self.target, "unknown", self.fx.ids[1], 4)
        before = self.fx.snapshot()
        with patch.object(ReviewFiles, "save_review", side_effect=OSError("anonymous storage error")):
            with self.assertRaisesRegex(OSError, "anonymous storage error"):
                review.review(self.generation, self.state, self.target, "select", self.fx.ids[1], 4)
        self.assertEqual(self.fx.snapshot(), before)
        self.executor.assert_not_called()
        self.assert_released()

    def test_final_delivery_contains_only_the_explicit_passed_version(self):
        self.seeded()
        before = self.fx.snapshot()
        output, filename = review.export_passed(self.generation, self.state)
        self.assertIsInstance(output, io.BytesIO)
        self.assertEqual(output.tell(), 0)
        self.assertTrue(filename.startswith("task-" + self.state["id"] + "-passed-"))
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ["图片_01_V1.png"])
            self.assertEqual(archive.read("图片_01_V1.png"),
                             (self.fx.files.run_folder(self.fx.ids[0]) / "image.png").read_bytes())
        self.assertEqual(self.fx.snapshot(), before)

    def test_legacy_scope_file_io_and_core_operation_replacements_stay_late_bound(self):
        from image_workflow.tasks import review as legacy
        from infrastructure import evidence
        with patch.object(legacy, "image_scope", return_value="scope") as scope, \
                patch.object(legacy, "review_files", return_value="files") as files, \
                patch.object(legacy, "review_versions", return_value=["version"]) as versions:
            self.assertEqual(legacy.versions(self.generation, self.state, self.target), ["version"])
            scope.assert_called_once_with(self.state, self.target)
            files.assert_called_once_with(self.generation, self.state, self.target)
            versions.assert_called_once_with("scope", "files")
        with patch.object(legacy, "read_json") as reader, patch.object(legacy, "write_json_atomic") as writer:
            files = legacy.review_files(self.generation, self.state, self.target)
            self.assertIs(files.pointer_reader, reader)
            self.assertIs(files.pointer_writer, writer)
        fixed = datetime(2026, 10, 22, tzinfo=timezone.utc)
        with patch.object(legacy, "uuid4") as identifier, \
                patch.object(legacy, "datetime", SimpleNamespace(now=lambda tz: fixed)), \
                patch.object(legacy, "clean_record") as sanitize:
            bindings = legacy.review_io(self.generation, self.state)
            self.assertIs(bindings.new_id, identifier)
            self.assertEqual(bindings.utc_now(), fixed)
            self.assertIs(bindings.sanitize, sanitize)
        def apply(*args, **kwargs):
            self.assertIn((self.state["id"], 3, self.target), self.generation.active)
            return "applied"
        with patch.object(legacy, "apply_review", side_effect=apply) as called:
            self.assertEqual(legacy.review(self.generation, self.state, self.target, "select", "run", 1), "applied")
            self.assertEqual(called.call_count, 1)
        self.assert_released()

    def test_independent_process_runs_adapter_without_sdk_http_or_legacy_entries(self):
        script = r"""
import importlib.abc,runpy,sys,unittest
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'openai','flask','prepare_plan','generate_plan_image','image_review','generate_image','quick_redesign','evidence','api'}:
   raise AssertionError('Forbidden Task review dependency: '+name)
sys.meta_path.insert(0,Block())
def guard(event,args):
 if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
  raise AssertionError('Network forbidden')
sys.addaudithook(guard)
tests=runpy.run_path(sys.argv[1])['TaskReviewAdapterTests']
result=unittest.TextTestRunner().run(unittest.TestSuite([
 tests('test_scope_files_and_io_adapt_existing_store_and_paths_without_state_ownership'),
 tests('test_select_and_explicit_pass_keep_distinct_version_pointers'),
 tests('test_final_delivery_contains_only_the_explicit_passed_version')]))
sys.exit(not result.wasSuccessful())
"""
        result = subprocess.run([sys.executable, "-B", "-c", script, str(Path(__file__).resolve())],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
