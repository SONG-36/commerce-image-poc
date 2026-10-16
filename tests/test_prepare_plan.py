"""Offline tests only. SDK MockTransport is not evidence of real AI quality."""

import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI as OfficialClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import prepare_plan as web

HEADERS = {"X-Local-Action": "prepare-plan"}


def picture():
    output = io.BytesIO()
    Image.new("RGB", (24, 32), "pink").save(output, "PNG")
    return output.getvalue()


class PreparePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.runtime = root / "prepare-plan"
        self.case = root / "case-001"
        for role, count in [("product", 2), ("references", 3)]:
            (self.case / role).mkdir(parents=True)
            for index in range(count):
                (self.case / role / f"image-{index}.png").write_bytes(picture())
        (self.case / "listing.md").write_text("电动工具，Listing 声称具备冲击功能，尚未核实。", encoding="utf-8")
        (self.case / "requirements.md").write_text("白色和浅粉色，杂志风。", encoding="utf-8")
        self.original = {p: p.read_bytes() for p in self.case.rglob("*") if p.is_file()}
        self.app = web.create_app(self.runtime, self.case)
        self.client = self.app.test_client()
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "sk-only-offline-testing-secret", "OPENAI_PLANNING_MODEL": "gpt-4.1-mini"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.no_network = patch.object(web, "OpenAI", side_effect=AssertionError("Actual network forbidden"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)
        self.requests = []

    def tearDown(self):
        for path, content in self.original.items():
            self.assertEqual(path.read_bytes(), content)

    def load_case(self):
        result = self.client.post("/api/case-001", headers=HEADERS)
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return result.json["state"]

    def action(self, state, action, target=None, feedback=""):
        return self.client.post(f"/api/sessions/{state['id']}/action", json={"action": action, "revision": state["revision"], "target": target, "feedback": feedback}, headers=HEADERS)

    def result_for(self, request):
        body = json.loads(request.read())
        self.requests.append(body)
        self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
        self.assertFalse(body["store"])
        self.assertEqual(body["text"]["format"]["type"], "json_object")
        content = body["input"][0]["content"]
        context = json.loads(content[0]["text"])
        result = copy.deepcopy(context["return_json"])

        def replace(value):
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            return "离线测试候选内容（未经核验）"

        result = replace(result)
        if "product" in result:
            result["product"]["identity"] = "普通电动螺丝刀；不强调冲击功能" if "修正" in context["task"] else "电动工具候选理解"
        if "reference" in result:
            result["reference"]["applicable"] = "只借鉴排版，不参考使用场景"
        if "plan" in result:
            result["plan"]["design"] = context["operator_feedback"]
        return body, result

    def sdk(self, handler=None):
        def respond(request):
            body, result = self.result_for(request)
            if handler:
                return handler(body, result)
            return httpx.Response(200, json={"id": "resp_offline_test", "object": "response", "created_at": 1,
                "model": body["model"], "status": "completed", "output": [{"type": "message", "id": "msg_test", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": json.dumps(result), "annotations": []}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}}, headers={"x-request-id": "req_offline_test"})
        return OfficialClient(api_key=os.environ["OPENAI_API_KEY"], max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

    def with_ai(self, handler=None):
        return patch.object(web, "OpenAI", side_effect=lambda **kwargs: self.sdk(handler))

    def initial(self):
        state = self.load_case()
        with self.with_ai():
            response = self.action(state, "understand")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json["state"]

    def test_page_case_loading_and_refresh_never_call_ai(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIsNone(self.client.get("/api/current").json["state"])
        state = self.load_case()
        self.assertEqual(len(state["images"]), 5)
        self.assertEqual(sum(image["role"] == "reference" for image in state["images"]), 3)
        for image in state["images"]:
            with self.client.get(image["url"]) as response:
                self.assertEqual(response.status_code, 200)
        restarted = web.create_app(self.runtime, self.case).test_client()
        self.assertEqual(restarted.get("/api/current").json["state"], state)
        self.assertEqual(self.requests, [])

    def test_upload_dynamic_images_and_new_session_preserve_previous(self):
        previous = self.load_case()
        previous_bytes = (self.runtime / "sessions" / previous["id"] / "state.json").read_bytes()
        for count in [1, 5]:
            files = [(io.BytesIO(picture()), f"ref-{i}.png") for i in range(count)]
            response = self.client.post("/api/sessions", data={"product": (io.BytesIO(picture()), "sku.png"), "reference": files, "listing": "新商品", "description": "运营提供信息", "requirements": "浅粉色背景"}, headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            state = response.json["state"]
            self.assertEqual(len(web.reference_ids(state)), count)
            self.assertEqual(state["inputs"]["description"], "运营提供信息")
        self.assertEqual((self.runtime / "sessions" / previous["id"] / "state.json").read_bytes(), previous_bytes)

    def test_real_sdk_serialization_initial_understanding_and_n_plans(self):
        state = self.initial()
        self.assertEqual(set(state["references"]), set(web.reference_ids(state)))
        self.assertEqual(set(state["plans"]), set(web.reference_ids(state)))
        request = self.requests[0]
        images = [item for item in request["input"][0]["content"] if item["type"] == "input_image"]
        self.assertEqual(len(images), 5)
        self.assertTrue(all(item["image_url"].startswith("data:image/png;base64,") for item in images))
        self.assertIn("未经核实", request["instructions"])
        evidence = next((self.runtime / "sessions" / state["id"] / "calls").iterdir())
        self.assertEqual(web.read_json(evidence / "request.json"), request)
        self.assertEqual(web.read_json(evidence / "run.json")["request_id"], "req_offline_test")
        self.assertEqual(len(web.read_json(evidence / "image_order.json")), 5)

    def test_planning_default_and_fallbacks_preserve_inputs_and_record_parameters(self):
        baseline = None
        for configured in [None, *web.MODELS]:
            with self.subTest(configured=configured), patch.dict(os.environ):
                if configured is None:
                    os.environ.pop("OPENAI_PLANNING_MODEL", None)
                else:
                    os.environ["OPENAI_PLANNING_MODEL"] = configured
                state = self.initial()
                request = self.requests[-1]
                expected = configured or web.MODELS[0]
                self.assertEqual(request["model"], expected)
                if expected == web.MODELS[0]:
                    self.assertEqual(request["reasoning"], {"effort": "low"})
                else:
                    self.assertNotIn("reasoning", request)
                self.assertNotIn("temperature", request)
                self.assertNotIn("top_p", request)
                self.assertEqual(request["max_output_tokens"], 6000)
                self.assertEqual(request["text"], {"format": {"type": "json_object"}})
                if baseline is None:
                    baseline = request["input"]
                self.assertEqual(request["input"], baseline)
                evidence = next((self.runtime / "sessions" / state["id"] / "calls").iterdir())
                run = web.read_json(evidence / "run.json")
                self.assertEqual(run["model"], expected)
                self.assertEqual(run["returned_model"], expected)
                self.assertEqual(web.read_json(evidence / "request.json"), request)
                target = web.reference_ids(state)[0]
                with self.with_ai():
                    response = self.action(state, "plan", target, "仅修改背景配色")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.requests[-1]["max_output_tokens"], 2500)
                self.assertEqual(len([part for part in self.requests[-1]["input"][0]["content"] if part["type"] == "input_image"]), 3)

    def test_unknown_planning_model_is_rejected_before_api(self):
        state = self.load_case()
        with patch.dict(os.environ, {"OPENAI_PLANNING_MODEL": "not-a-supported-model"}):
            response = self.action(state, "understand")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.requests, [])
        run = next((self.runtime / "sessions" / state["id"]).glob("calls/*/run.json"))
        self.assertFalse(web.read_json(run)["api_call_attempted"])
        self.assertEqual(self.client.get("/api/current").json["state"], state)

    def test_corrections_targeted_plan_history_confirmation_and_restart(self):
        state = self.initial()
        first_plans = copy.deepcopy(state["plans"])
        folder = self.runtime / "sessions" / state["id"]
        original_versions = {p: p.read_bytes() for p in (folder / "versions").iterdir()}
        target, other = web.reference_ids(state)[:2]
        with self.with_ai():
            response = self.action(state, "product", feedback="这不是冲击电钻，不要强调冲击功能。")
            self.assertEqual(response.status_code, 200)
            state = response.json["state"]
            self.assertEqual(state["plans"], first_plans)
            self.assertEqual(len(state["stale_plans"]), 3)
            response = self.action(state, "reference", target, "只参考排版，不参考使用场景。")
            self.assertEqual(response.status_code, 200)
            state = response.json["state"]
            other_plan = copy.deepcopy(state["plans"][other])
            response = self.action(state, "plan", target, "不要展示配件，采用浅粉色背景。")
            self.assertEqual(response.status_code, 200)
            state = response.json["state"]
            self.assertEqual(state["plans"][other], other_plan)
            self.assertNotEqual(state["plans"][target], first_plans[target])
            self.assertNotIn(target, state["stale_plans"])
            context = json.loads(self.requests[-1]["input"][0]["content"][0]["text"])
            self.assertIn("不强调冲击", context["current"]["product"]["identity"])
            self.assertEqual(context["current"]["reference"]["applicable"], "只借鉴排版，不参考使用场景")
            self.assertEqual(context["current"]["plan"], first_plans[target])
            self.assertIn("不是冲击", context["current"]["corrections"]["product"][0])
            self.assertEqual(len([item for item in self.requests[-1]["input"][0]["content"] if item["type"] == "input_image"]), 3)
            calls = len(self.requests)
            self.assertEqual(self.action(state, "confirm").status_code, 400)
            self.assertEqual(len(self.requests), calls)
            response = self.action(state, "replan")
            self.assertEqual(response.status_code, 200)
            state = response.json["state"]
        self.assertEqual(state["stale_plans"], [])
        for image_id in web.reference_ids(state):
            confirmation = self.action(state, "confirm", image_id)
            self.assertEqual(confirmation.status_code, 200)
            state = confirmation.json["state"]
        self.assertTrue(state["confirmed"])
        restarted = web.create_app(self.runtime, self.case).test_client().get("/api/current").json["state"]
        self.assertEqual(restarted, state)
        event = next(event for event in state["events"] if event["action"] == "plan")
        self.assertEqual(event["before"], first_plans[target])
        self.assertIn("浅粉色", event["feedback"])
        for path, data in original_versions.items():
            self.assertEqual(path.read_bytes(), data)

    def test_missing_key_refuses_request_and_preserves_state(self):
        state = self.load_case()
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = self.action(state, "understand")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get("/api/current").json["state"], state)
        run_path = next((self.runtime / "sessions" / state["id"]).glob("calls/*/run.json"))
        self.assertFalse(web.read_json(run_path)["api_call_attempted"])

    def test_429_not_retried_and_secret_not_saved_or_returned(self):
        state = self.load_case()
        key = os.environ["OPENAI_API_KEY"]
        with self.with_ai(lambda body, result: httpx.Response(429, json={"error": {"message": "Rejected " + key, "type": "rate_limit_error"}})):
            response = self.action(state, "understand")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn(key, response.get_data(as_text=True))
        for path in (self.runtime / "sessions" / state["id"]).glob("calls/*/*"):
            self.assertNotIn(key, path.read_text())
        self.assertEqual(self.client.get("/api/current").json["state"], state)

    def test_bad_plan_count_preserves_existing_plan(self):
        state = self.initial()
        def bad_count(body, result):
            result["plans"] = {}
            return httpx.Response(200, json={"id": "resp_invalid", "status": "completed", "output": [{"type": "message", "id": "msg_bad", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(result), "annotations": []}]}]})
        with self.with_ai(bad_count):
            response = self.action(state, "replan")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.get("/api/current").json["state"], state)

    def test_stale_revision_and_foreign_origin_block_before_api(self):
        state = self.load_case()
        response = self.action({**state, "revision": 0}, "understand")
        self.assertEqual(response.status_code, 409)
        response = self.client.post("/api/case-001", headers={**HEADERS, "Origin": "https://elsewhere.example"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/case-001")
        self.assertEqual(response.status_code, 403)

    def test_invalid_image_is_rejected_without_creating_session(self):
        response = self.client.post("/api/sessions", data={"product": (io.BytesIO(b"not an image"), "p.png"), "reference": (io.BytesIO(picture()), "r.png")}, headers=HEADERS)
        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.runtime / "current.json").exists())


if __name__ == "__main__":
    unittest.main()
