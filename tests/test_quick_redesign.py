"""I01 free offline tests. Synthetic fixtures and MockTransport are not real experiments."""

import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cli import quick_redesign as experiment


def png(color, size=(32, 48)):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, "PNG")
    return stream.getvalue()


class QuickRedesignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.inputs, self.runtime = root / "inputs", root / "runtime"
        self.inputs.mkdir()
        for name, color in [("sample_01.png", "pink"), ("sample_02.png", "blue"), ("design.png", "white")]:
            (self.inputs / name).write_bytes(png(color))
        (self.inputs / "requirements.md").write_text("商业信息图，保留原文字与卖点，不使用白底主图模式。")
        (self.inputs / "facts.md").write_text("运营提供商品依据，未经程序核实，不添加新参数。")
        self.original = {p: p.read_bytes() for p in self.inputs.iterdir()}
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "sk-i01-offline-test-secret", "OPENAI_IMAGE_MODEL": experiment.MODELS[0]})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.network = patch.object(experiment, "make_client", side_effect=AssertionError("Real network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.requests = []

    def tearDown(self):
        for path, data in self.original.items():
            self.assertEqual(path.read_bytes(), data)

    def run_sample(self, **kwargs):
        return experiment.run(self.inputs, "sample_01.png", runtime_dir=self.runtime, **kwargs)

    def with_sdk(self, failure=False, invalid_image=False, reference=False):
        def transport(request):
            self.requests.append(request)
            self.assertEqual(str(request.url), "https://api.openai.com/v1/images/edits")
            self.assertEqual(request.method, "POST")
            body = request.read()
            self.assertEqual(body.count(b'name="image[]"'), 2 if reference else 1)
            self.assertIn(b'filename="original.png"', body)
            self.assertNotIn(self.original[self.inputs / "sample_02.png"], body)
            for name, value in experiment.PARAMETERS.items():
                self.assertIn(f'name="{name}"\r\n\r\n{value}'.encode(), body)
            if failure:
                return httpx.Response(429, json={"error": {"message": "Rejected " + os.environ["OPENAI_API_KEY"],
                                                         "type": "rate_limit_error"}})
            data = png("pink", (128, 128) if invalid_image else (1024, 1536))
            return httpx.Response(200, headers={"x-request-id": "req_i01_offline_only"},
                json={"created": 1, "data": [{"b64_json": base64.b64encode(data).decode()}],
                      "usage": {"total_tokens": 30}})
        def factory(_key):
            return OpenAI(api_key=_key, max_retries=0,
                          http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        return patch.object(experiment, "make_client", side_effect=factory)

    def test_default_check_saves_request_without_client_or_output(self):
        path, run = self.run_sample(requirements="requirements.md", facts="facts.md")
        self.assertEqual(run["status"], "LOCAL_CHECK_ONLY")
        self.assertTrue(run["request_ready"])
        self.assertFalse(run["api_call_attempted"])
        self.assertEqual(run["model"], experiment.MODELS[0])
        self.assertEqual(run["outputs"], [])
        self.assertFalse((self.runtime / "outputs").exists())
        request = json.loads((path.parent / "request.json").read_text())
        self.assertEqual([x["role"] for x in request["image_order"]], ["original"])
        self.assertEqual(request["prompt"], (path.parent / "prompt.txt").read_text())
        self.assertIn(self.original[self.inputs / "requirements.md"].decode(), request["prompt"])
        self.assertEqual((path.parent / "inputs/original.png").read_bytes(), self.original[self.inputs / "sample_01.png"])

    def test_missing_materials_save_failure_without_request_or_client(self):
        path, run = experiment.run(self.inputs / "missing", "sample.png", runtime_dir=self.runtime)
        self.assertEqual(run["status"], "LOCAL_CHECK_FAILED")
        self.assertFalse(run["request_ready"])
        self.assertFalse(run["api_call_attempted"])
        self.assertTrue((path.parent / "error.json").is_file())
        self.assertFalse((path.parent / "request.json").exists())

    def test_paid_flag_without_key_never_creates_client(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            _, run = self.run_sample(paid=True)
        self.assertEqual(run["status"], "LOCAL_CHECK_FAILED")
        self.assertTrue(run["request_ready"])
        self.assertFalse(run["api_call_attempted"])

    def test_sdk_single_image_and_unique_runs_preserve_history(self):
        with self.with_sdk():
            first_path, first = self.run_sample(paid=True)
            saved = {p: p.read_bytes() for p in first_path.parent.rglob('*') if p.is_file()}
            output = Path(first["outputs"][0]["path"])
            original_output = output.read_bytes()
            second_path, _ = self.run_sample(paid=True)
        self.assertEqual(len(self.requests), 2)  # Two explicit experiments, one call each.
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first["status"], "API_IMAGE_SAVED_AWAITING_REVIEW")
        self.assertEqual(first["operator_review"], "PENDING")
        self.assertEqual(first["request_id"], "req_i01_offline_only")
        response = json.loads((first_path.parent / "response.json").read_text())
        self.assertEqual(first["usage"], response["usage"])
        self.assertEqual(first["usage"]["total_tokens"], 30)
        self.assertIsNone(first["usage"]["input_tokens"])
        self.assertEqual(output.read_bytes(), original_output)
        for p, data in saved.items():
            self.assertEqual(p.read_bytes(), data)
        review = json.loads((first_path.parent / "review.json").read_text())
        self.assertIsNone(review["decision"])
        self.assertIsNone(review["actual_cost"])
        self.assertEqual(set(review["dimensions"]), set(experiment.DIMENSIONS))

    def test_optional_design_reference_is_second_image_only(self):
        with self.with_sdk(reference=True):
            path, run = self.run_sample(paid=True, reference="design.png")
        self.assertEqual(run["status"], "API_IMAGE_SAVED_AWAITING_REVIEW")
        order = json.loads((path.parent / "request.json").read_text())["image_order"]
        self.assertEqual([(x["slot"], x["role"]) for x in order], [(1, "original"), (2, "design_reference")])
        self.assertEqual(order[1]["sha256"], experiment.sha256(self.original[self.inputs / "design.png"]))

    def test_api_failure_not_retried_and_secret_not_saved(self):
        with self.with_sdk(failure=True):
            path, run = self.run_sample(paid=True)
        self.assertEqual(run["status"], "FAILED")
        self.assertTrue(run["api_call_attempted"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(run["error"]["status_code"], 429)
        for p in path.parent.glob("*.json"):
            self.assertNotIn(os.environ["OPENAI_API_KEY"], p.read_text())

    def test_invalid_returned_image_preserves_bytes_and_response(self):
        with self.with_sdk(invalid_image=True):
            path, run = self.run_sample(paid=True)
        self.assertEqual(run["status"], "FAILED")
        self.assertFalse(run["outputs"][0]["validated"])
        self.assertEqual(Path(run["outputs"][0]["path"]).read_bytes(), png("pink", (128, 128)))
        self.assertTrue((path.parent / "response.json").is_file())
        self.assertFalse((path.parent / "review.json").exists())

    def test_input_paths_and_unknown_model_fail_before_client(self):
        (self.inputs / "linked.png").symlink_to(self.inputs / "sample_01.png")
        for name in ["../outside.png", "linked.png", ".env"]:
            with self.subTest(image=name):
                _, run = experiment.run(self.inputs, name, paid=True, runtime_dir=self.runtime)
                self.assertEqual(run["status"], "LOCAL_CHECK_FAILED")
                self.assertFalse(run["api_call_attempted"])
        _, run = self.run_sample(model="unconfirmed-model", paid=True)
        self.assertFalse(run["api_call_attempted"])

    def test_credential_text_is_rejected_before_snapshot_or_request(self):
        (self.inputs / "secret.txt").write_text("Credential: " + os.environ["OPENAI_API_KEY"])
        path, run = self.run_sample(requirements="secret.txt", paid=True)
        self.assertEqual(run["status"], "LOCAL_CHECK_FAILED")
        self.assertFalse(run["api_call_attempted"])
        self.assertFalse((path.parent / "request.json").exists())
        for p in path.parent.rglob('*'):
            if p.is_file():
                self.assertNotIn(os.environ["OPENAI_API_KEY"].encode(), p.read_bytes())


if __name__ == "__main__":
    unittest.main()
