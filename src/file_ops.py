"""Filesystem primitives only; callers own sanitization and business rules."""

import hashlib
import json
from pathlib import Path, PurePosixPath


class ExportError(ValueError):
    """Historical name retained for existing handlers and recorded error types.

    Re-exported by experiment_export; shared path checks must not import an
    export workflow merely to raise the same backwards-compatible exception.
    """


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


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    """Read UTF-8 JSON, preserving filesystem and JSON decoding exceptions."""
    return json.loads(safe_path(path.parent, path.name).read_text(encoding="utf-8"))


def _json_text(value, transform):
    # Transformation is caller-owned, after path validation and before writing.
    if transform is not None:
        value = transform(value)
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_json_atomic(path, value, *, transform=None):
    """Replace one file using its existing .tmp sibling; no directory creation.

    This is a single-file replacement, not a multi-file transaction. A failed
    replacement retains the temporary file, matching the existing writers.
    """
    path = safe_path(path.parent, path.name)
    text = _json_text(value, transform)
    temporary = safe_path(path.parent, path.name + '.tmp')
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json_exclusive(path, value, *, transform=None):
    """Create immutable JSON with mode x; never replace an existing file."""
    path = safe_path(path.parent, path.name)
    text = _json_text(value, transform)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
