"""Anonymous T02 transport/application regressions, not visual-quality assertions.

All assets live in the existing temporary test store. Opaque response markers
test Image ID association; no historical model answer is a semantic oracle.
"""

import base64
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

import test_prepare_plan as fixtures


class T02ImageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.PreparePlanTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.addCleanup(self.fx.tearDown)
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.texts = {"listing": "Anonymous listing L; claims unverified",
                      "description": "Anonymous description D", "requirements": "Anonymous design requirement R"}
        self.uploaded = {}
        data = {"title": "Anonymous identity regression", **self.texts}
        for role, count in (("product", 3), ("reference", 4)):
            files = []
            for index in range(1, count + 1):
                stream = io.BytesIO()
                color = (30 * (len(self.uploaded) + 1), 80, 150)
                Image.new("RGB", (24, 32), color).save(stream, "PNG")
                raw = stream.getvalue()
                self.uploaded[f"{role}_{index:03}"] = raw
                # Repeated names must not determine image identity or role.
                files.append((io.BytesIO(raw), "shared.png"))
            data[role] = files
        response = self.fx.client.post("/api/sessions", data=data, headers=fixtures.HEADERS)
        self.assertEqual(response.status_code, 200)
        self.state = response.json["state"]
        self.folder = self.fx.runtime / "sessions" / self.state["id"]
        self.ids = [f"reference_{index:03}" for index in range(1, 5)]

    def marked(self, names, identity):
        return {name: f"opaque:{identity}:{name}" for name in names}

    def initial_result(self):
        web = fixtures.web
        # Deliberately reverse JSON key order: application must map by ID.
        return {"product": self.marked(web.PRODUCT_FIELDS, "product"),
                "references": {key: self.marked(web.REFERENCE_FIELDS, key) for key in reversed(self.ids)},
                "plans": {key: self.marked(web.PLAN_FIELDS, key) for key in reversed(self.ids)}}

    def send(self, state, action, result, target=None, feedback=""):
        parent = self.folder / "versions" / f"{state['revision']:06}.json"
        parent_bytes = parent.read_bytes()

        def reply(body, unused):
            return httpx.Response(200, json={"id": "resp_boundary_mock", "status": "completed",
                "model": body["model"], "output": [{"type": "message", "id": "msg_boundary",
                "role": "assistant", "content": [{"type": "output_text",
                "text": json.dumps(copy.deepcopy(result)), "annotations": []}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}},
                headers={"x-request-id": "req_boundary_mock"})

        with self.fx.with_ai(reply):
            response = self.fx.action(state, action, target, feedback)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        after = response.json["state"]
        event = after["events"][-1]
        call = self.folder / "calls" / event["call_id"]
        record = fixtures.web.read_json(call / "run.json")
        applied = fixtures.web.read_json(call / "applied.json")
        saved = fixtures.web.read_json(self.folder / "versions" / f"{after['revision']:06}.json")
        self.assertEqual(parent.read_bytes(), parent_bytes)
        self.assertEqual(after["revision"], state["revision"] + 1)
        self.assertEqual((event["target"], event["action"], event["after"]), (target, action, result))
        self.assertEqual(record["session_id"], state["id"])
        self.assertEqual((record["target"], record["parent_revision"]), (target, state["revision"]))
        self.assertEqual(record["parent_version_file"], f"versions/{state['revision']:06}.json")
        self.assertEqual(applied["run_id"], event["call_id"])
        self.assertEqual((applied["parent_revision"], applied["revision"]), (state["revision"], after["revision"]))
        self.assertEqual(applied["version_file"], f"versions/{after['revision']:06}.json")
        self.assertEqual(fixtures.web.read_json(call / "result.json"), result)
        for group in ("product", "references", "plans"):
            self.assertEqual(saved[group], after[group])
        request = self.fx.requests[-1]
        self.assertEqual(fixtures.web.read_json(call / "request.json"), request)
        return after, request, call

    def assert_images(self, request, call, expected_ids):
        content = request["input"][0]["content"]
        self.assertEqual([part["type"] for part in content],
                         ["input_text"] + [kind for _ in expected_ids for kind in ("input_text", "input_image")])
        order = fixtures.web.read_json(call / "image_order.json")
        self.assertEqual([image["id"] for image in order], expected_ids)
        for slot, image in enumerate(order, 1):
            identity = image["id"]
            role = identity.split("_")[0]
            meaning = "商品外观依据" if role == "product" else "仅设计参考"
            self.assertEqual(content[2 * slot - 1]["text"], f"{identity}：{meaning}（shared.png）")
            part = content[2 * slot]
            header, encoded = part["image_url"].split(",", 1)
            self.assertEqual((image["slot"], image["role"], part["detail"]), (slot, role, "auto"))
            self.assertEqual(header, "data:image/png;base64")
            raw = base64.b64decode(encoded, validate=True)
            self.assertEqual(raw, self.uploaded[identity])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), image["sha256"])
            self.assertEqual((self.folder / image["file"]).read_bytes(), raw)

    def test_understand_preserves_image_roles_bytes_and_id_keyed_results(self):
        result = self.initial_result()
        state, request, call = self.send(self.state, "understand", result)
        self.assert_images(request, call, list(self.uploaded))
        context = json.loads(request["input"][0]["content"][0]["text"])
        self.assertEqual(context["original_inputs"], self.texts)
        self.assertEqual(context["required_reference_ids"], self.ids)
        self.assertIsNone(context["current"]["product"])
        self.assertEqual(context["current"]["references"], {})
        self.assertEqual(context["current"]["plans"], {})
        for identity in self.ids:
            self.assertEqual(state["references"][identity], result["references"][identity])
            self.assertEqual(state["plans"][identity], result["plans"][identity])

    def test_reference_correction_is_scoped_to_target_context_and_snapshot(self):
        state, _, _ = self.send(self.state, "understand", self.initial_result())
        other_result = {"reference": self.marked(fixtures.web.REFERENCE_FIELDS, "other-correction")}
        state, _, _ = self.send(state, "reference", other_result, "reference_002", "OTHER_ONLY_MARKER")
        result = {"reference": self.marked(fixtures.web.REFERENCE_FIELDS, "target-correction")}
        after, request, call = self.send(state, "reference", result, "reference_001", "TARGET_MARKER")
        self.assert_images(request, call, ["product_001", "product_002", "product_003", "reference_001"])
        context = json.loads(request["input"][0]["content"][0]["text"])
        self.assertEqual(context["target"], "reference_001")
        self.assertEqual(context["operator_feedback"], "TARGET_MARKER")
        self.assertEqual(context["current"]["reference"], state["references"]["reference_001"])
        self.assertEqual(context["current"]["plan"], state["plans"]["reference_001"])
        self.assertEqual(context["current"]["corrections"]["references"], {"reference_001": []})
        self.assertNotIn("OTHER_ONLY_MARKER", json.dumps(context))
        self.assertEqual(after["references"]["reference_001"], result["reference"])
        for identity in self.ids[1:]:
            self.assertEqual(after["references"][identity], state["references"][identity])
        self.assertEqual(after["plans"], state["plans"])
        self.assertEqual(after["product"], state["product"])

    def test_plan_uses_corrected_understanding_and_updates_only_target(self):
        state, _, _ = self.send(self.state, "understand", self.initial_result())
        product = {"product": self.marked(fixtures.web.PRODUCT_FIELDS, "corrected-product")}
        state, _, _ = self.send(state, "product", product, feedback="PRODUCT_CORRECTION")
        reference = {"reference": self.marked(fixtures.web.REFERENCE_FIELDS, "corrected-reference")}
        state, _, _ = self.send(state, "reference", reference, "reference_001", "REFERENCE_CORRECTION")
        result = {"plan": self.marked(fixtures.web.PLAN_FIELDS, "target-plan")}
        after, request, call = self.send(state, "plan", result, "reference_001", "PLAN_FEEDBACK")
        self.assert_images(request, call, ["product_001", "product_002", "product_003", "reference_001"])
        context = json.loads(request["input"][0]["content"][0]["text"])
        self.assertEqual(context["original_inputs"], self.texts)
        self.assertEqual(context["current"]["product"], product["product"])
        self.assertEqual(context["current"]["reference"], reference["reference"])
        self.assertEqual(context["current"]["plan"], state["plans"]["reference_001"])
        self.assertEqual(context["current"]["corrections"],
                         {"product": ["PRODUCT_CORRECTION"], "references": {"reference_001": ["REFERENCE_CORRECTION"]}})
        self.assertEqual(context["operator_feedback"], "PLAN_FEEDBACK")
        self.assertEqual(after["plans"]["reference_001"], result["plan"])
        for identity in self.ids[1:]:
            self.assertEqual(after["plans"][identity], state["plans"][identity])
        self.assertEqual(after["product"], state["product"])
        self.assertEqual(after["references"], state["references"])

    def test_unknown_response_image_id_is_not_applied_to_any_snapshot(self):
        before = {p: p.read_bytes() for p in [self.folder / "state.json", *self.folder.glob("versions/*.json")]}
        for group in ("references", "plans"):
            with self.subTest(group=group):
                bad = self.initial_result()
                bad[group]["reference_999"] = bad[group].pop("reference_001")
                calls_before = set(self.folder.glob("calls/*"))

                def reply(body, unused):
                    return httpx.Response(200, json={"id": "resp_invalid_mock", "status": "completed",
                        "output": [{"type": "message", "role": "assistant", "content": [
                            {"type": "output_text", "text": json.dumps(bad), "annotations": []}]}]})

                with self.fx.with_ai(reply):
                    response = self.fx.action(self.state, "understand")
                self.assertEqual(response.status_code, 502)
                for path, raw in before.items():
                    self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(set(self.folder.glob("versions/*.json")), set(before) - {self.folder / "state.json"})
                call, = set(self.folder.glob("calls/*")) - calls_before
                self.assertEqual(fixtures.web.read_json(call / "run.json")["status"], "FAILED")
                self.assertTrue((call / "response.json").is_file())
                self.assertFalse((call / "applied.json").exists())

    def test_changed_image_bytes_stop_before_client_construction(self):
        image = next(item for item in self.state["images"] if item["id"] == "reference_001")
        (self.folder / image["file"]).write_bytes(self.uploaded["reference_002"])
        before = (self.folder / "state.json").read_bytes()
        with self.fx.with_ai() as factory:
            response = self.fx.action(self.state, "understand")
        self.assertEqual(response.status_code, 400)
        factory.assert_not_called()
        self.assertEqual(self.fx.requests, [])
        self.assertEqual((self.folder / "state.json").read_bytes(), before)
        call, = self.folder.glob("calls/*")
        record = fixtures.web.read_json(call / "run.json")
        self.assertEqual(record["status"], "FAILED")
        self.assertFalse(record["api_call_attempted"])
        self.assertFalse((call / "applied.json").exists())


if __name__ == "__main__":
    unittest.main()
