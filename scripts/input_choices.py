"""Readable asset labels and a shallow, read-only list of downloaded ZIPs."""
from collections import Counter
from pathlib import Path


def asset_choices(entries, root, symbols=False):
    names = {key: value.name for key, value in entries.items()}
    counts = Counter(names.values())
    choices = {}
    for key, value in entries.items():
        name = names[key]
        if counts[name] > 1:
            path = value.path if symbols else value
            name += " — " + Path(path).relative_to(root).as_posix()
        label, number = name, 2
        while label in choices:
            label = f"{name} [{number}]"
            number += 1
        choices[label] = key
    return choices


def downloaded_zips(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"Downloads folder not found: {folder}. Choose Folder… to select another location.")
    entries = [(path.stat().st_mtime_ns, path) for path in folder.iterdir()
               if path.suffix.lower() == ".zip" and not path.is_symlink() and path.is_file()]
    return [path for _, path in sorted(entries, key=lambda entry: (-entry[0], entry[1].name.casefold()))]
