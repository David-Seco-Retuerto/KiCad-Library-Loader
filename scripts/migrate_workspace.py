"""Copy local preferences to an independent loader without moving any assets."""
import argparse
import json
from pathlib import Path

from library_core import load_preferences
from loader_settings import LoaderSettings


def migrate_preferences(source_workspace, target_workspace):
    source = Path(source_workspace).resolve()
    target = Path(target_workspace).resolve()
    if not source.is_dir() or not target.is_dir():
        raise ValueError("Both settings workspaces must be existing folders.")
    source_file = source / ".kicad-importer.json"
    destination = target / source_file.name
    if not source_file.is_file():
        raise ValueError(f"No saved preferences found: {source_file}")
    if destination.exists():
        raise FileExistsError(f"Preferences already exist; nothing was replaced: {destination}")
    preferences = load_preferences(source_file, strict=True)
    settings = LoaderSettings.from_preferences(source, preferences)
    # Freeze relative paths against the OLD workspace before changing workspaces.
    preferences["paths"] = settings.to_preferences()
    preferences["categories"] = [category.to_preferences() for category in settings.categories]
    LoaderSettings.from_preferences(target, preferences)
    serialized = json.dumps(preferences, ensure_ascii=False, indent=2) + "\n"
    # Exclusive creation also protects against another process creating it meanwhile.
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-workspace", required=True, type=Path)
    parser.add_argument("--to-workspace", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        destination = migrate_preferences(args.from_workspace, args.to_workspace)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Migration failed: {exc}\n")
    print(f"Preferences copied to {destination}. Source settings and library assets were left unchanged.")


if __name__ == "__main__":
    main()
