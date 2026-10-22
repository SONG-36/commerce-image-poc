"""C2 export boundary checks using anonymous, temporary artifacts only."""

import ast
import base64
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import experiment_export as legacy
import file_ops
from image_workflow import experiment_export as core

STAMP = "2026-10-22T01:02:03.123456+00:00"
SESSION = "a" * 32
CALL = "b" * 32
RUNS = ["20261022T010203Z-" + digit * 32 for digit in ("1", "2", "3")]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6xkAAAAASUVORK5CYII=")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path.relative_to(root))] = ("symlink", str(path.readlink()))
        elif path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def fixture(root, scenario="complete"):
    """Anonymous saved artifacts only; no Flask/SDK/Task writer dependency."""
    runtime = root / ".runtime"
    store = SimpleNamespace(root=runtime / "prepare-plan", case_dir=runtime / "inputs/case-001")
    session = store.root / "sessions" / SESSION
    case = store.case_dir
    inputs = {"listing": "Anonymous listing, unverified", "description": "Anonymous description",
              "requirements": "Preserve appearance", "product_facts": "Operator statement, unverified"}
    images = [{"id": "product_001", "role": "product", "name": "original.png",
               "file": "inputs/product_001.png", "mime": "image/png", "sha256": hashlib.sha256(PNG).hexdigest()},
              {"id": "reference_001", "role": "reference", "name": "style.png",
               "file": "inputs/reference_001.png", "mime": "image/png", "sha256": hashlib.sha256(PNG).hexdigest()}]
    state = {"id": SESSION, "title": "case-001", "revision": 2, "confirmed": True,
             "case_id": "case-001", "mode": "product_pack", "inputs": inputs, "images": images,
             "events": [{"revision": 1, "action": "inputs_saved", "at": STAMP},
                        {"revision": 2, "action": "understand", "call_id": CALL, "at": STAMP}]}
    if scenario == "quick":
        state.update(mode="quick_redesign", case_id="case-" + SESSION, confirmed=False, title="Anonymous redesign")
    target = "product_001" if scenario == "quick" else "reference_001"
    for image in images:
        path = session / image["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
    for directory, name in (("product", "original.png"), ("references", "style.png")):
        path = case / directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
    for name in ("listing", "requirements"):
        (case / (name + ".md")).write_text(inputs[name], encoding="utf-8")
    write_json(session / "inputs/texts.json", inputs)
    write_json(session / "versions/000001.json", {**state, "revision": 1})
    write_json(session / "versions/000002.json", state)
    if scenario != "quick":
        call = session / "calls" / CALL
        write_json(call / "run.json", {"id": CALL, "status": "AI_RESULT_RECEIVED", "api_call_attempted": True,
                                      "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}})
        write_json(call / "request.json", {"model": "offline", "prompt": "anonymous planning"})
        write_json(call / "response.json", {"result": "anonymous candidate"})
        write_json(call / "image_order.json", images)
        write_json(call / "result.json", {"plans": {target: {"design": "anonymous plan"}}})
        write_json(call / "applied.json", {"revision": 2, "parent_revision": 1, "run_id": CALL})
        (call / "prompt.txt").write_text("anonymous planning prompt", encoding="utf-8")
    card = session / "generations/000002" / target
    for index, run_id in enumerate(RUNS[:2]):
        folder = card / "runs" / run_id
        folder.mkdir(parents=True)
        order = []
        if index:
            (folder / "inputs").mkdir()
            (folder / "inputs/current_image.png").write_bytes(PNG)
            order.append({"id": "current_image", "role": "current_image", "file": "inputs/current_image.png",
                          "slot": 1, "sha256": hashlib.sha256(PNG).hexdigest()})
        for image in images:
            path = folder / image["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(PNG)
            order.append({**image, "slot": len(order) + 1})
        if index:
            (folder / "inputs/auxiliary_reference.png").write_bytes(PNG)
            order.append({"id": "auxiliary_reference", "role": "auxiliary_reference",
                          "purpose": "product_appearance", "purpose_label": "商品外观修正",
                          "file": "inputs/auxiliary_reference.png", "slot": len(order) + 1,
                          "sha256": hashlib.sha256(PNG).hexdigest()})
        for name, text in inputs.items():
            (folder / "inputs" / (name + ".md")).write_text(text, encoding="utf-8")
        record = {"run_id": run_id, "session_id": SESSION, "reference_id": target, "confirmed_revision": 2,
                  "mode": state["mode"], "action": "revise_image" if index else "generate_image",
                  "parent_run_id": RUNS[0] if index else None, "feedback": "Only current image" if index else "",
                  "version": index + 1, "case_id": state["case_id"], "status": "SUCCEEDED",
                  "api_call_attempted": True, "usage": {"total_tokens": 9}, "inputs": order,
                  "output": {"file": "image.png", "sha256": hashlib.sha256(PNG).hexdigest()}}
        write_json(folder / "run.json", record)
        write_json(folder / "plan.json", {"mode": state["mode"], "target": target, "requirements": inputs["requirements"]})
        write_json(folder / "request.json", {"model": "offline", "image_order": order, "prompt": "anonymous edit"})
        write_json(folder / "response.json", {"status": "offline fixture", "usage": {"total_tokens": 9}})
        (folder / "prompt.txt").write_text("anonymous image prompt", encoding="utf-8")
        (folder / "image.png").write_bytes(PNG)
    write_json(card / "current.json", {"latest_run": RUNS[1], "selected_run": RUNS[1], "passed_run": RUNS[0], "card_revision": 3})
    write_json(card / "reviews" / ("c" * 32 + ".json"),
               {"action": "pass", "run_id": RUNS[0], "at": STAMP, "session_id": SESSION})
    if scenario != "quick":
        t01 = runtime / "evidence/case-001" / RUNS[2]
        original = case / "product/original.png"
        write_json(t01 / "run.json", {"run_id": RUNS[2], "status": "API_IMAGE_SAVED_AWAITING_REVIEW",
                  "api_call_attempted": True, "usage": None,
                  "inputs": [{"path": "inputs/case-001/product/original.png",
                              "sha256": hashlib.sha256(original.read_bytes()).hexdigest(), "selected_for_request": True}],
                  "outputs": [{"path": "outputs/case-001/" + RUNS[2] + "/image.png",
                               "sha256": hashlib.sha256(PNG).hexdigest()}]})
        write_json(t01 / "request.json", {"model": "offline", "prompt": "anonymous first image"})
        write_json(t01 / "response.json", {"status": "offline fixture"})
        (t01 / "prompt.txt").write_text("anonymous T01", encoding="utf-8")
        output = runtime / "outputs/case-001" / RUNS[2] / "image.png"
        output.parent.mkdir(parents=True)
        output.write_bytes(PNG)
    foreign = store.root / "sessions" / ("f" * 32) / "private.txt"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("foreign task must not be exported", encoding="utf-8")
    if scenario == "legacy_link":
        state.pop("case_id")
    elif scenario == "unlinked":
        (case / "listing.md").write_text("different source", encoding="utf-8")
    elif scenario == "missing":
        (session / "calls" / CALL / "response.json").unlink()
        (card / "runs" / RUNS[0] / "plan.json").unlink()
        (card / "runs" / RUNS[0] / "image.png").unlink()
    elif scenario in ("failed", "running"):
        path = card / "runs" / RUNS[1]
        record = json.loads((path / "run.json").read_text())
        record.update(status="RUNNING" if scenario == "running" else "FAILED", usage=None, output=None)
        write_json(path / "run.json", record)
        (path / "response.json").unlink()
        write_json(path / "error.json", {"type": "OfflineFailure", "message": "anonymous failure"})
    elif scenario == "wrong_task":
        state["id"] = "e" * 32
    elif scenario == "unsafe_input":
        state["images"][0]["file"] = "../foreign.png"
    elif scenario == "hash_mismatch":
        state["images"][0]["sha256"] = "0" * 64
    elif scenario == "private":
        write_json(card / "runs" / RUNS[1] / "response.json", {"Authorization": "opaque-canary"})
    write_json(session / "state.json", state)
    if scenario == "corrupt_json":
        (session / "state.json").write_text("{broken", encoding="utf-8")
    return store, state, card


def export_fingerprints(module):
    """Freeze clocks only; compare every member byte and ordered ZIP metadata."""
    results = {}
    for scenario in ("complete", "legacy_link", "unlinked", "quick", "missing", "failed",
                     "running", "wrong_task", "unsafe_input", "hash_mismatch", "private", "corrupt_json"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, state, card = fixture(root, scenario)
            before = file_snapshot(root)
            try:
                with patch.object(module, "datetime") as clock, \
                        patch.object(zipfile.time, "localtime", return_value=(2026, 10, 22, 1, 2, 4, 3, 295, -1)):
                    clock.now.return_value = datetime.fromisoformat(STAMP)
                    output, filename = module.export_experiment(store, SESSION)
                    assert output.tell() == 0
                    assert isinstance(output, io.BytesIO)
                    with zipfile.ZipFile(output) as archive:
                        members = [{"name": info.filename, "content": base64.b64encode(archive.read(info)).decode(),
                                    "date_time": info.date_time, "compression": info.compress_type,
                                    "flags": info.flag_bits, "create_version": info.create_version,
                                    "extract_version": info.extract_version, "external_attr": info.external_attr,
                                    "internal_attr": info.internal_attr, "extra": info.extra.hex(), "comment": info.comment.hex(),
                                    "crc": info.CRC, "size": info.file_size} for info in archive.infolist()]
                    outcome = {"filename": filename, "members": members}
                    assert clock.now.call_count == 1
            except Exception as error:
                cause = error.__cause__
                outcome = {"error_type": type(error).__name__, "message": str(error).replace(str(root), "<FIXTURE_ROOT>"),
                           "cause_type": type(cause).__name__ if cause else None}
            assert file_snapshot(root) == before, scenario
            results[scenario] = hashlib.sha256(json.dumps(outcome, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return results


# Original implementation fingerprints, with both clocks frozen.
BEFORE_MIGRATION = {
    "complete": "ca8118c7aeeec4d724af585023419d91c0e96da7caf1871be22dbce56fd975f7",
    "legacy_link": "c9dc6d48e2ea2767b583f52e00107929eb75fb214f86de3ba88391dc47c39f06",
    "unlinked": "f71a526a904b402b63721b719fadb4b174b25e07a879f3117f12b2dcb9403154",
    "quick": "a6da021b72ea746760bce2202fbe44ce07c3c716e210c18f65cd639676017c50",
    "missing": "8e8c65adb536ce697922b9f6ee1759f24050f7635966cfd51561306c359d79a5",
    "failed": "8208ebdbbf8edba889df11ba03dbe24f2704a5385e6fbd672a8b61835141f741",
    "running": "175ec0218bb5f427e4ba5429b49b05458e26dee9fa3f23702a441766b300bee7",
    "wrong_task": "11447d6f61c659d021d4c2060272213f23b82304d12f08bc70847c0ea9d50fd8",
    "unsafe_input": "f8818f651d43fedee43d10077cab0f00ccbb1a06d634513b8f24de86480d228a",
    "hash_mismatch": "4e3ce35c3aaa3649817ae0effb6e411798c2a69ca36fedd6598fd469cdd8339a",
    "private": "0fb6516af11b8df11493fcb397b7457fabe7f937f53ad0bdf9d6ee8190bf8c5f",
    "corrupt_json": "6acd74dc45dd03aba18dd560703dd27b119e39376ec61ca0d6fe2017cc91d885"
}

class ExperimentExportPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def exported(self, scenario="complete", module=core):
        store, state, card = fixture(self.root, scenario)
        before = file_snapshot(self.root)
        with patch.object(module, "datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(STAMP)
            output, filename = module.export_experiment(store, SESSION)
        self.assertEqual(output.tell(), 0)
        self.assertEqual(file_snapshot(self.root), before)
        self.assertEqual(filename, state.get("case_id", "case-001") + "-experiment-20261022-010203-123456.zip")
        archive = zipfile.ZipFile(output)
        self.addCleanup(archive.close)
        prefix = archive.namelist()[0].split("/", 1)[0] + "/"
        manifest = json.loads(archive.read(prefix + "manifest.json"))
        return archive, prefix, manifest

    def test_before_and_after_zip_member_bytes_order_metadata_and_error_fingerprints(self):
        # Captured from the original exporter before migration, not the new code.
        for module in (core, legacy):
            with self.subTest(module=module.__name__):
                self.assertEqual(export_fingerprints(module), BEFORE_MIGRATION)

    def test_actual_bytes_reconstructed_indexes_missing_fields_and_dedup_sources(self):
        archive, prefix, manifest = self.exported()
        statuses = {entry["status"] for entry in manifest["files"]}
        self.assertEqual(statuses, {"ACTUAL", "RECONSTRUCTED"})
        self.assertTrue(all(entry["status"] == "MISSING" for entry in manifest["missing"]))
        self.assertEqual(manifest["case_link"]["status"], "ACTUAL")
        for entry in manifest["files"]:
            content = archive.read(prefix + entry["path"])
            self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(entry["bytes"], len(content))
        self.assertEqual(archive.read(prefix + "inputs/product_001.png"), PNG)
        image = next(entry for entry in manifest["files"] if entry["path"] == "inputs/product_001.png")
        self.assertTrue(any(source["file"].endswith("auxiliary_reference.png") for source in image["sources"]))
        self.assertTrue(any(source["file"] == "inputs/reference_001.png" for source in image["sources"]))
        self.assertEqual(archive.namelist()[-1], prefix + "manifest.json")
        self.assertNotIn("manifest.json", {entry["path"] for entry in manifest["files"]})
        self.assertTrue(all(info.compress_type == zipfile.ZIP_DEFLATED for info in archive.infolist()))
        self.assertTrue(any(entry["field"] == "billed_cost" for entry in manifest["missing"]))

    def test_experiment_includes_candidates_reviews_auxiliary_inputs_and_pass_pointer(self):
        archive, prefix, manifest = self.exported()
        self.assertTrue(all(prefix + "generations/images/" + run + ".png" in archive.namelist() for run in RUNS[:2]))
        pointer = json.loads(archive.read(prefix + "generations/000002/reference_001/current.json"))
        self.assertEqual(pointer["selected_run"], RUNS[1])
        self.assertEqual(pointer["passed_run"], RUNS[0])
        self.assertIn(prefix + "generations/000002/reference_001/reviews/" + "c" * 32 + ".json", archive.namelist())
        revised = next(entry for entry in manifest["runs"] if entry["run_id"] == RUNS[1])
        self.assertEqual(revised["parent_run_id"], RUNS[0])
        self.assertEqual(revised["version"], 2)
        auxiliary = next(entry for entry in revised["inputs"] if entry.get("role") == "auxiliary_reference")
        self.assertEqual(auxiliary["purpose"], "product_appearance")
        self.assertEqual(archive.read(prefix + auxiliary["file"]), PNG)

    def test_quick_redesign_keeps_revision_evidence_without_joining_planning_or_t01(self):
        archive, prefix, manifest = self.exported("quick")
        self.assertEqual(manifest["mode"], "quick_redesign")
        self.assertEqual([entry["stage"] for entry in manifest["runs"]], ["I01", "T04"])
        self.assertNotIn("T01", {entry["stage"] for entry in manifest["runs"]})
        self.assertEqual(len(manifest["runs"]), 2)
        self.assertTrue(any("product_001/current.json" in name for name in archive.namelist()))

    def test_legacy_case_link_requires_original_hashes_and_text_match(self):
        archive, prefix, manifest = self.exported("legacy_link")
        store = SimpleNamespace(root=self.root / ".runtime/prepare-plan",
                                case_dir=self.root / ".runtime/inputs/case-001")
        session = store.root / "sessions" / SESSION
        state = json.loads((session / "state.json").read_text(encoding="utf-8"))
        for module in (core, legacy):
            self.assertTrue(module.historical_case_match(state, session, store.case_dir))
            state["mode"] = "quick_redesign"
            self.assertFalse(module.historical_case_match(state, session, store.case_dir))
            state["mode"] = "product_pack"
        self.assertEqual(manifest["case_link"]["status"], "RECONSTRUCTED")
        self.assertIn("T01", {entry["stage"] for entry in manifest["runs"]})

    def test_unmatched_originals_do_not_join_historical_t01(self):
        archive, prefix, manifest = self.exported("unlinked")
        self.assertNotIn("T01", {entry["stage"] for entry in manifest["runs"]})
        self.assertTrue(any(item["field"] == "T01_link" for item in manifest["missing"]))
        self.assertFalse(any("evidence/T01/" in name for name in archive.namelist()))

    def test_missing_saved_evidence_is_marked_without_substitution(self):
        archive, prefix, manifest = self.exported("missing")
        self.assertNotIn(prefix + "generations/images/" + RUNS[0] + ".png", archive.namelist())
        fields = {entry["field"] for entry in manifest["missing"]}
        self.assertIn("plan.json", fields)
        self.assertIn("planning/calls/" + CALL + "/response.json", fields)
        self.assertFalse(any(("f" * 32) in name for name in archive.namelist()))

    def test_shared_error_identity_json_conversion_and_path_error_cause(self):
        for module in (core, legacy):
            self.assertIs(module.ExportError, file_ops.ExportError)
            self.assertIs(module.safe_path, file_ops.safe_path)
            with self.assertRaises(file_ops.ExportError) as caught:
                module.read_json(self.root, "absent.json")
            self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)
            self.assertEqual(str(caught.exception), "导出已停止：证据 JSON 缺失或无法解析。")
            (self.root / "bad.json").write_text("{", encoding="utf-8")
            with self.assertRaises(file_ops.ExportError) as caught:
                module.read_json(self.root, "bad.json")
            self.assertIsInstance(caught.exception.__cause__, json.JSONDecodeError)
            with self.assertRaises(file_ops.ExportError) as caught:
                module.read_json(self.root, "../foreign")
            self.assertIsNone(caught.exception.__cause__)

    def test_symbols_are_rejected_before_reading_even_when_target_bytes_match(self):
        store, state, card = fixture(self.root)
        original = store.root / "sessions" / SESSION / "inputs/product_001.png"
        saved = self.root / "same-bytes.png"
        saved.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(saved)
        before = file_snapshot(self.root)
        for module in (core, legacy):
            with self.assertRaisesRegex(file_ops.ExportError, "符号链接"):
                module.export_experiment(store, SESSION)
        self.assertEqual(file_snapshot(self.root), before)

    def test_auth_hidden_reasoning_environment_values_reject_not_clean_originals(self):
        store, state, card = fixture(self.root)
        response = card / "runs" / RUNS[1] / "response.json"
        samples = [{"Authorization": "opaque"}, {"type": "reasoning", "summary": []},
                   {"message": "opaque-export-environment-canary"}]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "opaque-export-environment-canary"}):
            for value in samples:
                write_json(response, value)
                before = file_snapshot(self.root)
                for module in (core, legacy):
                    with self.assertRaisesRegex(file_ops.ExportError, "认证信息或隐藏推理"):
                        module.export_experiment(store, SESSION)
                self.assertEqual(file_snapshot(self.root), before)
                self.assertEqual(json.loads(response.read_text()), value)

    def test_legacy_helpers_and_constants_resolve_current_local_bindings(self):
        store, state, card = fixture(self.root)
        with patch.object(legacy, "safe_path", wraps=legacy.safe_path) as path, \
                patch.object(legacy, "read_json", wraps=legacy.read_json) as reader, \
                patch.object(legacy, "historical_case_match", wraps=legacy.historical_case_match) as match, \
                patch.object(legacy, "children", wraps=legacy.children) as children, \
                patch.object(legacy, "sha256", wraps=legacy.sha256) as digest, \
                patch.object(legacy, "contains_private", wraps=legacy.contains_private) as private:
            legacy.export_experiment(store, SESSION)
            path.assert_any_call(store.root, "sessions/" + SESSION)
            reader.assert_any_call(store.root / "sessions" / SESSION, "state.json")
            match.assert_called_once()
            self.assertGreater(children.call_count, 1)
            self.assertGreater(digest.call_count, 1)
            self.assertGreater(private.call_count, 1)
        with patch.object(legacy, "contains_private", return_value=True):
            with self.assertRaisesRegex(file_ops.ExportError, "认证信息或隐藏推理"):
                legacy.export_experiment(store, SESSION)
        with patch.object(legacy, "IMAGE_NAME", r"never-match"):
            with self.assertRaisesRegex(file_ops.ExportError, "白名单"):
                legacy.export_experiment(store, SESSION)
        with patch.object(legacy, "RUN_FILES", ("run.json",)), patch.object(legacy, "RUN_ID", r"never-match"):
            output, _ = legacy.export_experiment(store, SESSION)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertFalse(any("/response.json" in name for name in names))
                manifest = json.loads(archive.read("case-001-experiment/manifest.json"))
                self.assertEqual([run["stage"] for run in manifest["runs"]], ["T02"])

    def test_export_clock_still_runs_after_task_and_case_validation(self):
        store, state, card = fixture(self.root, "wrong_task")
        for module in (core, legacy):
            with patch.object(module, "datetime") as clock:
                with self.assertRaisesRegex(file_ops.ExportError, "任务标识"):
                    module.export_experiment(store, SESSION)
                clock.now.assert_not_called()

    def test_new_exporter_import_and_execution_are_sdk_web_cli_and_legacy_free(self):
        script = r"""
import importlib, importlib.abc, io, json, sys, tempfile, zipfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
blocked = {'openai','PIL','flask','prepare_plan','generate_image','quick_redesign',
           'generate_plan_image','image_review','experiment_export','evidence','api',
           'image_workflow.tasks','image_workflow.planning','image_workflow.generation','image_workflow.review'}
def forbidden(name):
    return any(name == prefix or name.startswith(prefix + '.') for prefix in blocked)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if forbidden(fullname):
            raise AssertionError('Forbidden export dependency: ' + fullname)
sys.meta_path.insert(0, Block())
def guard(event, args):
    if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
        raise AssertionError('Network forbidden')
sys.addaudithook(guard)
module = importlib.import_module('image_workflow.experiment_export')
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    session = root / 'sessions' / ('a' * 32)
    session.mkdir(parents=True)
    state = {'id': 'a' * 32, 'case_id': 'case-anonymous', 'revision': 1, 'inputs': {}, 'images': []}
    (session / 'state.json').write_text(json.dumps(state), encoding='utf-8')
    output, filename = module.export_experiment(SimpleNamespace(root=root, case_dir=None), 'a' * 32)
    assert isinstance(output, io.BytesIO) and output.tell() == 0
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read('case-anonymous-experiment/manifest.json'))
        assert manifest['session_id'] == 'a' * 32
        assert any(item['status'] == 'MISSING' for item in manifest['missing'])
assert not any(forbidden(name) for name in sys.modules)
print('independent import and export PASS')
"""
        result = subprocess.run([sys.executable, "-B", "-c", script,
                                 str(Path(core.__file__).resolve().parents[1])],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("independent import and export PASS", result.stdout)

    def test_canonical_business_owner_has_single_algorithm_and_no_upward_imports(self):
        shim = ast.parse(Path(legacy.__file__).read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(node, (ast.For, ast.While, ast.Try, ast.ListComp, ast.DictComp))
                             for node in ast.walk(shim)))
        tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
        imported = {node.module if isinstance(node, ast.ImportFrom) else alias.name
                    for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        self.assertEqual(imported, {"datetime", "io", "json", "pathlib", "re", "zipfile",
                                    "infrastructure.evidence", "file_ops"})
        # The bootstrap uses the new owner directly; old imports remain callable.
        import prepare_plan
        self.assertIs(prepare_plan.export_experiment, core.export_experiment)
        self.assertIs(prepare_plan.historical_case_match, core.historical_case_match)


if __name__ == "__main__":
    unittest.main()
