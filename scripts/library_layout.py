"""Category names and native KiCad library paths; users enter base names only."""
from dataclasses import dataclass
from pathlib import Path
import re


def validate_segment(name, maximum=140):
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
    if (not isinstance(name, str) or not name or name != name.strip() or len(name) > maximum
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((".", " "))
            or name in (".", "..") or name.split(".")[0].upper() in reserved):
        raise ValueError(f"Invalid KiCad/Windows name (maximum {maximum} characters)")
    return name


def validate_base_name(name, description):
    try:
        validate_segment(name, maximum=100)
    except ValueError as exc:
        raise ValueError(f"{description}: {exc}") from exc
    if name.casefold() in {".git", ".venv", "__pycache__"} or name.startswith("."):
        raise ValueError(f"{description} cannot be a hidden or metadata folder name.")
    if name.casefold().endswith((".pretty", ".kicad_sym", ".kicad_symdir", ".kicad_mod", ".stp", ".step")):
        raise ValueError(f"{description}: enter a base name without a file extension. KiCad suffixes are added automatically.")
    return name


@dataclass(frozen=True)
class LibraryCategory:
    name: str
    library_name: str
    model_folder: str

    def validated(self):
        return LibraryCategory(validate_base_name(self.name, "Category"),
                               validate_base_name(self.library_name, "Library name"),
                               validate_base_name(self.model_folder, "3D folder"))

    def symbol_library(self, root, symbol_format):
        if symbol_format not in ("packed", "unpacked"):
            raise ValueError("Invalid symbol output format")
        suffix = ".kicad_symdir" if symbol_format == "unpacked" else ".kicad_sym"
        return Path(root) / "Symbols" / (self.library_name + suffix)

    def footprint_library(self, root):
        return Path(root) / "Footprints" / (self.library_name + ".pretty")

    def model_directory(self, root):
        return Path(root) / "3DModels" / self.model_folder

    def to_preferences(self):
        return {"name": self.name, "library_name": self.library_name, "model_folder": self.model_folder}


DEFAULT_CATEGORIES = tuple(LibraryCategory(name, f"DVL_{name}", name)
                           for name in ("ICs", "Connectors", "Power", "Misc"))


def validate_categories(categories):
    if not isinstance(categories, (tuple, list)) or not categories:
        raise ValueError("Configure at least one category.")
    if len(categories) > 100:
        raise ValueError("A maximum of 100 categories is supported.")
    validated = []
    seen = {field: set() for field in ("name", "library_name", "model_folder")}
    for category in categories:
        if not isinstance(category, LibraryCategory):
            raise ValueError("Each category must define a name, library name and 3D folder.")
        category = category.validated()
        for field, values in seen.items():
            value = getattr(category, field)
            if value.casefold() in values:
                raise ValueError(f"Duplicate {field.replace('_', ' ')}: {value}. Names must be unique, ignoring case.")
            values.add(value.casefold())
        validated.append(category)
    return tuple(validated)


def categories_from_preferences(raw):
    if not isinstance(raw, list):
        raise ValueError("Saved categories must be a JSON list.")
    categories = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each saved category must be a JSON object.")
        categories.append(LibraryCategory(item.get("name"), item.get("library_name"), item.get("model_folder", item.get("name"))))
    return validate_categories(categories)
