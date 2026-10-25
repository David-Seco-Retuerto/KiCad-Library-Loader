"""Conservative in-place component updates, backed by import history."""
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile

from import_history import read_history, component_identity, current_components, latest_file_output
from library_core import (ImportErrorDetail, Plan, build_plan, check_destination, child, children,
                          dump, parse, prop, read_tree, require_kicad9, KICAD9_SYMBOL_VERSION)
from library_layout import DEFAULT_CATEGORIES


def digest(data):
    return hashlib.sha256(data).hexdigest()


def recorded_path(root, value):
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in value:
        raise ImportErrorDetail("History contains an unsafe output path.")
    result = root.joinpath(*path.parts)
    if not result.resolve().is_relative_to(root):
        raise ImportErrorDetail("A historical output resolves outside the library root.")
    return result


def build_update_plan(workspace, inv, symbol_key, fp_key, model_key, category, mode="Suggestion", custom="",
                      symbol_format="unpacked", output_root=None, input_roots=None, model_path_mode="variable",
                      model_variable="DVL_LIB_ROOT", category_config=None):
    root = Path(output_root or workspace).resolve()
    layout = category_config or next((item for item in DEFAULT_CATEGORIES if item.name == category), None)
    if layout is None or symbol_key not in inv.symbols:
        raise ImportErrorDetail("Choose a configured category and source symbol.")
    symbol = inv.symbols[symbol_key]
    records, notices = read_history(root)
    if notices:
        raise ImportErrorDetail("History could not be fully verified. Resolve the history errors before updating. " + " ".join(notices))
    matching = [record for record in records if record["symbol"].casefold() == symbol.name.casefold()
                and record["category"] == category and record["library_name"] == layout.library_name
                and record["symbol_format"] == symbol_format]
    if not matching:
        raise ImportErrorDetail("No matching import history for this component, category and symbol format. Import an untracked component separately; automatic adoption and migration are not supported yet.")
    previous = matching[0]
    active = current_components(records).get(component_identity(previous))
    if active is None or active["event_id"] != previous["event_id"]:
        raise ImportErrorDetail("This component was moved out of this category or removed. Choose its active category, or recover it from history before updating.")
    if previous.get("mpn") and previous["mpn"] != symbol.mpn:
        raise ImportErrorDetail("The source MPN differs from the tracked component. Review the selected symbol.")
    old = {}
    for item in previous["outputs"]:
        role = item["role"]
        if role in old or role not in {"symbol", "footprint", "model"}:
            raise ImportErrorDetail("History has ambiguous component outputs.")
        old[role] = (recorded_path(root, item["relative_path"]), item["sha256"])
    if "symbol" not in old or bool(fp_key) != ("footprint" in old) or bool(model_key) != ("model" in old):
        raise ImportErrorDetail("This update must retain the existing symbol/footprint/model set. Adding or removing assets needs a separate workflow.")
    snapshots = {}
    for role, (path, expected_hash) in old.items():
        check_destination(path, root, tuple(Path(p).resolve() for p in (input_roots or ())))
        if not path.is_file():
            raise ImportErrorDetail(f"Tracked {role} is missing: {path}")
        data = path.read_bytes()
        snapshots[path] = data
        if role == "symbol" and symbol_format == "packed":
            latest = latest_file_output(records, path.relative_to(root).as_posix())
            if latest is None or digest(data) != latest["sha256"]:
                raise ImportErrorDetail("Packed symbol library changed outside the recorded history. Manual changes are protected.")
        elif digest(data) != expected_hash:
            raise ImportErrorDetail(f"Tracked {role} was edited since its last import. Manual edits are protected: {path}")
    current_tree = parse(snapshots[old["symbol"][0]].decode("utf-8-sig"))
    current_nodes = children(current_tree, "symbol")
    existing = [node for node in current_nodes if str(node[1]) == symbol.name]
    if len(existing) != 1 or (symbol_format == "unpacked" and len(current_nodes) != 1):
        raise ImportErrorDetail("The destination symbol is missing, renamed, duplicated or shares an unpacked file. Update blocked.")
    if previous.get("symbol_sha256"):
        if digest(dump(existing[0]).encode("utf-8")) != previous["symbol_sha256"]:
            raise ImportErrorDetail("The tracked symbol was manually edited. Update blocked.")
    elif digest(snapshots[old["symbol"][0]]) != old["symbol"][1]:
        raise ImportErrorDetail("Older packed history lacks a per-symbol fingerprint and the library has changed. This component cannot be verified for automatic update.")
    preserved_name = old["footprint"][0].stem if fp_key else ""
    with tempfile.TemporaryDirectory(prefix="kicad-update-plan-") as directory:
        stage = Path(directory).resolve()
        candidate = build_plan(workspace, inv, symbol_key, fp_key, model_key, category, "Custom", preserved_name,
                               symbol_format=symbol_format, output_root=stage, input_roots=input_roots,
                               model_path_mode=model_path_mode, model_variable=model_variable, category_config=layout)
        if previous.get("mpn") and candidate.history["mpn"] != previous["mpn"]:
            raise ImportErrorDetail("The current source MPN differs from the tracked component. Refresh and review the source.")
        desired = {}
        for path, role in candidate.assets.items():
            destination = root / path.relative_to(stage)
            if role not in old or destination != old[role][0]:
                raise ImportErrorDetail("Updating would rename or relocate an asset. Existing names, categories, extensions and output format must be retained.")
            data = candidate.files[path]
            if role == "footprint" and model_path_mode == "absolute":
                tree = parse(data.decode("utf-8"))
                for model in children(tree, "model"):
                    model[1] = (root / Path(str(model[1])).relative_to(stage)).as_posix()
                data = (dump(tree) + "\n").encode("utf-8")
            if role == "symbol" and symbol_format == "packed":
                incoming = parse(data.decode("utf-8"))
                require_kicad9(current_tree, KICAD9_SYMBOL_VERSION, "The current symbol library")
                if child(incoming, "version")[1] != child(current_tree, "version")[1]:
                    raise ImportErrorDetail("Packed library format versions differ. Normalise them using KiCad before updating.")
                updated = copy.deepcopy(current_tree)
                position = next(index for index, node in enumerate(updated) if isinstance(node, list) and node and node[0] == "symbol" and str(node[1]) == symbol.name)
                updated[position] = children(incoming, "symbol")[0]
                data = (dump(updated) + "\n").encode("utf-8")
            desired[destination] = (role, data)
    if not any(snapshots[path] != data for path, (_, data) in desired.items()):
        raise ImportErrorDetail("No component changes found. Nothing needs updating.")
    plan = Plan(output_root=root, protected_roots=candidate.protected_roots)
    plan.history = dict(candidate.history)
    plan.history.update({"operation": "update", "previous_event_id": previous["event_id"], "naming_mode": "Preserve existing names"})
    plan.warnings = list(candidate.warnings)
    if any(record["symbol"].casefold() == symbol.name.casefold() and record["library_name"] == layout.library_name
           and record["symbol_format"] != symbol_format for record in records):
        plan.warnings.append("This component is also recorded in another symbol output format. Only the selected format is updated; the copies are not synchronised.")
    plan.warnings.append("Review pin/pad, geometry and 3D changes. Updating a library does not update already placed schematic or PCB instances automatically.")
    plan.info = [f"Update component: {symbol.name}", f"Category: {category} | Format: {symbol_format}",
                 f"Library root: {root}", "Existing asset names are preserved.",
                 f"Backups: {root / '.kicad-loader-backups'}/<update id>/ (created before changes)"]
    for path, (role, data) in desired.items():
        plan.before[path] = snapshots[path]
        plan.add(path, data, merge=True, role=role)
        if plan.before[path] != snapshots[path]:
            raise ImportErrorDetail("Destination changed while the update was being reviewed. Reopen the review.")
        if snapshots[path] != data:
            plan.backup_files[path] = snapshots[path]
            plan.info.append(f"Update {role}: {path.relative_to(root)}")
        else:
            plan.info.append(f"Keep unchanged {role}: {path.relative_to(root)}")

    changed_assets = {path for path, (role, data) in desired.items()
                      if role in {"footprint", "model"} and data != snapshots[path]}
    verify_replacement_dependencies(plan, records, old, previous, changed_assets,
                                    symbol.name, layout.library_name, model_variable)
    return plan


def verify_replacement_dependencies(plan, records, old, previous, changed_assets,
                                    symbol_name, library_name, model_variable):
    """Snapshot history and local references before any tracked asset replacement."""
    root = plan.output_root

    def watch_directory(folder):
        check_destination(folder, root, plan.protected_roots)
        plan.dependency_directories[folder] = tuple(sorted(item.name for item in folder.iterdir())) if folder.is_dir() else None

    def inspect(path):
        check_destination(path, root, plan.protected_roots)
        data = path.read_bytes()
        if path in plan.before and plan.before[path] != data:
            raise ImportErrorDetail("A dependency changed during the replacement check. Reopen the review.")
        plan.before[path] = data
        return parse(data.decode("utf-8-sig"))

    watch_directory(root / '.kicad-loader-history')
    for record in records:
        path = Path(record["record_path"])
        check_destination(path, root, plan.protected_roots)
        data = path.read_bytes()
        if json.loads(data.decode("utf-8")) != {key: value for key, value in record.items() if key != "record_path"}:
            raise ImportErrorDetail("History changed during the replacement check. Reopen the review.")
        plan.before[path] = data
    identity = (previous["symbol"].casefold(), previous["library_name"], previous["symbol_format"])
    for record in records:
        if (record["symbol"].casefold(), record["library_name"], record["symbol_format"]) != identity:
            for output in record["outputs"]:
                if recorded_path(root, output["relative_path"]) in changed_assets:
                    raise ImportErrorDetail("A changed footprint or model is recorded for another component or symbol format. Shared assets cannot be replaced in place.")
    if changed_assets:
        symbol_root, footprint_root = root / "Symbols", root / "Footprints"
        watch_directory(symbol_root)
        watch_directory(footprint_root)
        symbol_paths = list(symbol_root.glob("*.kicad_sym"))
        for folder in symbol_root.glob("*.kicad_symdir"):
            watch_directory(folder)
            symbol_paths.extend(folder.glob("*.kicad_sym"))
        if "footprint" in old:
            reference = f"{library_name}:{old['footprint'][0].stem}"
            for path in symbol_paths:
                tree = inspect(path)
                if tree[0] != "kicad_symbol_lib":
                    raise ImportErrorDetail(f"Cannot verify symbol dependencies in {path}")
                for node in children(tree, "symbol"):
                    if path == old["symbol"][0] and str(node[1]) == symbol_name:
                        continue
                    if prop(node, "Footprint") == reference:
                        raise ImportErrorDetail(f"Another symbol references this footprint: {node[1]} in {path}. Shared replacements are blocked.")
        for folder in footprint_root.glob("*.pretty"):
            watch_directory(folder)
            for path in folder.glob("*.kicad_mod"):
                tree = inspect(path)
                if tree[0] not in ("module", "footprint"):
                    raise ImportErrorDetail(f"Cannot verify footprint dependencies in {path}")
                if "model" not in old or old["model"][0] not in changed_assets or path == old.get("footprint", (None,))[0]:
                    continue
                for model in children(tree, "model"):
                    value = str(model[1]).replace("${" + model_variable + "}", root.as_posix())
                    target = Path(value)
                    if ((target.is_absolute() and target.resolve() == old["model"][0].resolve())
                            or Path(value.replace("\\", "/")).name == old["model"][0].name):
                        raise ImportErrorDetail(f"Another footprint may reference this model: {path}. Shared model replacements are blocked.")
    return plan


def same_update_plan(first, second):
    return (first.files == second.files and first.before == second.before
            and first.warnings == second.warnings and first.backup_files == second.backup_files
            and first.dependency_directories == second.dependency_directories
            and first.history == second.history and first.assets == second.assets
            and first.removals == second.removals and first.related_assets == second.related_assets)
