"""Execute one T02 call; return validated data for the caller to apply.

This service owns call Evidence and in-flight activity, not Task revisions,
confirmations or snapshots. All external adapters are explicit per-call inputs.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Callable, Mapping, MutableMapping

from file_ops import sha256
from ..errors import Problem
from .request import RULES, build_planning_request, planning_images, reference_ids
from .validation import validate_result


@dataclass(frozen=True)
class PlanningIO:
    """Concrete call adapters, not a global registry or a shared model context.

    source_file identifies the calling entry source for source_sha256. It is
    deliberately NOT the service file or a fingerprint of all dependencies.
    JSON/text writers retain the caller's existing sanitization policy.
    """

    client_factory: Callable
    write_json: Callable
    safe_text: Callable
    now: Callable
    new_id: Callable
    sdk_version: Callable
    source_file: Path
    clock: Callable = time.perf_counter


def load_image_bytes(folder, state, action, target):
    """Read only selected identities and reject bytes changed since upload."""
    image_bytes = {}
    for image in planning_images(state, action, target):
        data = (folder / image["file"]).read_bytes()
        if sha256(data) != image["sha256"]:
            raise Problem("保存的输入图片发生变化，已停止调用。")
        image_bytes[image["file"]] = data
    return image_bytes


def save_request(evidence, arguments, image_order, record, io, instructions):
    """Preserve request -> image order -> sent text order and record metadata."""
    content = arguments["input"][0]["content"]
    io.write_json(evidence / "request.json", arguments, exclusive=True)
    io.write_json(evidence / "image_order.json", image_order, exclusive=True)
    (evidence / "prompt.txt").write_text(io.safe_text(instructions + "\n\n" + "\n\n".join(
        item["text"] for item in content if item["type"] == "input_text")), encoding="utf-8")
    record["inputs"] = image_order
    record["parameters"] = {key: value for key, value in arguments.items() if key not in ["input", "instructions"]}
    record["request_file"] = "request.json"


def invoke_model(arguments, key, record, evidence, io):
    """One Responses SDK attempt with the original timeout and zero retries.

    Status is written only after the client context opens, as before. Exceptions
    propagate to execute_planning; timing also survives an interrupted request.
    """
    with io.client_factory(api_key=key, base_url="https://api.openai.com/v1", max_retries=0, timeout=120.0) as client:
        record["api_call_attempted"] = True
        record['status'] = 'RUNNING'
        record["api_started_at"] = io.now()
        io.write_json(evidence / "run.json", record)
        api_started = io.clock()
        try:
            response = client.responses.create(**arguments)
        finally:
            record["api_elapsed_seconds"] = round(io.clock() - api_started, 3)
    return response


def receive_result(response, action, ids, record, evidence, io, validator):
    """Save the actual response before parsing/validation; never apply Task state."""
    record["request_id"] = response._request_id
    raw = response.model_dump(mode="json")
    record["usage"] = raw.get("usage")
    record["returned_model"] = raw.get("model")
    io.write_json(evidence / "response.json", raw, exclusive=True)
    if response.status != "completed":
        raise Problem("AI 本次未完整返回结果，请查看错误后再决定是否重试。", 502)
    result = validator(json.loads(response.output_text), action, ids)
    io.write_json(evidence / "result.json", result, exclusive=True)
    record["result_file"] = "result.json"
    record["status"] = "AI_RESULT_RECEIVED"
    return result


def execute_planning(folder: Path, state, action, target, feedback, *, case_id_for: Callable,
                     activity: MutableMapping, models: tuple, environment: Mapping,
                     io: PlanningIO, request_builder=None, validator=validate_result, instructions=RULES):
    """Return (validated_result, call_id); state application remains caller-owned.

    folder/identity are validated by the caller. The activity mapping is the
    existing in-process registry. Optional pure callbacks retain old mock/import
    seams; normal standalone calls use this package's builder and validator.
    """
    call_id = io.new_id().hex
    evidence = folder / "calls" / call_id
    evidence.mkdir(parents=True)
    model = environment.get("OPENAI_PLANNING_MODEL", models[0])
    record = {"id": call_id, "run_id": call_id, "case_id": case_id_for(state), "session_id": state["id"],
              "parent_revision": state["revision"], "parent_version_file": f"versions/{state['revision']:06}.json",
              "action": action, "target": target, "feedback": feedback,
              "started_at": io.now(), "model": model, "sdk_version": io.sdk_version("openai"),
              "source_sha256": sha256(io.source_file.read_bytes()), "endpoint": "https://api.openai.com/v1/responses",
              "max_retries": 0, "timeout_seconds": 120.0, "api_call_attempted": False,
              "status": "PREPARING", "usage": None, "request_id": None}
    started = io.clock()
    try:
        activity[state['id']] = record
        io.write_json(evidence / 'run.json', record)
        if model not in models:
            raise Problem("规划模型配置不在已核实的模型列表内，请检查运行配置。")
        ids = reference_ids(state)
        image_bytes = load_image_bytes(folder, state, action, target)
        if request_builder is None:
            arguments, image_order = build_planning_request(state, action, target, feedback, model, image_bytes,
                                                            reasoning_model=models[0], instructions=instructions)
        else:
            arguments, image_order = request_builder(state, action, target, feedback, model, image_bytes)
        del image_bytes
        save_request(evidence, arguments, image_order, record, io, instructions)
        key = environment.get("OPENAI_API_KEY", "")
        if not key.strip():
            raise Problem("AI 服务尚未配置。请由运行人员在启动服务的终端设置环境密钥；本次没有调用模型。", 503)
        response = invoke_model(arguments, key, record, evidence, io)
        def validate_response(raw, action, ids):
            result = validator(raw, action, ids)
            if 'listing_slots' in state:
                from .conflicts import validate_reports
                result['fact_issues'] = validate_reports(raw, state, ids)
            return result
        result = receive_result(response, action, ids, record, evidence, io, validate_response)
        return result, call_id
    except Exception as error:
        record["status"] = "FAILED"
        record["request_id"] = getattr(error, "request_id", None) or record["request_id"]
        record["error"] = {"type": type(error).__name__, "message": str(error),
                           "status_code": getattr(error, "status_code", None), "body": getattr(error, "body", None)}
        io.write_json(evidence / "error.json", record["error"], exclusive=True)
        if isinstance(error, Problem):
            raise
        if isinstance(error, (json.JSONDecodeError, TypeError)):
            raise Problem("AI 返回内容无法解析，已保存原始响应；当前理解与计划未替换。", 502) from error
        raise Problem("AI 请求失败：" + io.safe_text(str(error)), 502) from error
    finally:
        record["finished_at"] = io.now()
        record["elapsed_seconds"] = round(io.clock() - started, 3)
        activity.pop(state['id'], None)
        io.write_json(evidence / "run.json", record)
