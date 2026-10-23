"""Reviewed removal and source-independent recovery of tracked native components."""
import copy
import json
from pathlib import Path
import re

from component_lifecycle import prepare_component
from component_restore import outputs, single_symbol
from component_updates import digest, recorded_path
from import_history import BACKUP_FOLDER, HISTORY_FOLDER, component_identity, latest_file_output, read_history
from library_core import ImportErrorDetail, Plan, check_destination, check_folders, child, children, dump, parse
from loader_settings import validate_output_layout


def retained_history(record):
    return {key: value for key, value in record.items() if key not in {
        "record_path", "outputs", "event_id", "schema_version", "imported_at_utc", "warnings", "backup_folder",
        "file_changes", "operation", "previous_event_id", "restored_from_event_id", "reverted_event_id", "restore_backup_folder",
        "moved_from", "move_sources", "removed_event_id", "recovery_backup_folder"}}


def build_remove_plan(output_root, event_id, protected_roots=(), model_variable="DVL_LIB_ROOT"):
    plan, records, record, source, old, tree, node, shared = prepare_component(
        output_root, event_id, protected_roots, model_variable)
    root = plan.output_root
    symbol = old["symbol"][0]
    if record["symbol_format"] == "packed":
        remaining = [copy.deepcopy(item) for item in tree if item is not node]
        snapshot = plan.before[symbol]
        plan.add(symbol, (dump(remaining) + "\n").encode("utf-8"), merge=True)
        if plan.before[symbol] != snapshot:
            raise ImportErrorDetail("Source changed during removal planning.")
        plan.related_assets[symbol] = "source_symbol_library"
        plan.backup_files[symbol] = snapshot
    else:
        plan.remove(symbol, "source_symbol")
    for role in ("footprint", "model"):
        if role in old:
            if role in shared:
                plan.related_assets[old[role][0]] = "source_" + role
            else:
                plan.remove(old[role][0], "source_" + role)
    plan.history = retained_history(record)
    plan.history.update({"operation": "remove", "previous_event_id": record["event_id"]})
    plan.info = [f"Remove component: {record['symbol']}", f"Category: {record['category']} / {record['library_name']}",
                 f"Library root: {root}", "Backups and a removal history record are saved before removing files."]
    if record["symbol_format"] == "packed":
        plan.info.append("Remove only the selected packed symbol; preserve other symbols and the library file.")
    plan.info.extend(f"Remove after backup: {p.relative_to(root)}" for p in plan.removals)
    plan.info.extend(f"Keep shared {role}: {old[role][0].relative_to(root)}" for role in sorted(shared))
    plan.warnings = ["Existing schematic/PCB instances and external libraries/projects are not inspected or changed. They may still reference this component.",
                     "Sharing checks cover the selected output root only. Shared source footprints/models are retained; empty libraries/folders remain.",
                     "Recover removed… needs the local history, unchanged retained assets and verified backups. Do not delete the history or backup folders.",
                     "Multi-file changes roll back on I/O errors, but are not atomic against power loss. Review affected designs in KiCad."]
    return plan


def build_recover_plan(output_root, event_id, protected_roots=()):
    root = Path(output_root).resolve()
    protected = tuple(Path(p).resolve() for p in protected_roots)
    validate_output_layout(root, protected)
    records, notices = read_history(root)
    if notices or len({r["event_id"] for r in records}) != len(records):
        raise ImportErrorDetail("History cannot be fully verified. Resolve corrupt or duplicate records before recovery.")
    selected = next((r for r in records if r["event_id"] == event_id), None)
    if selected is None or selected.get("operation") != "remove":
        raise ImportErrorDetail("Select a recorded component removal.")
    latest = next(r for r in records if component_identity(r) == component_identity(selected))
    if latest["event_id"] != event_id:
        raise ImportErrorDetail("This component has a later operation or was already recovered/reimported.")
    previous = next((r for r in records if r["event_id"] == selected.get("previous_event_id")), None)
    if (previous is None or component_identity(previous) != component_identity(selected)
            or previous.get("mpn") != selected.get("mpn") or previous.get("operation") == "remove"):
        raise ImportErrorDetail("The component version before removal cannot be verified.")
    old = outputs(root, previous)
    plan = Plan(output_root=root, protected_roots=protected)

    def watch(folder):
        check_destination(folder, root, protected)
        if folder.resolve() != folder or (folder.exists() and not folder.is_dir()):
            raise ImportErrorDetail(f"Cannot verify recovery folder: {folder}")
        plan.dependency_directories[folder] = tuple(sorted(p.name for p in folder.iterdir())) if folder.is_dir() else None

    def snapshot(path, missing=False):
        check_destination(path, root, protected)
        if path.resolve() != path or path.is_symlink() or (path.exists() and not path.is_file()):
            raise ImportErrorDetail(f"Cannot use linked or non-file recovery path: {path}")
        if not path.exists() and not missing:
            raise ImportErrorDetail(f"Missing recovery dependency: {path}")
        data = path.read_bytes() if path.exists() else None
        if path in plan.before and plan.before[path] != data:
            raise ImportErrorDetail("A recovery dependency changed during review.")
        plan.before[path] = data
        return data

    watch(root / HISTORY_FOLDER)
    for record in records:
        data = snapshot(Path(record["record_path"]))
        if json.loads(data.decode("utf-8")) != {k: v for k, v in record.items() if k != "record_path"}:
            raise ImportErrorDetail("History changed during recovery planning.")
    folder_name = selected.get("backup_folder", "")
    if not isinstance(folder_name, str) or not re.fullmatch(re.escape(BACKUP_FOLDER) + r"/[0-9a-f]{32}", folder_name):
        raise ImportErrorDetail("Invalid removal backup folder.")
    folder = recorded_path(root, folder_name)
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > 5 * 1024 * 1024:
        raise ImportErrorDetail("Removal backup manifest is missing or oversized.")
    manifest = json.loads(snapshot(manifest_path).decode("utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("operation") != "remove"
            or manifest.get("previous_event_id") != previous["event_id"] or not isinstance(manifest.get("files"), list)):
        raise ImportErrorDetail("Backup manifest does not match the selected removal.")
    changes = selected.get("file_changes", [])
    expected_paths = {p.relative_to(root).as_posix() for p, _ in old.values()}
    if (len(changes) != len(old) or {c["relative_path"] for c in changes} != expected_paths
            or any(c["action"] not in {"removed", "updated", "reused"} for c in changes)):
        raise ImportErrorDetail("Removal history does not match the previous component assets.")
    changed = {c["relative_path"]: c for c in changes if c["action"] in {"removed", "updated"}}
    manifest_files = {}
    for item in manifest["files"]:
        if (not isinstance(item, dict) or not isinstance(item.get("relative_path"), str)
                or not isinstance(item.get("sha256"), str) or item["relative_path"] in manifest_files):
            raise ImportErrorDetail("Malformed or duplicate removal backup entry.")
        recorded_path(root, item["relative_path"])
        manifest_files[item["relative_path"]] = item["sha256"]
    if set(manifest_files) != set(changed):
        raise ImportErrorDetail("Backup files do not match the removal changes.")
    symbol_path = old["symbol"][0]
    for name in ("Symbols", "Footprints", "3DModels"):
        watch(root / name)
    for path, _ in old.values():
        watch(path.parent)
    # Detect a same-name symbol in a differently named unpacked file as well.
    if previous["symbol_format"] == "unpacked":
        for path in symbol_path.parent.glob("*.kicad_sym"):
            tree = parse(snapshot(path).decode("utf-8-sig"))
            if tree[0] != "kicad_symbol_lib" or not child(tree, "version"):
                raise ImportErrorDetail("Cannot verify the destination symbol library.")
            if any(str(n[1]).casefold() == previous["symbol"].casefold() for n in children(tree, "symbol")):
                raise ImportErrorDetail("The destination already contains this symbol. Recovery never replaces it.")
    for role, (path, item) in old.items():
        relative = path.relative_to(root).as_posix()
        change = next(c for c in changes if c["relative_path"] == relative)
        current = snapshot(path, missing=change["action"] == "removed")
        restored = current
        if relative in changed:
            restored = snapshot(folder / path.relative_to(root))
            if (digest(restored) != manifest_files[relative]
                    or digest(restored) != change.get("previous_sha256")):
                raise ImportErrorDetail("Removal backup contents do not match their recorded hashes.")
        elif current is None or digest(current) != item["sha256"] or digest(current) != change["sha256"]:
            raise ImportErrorDetail("A retained shared asset was edited or is missing. Recovery blocked.")
        if role == "symbol":
            backup_tree, node = single_symbol(restored, previous)
            if previous.get("symbol_sha256"):
                if digest(dump(node).encode("utf-8")) != previous["symbol_sha256"]:
                    raise ImportErrorDetail("Backup symbol fingerprint differs from the previous version.")
            elif digest(restored) != item["sha256"]:
                raise ImportErrorDetail("Older history cannot verify the removed symbol.")
            if previous["symbol_format"] == "packed":
                latest_file = latest_file_output(records, relative)
                if current is None or latest_file is None or digest(current) != latest_file["sha256"]:
                    raise ImportErrorDetail("Packed library changed outside recorded history. Recovery blocked.")
                tree = parse(current.decode("utf-8-sig"))
                if (tree[0] != "kicad_symbol_lib" or child(tree, "version") != child(backup_tree, "version")):
                    raise ImportErrorDetail("Native packed library version changed. No conversion is performed.")
                if any(str(n[1]).casefold() == previous["symbol"].casefold() for n in children(tree, "symbol")):
                    raise ImportErrorDetail("The destination already contains this symbol. Recovery never replaces it.")
                tree.append(copy.deepcopy(node))
                restored = (dump(tree) + "\n").encode("utf-8")
            plan.history = retained_history(previous)
            plan.history["symbol_sha256"] = digest(dump(node).encode("utf-8"))
        elif relative in changed and digest(restored) != item["sha256"]:
            raise ImportErrorDetail("Backup asset differs from the previous component version.")
        before = current
        plan.add(path, restored, merge=role == "symbol" and previous["symbol_format"] == "packed", role=role)
        if plan.before[path] != before:
            raise ImportErrorDetail("Destination changed during recovery planning.")
        if before is not None and before != restored:
            plan.backup_files[path] = before
    plan.history.update({"operation": "recover", "previous_event_id": selected["event_id"],
                         "removed_event_id": selected["event_id"], "restored_from_event_id": previous["event_id"],
                         "recovery_backup_folder": folder_name})
    plan.folders = tuple(sorted({p.parent for p in plan.assets}))
    check_folders(plan.folders)
    plan.info = [f"Recover removed component: {previous['symbol']}", f"Category: {previous['category']} / {previous['library_name']}",
                 f"Recovery backup: {folder}", "Unrelated packed symbols and existing identical resources are preserved."]
    plan.info.extend(f"Recover {role}: {p.relative_to(root)}" for p, role in plan.assets.items())
    plan.warnings = ["Recovery restores library assets only. Existing schematic/PCB instances are not changed; review them in KiCad.",
                     "The original removal history and backups remain. Other format copies are not synchronised.",
                     "I/O errors roll back the transaction; abrupt power loss is not atomic across files."]
    return plan
