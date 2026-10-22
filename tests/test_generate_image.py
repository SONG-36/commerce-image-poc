"""Offline safety checks. Mock transport results are NOT real model evidence."""

import base64
import hashlib
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
from cli import generate_image as generator


class GenerationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / "inputs" / "case-001"
        for folder in ["product", "references"]:
            (self.case / folder).mkdir(parents=True)
        for i in range(1, 4):
            Image.new("RGB", (16, 16), "white").save(self.case / f"product/product_{i:02}.jpg")
        for i in range(1, 5):
            Image.new("RGB", (16, 24), "pink").save(self.case / f"references/ref_{i:02}.webp")
        (self.case / "listing.md").write_text("電動ドライバー。数値は未確認。", encoding="utf-8")
        (self.case / "requirements.md").write_text("白色、淡粉、杂志风。", encoding="utf-8")
        self.original = {str(p): p.read_bytes() for p in self.case.rglob("*") if p.is_file()}
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "sk-local-test-secret-do-not-save"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.requests = []

    def tearDown(self):
        for name, content in self.original.items():
            self.assertEqual(Path(name).read_bytes(), content, name)

    def run_case(self, paid=False):
        return generator.run(self.case, "ref_01.webp", generator.MODELS[0], paid, self.root)

    def client(self, handler):
        def transport(request):
            self.requests.append(request)
            self.assertEqual(str(request.url), "https://api.openai.com/v1/images/edits")
            self.assertEqual(request.method, "POST")
            return handler(request)
        return OpenAI(
            api_key=os.environ["OPENAI_API_KEY"], base_url="https://api.openai.com/v1",
            max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(transport)),
        )

    def response(self, data=None):
        if data is None:
            image = io.BytesIO()
            Image.new("RGB", (1024, 1536), "pink").save(image, format="PNG")
            data = image.getvalue()
        return {"created": 1, "data": [{"b64_json": base64.b64encode(data).decode()}],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}}

    def test_local_check_never_constructs_api_client_and_reads_all_inputs(self):
        with patch.object(generator, "make_client", side_effect=AssertionError("Network forbidden")):
            path, record = self.run_case()
        self.assertEqual(record["status"], "LOCAL_CHECK_ONLY")
        self.assertFalse(record["api_call_attempted"])
        self.assertEqual(record["outputs"], [])
        self.assertEqual(len(record["inputs"]), 9)
        self.assertEqual(sum(x["selected_for_request"] for x in record["inputs"]), 6)
        request = json.loads((path.parent / "request.json").read_text())
        self.assertEqual(request["image_order"], ["product_01.jpg", "product_02.jpg", "product_03.jpg", "ref_01.webp"])
        self.assertFalse((self.root / "outputs").exists())

    def test_paid_flag_without_key_does_not_construct_api_client(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch.object(generator, "make_client", side_effect=AssertionError("Network forbidden")):
            _, record = self.run_case(paid=True)
        self.assertEqual(record["status"], "LOCAL_CHECK_FAILED")
        self.assertFalse(record["api_call_attempted"])

    def test_sdk_multipart_output_evidence_and_unique_runs(self):
        def handler(request):
            body = request.read()
            self.assertEqual(body.count(b'name="image[]"'), 4)
            self.assertIn(b'filename="ref_01.webp"', body)
            self.assertNotIn(b'filename="ref_02.webp"', body)
            for field, value in [("n", "1"), ("quality", "low"), ("size", "1024x1536"), ("output_format", "png")]:
                self.assertIn(f'name="{field}"\r\n\r\n{value}'.encode(), body)
            return httpx.Response(200, json=self.response(), headers={"x-request-id": "req_offline_test"})
        with patch.object(generator, "make_client", side_effect=lambda _: self.client(handler)):
            first_path, first = self.run_case(paid=True)
            first_files = {p: p.read_bytes() for p in first_path.parent.iterdir()}
            first_image = Path(first["outputs"][0]["path"])
            image_bytes = first_image.read_bytes()
            second_path, second = self.run_case(paid=True)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(first["status"], "API_IMAGE_SAVED_AWAITING_REVIEW")
        self.assertEqual(first["operator_review"], "NOT_REVIEWED")
        self.assertEqual(first["request_id"], "req_offline_test")
        self.assertEqual(first["usage"]["total_tokens"], 30)
        self.assertEqual(first["outputs"][0]["sha256"], hashlib.sha256(image_bytes).hexdigest())
        self.assertNotEqual(first_path, second_path)
        self.assertNotEqual(first["outputs"][0]["path"], second["outputs"][0]["path"])
        self.assertEqual(first_image.read_bytes(), image_bytes)
        for path, content in first_files.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertTrue((first_path.parent / "response.json").is_file())

    def test_429_is_not_retried_and_error_key_is_redacted(self):
        key = os.environ["OPENAI_API_KEY"]
        def handler(request):
            return httpx.Response(429, json={"error": {"message": f"Rejected {key}", "type": "rate_limit_error", "code": "rate_limit"}}, headers={"x-request-id": "req_rejected"})
        with patch.object(generator, "make_client", side_effect=lambda _: self.client(handler)):
            path, record = self.run_case(paid=True)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(record["status"], "FAILED")
        self.assertEqual(record["request_id"], "req_rejected")
        self.assertEqual(record["error"]["status_code"], 429)
        self.assertEqual(record["outputs"], [])
        for file in path.parent.iterdir():
            self.assertNotIn(key, file.read_text())
        self.assertIn("[REDACTED]", (path.parent / "error.json").read_text())

    def test_bad_base64_retains_response_without_claiming_success(self):
        def handler(request):
            return httpx.Response(200, json={"data": [{"b64_json": "not base64!"}]})
        with patch.object(generator, "make_client", side_effect=lambda _: self.client(handler)):
            path, record = self.run_case(paid=True)
        self.assertEqual(record["status"], "FAILED")
        self.assertTrue((path.parent / "response.json").exists())
        self.assertEqual(record["outputs"], [])

    def test_invalid_image_bytes_are_retained_as_failed_output(self):
        with patch.object(generator, "make_client", side_effect=lambda _: self.client(lambda request: httpx.Response(200, json=self.response(b"invalid PNG")))):
            _, record = self.run_case(paid=True)
        self.assertEqual(record["status"], "FAILED")
        self.assertFalse(record["outputs"][0]["validated"])
        self.assertEqual(Path(record["outputs"][0]["path"]).read_bytes(), b"invalid PNG")

    def test_missing_reference_stops_before_api_call(self):
        original_read = Path.read_bytes

        def read_bytes(path):
            if path.name == "ref_04.webp":
                raise FileNotFoundError(str(path))
            return original_read(path)

        with patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes), patch.object(generator, "make_client", side_effect=AssertionError("Network forbidden")):
            _, record = self.run_case(paid=True)
        self.assertEqual(record["status"], "LOCAL_CHECK_FAILED")
        self.assertFalse(record["api_call_attempted"])
        self.assertIn("ref_04.webp", record["error"]["message"])


if __name__ == "__main__":
    unittest.main()
