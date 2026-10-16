"""Free evidence/export checks, with blocked real clients and synthetic SDK replies."""

import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import httpx
from openai import OpenAI
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import prepare_plan as web
import generate_plan_image as generation
from evidence import clean_record

HEADERS = {"X-Local-Action": "prepare-plan"}


def png(size=(24, 32)):
    data = io.BytesIO()
    Image.new("RGB", size, "pink").save(data, "PNG")
    return data.getvalue()


class ExperimentExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".runtime"
        self.case = self.root / "inputs/case-001"
        for role in ("product", "references"):
            (self.case / role).mkdir(parents=True)
            (self.case / role / "original.png").write_bytes(png())
        for name, text in [("listing.md", "SKU，宣称待核验"), ("requirements.md", "淡粉背景")]:
            (self.case / name).write_text(text, encoding="utf-8")
        self.app = web.create_app(self.root / "prepare-plan", self.case)
        self.client = self.app.test_client()
        self.store = self.app.extensions["plan_store"]
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "sk-export-offline-test-secret", "OPENAI_PLANNING_MODEL": "gpt-4.1-mini", "OPENAI_IMAGE_MODEL": "gpt-image-2.5-sunburst"})
        self.env.start()
        self.addCleanup(self.env.stop)
        for module, name in [(web, "OpenAI"), (generation, "make_client")]:
            block = patch.object(module, name, side_effect=AssertionError("Real API forbidden"))
            block.start()
            self.addCleanup(block.stop)
        self.sent = []
        self.state = self.client.post("/api/case-001", headers=HEADERS).json["state"]

    def action(self, action, target=None, feedback=""):
        response = self.client.post(f"/api/sessions/{self.state['id']}/action", headers=HEADERS,
            json={"revision": self.state["revision"], "action": action, "target": target, "feedback": feedback})
        if response.status_code == 200:
            self.state = response.json["state"]
        return response

    def sdk(self, fail=False, reasoning=False):
        def transport(request):
            body = json.loads(request.read())
            self.sent.append(body)
            if fail:
                return httpx.Response(429, json={"error": {"message": "Synthetic failure", "type": "rate_limit"}})
            context = json.loads(body["input"][0]["content"][0]["text"])
            result = context["return_json"]
            result = json.loads(json.dumps(result).replace("简短中文", "离线候选，无业务验收"))
            output = [{"type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": json.dumps(result), "annotations": []}]}]
            if reasoning:
                output.insert(0, {"type": "reasoning", "id": "rs_test", "summary": [], "encrypted_content": "hidden-never-store"})
            return httpx.Response(200, json={"id": "resp_test", "status": "completed", "model": "gpt-4.1-mini",
                "output": output, "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}}, headers={"x-request-id": "req_test"})
        return patch.object(web, "OpenAI", side_effect=lambda **kwargs: OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(transport))))

    def initial(self):
        with self.sdk():
            self.assertEqual(self.action("understand").status_code, 200)

    def generate(self, fail=False):
        def transport(request):
            if fail:
                return httpx.Response(500, json={"error": {"message": "Synthetic image failure", "type": "server_error"}})
            return httpx.Response(200, json={"created": 1, "data": [{"b64_json": base64.b64encode(png((1024,1536))).decode()}],
                        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}}, headers={"x-request-id": "req_image"})
        with patch.object(generation, "make_client", side_effect=lambda key: OpenAI(api_key=key, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport)))):
            return self.client.post(f"/api/sessions/{self.state['id']}/generate/reference_001", headers=HEADERS,
                                    json={"confirmed_revision": self.state["revision"]})

    def export(self):
        return self.client.post(f"/api/sessions/{self.state['id']}/export-experiment", headers=HEADERS)

    def inspect_zip(self, response):
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True) if response.status_code != 200 else "")
        self.assertEqual(response.mimetype, "application/zip")
        archive = zipfile.ZipFile(io.BytesIO(response.data))
        self.addCleanup(archive.close)
        self.assertIsNone(archive.testzip())
        self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
        prefix = next(name for name in archive.namelist() if name.endswith("/manifest.json"))[:-len("manifest.json")]
        manifest = json.loads(archive.read(prefix + "manifest.json"))
        expected = {prefix + row["path"] for row in manifest["files"]} | {prefix + "manifest.json"}
        self.assertEqual(set(archive.namelist()), expected)
        for row in manifest["files"]:
            content = archive.read(prefix + row["path"])
            self.assertEqual(hashlib.sha256(content).hexdigest(), row["sha256"])
            self.assertEqual(len(content), row["bytes"])
            self.assertNotIn(os.environ["OPENAI_API_KEY"].encode(), content)
            self.assertNotIn(b"Bearer ", content)
        extracted = Path(self.temp.name) / "extracted"
        archive.extractall(extracted)
        for row in manifest["files"]:
            self.assertEqual(hashlib.sha256((extracted / prefix / row["path"]).read_bytes()).hexdigest(), row["sha256"])
        return archive, prefix, manifest

    def test_all_planning_actions_preserve_exact_requests_and_version_links(self):
        self.initial()
        session = self.store.folder(self.state["id"])
        originals = {p: p.read_bytes() for p in (session / "versions").iterdir()}
        with self.sdk():
            for action, target in [("product", None), ("reference", "reference_001"), ("plan", "reference_001"), ("replan", None)]:
                self.assertEqual(self.action(action, target, "人工修正意见").status_code, 200)
        self.assertEqual(self.action("confirm", "reference_001").status_code, 200)
        for event in self.state["events"]:
            if not event.get("call_id"):
                continue
            folder = session / "calls" / event["call_id"]
            record = web.read_json(folder / "run.json")
            request = web.read_json(folder / "request.json")
            self.assertIn(request, self.sent)
            texts = [item["text"] for item in request["input"][0]["content"] if item["type"] == "input_text"]
            self.assertEqual((folder / "prompt.txt").read_text(), request["instructions"] + "\n\n" + "\n\n".join(texts))
            self.assertEqual(record["run_id"], event["call_id"])
            self.assertEqual(record["case_id"], "case-001")
            self.assertEqual(record["parent_revision"], event["revision"] - 1)
            self.assertEqual(record["parameters"]["model"], request["model"])
            self.assertIn("api_elapsed_seconds", record)
            applied = web.read_json(folder / "applied.json")
            self.assertEqual(applied["revision"], event["revision"])
            self.assertEqual(applied["parent_revision"], record["parent_revision"])
            for item, image in zip([i for i in request["input"][0]["content"] if i["type"]=="input_image"], record["inputs"]):
                data = base64.b64decode(item["image_url"].split(",", 1)[1])
                self.assertEqual(hashlib.sha256(data).hexdigest(), image["sha256"])
                self.assertEqual(data, (session / image["file"]).read_bytes())
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)
        _, _, manifest = self.inspect_zip(self.export())
        self.assertEqual(len(manifest["run_ids"]), 5)
        self.assertEqual(manifest["confirmed_revision"], self.state["revision"])

    def test_generation_failure_and_export_preserve_success_bytes(self):
        self.initial()
        self.assertEqual(self.action("confirm", "reference_001").status_code, 200)
        success = self.generate()
        self.assertEqual(success.status_code, 200)
        folder = self.store.folder(self.state["id"])
        saved = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        failure = self.generate(fail=True)
        self.assertEqual(failure.status_code, 502)
        before_export = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        _, _, manifest = self.inspect_zip(self.export())
        for path, content in before_export.items():
            self.assertEqual(path.read_bytes(), content)
        for path, content in saved.items():
            if path.name != "current.json":
                self.assertEqual(path.read_bytes(), content)
        runs = [row for row in manifest["runs"] if row["stage"] == "T03"]
        self.assertEqual({row["status"] for row in runs}, {"SUCCEEDED", "FAILED"})
        record_path = next(folder.glob(f"generations/**/runs/{success.json['run_id']}/run.json"))
        record = web.read_json(record_path)
        self.assertEqual(record["case_id"], "case-001")
        self.assertEqual(record["action"], "generate_image")
        request = web.read_json(record_path.with_name("request.json"))
        self.assertEqual(request["prompt"], record_path.with_name("prompt.txt").read_text())
        self.assertEqual(record["parameters"]["n"], 1)
        self.assertEqual(runs[0]["inputs"][0]["slot"], 1)

    def test_export_free_allowlist_foreign_files_and_reconstructed_text(self):
        self.initial()
        folder = self.store.folder(self.state["id"])
        for path in [folder / ".env", folder / ".env.example", folder / "source.py", self.root / "foreign/secret.txt"]:
            path.parent.mkdir(exist_ok=True)
            path.write_text("sk-do-not-export-credentials")
        foreign = self.store.create({"listing":"other", "description":"", "requirements":""}, [("product","p.png",png()),("reference","r.png",png())], "other")
        archive, prefix, manifest = self.inspect_zip(self.export())
        self.assertFalse(any(".env" in name or "source.py" in name or foreign["id"] in name for name in archive.namelist()))
        self.assertEqual(archive.read(prefix + "inputs/listing.md").decode(), self.state["inputs"]["listing"])
        row = next(row for row in manifest["files"] if row["path"] == "inputs/listing.md")
        self.assertEqual(row["status"], "RECONSTRUCTED")
        self.assertIn("导出实验包", self.client.get(f"/generate/{self.state['id']}").get_data(as_text=True))
        with self.client.get("/static/generate.js") as response:
            script = response.get_data(as_text=True)
        handler = script[script.index("node('export-experiment').onclick"):]
        self.assertIn("downloadPackage('experiment')", handler)
        self.assertIn('/export-${kind}', script)
        self.assertNotIn("generateOne(", handler)

    def test_symlinks_escaping_paths_and_hash_tampering_rejected(self):
        folder = self.store.folder(self.state["id"])
        image = self.state["images"][0]
        path = folder / image["file"]
        data = path.read_bytes()
        outside = Path(self.temp.name) / "unrelated.png"
        outside.write_bytes(data)
        path.unlink()
        path.symlink_to(outside)
        response = self.export()
        self.assertEqual(response.status_code, 409)
        self.assertIn("符号链接", response.json["error"])
        path.unlink()
        path.write_bytes(b"changed bytes")
        self.assertEqual(self.export().status_code, 409)
        path.write_bytes(data)
        raw = web.read_json(folder / "state.json")
        for invalid in ["../unrelated.png", str(outside), "inputs/../../unrelated.png"]:
            raw["images"][0]["file"] = invalid
            web.write_json(folder / "state.json", raw)
            self.assertEqual(self.export().status_code, 409)
        self.assertEqual(self.client.post("/api/sessions/invalid/export-experiment", headers=HEADERS).status_code, 404)

    def test_credentials_or_hidden_reasoning_in_legacy_artifacts_refuse_export(self):
        self.initial()
        response_path = next(self.store.folder(self.state["id"]).glob("calls/*/response.json"))
        original = response_path.read_bytes()
        for private in [{"Authorization": "opaque-auth-value"}, {"access_token": "opaque-token"},
                        {"output": [{"type": "reasoning", "content": "private thoughts"}]}, {"error": {"body": '{"refresh_token":"opaque"}'}}]:
            response_path.write_text(json.dumps(private))
            response = self.export()
            self.assertEqual(response.status_code, 409)
            self.assertNotIn("opaque", response.json["error"])
        response_path.write_bytes(original)
        self.inspect_zip(self.export())

    def test_new_response_logging_excludes_credentials_and_hidden_reasoning(self):
        with self.sdk(reasoning=True):
            self.assertEqual(self.action("understand").status_code, 200)
        folder = next(self.store.folder(self.state["id"]).glob("calls/*"))
        self.assertNotIn("hidden-never-store", (folder / "response.json").read_text())
        value = clean_record({"headers":{"Authorization":"opaque"}, "usage":{"reasoning_tokens":10},
                              "output":[{"type":"reasoning","summary":["hidden"]},{"type":"message","text":"visible"}]})
        self.assertEqual(value["headers"], {})
        self.assertEqual(value["usage"]["reasoning_tokens"], 10)
        self.assertEqual(len(value["output"]), 1)

    def test_failed_planning_attempt_keeps_previous_versions_and_has_independent_run(self):
        self.initial()
        folder = self.store.folder(self.state["id"])
        before = {p:p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        with self.sdk(fail=True):
            self.assertEqual(self.action("plan", "reference_001", "人工修改").status_code, 502)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        _, _, manifest = self.inspect_zip(self.export())
        self.assertEqual({r["status"] for r in manifest["runs"]}, {"AI_RESULT_RECEIVED", "FAILED"})
        self.assertTrue(any(row["field"].endswith("response.json") for row in manifest["missing"]))

    def test_legacy_t01_included_with_original_bytes_and_missing_labels(self):
        run_id = "20261014T000000Z-" + "1"*32
        folder = self.root / "evidence/case-001" / run_id
        folder.mkdir(parents=True)
        inputs = [{"path":str(path), "sha256":hashlib.sha256(path.read_bytes()).hexdigest(), "selected_for_request":True}
                  for path in self.case.rglob("*") if path.is_file()]
        record = {"run_id":run_id,"status":"API_IMAGE_SAVED_AWAITING_REVIEW","model":"synthetic-history", "api_call_attempted":True,"inputs":inputs,"outputs":[]}
        (folder / "run.json").write_text(json.dumps(record))
        (folder / "request.json").write_text('{"model":"synthetic-history"}')
        (folder / "prompt.txt").write_text("Saved historical prompt")
        (folder / "response.json").write_text('{"usage":null}')
        # Simulate a historical T02 session without case_id, without modifying production history.
        state_path = self.store.folder(self.state["id"]) / "state.json"
        raw = web.read_json(state_path); raw.pop("case_id")
        state_path.write_text(json.dumps(raw))
        archive, prefix, manifest = self.inspect_zip(self.export())
        self.assertEqual(manifest["case_link"]["status"], "RECONSTRUCTED")
        self.assertIn(run_id, manifest["run_ids"])
        self.assertEqual(archive.read(prefix + "evidence/T01/" + run_id + "/run.json"), (folder/"run.json").read_bytes())
        self.assertTrue(any(row["field"]=="usage" and row["status"]=="MISSING" for row in manifest["missing"]))
        (self.case / "listing.md").write_text("different source")
        _, _, unmatched = self.inspect_zip(self.export())
        self.assertNotIn(run_id, unmatched["run_ids"])

    def test_unfinished_or_active_generation_blocks_export_without_retry(self):
        service = self.app.extensions["generation_service"]
        service.active.add((self.state["id"], 1, "reference_001"))
        self.assertEqual(self.export().status_code, 409)
        service.active.clear()
        run = self.store.folder(self.state["id"]) / "generations/000001/reference_001/runs" / ("20261014T000000Z-" + "2" * 32)
        run.mkdir(parents=True)
        (run / "run.json").write_text('{"status":"RUNNING", "api_call_attempted":true}')
        response = self.export()
        self.assertEqual(response.status_code, 409)
        self.assertIn("尚未结束", response.json["error"])
        (run / "run.json").write_text('{"status":"FAILED", "api_call_attempted":false}')
        self.assertEqual(self.client.post(f"/api/sessions/{self.state['id']}/export-experiment").status_code, 403)
        self.inspect_zip(self.export())


if __name__ == "__main__":
    unittest.main()
