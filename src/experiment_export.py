"""Offline, case-scoped ZIP export of existing evidence. Never calls a model."""

from datetime import datetime, timezone
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

from evidence import contains_private
from generate_image import sha256

RUN_ID = r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}"
IMAGE_NAME = r"(?:product|reference)_[0-9]+\.(?:jpg|jpeg|png|webp)"
RUN_FILES = ("run.json", "request.json", "prompt.txt", "response.json", "error.json")


class ExportError(ValueError):
    pass


def safe_path(root, relative="."):
    """Allow only descendants; reject symlinks before any file read."""
    relative = PurePosixPath(str(relative))
    if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
        raise ExportError("导出已停止：记录包含越界路径。")
    root = Path(root).absolute()
    # Trust platform ancestors, but not symlinks in the configured runtime tree.
    parents = [root, *root.parents]
    boundary = next((i for i, parent in enumerate(parents) if parent.name == ".runtime"), 0)
    for parent in parents[:boundary + 1]:
        if parent.is_symlink():
            raise ExportError("导出已停止：运行目录是符号链接。")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ExportError("导出已停止：允许范围内发现符号链接。")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ExportError("导出已停止：文件超出允许目录。")
    return path


def children(root, relative, pattern):
    path = safe_path(root, relative)
    if not path.exists():
        return []
    if not path.is_dir():
        raise ExportError("导出已停止：预期目录不可读取。")
    result = []
    for child in sorted(path.iterdir()):
        if re.fullmatch(pattern, child.name):
            safe_path(root, str(child.relative_to(root)))
            result.append(child)
    return result


def read_json(root, relative):
    try:
        return json.loads(safe_path(root, relative).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        if isinstance(error, ExportError):
            raise
        raise ExportError("导出已停止：证据 JSON 缺失或无法解析。") from error


def historical_case_match(state, session, case):
    """Historical linkage is inferred, only after matching original input hashes."""
    if state.get("mode") == "quick_redesign":
        return False
    if state.get("case_id", state.get("title")) != "case-001":
        return False
    try:
        for name in ("listing", "requirements"):
            if safe_path(case, name + ".md").read_text(encoding="utf-8") != state["inputs"][name]:
                return False
        known = {}
        for role, folder in [("product", "product"), ("reference", "references")]:
            known[role] = {sha256(p.read_bytes()) for p in children(case, folder, r"[^.][^/]*\.(?:jpg|jpeg|png|webp)") if p.is_file()}
        for image in state["images"]:
            if not re.fullmatch("inputs/" + IMAGE_NAME, image["file"]):
                raise ExportError("导出已停止：输入文件路径不在白名单。")
            if sha256(safe_path(session, image["file"]).read_bytes()) != image["sha256"] or image["sha256"] not in known.get(image["role"], set()):
                return False
        return bool(state["images"])
    except FileNotFoundError:
        return False


def export_experiment(store, session_id):
    session = safe_path(store.root, "sessions/" + session_id)
    state = read_json(session, "state.json")
    if state.get("id") != session_id:
        raise ExportError("导出已停止：任务标识与记录不一致。")
    case = store.case_dir
    linked = bool(case and historical_case_match(state, session, case))
    case_id = state.get("case_id") or ("case-001" if linked else "case-" + session_id)
    if not re.fullmatch(r"case-[a-zA-Z0-9_-]+", case_id):
        raise ExportError("导出已停止：Case ID 不合法。")
    prefix = case_id + "-experiment/"
    exported_at = datetime.now(timezone.utc)
    manifest = {"case_id": case_id, "session_id": session_id, "exported_at": exported_at.isoformat(),
                "mode": state.get("mode", "product_pack"),
                "confirmed_revision": state["revision"] if state.get("confirmed") else None,
                "case_link": {"status": "ACTUAL" if state.get("case_id") else "RECONSTRUCTED",
                              "basis": "saved case_id" if state.get("case_id") else "original inputs hash/text match" if linked else "session identifier"},
                "files": [], "runs": [], "missing": [],
                "version_relationships": [{"status": "RECONSTRUCTED", "source": "planning/state.json#events",
                                            "run_id": event.get("call_id"), "action": event.get("action"),
                                            "before_revision": event["revision"] - 1, "after_revision": event["revision"],
                                            "version_file": f"planning/revisions/{event['revision']:06}.json"}
                                           for event in state.get("events", []) if "revision" in event],
                "notes": ["ACTUAL = saved original bytes; RECONSTRUCTED = derived index/link; MISSING = unavailable evidence.",
                          "This package is experimental evidence, not an approved final image pack.",
                          "File paths are relative to the package root. manifest.json does not hash itself."]}
    buffer = io.BytesIO()
    binary_files = {}
    files_by_path = {}

    def missing(run_id, field, reason):
        manifest["missing"].append({"run_id": run_id, "field": field, "status": "MISSING", "reason": reason})

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(root, relative, destination, expected=None, run_id=None, required=False):
            path = safe_path(root, relative)
            if not path.is_file():
                if required:
                    missing(run_id, destination, "Not saved or no longer available; no substitute created.")
                return None
            data = path.read_bytes()
            digest = sha256(data)
            if contains_private(data.decode("utf-8", errors="ignore")):
                raise ExportError("导出已停止：证据含认证信息或隐藏推理，未生成下载包；原记录未改动。")
            if expected and digest != expected:
                raise ExportError("导出已停止：文件与已记录的 SHA-256 不一致。")
            if path.suffix in (".json", ".txt", ".md"):
                try:
                    value = json.loads(data) if path.suffix == ".json" else data.decode("utf-8")
                except (ValueError, UnicodeError) as error:
                    raise ExportError("导出已停止：文本证据不可读取。") from error
                if contains_private(value):
                    raise ExportError("导出已停止：证据含认证信息或隐藏推理，未生成下载包；原记录未改动。")
            area = "session" if root == session else "original_inputs" if root == case else "T01_evidence" if root.name == "case-001" and root.parent.name == "evidence" else "T01_outputs"
            source = {"area": area, "file": str(relative), "run_id": run_id}
            if destination in files_by_path:
                entry = files_by_path[destination]
                if entry["sha256"] != digest:
                    raise ExportError("导出已停止：同名证据内容不一致。")
                if source not in entry["sources"]:
                    entry["sources"].append(source)
                return entry["path"]
            # Share identical input images across run snapshots; preserve all source mappings.
            if path.suffix.lower() in (".jpg", ".jpeg", ".webp", ".png") and "/inputs/" in "/" + destination and digest in binary_files:
                entry = binary_files[digest]
                if source not in entry["sources"]:
                    entry["sources"].append(source)
                return entry["path"]
            entry = {"path": destination, "sha256": digest, "bytes": len(data), "status": "ACTUAL", "sources": [source]}
            archive.writestr(prefix + destination, data)
            manifest["files"].append(entry)
            files_by_path[destination] = entry
            if path.suffix.lower() in (".jpg", ".jpeg", ".webp", ".png") and "/inputs/" in "/" + destination:
                binary_files[digest] = entry
            return destination

        add(session, "state.json", "planning/state.json", required=True)
        add(session, "inputs/texts.json", "inputs/texts.json", required=True)
        for name in ("listing", "description", "requirements", "product_facts"):
            if name not in state["inputs"]:
                continue
            data = state["inputs"][name].encode("utf-8")
            if contains_private(state["inputs"][name]):
                raise ExportError("导出已停止：商品文本含认证信息。")
            destination = "inputs/" + name + ".md"
            archive.writestr(prefix + destination, data)
            entry = {"path": destination, "sha256": sha256(data), "bytes": len(data), "status": "RECONSTRUCTED",
                     "sources": [{"area": "session", "file": "state.json#inputs." + name}],
                     "reason": "Convenience text extracted from saved state; not an original standalone file."}
            manifest["files"].append(entry)
            files_by_path[destination] = entry
        for image in state["images"]:
            if not re.fullmatch("inputs/" + IMAGE_NAME, image["file"]):
                raise ExportError("导出已停止：输入文件路径不在白名单。")
            add(session, image["file"], image["file"], image["sha256"], required=True)
        for version in children(session, "versions", r"[0-9]{6}\.json"):
            add(session, str(version.relative_to(session)), "planning/revisions/" + version.name)

        def gather_run(root, relative, destination, stage, run_id, extras=()):
            record = read_json(root, relative + "/run.json")
            if record.get("status") in ("RUNNING", "PREPARING"):
                raise ExportError("存在尚未结束的调用，请待状态确认后再导出；本次未调用模型。")
            entry = {"run_id": run_id, "stage": stage, "status": record.get("status"),
                     "index_status": "RECONSTRUCTED", "record": destination + "/run.json", "inputs": []}
            manifest["runs"].append(entry)
            for name in (*RUN_FILES, *extras):
                add(root, relative + "/" + name, destination + "/" + name, run_id=run_id,
                    required=name in ("run.json", "request.json", "prompt.txt") or name == "response.json" and bool(record.get("api_call_attempted")))
            if stage == "T02":
                for name in ("image_order.json", "result.json", "applied.json"):
                    if not safe_path(root, relative + "/" + name).is_file() and (name == "image_order.json" or record.get("status") == "AI_RESULT_RECEIVED"):
                        missing(run_id, name, "Original planning evidence was not saved or is unavailable.")
            if stage in ("T03", "T04", "I01") and not safe_path(root, relative + "/plan.json").is_file():
                missing(run_id, "plan.json", "No saved image context; not reconstructed from current state.")
            if record.get("usage") is None:
                missing(run_id, "usage", "No usage was saved/returned; no token estimate substituted.")
            if record.get("api_call_attempted"):
                missing(run_id, "model_internal_effective_prompt", "Only client-submitted prompt and returned fields are available; hidden reasoning is excluded.")
                missing(run_id, "billed_cost", "No actual billing amount was recorded.")
                missing(run_id, "raw_http_and_full_response_headers", "SDK arguments/returned fields and request ID are retained; raw HTTP and full headers were not recorded.")
            if "case_id" not in record:
                missing(run_id, "case_id_in_original_run", "Case linkage is in the derived manifest; legacy original run was not rewritten.")
            return record, entry

        for call in children(session, "calls", r"[0-9a-f]{32}"):
            relative = str(call.relative_to(session))
            record, entry = gather_run(session, relative, "planning/calls/" + call.name, "T02", call.name,
                                       ("image_order.json", "result.json", "applied.json"))
            order_path = safe_path(session, relative + "/image_order.json")
            if order_path.is_file():
                for slot, image in enumerate(read_json(session, relative + "/image_order.json"), 1):
                    if not re.fullmatch("inputs/" + IMAGE_NAME, image["file"]):
                        raise ExportError("导出已停止：调用输入路径不在白名单。")
                    exported = add(session, image["file"], image["file"], image["sha256"], call.name, True)
                    entry["inputs"].append({"slot": image.get("slot", slot), "id": image["id"], "sha256": image["sha256"], "file": exported})
            else:
                missing(call.name, "image_order", "No original image-order record available.")
            if "parent_revision" not in record:
                missing(call.name, "parent_revision_in_run", "Absent in legacy run; existing versions/events/applied record retained without rewriting.")

        for revision in children(session, "generations", r"[0-9]{6}"):
            for target in children(session, str(revision.relative_to(session)), r"(?:product|reference)_[0-9]+"):
                task = str(target.relative_to(session))
                add(session, task + "/current.json", "generations/" + revision.name + "/" + target.name + "/current.json")
                for event in children(session, task + '/reviews', r'[0-9a-f]{32}\.json'):
                    add(session, str(event.relative_to(session)), 'generations/' + revision.name + '/' + target.name + '/reviews/' + event.name)
                for run in children(session, task + "/runs", RUN_ID):
                    relative = str(run.relative_to(session))
                    destination = "generations/runs/" + run.name
                    recorded = read_json(session, relative + '/run.json')
                    stage = "T04" if recorded.get('action') == 'revise_image' else "I01" if recorded.get('mode') == 'quick_redesign' else "T03"
                    record, entry = gather_run(session, relative, destination, stage, run.name, ("plan.json",))
                    entry['mode'] = record.get('mode', 'product_pack')
                    entry.update(parent_run_id=record.get('parent_run_id'), version=record.get('version'), feedback=record.get('feedback'))
                    entry.update(confirmed_revision=record.get("confirmed_revision"), reference_id=record.get("reference_id"))
                    for image in record.get("inputs", []):
                        if not re.fullmatch("inputs/(?:" + IMAGE_NAME + r"|current_image\.png)", image["file"]):
                            raise ExportError("导出已停止：生图输入路径不在白名单。")
                        exported = add(session, relative + "/" + image["file"], destination + "/" + image["file"], image["sha256"], run.name, True)
                        entry["inputs"].append({"slot": image["slot"], "id": image["id"], "sha256": image["sha256"], "file": exported})
                    for name in ("listing.md", "description.md", "requirements.md", "product_facts.md"):
                        add(session, relative + "/inputs/" + name, destination + "/inputs/" + name, run_id=run.name)
                    output = record.get("output")
                    if output:
                        if output.get("file") != "image.png":
                            raise ExportError("导出已停止：输出图片路径不在白名单。")
                        entry["output"] = add(session, relative + "/image.png", "generations/images/" + run.name + ".png", output.get("sha256"), run.name, True)

        # Legacy T01 is joined only by matching Case input bytes, never by arbitrary JSON paths.
        if linked:
            for name in ("listing.md", "requirements.md"):
                add(case, name, "inputs/original/" + name)
            for folder in ("product", "references"):
                for path in children(case, folder, r"[^.][^/]*\.(?:jpg|jpeg|png|webp)"):
                    add(case, str(path.relative_to(case)), "inputs/original/" + folder + "/" + path.name)
            runtime = case.parent.parent
            legacy = safe_path(runtime, "evidence/case-001")
            for run in children(legacy, ".", RUN_ID):
                record, entry = gather_run(legacy, run.name, "evidence/T01/" + run.name, "T01", run.name)
                for image in record.get("inputs", []):
                    parts = Path(image["path"]).parts
                    marker = next((i for i in range(len(parts)-1) if parts[i:i+2] == ("inputs", "case-001")), None)
                    relative = "/".join(parts[marker+2:]) if marker is not None else ""
                    if not re.fullmatch(r"(?:listing|requirements)\.md|(?:product|references)/[^./][^/]*\.(?:jpg|jpeg|png|webp)", relative):
                        raise ExportError("导出已停止：T01 历史输入路径不在白名单。")
                    exported = add(case, relative, "inputs/original/" + relative, image["sha256"], run.name, True)
                    entry["inputs"].append({"file": exported, "sha256": image["sha256"], "selected_for_request": image.get("selected_for_request")})
                for output in record.get("outputs", []):
                    if Path(output["path"]).name != "image.png":
                        raise ExportError("导出已停止：T01 输出路径不在白名单。")
                    entry["output"] = add(runtime, "outputs/case-001/" + run.name + "/image.png", "evidence/T01/" + run.name + "/image.png", output["sha256"], run.name, True)
        elif case_id == "case-001":
            missing(None, "T01_link", "Original Case inputs unavailable or changed; historical T01 was not mixed into this session.")

        manifest["run_ids"] = [entry["run_id"] for entry in manifest["runs"]]
        archive.writestr(prefix + "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    filename = case_id + "-experiment-" + exported_at.strftime("%Y%m%d-%H%M%S-%f") + ".zip"
    buffer.seek(0)
    return buffer, filename
