"""Pure request-builder checks plus pre-refactor SDK/Evidence fingerprints.

Characterization uses anonymous temporary fixtures and MockTransport only.
The golden values cover requests, stable evidence bytes and write order, not
AI semantics. Dynamic IDs/times are checked by the existing boundary fixture.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import test_prepare_plan as fixtures
import test_t02_image_boundaries as boundaries


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def capture_characterization():
    cases = {}
    for model in fixtures.web.MODELS:
        fx = boundaries.T02ImageBoundaryTests()
        fx.setUp()
        try:
            with patch.dict(os.environ, {"OPENAI_PLANNING_MODEL": model}):
                state = fx.state
                operations = [
                    ("understand", None, "", fx.initial_result()),
                    ("product", None, "PRODUCT_CORRECTION",
                     {"product": fx.marked(fixtures.web.PRODUCT_FIELDS, "corrected-product")}),
                    ("reference", "reference_001", "REFERENCE_CORRECTION",
                     {"reference": fx.marked(fixtures.web.REFERENCE_FIELDS, "corrected-reference")}),
                    ("plan", "reference_001", "PLAN_FEEDBACK",
                     {"plan": fx.marked(fixtures.web.PLAN_FIELDS, "corrected-plan")}),
                    ("replan", None, "", {"plans": fx.initial_result()["plans"]}),
                ]
                for action, target, feedback, result in operations:
                    writes, wire = [], []
                    original_json = fixtures.web.write_json
                    original_text = Path.write_text
                    original_result_for = fx.fx.result_for

                    def relative(path):
                        name = str(path.relative_to(fx.folder))
                        return re.sub(r"^calls/[0-9a-f]{32}/", "calls/<CALL>/", name)

                    def trace_json(path, value, exclusive=False):
                        metadata = value if isinstance(value, dict) else {}
                        writes.append([relative(path), metadata.get("status"),
                                       metadata.get("api_call_attempted"), exclusive])
                        return original_json(path, value, exclusive=exclusive)

                    def trace_text(path, text, *args, **kwargs):
                        if path.name == "prompt.txt":
                            writes.append([relative(path), None, None, False])
                        return original_text(path, text, *args, **kwargs)

                    def trace_request(request):
                        wire.append(hashlib.sha256(request.read()).hexdigest())
                        return original_result_for(request)

                    with patch.object(fixtures.web, "write_json", side_effect=trace_json), \
                            patch.object(Path, "write_text", new=trace_text), \
                            patch.object(fx.fx, "result_for", side_effect=trace_request):
                        state, request, call = fx.send(state, action, result, target, feedback)
                    record = fixtures.web.read_json(call / "run.json")
                    fx.assertEqual(record["source_sha256"], hashlib.sha256(Path(fixtures.web.__file__).read_bytes()).hexdigest())
                    stable = {name: hashlib.sha256((call / name).read_bytes()).hexdigest()
                              for name in ("request.json", "prompt.txt", "image_order.json", "response.json", "result.json")}
                    cases[f"{model}/{action}"] = digest({"wire": wire, "request": request,
                        "evidence": stable, "writes": writes, "parameters": record["parameters"]})
        finally:
            fx.doCleanups()
    return cases


# Recorded from the unmodified call_ai() with the pinned SDK and anonymous fixtures.
GOLDEN = {
    "gpt-4.1-mini-2025-04-14/plan": "27e87188b9be084b0c053a0bb590ef86a802e7ff539780024256051b2a012af4",
    "gpt-4.1-mini-2025-04-14/product": "431b98559f9e3307c1f8131983950560e771fc83c3e20c4eaaa55d31099adf59",
    "gpt-4.1-mini-2025-04-14/reference": "bed364edf6cd67861be71703f8acfce43b3c95af2ae793a0f566ef36c474ec9d",
    "gpt-4.1-mini-2025-04-14/replan": "c6a177a2f9eaeb8e5fbda78f591b372d4a6b0c947b34a524731e2304430ea6aa",
    "gpt-4.1-mini-2025-04-14/understand": "94ee9fdceb4ffe782dfc395106aae3cea30f6690134e5cbc1d151bc291346d1d",
    "gpt-4.1-mini/plan": "3e161faa82e4572946e2a70df813e57d8f0cd31d7395c569ac41ae9b0b51a114",
    "gpt-4.1-mini/product": "b8c346198cd945b104ae67d92bb03ce96333d46094a541d155539c11b0b91015",
    "gpt-4.1-mini/reference": "28c25665f68f874b287dd64b17b9270568ea9ff5fdba5b6068d6f926d3815797",
    "gpt-4.1-mini/replan": "8706e9692fcb05e13ab64f45d92e5511bdab69159a9541201891d8b14e05737c",
    "gpt-4.1-mini/understand": "18368bda21af006449589fee8c58b5532a9a0912a80f71d99015eeda2790859a",
    "gpt-5.4-mini/plan": "67f714ce4dde198d0fbd8083288f50a5b351d758ccc18a320b3ea6d4cd1f9cd7",
    "gpt-5.4-mini/product": "9c806b67f40d939c4011ef1a6ca10d437eb2f1a5e3f65258fcf0f3292e3f63cc",
    "gpt-5.4-mini/reference": "0552a545942b5f822aae4286055cd4abae5208b1dda0f71b7814378ff53b860d",
    "gpt-5.4-mini/replan": "9e8a2b5137f5f78c4a0c34e19bec85af29c3b545fe1089d3bd66785fcc06a9ce",
    "gpt-5.4-mini/understand": "939641a3276a8105953c4f597fab025036c242d8777579b8418c0e3b2f5ea563"
}


class T02RequestConstructionTests(unittest.TestCase):
    def anonymous_inputs(self):
        state = {"inputs": {"listing": "source L", "description": "source D", "requirements": "source R"},
                 "product": {"identity": "candidate P"}, "references": {"reference_001": {"style": "candidate R"}},
                 "plans": {"reference_001": {"goal": "candidate plan"}},
                 "corrections": {"product": [], "references": {}}, "images": []}
        images = {}
        for role in ("product", "reference"):
            identity = role + "_001"
            raw = fixtures.picture()
            state["images"].append({"id": identity, "role": role, "name": "shared.png",
                                    "file": "inputs/" + identity + ".png", "mime": "image/png",
                                    "sha256": hashlib.sha256(raw).hexdigest()})
            images["inputs/" + identity + ".png"] = raw
        return state, images

    def test_builder_has_no_io_environment_dependency_or_input_mutation(self):
        state, images = self.anonymous_inputs()
        before = copy.deepcopy((state, images))
        rules, models = fixtures.web.RULES, fixtures.web.MODELS
        block = AssertionError("Pure construction must not perform external I/O")
        with patch("builtins.open", side_effect=block), \
                patch.object(Path, "read_bytes", side_effect=block), \
                patch.object(fixtures.web, "write_json", side_effect=block), \
                patch.object(fixtures.web, "OpenAI", side_effect=block), \
                patch.object(os, "environ", {}):
            for model in models:
                for action in ("understand", "product", "reference", "plan", "replan"):
                    target = "reference_001" if action in ("reference", "plan") else None
                    arguments, order = fixtures.web.build_planning_request(
                        state, action, target, "feedback", model, images)
                    self.assertEqual(arguments["model"], model)
                    self.assertEqual(arguments["instructions"], rules)
                    self.assertEqual(arguments["max_output_tokens"], 6000 if action in ("understand", "replan") else 2500)
                    self.assertEqual(arguments.get("reasoning"), {"effort": "low"} if model == models[0] else None)
                    order[0]["name"] = "changed output only"
        self.assertEqual((state, images), before)
        self.assertEqual((fixtures.web.RULES, fixtures.web.MODELS), (rules, models))

    def test_builder_only_requires_selected_bytes_and_never_reads_unused_files(self):
        state, images = self.anonymous_inputs()
        with patch.object(Path, "read_bytes", side_effect=AssertionError("No file reads")):
            arguments, order = fixtures.web.build_planning_request(
                state, "product", None, "", "gpt-4.1-mini", {"inputs/product_001.png": images["inputs/product_001.png"]})
        self.assertEqual([image["id"] for image in order], ["product_001"])
        self.assertEqual(sum(part["type"] == "input_image" for part in arguments["input"][0]["content"]), 1)
        with self.assertRaises(KeyError):
            fixtures.web.build_planning_request(state, "reference", "reference_001", "", "gpt-4.1-mini", {})

    def test_characterized_sdk_requests_evidence_and_write_order_are_unchanged(self):
        self.assertEqual(capture_characterization(), GOLDEN)


if __name__ == "__main__":
    unittest.main()
