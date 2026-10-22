"""I01 experiment: one original image, no T02 planning, offline unless --run-paid."""

import argparse
import base64
from datetime import datetime, timezone
from importlib.metadata import version
import io
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

from PIL import Image

from generate_image import ROOT, write_json
from infrastructure.openai_images import MODELS, PARAMETERS, TIMEOUT_SECONDS, make_client
from evidence import clean_record, contains_private, safe_text
from file_ops import safe_path, sha256
from image_workflow.generation import quick_prompt as _quick_prompt
from image_workflow.generation.quick_prompt import DEFAULT_REQUIREMENTS, SIZES


EXPERIMENT = "i01-quick-redesign"
DIMENSIONS = ("Product Fidelity", "Information Fidelity", "Visual Quality", "Hallucination",
              "Revision Effort", "Cost & Latency")


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    write_json(path, clean_record(value), os.environ.get("OPENAI_API_KEY", ""))


def prepare_inputs(case_dir, image, requirements=None, facts=None, reference=None):
    """Read only explicitly selected files. No directory scanning or other samples."""
    if not case_dir.is_dir():
        raise ValueError("I01 测试资料目录不存在，请先准备真实业务图片。")
    manifest, images, texts, snapshots = [], [], {}, []
    for role, name in [("original", image), ("design_reference", reference),
                       ("requirements", requirements), ("product_facts", facts)]:
        if name is None:
            continue
        path = safe_path(case_dir, name)
        if any(part.startswith('.') for part in Path(name).parts):
            raise ValueError("不读取隐藏文件，请明确选择实验图片或资料文本。")
        data = path.read_bytes()
        if not data:
            raise ValueError(f"输入文件为空：{name}")
        entry = {"role": role, "source": str(path), "sha256": sha256(data), "bytes": len(data)}
        if role in ["original", "design_reference"]:
            if len(data) >= 50 * 1024 * 1024:
                raise ValueError("单张图片必须小于 50 MB。")
            with Image.open(io.BytesIO(data)) as picture:
                extension, mime = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"),
                                   "WEBP": ("webp", "image/webp")}[picture.format]
                entry.update(width=picture.width, height=picture.height, mime=mime)
                picture.verify()
            with Image.open(io.BytesIO(data)) as picture:
                picture.load()
            filename = f"{role}.{extension}"
            entry.update(file="inputs/" + filename, slot=len(images) + 1)
            images.append((filename, data, mime))
        else:
            if path.suffix.lower() not in [".md", ".txt"]:
                raise ValueError("运营要求与商品依据请使用 UTF-8 的 .md 或 .txt 文件。")
            text = data.decode("utf-8")
            if not text.strip() or contains_private(text):
                raise ValueError("资料文本为空或包含疑似密钥；已停止，不发送该文本。")
            texts[role] = text
            entry["file"] = f"inputs/{role}.md"
        manifest.append(entry)
        snapshots.append((entry["file"], data))
    if not images or manifest[0]["role"] != "original":
        raise ValueError("必须明确选择一张真实业务原图。")
    texts.setdefault("requirements", DEFAULT_REQUIREMENTS)
    texts.setdefault("product_facts", "未提供额外商品事实说明；不得据此补充或验证商品宣称。")
    return manifest, images, texts, snapshots


def build_prompt(texts, order):
    return _quick_prompt.build_prompt(texts, order)


def build_edit_prompt(texts, order, feedback):
    return _quick_prompt.build_edit_prompt(texts, order, feedback)


def run(case_dir, image, model=None, paid=False, requirements=None, facts=None, reference=None,
        runtime_dir=ROOT / ".runtime"):
    started = time.perf_counter()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex
    evidence = safe_path(Path(runtime_dir), f"evidence/{EXPERIMENT}/{run_id}")
    (evidence / "inputs").mkdir(parents=True, exist_ok=False)
    record = {"experiment_id": "I01", "run_id": run_id, "started_at": now(), "status": "PREPARING",
              "mode": "paid" if paid else "local_check", "model": model or os.environ.get("OPENAI_IMAGE_MODEL", MODELS[0]),
              "parameters": dict(PARAMETERS), "sdk_version": version("openai"),
              "source_sha256": sha256(Path(__file__).read_bytes()),
              "t01_source_sha256": sha256(Path(__file__).with_name("generate_image.py").read_bytes()),
              "endpoint": "https://api.openai.com/v1/images/edits", "timeout_seconds": TIMEOUT_SECONDS,
              "max_retries": 0, "api_call_attempted": False, "request_id": None, "usage": None,
              "actual_cost": None, "operator_review": "PENDING", "request_ready": False,
              "selected_files": {"case_dir": str(case_dir), "original": image,
                                 "requirements": requirements, "product_facts": facts, "design_reference": reference},
              "inputs": [], "outputs": [], "error": None}
    save_json(evidence / "run.json", record)
    try:
        if record["model"] not in MODELS:
            raise ValueError("图像模型不在现有 T01 允许列表内。")
        manifest, images, texts, snapshots = prepare_inputs(Path(case_dir), image, requirements, facts, reference)
        record["inputs"] = manifest
        for filename, data in snapshots:
            with (evidence / filename).open("xb") as stream:
                stream.write(data)
        order = [entry for entry in manifest if "slot" in entry]
        prompt = build_prompt(texts, order)
        request = {"model": record["model"], "prompt": prompt, **PARAMETERS, "image_order": order}
        record["requirements_source"] = "operator_file" if requirements else "experiment_default"
        record["prompt_sha256"] = sha256(prompt.encode())
        save_json(evidence / "context.json", {"texts": texts, "inputs": manifest,
                  "requirements_source": record["requirements_source"]})
        save_json(evidence / "request.json", request)
        (evidence / "prompt.txt").write_text(safe_text(prompt), encoding="utf-8")
        record["request_ready"] = True
        if not paid:
            record["status"] = "LOCAL_CHECK_ONLY"
        else:
            key = os.environ.get("OPENAI_API_KEY", "")
            if not key.strip():
                raise ValueError("OPENAI_API_KEY 未配置，本次没有调用模型。不要向聊天发送密钥。")
            record["status"] = "CALLING_API"
            with make_client(key) as client:
                record["api_call_attempted"] = True
                record["api_started_at"] = now()
                save_json(evidence / "run.json", record)
                api_started = time.perf_counter()
                try:
                    response = client.images.edit(model=record["model"], prompt=prompt, image=images, **PARAMETERS)
                finally:
                    record["api_elapsed_seconds"] = round(time.perf_counter() - api_started, 3)
            raw = response.model_dump(mode="json")
            record["request_id"] = response._request_id
            record["usage"] = raw.get("usage")
            record["returned_model"] = raw.get("model")
            save_json(evidence / "response.json", raw)
            if not response.data or len(response.data) != 1 or not response.data[0].b64_json:
                raise ValueError("接口未返回预期的一张 base64 图片，实际响应已保存。")
            data = base64.b64decode(response.data[0].b64_json, validate=True)
            output = safe_path(Path(runtime_dir), f"outputs/{EXPERIMENT}/{run_id}")
            output.mkdir(parents=True, exist_ok=False)
            path = output / "image.png"
            with path.open("xb") as stream:
                stream.write(data)
            record["outputs"].append({"path": str(path), "sha256": sha256(data), "bytes": len(data), "validated": False})
            with Image.open(io.BytesIO(data)) as picture:
                if picture.format != "PNG" or picture.size != tuple(map(int, PARAMETERS["size"].split("x"))):
                    raise ValueError("返回图片格式或尺寸不符，已保留返回字节。")
                picture.verify()
            with Image.open(io.BytesIO(data)) as picture:
                picture.load()
            record["outputs"][0]["validated"] = True
            record["status"] = "API_IMAGE_SAVED_AWAITING_REVIEW"
            save_json(evidence / "review.json", {"decision": None, "allowed_decisions": ["PASS", "MODIFY", "REJECT"],
                      "reason": None, "dimensions": {name: None for name in DIMENSIONS},
                      "actual_cost": None, "currency": None, "note": "待人工评价；usage 不等于实际账单费用。"})
    except (Exception, KeyboardInterrupt) as error:
        record["status"] = "FAILED" if record["api_call_attempted"] else "LOCAL_CHECK_FAILED"
        record["request_id"] = getattr(error, "request_id", None) or record["request_id"]
        record["error"] = {"type": type(error).__name__, "message": str(error),
                           "status_code": getattr(error, "status_code", None), "body": getattr(error, "body", None)}
        save_json(evidence / "error.json", record["error"])
    finally:
        record["finished_at"] = now()
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        save_json(evidence / "run.json", record)
    return evidence / "run.json", record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=ROOT / ".runtime/inputs" / EXPERIMENT)
    parser.add_argument("--image", required=True, help="本次唯一待重设计原图，相对于 case-dir。")
    parser.add_argument("--requirements", help="可选：UTF-8 运营要求 .md/.txt，相对于 case-dir。")
    parser.add_argument("--facts", help="可选：UTF-8 商品依据 .md/.txt，相对于 case-dir。")
    parser.add_argument("--reference", help="可选：一张仅用于设计的参考图，相对于 case-dir。")
    parser.add_argument("--model", choices=MODELS, default=os.environ.get("OPENAI_IMAGE_MODEL", MODELS[0]))
    parser.add_argument("--run-paid", action="store_true", help="仅在人工批准后：发送所选业务资料，执行一次付费调用。")
    args = parser.parse_args()
    path, record = run(args.case_dir, args.image, args.model, args.run_paid,
                       args.requirements, args.facts, args.reference)
    print("Status:", record["status"])
    print("Evidence:", path)
    for item in record["outputs"]:
        print("Output:", item["path"])
    if record["error"]:
        print(safe_text(record["error"]["message"]), file=sys.stderr)
        if record["api_call_attempted"]:
            print("请求已尝试发送，服务端执行与费用需核对；未自动重试。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
