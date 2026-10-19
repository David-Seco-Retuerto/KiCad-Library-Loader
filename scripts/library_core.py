"""Safe, dependency-free import of native KiCad libraries. Never edits Imports."""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from loader_settings import validate_model_paths, validate_output_layout
from providers import get_provider
from import_history import HISTORY_FOLDER, ORIGIN_FILE
from library_layout import DEFAULT_CATEGORIES, LibraryCategory, validate_segment

CATEGORIES = tuple(category.name for category in DEFAULT_CATEGORIES)
SYMBOL_FORMATS = {"unpacked": "KiCad 10+ — Unpacked", "packed": "KiCad 9 — Packed"}
# Format limits used by KiCad 9; packing is not a file-format downgrade.
KICAD9_SYMBOL_VERSION = 20241209
KICAD9_FOOTPRINT_VERSION = 20241229


class ImportErrorDetail(ValueError):
    pass


class Atom(str):
    """Unquoted S-expression token (quoted strings remain ordinary str)."""


def parse(text):
    matches = list(re.finditer(r'"(?:\\.|[^"\\])*"|[()]|[^\s()"]+', text))
    end = 0
    for match in matches:
        if text[end:match.start()].strip():
            raise ImportErrorDetail("Unterminated string or invalid token")
        end = match.end()
    if text[end:].strip():
        raise ImportErrorDetail("Unterminated string")
    tokens = [m.group() for m in matches]
    stack, roots = [], []
    for token in tokens:
        if token == "(":
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ImportErrorDetail("Unexpected parenthesis")
            stack.pop()
        else:
            if not stack:
                raise ImportErrorDetail("Content outside the expression")
            if token.startswith('"'):
                # KiCad strings support escaped quotes and backslashes; retain other escapes.
                value = re.sub(r'\\(["\\])', r'\1', token[1:-1])
            else:
                value = Atom(token)
            stack[-1].append(value)
    if stack or len(roots) != 1 or not roots[0]:
        raise ImportErrorDetail("Incomplete S-expression or multiple roots")
    return roots[0]


def dump(node, level=0):
    if isinstance(node, Atom):
        return str(node)
    if isinstance(node, str):
        return '"' + node.replace('\\', '\\\\').replace('"', '\\"') + '"'
    parts = []
    for item in node:
        if isinstance(item, list):
            parts.append("\n" + "  " * (level + 1) + dump(item, level + 1))
        else:
            parts.append((" " if parts else "") + dump(item, level))
    return "(" + "".join(parts) + ")"


def children(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def child(node, key):
    return next(iter(children(node, key)), None)


def walk(node, key):
    for item in node:
        if isinstance(item, list):
            if item and item[0] == key:
                yield item
            yield from walk(item, key)


def prop(node, name):
    return next((p[2] for p in children(node, "property") if len(p) > 2 and p[1] == name), "")


def set_prop(node, name, value):
    p = next((p for p in children(node, "property") if p[1] == name), None)
    if p is not None:
        p[2] = value
    else:
        node.append([Atom("property"), name, value,
                     [Atom("at"), Atom("0"), Atom("0"), Atom("0")],
                     [Atom("effects"), [Atom("font"), [Atom("size"), Atom("1.27"), Atom("1.27")]], Atom("hide")]])


def read_tree(path):
    return parse(path.read_text(encoding="utf-8-sig"))


def safe_name(name):
    try:
        return validate_segment(name)
    except ValueError as exc:
        raise ImportErrorDetail(str(exc)) from exc


def slug(value):
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", str(value)).strip("_.")


@dataclass
class Symbol:
    path: Path
    node: list
    header: list

    @property
    def name(self):
        return str(self.node[1])

    @property
    def mpn(self):
        return str(prop(self.node, "Manufacturer_Part_Number") or prop(self.node, "MPN") or self.name)


@dataclass
class Inventory:
    root: Path
    symbols: dict = field(default_factory=dict)
    footprints: dict = field(default_factory=dict)
    models: dict = field(default_factory=dict)
    notices: list = field(default_factory=list)


def scan(repo, source, input_root=None):
    provider = get_provider(source)
    return provider.scan(input_root if input_root is not None else provider.default_folder(repo))


def scan_directory(folder):
    """Read a native-export folder, independent of provider and output location."""
    root = Path(folder).resolve()
    inv = Inventory(root)
    if not root.is_dir():
        inv.notices.append(f"Folder not found: {root}")
        return inv
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.resolve().is_relative_to(root))
    modern = {p.with_suffix("") for p in files if p.suffix.lower() == ".kicad_sym"}
    for path in files:
        if path.parent == root and path.name == ORIGIN_FILE:
            continue
        key = path.relative_to(root).as_posix()
        try:
            suffix = path.suffix.lower()
            if suffix == ".kicad_sym":
                tree = read_tree(path)
                if tree[0] != "kicad_symbol_lib" or not child(tree, "version"):
                    raise ImportErrorDetail("Not a kicad_symbol_lib library")
                header = [copy.deepcopy(n) for n in tree[1:] if not (isinstance(n, list) and n[0] == "symbol")]
                for node in children(tree, "symbol"):
                    inv.symbols[f"{node[1]} — {key}"] = Symbol(path, node, header)
            elif suffix == ".kicad_mod":
                tree = read_tree(path)
                if tree[0] not in ("module", "footprint"):
                    raise ImportErrorDetail("Unrecognised native footprint")
                inv.footprints[key] = path
            elif suffix in (".stp", ".step"):
                inv.models[key] = path
            elif suffix == ".lib" and path.with_suffix("") not in modern:
                inv.notices.append(f"{key}: legacy .lib is unsupported; convert to .kicad_sym using KiCad")
            elif suffix in (".json", ".epro", ".elib", ".zip"):
                inv.notices.append(f"{key}: unsupported format/container; export/extract native KiCad files first")
        except (ValueError, OSError, IndexError) as exc:
            inv.notices.append(f"{key}: {exc}")
    if not inv.symbols:
        inv.notices.append("No native KiCad symbols are available in this source.")
    return inv


def basename(value):
    return str(value).replace("\\", "/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def associate(inv, symbol):
    """Only unambiguous exact references/names; no arbitrary first-item fallback."""
    target = basename(prop(symbol.node, "Footprint"))
    matches = [k for k, p in inv.footprints.items() if p.stem.casefold() == target.casefold()]
    if not matches:
        matches = [k for k, p in inv.footprints.items() if p.stem.casefold() in {symbol.name.casefold(), symbol.mpn.casefold()}]
    fp = matches[0] if len(matches) == 1 else ""
    model = associate_model(inv, symbol, fp)
    return fp, model


def associate_model(inv, symbol, fp):
    refs = []
    if fp:
        refs = [basename(n[1]).casefold() for n in children(read_tree(inv.footprints[fp]), "model")]
    matches = [k for k, p in inv.models.items() if p.name.casefold() in refs]
    if not matches:
        matches = [k for k, p in inv.models.items() if p.stem.casefold() in {symbol.name.casefold(), symbol.mpn.casefold()}]
    return matches[0] if len(matches) == 1 else ""


def suggestion(symbol, fp):
    tree = read_tree(fp)
    # Preserve the vendor geometry code; add only descriptions actually present.
    description = child(tree, "descr")
    bits = [slug(symbol.mpn), slug(str(tree[1]))]
    if description and len(description) > 1:
        desc = slug(description[1])
        if desc and desc not in bits:
            bits.append(desc[:45])
    return "_".join(dict.fromkeys(bits))[:140].rstrip(".")


@dataclass
class Plan:
    files: dict = field(default_factory=dict)
    before: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    info: list = field(default_factory=list)
    directories: dict = field(default_factory=dict)
    output_root: Path | None = None
    protected_roots: tuple = ()
    folders: tuple = ()
    assets: dict = field(default_factory=dict)
    history: dict | None = None
    history_file: Path | None = None

    def watch_directory(self, path):
        paths = symbol_files(path)
        self.directories[path] = tuple(p.name for p in paths)
        return paths

    def add(self, path, content, merge=False, role=None):
        if role is not None:
            self.assets[path] = role
        old = path.read_bytes() if path.exists() else None
        if old == content:
            self.info.append(f"Reuse unchanged: {path}")
            self.before[path] = old
            return
        if old is not None and not merge:
            raise ImportErrorDetail(f"Already exists with different content: {path}. Choose another name; overwriting is disabled.")
        self.before[path] = old
        self.files[path] = content


def symbol_files(folder):
    if folder.exists() and not folder.is_dir():
        raise ImportErrorDetail(f"Expected an unpacked library folder: {folder}")
    return sorted((p for p in folder.iterdir() if p.suffix.lower() == ".kicad_sym"), key=lambda p: p.name) if folder.exists() else []


def read_symbol_library(path, plan):
    if path.is_dir():
        raise ImportErrorDetail(f"Expected a .kicad_sym file: {path}")
    data = path.read_bytes()
    plan.before[path] = data
    tree = parse(data.decode("utf-8-sig"))
    if tree[0] != "kicad_symbol_lib" or not child(tree, "version"):
        raise ImportErrorDetail(f"Not a native symbol library: {path}")
    return tree


def require_kicad9(tree, maximum, description):
    version = child(tree, "version")
    # Old module footprints may legitimately have no version token.
    if version is None and tree[0] == "module":
        return
    try:
        value = int(version[1]) if version else None
    except (IndexError, ValueError):
        value = None
    if value is None or value > maximum:
        raise ImportErrorDetail(f"{description} is newer than the KiCad 9 format or has no valid version. "
                                "Choose KiCad 10+ or export a compatible source with KiCad; no downgrade is performed.")


def build_plan(repo, inv, symbol_key, fp_key, model_key, category, mode, custom="", symbol_format="unpacked",
               output_root=None, input_roots=None, model_path_mode="variable", model_variable="DVL_LIB_ROOT", category_config=None):
    workspace = Path(repo).resolve()
    repo = Path(output_root).resolve() if output_root is not None else workspace
    # Keep every configured source protected, not just the currently selected one.
    protected = tuple(sorted({Path(p).resolve() for p in (input_roots or ())} | {inv.root.resolve(), (workspace / "Imports").resolve()}))
    validate_output_layout(repo, protected)
    model_variable = validate_model_paths(model_path_mode, model_variable)
    layout = category_config if category_config is not None else next((item for item in DEFAULT_CATEGORIES if item.name == category), None)
    if not isinstance(layout, LibraryCategory) or layout.name != category or mode not in ("Original", "Suggestion", "Custom"):
        raise ImportErrorDetail("Invalid category or naming mode")
    layout = layout.validated()
    if symbol_format not in SYMBOL_FORMATS:
        raise ImportErrorDetail("Invalid symbol output format")
    if symbol_key not in inv.symbols:
        raise ImportErrorDetail("Select a symbol")
    symbol = inv.symbols[symbol_key]
    # Re-read source on validation/import, so Refresh is not required for safety.
    current = read_tree(symbol.path)
    if current[0] != "kicad_symbol_lib" or not child(current, "version"):
        raise ImportErrorDetail("The source library changed or is not native; click Refresh")
    if symbol_format == "packed":
        require_kicad9(current, KICAD9_SYMBOL_VERSION, "The source symbol library")
    nodes = [n for n in children(current, "symbol") if n[1] == symbol.name]
    if len(nodes) != 1:
        raise ImportErrorDetail("The symbol changed or is duplicated; click Refresh")
    node = copy.deepcopy(nodes[0])
    if child(node, "extends"):
        raise ImportErrorDetail("Inherited symbol (extends): export a standalone copy with KiCad before importing")
    safe_name(symbol.name)
    plan = Plan(output_root=repo, protected_roots=protected)
    plan.history = {"symbol": symbol.name, "mpn": symbol.mpn, "category": layout.name,
                    "library_name": layout.library_name, "model_folder": layout.model_folder,
                    "symbol_format": symbol_format, "naming_mode": mode,
                    "input_root": str(inv.root), "source_files": {
                        "symbol": str(symbol.path),
                        "footprint": str(inv.footprints[fp_key]) if fp_key else None,
                        "model": str(inv.models[model_key]) if model_key else None}}
    plan.info.extend([f"Input folder: {inv.root}", f"Library output root: {repo}",
                      f"Import history folder: {repo / HISTORY_FOLDER}"])
    for path in (symbol.path, inv.footprints.get(fp_key), inv.models.get(model_key)):
        if path and not path.resolve().is_relative_to(inv.root):
            raise ImportErrorDetail("Source is outside the selected Imports folder")
    if model_key and not fp_key:
        raise ImportErrorDetail("Select a footprint to associate the 3D model")
    if fp_key:
        fp_path = inv.footprints[fp_key]
        fp = read_tree(fp_path)
        if fp[0] not in ("module", "footprint") or len(fp) < 2:
            raise ImportErrorDetail("The footprint changed or is not native; click Refresh")
        if symbol_format == "packed":
            require_kicad9(fp, KICAD9_FOOTPRINT_VERSION, "The source footprint")
        name = safe_name(str(fp[1]) if mode == "Original" else suggestion(symbol, fp_path) if mode == "Suggestion" else custom)
        fp[1] = name
        for text in children(fp, "fp_text"):
            if len(text) > 2 and text[1] == "value":
                text[2] = name
        for p in children(fp, "property"):
            if len(p) > 2 and p[1] == "Value":
                p[2] = name
        models = children(fp, "model")
        fp[:] = [n for n in fp if n not in models]
        if model_key:
            model_path = inv.models[model_key]
            data = model_path.read_bytes()
            if b"ISO-10303-21;" not in data[:4096] or b"END-ISO-10303-21;" not in data[-4096:]:
                raise ImportErrorDetail("The model does not appear to be a complete ISO-10303-21 STEP file")
            matching = [m for m in models if basename(m[1]).casefold() == model_path.name.casefold()]
            if len(models) > 1 and len(matching) != 1:
                raise ImportErrorDetail("Multiple models/transforms: a safe alignment cannot be selected")
            transform = copy.deepcopy(matching[0] if matching else models[0]) if models else [Atom("model"), "", [Atom("offset"), [Atom("xyz"), Atom("0"), Atom("0"), Atom("0")]], [Atom("scale"), [Atom("xyz"), Atom("1"), Atom("1"), Atom("1")]], [Atom("rotate"), [Atom("xyz"), Atom("0"), Atom("0"), Atom("0")]]]
            if not matching:
                plan.warnings.append("Manually selected model: check 3D alignment; the available transform is preserved, or identity is used.")
            model_name = name + model_path.suffix.lower()
            destination_model = layout.model_directory(repo) / model_name
            transform[1] = (f"${{{model_variable}}}/3DModels/{layout.model_folder}/{model_name}"
                            if model_path_mode == "variable" else destination_model.as_posix())
            fp.append(transform)
            plan.add(destination_model, data, role="model")
            if model_path_mode == "variable":
                plan.info.append(f"KiCad path variable: {model_variable} = {repo}. Changing a shared variable affects all libraries using it.")
            else:
                plan.info.append("3D model paths: absolute; no KiCad path variable is needed.")
        else:
            plan.warnings.append("No STEP model: the footprint copy will have no 3D references.")
        pins = {str(n[1]) for n in walk(node, "number") if len(n) > 1}
        pads = {str(n[1]) for n in children(fp, "pad") if len(n) > 1 and n[1]}
        if pins != pads:
            plan.warnings.append(f"Pin/pad mismatch: symbol only={sorted(pins - pads)}, footprint only={sorted(pads - pins)}. Check the association.")
        set_prop(node, "Footprint", f"{layout.library_name}:{name}")
        plan.add(layout.footprint_library(repo) / f"{name}.kicad_mod", (dump(fp) + "\n").encode(), role="footprint")
    else:
        set_prop(node, "Footprint", "")
        plan.warnings.append("Symbol-only import: its Footprint reference is cleared in the copy.")
    packed = layout.symbol_library(repo, "packed")
    unpacked = layout.symbol_library(repo, "unpacked")
    header = [Atom("kicad_symbol_lib")] + [copy.deepcopy(n) for n in current[1:] if not (isinstance(n, list) and n[0] == "symbol")]
    selected = packed if symbol_format == "packed" else unpacked
    destination = packed if symbol_format == "packed" else unpacked / f"{symbol.name}.kicad_sym"
    existing = plan.watch_directory(unpacked) if symbol_format == "unpacked" else [packed] if packed.exists() else []
    library = header
    for path in existing:
        tree = read_symbol_library(path, plan)
        if any(str(n[1]).casefold() == symbol.name.casefold() for n in children(tree, "symbol")):
            raise ImportErrorDetail(f"Symbol {node[1]} already exists in {path}; it will not be replaced")
        if symbol_format == "packed":
            require_kicad9(tree, KICAD9_SYMBOL_VERSION, "The destination library")
            if child(current, "version")[1] != child(tree, "version")[1]:
                raise ImportErrorDetail("Library format versions differ: normalise them with KiCad before merging")
            library = tree
    # Each new unpacked file is a complete native library containing one symbol.
    # Existing files remain untouched, even if they contain several symbols.
    library.append(node)
    plan.add(destination, (dump(library) + "\n").encode(), merge=symbol_format == "packed", role="symbol")
    plan.info.extend([f"Symbol output: {SYMBOL_FORMATS[symbol_format]}",
                      f"Symbol destination: {destination}",
                      f"Register symbol {'folder' if symbol_format == 'unpacked' else 'file'} in KiCad: {selected}",
                      f"Register footprint folder in KiCad: {layout.footprint_library(repo)}",
                      f"Library nickname: {layout.library_name} (symbols and footprints)"])
    other_files = plan.watch_directory(unpacked) if symbol_format == "packed" else [packed] if packed.exists() else []
    # A missing packed counterpart is also observed, so creation invalidates a plan.
    if symbol_format == "unpacked" and not packed.exists():
        plan.before[packed] = None
    if other_files:
        plan.warnings.append(f"Both symbol output formats are present. Register only one as {layout.library_name} in each KiCad library table; they are not synchronised.")
    for path in other_files:
        try:
            tree = read_symbol_library(path, plan)
        except (OSError, ValueError, IndexError) as exc:
            plan.warnings.append(f"Could not check the other output format at {path}: {exc}. Review it manually; it will not be changed.")
            continue
        for previous in children(tree, "symbol"):
            if str(previous[1]).casefold() == symbol.name.casefold():
                status = "matching content" if previous == node else "different content — copies may be out of sync"
                plan.warnings.append(f"Symbol {symbol.name} already exists in the other output format ({path}): {status}. Only the selected format will be written.")
    for path in plan.before:
        check_destination(path, repo, protected)
    plan.info.extend(f"Write: {p.relative_to(repo)}" for p in plan.files)
    return plan


def commit_plan(repo, plan):
    """Exclusive application lock + optimistic concurrency + rollback on I/O errors.

    Not crash-atomic across files: after a power loss inspect outputs before retrying.
    """
    repo = Path(repo).resolve()
    if plan.output_root is not None and repo != plan.output_root:
        raise ImportErrorDetail("The output root changed since validation. Build a new import plan.")
    validate_output_layout(repo, plan.protected_roots)
    from import_history import add_history_record
    add_history_record(plan)
    # Validate the whole plan before creating the root or a lock file.
    for path in (*plan.before, *plan.files, *plan.directories, *plan.folders):
        check_destination(path, repo, plan.protected_roots)
    check_folders(plan.folders)
    repo.mkdir(parents=True, exist_ok=True)
    lock = repo / ".kicad-importer.lock"
    check_destination(lock, repo, plan.protected_roots)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ImportErrorDetail(f"Import blocked by {lock}. If no other importer is running, review the files before removing the lock.") from exc
    written = []
    try:
        os.write(fd, str(os.getpid()).encode())
        check_folders(plan.folders)
        for path, before in plan.before.items():
            check_destination(path, repo, plan.protected_roots)
            actual = path.read_bytes() if path.exists() else None
            if actual != before:
                raise ImportErrorDetail(f"Destination changed since validation: {path}")
        for directory, names in plan.directories.items():
            check_destination(directory, repo, plan.protected_roots)
            if tuple(p.name for p in symbol_files(directory)) != names:
                raise ImportErrorDetail(f"Symbol library folder changed since validation: {directory}")
        for folder in plan.folders:
            check_destination(folder, repo, plan.protected_roots)
            folder.mkdir(parents=True, exist_ok=True)
        for path, data in plan.files.items():
            check_destination(path, repo, plan.protected_roots)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".import-tmp")
            temporary_created = False
            try:
                with temporary.open("xb") as stream:
                    temporary_created = True
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Recheck immediately before replacing an existing packed library.
                actual = path.read_bytes() if path.exists() else None
                if actual != plan.before[path]:
                    raise ImportErrorDetail(f"Destination changed during import: {path}")
                if plan.before[path] is None:
                    # Exclusive creation prevents overwriting a competing writer.
                    with path.open("xb") as stream:
                        written.append(path)
                        stream.write(data)
                else:
                    os.replace(temporary, path)
                    written.append(path)
            finally:
                if temporary_created:
                    temporary.unlink(missing_ok=True)
    except Exception:
        for path in reversed(written):
            old = plan.before[path]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def check_destination(path, output_root, protected_roots):
    resolved = path.resolve()
    if not resolved.is_relative_to(output_root) or any(resolved.is_relative_to(root) for root in protected_roots):
        raise ImportErrorDetail(f"Destination is outside the selected output root or inside an input folder: {path}")


def check_folders(folders):
    for folder in folders:
        for path in (folder, *folder.parents):
            if path.exists() and not path.is_dir():
                raise ImportErrorDetail(f"Expected a folder, but a file already exists: {path}")


def build_folder_plan(workspace, settings, symbol_format):
    """Prepare native library folders only; packed symbol files wait for import."""
    settings = settings.validated(workspace)
    if symbol_format not in SYMBOL_FORMATS:
        raise ImportErrorDetail("Invalid symbol output format")
    root = settings.output_root
    protected = tuple(sorted({*settings.sources.values(), (Path(workspace).resolve() / "Imports").resolve()}))
    plan = Plan(output_root=root, protected_roots=protected)
    folders = set()
    plan.info.extend([f"Library output root: {root}", f"Symbol output: {SYMBOL_FORMATS[symbol_format]}"])
    for category in settings.categories:
        symbol_path = category.symbol_library(root, symbol_format)
        folders.update((symbol_path if symbol_format == "unpacked" else symbol_path.parent,
                        category.footprint_library(root), category.model_directory(root)))
        existing = plan.watch_directory(symbol_path) if symbol_format == "unpacked" else [symbol_path] if symbol_path.exists() else []
        for path in existing:
            check_destination(path, root, protected)
            tree = read_symbol_library(path, plan)
            if symbol_format == "packed":
                require_kicad9(tree, KICAD9_SYMBOL_VERSION, "The existing symbol library")
        if symbol_format == "packed" and not symbol_path.exists():
            plan.before[symbol_path] = None
        other = category.symbol_library(root, "packed" if symbol_format == "unpacked" else "unpacked")
        if other.exists() and (other.is_file() or (other.is_dir() and symbol_files(other))):
            plan.warnings.append(f"Another symbol format is present at {other}. Register only one symbol library as {category.library_name}; nothing will be converted or replaced.")
        plan.info.append(f"Library nickname: {category.library_name} · 3D folder: {category.model_folder}")
        plan.info.append(f"{'Symbol library folder' if symbol_format == 'unpacked' else 'Packed symbol file (on first import)'}: {symbol_path}")
    plan.folders = tuple(sorted(folders))
    for folder in plan.folders:
        check_destination(folder, root, protected)
    check_folders(plan.folders)
    plan.info.extend(f"{'Reuse folder' if folder.exists() else 'Create folder'}: {folder}" for folder in plan.folders)
    if symbol_format == "packed":
        plan.info.append("Packed .kicad_sym files are created on first symbol import; no empty symbol files will be generated.")
    plan.info.append("Existing files and folder contents are preserved. KiCad registration is a separate step.")
    return plan


def load_preferences(path, *, strict=False):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        if strict:
            raise ImportErrorDetail(f"Could not read saved preferences at {path}: {exc}") from exc
        return {}
    if not isinstance(data, dict):
        if strict:
            raise ImportErrorDetail(f"Saved preferences at {path} must be a JSON object.")
        return {}
    return data


def save_preferences(path, data):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
