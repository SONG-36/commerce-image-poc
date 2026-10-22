"""Auxiliary edit input validation and role-specific Prompt policy.

Reads supplied image bytes in memory only. This is a Generation input policy,
not Review, upload persistence or model execution. Validation and Prompt policy have one canonical owner.
"""

import io
from pathlib import Path

from PIL import Image

from file_ops import sha256
from infrastructure.evidence import contains_private, safe_text


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
