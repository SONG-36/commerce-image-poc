"""Product integration checks using only temporary inputs and SDK MockTransport."""

import base64
import io
import json
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

import httpx
import test_generate_plan_image as fixtures


class QuickRedesignIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        self.no_planning = patch.object(fixtures.web, "call_ai", side_effect=AssertionError("Quick mode must not plan"))
        self.no_planning.start()
        self.addCleanup(self.no_planning.stop)
        self.state = self.create().json["state"]
        self.folder = self.store.folder(self.state["id"])

    def create(self, count=3, references=1, **extra):
        data = {"title": "离线重设计测试", "mode": "quick_redesign", "requirements": "浅色商业信息图，保留日文",
                "product_facts": "不得新增配件或参数", "product": [(io.BytesIO(fixtures.png()), f"商品{i}.png") for i in range(count)],
                "reference": [(io.BytesIO(fixtures.png()), f"风格{i}.png") for i in range(references)], **extra}
        return self.client.post("/api/sessions", data=data, headers=fixtures.HEADERS)

    def cards(self, state=None, client=None):
        return (client or self.client).get(f"/api/sessions/{(state or self.state)['id']}/generation").json["cards"]

    def generate(self, target="product_001", *, state=None, operation_id=None, card_revision=None):
        state = state or self.state
        card = next(c for c in self.cards(state) if c["id"] == target)
        return self.client.post(f"/api/sessions/{state['id']}/generate/{target}", headers=fixtures.HEADERS,
            json={"confirmed_revision": state["revision"], "card_revision": card["card_revision"] if card_revision is None else card_revision,
                  "operation_id": operation_id or uuid4().hex})

    def edit(self, feedback="布局保留，背景变浅", parent=None):
        card = self.cards()[0]
        return self.client.post(f"/api/sessions/{self.state['id']}/revise/product_001", headers=fixtures.HEADERS,
            json={"confirmed_revision": self.state["revision"], "card_revision": card["card_revision"], "operation_id": uuid4().hex,
                  "parent_run_id": parent or card["selected_run"], "feedback": feedback})

    def review(self, action, run_id):
        return self.client.post(f"/api/sessions/{self.state['id']}/review/product_001", headers=fixtures.HEADERS,
            json={"confirmed_revision": self.state["revision"], "card_revision": self.cards()[0]["card_revision"],
                  "action": action, "run_id": run_id})

    def run_folder(self, run_id):
        return next(self.folder.glob(f"generations/*/product_001/runs/{run_id}"))

    def test_creation_dynamic_cards_without_listing_reference_or_ai_plan(self):
        for count in (1, 5):
            response = self.create(count=count, references=0, requirements="")
            self.assertEqual(response.status_code, 200, response.json)
            state = response.json["state"]
            self.assertEqual(state["mode"], "quick_redesign")
            self.assertEqual(state["plans"], {})
            self.assertFalse(state["confirmed"])
            self.assertEqual(state["inputs"]["listing"], "")
            self.assertTrue(state["inputs"]["requirements"])
            self.assertEqual(len(self.cards(state)), count)
            for page in ("/", "/prepare/new", "/prepare/" + state["id"], "/generate/" + state["id"]):
                self.assertEqual(self.client.get(page).status_code, 200)
            self.assertFalse((self.store.folder(state["id"]) / "generations").exists())
        self.assertEqual(self.fx.requests, [])

    def test_reload_and_legacy_mode_remain_read_only(self):
        legacy = self.fx.state
        path = self.store.folder(legacy["id"]) / "state.json"
        saved = json.loads(path.read_text())
        saved.pop("mode")
        path.write_text(json.dumps(saved))
        before = {p: p.read_bytes() for p in self.store.root.rglob("*") if p.is_file()}
        client = fixtures.web.create_app(self.fx.runtime).test_client()
        self.assertEqual(client.get(f"/api/sessions/{legacy['id']}").json["state"]["mode"], "product_pack")
        self.assertEqual(len(self.cards(legacy, client)), 3)
        self.assertEqual(len(self.cards(client=client)), 3)
        tasks = client.get("/api/tasks").json["tasks"]
        self.assertEqual({task["mode"] for task in tasks}, {"product_pack", "quick_redesign"})
        self.assertEqual(next(t for t in tasks if t["id"] == self.state["id"])["url"], "/workspace/" + self.state["id"])
        for file, data in before.items():
            self.assertEqual(file.read_bytes(), data)

    def test_mode_validation_copy_and_planner_guard_do_not_call_ai(self):
        for extra in ({"mode": "unknown"}, {"output_size": "999x999"}, {"product_facts": "sk-offline-leaked-secret-example"}):
            self.assertEqual(self.create(**extra).status_code, 400)
        result = self.client.post(f"/api/sessions/{self.state['id']}/action", headers=fixtures.HEADERS,
                                 json={"action": "understand", "revision": self.state["revision"]})
        self.assertEqual(result.status_code, 409)
        data = {"title": "复制", "from_session": self.state["id"], "keep_images": json.dumps([i["id"] for i in self.state["images"]]),
                "mode": "product_pack"}
        self.assertEqual(self.client.post("/api/sessions", data=data, headers=fixtures.HEADERS).status_code, 400)
        before = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        data.update(mode="quick_redesign", requirements="只改整体要求", product_facts="商品结构保留", output_size="1024x1024")
        copy = self.client.post("/api/sessions", data=data, headers=fixtures.HEADERS)
        self.assertEqual(copy.status_code, 200, copy.json)
        self.assertNotEqual(copy.json["state"]["id"], self.state["id"])
        self.assertEqual(copy.json["state"]["output_size"], "1024x1024")
        for file, content in before.items():
            self.assertEqual(file.read_bytes(), content)
        self.assertEqual(self.fx.requests, [])

    def test_independent_request_uses_only_target_source_and_shared_style_constraints(self):
        with self.fx.with_sdk():
            result = self.generate()
        self.assertEqual(result.status_code, 200, result.json)
        folder = self.run_folder(result.json["run_id"])
        request = json.loads((folder / "request.json").read_text())
        self.assertEqual([i["id"] for i in request["image_order"]], ["product_001", "reference_001"])
        self.assertEqual([i["role"] for i in request["image_order"]], ["original", "design_reference"])
        wire = self.fx.requests[-1].read()
        self.assertNotIn(b'filename="product_002.png"', wire)
        self.assertNotIn(b'filename="product_003.png"', wire)
        self.assertEqual(request["prompt"], (folder / "prompt.txt").read_text())
        self.assertIn(self.state["inputs"]["requirements"], request["prompt"])
        self.assertIn(self.state["inputs"]["product_facts"], request["prompt"])
        record = json.loads((folder / "run.json").read_text())
        self.assertEqual(record["mode"], "quick_redesign")
        self.assertEqual(record["usage"]["total_tokens"], 30)
        self.assertEqual(record["request_id"], "req_offline_generation")
        context = json.loads((folder / "plan.json").read_text())
        self.assertNotIn("confirmed_plan", context)
        self.assertEqual(context["source_image_id"], "product_001")
        for image in request["image_order"]:
            self.assertEqual(fixtures.generation.sha256((folder / image["file"]).read_bytes()), image["sha256"])
        self.assertEqual([c["status"] for c in self.cards()], ["SUCCEEDED", "NOT_STARTED", "NOT_STARTED"])

    def test_supported_sizes_use_actual_sdk_parameters(self):
        for size in ("1024x1024", "1536x1024"):
            state = self.create(count=1, references=0, output_size=size).json["state"]
            def handler(request):
                return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(fixtures.png(tuple(map(int, size.split('x'))))).decode()}]})
            with self.fx.with_sdk(handler):
                result = self.generate(state=state)
            self.assertEqual(result.status_code, 200, result.json)
            self.assertIn(size.encode(), self.fx.requests[-1].read())
            self.assertEqual(self.cards(state)[0]["output_size"], size)

    def test_revisions_selection_pass_and_both_exports_share_existing_history(self):
        with self.fx.with_sdk():
            first = self.generate().json["run_id"]
        self.assertEqual(self.review("pass", first).status_code, 200)
        before = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file() and p.name != "current.json"}
        with self.fx.with_sdk():
            result = self.edit()
        self.assertEqual(result.status_code, 200, result.json)
        second = result.json["run_id"]
        request = json.loads((self.run_folder(second) / "request.json").read_text())
        self.assertEqual([i["id"] for i in request["image_order"]], ["current_image", "product_001", "reference_001"])
        self.assertIn("布局保留，背景变浅", request["prompt"])
        self.assertEqual(self.cards()[0]["passed_run"], first)
        self.assertEqual([v["version"] for v in self.cards()[0]["versions"]], [1, 2])
        self.assertEqual(self.review("select", first).status_code, 200)
        with self.fx.with_sdk():
            third = self.edit("保留当前文字").json["run_id"]
        self.assertEqual(self.cards()[0]["versions"][-1]["parent_run_id"], first)
        third_prompt = (self.run_folder(third) / "prompt.txt").read_text()
        self.assertNotIn("布局保留，背景变浅", third_prompt)
        self.assertEqual(self.review("pass", third).status_code, 200)
        final = self.client.post(f"/api/sessions/{self.state['id']}/export-passed", headers=fixtures.HEADERS)
        self.assertEqual(final.status_code, 200, final.json)
        with zipfile.ZipFile(io.BytesIO(final.data)) as archive:
            self.assertEqual(archive.namelist(), ["图片_01_V3.png"])
            self.assertEqual(archive.read(archive.namelist()[0]), (self.run_folder(third) / "image.png").read_bytes())
        package = self.client.post(f"/api/sessions/{self.state['id']}/export-experiment", headers=fixtures.HEADERS)
        self.assertEqual(package.status_code, 200, package.json)
        with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
            manifest = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/manifest.json'))))
            self.assertEqual(manifest["mode"], "quick_redesign")
            self.assertEqual(len(manifest["runs"]), 3)
            self.assertEqual(sorted(r["stage"] for r in manifest["runs"]), ["I01", "T04", "T04"])
            prefix = f"case-{self.state['id']}-experiment/"
            for item in manifest["files"]:
                self.assertEqual(fixtures.generation.sha256(archive.read(prefix + item["path"])), item["sha256"])
            names = archive.namelist()
            self.assertTrue(any(n.endswith('/product_facts.md') for n in names))
            self.assertFalse(any('/evidence/T01/' in n or '/.env' in n for n in names))
            for name in names:
                self.assertNotIn(b'sk-offline-t03-test-key', archive.read(name))
        restarted = fixtures.web.create_app(self.fx.runtime).test_client()
        self.assertEqual(self.cards(client=restarted), self.cards())
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)

    def test_failed_request_preserves_same_and_other_results_without_retry(self):
        with self.fx.with_sdk():
            self.generate()
            self.generate("product_002")
        first, other = self.cards()[:2]
        count = len(self.fx.requests)
        with self.fx.with_sdk(lambda request: httpx.Response(500, json={"error": {"message": "offline connection failure"}})):
            result = self.edit()
        self.assertEqual(result.status_code, 502)
        self.assertEqual(len(self.fx.requests), count + 1)
        self.assertIn("计费尚未确认", result.json["error"])
        self.assertEqual(self.cards()[0]["selected_run"], first["selected_run"])
        self.assertEqual(self.cards()[0]["status"], "FAILED")
        self.assertEqual(self.cards()[1], other)
        self.assertTrue((self.run_folder(result.json["run_id"]) / "error.json").is_file())

    def test_inflight_double_click_and_operation_replay_call_once(self):
        entered, release = threading.Event(), threading.Event()
        def handler(request):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test release timed out")
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(fixtures.png((1024, 1536))).decode()}]})
        operation = uuid4().hex
        result = []
        with self.fx.with_sdk(handler):
            thread = threading.Thread(target=lambda: result.append(self.generate(operation_id=operation)))
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.cards()[0]["status"], "RUNNING")
                self.assertEqual(self.generate().status_code, 409)
            finally:
                release.set()
                thread.join(5)
        self.assertEqual(result[0].status_code, 200)
        self.assertEqual(self.generate(operation_id=operation, card_revision=0).json["run_id"], result[0].json["run_id"])
        self.assertEqual(len(self.fx.requests), 1)

    def test_cross_task_or_style_target_cannot_edit_or_generate_unrelated_image(self):
        other = self.create(count=1).json["state"]
        with self.fx.with_sdk():
            foreign = self.generate(state=other).json["run_id"]
            self.generate()
        before = {p: p.read_bytes() for p in self.store.folder(other["id"]).rglob("*") if p.is_file()}
        self.assertEqual(self.edit(parent=foreign).status_code, 409)
        response = self.client.post(f"/api/sessions/{self.state['id']}/generate/reference_001", headers=fixtures.HEADERS,
                                   json={"confirmed_revision": self.state["revision"], "card_revision": 0, "operation_id": uuid4().hex})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.fx.requests), 2)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
