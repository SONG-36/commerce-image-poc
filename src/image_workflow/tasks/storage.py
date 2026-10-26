"""Task file access only; business transitions and query projections live elsewhere.

Reuse persistence.task_state and the caller's existing JSON policy. No locks,
confirmation rules, model calls or automatic repair are introduced here.
"""

from pathlib import Path
import re

from file_ops import safe_path
from image_workflow import Problem
from persistence import task_state
import image_workflow.generation.quick_v1 as quick_v1
from image_workflow.generation.request import validate_image_sizes
from image_workflow.generation.quick_prompt import SIZES


class TaskFiles:
    def __init__(self, root, case_dir=None, *, reader, writer):
        self.root = Path(root)
        self.case_dir = Path(case_dir) if case_dir else None
        self.read_json = reader
        self.write_json = writer

    def folder(self, session_id):
        if not re.fullmatch(r"[0-9a-f]{32}", session_id or ""):
            raise Problem("无效的任务标识。", 404)
        return safe_path(self.root, 'sessions/' + session_id)

    def load(self, session_id):
        try:
            state = task_state.read_current(self.folder(session_id), reader=self.read_json)
        except task_state.MissingStateFile:
            raise Problem("准备任务不存在，请重新加载资料。", 404) from None
        if state.get('id') != session_id:
            raise Problem('任务标识与保存记录不一致。', 409)
        for image in state['images']:
            if not re.fullmatch(r'inputs/(?:product|reference)_[0-9]+\.(?:jpg|jpeg|png|webp)', image['file']):
                raise Problem('任务图片路径不在本任务允许范围内。', 409)
            safe_path(self.folder(session_id), image['file'])
        try:
            if quick_v1.is_v1(state):
                quick_v1.slots_for(state)
            if 'image_sizes' in state:
                targets = {slot['id'] for slot in state['quick_slots']} if quick_v1.is_v1(state) else {
                    image['id'] for image in state['images'] if image['role'] == ('product' if state.get('mode') == 'quick_redesign' else 'reference')}
                validate_image_sizes(state['image_sizes'], targets, SIZES)
        except ValueError as error:
            raise Problem(str(error), 409) from error
        return state

    def read_snapshot(self, session_id, revision):
        return task_state.read_snapshot(self.folder(session_id), revision, reader=self.read_json)

    def persist(self, state):
        task_state.write_snapshot_and_current(self.folder(state["id"]), state, writer=self.write_json)

    def begin_inputs(self, session_id):
        folder = self.folder(session_id)
        (folder / "inputs").mkdir(parents=True)
        return folder

    def write_input(self, folder, relative, data):
        with (folder / relative).open("xb") as stream:
            stream.write(data)

    def read_input(self, session_id, relative):
        return (self.folder(session_id) / relative).read_bytes()

    def write_texts(self, folder, text):
        self.write_json(folder / "inputs" / "texts.json", text, exclusive=True)

    def write_current(self, session_id):
        self.write_json(self.root / "current.json", {"id": session_id})

    def case_inputs(self, case):
        text = {"listing": (case / "listing.md").read_text(encoding="utf-8"),
                "description": "", "requirements": (case / "requirements.md").read_text(encoding="utf-8")}
        uploads = [(role, path.name, path.read_bytes()) for role, folder in [("product", "product"), ("reference", "references")]
                   for path in sorted((case / folder).iterdir()) if path.is_file() and path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
        return text, uploads

    def load_current(self):
        path = self.root / "current.json"
        return self.load(self.read_json(path)["id"]) if path.is_file() else None
