"""Reviewed category moves of tracked native components, preserving shared assets."""
import copy

from component_lifecycle import prepare_component
from component_updates import digest

from library_core import (ImportErrorDetail, basename, check_destination, check_folders,
                          child, children, dump, parse, prop, set_prop, require_kicad9,
                          KICAD9_SYMBOL_VERSION, KICAD9_FOOTPRINT_VERSION)
from library_layout import LibraryCategory
from loader_settings import validate_model_paths


def build_move_plan(output_root, event_id, target_category, protected_roots=(),
                    model_path_mode="variable", model_variable="DVL_LIB_ROOT"):
    if not isinstance(target_category, LibraryCategory):
        raise ImportErrorDetail("Select a configured destination category.")
    target = target_category.validated()
    model_variable = validate_model_paths(model_path_mode, model_variable)
    plan, records, record, source, old, source_tree, original_node, shared = prepare_component(
        output_root, event_id, protected_roots, model_variable)
    if (source.name.casefold() == target.name.casefold() or source.library_name.casefold() == target.library_name.casefold()
            or source.model_folder.casefold() == target.model_folder.casefold()):
        raise ImportErrorDetail("Choose a different category with distinct library and model folder names.")
    root, mode = plan.output_root, record["symbol_format"]
    protected = plan.protected_roots
    source_snapshots = {path: plan.before[path] for path, _ in old.values()}
    symbol_path = old["symbol"][0]
    def inspect(path):
        check_destination(path, root, protected)
        if path.resolve() != path or path.is_symlink() or not path.is_file() or path.read_bytes() != plan.before[path]:
            raise ImportErrorDetail("A move dependency changed during review.")
        return plan.before[path]

    def add_destination(path, data, merge=False, role=None):
        check_destination(path, root, protected)
        if path.resolve() != path or path.is_symlink() or (path.exists() and not path.is_file()):
            raise ImportErrorDetail(f"Cannot use linked or non-file destination: {path}")
        expected = plan.before[path] if path in plan.before else path.read_bytes() if path.exists() else None
        plan.add(path, data, merge=merge, role=role)
        if plan.before[path] != expected:
            raise ImportErrorDetail("A destination changed during move planning. Reopen the review.")

    def watch(folder):
        check_destination(folder, root, protected)
        if folder.resolve() != folder or (folder.exists() and not folder.is_dir()):
            raise ImportErrorDetail(f"Cannot verify library folder: {folder}")
        plan.dependency_directories[folder] = tuple(sorted(p.name for p in folder.iterdir())) if folder.is_dir() else None

    watch(target.footprint_library(root))
    watch(target.model_directory(root))
    if mode == "unpacked":
        watch(target.symbol_library(root, mode))
    symbol_trees = {path: parse(data.decode("utf-8-sig")) for path, data in plan.before.items()
                    if path.suffix == ".kicad_sym"}
    footprint_trees = {path: parse(data.decode("utf-8-sig")) for path, data in plan.before.items()
                       if path.suffix == ".kicad_mod"}

    new_node = copy.deepcopy(original_node)
    destinations = {}
    if "model" in old:
        model_path = target.model_directory(root) / old["model"][0].name
        destinations["model"] = model_path
        add_destination(model_path, plan.before[old["model"][0]], role="model")
    if "footprint" in old:
        old_fp = old["footprint"][0]
        fp = copy.deepcopy(footprint_trees[old_fp])
        if str(fp[1]) != old_fp.stem:
            raise ImportErrorDetail("The footprint's internal name differs from its tracked filename.")
        if mode == "packed":
            require_kicad9(fp, KICAD9_FOOTPRINT_VERSION, "The footprint")
        models = children(fp, "model")
        if len(models) != (1 if "model" in old else 0):
            raise ImportErrorDetail("Unexpected footprint model references; move requires the tracked asset set.")
        if models:
            if basename(models[0][1]).casefold() != old["model"][0].name.casefold():
                raise ImportErrorDetail("The model reference does not match the tracked STEP file.")
            models[0][1] = (f"${{{model_variable}}}/3DModels/{target.model_folder}/{destinations['model'].name}"
                            if model_path_mode == "variable" else destinations["model"].as_posix())
        fp_path = target.footprint_library(root) / old_fp.name
        destinations["footprint"] = fp_path
        add_destination(fp_path, (dump(fp) + "\n").encode("utf-8"), role="footprint")
        set_prop(new_node, "Footprint", f"{target.library_name}:{fp_path.stem}")
    library = target.symbol_library(root, mode)
    destination_symbol = library if mode == "packed" else library / symbol_path.name
    if mode == "packed" and library.exists():
        if library not in symbol_trees:
            raise ImportErrorDetail("The destination symbol library is not a readable native library.")
        destination_tree = copy.deepcopy(symbol_trees[library])
        require_kicad9(destination_tree, KICAD9_SYMBOL_VERSION, "The destination library")
        if child(source_tree, "version")[1] != child(destination_tree, "version")[1]:
            raise ImportErrorDetail("Source and destination symbol format versions differ. No conversion is performed.")
    else:
        destination_tree = [copy.deepcopy(node) for node in source_tree
                            if not (isinstance(node, list) and node and node[0] == "symbol")]
    destination_paths = ([library] if mode == "packed" else list(library.glob("*.kicad_sym")))
    for path in destination_paths:
        tree = symbol_trees.get(path)
        if tree and any(str(node[1]).casefold() == record["symbol"].casefold() for node in children(tree, "symbol")):
            raise ImportErrorDetail("The destination already contains this symbol. Nothing will be overwritten.")
    destination_tree.append(new_node)
    destinations["symbol"] = destination_symbol
    add_destination(destination_symbol, (dump(destination_tree) + "\n").encode("utf-8"), merge=mode == "packed", role="symbol")
    if mode == "packed":
        remaining = [copy.deepcopy(node) for node in source_tree if node is not original_node]
        add_destination(symbol_path, (dump(remaining) + "\n").encode("utf-8"), merge=True)
        plan.related_assets[symbol_path] = "source_symbol_library"
    else:
        plan.remove(symbol_path, "source_symbol")
    for role in ("footprint", "model"):
        if role in old and role not in shared:
            plan.remove(old[role][0], "source_" + role)
    for path in plan.files:
        if plan.before[path] is not None:
            plan.backup_files[path] = plan.before[path]
    plan.folders = tuple(sorted({path.parent for path in plan.assets}))
    check_folders(plan.folders)
    # Recheck every asset read before assigning its mutation, including reused targets.
    for role, (path, _) in old.items():
        if plan.before[path] != source_snapshots[path] or inspect(path) != source_snapshots[path]:
            raise ImportErrorDetail("The source changed during move planning.")

    plan.history = {key: value for key, value in record.items() if key not in {
        "record_path", "outputs", "event_id", "schema_version", "imported_at_utc", "warnings", "backup_folder",
        "file_changes", "operation", "previous_event_id", "restored_from_event_id", "reverted_event_id", "restore_backup_folder",
        "moved_from", "move_sources"}}
    plan.history.update({"operation": "move", "previous_event_id": record["event_id"],
                         "category": target.name, "library_name": target.library_name, "model_folder": target.model_folder,
                         "moved_from": {key: record[key] for key in ("symbol", "category", "library_name", "symbol_format", "event_id")},
                         "move_sources": {role: path.relative_to(root).as_posix() for role, (path, _) in old.items()},
                         "symbol_sha256": digest(dump(new_node).encode("utf-8")), "naming_mode": "Preserve existing names"})
    plan.info = [f"Move component: {record['symbol']}", f"From: {source.name} / {source.library_name}",
                 f"To: {target.name} / {target.library_name}", f"Format retained: {mode}", f"Library root: {root}"]
    plan.info.extend(f"Destination {role}: {path.relative_to(root)}" for role, path in destinations.items())
    plan.info.extend(f"Keep shared source {role}: {old[role][0].relative_to(root)}" for role in sorted(shared))
    plan.info.extend(f"Remove source file after backup: {path.relative_to(root)}" for path in plan.removals)
    plan.info += [f"Register destination symbol library in KiCad as {target.library_name}: {library}",
                  f"Register destination footprint library as {target.library_name}: {target.footprint_library(root)}"]
    plan.warnings = ["Existing schematics/PCBs keep their old library nicknames. Review and reassign affected instances in KiCad; project files are not modified.",
                     "Source symbol files/definitions are removed after backup. External projects or libraries may still reference them and are not inspected.",
                     "Shared source footprints/models are retained conservatively. This move does not convert formats or synchronise other copies.",
                     "Move backups contain the prior files. The current Restore button only reverts updates; automatic move undo is not implemented."]
    if model_path_mode == "variable" and "model" in old:
        plan.info.append(f"KiCad path variable: {model_variable} = {root}")
    return plan
