"""Immutable local provenance records committed with the imported assets."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

HISTORY_FOLDER = ".kicad-loader-history"
BACKUP_FOLDER = ".kicad-loader-backups"
ORIGIN_FILE = ".loader-archive-origin.json"


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_backup_files(plan):
    if not plan.backup_files or plan.backup_directory is not None:
        return
    root = Path(plan.output_root).resolve()
    folder = root / BACKUP_FOLDER / uuid.uuid4().hex
    backup_paths = []
    manifest = {"schema_version": 1, "operation": "update", "previous_event_id": plan.history.get("previous_event_id"), "files": []}
    for path, data in plan.backup_files.items():
        relative = path.relative_to(root)
        destination = folder / relative
        plan.add(destination, data)
        backup_paths.append(destination)
        manifest["files"].append({"relative_path": relative.as_posix(), "sha256": hashlib.sha256(data).hexdigest()})
    destination = folder / "manifest.json"
    plan.add(destination, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    backup_paths.append(destination)
    # Persist every backup before changing a component, under the same lock.
    plan.files = {**{path: plan.files[path] for path in backup_paths}, **plan.files}
    plan.backup_directory = folder
    plan.history["backup_folder"] = folder.relative_to(root).as_posix()


def add_history_record(plan):
    if plan.history is None:
        return None
    if plan.history_file is not None:
        return plan.history_file
    root = Path(plan.output_root).resolve()
    event_id = uuid.uuid4().hex
    record = dict(plan.history)
    record.update({"schema_version": 1, "event_id": event_id,
                   "imported_at_utc": datetime.now(timezone.utc).isoformat(),
                   "output_root": str(root), "warnings": list(plan.warnings), "outputs": []})
    for path, role in plan.assets.items():
        before = plan.before[path]
        data = plan.files.get(path, before)
        action = "created" if before is None else "updated" if path in plan.files else "reused"
        record["outputs"].append({"role": role, "relative_path": path.relative_to(root).as_posix(),
                                  "action": action, "sha256": hashlib.sha256(data).hexdigest(),
                                  "previous_sha256": hashlib.sha256(before).hexdigest() if before is not None else None})
    origin = Path(record["input_root"]) / ORIGIN_FILE
    record["source_archive"] = None
    if origin.is_file():
        try:
            metadata = json.loads(origin.read_text(encoding="utf-8"))
            if isinstance(metadata, dict) and isinstance(metadata.get("archive_path"), str) and isinstance(metadata.get("archive_sha256"), str):
                record["source_archive"] = metadata
        except (OSError, ValueError):
            # Existing cached exports may have no usable provenance metadata.
            pass
    path = root / HISTORY_FOLDER / f"{event_id}.json"
    plan.add(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    plan.history_file = path
    return path


def read_history(output_root):
    root = Path(output_root).resolve()
    folder = root / HISTORY_FOLDER
    records, notices = [], []
    if not folder.exists():
        return records, notices
    if folder.resolve() != folder or not folder.is_dir():
        return [], [f"History is not a regular folder inside the output root: {folder}"]
    for path in folder.glob("*.json"):
        try:
            if path.is_symlink() or path.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("linked or oversized record")
            data = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(data, dict) or data.get("schema_version") != 1
                    or not all(isinstance(data.get(key), str) for key in ("symbol", "category", "library_name", "symbol_format", "imported_at_utc", "event_id"))
                    or not isinstance(data.get("outputs"), list)):
                raise ValueError("unsupported or malformed history record")
            if not isinstance(data.get("warnings", []), list) or not all(isinstance(value, str) for value in data.get("warnings", [])):
                raise ValueError("malformed warnings")
            for output in data["outputs"]:
                if not isinstance(output, dict) or not all(isinstance(output.get(key), str) for key in ("role", "relative_path", "action", "sha256")):
                    raise ValueError("malformed output information")
            data["record_path"] = str(path)
            records.append(data)
        except (OSError, ValueError) as exc:
            notices.append(f"Could not read history record {path.name}: {exc}")
    records.sort(key=lambda record: (record["imported_at_utc"], record["event_id"]), reverse=True)
    return records, notices


def describe_record(record):
    archive = record.get("source_archive")
    archive_path = archive.get("archive_path") if isinstance(archive, dict) else None
    lines = [f"Component: {record['symbol']}", f"MPN: {record.get('mpn', '')}",
             f"Imported (UTC): {record['imported_at_utc']}",
             f"Operation: {record.get('operation', 'import')}",
             f"Backup folder: {record.get('backup_folder') or 'Not applicable'}",
             f"Category: {record['category']} | Library: {record['library_name']}",
             f"Symbol format: {record['symbol_format']} | Naming: {record.get('naming_mode', '')}",
             f"Provider: {record.get('provider') or 'Local export'}",
             f"Input folder: {record.get('input_root', '')}",
             f"Original ZIP: {archive_path or 'Not recorded (folder input or older ZIP cache)'}",
             f"Output root: {record.get('output_root', '')}", "", "Files at import time:"]
    lines.extend(f"{item['action'].title()} | {item['role']} | {item['relative_path']}" for item in record["outputs"])
    lines += ["", "Warnings acknowledged at import:", *record.get("warnings", [])]
    lines += ["", f"Record: {record.get('record_path', '')}",
              "This is an import-time record. Files may have changed afterwards; it does not certify their current state."]
    return "\n".join(lines)
