"""C3 Images transport and CLI compatibility, entirely offline/anonymous."""

import base64
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import APIStatusError, OpenAI
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from infrastructure import openai_images as images
import generate_image as t01



def cli_fingerprints():
    """Anonymous legacy fixtures; record kwargs, saved bytes and write sequence."""
    import test_generate_image as t01_fixture
    import test_quick_redesign as quick_fixture
    result = {}
    for kind in ("t01", "quick"):
        for scenario in ("local", "success", "failure", "missing_key"):
            fx = (t01_fixture.GenerationSafetyTests() if kind == "t01"
                  else quick_fixture.QuickRedesignTests())
            fx.setUp()
            try:
                module = t01_fixture.generator if kind == "t01" else quick_fixture.experiment
                root = fx.root if kind == "t01" else Path(fx.temp.name)
                requests, writes = [], []
                original_open = Path.open
                original_writer = module.write_json if kind == "t01" else module.save_json
                def track_open(path, mode="r", *args, **kwargs):
                    if path.is_relative_to(root) and any(flag in mode for flag in ("w", "a", "x", "+")):
                        writes.append(["open", str(path.relative_to(root)), mode])
                    return original_open(path, mode, *args, **kwargs)
                def track_write(path, value, *args):
                    writes.append(["json", str(path.relative_to(root)), copy.deepcopy(value)])
                    return original_writer(path, value, *args)
                def edit(**kwargs):
                    requests.append(copy.deepcopy(kwargs))
                    if scenario == "failure":
                        raise ValueError("anonymous model response failure")
                    image = io.BytesIO()
                    Image.new("RGB", (1024, 1536), "pink").save(image, "PNG")
                    data = image.getvalue()
                    raw = {"data": [{"b64_json": base64.b64encode(data).decode()}],
                           "usage": {"input_tokens": 7, "output_tokens": 11, "total_tokens": 18}}
                    return SimpleNamespace(data=[SimpleNamespace(b64_json=raw["data"][0]["b64_json"])],
                                           _request_id="req_anonymous", model_dump=lambda mode: copy.deepcopy(raw))
                @contextmanager
                def client_factory(key):
                    yield SimpleNamespace(images=SimpleNamespace(edit=edit))
                writer_name = "write_json" if kind == "t01" else "save_json"
                with patch.object(module, "datetime", SimpleNamespace(now=lambda tz: datetime(2026, 10, 22, tzinfo=timezone.utc))), \
                        patch.object(module, "uuid4", return_value=SimpleNamespace(hex="a" * 32)), \
                        patch.object(module, "now", return_value="2026-10-22T00:00:00+00:00"), \
                        patch.object(module, "time", SimpleNamespace(perf_counter=lambda: 1.0)), \
                        patch.object(module, "version", return_value="offline-sdk"), \
                        patch.object(module, "make_client", side_effect=client_factory), \
                        patch.object(module, writer_name, side_effect=track_write), \
                        patch.object(Path, "open", track_open), \
                        patch.dict(os.environ, {"OPENAI_API_KEY": "" if scenario == "missing_key" else "opaque-cli-canary"}):
                    if kind == "t01":
                        _, record = fx.run_case(paid=scenario != "local")
                    else:
                        _, record = fx.run_sample(paid=scenario != "local", requirements="requirements.md",
                                                  facts="facts.md", reference="design.png")
                expected = {"local": "LOCAL_CHECK_ONLY", "success": "API_IMAGE_SAVED_AWAITING_REVIEW",
                            "failure": "FAILED", "missing_key": "LOCAL_CHECK_FAILED"}[scenario]
                assert record["status"] == expected, record
                assert len(requests) == int(scenario in ("success", "failure"))
                files = {}
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        data = path.read_bytes()
                        files[str(path.relative_to(root))] = data.decode("utf-8") if path.suffix in (".json", ".txt", ".md") else data
                def encode(value):
                    if isinstance(value, bytes):
                        return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
                    raise TypeError(type(value).__name__)
                payload = json.dumps({"record": record, "requests": requests, "writes": writes, "files": files},
                                     ensure_ascii=False, sort_keys=True, default=encode).replace(str(root), "<ROOT>")
                for entry in (t01_fixture.generator, quick_fixture.experiment):
                    path = Path(entry.__file__)
                    payload = payload.replace(hashlib.sha256(path.read_bytes()).hexdigest(), "<ENTRY_HASH:" + path.name + ">")
                result[kind + "_" + scenario] = hashlib.sha256(payload.encode()).hexdigest()
            finally:
                fx.tearDown()
                fx.doCleanups()
    return result


CLI_BEFORE = {
    "t01_local": "9f6bf32028a413de16e067db5b9b3f79576189bcc03bd05829248883e2245a20",
    "t01_success": "b65ee7a4e4fb23abb42519081e69b3e79d15ab63a01a690426244108f14c34c0",
    "t01_failure": "f12c35c5414ce1034a5eb0df9653bdd421ecf0504db6ae2d1ded0077b196dec9",
    "t01_missing_key": "cf4480fd9fa3871f5b625dcc420af1f640e9ce38643db87a1f901576983439ec",
    "quick_local": "8dd52510a7e31f454a3ec2a2f2dab1331feb76c2fc10669a494cfde2e5bf3856",
    "quick_success": "5103d7093de29bb27d78b4cae805771e1d519a8685f969ef8d9f3911dbbff832",
    "quick_failure": "2997812122970948772b96366bce6d15faffa66e3a29c69177bb2c45561ca19d",
    "quick_missing_key": "ddb09907b166f5b409cece33eba121205f99eeb92911d5dcf15cb84e16f6d5c8"
}

class ImageCapabilitiesTests(unittest.TestCase):
    def test_images_policy_values_are_unchanged_and_shared_without_copying(self):
        import generate_plan_image as generation
        import quick_redesign as quick
        self.assertEqual(images.MODELS, ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare"))
        self.assertEqual(images.PARAMETERS, {"n": 1, "quality": "low", "size": "1024x1536", "output_format": "png"})
        self.assertEqual(images.TIMEOUT_SECONDS, 180.0)
        for module in (t01, quick, generation):
            self.assertIs(module.MODELS, images.MODELS)
            self.assertIs(module.PARAMETERS, images.PARAMETERS)
            self.assertEqual(module.TIMEOUT_SECONDS, images.TIMEOUT_SECONDS)
        self.assertIs(generation.make_client, images.make_client)
        self.assertIs(quick.make_client, images.make_client)

    def test_client_constructs_once_with_exact_official_configuration(self):
        with patch.object(images, "OpenAI", return_value="client") as constructor:
            self.assertEqual(images.make_client("opaque"), "client")
        constructor.assert_called_once_with(api_key="opaque", base_url="https://api.openai.com/v1",
                                            max_retries=0, timeout=180.0)

    def test_t01_entry_retains_sdk_and_timeout_late_binding(self):
        with patch.object(t01, "OpenAI", return_value="legacy-client") as constructor, \
                patch.object(t01, "TIMEOUT_SECONDS", 13.5):
            self.assertEqual(t01.make_client("opaque"), "legacy-client")
        constructor.assert_called_once_with(api_key="opaque", base_url="https://api.openai.com/v1",
                                            max_retries=0, timeout=13.5)
        self.assertEqual(images.TIMEOUT_SECONDS, 180.0)

    def test_factory_error_identity_is_not_caught_or_retried(self):
        failure = RuntimeError("anonymous constructor error")
        for module in (images, t01):
            with self.subTest(module=module.__name__), \
                    patch.object(module, "OpenAI", side_effect=failure) as constructor:
                with self.assertRaises(RuntimeError) as caught:
                    module.make_client("opaque")
                self.assertIs(caught.exception, failure)
                self.assertEqual(constructor.call_count, 1)

    def test_callers_keep_local_model_parameter_and_factory_override_seams(self):
        import test_generate_image as t01_fixtures
        import test_quick_redesign as quick_fixtures
        import generate_plan_image as generation
        parameters = {**images.PARAMETERS, "quality": "medium"}
        models = ("anonymous-offline-model",)
        for kind, module, fixtures in (("t01", t01, t01_fixtures.GenerationSafetyTests),
                                        ("quick", quick_fixtures.experiment, quick_fixtures.QuickRedesignTests)):
            fx = fixtures()
            fx.setUp()
            try:
                with patch.object(module, "MODELS", models), patch.object(module, "PARAMETERS", parameters), \
                        patch.object(module, "TIMEOUT_SECONDS", 13.5), \
                        patch.object(module, "make_client", side_effect=AssertionError("Local check must not construct client")):
                    path, record = fx.run_case() if kind == "t01" else fx.run_sample(model=models[0])
                self.assertEqual(record["status"], "LOCAL_CHECK_ONLY")
                self.assertEqual(record["model"], models[0])
                self.assertEqual(record["parameters"], parameters)
                self.assertEqual(record["timeout_seconds"], 13.5)
                self.assertEqual(json.loads((path.parent / "request.json").read_text())["quality"], "medium")
            finally:
                fx.tearDown()
                fx.doCleanups()
        with patch.object(generation, "MODELS", models), patch.object(generation, "PARAMETERS", parameters), \
                patch.object(generation, "TIMEOUT_SECONDS", 13.5), \
                patch.object(generation, "make_client") as factory, \
                patch.object(generation, "execute_generation", return_value="record") as execute:
            result = generation.GenerationService(SimpleNamespace())._generate({"id": "a" * 32, "revision": 1}, "reference_001")
            self.assertEqual(result, "record")
            self.assertIs(execute.call_args.kwargs["io"].client_factory, factory)
            self.assertIs(execute.call_args.kwargs["models"], models)
            self.assertIs(execute.call_args.kwargs["defaults"], parameters)
            self.assertEqual(execute.call_args.kwargs["timeout_seconds"], 13.5)

    def test_actual_sdk_serialization_and_zero_retry_match_old_entry(self):
        captured = []
        constructors = []
        status = 200
        def transport(request):
            content_type = request.headers["content-type"]
            message = BytesParser().parsebytes(("Content-Type: " + content_type + "\r\n\r\n").encode() + request.read())
            captured.append({"url": str(request.url), "method": request.method,
                "parts": [(part.get_param("name", header="content-disposition"), part.get_filename(),
                           part.get_content_type(), part.get_payload(decode=True))
                          for part in message.get_payload()]})
            if status != 200:
                return httpx.Response(429, json={"error": {"message": "anonymous rejection", "type": "rate_limit"}})
            return httpx.Response(200, json={"created": 1, "data": [{"b64_json": "Ynl0ZXM="}]})
        def factory(**kwargs):
            constructors.append(kwargs)
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        for status in (200, 429):
            for module in (images, t01):
                with patch.object(module, "OpenAI", side_effect=factory):
                    with module.make_client("opaque") as client:
                        kwargs = {"model": images.MODELS[0], "prompt": "anonymous prompt",
                                  "image": [("original.png", b"anonymous bytes", "image/png")], **images.PARAMETERS}
                        if status == 200:
                            client.images.edit(**kwargs)
                        else:
                            with self.assertRaises(APIStatusError):
                                client.images.edit(**kwargs)
        self.assertEqual(len(captured), 4)  # Four explicit calls, never an SDK retry.
        self.assertTrue(all(request == captured[0] for request in captured))
        self.assertEqual(constructors, [{"api_key": "opaque", "base_url": "https://api.openai.com/v1",
                                        "max_retries": 0, "timeout": 180.0}] * 4)

    def test_cli_requests_saved_files_and_write_order_match_pre_migration(self):
        self.assertEqual(cli_fingerprints(), CLI_BEFORE)

    def test_transport_import_does_not_load_images_business_web_or_cli(self):
        script = r"""
import importlib, importlib.abc, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
blocked={'generate_image','quick_redesign','generate_plan_image','prepare_plan','image_review','image_workflow','flask','PIL'}
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, name, *args):
  if name.split('.')[0] in blocked:
   raise AssertionError('Forbidden Images dependency: '+name)
sys.meta_path.insert(0,Block())
module=importlib.import_module('infrastructure.openai_images')
with patch.object(module,'OpenAI',return_value='client') as factory:
 assert module.make_client('opaque')=='client'
 assert factory.call_count==1
assert not any(name.split('.')[0] in blocked for name in sys.modules)
print('isolated transport PASS')
"""
        result = subprocess.run([sys.executable, "-B", "-c", script, str(Path(images.__file__).resolve().parents[1])],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("isolated transport PASS", result.stdout)

    def test_both_original_cli_help_entrypoints_stay_available(self):
        for name in ("generate_image.py", "quick_redesign.py"):
            result = subprocess.run([sys.executable, "-B", str(Path(t01.__file__).with_name(name)), "--help"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--run-paid", result.stdout)
            self.assertIn(images.MODELS[0], result.stdout)


if __name__ == "__main__":
    unittest.main()
