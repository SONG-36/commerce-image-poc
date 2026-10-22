"""Task-owned coordination tests: isolated files, fake execution, no HTTP/SDK."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from file_ops import read_json, safe_path
from image_workflow.tasks.generation import GenerationRuntime, GenerationService
from image_workflow.tasks.generation_queries import request_uncertain


TASK = "a" * 32
TARGET = "reference_001"
OTHER = "reference_002"
OPERATION = "b" * 32
RUNS = ["20261022T000000Z-" + value * 32 for value in ("1", "2")]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FakeStore:
    def __init__(self, root, state):
        self.root = root
        self.state = state
        self.lock = threading.Lock()
        self.fresh_revision = state["revision"]

    def folder(self, task_id):
        return safe_path(self.root, "sessions/" + task_id)

    def load(self, task_id):
        assert task_id == self.state["id"]
        return copy.deepcopy(self.state)

    def image_state(self, state, target):
        return {**state, "revision": self.fresh_revision}

    def case_id(self, state):
        return "case-anonymous"


class TaskGenerationCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = {"id": TASK, "revision": 3, "mode": "product_pack",
                      "images": [{"id": target, "role": "reference", "name": target + ".png"}
                                 for target in (TARGET, OTHER)],
                      "plans": {TARGET: {}, OTHER: {}}, "inputs": {"requirements": "anonymous"}}
        self.store = FakeStore(self.root, self.state)
        self.executor = Mock(return_value={"status": "SUCCEEDED"})
        self.review = SimpleNamespace(versions=Mock(return_value=[]),
                                      image_bytes=Mock(return_value=(b"anonymous parent", {"version": 1})))
        self.auxiliary = Mock(side_effect=lambda name, data, purpose:
                              {"name": name, "data": data, "purpose": purpose, "sha256": "fixed"})
        self.runtime = GenerationRuntime(
            io=SimpleNamespace(read_json=read_json, safe_text=lambda value: value),
            prompts=None, executor=self.executor, environment={}, models=("offline",),
            defaults={"size": "1024x1536"}, quick_sizes=("1024x1536",), timeout_seconds=180.0)
        self.service = GenerationService(self.store, runtime=lambda: self.runtime,
                                         review=self.review, prepare_auxiliary=self.auxiliary)

    def seed(self, status="SUCCEEDED", *, operation=OPERATION, target=TARGET, run_id=RUNS[0], **changes):
        record = {"run_id": run_id, "session_id": TASK, "reference_id": target, "confirmed_revision": 3,
                  "status": status, "operation_id": operation, "parent_run_id": None, "feedback": "",
                  "api_call_attempted": True, "started_at": "fixed", "error": None}
        record.update(changes)
        write(self.service.run_folder(TASK, 3, target, run_id) / "run.json", record)
        return record

    def assert_released(self):
        self.assertFalse(self.service.active)
        self.assertFalse(self.store.lock.locked())
        self.assertFalse(self.service.guard.locked())
        self.assertTrue(all(not lock.locked() for lock in self.service.locks.values()))

    def test_instance_owns_one_runtime_registry_and_execution_receives_scoped_access(self):
        self.assertEqual(self.service.generate(self.state, TARGET, operation_id=OPERATION)["status"], "SUCCEEDED")
        args = self.executor.call_args
        self.assertEqual(args.args, (self.state, TARGET, None, "", OPERATION, None))
        self.assertIs(args.kwargs["io"], self.runtime.io)
        self.assertEqual(args.kwargs["access"].input_folder(), self.store.folder(TASK))
        self.assertEqual(args.kwargs["access"].case_id(), "case-anonymous")
        other = GenerationService(self.store, runtime=lambda: self.runtime,
                                  review=self.review, prepare_auxiliary=self.auxiliary)
        self.assertIsNot(other.guard, self.service.guard)
        self.assertIsNot(other.locks, self.service.locks)
        self.assert_released()

    def test_busy_generation_blocks_same_image_and_review_but_allows_other_image(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        active = (TASK, 3, TARGET)
        def execute(state, target, *args, **kwargs):
            if target == TARGET:
                entered.set()
                if not release.wait(3):
                    raise AssertionError("Test executor did not receive release")
            else:
                self.assertIn(active, self.service.active)
                self.assertIn((TASK, 3, OTHER), self.service.active)
            return {"status": "SUCCEEDED"}
        self.executor.side_effect = execute
        def worker():
            try:
                self.service.generate(self.state, TARGET)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            with self.assertRaisesRegex(ValueError, "正在生成"):
                self.service.generate(self.state, TARGET)
            with self.assertRaisesRegex(ValueError, "正在处理"):
                with self.service.review_operation(self.state, TARGET):
                    self.fail("Review must not enter while generation owns the image")
            self.assertEqual(self.service.generate(self.state, OTHER)["status"], "SUCCEEDED")
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.executor.call_count, 2)
        self.assert_released()

    def test_review_uses_same_registry_and_blocks_generation_without_a_second_lock(self):
        key = (TASK, 3, TARGET)
        with self.service.review_operation(self.state, TARGET):
            original = self.service.locks[key]
            self.assertTrue(original.locked())
            self.assertIn(key, self.service.active)
            with self.assertRaisesRegex(ValueError, "正在生成"):
                self.service.generate(self.state, TARGET)
            self.assertIs(self.service.locks[key], original)
            self.assertEqual(self.service.generate(self.state, OTHER)["status"], "SUCCEEDED")
        self.assert_released()

    def test_store_exclusion_and_changed_confirmation_release_the_original_locks(self):
        with self.store.lock:
            with self.assertRaisesRegex(ValueError, "资料或计划"):
                self.service.generate(self.state, TARGET)
        self.assert_released()
        self.store.fresh_revision = 4
        with self.assertRaisesRegex(ValueError, "确认版本已改变"):
            self.service.generate(self.state, TARGET)
        self.executor.assert_not_called()
        self.assert_released()

    def test_execution_and_review_exceptions_release_activity_and_image_lock(self):
        for error in (RuntimeError("offline executor error"), KeyboardInterrupt()):
            self.executor.side_effect = error
            with self.assertRaises(type(error)):
                self.service.generate(self.state, TARGET)
            self.assert_released()
        with self.assertRaisesRegex(RuntimeError, "offline review error"):
            with self.service.review_operation(self.state, TARGET):
                raise RuntimeError("offline review error")
        self.assert_released()

    def test_terminal_operation_is_reused_before_card_conflict_without_retry(self):
        for status in ("SUCCEEDED", "FAILED"):
            record = self.seed(status)
            self.assertEqual(self.service.generate(self.state, TARGET, operation_id=OPERATION,
                                                  expected_revision=999), record)
            self.assert_released()
        self.executor.assert_not_called()

    def test_unfinished_or_changed_operation_never_invokes_executor(self):
        self.seed("RUNNING")
        with self.assertRaisesRegex(ValueError, "状态待确认"):
            self.service.generate(self.state, TARGET, operation_id=OPERATION)
        self.seed("FAILED")
        with self.assertRaisesRegex(ValueError, "不同请求"):
            self.service.generate(self.state, TARGET, operation_id=OPERATION, feedback="changed")
        self.executor.assert_not_called()
        self.assert_released()

    def test_operation_query_preserves_identity_and_uncertain_failure_meaning(self):
        self.assertEqual(self.service.operation(self.state, TARGET, OPERATION)["status"], "NOT_FOUND")
        self.seed("RUNNING")
        result = self.service.operation(self.state, TARGET, OPERATION)
        self.assertEqual(result["status"], "INTERRUPTED")
        self.assertTrue(result["uncertain"])
        with self.service.review_operation(self.state, TARGET):
            self.assertEqual(self.service.operation(self.state, TARGET, OPERATION)["status"], "RUNNING")
        self.seed("SUCCEEDED", session_id="c" * 32)
        with self.assertRaisesRegex(ValueError, "本任务不一致"):
            self.service.operation(self.state, TARGET, OPERATION)
        for code, expected in ((429, False), (408, True), (500, True), (None, True)):
            self.assertEqual(request_uncertain({"status": "FAILED", "api_call_attempted": True,
                                                "error": {"status_code": code}}), expected)
        self.executor.assert_not_called()
        self.assert_released()

    def test_card_query_keeps_selected_passed_and_previous_success_without_writes(self):
        self.seed("SUCCEEDED")
        folder = self.service.run_folder(TASK, 3, TARGET, RUNS[0])
        (folder / "image.png").write_bytes(b"anonymous existing image")
        self.seed("RUNNING", run_id=RUNS[1])
        write(self.service.folder(TASK, 3, TARGET) / "current.json",
              {"latest_run": RUNS[1], "selected_run": RUNS[0], "passed_run": RUNS[0], "card_revision": 4})
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        card = self.service.card(self.state, TARGET)
        self.assertEqual(card["status"], "INTERRUPTED")
        self.assertEqual(card["selected_run"], RUNS[0])
        self.assertEqual(card["passed_run"], RUNS[0])
        self.assertIn(RUNS[0], card["image_url"])
        self.assertFalse(card["image_is_latest"])
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        self.executor.assert_not_called()

    def test_parent_revision_and_auxiliary_validation_keep_error_precedence(self):
        with self.assertRaisesRegex(ValueError, "只用于修改"):
            self.service.generate(self.state, TARGET, auxiliary={"name": "x", "data": b"x", "purpose": "design_style"})
        self.auxiliary.assert_not_called()
        write(self.service.folder(TASK, 3, TARGET) / "current.json",
              {"selected_run": RUNS[0], "passed_run": RUNS[0], "card_revision": 4})
        with self.assertRaisesRegex(ValueError, "状态已改变"):
            self.service.generate(self.state, TARGET, RUNS[1], expected_revision=3)
        with self.assertRaisesRegex(ValueError, "选中版本已改变"):
            self.service.generate(self.state, TARGET, RUNS[1], expected_revision=4)
        self.service.generate(self.state, TARGET, RUNS[0], "feedback", 4,
                              auxiliary={"name": "x.png", "data": b"current-only", "purpose": "design_style"})
        self.auxiliary.assert_called_once_with("x.png", b"current-only", "design_style")
        self.review.image_bytes.assert_called_once_with(self.service, self.state, TARGET, RUNS[0])
        self.assertEqual(self.executor.call_args.args[-1]["data"], b"current-only")
        self.assertEqual(read_json(self.service.folder(TASK, 3, TARGET) / "current.json")["passed_run"], RUNS[0])
        self.assert_released()

    def test_original_class_and_instance_method_override_seams_remain_usable(self):
        import generate_plan_image as legacy
        service = legacy.GenerationService(self.store)
        self.assertIsInstance(service, GenerationService)
        with patch.object(legacy, "make_client") as factory, \
                patch.object(legacy, "execute_generation", return_value={"status": "FAKE"}) as execute:
            self.assertEqual(service._generate(self.state, TARGET)["status"], "FAKE")
            self.assertIs(execute.call_args.kwargs["io"].client_factory, factory)
            self.assertEqual(execute.call_args.kwargs["io"].source_file, Path(legacy.__file__))
        with patch.object(legacy.GenerationService, "targets", return_value=[]):
            with self.assertRaisesRegex(ValueError, "不属于"):
                service.generate(self.state, TARGET)
        service._generate = Mock(return_value={"status": "INSTANCE_OVERRIDE"})
        self.assertEqual(service.generate(self.state, TARGET)["status"], "INSTANCE_OVERRIDE")
        with patch.object(legacy.GenerationService, "_generate", return_value={"status": "CLASS_OVERRIDE"}):
            other = legacy.GenerationService(self.store)
            self.assertEqual(other.generate(self.state, OTHER)["status"], "CLASS_OVERRIDE")
        self.assertFalse(service.active)
        self.assertFalse(other.active)

    def test_fresh_process_coordinates_without_web_sdk_or_legacy_entries(self):
        script = r"""
import importlib.abc,runpy,sys,unittest
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'flask','openai','prepare_plan','generate_plan_image','image_review','generate_image','quick_redesign','evidence','api'}:
   raise AssertionError('Forbidden Task coordination dependency: '+name)
sys.meta_path.insert(0,Block())
def guard(event,args):
 if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
  raise AssertionError('Network forbidden')
sys.addaudithook(guard)
tests=runpy.run_path(sys.argv[1])['TaskGenerationCoordinationTests']
result=unittest.TextTestRunner().run(unittest.TestSuite([
 tests('test_instance_owns_one_runtime_registry_and_execution_receives_scoped_access'),
 tests('test_busy_generation_blocks_same_image_and_review_but_allows_other_image'),
 tests('test_terminal_operation_is_reused_before_card_conflict_without_retry')]))
sys.exit(not result.wasSuccessful())
"""
        result = subprocess.run([sys.executable, "-B", "-c", script, str(Path(__file__).resolve())],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
