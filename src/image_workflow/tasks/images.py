"""Task-scoped image use cases and existing cross-operation coordination.

Generation and Review retain their own rules/execution. This application boundary
coordinates their public interfaces with Task snapshots and the SAME locks.
No Flask, SDK, Prompt or new persistent state is introduced.
"""

from file_ops import ExportError
from image_workflow import Problem


class TaskImageApplication:
    def __init__(self, store, generation, queries, *, review, exporter, safe_text):
        self.store = store
        self.generation = generation
        self.queries = queries
        self.review = review
        self.exporter = exporter
        self.safe_text = safe_text

    def review_one(self, session_id, target, read_command):
        state = self.queries.confirmed_state(session_id, target)
        body = read_command()
        if target not in self.generation.targets(state) or not isinstance(body, dict) or body.get('confirmed_revision') != state['revision']:
            raise Problem('任务、图片或确认计划已改变，请刷新。', 409)
        try:
            event = self.review.review(self.generation, state, target, body.get('action'), body.get('run_id'), body.get('card_revision'))
        except (ValueError, OSError) as error:
            raise Problem(self.safe_text(str(error)), 409) from error
        return event

    def edit_state(self, session_id, target):
        state = self.queries.confirmed_state(session_id, target)
        if self.queries.card_view(self.store.load(session_id), target)['request_uncertain']:
            raise Problem('本图存在运行中或结果不确定的请求，请先人工核对；未重新调用模型。', 409)
        return state

    def revise(self, state, target, body, read_auxiliary):
        if target not in self.generation.targets(state) or not isinstance(body, dict) or body.get('confirmed_revision') != state['revision']:
            raise Problem('任务、图片或确认计划已改变，请刷新；未调用模型。', 409)
        feedback = body.get('feedback')
        if not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 12000 or not body.get('parent_run_id') or not body.get('operation_id') or not isinstance(body.get('card_revision'), int):
            raise Problem('请选择当前版本并填写修改意见（最多 12000 字）。')
        auxiliary = read_auxiliary()
        try:
            record = self.generation.generate(state, target, body['parent_run_id'], feedback, body['card_revision'], body['operation_id'], auxiliary=auxiliary)
        except ValueError as error:
            raise Problem(str(error), 409) from error
        return record

    def generate_one(self, session_id, target, read_command):
        latest = self.store.load(session_id)
        state = self.queries.confirmed_state(session_id, target)
        if self.queries.card_view(latest, target)['request_uncertain']:
            raise Problem('本图存在运行中或结果不确定的请求，请先人工核对；未重新调用模型。', 409)
        body = read_command()
        if not isinstance(body, dict) or body.get("confirmed_revision") != state["revision"]:
            raise Problem("确认计划的版本已改变，请刷新页面；本次没有调用模型。", 409)
        if target not in self.generation.targets(state):
            raise Problem("指定图片计划不存在。", 404)
        if state.get("mode") == "quick_redesign" and (not isinstance(body.get("card_revision"), int) or not body.get("operation_id")):
            raise Problem("请刷新图片状态后再提交；本次未调用模型。", 409)
        if body.get('batch_only'):
            if not body.get('operation_id') or not isinstance(body.get('card_revision'), int) or not self.queries.card_view(latest, target)['batch_eligible']:
                raise Problem('本图不再符合批量条件，已生成、已尝试、已 Pass 或状态待确认；未调用模型。', 409)
        try:
            record = self.generation.generate(state, target, expected_revision=body.get('card_revision'), operation_id=body.get('operation_id'))
        except ValueError as error:
            raise Problem(str(error), 409) from error
        return record

    def export_case(self, session_id):
        self.store.folder(session_id)  # Validate the identifier before filesystem access.
        try:
            if not self.store.lock.acquire(blocking=False):
                raise Problem("理解或规划尚在处理中，请完成后再导出。", 409)
            try:
                with self.generation.guard:
                    if any(key[0] == session_id for key in self.generation.active):
                        raise Problem("当前任务有图片正在生成，请完成后再导出。", 409)
                    package, filename = self.exporter(self.store, session_id)
            finally:
                self.store.lock.release()
        except (ExportError, OSError, KeyError, TypeError) as error:
            raise Problem(str(error) if isinstance(error, ExportError) else "实验包导出失败：允许范围内的证据缺失或不可读取；原文件未改动。", 409) from error
        return package, filename

    def passed_images(self, session_id):
        state = self.queries.confirmed_state(session_id)
        try:
            with self.generation.guard:
                if any(key[0] == session_id for key in self.generation.active):
                    raise ValueError('任务有图片正在处理，请完成后再导出。')
                package, filename = self.review.export_passed(self.generation, state)
        except (ValueError, OSError) as error:
            raise Problem(str(error), 409) from error
        return package, filename

    def generated_image(self, session_id, revision, target, run_id):
        self.store.load(session_id)
        try:
            folder = self.generation.run_folder(session_id, revision, target, run_id)
        except ValueError as error:
            raise Problem(str(error), 404) from error
        if not (folder / "run.json").is_file() or self.store.read_json(folder / "run.json").get("status") != "SUCCEEDED":
            raise Problem("成功生成的图片不存在。", 404)
        try:
            image_state = self.store.load(session_id)
            image_state['revision'] = revision
            data, _ = self.review.image_bytes(self.generation, image_state, target, run_id)
        except (ValueError, OSError) as error:
            raise Problem(str(error), 409) from error
        return data

    def operation_status(self, session_id, target, operation_id, read_revision):
        state = self.store.load(session_id)
        if target not in self.generation.targets(state):
            raise Problem('图片不属于当前任务。', 404)
        try:
            revision = int(read_revision())
            snapshot = self.store.version(state, revision)
            if target not in self.generation.targets(snapshot):
                raise Problem('图片不属于请求版本。', 404)
            return self.generation.operation(snapshot, target, operation_id)
        except ValueError as error:
            raise Problem(str(error), 400) from error
