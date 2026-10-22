"""Session-only arrival tracking and stable ZIP preparation; no provider requests."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import threading

from archive_import import discard_extraction, extract_native_zip, MAX_TOTAL_BYTES
from import_history import ORIGIN_FILE, file_hash

PARTIAL_SUFFIXES = (".crdownload", ".part", ".download", ".tmp")


def fingerprint(path):
    value = Path(path).stat()
    return value.st_size, value.st_mtime_ns


@dataclass
class ZipArrivalTracker:
    previous: dict = field(default_factory=dict)
    pending: dict = field(default_factory=dict)
    stable_seconds: float = 6.0

    def baseline(self, snapshot):
        self.previous = dict(snapshot)
        self.pending.clear()

    def observe(self, snapshot, now):
        for path, signature in snapshot.items():
            if self.previous.get(path) != signature:
                self.pending[path] = (signature, now)
        self.previous = dict(snapshot)
        self.pending = {path: value for path, value in self.pending.items() if path in snapshot}

    def ready(self, now):
        candidates = [(path, signature) for path, (signature, since) in self.pending.items()
                      if now - since >= self.stable_seconds and signature[0] > 0]
        return sorted(candidates, key=lambda item: (-item[1][1], item[0].name.casefold()))

    def consume(self, path, signature):
        if self.pending.get(path, (None,))[0] == signature:
            self.pending.pop(path, None)


def has_partial(path):
    return any(Path(str(path) + suffix).exists() for suffix in PARTIAL_SUFFIXES)


class ArrivalChanged(ValueError):
    pass


def prepare_arrival(path, workspace, signature, cancelled=None):
    """Extract a verified snapshot of a stable candidate into the normal ZIP cache."""
    path = Path(path)
    cancelled = cancelled if cancelled is not None else threading.Event()
    extracted = None
    try:
        if cancelled.is_set():
            raise ArrivalChanged("Automatic ZIP loading was cancelled.")
        if path.is_symlink() or has_partial(path) or fingerprint(path) != signature:
            raise ArrivalChanged("The ZIP is still changing. Waiting for a stable download.")
        if signature[0] > MAX_TOTAL_BYTES:
            raise ValueError("ZIP is too large for automatic loading. Review it and use Open ZIP manually.")
        before_hash = file_hash(path)
        extracted = extract_native_zip(path, workspace)
        origin = json.loads((extracted / ORIGIN_FILE).read_text(encoding="utf-8"))
        if (cancelled.is_set() or has_partial(path) or fingerprint(path) != signature
                or origin["archive_sha256"] != before_hash):
            raise ArrivalChanged("The ZIP changed during validation. Waiting for a stable download.")
        return extracted
    except BaseException:
        if extracted is not None:
            discard_extraction(extracted, workspace)
        raise
