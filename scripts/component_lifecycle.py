"""Shared verification and ownership checks for tracked component lifecycle actions."""
import json
from pathlib import Path

from component_restore import outputs, single_symbol
from component_updates import digest, recorded_path
from import_history import (HISTORY_FOLDER, component_identity, current_components,
                            latest_file_output, read_history)
from library_core import (ImportErrorDetail, Plan, basename, check_destination,
                          child, children, dump, parse, prop, require_kicad9,
                          KICAD9_SYMBOL_VERSION)
from library_layout import LibraryCategory
from loader_settings import validate_model_paths, validate_output_layout


def active_record(records, event_id):
    record = next((item for item in records if item["event_id"] == event_id), None)
    if record is None:
        raise ImportErrorDetail("The selected component history record is unavailable.")
    active = current_components(records).get(component_identity(record))
    if active is None or active["event_id"] != event_id:
        raise ImportErrorDetail("Select the latest active record for this component. It has a later operation, was moved or removed.")
    return record


def prepare_component(output_root, event_id, protected_roots=(), model_variable="DVL_LIB_ROOT"):
    root = Path(output_root).resolve()
    model_variable = validate_model_paths("variable", model_variable)
    protected = tuple(Path(path).resolve() for path in protected_roots)
    validate_output_layout(root, protected)
    records, notices = read_history(root)
    if notices or len({item["event_id"] for item in records}) != len(records):
        raise ImportErrorDetail("History cannot be fully verified. Resolve corrupt or duplicate records before changing a component. " + " ".join(notices))
    record = active_record(records, event_id)
    source = LibraryCategory(record["category"], record["library_name"], record.get("model_folder")).validated()
    mode = record["symbol_format"]
    old = outputs(root, record)
    plan = Plan(output_root=root, protected_roots=protected)

    def inspect(path):
        check_destination(path, root, protected)
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ImportErrorDetail(f"Cannot verify a missing or linked file: {path}")
        data = path.read_bytes()
        if path in plan.before and plan.before[path] != data:
            raise ImportErrorDetail("A file changed while the component was being reviewed.")
        plan.before[path] = data
        return data

    def watch(folder):
        check_destination(folder, root, protected)
        if folder.resolve() != folder or (folder.exists() and not folder.is_dir()):
            raise ImportErrorDetail(f"Cannot verify library folder: {folder}")
        plan.dependency_directories[folder] = tuple(sorted(p.name for p in folder.iterdir())) if folder.is_dir() else None

    # Capture dependencies before examining any ownership/reference decisions.
    watch(root / HISTORY_FOLDER)
    for item in records:
        path = Path(item["record_path"])
        data = inspect(path)
        if json.loads(data.decode("utf-8")) != {key: value for key, value in item.items() if key != "record_path"}:
            raise ImportErrorDetail("History changed while planning the component action.")
    for role, (path, item) in old.items():
        data = inspect(path)
        expected = item["sha256"]
        if role == "symbol" and mode == "packed":
            latest = latest_file_output(records, path.relative_to(root).as_posix())
            expected = latest["sha256"] if latest else None
        if digest(data) != expected:
            raise ImportErrorDetail(f"Tracked {role} changed outside the recorded history. Manual edits are protected.")
    symbol_path = old["symbol"][0]
    source_tree, original_node = single_symbol(plan.before[symbol_path], record)
    if len([node for node in children(source_tree, "symbol") if str(node[1]).casefold() == record["symbol"].casefold()]) != 1:
        raise ImportErrorDetail("The source library has ambiguous symbol names.")
    symbol_fingerprint = digest(dump(original_node).encode("utf-8"))
    if record.get("symbol_sha256"):
        if symbol_fingerprint != record["symbol_sha256"]:
            raise ImportErrorDetail("The source symbol was manually edited. Operation blocked.")
    elif digest(plan.before[symbol_path]) != old["symbol"][1]["sha256"]:
        raise ImportErrorDetail("Older packed history cannot verify this symbol after later library changes.")
    if "model" in old and "footprint" not in old:
        raise ImportErrorDetail("History has a model without a tracked footprint.")
    old_reference = f"{source.library_name}:{old['footprint'][0].stem}" if "footprint" in old else ""
    if prop(original_node, "Footprint") != old_reference:
        raise ImportErrorDetail("The symbol footprint reference does not match the tracked component.")
    if mode == "packed":
        require_kicad9(source_tree, KICAD9_SYMBOL_VERSION, "The source library")

    symbol_trees, footprint_trees = {}, {}
    for name in ("Symbols", "Footprints", "3DModels"):
        watch(root / name)
    symbol_paths = list((root / "Symbols").glob("*.kicad_sym"))
    for folder in (root / "Symbols").glob("*.kicad_symdir"):
        watch(folder)
        symbol_paths.extend(folder.glob("*.kicad_sym"))
    for path in symbol_paths:
        tree = parse(inspect(path).decode("utf-8-sig"))
        if tree[0] != "kicad_symbol_lib" or not child(tree, "version"):
            raise ImportErrorDetail(f"Cannot inspect symbol references in {path}")
        symbol_trees[path] = tree
        for node in children(tree, "symbol"):
            if path == symbol_path and str(node[1]) == record["symbol"]:
                continue
            extends = child(node, "extends")
            if extends and ((str(extends[1]) == record["symbol"] and
                             (path == symbol_path or (mode == "unpacked" and path.parent == symbol_path.parent)))
                            or str(extends[1]) == f"{source.library_name}:{record['symbol']}"):
                raise ImportErrorDetail("Another symbol inherits from this symbol. Move its dependants separately before relocating the base.")
    for folder in (root / "Footprints").glob("*.pretty"):
        watch(folder)
        for path in folder.glob("*.kicad_mod"):
            tree = parse(inspect(path).decode("utf-8-sig"))
            if tree[0] not in {"module", "footprint"}:
                raise ImportErrorDetail(f"Cannot inspect model references in {path}")
            footprint_trees[path] = tree
    shared = set()
    # Retain assets claimed by another currently tracked component, even if its
    # current references are unavailable or stale. No silent ownership transfer.
    for other in current_components(records).values():
        if other is None or other["event_id"] == record["event_id"]:
            continue
        for item in other["outputs"]:
            path = recorded_path(root, item["relative_path"])
            for role in ("footprint", "model"):
                if role in old and old[role][0] == path:
                    shared.add(role)
    if "footprint" in old:
        for path, tree in symbol_trees.items():
            for node in children(tree, "symbol"):
                if path == symbol_path and str(node[1]) == record["symbol"]:
                    continue
                if str(prop(node, "Footprint")).casefold() == old_reference.casefold():
                    shared.add("footprint")
    if "model" in old:
        model = old["model"][0]
        for path, tree in footprint_trees.items():
            if "footprint" in old and path == old["footprint"][0] and "footprint" not in shared:
                continue
            for reference in children(tree, "model"):
                raw = str(reference[1]).replace("\\", "/")
                resolved = raw.replace("${" + model_variable + "}", root.as_posix())
                if Path(resolved).is_absolute() and "${" not in resolved:
                    if Path(resolved).resolve() == model:
                        shared.add("model")
                elif basename(raw).casefold() == model.name.casefold():
                    shared.add("model")
        if "footprint" in shared:
            shared.add("model")

    return plan, records, record, source, old, source_tree, original_node, shared
