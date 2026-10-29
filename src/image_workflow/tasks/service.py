"""Task use cases: creation, state advancement and Planning application.

HTTP readers are deferred callbacks so existing lock/error precedence is kept.
They return plain form/command values; this module has no Flask dependency.
"""

import io
import json
from pathlib import Path

from PIL import Image

from file_ops import sha256
from image_workflow import Problem
from image_workflow.planning.request import reference_ids
import image_workflow.generation.quick_v1 as quick_v1
from image_workflow.generation.request import validate_image_sizes, validate_quality, validate_image_qualities
from .rules import apply_planning_result, confirm_plan, edit_plan, plan_status, stale_ids
from image_workflow.planning.validation import manual_plan
from infrastructure.evidence import contains_private
from image_workflow.planning.conflicts import resolve


def save_task(store, state, event, *, clock):
    state["revision"] += 1
    if state.get('plan_confirmations'):
        state['confirmed'] = all(plan_status(state, target)['confirmed'] for target in reference_ids(state))
    state["updated_at"] = clock()
    state["events"].append({"at": clock(), "revision": state["revision"], **event})
    store.persist(state)


def create_task(store, text, uploads, title, case_id=None, mode="product_pack", output_size="1024x1536", *,
                clock, new_id, contains_private, sizes, default_requirements,
                quick_business_version=None, quick_slots=None, image_sizes=None,
                quick_scenario=None, listing_slots=None, generation_quality=None, image_qualities=None):
    if mode not in ("product_pack", "quick_redesign"):
        raise Problem("请选择有效的工作模式。")
    if quick_business_version is not None or quick_slots is not None:
        if mode != "quick_redesign" or quick_business_version not in (quick_v1.LEGACY, quick_v1.VERSION):
            raise Problem("请显式指定有效的 Quick 业务版本。")
        if quick_business_version != quick_v1.VERSION and quick_slots is not None:
            raise Problem("图位配置仅适用于 Quick V1。")
    if quick_scenario is not None:
        try:
            quick_v1.validate_scenario({"mode": mode, "quick_business_version": quick_business_version,
                                        "quick_scenario": quick_scenario})
        except ValueError as error:
            raise Problem(str(error)) from error
    if listing_slots is not None and (mode != "product_pack" or image_sizes is not None):
        raise Problem("Listing 图位仅用于商品资料制图，逐图尺寸请保存在图位内。")
    if mode == "quick_redesign" and output_size not in sizes:
        raise Problem("请选择支持的输出比例。")
    if not any(role == "product" for role, _, _ in uploads):
        raise Problem("请至少提供一张商品原图。")
    if mode == "product_pack" and not any(role == "reference" for role, _, _ in uploads):
        raise Problem("请至少提供一张商品原图和一张设计参考图。")
    if any(not isinstance(text.get(key), str) for key in ["listing", "description", "requirements"]):
        raise Problem("资料文本格式不正确。")
    if mode == "quick_redesign":
        if not isinstance(text.get("product_facts", ""), str):
            raise Problem("商品事实说明格式不正确。")
        if contains_private(text):
            raise Problem("资料包含疑似认证信息，请移除后重新保存；未发送模型。")
        text = {**text, "requirements": text["requirements"].strip() or default_requirements,
                "product_facts": text.get("product_facts", "")}
    checked = []
    for role, name, data in uploads:
        if len(data) > 20 * 1024 * 1024:
            raise Problem("单张图片不能超过 20 MB。")
        try:
            with Image.open(io.BytesIO(data)) as image:
                ext, mime = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}[image.format]
                width, height = image.size
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        except Exception as error:
            raise Problem("无法读取上传图片，请使用有效的 JPG、PNG 或 WebP。") from error
        checked.append((role, Path(name).name, data, ext, mime, width, height))
    # Resolve upload-local asset IDs before any writes. References can only name
    # these assets, never a server path or another task's asset.
    identities, counts = [], {"product": 0, "reference": 0}
    for role, *_ in checked:
        counts[role] += 1
        identities.append({"id": f"{role}_{counts[role]:03}", "role": role})
    if quick_business_version == quick_v1.VERSION:
        try:
            quick_slots = quick_v1.validate_slots(quick_slots, identities)
        except ValueError as error:
            raise Problem(str(error)) from error
        if contains_private(quick_slots):
            raise Problem("图位资料包含疑似认证信息，请移除后重新保存；未发送模型。")
    if listing_slots is not None:
        try:
            listing_slots = quick_v1.validate_listing_slots(listing_slots, identities, sizes)
        except ValueError as error:
            raise Problem(str(error)) from error
        if contains_private(listing_slots):
            raise Problem("图位资料包含疑似认证信息，请移除后重新保存；未发送模型。")
    if image_sizes is not None:
        targets = {slot['id'] for slot in quick_slots} if quick_business_version == quick_v1.VERSION else {
            image['id'] for image in identities if image['role'] == ('product' if mode == 'quick_redesign' else 'reference')}
        try:
            image_sizes = validate_image_sizes(image_sizes, targets, sizes)
        except ValueError as error:
            raise Problem(str(error)) from error
    targets = ({slot['id'] for slot in quick_slots} if quick_business_version == quick_v1.VERSION else
               {image['id'] for image in identities if image['role'] == ('product' if mode == 'quick_redesign' else 'reference')})
    try:
        if generation_quality is not None:
            generation_quality = validate_quality(generation_quality)
        if image_qualities is not None:
            image_qualities = validate_image_qualities(image_qualities, targets)
    except ValueError as error:
        raise Problem(str(error)) from error
    session_id = new_id().hex
    folder = store.begin_inputs(session_id)
    state = {
        "id": session_id, "title": title, "created_at": clock(), "revision": 0,
        "mode": mode, "output_size": output_size,
        "case_id": case_id or "case-" + session_id,
        "inputs": text, "images": [], "product": None, "references": {}, "plans": {},
        "product_version": 0, "reference_versions": {}, "plan_context": {},
        "corrections": {"product": [], "references": {}}, "events": [], "confirmed": False,
    }
    if quick_business_version is not None:
        state["quick_business_version"] = quick_business_version
    if quick_business_version == quick_v1.VERSION:
        state["quick_slots"] = quick_slots
    if quick_scenario is not None:
        state["quick_scenario"] = quick_scenario
    if listing_slots is not None:
        state["listing_slots"] = listing_slots
    if image_sizes is not None:
        state['image_sizes'] = image_sizes
    if generation_quality is not None:
        state['generation_quality'] = generation_quality
    if image_qualities is not None:
        state['image_qualities'] = image_qualities
    counts = {"product": 0, "reference": 0}
    for role, name, data, ext, mime, width, height in checked:
        counts[role] += 1
        image_id = f"{role}_{counts[role]:03}"
        relative = f"inputs/{image_id}.{ext}"
        store.write_input(folder, relative, data)
        state["images"].append({"id": image_id, "role": role, "name": name, "file": relative,
                                "mime": mime, "sha256": sha256(data), "bytes": len(data), "width": width, "height": height})
    store.write_texts(folder, text)
    store.save(state, {"action": "inputs_saved", "feedback": "", "target": None})
    store.write_current(session_id)
    return state


class TaskApplication:
    def __init__(self, store, generation, *, planner, clock, writer):
        self.store = store
        self.generation = generation
        self.planner = planner
        self.clock = clock
        self.writer = writer

    def load_case(self, case):
        with self.store.lock:
            text, uploads = self.store.case_inputs(case)
            return self.store.create(text, uploads, "case-001", case_id="case-001")

    def save_inputs(self, read_form, read_uploads):
        with self.store.lock:
            form = read_form()
            uploads = []
            previous_id = form.get("from_session")
            if previous_id:
                previous = self.store.load(previous_id)
                try:
                    keep = json.loads(form.get("keep_images", "[]"))
                except json.JSONDecodeError as error:
                    raise Problem("保留图片列表无效。") from error
                if not isinstance(keep, list) or not set(keep).issubset({image["id"] for image in previous["images"]}):
                    raise Problem("保留图片列表无效。")
                for image in previous["images"]:
                    if image["id"] in keep:
                        uploads.append((image["role"], image["name"], self.store.read_input(previous_id, image["file"])))
            uploads.extend(read_uploads())
            mode = form.get("mode", "product_pack")
            if previous_id and mode != previous.get("mode", "product_pack"):
                raise Problem("复制任务不能切换工作模式；请从任务中心新建。")
            keys = ["listing", "description", "requirements"] + (["product_facts"] if mode == "quick_redesign" else [])
            text = {key: form.get(key, "") for key in keys}
            title = form.get('title', '新商品资料').strip()
            if not title or len(title) > 120:
                raise Problem('请填写任务名称（最多 120 字）。')
            options = {}
            if 'generation_quality' in form:
                options['generation_quality'] = form['generation_quality']
            elif previous_id and 'generation_quality' in previous:
                options['generation_quality'] = previous['generation_quality']
            if 'image_qualities' in form:
                try:
                    options['image_qualities'] = json.loads(form['image_qualities'])
                except (TypeError, ValueError) as error:
                    raise Problem('逐图质量配置不是有效 JSON。') from error
            elif previous_id and previous.get('image_qualities'):
                raise Problem('另存任务须显式提交重映射后的逐图质量。')
            version = form.get("quick_business_version")
            if previous_id and previous.get("quick_business_version") == quick_v1.VERSION:
                if version != quick_v1.VERSION:
                    raise Problem("复制 Quick V1 必须显式保留业务版本并重新提交图位绑定。")
            if version is not None or "quick_slots" in form:
                try:
                    slots = json.loads(form["quick_slots"]) if "quick_slots" in form else None
                except (TypeError, ValueError) as error:
                    raise Problem("图位配置不是有效的 JSON。") from error
                options.update(quick_business_version=version, quick_slots=slots)
            scenario = form.get("quick_scenario")
            if previous_id and scenario != previous.get("quick_scenario"):
                raise Problem("另存任务须保留原 Quick 子场景；请从任务中心新建其他场景。")
            if scenario is not None:
                options["quick_scenario"] = scenario
            if previous_id and "listing_slots" in previous and "listing_slots" not in form:
                raise Problem("另存 Listing 请显式保留图位分类并重新提交参考绑定。")
            if "listing_slots" in form:
                try:
                    options["listing_slots"] = json.loads(form["listing_slots"])
                except (TypeError, ValueError) as error:
                    raise Problem("Listing 图位配置不是有效的 JSON。") from error
                if options["listing_slots"] is None:
                    raise Problem("Listing 图位配置必须为列表。")
            if previous_id and previous.get('image_sizes') and 'image_sizes' not in form and 'listing_slots' not in options:
                raise Problem('另存任务请显式提交逐图尺寸，以保持输出绑定。')
            if 'image_sizes' in form:
                try:
                    options['image_sizes'] = json.loads(form['image_sizes'])
                except (TypeError, ValueError) as error:
                    raise Problem('逐图尺寸不是有效的 JSON。') from error
                if not isinstance(options['image_sizes'], dict):
                    raise Problem('逐图尺寸必须为本任务输出到合法尺寸的映射。')
            state = self.store.create(text, uploads, title, mode=mode, output_size=form.get("output_size", "1024x1536"), **options)
            return state

    def action(self, session_id, read_command):
        if not self.store.lock.acquire(blocking=False):
            raise Problem("有操作正在处理，请稍候；本次没有重复调用模型。", 409)
        try:
            with self.generation.guard:
                if any(key[0] == session_id for key in self.generation.active):
                    raise Problem('本任务有图片正在处理，请完成后再改动或确认计划。', 409)
            state = self.store.load(session_id)
            body = read_command()
            if isinstance(body, dict) and body.get('action') == 'set_quality':
                options = {key: body[key] for key in
                           ('knowledge_enabled', 'knowledge_conditions', 'knowledge_char_budget') if key in body}
                if options:
                    from image_workflow.planning.knowledge import validate_options
                    validate_options(**options)
                    if options.get('knowledge_enabled', False):
                        raise Problem('质量设置不接受 Planning Knowledge 实验参数。')
                return self.set_quality(state, body)
            if state.get("mode") == "quick_redesign":
                raise Problem("快速重设计不执行商品理解或规划；请进入图片生成。", 409)
            if not isinstance(body, dict) or body.get("revision") != state["revision"]:
                raise Problem("页面内容已过期，请刷新后再操作；本次没有调用模型。", 409)
            kind, target, feedback = body.get("action"), body.get("target"), body.get("feedback", "")
            ids = reference_ids(state)
            if kind not in ["understand", "product", "reference", "plan", "replan", "confirm", "resolve_conflict", "manual_plan"]:
                raise Problem("不支持的操作。")
            knowledge_options = {key: body[key] for key in
                                 ('knowledge_enabled', 'knowledge_conditions', 'knowledge_char_budget') if key in body}
            if knowledge_options:
                from image_workflow.planning.knowledge import validate_options
                validate_options(**knowledge_options)
                if knowledge_options.get('knowledge_enabled', False) and kind in ('confirm', 'resolve_conflict', 'manual_plan'):
                    raise Problem('免费确认或编辑操作不接受 Planning Knowledge 实验参数。')
                if contains_private(body.get('knowledge_conditions')):
                    raise Problem('Knowledge 条件包含疑似凭据，请移除后重试；未调用模型。')
                if not knowledge_options.get('knowledge_enabled', False):
                    knowledge_options = {}
            if kind != "understand" and state["product"] is None:
                raise Problem("请先完成 AI 理解与规划。")
            if kind in ["reference", "plan"] and target not in ids:
                raise Problem("指定参考图或计划不存在。")
            if not isinstance(feedback, str) or len(feedback) > 12000 or kind in ["product", "reference", "plan"] and not feedback.strip():
                raise Problem("请填写本次修改意见（最多 12000 字）。")
            if kind == "understand" and state["product"] is not None:
                raise Problem("已有理解与计划，请使用修正或重新规划按钮，避免覆盖修改。")
            if kind == 'resolve_conflict':
                # Keep previous per-image confirmations before invalidating only affected plans.
                from .rules import materialize_confirmations
                materialize_confirmations(state)
                event = resolve(state, body, clock=self.clock)
                self.store.save(state, event)
                return state
            if kind == "confirm":
                event = confirm_plan(state, target, body, clock=self.clock)
                if event is not None:
                    self.store.save(state, event)
                return state
            if kind == 'manual_plan':
                if contains_private(body.get('plan')):
                    raise Problem('方案包含疑似认证信息，请移除后保存。')
                try:
                    plan = manual_plan(body.get('plan'))
                except Problem as error:
                    raise Problem(str(error)) from error
                event = edit_plan(state, target, plan, body.get('plan_version'))
                self.store.save(state, event)
                return state
            parent_revision = state["revision"]
            result, call_id = self.planner(state, kind, target, feedback, **knowledge_options)
            event = apply_planning_result(state, kind, target, feedback, result, call_id)
            self.store.save(state, event)
            self.writer(self.store.folder(session_id) / "calls" / call_id / "applied.json",
                       {"revision": state["revision"], "parent_revision": parent_revision, "run_id": call_id,
                        "case_id": self.store.case_id(state), "version_file": f"versions/{state['revision']:06}.json", "at": self.clock()}, exclusive=True)
            return state
        finally:
            self.store.lock.release()

    def set_quality(self, state, body):
        """Caller holds the Task lock; preferences do not change plan/Run buckets."""
        if (body.get('revision') != state['revision'] or
                body.get('quality_revision') != state.get('quality_revision', 0)):
            raise Problem('质量或任务版本已改变，请刷新。', 409)
        try:
            quality = validate_quality(body.get('generation_quality', state.get('generation_quality', 'low')))
            targets = ({slot['id'] for slot in state['quick_slots']} if quick_v1.is_v1(state) else
                       {image['id'] for image in state['images'] if image['role'] ==
                        ('product' if state.get('mode') == 'quick_redesign' else 'reference')})
            overrides = validate_image_qualities(body.get('image_qualities', state.get('image_qualities', {})), targets)
        except ValueError as error:
            raise Problem(str(error)) from error
        self.writer(self.store.folder(state['id']) / 'generation_settings.json',
                    {'task_id': state['id'], 'quality_revision': state.get('quality_revision', 0) + 1,
                     'generation_quality': quality, 'image_qualities': overrides, 'source': 'OPERATOR_SETTINGS',
                     'updated_at': self.clock()})
        return self.store.load(state['id'])
