"""Compatibility entry points for the task-scoped experiment exporter.

The implementation belongs to image_workflow.experiment_export. Explicit
bindings preserve legacy callers that replace helper functions or constants.
"""

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import zipfile

from evidence import contains_private
from file_ops import ExportError, safe_path, sha256
from image_workflow import experiment_export as _implementation
from image_workflow.experiment_export import IMAGE_NAME, RUN_FILES, RUN_ID


def children(root, relative, pattern):
    return _implementation._children(root, relative, pattern, safe_path=safe_path)


def read_json(root, relative):
    return _implementation._read_json(root, relative, safe_path=safe_path)


def historical_case_match(state, session, case):
    return _implementation._historical_case_match(
        state, session, case, safe_path=safe_path, children=children,
        sha256=sha256, IMAGE_NAME=IMAGE_NAME)


def export_experiment(store, session_id):
    return _implementation._export_experiment(
        store, session_id, safe_path=safe_path, read_json=read_json,
        historical_case_match=historical_case_match, children=children,
        sha256=sha256, contains_private=contains_private, RUN_ID=RUN_ID,
        IMAGE_NAME=IMAGE_NAME, RUN_FILES=RUN_FILES,
        clock=lambda: datetime.now(timezone.utc))
