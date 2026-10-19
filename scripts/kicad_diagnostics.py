"""Read-only checks of saved KiCad library tables and generated asset references."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys

from library_core import child, children, prop, read_tree


@dataclass(frozen=True)
class Finding:
    level: str
    subject: str
    detail: str


@dataclass(frozen=True)
class Registration:
    nickname: str
    kind: str
    uri: str
    enabled: bool
    table: Path


def config_folders():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "kicad"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Preferences/kicad"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "kicad"
    if not base.is_dir():
        return []
    folders = [p for p in base.iterdir() if p.is_dir() and re.fullmatch(r"\d+\.\d+", p.name)]
    return sorted(folders, key=lambda p: tuple(map(int, p.name.split("."))), reverse=True)


def resolve_uri(uri, variables, project=None):
    if not isinstance(uri, str) or not uri:
        raise ValueError("The registered path is empty.")
    values = dict(variables)
    values.pop("KIPRJMOD", None)
    if project is not None:
        values["KIPRJMOD"] = str(Path(project).resolve())
    def substitute(match):
        key = match.group(1)
        if key not in values:
            if key == "KIPRJMOD":
                raise ValueError("Select the KiCad project folder to resolve ${KIPRJMOD}.")
            raise ValueError(f"Path variable {key} is undefined. Set it in KiCad Preferences > Configure Paths.")
        return str(values[key])
    expanded = uri
    for _ in range(16):
        if not re.search(r"\$\{[^}]+\}", expanded):
            break
        expanded = re.sub(r"\$\{([^}]+)\}", substitute, expanded)
    if "${" in expanded:
        raise ValueError("The registered path contains unresolved or cyclic variables.")
    path = Path(expanded)
    if not path.is_absolute():
        raise ValueError(f"Cannot resolve relative path without guessing: {uri}. Use an absolute path or ${{KIPRJMOD}}.")
    return path.resolve()


def load_registrations(path, root_tag, variables, project, findings, stack=(), optional=False):
    path = Path(path).resolve()
    if path in stack or len(stack) >= 8:
        findings.append(Finding("ERROR", "Library table", f"Cyclic or excessively nested table: {path}"))
        return {}
    if not path.is_file():
        if not optional:
            findings.append(Finding("WARNING", "Library table", f"Table not found: {path}. Its entries could not be checked."))
        return {}
    try:
        tree = read_tree(path)
        if tree[0] != root_tag:
            raise ValueError(f"Expected {root_tag}.")
        result = {}
        for row in children(tree, "lib"):
            def field(key):
                value = child(row, key)
                if value is None or len(value) != 2 or not isinstance(value[1], str):
                    raise ValueError(f"Invalid {key} in {path}")
                return str(value[1])
            entry = Registration(field("name"), field("type"), field("uri"),
                                 child(row, "disabled") is None and "disabled" not in row, path)
            if entry.kind == "Table":
                if entry.enabled:
                    try:
                        nested = resolve_uri(entry.uri, variables, project)
                        entries = load_registrations(nested, root_tag, variables, project, findings, (*stack, path))
                    except ValueError as exc:
                        findings.append(Finding("WARNING", entry.nickname, f"Linked table could not be resolved: {exc}"))
                        entries = {}
                else:
                    entries = {}
            else:
                entries = {entry.nickname: entry}
            for nickname, candidate in entries.items():
                if nickname in result:
                    findings.append(Finding("ERROR", nickname, f"Duplicate nickname in table scope: {path}. Check Manage Libraries."))
                else:
                    result[nickname] = candidate
        return result
    except (OSError, ValueError, IndexError) as exc:
        findings.append(Finding("ERROR", "Library table", f"Cannot read {path}: {exc}"))
        return {}


def diagnose(settings, symbol_format, config, project=None, category_name=None, environment=None):
    """Inspect selected output categories; never edit KiCad or library files."""
    findings = []
    config = Path(config).resolve()
    project = Path(project).resolve() if project else None
    if not config.is_dir():
        return [Finding("ERROR", "KiCad settings", f"Select an existing KiCad version configuration folder: {config}")]
    if project is not None and not project.is_dir():
        return [Finding("ERROR", "Project", f"Project folder not found: {project}")]
    if symbol_format not in ("packed", "unpacked"):
        return [Finding("ERROR", "Symbol format", "Choose a supported symbol output format.")]
    variables = {}
    common = config / "kicad_common.json"
    try:
        data = json.loads(common.read_text(encoding="utf-8-sig"))
        raw_environment = data.get("environment") or {}
        raw = raw_environment.get("vars") or {}
        if not isinstance(raw, dict):
            raise ValueError("environment.vars must be an object")
        variables.update({key: value for key, value in raw.items() if isinstance(value, str)})
    except (OSError, ValueError, AttributeError) as exc:
        findings.append(Finding("WARNING", "Path variables", f"Could not read saved variables from {common}: {exc}"))
    # A KiCad process may have a different inherited environment; the report explains this limit.
    variables.update(dict(os.environ if environment is None else environment))
    tables = {}
    for kind, filename, tag in (("symbol", "sym-lib-table", "sym_lib_table"),
                                ("footprint", "fp-lib-table", "fp_lib_table")):
        entries = load_registrations(config / filename, tag, variables, project, findings)
        if project is not None:
            entries.update(load_registrations(project / filename, tag, variables, project, findings, optional=True))
        tables[kind] = entries
    categories = [c for c in settings.categories if category_name is None or c.name == category_name]
    if not categories:
        return findings + [Finding("ERROR", "Category", "The selected category is no longer configured.")]
    match = re.match(r"(\d+)\.", config.name)
    if symbol_format == "unpacked" and match and int(match.group(1)) < 10:
        findings.append(Finding("ERROR", "KiCad version", "Unpacked .kicad_symdir output needs KiCad 10+. Select a KiCad 10+ profile, or choose packed output for KiCad 9."))

    def location(entry):
        if not entry.enabled:
            raise ValueError(f"Library {entry.nickname} is disabled in {entry.table}.")
        if entry.kind != "KiCad":
            raise ValueError(f"Expected KiCad library format, found {entry.kind} in {entry.table}.")
        return resolve_uri(entry.uri, variables, project)

    def check_registration(kind, nickname, expected):
        entries = tables[kind]
        entry = entries.get(nickname)
        if entry is None:
            aliases = []
            for candidate in entries.values():
                try:
                    if location(candidate) == expected.resolve():
                        aliases.append(candidate.nickname)
                except ValueError:
                    pass
            detail = (f"Folder/file is registered as {', '.join(aliases)}, but the loader category uses nickname {nickname}. "
                      if aliases else f"Nickname {nickname} was not found in the inspected {kind} tables. ")
            findings.append(Finding("ERROR", f"{nickname} / {kind}", detail + f"In Preferences > Manage {kind.title()} Libraries, add or correct nickname {nickname} with path {expected}."))
            return
        try:
            actual = location(entry)
            if actual != expected.resolve():
                findings.append(Finding("ERROR", f"{nickname} / {kind}", f"Registered path: {actual}. Expected: {expected}. Correct the path or select the matching output format. Table: {entry.table}"))
            else:
                findings.append(Finding("OK", f"{nickname} / {kind}", f"Nickname and path match: {actual}. Table: {entry.table}"))
        except ValueError as exc:
            findings.append(Finding("ERROR", f"{nickname} / {kind}", str(exc)))
        if not expected.exists():
            findings.append(Finding("WARNING", nickname, f"Output library does not exist yet: {expected}. Prepare folders or complete the first import."))
        elif (kind == "footprint" or symbol_format == "unpacked") and not expected.is_dir():
            findings.append(Finding("ERROR", nickname, f"Expected a library folder, but this path is a file: {expected}."))
        elif kind == "symbol" and symbol_format == "packed" and not expected.is_file():
            findings.append(Finding("ERROR", nickname, f"Packed symbols require a .kicad_sym file, not a folder: {expected}."))

    checked_footprints = set()
    def check_footprint(path):
        path = path.resolve()
        if path in checked_footprints:
            return
        checked_footprints.add(path)
        try:
            tree = read_tree(path)
            if tree[0] not in ("module", "footprint"):
                raise ValueError("Not a native footprint")
            if not children(tree, "model"):
                findings.append(Finding("INFO", path.name, "No 3D model is assigned to this footprint."))
            for model in children(tree, "model"):
                if len(model) < 2:
                    raise ValueError("Empty model reference")
                try:
                    target = resolve_uri(str(model[1]), variables, project)
                    if not target.is_file():
                        raise ValueError(f"3D file not found: {target}")
                    findings.append(Finding("OK", path.name, f"3D model exists: {target}"))
                except ValueError as exc:
                    findings.append(Finding("ERROR", path.name, f"3D reference {model[1]}: {exc}"))
        except (OSError, ValueError, IndexError) as exc:
            findings.append(Finding("ERROR", path.name, f"Cannot inspect footprint: {exc}"))

    for category in categories:
        symbol_path = category.symbol_library(settings.output_root, symbol_format)
        footprint_path = category.footprint_library(settings.output_root)
        check_registration("symbol", category.library_name, symbol_path)
        check_registration("footprint", category.library_name, footprint_path)
        if settings.model_path_mode == "variable":
            try:
                actual = resolve_uri("${" + settings.model_variable + "}", variables, project)
                if actual != settings.output_root.resolve():
                    raise ValueError(f"{settings.model_variable} points to {actual}; future imports expect {settings.output_root}.")
                findings.append(Finding("OK", "3D path variable", f"{settings.model_variable} = {actual}"))
            except ValueError as exc:
                findings.append(Finding("ERROR", "3D path variable", str(exc)))
        files = sorted(symbol_path.glob("*.kicad_sym")) if symbol_path.is_dir() else [symbol_path] if symbol_path.is_file() else []
        for path in files:
            try:
                tree = read_tree(path)
                if tree[0] != "kicad_symbol_lib":
                    raise ValueError("Not a native symbol library")
                for symbol in children(tree, "symbol"):
                    reference = str(prop(symbol, "Footprint"))
                    if not reference:
                        findings.append(Finding("INFO", path.name, "Symbol has no assigned footprint; a symbol-only import may be intentional."))
                        continue
                    if ":" not in reference:
                        raise ValueError(f"Footprint reference has no library nickname: {reference}")
                    nickname, name = reference.split(":", 1)
                    from library_core import safe_name
                    safe_name(name)
                    entry = tables["footprint"].get(nickname)
                    if entry is None:
                        raise ValueError(f"Footprint {reference} uses an unregistered nickname. Add {nickname} in Manage Footprint Libraries.")
                    target = location(entry) / f"{name}.kicad_mod"
                    if not target.is_file():
                        raise ValueError(f"Footprint {reference} not found at {target}.")
                    findings.append(Finding("OK", str(symbol[1]), f"Assigned footprint exists: {reference}"))
                    check_footprint(target)
            except (OSError, ValueError, IndexError) as exc:
                findings.append(Finding("ERROR", path.name, f"Cannot resolve symbol references: {exc}"))
        if footprint_path.is_dir():
            for path in sorted(footprint_path.glob("*.kicad_mod")):
                check_footprint(path)
    return findings


def format_report(findings):
    errors = sum(item.level == "ERROR" for item in findings)
    warnings = sum(item.level == "WARNING" for item in findings)
    lines = [f"{errors} error(s), {warnings} warning(s). Saved configuration and file paths only."]
    lines.extend(f"[{item.level}] {item.subject}\n{item.detail}" for item in findings)
    return "\n\n".join(lines)
