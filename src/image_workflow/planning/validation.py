"""Structural validation only; a valid response is not semantic or operator acceptance.

The shared Problem retains its legacy name/status contract; this module does
not import Flask or make HTTP responses.
"""

from ..errors import Problem

PRODUCT_FIELDS = ("identity", "claims", "appearance", "uncertainties")
REFERENCE_FIELDS = ("style", "composition", "layout", "expression", "applicable", "risks")
PLAN_FIELDS = ("goal", "selling_points", "design", "scene_style", "risks")


def fields(value, names):
    if not isinstance(value, dict) or any(not isinstance(value.get(name), str) or not value[name].strip() for name in names):
        raise Problem("AI 返回内容缺少必要信息，未替换当前结果。请查看实际错误后再决定是否重试。", 502)
    return {name: value[name] for name in names}


def manual_plan(value):
    """Human text still uses the existing plan schema, not fact certification."""
    if not isinstance(value, dict) or set(value) != set(PLAN_FIELDS):
        raise Problem('请完整填写本图方案的五项内容。')
    clean = fields(value, PLAN_FIELDS)
    if any(len(text) > 12000 for text in clean.values()):
        raise Problem('每项方案最多 12000 字。')
    return clean


def response_shape(action, ids):
    product = {key: "简短中文" for key in PRODUCT_FIELDS}
    ref = {key: "简短中文" for key in REFERENCE_FIELDS}
    plan = {key: "简短中文" for key in PLAN_FIELDS}
    if action == "understand":
        return {"product": product, "references": {key: ref for key in ids}, "plans": {key: plan for key in ids}}
    if action == "product":
        return {"product": product}
    if action == "reference":
        return {"reference": ref}
    if action == "plan":
        return {"plan": plan}
    return {"plans": {key: plan for key in ids}}


def validate_result(result, action, ids):
    if not isinstance(result, dict):
        raise Problem("AI 未返回可用的理解或计划。", 502)
    clean = {}
    if action in ["understand", "product"]:
        clean["product"] = fields(result.get("product"), PRODUCT_FIELDS)
    if action == "reference":
        clean["reference"] = fields(result.get("reference"), REFERENCE_FIELDS)
    if action == "plan":
        clean["plan"] = fields(result.get("plan"), PLAN_FIELDS)
    for group, names in [("references", REFERENCE_FIELDS), ("plans", PLAN_FIELDS)]:
        if action == "understand" or action == "replan" and group == "plans":
            values = result.get(group)
            if not isinstance(values, dict) or set(values) != set(ids):
                raise Problem("AI 返回的参考图或计划数量不一致，未替换当前结果。", 502)
            clean[group] = {key: fields(values[key], names) for key in ids}
    return clean
