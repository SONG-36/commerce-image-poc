"""Scoped Run/review file access, preserving the existing layout and writes.

No confirmation, version selection, Pass decisions or execution locks live here.
Callers supply validated path builders and the existing sanitization policy.
"""

from dataclasses import dataclass
import json
from typing import Callable

from file_ops import read_json, safe_path, write_json_atomic


@dataclass(frozen=True)
class ReviewFiles:
    card_folder: Callable
    run_folder: Callable
    pointer_reader: Callable = read_json
    pointer_writer: Callable = write_json_atomic

    def run_records(self):
        """Yield original JSON in directory order; skip missing Run records only."""
        folder = self.card_folder()
        runs = safe_path(folder, 'runs')
        if runs.is_dir():
            for child in sorted(runs.iterdir()):
                path = safe_path(folder, 'runs/' + child.name + '/run.json')
                if path.is_file():
                    yield child.name, json.loads(path.read_text())

    def read_image(self, run_id):
        folder = self.run_folder(run_id)
        record = json.loads(safe_path(folder, 'run.json').read_text())
        data = safe_path(folder, 'image.png').read_bytes()
        return record, data

    def read_pointer(self, folder, *, checked=False):
        # Final export historically checks the pointer path even when missing;
        # review operations use the existing reader only when is_file() is true.
        path = safe_path(folder, 'current.json') if checked else folder / 'current.json'
        return self.pointer_reader(path) if path.is_file() else {}

    def save_review(self, folder, event, pointer, *, sanitize):
        """Create event exclusively, then replace pointer; not a transaction.

        Keep the direct event serialization INSIDE open('x'). Sanitizer failures
        therefore still leave an empty event file and the old current pointer.
        """
        events = safe_path(folder, 'reviews')
        events.mkdir(exist_ok=True)
        with (events / (event['id'] + '.json')).open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(sanitize(event), ensure_ascii=False, indent=2) + '\n')
        self.pointer_writer(folder / 'current.json', pointer, transform=sanitize)
