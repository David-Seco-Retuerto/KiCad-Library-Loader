"""Restore the latest tracked update without replacing unrelated packed symbols."""
import copy
import json
from pathlib import Path
import re

from component_updates import digest, recorded_path, verify_replacement_dependencies
from import_history import BACKUP_FOLDER, read_history, component_identity, current_components, latest_file_output
from library_core import ImportErrorDetail, Plan, check_destination, children, dump, parse


def identity(record):
    return (record["symbol"], record["category"], record["library_name"], record["symbol_format"])


def outputs(root, record):
    result = {}
    for item in record["outputs"]:
        role = item["role"]
        if role not in {"symbol", "footprint", "model"} or role in result:
            raise ImportErrorDetail("History has ambiguous component outputs.")
        path = recorded_path(root, item["relative_path"])
        relative = path.relative_to(root)
        library = record["library_name"]
        expected_symbol = (Path("Symbols") / (library + ".kicad_sym") if record["symbol_format"] == "packed"
                           else Path("Symbols") / (library + ".kicad_symdir") / (record["symbol"] + ".kicad_sym"))
        valid = ((role == "symbol" and relative == expected_symbol)
                 or (role == "footprint" and len(relative.parts) == 3
                     and relative.parts[:2] == ("Footprints", library + ".pretty") and path.suffix == ".kicad_mod")
                 or (role == "model" and len(relative.parts) == 3 and relative.parts[0] == "3DModels"
                     and relative.parts[1] == record.get("model_folder") and path.suffix.lower() in {".stp", ".step"}))
        if not valid or record["symbol_format"] not in {"packed", "unpacked"}:
            raise ImportErrorDetail("History output does not match the recorded native library layout.")
        if path in (value[0] for value in result.values()):
            raise ImportErrorDetail("History repeats an output path.")
        result[role] = (path, item)
    if "symbol" not in result:
        raise ImportErrorDetail("History has no symbol output.")
    return result


def single_symbol(data, record):
    tree = parse(data.decode("utf-8-sig"))
    if tree[0] != "kicad_symbol_lib":
        raise ImportErrorDetail("Expected a native symbol library.")
    nodes = children(tree, "symbol")
    target = [node for node in nodes if str(node[1]) == record["symbol"]]
    if len(target) != 1 or (record["symbol_format"] == "unpacked" and len(nodes) != 1):
        raise ImportErrorDetail("The tracked symbol is missing, renamed, duplicated or shares an unpacked file.")
    return tree, target[0]


def build_restore_plan(output_root, event_id, protected_roots=(), model_variable="DVL_LIB_ROOT"):
    root = Path(output_root).resolve()
    records, notices = read_history(root)
    if notices:
        raise ImportErrorDetail("History could not be fully verified. " + " ".join(notices))
    if len({record["event_id"] for record in records}) != len(records):
        raise ImportErrorDetail("History contains duplicate event identifiers.")
    selected = next((record for record in records if record["event_id"] == event_id), None)
    if selected is None or selected.get("operation") != "update":
        raise ImportErrorDetail("Select a recorded component update with a backup. Initial imports and restorations cannot be undone here.")
    latest = next(record for record in records if identity(record) == identity(selected))
    active = current_components(records).get(component_identity(selected))
    if latest["event_id"] != event_id or active is None or active["event_id"] != event_id:
        raise ImportErrorDetail("This component has a later recorded operation. Only its latest update can be restored.")
    previous = next((record for record in records if record["event_id"] == selected.get("previous_event_id")), None)
    if previous is None or identity(previous) != identity(selected):
        raise ImportErrorDetail("The previous component version cannot be verified from history.")
    if previous.get("mpn") != selected.get("mpn"):
        raise ImportErrorDetail("The recorded component MPN changed between versions. Restore blocked.")
    current_outputs, previous_outputs = outputs(root, selected), outputs(root, previous)
    if {role: path for role, (path, _) in current_outputs.items()} != {role: path for role, (path, _) in previous_outputs.items()}:
        raise ImportErrorDetail("Restoring cannot add, remove, rename or relocate component assets.")
    folder_name = selected.get("backup_folder", "")
    if not isinstance(folder_name, str) or not re.fullmatch(re.escape(BACKUP_FOLDER) + r"/[0-9a-f]{32}", folder_name):
        raise ImportErrorDetail("The recorded backup folder is invalid.")
    folder = recorded_path(root, folder_name)
    plan = Plan(output_root=root, protected_roots=tuple(Path(p).resolve() for p in protected_roots))

    def read_snapshot(path):
        check_destination(path, root, plan.protected_roots)
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ImportErrorDetail(f"Missing or linked file cannot be restored safely: {path}")
        data = path.read_bytes()
        if path in plan.before and data != plan.before[path]:
            raise ImportErrorDetail("A restore dependency changed during review.")
        plan.before[path] = data
        return data

    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > 5 * 1024 * 1024:
        raise ImportErrorDetail("Backup manifest is missing or oversized.")
    manifest = json.loads(read_snapshot(manifest_path).decode("utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("operation") != "update"
            or manifest.get("previous_event_id") != previous["event_id"]
            or not isinstance(manifest.get("files"), list)):
        raise ImportErrorDetail("Backup manifest does not match the selected update.")
    manifest_files = {}
    for item in manifest["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("relative_path"), str) or not isinstance(item.get("sha256"), str):
            raise ImportErrorDetail("Backup manifest contains invalid file information.")
        path = recorded_path(root, item["relative_path"])
        if path in manifest_files:
            raise ImportErrorDetail("Backup manifest contains duplicate files.")
        manifest_files[path] = item["sha256"]
    changed = {path for path, item in current_outputs.values() if item["action"] == "updated"}
    if not changed or set(manifest_files) != changed:
        raise ImportErrorDetail("Backup files do not match the files changed by this update.")
    desired = {}
    for role, (path, item) in current_outputs.items():
        data = read_snapshot(path)
        if role == "symbol" and selected["symbol_format"] == "packed":
            latest_file = latest_file_output(records, path.relative_to(root).as_posix())
            if latest_file is None or digest(data) != latest_file["sha256"]:
                raise ImportErrorDetail("Packed library was edited outside the recorded history. Manual edits are protected.")
        elif digest(data) != item["sha256"]:
            raise ImportErrorDetail(f"Tracked {role} was edited after the update. Manual edits are protected.")
        before_version = previous_outputs[role][1]
        restored = data
        if path in changed:
            restored = read_snapshot(folder / path.relative_to(root))
            if digest(restored) != manifest_files[path] or digest(restored) != item.get("previous_sha256"):
                raise ImportErrorDetail("Backup contents do not match their recorded hashes.")
            if role != "symbol" or selected["symbol_format"] != "packed":
                if digest(restored) != before_version["sha256"]:
                    raise ImportErrorDetail("Backup does not match the previous component version.")
        elif role != "symbol" and digest(data) != before_version["sha256"]:
            raise ImportErrorDetail("Unchanged assets do not match the previous component version.")
        if role == "symbol":
            current_tree, current_node = single_symbol(data, selected)
            if selected.get("symbol_sha256"):
                if digest(dump(current_node).encode("utf-8")) != selected["symbol_sha256"]:
                    raise ImportErrorDetail("The tracked symbol was manually edited. Restore blocked.")
            elif digest(data) != item["sha256"]:
                raise ImportErrorDetail("Older packed history cannot verify this symbol after later changes.")
            _, restored_node = single_symbol(restored, previous)
            if previous.get("symbol_sha256"):
                if digest(dump(restored_node).encode("utf-8")) != previous["symbol_sha256"]:
                    raise ImportErrorDetail("Backup symbol does not match the previous component fingerprint.")
            elif digest(restored) != before_version["sha256"]:
                raise ImportErrorDetail("Older history cannot verify the backup symbol.")
            symbol_hash = digest(dump(restored_node).encode("utf-8"))
            if selected["symbol_format"] == "packed":
                merged = copy.deepcopy(current_tree)
                index = next(
                    i for i, node in enumerate(merged) if isinstance(node, list) and node and node[0] == "symbol" and str(node[1]) == selected["symbol"])
                merged[index] = copy.deepcopy(restored_node)
                restored = (dump(merged) + "\n").encode("utf-8") if dump(current_node) != dump(restored_node) else data
        desired[path] = (role, restored)
    if not any(plan.before[path] != data for path, (_, data) in desired.items()):
        raise ImportErrorDetail("No component changes to restore.")
    # Preserve provenance of the restored version, without rereading possibly replaced source exports.
    plan.history = {key: value for key, value in previous.items() if key not in {
        "record_path", "outputs", "event_id", "schema_version", "imported_at_utc", "warnings",
        "backup_folder", "operation", "previous_event_id", "restored_from_event_id", "reverted_event_id", "restore_backup_folder", "file_changes", "moved_from", "move_sources"}}
    plan.history.update({"operation": "restore", "previous_event_id": selected["event_id"],
                         "reverted_event_id": selected["event_id"], "restored_from_event_id": previous["event_id"],
                         "restore_backup_folder": folder_name, "symbol_sha256": symbol_hash,
                         "naming_mode": "Preserve existing names"})
    plan.warnings = ["Only the selected component is restored. Already placed schematic and PCB instances are not changed.",
                     "Check pin/pad compatibility, geometry and 3D alignment before updating existing designs.",
                     "Shared-reference checks cover this output root; external projects and libraries are not inspected."]
    plan.info = [f"Restore component: {selected['symbol']}", f"Revert update: {selected['event_id']}",
                 f"Restore version: {previous['event_id']}", f"Library root: {root}",
                 "Unrelated symbols in a packed library are preserved. Current changed files will be backed up first."]
    for path, (role, data) in desired.items():
        snapshot = plan.before[path]
        plan.add(path, data, merge=True, role=role)
        if plan.before[path] != snapshot:
            raise ImportErrorDetail("Destination changed during restore planning. Reopen the review.")
        if data != snapshot:
            plan.backup_files[path] = snapshot
    changed_assets = {path for path, (role, data) in desired.items()
                      if role in {"footprint", "model"} and data != plan.before[path]}
    old = {role: (path, item["sha256"]) for role, (path, item) in current_outputs.items()}
    verify_replacement_dependencies(plan, records, old, selected, changed_assets,
                                    selected["symbol"], selected["library_name"], model_variable)
    return plan
