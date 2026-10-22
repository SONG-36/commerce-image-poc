"""T03 offline fixtures and SDK transport tests; never a real model acceptance."""

import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import app as web
from image_workflow.tasks import generation_runtime as generation

HEADERS = {"X-Local-Action": "prepare-plan"}


def png(size=(24, 32)):
    output = io.BytesIO()
    Image.new("RGB", size, "pink").save(output, "PNG")
    return output.getvalue()


class GenerationPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name) / "prepare-plan"
        self.app = web.create_app(self.runtime)
        self.client = self.app.test_client()
        self.store = self.app.extensions["plan_store"]
        self.state = self.confirmed(3)
        self.original = {p: p.read_bytes() for p in self.store.folder(self.state["id"]).rglob("*") if p.is_file()}
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "sk-offline-t03-test-key", "OPENAI_IMAGE_MODEL": "gpt-image-2.5-sunburst"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.no_network = patch.object(generation, "make_client", side_effect=AssertionError("Real network forbidden"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)
        self.requests = []

    def confirmed(self, count):
        uploads = [("product", f"p-{i}.png", png()) for i in range(2)]
        uploads += [("reference", f"r-{i}.png", png()) for i in range(count)]
        state = self.store.create({"listing": "原始 Listing：参数待核实。", "description": "当前商品描述。", "requirements": "淡粉色杂志风。"}, uploads, "离线测试资料")
        ids = web.reference_ids(state)
        state["product"] = {key: "商品候选理解，未经核验" for key in web.PRODUCT_FIELDS}
        state["product_version"] = 1
        state["references"] = {ref: {key: f"仅 {ref} 的参考理解" for key in web.REFERENCE_FIELDS} for ref in ids}
        state["reference_versions"] = {ref: 1 for ref in ids}
        state["plans"] = {ref: {key: f"仅 {ref} 的计划：{key}" for key in web.PLAN_FIELDS} for ref in ids}
        state["plan_context"] = {ref: [1, 1] for ref in ids}
        state["confirmed"] = True
        self.store.save(state, {"action": "confirm", "target": None, "feedback": "DO_NOT_SEND_OTHER_IMAGE_HISTORY"})
        return state

    def post(self, target, state=None):
        state = state or self.state
        return self.client.post(f"/api/sessions/{state['id']}/generate/{target}", json={"confirmed_revision": state["revision"]}, headers=HEADERS)

    def cards(self, state=None, client=None):
        state = state or self.state
        return (client or self.client).get(f"/api/sessions/{state['id']}/generation")

    def with_sdk(self, handler=None):
        def transport(request):
            self.requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://api.openai.com/v1/images/edits")
            if handler:
                return handler(request)
            return httpx.Response(200, json={"created": 1, "data": [{"b64_json": base64.b64encode(png((1024, 1536))).decode()}], "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}}, headers={"x-request-id": "req_offline_generation"})
        return patch.object(generation, "make_client", side_effect=lambda key: OpenAI(api_key=key, max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(transport))))

    def test_page_and_dynamic_cards_are_read_only_and_free(self):
        for count in [1, 5]:
            state = self.confirmed(count)
            self.assertEqual(self.client.get(f"/generate/{state['id']}").status_code, 200)
            response = self.cards(state)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json["cards"]), count)
            self.assertTrue(all(card["status"] == "NOT_STARTED" for card in response.json["cards"]))
            self.assertFalse((self.store.folder(state["id"]) / "generations").exists())
            self.assertEqual(self.client.get(f"/api/sessions/{state['id']}").json["state"]["id"], state["id"])
        self.assertIn(b'enter-generate', self.client.get('/prepare/new').data)
        self.assertEqual(self.requests, [])

    def test_confirmed_version_and_target_checked_before_paid_attempt(self):
        target = web.reference_ids(self.state)[0]
        self.assertEqual(self.post(target, {**self.state, "revision": 0}).status_code, 409)
        self.assertEqual(self.post("reference_999").status_code, 404)
        changed = self.store.load(self.state["id"])
        changed["confirmed"] = False
        self.store.save(changed, {"action": "fixture_unconfirm"})
        self.assertEqual(self.post(target, changed).status_code, 409)
        self.assertFalse((self.store.folder(changed["id"]) / "generations").exists())

    def test_target_request_evidence_output_and_refresh_match(self):
        target = web.reference_ids(self.state)[1]
        with self.with_sdk():
            response = self.post(target)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(self.requests), 1)
        body = self.requests[0].read()
        self.assertEqual(body.count(b'name="image[]"'), 3)
        self.assertIn(b'filename="reference_002.png"', body)
        self.assertNotIn(b'filename="reference_001.png"', body)
        self.assertNotIn(b'DO_NOT_SEND_OTHER_IMAGE_HISTORY', body)
        for ref in ["reference_001", "reference_003"]:
            self.assertNotIn(f"仅 {ref} 的计划".encode(), body)
        self.assertIn(self.state["inputs"]["listing"].encode(), body)
        self.assertIn(self.state["inputs"]["description"].encode(), body)
        self.assertIn(self.state["inputs"]["requirements"].encode(), body)
        self.assertIn(b'name="quality"\r\n\r\nlow', body)
        cards = self.cards().json["cards"]
        card = next(card for card in cards if card["id"] == target)
        self.assertEqual(card["status"], "SUCCEEDED")
        self.assertTrue(card["image_is_latest"])
        with self.client.get(card["image_url"]) as image_response:
            self.assertEqual(image_response.status_code, 200)
            self.assertEqual(image_response.data, png((1024, 1536)))
        service = self.app.extensions["generation_service"]
        folder = service.run_folder(self.state["id"], self.state["revision"], target, response.json["run_id"])
        record = web.read_json(folder / "run.json")
        self.assertEqual(record["request_id"], "req_offline_generation")
        self.assertEqual(record["usage"]["total_tokens"], 30)
        self.assertEqual(web.read_json(folder / "plan.json")["confirmed_plan"], self.state["plans"][target])
        request = web.read_json(folder / "request.json")
        self.assertEqual([image["id"] for image in request["image_order"]], ["product_001", "product_002", target])
        self.assertEqual(request["prompt"], (folder / "prompt.txt").read_text())
        for image in request["image_order"]:
            self.assertEqual(hashlib.sha256((folder / image["file"]).read_bytes()).hexdigest(), image["sha256"])
        restarted = web.create_app(self.runtime).test_client()
        self.assertEqual(self.cards(client=restarted).json["cards"], cards)
        for path, data in self.original.items():
            self.assertEqual(path.read_bytes(), data)

    def test_failure_keeps_other_card_and_same_card_last_success(self):
        first, second = web.reference_ids(self.state)[:2]
        with self.with_sdk():
            self.assertEqual(self.post(first).status_code, 200)
        initial = self.cards().json["cards"][0]
        original_runs = {p: p.read_bytes() for p in (self.store.folder(self.state["id"]) / "generations").rglob("*") if p.is_file() and p.name != "current.json"}
        key = os.environ["OPENAI_API_KEY"]
        with self.with_sdk(lambda request: httpx.Response(429, json={"error": {"message": "Rejected " + key, "type": "rate_limit_error"}})):
            self.assertEqual(self.post(second).status_code, 502)
            self.assertEqual(self.post(first).status_code, 502)
        self.assertEqual(len(self.requests), 3)  # one success plus two explicit attempts, no retry
        cards = self.cards().json["cards"]
        self.assertEqual(cards[0]["status"], "FAILED")
        self.assertEqual(cards[0]["image_url"], initial["image_url"])
        self.assertFalse(cards[0]["image_is_latest"])
        self.assertIsNone(cards[1]["image_url"])
        for path, data in original_runs.items():
            self.assertEqual(path.read_bytes(), data)
        for path in (self.store.folder(self.state["id"]) / "generations").rglob("*.json"):
            self.assertNotIn(key, path.read_text())

    def test_missing_key_does_not_construct_client(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = self.post(web.reference_ids(self.state)[0])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.requests, [])
        run = next((self.store.folder(self.state["id"]) / "generations").glob("*/*/runs/*/run.json"))
        self.assertFalse(web.read_json(run)["api_call_attempted"])

    def test_repeated_click_rejected_but_other_card_remains_independent(self):
        service = self.app.extensions["generation_service"]
        first, second = web.reference_ids(self.state)[:2]
        entered, release = threading.Event(), threading.Event()
        result = []

        def handler(request):
            if b'filename="reference_001.png"' in request.read():
                entered.set()
                release.wait(timeout=5)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png((1024, 1536))).decode()}]})

        with self.with_sdk(handler):
            thread = threading.Thread(target=lambda: result.append(self.app.test_client().post(f"/api/sessions/{self.state['id']}/generate/{first}", json={"confirmed_revision": self.state["revision"]}, headers=HEADERS)))
            thread.start()
            self.assertTrue(entered.wait(timeout=5))
            try:
                self.assertEqual(self.cards().json["cards"][0]["status"], "RUNNING")
                self.assertEqual(self.post(first).status_code, 409)
                self.assertEqual(self.post(second).status_code, 200)
            finally:
                release.set()
                thread.join(timeout=5)
        self.assertEqual(result[0].status_code, 200)
        self.assertEqual(len(self.requests), 2)
        self.assertFalse(service.active)

    def test_invalid_returned_image_is_failed_and_retained(self):
        with self.with_sdk(lambda request: httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"invalid image").decode()}]})):
            response = self.post(web.reference_ids(self.state)[0])
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(self.cards().json["cards"][0]["image_url"])
        folder = next((self.store.folder(self.state["id"]) / "generations").glob("*/*/runs/*"))
        self.assertEqual((folder / "image.png").read_bytes(), b"invalid image")
        self.assertTrue((folder / "response.json").exists())

    def test_new_confirmation_does_not_relabel_old_generation(self):
        target = web.reference_ids(self.state)[0]
        with self.with_sdk():
            self.assertEqual(self.post(target).status_code, 200)
        old = self.cards().json["cards"][0]
        changed = self.store.load(self.state["id"])
        changed["plans"][target]["design"] = "新确认版本"
        self.store.save(changed, {"action": "fixture_reconfirm"})
        new = self.cards(changed).json["cards"][0]
        self.assertEqual(new["status"], "NOT_STARTED")
        self.assertIsNone(new["image_url"])
        with self.client.get(old["image_url"]) as response:
            self.assertEqual(response.status_code, 200)

    def test_service_restart_does_not_retry_unfinished_run(self):
        service = self.app.extensions["generation_service"]
        target = web.reference_ids(self.state)[0]
        run_id = "20261014T000000Z-" + "a" * 32
        folder = service.run_folder(self.state["id"], self.state["revision"], target, run_id)
        folder.mkdir(parents=True)
        web.write_json(folder / "run.json", {"status": "RUNNING"})
        pointer = folder.parent.parent / "current.json"
        web.write_json(pointer, {"latest_run": run_id, "last_successful_run": None})
        before = (folder / "run.json").read_bytes()
        restarted = web.create_app(self.runtime).test_client()
        self.assertEqual(self.cards(client=restarted).json["cards"][0]["status"], "INTERRUPTED")
        self.assertEqual((folder / "run.json").read_bytes(), before)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
