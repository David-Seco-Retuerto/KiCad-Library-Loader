"""Independent local input folders and output-library root, persisted as JSON."""
from dataclasses import dataclass
from pathlib import Path
import re

from providers import PROVIDERS
from library_layout import DEFAULT_CATEGORIES, categories_from_preferences, validate_categories

MODEL_PATH_MODES = {
    "variable": "KiCad path variable (portable)",
    "absolute": "Absolute file paths (this computer)",
}


def folder_path(value, base, description):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError(f"{description} must be a non-empty folder path.")
    path = Path(str(value).strip()).expanduser()
    if not path.is_absolute():
        path = Path(base) / path
    path = path.resolve()
    # Walk existing ancestors too, so a new folder below a file is rejected.
    for parent in (path, *path.parents):
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"{description} is not a folder: {parent}")
    return path


def overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def validate_model_paths(mode, variable):
    if not isinstance(mode, str) or mode not in MODEL_PATH_MODES:
        raise ValueError("Choose a valid 3D model path style.")
    valid = isinstance(variable, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable)
    if mode == "variable":
        if not valid:
            raise ValueError("The KiCad path variable must contain letters, numbers or underscores and cannot start with a number.")
        if variable == "KIPRJMOD" or variable.startswith("KICAD"):
            raise ValueError("Use a custom KiCad path variable, rather than KIPRJMOD or a KICAD-prefixed built-in variable.")
    return variable if valid else "DVL_LIB_ROOT"


def validate_output_layout(output_root, input_roots):
    """Protect source folders, metadata and resolved paths, including junctions."""
    output_root = Path(output_root).resolve()
    if any(part.casefold() in {".git", ".venv", "__pycache__"} for part in output_root.parts):
        raise ValueError("Choose a library output folder outside Git metadata and Python environments.")
    for name in ("Symbols", "Footprints", "3DModels"):
        destination = (output_root / name).resolve()
        if not destination.is_relative_to(output_root):
            raise ValueError(f"Output folder resolves outside the selected library root: {destination}")
        if destination.exists() and not destination.is_dir():
            raise ValueError(f"Output folder is a file: {destination}")
        for source in input_roots:
            source = Path(source).resolve()
            if overlaps(destination, source):
                raise ValueError(f"Input folder {source} overlaps output folder {destination}. "
                                 "Choose separate input and output asset folders.")


@dataclass(frozen=True)
class LoaderSettings:
    sources: dict
    output_root: Path
    model_path_mode: str = "variable"
    model_variable: str = "DVL_LIB_ROOT"
    categories: tuple = DEFAULT_CATEGORIES

    @classmethod
    def defaults(cls, workspace):
        workspace = Path(workspace).resolve()
        return cls({key: provider.default_folder(workspace) for key, provider in PROVIDERS.items()}, workspace)

    @classmethod
    def from_preferences(cls, workspace, preferences):
        defaults = cls.defaults(workspace)
        raw = preferences.get("paths", {})
        if not isinstance(raw, dict):
            raise ValueError("Saved path settings must be a JSON object. Open Settings to correct them.")
        sources = raw.get("sources", {})
        if not isinstance(sources, dict):
            raise ValueError("Saved source paths must be a JSON object. Open Settings to correct them.")
        return cls(
            {key: sources.get(key, path) for key, path in defaults.sources.items()},
            raw.get("output_root", defaults.output_root),
            raw.get("model_path_mode", defaults.model_path_mode),
            raw.get("model_variable", defaults.model_variable),
            categories_from_preferences(preferences["categories"]) if "categories" in preferences else defaults.categories,
        ).validated(workspace)

    def validated(self, workspace):
        if not isinstance(self.sources, dict) or set(self.sources) != set(PROVIDERS):
            raise ValueError("Configure an input folder for every source provider.")
        sources = {key: folder_path(value, workspace, f"{key} input") for key, value in self.sources.items()}
        output = folder_path(self.output_root, workspace, "Library output")
        variable = validate_model_paths(self.model_path_mode, self.model_variable)
        categories = validate_categories(self.categories)
        validate_output_layout(output, (*sources.values(), Path(workspace).resolve() / "Imports"))
        return LoaderSettings(sources, output, self.model_path_mode, variable, categories)

    def get_category(self, name):
        return next((category for category in self.categories if category.name == name), None)

    def to_preferences(self):
        return {"sources": {key: str(path) for key, path in self.sources.items()},
                "output_root": str(self.output_root), "model_path_mode": self.model_path_mode,
                "model_variable": self.model_variable}
