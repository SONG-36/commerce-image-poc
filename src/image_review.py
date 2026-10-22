"""Legacy Review adapters plus unchanged auxiliary-image input/Prompt helpers."""

from datetime import datetime, timezone
import io
from pathlib import Path
from uuid import uuid4

from file_ops import read_json, safe_path, sha256, write_json_atomic
from evidence import contains_private
from PIL import Image
from persistence.review_state import ReviewFiles
from image_workflow.review import (ImageScope, ReviewIO, apply_review, export_passed as export_accepted,
                                   image_bytes as reviewed_image_bytes, versions as review_versions)
from image_workflow.tasks import review as _task_review


MAX_AUXILIARY_BYTES = 20 * 1024 * 1024
AUXILIARY_PURPOSES = {
    "product_appearance": "商品外观修正",
    "design_style": "设计风格参考",
    "local_content": "局部内容参考",
}


def prepare_auxiliary(name, data, purpose):
    """Validate a newly uploaded image; never accept a server path or asset ID."""
    if purpose not in AUXILIARY_PURPOSES:
        raise ValueError("请选择辅助图片用途：商品外观修正、设计风格参考或局部内容参考。")
    if not data or len(data) > MAX_AUXILIARY_BYTES:
        raise ValueError("辅助图片不能为空，且不能超过 20 MB。")
    if contains_private(data.decode('utf-8', errors='ignore')):
        raise ValueError("辅助图片包含疑似认证信息，请移除后重新上传；未发送模型。")
    try:
        with Image.open(io.BytesIO(data)) as image:
            extension, mime = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"),
                               "WEBP": ("webp", "image/webp")}[image.format]
            width, height = image.size
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except Exception as error:
        raise ValueError("辅助图片无法读取，请上传有效的 JPG、PNG 或 WebP。") from error
    from evidence import safe_text
    return {"name": safe_text(Path(name).name[:255]), "data": data,
            "file": f"inputs/auxiliary_reference.{extension}", "mime": mime,
            "role": "auxiliary_reference", "purpose": purpose, "purpose_label": AUXILIARY_PURPOSES[purpose],
            "sha256": sha256(data), "bytes": len(data), "width": width, "height": height,
            "scope": "current_image_only"}


def auxiliary_prompt(reference, slot):
    instructions = {
        "product_appearance": "该图是本次商品外观修正依据，不是普通设计风格参考。仅修正本次意见指定的外观，优先核对是否为当前同一 SKU；存在明显差异、冲突或无法确认身份时，不把其他 SKU 的结构或外观自动认定为当前商品事实，不猜测或拼合商品结构。",
        "design_style": "该图只用于借鉴构图、排版、配色和风格，不继承其中商品的外观、品牌、功能、参数或卖点。",
        "local_content": "该图仅用于修改意见明确指定的局部内容，尽量保留其余构图、商品和文字；不得自动复制其余商品结构、品牌或宣称。",
    }
    return f"""\n本次新增辅助输入：图片 {slot}（auxiliary_reference），用途：{reference['purpose_label']}。
{instructions[reference['purpose']]}
用途是运营声明，未经自动核验；不因上传而确认新功能、参数、附件或承诺。
仅影响当前图片的本次修改，不修改任务全局商品依据、其他图片或已有 Pass。
只结合当前选中成图、必要原始依据和本次意见；不沿用历史辅助图或全部修改历史。
尽量保持未要求修改的区域，但不保证 100% 不变，结果仍交运营审核。
"""


def _scope(state, target):
    return _task_review.image_scope(state, target, scope_type=ImageScope)


def _files(service, state, target):
    return _task_review.review_files(service, state, target, reader=read_json,
                                     writer=write_json_atomic, files_type=ReviewFiles)


def _io(service, state):
    from evidence import clean_record
    return _task_review.review_io(
        service, state, new_id=uuid4, utc_now=lambda: datetime.now(timezone.utc),
        sanitize=clean_record, private=contains_private, io_type=ReviewIO)


def versions(service, state, target):
    return _task_review.versions(service, state, target, scope_for=_scope,
                                 files_for=_files, version_reader=review_versions)


def image_bytes(service, state, target, run_id):
    return _task_review.image_bytes(service, state, target, run_id, scope_for=_scope,
                                    files_for=_files, image_reader=reviewed_image_bytes)


def review(service, state, target, kind, run_id, expected_revision):
    return _task_review.review(service, state, target, kind, run_id, expected_revision,
                               scope_for=_scope, files_for=_files, io_for=_io, apply=apply_review)


def export_passed(service, state):
    return _task_review.export_passed(service, state, files_for=_files,
                                      io_for=_io, exporter=export_accepted)
