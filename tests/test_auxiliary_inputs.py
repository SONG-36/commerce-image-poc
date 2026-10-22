"""C5 auxiliary input policy regressions; anonymous in-memory images only."""

import copy
import hashlib
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from image_workflow.generation import auxiliary
import evidence
import image_review as legacy


# Captured from the actual pre-C5 auxiliary_prompt, before moving the policy.
PROMPT_BEFORE = {
    "product_appearance:1": "f9dfb0ee163bdf8bbe036e362a16ca7685a3dbde56f0ef570450d1c15f16cb43",
    "product_appearance:5": "5d783cc952b0f74cc447ab0279fd3b461c2681a809eca36590e44ed2580a9d94",
    "product_appearance:12": "3de62f300da4b8c956c081b0e1ea01208d31379a69e22dae1334f908f5777c60",
    "design_style:1": "c2fd50d488fd06de71d29b8340daf58feac26e104089fafd7c282909f68e973d",
    "design_style:5": "29852f67ca6eeee52ae1ab7174549858b363d2c0953686f39f4aac2ddc285827",
    "design_style:12": "a604c3f0980324b08d609f6d9712906c974cd9db77701b006e7be4e92e839e01",
    "local_content:1": "ae3016b85efae0ebac0039e53c89f8da6708225484e03d5f66ba981fa770386a",
    "local_content:5": "4e3d65a94ec52c93da21c2b4dec70e5867185b682c481820e388e2aaacd05b1b",
    "local_content:12": "740e42b984ed42e5f0f643779021290219477512310d063ff2fe47f2011400fa"
}


def picture(format="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", (17, 23), "blue").save(stream, format)
    return stream.getvalue()


class AuxiliaryInputTests(unittest.TestCase):
    def test_all_formats_and_purposes_keep_original_bytes_identity_and_metadata(self):
        with patch.dict("os.environ", {}, clear=True):
            for format, extension, mime in (("JPEG", "jpg", "image/jpeg"),
                                            ("PNG", "png", "image/png"),
                                            ("WEBP", "webp", "image/webp")):
                data = picture(format)
                for purpose, label in auxiliary.AUXILIARY_PURPOSES.items():
                    expected = {
                        "name": "匿名图.bin", "data": data, "file": f"inputs/auxiliary_reference.{extension}",
                        "mime": mime, "role": "auxiliary_reference", "purpose": purpose, "purpose_label": label,
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                        "width": 17, "height": 23, "scope": "current_image_only"}
                    for module in (auxiliary, legacy):
                        with self.subTest(format=format, purpose=purpose, entry=module.__name__):
                            result = module.prepare_auxiliary("../匿名图.bin", data, purpose)
                            self.assertEqual(result, expected)
                            self.assertIs(result["data"], data)

    def test_purpose_size_and_private_checks_keep_original_error_precedence(self):
        for module in (auxiliary, legacy):
            with self.subTest(entry=module.__name__):
                with self.assertRaisesRegex(ValueError, "请选择辅助图片用途"):
                    module.prepare_auxiliary("x", b"", "unknown")
                with self.assertRaisesRegex(ValueError, "不能为空"):
                    module.prepare_auxiliary("x", b"", "design_style")
                with self.assertRaisesRegex(ValueError, "认证信息"):
                    module.prepare_auxiliary("x", b"sk-anonymous-fixture-canary", "design_style")
                with self.assertRaisesRegex(ValueError, "请选择辅助图片用途"):
                    module.prepare_auxiliary("x", None, "unknown")

    def test_size_boundary_is_inclusive_and_legacy_limit_override_remains_effective(self):
        data = picture()
        with patch.object(legacy, "MAX_AUXILIARY_BYTES", len(data)):
            self.assertEqual(legacy.prepare_auxiliary("x", data, "local_content")["data"], data)
        with patch.object(legacy, "MAX_AUXILIARY_BYTES", len(data) - 1), \
                patch.object(legacy, "contains_private", side_effect=AssertionError("Must reject size first")):
            with self.assertRaisesRegex(ValueError, "不能超过 20 MB"):
                legacy.prepare_auxiliary("x", data, "local_content")
        self.assertEqual(auxiliary.MAX_AUXILIARY_BYTES, 20 * 1024 * 1024)

    def test_corrupt_and_unsupported_images_keep_validation_error_and_cause(self):
        for data in (b"not an image", picture("GIF"), picture("BMP")):
            for module in (auxiliary, legacy):
                with self.subTest(entry=module.__name__, bytes=len(data)):
                    with self.assertRaisesRegex(ValueError, "有效的 JPG、PNG 或 WebP") as caught:
                        module.prepare_auxiliary("x", data, "local_content")
                    self.assertIsInstance(caught.exception.__cause__, Exception)

    def test_decoder_errors_are_wrapped_but_private_check_errors_still_propagate(self):
        failure = RuntimeError("anonymous decoder error")
        with patch.object(legacy, "Image", SimpleNamespace(open=Mock(side_effect=failure))):
            with self.assertRaisesRegex(ValueError, "辅助图片无法读取") as caught:
                legacy.prepare_auxiliary("x", picture(), "design_style")
        self.assertIs(caught.exception.__cause__, failure)
        with patch.object(legacy, "contains_private", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                legacy.prepare_auxiliary("x", picture(), "design_style")
        self.assertIs(caught.exception, failure)

    def test_filename_sanitization_and_environment_filter_remain_late_bound(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "opaque-anonymous-canary"}, clear=True):
            for module in (auxiliary, legacy):
                result = module.prepare_auxiliary("../opaque-anonymous-canary.png", picture(), "design_style")
                self.assertEqual(result["name"], "[REDACTED].png")
        with patch.object(evidence, "safe_text", return_value="legacy-label") as sanitize:
            result = legacy.prepare_auxiliary("x.png", picture(), "local_content")
            self.assertEqual(result["name"], "legacy-label")
            sanitize.assert_called_once_with("x.png")
        name = "名" * 260 + ".png"
        self.assertEqual(legacy.prepare_auxiliary(name, picture(), "local_content")["name"], "名" * 255)

    def test_legacy_policy_hash_and_privacy_replacements_remain_effective(self):
        with patch.object(legacy, "AUXILIARY_PURPOSES", {"local_content": "匿名角色"}), \
                patch.object(legacy, "sha256", return_value="overridden") as digest, \
                patch.object(legacy, "contains_private", return_value=False) as private:
            data = picture()
            record = legacy.prepare_auxiliary("x.png", data, "local_content")
            self.assertEqual(record["purpose_label"], "匿名角色")
            self.assertEqual(record["sha256"], "overridden")
            digest.assert_called_once_with(data)
            private.assert_called_once_with(data.decode("utf-8", errors="ignore"))
            with self.assertRaisesRegex(ValueError, "请选择辅助图片用途"):
                legacy.prepare_auxiliary("x.png", data, "design_style")

    def test_prompt_bytes_match_nine_pre_migration_cases_without_mutation(self):
        for purpose, label in auxiliary.AUXILIARY_PURPOSES.items():
            reference = {"purpose": purpose, "purpose_label": label}
            before = copy.deepcopy(reference)
            for slot in (1, 5, 12):
                for module in (auxiliary, legacy):
                    digest = hashlib.sha256(module.auxiliary_prompt(reference, slot).encode()).hexdigest()
                    self.assertEqual(digest, PROMPT_BEFORE[f"{purpose}:{slot}"])
            self.assertEqual(reference, before)
        for module in (auxiliary, legacy):
            with self.assertRaises(KeyError):
                module.auxiliary_prompt({"purpose": "unknown", "purpose_label": "未知"}, 1)

    def test_policy_import_and_execution_do_not_load_review_web_sdk_or_cli(self):
        script = r"""
import importlib.abc,io,sys
from pathlib import Path
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'openai','flask','prepare_plan','generate_plan_image','image_review','generate_image','quick_redesign','evidence','experiment_export','api'} or name.startswith(('image_workflow.review','image_workflow.tasks')):
   raise AssertionError('Forbidden Generation input dependency: '+name)
sys.meta_path.insert(0,Block())
def guard(event,args):
 if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
  raise AssertionError('Network forbidden')
sys.addaudithook(guard)
sys.path.insert(0,sys.argv[1])
from image_workflow.generation import auxiliary
from PIL import Image
stream=io.BytesIO()
Image.new('RGB',(2,3),'blue').save(stream,'PNG')
data=stream.getvalue()
result=auxiliary.prepare_auxiliary('anonymous.png',data,'design_style')
assert result['data'] is data and result['scope']=='current_image_only'
assert '辅助输入' in auxiliary.auxiliary_prompt(result,2)
"""
        result = subprocess.run([sys.executable, "-B", "-c", script,
                                 str(Path(__file__).resolve().parents[1] / "src")],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
