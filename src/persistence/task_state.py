"""Task state files and immutable revision snapshots, without business rules.

Callers validate task identity/revision and own mutation, locks and error mapping.
The writer is supplied to retain the existing serialization/sanitization policy.
Saving is deliberately snapshot-then-current, not a multi-file transaction.
"""

from file_ops import read_json, safe_path


class MissingStateFile(FileNotFoundError):
    """A state/snapshot path is not a regular file, matching the old read check."""


def _read(path, reader):
    if not path.is_file():
        raise MissingStateFile(path)
    return reader(path)


def read_current(task_folder, *, reader=read_json):
    """Read raw state; task ownership and payload validation belong to the caller."""
    return _read(safe_path(task_folder, "state.json"), reader)


def read_snapshot(task_folder, revision, *, reader=read_json):
    """Read one raw snapshot using the caller-validated revision."""
    return _read(safe_path(task_folder, f"versions/{revision:06}.json"), reader)


def write_snapshot_and_current(task_folder, state, *, writer):
    """Exclusively create the snapshot, then replace current state.

    Do not mutate state, advance revision, create task parents, catch errors or
    roll back a completed write. Retain the existing partial-failure behavior.
    """
    versions = task_folder / "versions"
    versions.mkdir(exist_ok=True)
    writer(versions / f"{state['revision']:06}.json", state, exclusive=True)
    writer(task_folder / "state.json", state)
